"""Per-case execution traces: the waterfall behind every scored prediction.

A run writes ``trace.jsonl`` next to ``predictions.jsonl``. One line per case,
each holding an ordered list of spans:

    {"case_id": "FIN-0001",
     "total_ms": 812.4,
     "spans": [{"name": "provider_call", "duration_ms": 800.1, ...},
               {"name": "score", "duration_ms": 1.2, ...}]}

Design rules:

* Spans are wall-clock measurements taken by the runner — never estimates.
* A span that failed still lands in the trace with ``status="error"`` and its
  error text, because "the provider took 30s and then failed" is the single
  most useful fact when a run looks wrong.
* Traces are optional at read time: runs written before this module existed
  simply have no trace file, and callers get an empty list rather than a 500.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

TRACE_FILENAME = "trace.jsonl"

#: Span names emitted by the runner. Kept as constants so the UI can colour
#: them without duplicating string literals.
SPAN_PROVIDER_CALL = "provider_call"
SPAN_SCORE = "score"
SPAN_JUDGE = "judge"
SPAN_PROMPT_BUILD = "prompt_build"

SPAN_LABELS: dict[str, str] = {
    SPAN_PROVIDER_CALL: "Provider call",
    SPAN_SCORE: "Parse & score",
    SPAN_JUDGE: "Judge",
    SPAN_PROMPT_BUILD: "Prompt build",
}


@dataclass
class Span:
    """One timed step inside a single case."""

    name: str
    duration_ms: float
    status: str = "ok"  # ok | error
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "duration_ms": round(self.duration_ms, 3),
            "status": self.status,
        }
        if self.detail:
            payload["detail"] = self.detail
        return payload


@dataclass
class CaseTrace:
    """All spans for one case, in execution order."""

    case_id: str
    spans: list[Span] = field(default_factory=list)

    @property
    def total_ms(self) -> float:
        return sum(span.duration_ms for span in self.spans)

    @property
    def ok(self) -> bool:
        return all(span.status != "error" for span in self.spans)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "total_ms": round(self.total_ms, 3),
            "ok": self.ok,
            "spans": [span.to_dict() for span in self.spans],
        }


class TraceRecorder:
    """Collects case traces during a run, then writes them once.

    Measuring with ``perf_counter`` around each step keeps the runner honest:
    no span duration is derived from provider-reported numbers alone, so a
    provider that under-reports latency still shows its true wall-clock cost.
    """

    def __init__(self) -> None:
        self._traces: list[CaseTrace] = []

    def case(self, case_id: str) -> _CaseSpanBuilder:
        return _CaseSpanBuilder(self, case_id)

    def record(self, trace: CaseTrace) -> None:
        self._traces.append(trace)

    @property
    def traces(self) -> list[CaseTrace]:
        return list(self._traces)

    def write(self, run_dir: Path) -> Path:
        path = run_dir / TRACE_FILENAME
        lines = [json.dumps(t.to_dict(), sort_keys=False) for t in self._traces]
        path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        return path


class _CaseSpanBuilder:
    """Context manager that times one span and appends it to its case."""

    def __init__(self, recorder: TraceRecorder, case_id: str) -> None:
        self._recorder = recorder
        self._trace = CaseTrace(case_id=case_id)

    def __enter__(self) -> _CaseSpanBuilder:
        return self

    def __exit__(self, *exc: object) -> bool:
        self._recorder.record(self._trace)
        return False

    def add(self, name: str, duration_ms: float, *, error: str | None = None,
            detail: dict[str, Any] | None = None) -> Span:
        span = Span(
            name=name,
            duration_ms=max(0.0, duration_ms),
            status="error" if error else "ok",
            detail=dict(detail or {}),
        )
        if error:
            span.detail["error"] = error
        self._trace.spans.append(span)
        return span


class SpanProxyProvider:
    """Wraps a provider so every ``predict_text`` call becomes a judge span.

    The scoring path only knows ``judge_provider.predict_text(prompt)``; it
    has no hook for timing. Wrapping instead of editing the scorer keeps the
    judge logic untouched while still capturing how long judging really took.
    """

    def __init__(
        self,
        inner: Any,
        builder: _CaseSpanBuilder,
        name: str = SPAN_JUDGE,
        on_ms: Any = None,
    ) -> None:
        self._inner = inner
        self._builder = builder
        self._name = name
        self._on_ms = on_ms
        # Delegated so scorers can read provider identity without special cases.
        self.name = getattr(inner, "name", "judge")
        self.model = getattr(inner, "model", "")

    def predict_text(self, prompt: str, **kwargs: Any) -> Any:
        started = time.perf_counter()
        try:
            result = self._inner.predict_text(prompt, **kwargs)
        except Exception as exc:
            elapsed = (time.perf_counter() - started) * 1000.0
            self._builder.add(self._name, elapsed, error=str(exc))
            if self._on_ms is not None:
                self._on_ms(elapsed)
            raise
        elapsed = (time.perf_counter() - started) * 1000.0
        self._builder.add(self._name, elapsed)
        if self._on_ms is not None:
            self._on_ms(elapsed)
        return result

    def __getattr__(self, item: str) -> Any:
        return getattr(self._inner, item)


def read_traces(run_dir: Path) -> list[dict[str, Any]]:
    """Traces for one run; ``[]`` for runs written before tracing existed."""
    path = run_dir / TRACE_FILENAME
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def summarise_traces(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate a run's traces for the modal header (mean/p50/p95 per span)."""
    if not traces:
        return {"n_cases": 0}
    totals = sorted(t.get("total_ms", 0.0) for t in traces)
    per_span: dict[str, list[float]] = {}
    errors = 0
    for trace in traces:
        if not trace.get("ok", True):
            errors += 1
        for span in trace.get("spans", []):
            per_span.setdefault(span.get("name", "?"), []).append(
                float(span.get("duration_ms", 0.0))
            )

    def _pct(values: list[float], q: float) -> float:
        if not values:
            return 0.0
        index = min(len(values) - 1, max(0, int(round(q * (len(values) - 1)))))
        return round(sorted(values)[index], 3)

    return {
        "n_cases": len(totals),
        "errors": errors,
        "total_ms": round(sum(totals), 3),
        "mean_ms": round(sum(totals) / len(totals), 3),
        "p50_ms": _pct(totals, 0.50),
        "p95_ms": _pct(totals, 0.95),
        "spans": {
            name: {
                "count": len(values),
                "mean_ms": round(sum(values) / len(values), 3),
                "p95_ms": _pct(values, 0.95),
            }
            for name, values in sorted(per_span.items())
        },
    }


__all__ = [
    "TRACE_FILENAME",
    "SPAN_LABELS",
    "SPAN_PROVIDER_CALL",
    "SPAN_SCORE",
    "SPAN_JUDGE",
    "SPAN_PROMPT_BUILD",
    "CaseTrace",
    "Span",
    "TraceRecorder",
    "SpanProxyProvider",
    "read_traces",
    "summarise_traces",
]

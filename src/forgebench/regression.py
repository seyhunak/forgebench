"""Regression view: what changed between a run and its baseline.

Two independent questions, both answered here:

1. *Did the metrics move?* Scalar deltas from ``metrics.json``.
2. *Which cases flipped?* Per-case verdicts from ``predictions.jsonl`` joined
   on ``case_id`` — because a metric that moved by 0.02 is unreadable, while
   "FIN-0007 regressed, FIN-0012 improved" is a bug report.

Baselines are pinned per *dataset* in ``runs/baselines.json`` (local state:
``runs/`` is git-ignored, so a pin never leaks into a diff or a CI run).
Pinning by dataset rather than by config is deliberate — the baseline answers
"did this dataset's score get better", which is the comparison that survives
provider and prompt changes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .schemas import PredictionRecord

BASELINES_FILENAME = "baselines.json"

VERDICT_IMPROVED = "improved"
VERDICT_REGRESSED = "regressed"
VERDICT_SAME_CORRECT = "unchanged_correct"
VERDICT_SAME_WRONG = "unchanged_wrong"
VERDICT_ADDED = "added"
VERDICT_REMOVED = "removed"


@dataclass
class CaseDelta:
    """One case's movement from baseline to candidate."""

    case_id: str
    verdict: str
    baseline_correct: bool | None = None
    candidate_correct: bool | None = None
    scenario_family: str | None = None

    @property
    def flipped(self) -> bool:
        return self.verdict in (VERDICT_IMPROVED, VERDICT_REGRESSED)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "verdict": self.verdict,
            "baseline_correct": self.baseline_correct,
            "candidate_correct": self.candidate_correct,
            "scenario_family": self.scenario_family,
        }


@dataclass
class RegressionReport:
    """Structured comparison, ready to be serialised straight to the UI."""

    baseline_run: str
    candidate_run: str
    dataset: str | None = None
    cases: list[CaseDelta] = field(default_factory=list)
    metrics: dict[str, dict[str, float | None]] = field(default_factory=dict)
    unreadable: dict[str, int] = field(default_factory=dict)

    def counts(self) -> dict[str, int]:
        tallies = {
            VERDICT_IMPROVED: 0,
            VERDICT_REGRESSED: 0,
            VERDICT_SAME_CORRECT: 0,
            VERDICT_SAME_WRONG: 0,
            VERDICT_ADDED: 0,
            VERDICT_REMOVED: 0,
        }
        for case in self.cases:
            tallies[case.verdict] = tallies.get(case.verdict, 0) + 1
        return tallies

    @property
    def verdict(self) -> str:
        """One-word answer: did the candidate beat, lose to, or match baseline?"""
        improved = self.counts().get(VERDICT_IMPROVED, 0)
        regressed = self.counts().get(VERDICT_REGRESSED, 0)
        if regressed > improved:
            return "regressed"
        if improved > regressed:
            return "improved"
        return "unchanged"

    def to_dict(self) -> dict[str, Any]:
        # Regressions first: the reader's eye should land on what broke.
        order = {
            VERDICT_REGRESSED: 0,
            VERDICT_IMPROVED: 1,
            VERDICT_REMOVED: 2,
            VERDICT_ADDED: 3,
            VERDICT_SAME_WRONG: 4,
            VERDICT_SAME_CORRECT: 5,
        }
        cases = sorted(self.cases, key=lambda c: (order.get(c.verdict, 9), c.case_id))
        return {
            "baseline_run": self.baseline_run,
            "candidate_run": self.candidate_run,
            "dataset": self.dataset,
            "verdict": self.verdict,
            "counts": self.counts(),
            "metrics": self.metrics,
            "unreadable": self.unreadable,
            "cases": [case.to_dict() for case in cases],
        }


def read_prediction_index(run_dir: Path) -> tuple[dict[str, PredictionRecord], int]:
    """case_id -> record, plus how many lines could not be parsed.

    Tolerant on purpose: one damaged line in a large run should degrade the
    comparison (via ``unreadable``) instead of refusing to run at all.
    """
    path = run_dir / "predictions.jsonl"
    index: dict[str, PredictionRecord] = {}
    unreadable = 0
    if not path.is_file():
        return index, unreadable
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = PredictionRecord.model_validate_json(line)
        except Exception:  # noqa: BLE001 - count it, keep comparing
            unreadable += 1
            continue
        index[record.case_id] = record
    return index, unreadable


def _scalar_metrics(run_dir: Path) -> dict[str, float]:
    path = run_dir / "metrics.json"
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    scalars: dict[str, float] = {}
    if not isinstance(raw, dict):
        return scalars

    def walk(prefix: str, value: Any) -> None:
        if isinstance(value, bool):
            return
        if isinstance(value, (int, float)):
            scalars[prefix] = float(value)
        elif isinstance(value, dict):
            for key, nested in value.items():
                walk(f"{prefix}.{key}" if prefix else str(key), nested)

    for key, value in raw.items():
        walk(str(key), value)
    return scalars


def _run_label(run_dir: Path) -> str:
    return run_dir.name


def compare_runs(baseline_dir: Path, candidate_dir: Path) -> RegressionReport:
    """Compare two run directories case by case and metric by metric."""
    baseline, baseline_bad = read_prediction_index(baseline_dir)
    candidate, candidate_bad = read_prediction_index(candidate_dir)

    cases: list[CaseDelta] = []
    for case_id in sorted(set(baseline) | set(candidate)):
        before = baseline.get(case_id)
        after = candidate.get(case_id)
        before_correct = before.correct if before is not None else None
        after_correct = after.correct if after is not None else None
        family = (after or before).scenario_family if (after or before) else None

        if before is None:
            verdict = VERDICT_ADDED
        elif after is None:
            verdict = VERDICT_REMOVED
        elif before_correct and after_correct:
            verdict = VERDICT_SAME_CORRECT
        elif (not before_correct) and (not after_correct):
            verdict = VERDICT_SAME_WRONG
        elif (not before_correct) and after_correct:
            verdict = VERDICT_IMPROVED
        else:
            verdict = VERDICT_REGRESSED

        cases.append(
            CaseDelta(
                case_id=case_id,
                verdict=verdict,
                baseline_correct=before_correct,
                candidate_correct=after_correct,
                scenario_family=family,
            )
        )

    base_metrics = _scalar_metrics(baseline_dir)
    cand_metrics = _scalar_metrics(candidate_dir)
    metrics: dict[str, dict[str, float | None]] = {}
    for key in sorted(set(base_metrics) | set(cand_metrics)):
        before = base_metrics.get(key)
        after = cand_metrics.get(key)
        metrics[key] = {
            "baseline": before,
            "candidate": after,
            "delta": None if before is None or after is None else round(after - before, 6),
        }

    dataset = run_dataset_name(baseline_dir) or run_dataset_name(candidate_dir)
    unreadable = {"baseline": baseline_bad, "candidate": candidate_bad}
    return RegressionReport(
        baseline_run=_run_label(baseline_dir),
        candidate_run=_run_label(candidate_dir),
        dataset=dataset,
        cases=cases,
        metrics=metrics,
        unreadable=unreadable,
    )


def run_dataset_name(run_dir: Path) -> str | None:
    """Dataset name from a run's manifest (``None`` when unreadable)."""
    manifest = run_dir / "manifest.json"
    if not manifest.is_file():
        return None
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    dataset = data.get("dataset")
    if isinstance(dataset, dict):
        return str(dataset.get("name") or "") or None
    return str(dataset) if dataset else None


# ---------------------------------------------------------------------------
# Baseline pins (runs/baselines.json)
# ---------------------------------------------------------------------------


def baselines_path(runs_root: Path) -> Path:
    return runs_root / BASELINES_FILENAME


def list_baselines(runs_root: Path) -> dict[str, dict[str, Any]]:
    """``{dataset: pin}`` for every pinned baseline; ``{}`` when none/partial."""
    path = baselines_path(runs_root)
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return raw if isinstance(raw, dict) else {}


def _write_baselines(runs_root: Path, pins: dict[str, dict[str, Any]]) -> None:
    runs_root.mkdir(parents=True, exist_ok=True)
    path = baselines_path(runs_root)
    if pins:
        path.write_text(json.dumps(pins, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    elif path.is_file():
        path.unlink()


def pin_baseline(
    dataset: str, run_dir: Path, runs_root: Path, *, manifest: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Pin ``run_dir`` as the baseline for ``dataset`` (replacing any pin)."""
    if manifest is None:
        manifest_path = run_dir / "manifest.json"
        manifest = (
            json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
        )
    provider = manifest.get("provider") or {}
    pin = {
        "run_id": run_dir.name,
        "dataset_version": (manifest.get("dataset") or {}).get("version"),
        "provider": provider.get("name"),
        "model": provider.get("model"),
        "created_at_utc": manifest.get("created_at_utc"),
        "pinned_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    pins = list_baselines(runs_root)
    pins[dataset] = pin
    _write_baselines(runs_root, pins)
    return pin


def clear_baseline(dataset: str, runs_root: Path) -> bool:
    """Drop the pin for ``dataset``. Returns whether anything was removed."""
    pins = list_baselines(runs_root)
    if dataset not in pins:
        return False
    del pins[dataset]
    _write_baselines(runs_root, pins)
    return True


__all__ = [
    "BASELINES_FILENAME",
    "CaseDelta",
    "RegressionReport",
    "VERDICT_ADDED",
    "VERDICT_IMPROVED",
    "VERDICT_REMOVED",
    "VERDICT_REGRESSED",
    "VERDICT_SAME_CORRECT",
    "VERDICT_SAME_WRONG",
    "baselines_path",
    "clear_baseline",
    "compare_runs",
    "list_baselines",
    "pin_baseline",
    "read_prediction_index",
    "run_dataset_name",
]

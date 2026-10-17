"""Tracing: spans are measured, written, read back, and aggregated."""

from __future__ import annotations

import json

from forgebench.tracing import (
    SPAN_PROVIDER_CALL,
    SPAN_SCORE,
    TRACE_FILENAME,
    CaseTrace,
    Span,
    TraceRecorder,
    read_traces,
    summarise_traces,
)


def test_recorder_writes_one_json_line_per_case(tmp_path):
    recorder = TraceRecorder()
    with recorder.case("FIN-0001") as trace:
        trace.add(SPAN_PROVIDER_CALL, 800.0, detail={"input_tokens": 120})
        trace.add(SPAN_SCORE, 1.5)
    with recorder.case("FIN-0002") as trace:
        trace.add(SPAN_PROVIDER_CALL, 300.0)

    path = recorder.write(tmp_path)
    assert path.name == TRACE_FILENAME
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 2

    first = json.loads(lines[0])
    assert first["case_id"] == "FIN-0001"
    assert first["total_ms"] == 801.5
    assert first["ok"] is True
    assert first["spans"][0]["name"] == SPAN_PROVIDER_CALL
    assert first["spans"][0]["detail"]["input_tokens"] == 120


def test_failed_span_is_recorded_with_its_error(tmp_path):
    recorder = TraceRecorder()
    with recorder.case("FIN-0003") as trace:
        trace.add(
            SPAN_PROVIDER_CALL,
            1200.0,
            error="rate limited",
            detail={"provider": "openrouter"},
        )

    recorder.write(tmp_path)
    (trace_record,) = read_traces(tmp_path)
    assert trace_record["ok"] is False
    span = trace_record["spans"][0]
    assert span["status"] == "error"
    assert span["detail"]["error"] == "rate limited"
    assert span["detail"]["provider"] == "openrouter"


def test_missing_trace_file_reads_as_empty(tmp_path):
    # Runs written before tracing existed must not 500 the API.
    assert read_traces(tmp_path) == []


def test_summary_reports_percentiles_and_per_span_stats():
    traces = []
    for i in range(10):
        traces.append(
            CaseTrace(
                case_id=f"C-{i}",
                spans=[
                    Span(name=SPAN_PROVIDER_CALL, duration_ms=100.0 * (i + 1)),
                    Span(name=SPAN_SCORE, duration_ms=1.0),
                ],
            ).to_dict()
        )
    summary = summarise_traces(traces)

    assert summary["n_cases"] == 10
    assert summary["total_ms"] == sum(100.0 * (i + 1) + 1.0 for i in range(10))
    assert summary["mean_ms"] == summary["total_ms"] / 10
    assert summary["p95_ms"] == 1001.0
    assert summary["spans"][SPAN_PROVIDER_CALL]["count"] == 10
    assert summary["spans"][SPAN_PROVIDER_CALL]["mean_ms"] == 550.0


def test_empty_summary_is_safe():
    assert summarise_traces([]) == {"n_cases": 0}


def test_run_artifacts_include_trace(tmp_path, mock_config, tiny_dataset, monkeypatch):
    """The runner's wiring: every case gets provider + score spans on disk."""
    from types import SimpleNamespace

    from forgebench.runner import run_experiment

    class FakeProvider:
        name = "fake"
        model = "fake-1"

        def predict(self, case):  # noqa: ANN001 - case shape is runner-internal
            return SimpleNamespace(
                content='{"category": "matched", "requires_review": false}',
                latency_ms=42.0,
                input_tokens=10,
                output_tokens=5,
            )

    # No network in tests: replace provider construction, keep the real loop.
    monkeypatch.setattr(
        "forgebench.runner._make_provider", lambda cfg, ex, system_text=None: FakeProvider()
    )

    result = run_experiment(
        mock_config,
        datasets_root=tiny_dataset,
        output_root=tmp_path,
        limit=3,
        run_id="trace-test",
    )
    trace_path = result.run_dir / TRACE_FILENAME
    assert trace_path.is_file()

    traces = read_traces(result.run_dir)
    assert len(traces) == 3
    # Every case must expose both the provider call and the scoring step.
    for record in traces:
        names = [span["name"] for span in record["spans"]]
        assert names == [SPAN_PROVIDER_CALL, SPAN_SCORE]
        assert record["total_ms"] >= 0
        provider_span = record["spans"][0]
        assert provider_span["detail"]["reported_ms"] == 42.0
        assert provider_span["detail"]["input_tokens"] == 10

    manifest = json.loads((result.run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["trace"] == {"file": TRACE_FILENAME, "n_cases": 3}

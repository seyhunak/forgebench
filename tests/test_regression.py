"""Regression view: per-case verdicts, metric deltas, and baseline pins."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from forgebench.regression import (
    VERDICT_ADDED,
    VERDICT_IMPROVED,
    VERDICT_REGRESSED,
    VERDICT_REMOVED,
    VERDICT_SAME_CORRECT,
    VERDICT_SAME_WRONG,
    clear_baseline,
    compare_runs,
    list_baselines,
    pin_baseline,
    read_prediction_index,
)
from forgebench.schemas import Category, PredictionRecord


def _record(case_id: str, correct: bool, *, family: str = "finance") -> PredictionRecord:
    return PredictionRecord(
        case_id=case_id,
        scenario_family=family,
        ok=True,
        category=Category.MATCHED,
        requires_review=False,
        expected_category=Category.MATCHED,
        expected_requires_review=False,
        correct=correct,
        raw_content='{"category": "matched", "requires_review": false}',
        latency_ms=10.0,
    )


def _write_run(
    directory: Path,
    records: list[PredictionRecord],
    *,
    metrics: dict | None = None,
    dataset: str = "finance_v1",
    dataset_version: str = "1.0.0",
    manifest_extra: dict | None = None,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "predictions.jsonl").write_text(
        "".join(r.model_dump_json() + "\n" for r in records), encoding="utf-8"
    )
    (directory / "metrics.json").write_text(
        json.dumps(metrics if metrics is not None else {"accuracy": 0.5}), encoding="utf-8"
    )
    manifest = {
        "run_id": directory.name,
        "dataset": {"name": dataset, "version": dataset_version, "split": "test"},
        "provider": {"name": "openrouter", "model": "openai/gpt-4o-mini"},
        "created_at_utc": "2026-10-17T00:00:00+00:00",
        **(manifest_extra or {}),
    }
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return directory


def test_every_case_verdict_is_classified(tmp_path: Path) -> None:
    baseline = _write_run(
        tmp_path / "base",
        [
            _record("C-same-ok", True),
            _record("C-same-bad", False),
            _record("C-regressed", True),
            _record("C-improved", False),  # wrong at baseline, fixed later
            _record("C-removed", True),
        ],
        metrics={"accuracy": 0.75},
    )
    candidate = _write_run(
        tmp_path / "cand",
        [
            _record("C-same-ok", True),
            _record("C-same-bad", False),
            _record("C-regressed", False),
            _record("C-improved", True),
            _record("C-added", True),
        ],
        metrics={"accuracy": 0.60},
    )

    report = compare_runs(baseline, candidate)
    verdicts = {case.case_id: case.verdict for case in report.cases}
    assert verdicts == {
        "C-same-ok": VERDICT_SAME_CORRECT,
        "C-same-bad": VERDICT_SAME_WRONG,
        "C-regressed": VERDICT_REGRESSED,
        "C-improved": VERDICT_IMPROVED,
        "C-removed": VERDICT_REMOVED,
        "C-added": VERDICT_ADDED,
    }
    counts = report.counts()
    assert counts[VERDICT_IMPROVED] == 1
    assert counts[VERDICT_REGRESSED] == 1
    assert counts[VERDICT_REMOVED] == 1
    assert counts[VERDICT_ADDED] == 1
    # Equal numbers of improvements and regressions -> the run merely matched.
    assert report.verdict == "unchanged"


def test_verdict_reflects_the_balance_of_flips(tmp_path: Path) -> None:
    baseline = _write_run(
        tmp_path / "base",
        [_record("A", False), _record("B", False), _record("C", True)],
    )
    better = _write_run(
        tmp_path / "better", [_record("A", True), _record("B", True), _record("C", True)]
    )
    worse = _write_run(
        tmp_path / "worse", [_record("A", False), _record("B", False), _record("C", False)]
    )

    assert compare_runs(baseline, better).verdict == "improved"
    assert compare_runs(baseline, worse).verdict == "regressed"


def test_metric_deltas_are_computed_and_rounded(tmp_path: Path) -> None:
    baseline = _write_run(
        tmp_path / "base",
        [_record("A", True)],
        metrics={"accuracy": 0.5, "latency": {"mean_ms": 100.0}, "flagged": True},
    )
    candidate = _write_run(
        tmp_path / "cand",
        [_record("A", True)],
        metrics={"accuracy": 0.75, "latency": {"mean_ms": 125.5}, "flagged": True},
    )

    metrics = compare_runs(baseline, candidate).metrics
    assert metrics["accuracy"]["baseline"] == 0.5
    assert metrics["accuracy"]["candidate"] == 0.75
    assert metrics["accuracy"]["delta"] == 0.25
    assert metrics["latency.mean_ms"]["delta"] == 25.5
    # Bools are not metrics: True/False must never surface as a 1/0 delta.
    assert "flagged" not in metrics


def test_report_serialises_for_the_ui(tmp_path: Path) -> None:
    baseline = _write_run(tmp_path / "base", [_record("A", True)])
    candidate = _write_run(tmp_path / "cand", [_record("A", False)])

    payload = compare_runs(baseline, candidate).to_dict()
    assert payload["baseline_run"] == "base"
    assert payload["candidate_run"] == "cand"
    assert payload["dataset"] == "finance_v1"
    assert payload["verdict"] == "regressed"
    assert payload["counts"][VERDICT_REGRESSED] == 1
    # Regressions sort first so the eye lands on what broke.
    assert payload["cases"][0]["case_id"] == "A"
    assert set(payload["cases"][0]) == {
        "case_id",
        "verdict",
        "baseline_correct",
        "candidate_correct",
        "scenario_family",
    }


def test_unreadable_prediction_lines_are_counted_not_fatal(tmp_path: Path) -> None:
    baseline = _write_run(tmp_path / "base", [_record("A", True)])
    candidate = _write_run(tmp_path / "cand", [_record("A", True)])
    with (candidate / "predictions.jsonl").open("a", encoding="utf-8") as handle:
        handle.write('{"case_id": "truncated", \n')

    report = compare_runs(baseline, candidate)
    assert report.unreadable == {"baseline": 0, "candidate": 1}
    assert len(report.cases) == 1


def test_missing_predictions_files_compare_as_empty(tmp_path: Path) -> None:
    baseline = tmp_path / "base"
    candidate = tmp_path / "cand"
    baseline.mkdir()
    candidate.mkdir()
    report = compare_runs(baseline, candidate)
    assert report.cases == []
    assert report.metrics == {}
    assert report.verdict == "unchanged"


def test_read_prediction_index_keeps_last_write_per_case(tmp_path: Path) -> None:
    run = _write_run(tmp_path / "run", [_record("A", False), _record("A", True)])
    index, bad = read_prediction_index(run)
    assert bad == 0
    assert index["A"].correct is True


def test_pins_are_stored_per_dataset_and_round_trip(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    run = _write_run(runs_root / "run-1", [_record("A", True)], dataset="finance_v1")

    pin = pin_baseline("finance_v1", run, runs_root)
    assert pin["run_id"] == "run-1"
    assert pin["provider"] == "openrouter"
    assert pin["pinned_at"]
    assert (runs_root / "baselines.json").is_file()

    pins = list_baselines(runs_root)
    assert pins["finance_v1"]["run_id"] == "run-1"

    # A second pin for the same dataset replaces the first, not the file.
    other = _write_run(runs_root / "run-2", [_record("A", True)], dataset="finance_v1")
    pin_baseline("finance_v1", other, runs_root)
    assert list_baselines(runs_root)["finance_v1"]["run_id"] == "run-2"

    assert clear_baseline("finance_v1", runs_root) is True
    assert list_baselines(runs_root) == {}
    assert clear_baseline("finance_v1", runs_root) is False


def test_corrupt_baselines_file_reads_as_no_pins(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    (runs_root / "baselines.json").write_text("{not json", encoding="utf-8")
    assert list_baselines(runs_root) == {}


def test_run_dataset_name_comes_from_the_manifest(tmp_path: Path) -> None:
    from forgebench.regression import run_dataset_name

    run = _write_run(tmp_path / "run", [], dataset="legal_v1", dataset_version="2.0.0")
    assert run_dataset_name(run) == "legal_v1"
    assert run_dataset_name(tmp_path / "missing") is None


@pytest.fixture()
def two_runs(tmp_path: Path) -> tuple[Path, Path, Path]:
    """(runs_root, baseline, candidate) — one regression, one improvement."""
    runs_root = tmp_path / "runs"
    baseline = _write_run(
        runs_root / "base-run",
        [_record("A", True), _record("B", False)],
        metrics={"accuracy": 0.5},
    )
    candidate = _write_run(
        runs_root / "cand-run",
        [_record("A", False), _record("B", True)],
        metrics={"accuracy": 0.5},
    )
    return runs_root, baseline, candidate


def test_api_baseline_pin_and_regression_flow(two_runs, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("fastapi")

    from starlette.testclient import TestClient

    from forgebench import api
    from forgebench.api import app

    runs_root, baseline, candidate = two_runs
    runs = {baseline.name: baseline, candidate.name: candidate}

    # Keep the test inside tmp_path: the real runs/ must not be touched.
    monkeypatch.setattr(
        api,
        "_resolve_run_dir",
        lambda run_id: runs.get(str(run_id).removeprefix("runs/")),
    )
    monkeypatch.setattr(api, "_runs_root", lambda: runs_root)

    client = TestClient(app)

    # Nothing pinned yet: the endpoint explains what to do instead of 500ing.
    assert client.get("/api/baselines").json() == {}
    missing = client.get(f"/api/runs/{candidate.name}/regression")
    assert missing.status_code == 404
    assert "pin" in missing.json()["detail"]

    # Pin the baseline, then the comparison resolves without an explicit id.
    pinned = client.post("/api/baselines", json={"dataset": "finance_v1", "run_id": candidate.name})
    assert pinned.status_code == 201
    # Pinning the *candidate* would compare it with itself — reject that.
    assert client.get(f"/api/runs/{candidate.name}/regression").status_code == 400

    pinned = client.post("/api/baselines", json={"dataset": "finance_v1", "run_id": "base-run"})
    assert pinned.status_code == 201
    assert client.get("/api/baselines").json()["finance_v1"]["run_id"] == "base-run"

    report = client.get(f"/api/runs/{candidate.name}/regression")
    assert report.status_code == 200
    payload = report.json()
    assert payload["verdict"] == "unchanged"  # one flipped each way
    assert payload["counts"][VERDICT_REGRESSED] == 1
    assert payload["counts"][VERDICT_IMPROVED] == 1

    # An explicit baseline id wins over the pin.
    other = client.get(f"/api/runs/{candidate.name}/regression?baseline=base-run")
    assert other.status_code == 200

    assert client.delete("/api/baselines/finance_v1").status_code == 200
    assert client.delete("/api/baselines/finance_v1").status_code == 404
    assert client.get("/api/baselines").json() == {}


def test_api_regression_of_unknown_run_is_404(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("fastapi")

    from starlette.testclient import TestClient

    from forgebench import api
    from forgebench.api import app

    monkeypatch.setattr(api, "_resolve_run_dir", lambda run_id: None)
    monkeypatch.setattr(api, "_runs_root", lambda: Path("/nonexistent"))

    client = TestClient(app)
    assert client.get("/api/runs/ghost/regression").status_code == 404
    pin = client.post("/api/baselines", json={"dataset": "x", "run_id": "ghost"})
    assert pin.status_code == 404

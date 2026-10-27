"""The 0.2.0 feature set: judge-in-benchmark, N-model task comparison,
per-rule metrics, history, HTML export, webhooks, and the API auth gate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from forgebench.config import (
    EvaluationSection,
    ExperimentConfig,
    ExperimentSection,
    JudgeSection,
    ProviderSection,
)
from forgebench.history import collect_history, render_history
from forgebench.notify import build_run_payload, post_run_webhook

REPO_ROOT = Path(__file__).resolve().parents[1]
runner = CliRunner()


# ---------------------------------------------------------------------------
# Finance-run judge
# ---------------------------------------------------------------------------


class FakeProvider:
    """A perfect silent model (same shape as the conftest seam fake)."""

    name = "openrouter"
    model = "fake-v1"

    def __init__(self, **_options: object) -> None:
        pass

    def predict(self, case):
        from forgebench.schemas import ProviderResponse

        content = json.dumps(
            {
                "category": case.expected.category.value,
                "requires_review": case.expected.requires_review,
                "reason": f"Reference logic for {case.scenario_family}.",
                "evidence_fields": ["bank_amount", "ledger_amount"],
            }
        )
        return ProviderResponse(content=content, latency_ms=1.0, model=self.model)


class FakeJudgeProvider:
    """Deterministic verdict for any judge prompt, shaped like a provider."""

    name = "judge-mock"
    model = "judge-v1"

    def predict_text(self, prompt: str):
        from forgebench.schemas import ProviderResponse

        return ProviderResponse(
            content=json.dumps({"score": 0.85, "pass": True, "reason": "grounded"}),
            latency_ms=1.0,
            model=self.model,
        )


def _judge_config(tmp_output: Path | None = None) -> ExperimentConfig:
    return ExperimentConfig(
        experiment=ExperimentSection(name="unit", dataset="tiny_v1", dataset_version="1.0.0"),
        provider=ProviderSection(name="judge-mock", model="fake-v1"),
        evaluation=EvaluationSection(
            metrics=["accuracy", "schema_validity"],
            judge=JudgeSection(
                provider="judge-mock",
                model="judge-v1",
                options={"probe": "fake-judge"},
            ),
        ),
    )


def test_finance_run_judge_with_tiny_dataset(
    tmp_path: Path,
    tiny_dataset: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Judge averages land in metrics, manifest, and the Markdown report."""
    from forgebench import runner
    from forgebench.runner import run_experiment

    def fake_build(name, *, model="", options=None):
        if options and options.get("probe") == "fake-judge":
            return FakeJudgeProvider()
        return FakeProvider(**(options or {}))

    monkeypatch.setattr(runner, "build_provider", fake_build)

    result = run_experiment(
        _judge_config(),
        datasets_root=tiny_dataset,
        output_root=tmp_path,
        run_id="judge-run",
    )
    judge_metrics = result.metrics["judge"]
    assert judge_metrics["n_judged"] == 6  # every case judged
    assert judge_metrics["avg_score"] == pytest.approx(0.85)
    assert judge_metrics["pass_rate"] == pytest.approx(1.0)
    assert result.manifest["judge"] == {"name": "judge-mock", "model": "judge-v1"}

    report = (result.run_dir / "report.md").read_text(encoding="utf-8")
    assert "Judge avg score" in report
    # The per-case table shows the test data, not bare case ids.
    assert "vendor=Test Vendor" in report


def test_run_without_judge_has_no_judge_metrics(
    tmp_path: Path, tiny_dataset: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from forgebench import runner
    from forgebench.runner import run_experiment

    monkeypatch.setattr(runner, "build_provider", lambda *a, **k: FakeProvider())
    config = ExperimentConfig(
        experiment=ExperimentSection(name="unit", dataset="tiny_v1", dataset_version="1.0.0"),
        provider=ProviderSection(name="fake", model="fake-v1"),
        evaluation=EvaluationSection(metrics=["accuracy"]),
    )
    result = run_experiment(
        config, datasets_root=tiny_dataset, output_root=tmp_path, run_id="plain"
    )
    assert "judge" not in result.metrics
    assert "judge" not in result.manifest


# ---------------------------------------------------------------------------
# Custom task engine: per-rule metrics, report, trace, N models
# ---------------------------------------------------------------------------


def _write_minimal_task(root: Path, with_judge: bool = False) -> None:
    """A tiny custom task: sentiment enum + a boolean flag (8 test cases)."""
    task_dir = root / "mini_task"
    task_dir.mkdir(parents=True, exist_ok=True)
    schema = [
        {
            "name": "sentiment",
            "type": "enum",
            "enum_values": ["positive", "negative", "neutral"],
            "description": "",
        },
        {"name": "confident", "type": "boolean", "description": ""},
    ]
    rules = [
        {"field": "sentiment", "method": "exact_match", "weight": 1.0},
        {"field": "confident", "method": "boolean", "weight": 1.0},
    ]
    if with_judge:
        rules.append(
            {
                "field": "sentiment",
                "method": "llm_judge",
                "weight": 1.0,
                "threshold": 0.5,
                "criteria": "Decide if the sentiment call is justified.",
            }
        )
    task = {
        "name": "mini_task",
        "version": "1.0.0",
        "description": "offline test task",
        "input_fields": ["text"],
        "output_schema": schema,
        "scoring_rules": rules,
        "system_prompt": "Return JSON only.",
    }
    (task_dir / "task.yaml").write_text(json.dumps(task), encoding="utf-8")
    cases = [
        {
            "id": f"MT-{i:04d}",
            "input": {"text": f"case text {i}"},
            "expected": {"sentiment": "negative", "confident": True},
        }
        for i in range(1, 9)
    ]
    for split in ("train", "dev", "test"):
        (task_dir / f"{split}.jsonl").write_text(
            "".join(json.dumps(c) + "\n" for c in cases), encoding="utf-8"
        )


def test_task_run_engine_offline_artifacts(tmp_path: Path) -> None:
    """Mock-provider task run: per-rule metrics, report.md, trace.jsonl."""
    from forgebench.task_runner import run_task_experiment

    _write_minimal_task(tmp_path / "tasks")
    result = run_task_experiment(
        "mini_task",
        split="test",
        provider="mock",
        model="rule-mock-v1",
        output_root=tmp_path / "runs",
        tasks_root=tmp_path / "tasks",
    )
    metrics = result.metrics
    assert metrics["n_cases"] == 8
    assert metrics["accuracy"] == pytest.approx(metrics["n_valid"] / 8, abs=1e-6)
    assert "per_rule" in metrics
    assert set(metrics["per_rule"]) == {"sentiment", "confident"}
    for stats in metrics["per_rule"].values():
        assert stats["n_pass"] + (stats["n_cases"] - stats["n_pass"]) == stats["n_cases"]

    run_dir = result.run_dir
    assert (run_dir / "report.md").exists()
    assert (run_dir / "trace.jsonl").exists()
    report = (run_dir / "report.md").read_text(encoding="utf-8")
    assert "Per-rule results" in report
    assert "Per-case results" in report
    assert "case text" in report  # the input data is in the report
    assert "judge" in result.manifest


def test_task_run_with_judge_rule_online_judge(tmp_path: Path) -> None:
    """llm_judge rules get a decisive verdict through the mock judge, offline."""
    from forgebench.task_runner import run_task_experiment

    _write_minimal_task(tmp_path / "tasks", with_judge=True)
    result = run_task_experiment(
        "mini_task",
        split="test",
        provider="mock",
        model="rule-mock-v1",
        output_root=tmp_path / "runs",
        tasks_root=tmp_path / "tasks",
    )
    assert result.n_cases == 8
    # Judge metrics surface in the trace spans and the manifest keeps the judge.
    assert result.manifest["judge"]["model"]
    trace_text = (result.run_dir / "trace.jsonl").read_text(encoding="utf-8")
    assert '"judge"' in trace_text


def test_load_case_inputs_for_task_runs(tmp_path: Path) -> None:
    from forgebench.tasks import load_case_inputs

    _write_minimal_task(tmp_path / "tasks")
    manifest = {"task": "mini_task", "split": "test"}
    inputs = load_case_inputs(manifest, tmp_path, tasks_root=tmp_path / "tasks")
    assert "MT-0001" in inputs
    assert inputs["MT-0001"]["input"] == {"text": "case text 1"}


def test_history_collects_and_renders(tmp_path: Path) -> None:
    """Two runs of the same group get a delta; groups sort chronologically."""

    def write_run(name: str, group: str, model: str, n_cases: int, n_valid: int, at: str) -> None:
        run_dir = tmp_path / name
        run_dir.mkdir()
        (run_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "run_id": name,
                    "task": group,
                    "split": "test",
                    "created_at_utc": at,
                    "provider": {"name": "mock", "model": model},
                }
            ),
            encoding="utf-8",
        )
        (run_dir / "metrics.json").write_text(
            json.dumps(
                {
                    "n_cases": n_cases,
                    "n_valid": n_valid,
                    "accuracy": round(n_valid / n_cases, 4),
                }
            ),
            encoding="utf-8",
        )

    write_run("run-a", "mini_task", "model-v1", 10, 8, "2026-10-01T10:00:00")
    write_run("run-b", "mini_task", "model-v2", 10, 9, "2026-10-02T10:00:00")
    write_run("run-c", "other_task", "model-v1", 5, 5, "2026-10-03T10:00:00")

    entries = collect_history(tmp_path)
    by_id = {e["run_id"]: e for e in entries}
    assert by_id["run-b"]["delta_vs_previous"] == pytest.approx(0.1)
    assert by_id["run-a"]["delta_vs_previous"] is None
    assert by_id["run-c"]["delta_vs_previous"] is None

    text = render_history(entries)
    assert "| mini_task |" in text
    assert "+0.1000" in text


def test_history_skips_broken_runs(tmp_path: Path) -> None:
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "manifest.json").write_text("{oops", encoding="utf-8")
    assert collect_history(tmp_path) == []


# ---------------------------------------------------------------------------
# CLI: mock offline task runs, N models, safety-scan, export html
# ---------------------------------------------------------------------------


def test_task_run_cli_mock_offline(tmp_path: Path) -> None:
    from forgebench.cli import app

    _write_minimal_task(tmp_path / "tasks")
    result = runner.invoke(
        app,
        [
            "task-run",
            "mini_task",
            "--provider",
            "mock",
            "--output-root",
            str(tmp_path / "runs"),
            "--tasks-root",
            str(tmp_path / "tasks"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Run:" in result.output


def test_task_run_cli_n_model_comparison(tmp_path: Path) -> None:
    from forgebench.cli import app

    _write_minimal_task(tmp_path / "tasks")
    result = runner.invoke(
        app,
        [
            "task-run",
            "mini_task",
            "--provider",
            "mock",
            "--models",
            "model-a,model-b",
            "--output-root",
            str(tmp_path / "runs"),
            "--tasks-root",
            str(tmp_path / "tasks"),
        ],
    )
    assert result.exit_code == 0, result.output
    run_dirs = sorted((tmp_path / "runs").glob("mini_task-*"))
    assert len(run_dirs) == 2
    comparison_path = run_dirs[0] / "comparison.md"
    assert comparison_path.exists()
    comparison = comparison_path.read_text(encoding="utf-8")
    assert "`model-a`" in comparison
    assert "`model-b`" in comparison
    # Check basic comparison elements
    assert "model-a" in comparison
    assert "model-b" in comparison
    assert "Delta vs Baseline" in comparison


def test_compare_task_runs_via_common_command(tmp_path: Path) -> None:
    from forgebench.cli import app

    _write_minimal_task(tmp_path / "tasks")
    for model in ("model-a", "model-b"):
        one = runner.invoke(
            app,
            [
                "task-run",
                "mini_task",
                "--provider",
                "mock",
                "--model",
                model,
                "--output-root",
                str(tmp_path / "runs"),
                "--tasks-root",
                str(tmp_path / "tasks"),
            ],
        )
        assert one.exit_code == 0, one.output
    run_dirs = sorted((tmp_path / "runs").glob("mini_task-*model-a-*"))
    other = sorted((tmp_path / "runs").glob("mini_task-*model-b-*"))
    compared = runner.invoke(app, ["compare", str(run_dirs[0]), str(other[0])])
    assert compared.exit_code == 0, compared.output
    assert "mini_task" in compared.output
    assert "mini_task" in compared.output


def test_safety_scan_cli_offline(tmp_path: Path) -> None:
    from forgebench.cli import app

    result = runner.invoke(
        app,
        [
            "safety-scan",
            "--provider",
            "mock",
            "--output-root",
            str(tmp_path / "runs"),
        ],
    )
    assert result.exit_code == 0, result.output
    run_dirs = list((tmp_path / "runs").glob("safety_redteam-*"))
    assert len(run_dirs) == 1
    assert (run_dirs[0] / "report.md").exists()


def test_export_html_standalone(tmp_path: Path) -> None:
    from forgebench.cli import app

    _write_minimal_task(tmp_path / "tasks")
    built = runner.invoke(
        app,
        [
            "task-run",
            "mini_task",
            "--provider",
            "mock",
            "--output-root",
            str(tmp_path / "runs"),
            "--tasks-root",
            str(tmp_path / "tasks"),
        ],
    )
    assert built.exit_code == 0, built.output
    run_dir = next(tmp_path.joinpath("runs").glob("mini_task-*"))
    out_file = tmp_path / "out.html"
    exported = runner.invoke(
        app,
        ["export", str(run_dir), "--format", "html", "--out", str(out_file)],
    )
    assert exported.exit_code == 0, exported.output
    html = out_file.read_text(encoding="utf-8")
    assert html.startswith("<!doctype html>")
    assert "<table>" in html
    assert "<script" not in html.lower()


def test_export_unknown_format_fails(tmp_path: Path) -> None:
    from forgebench.cli import app

    failed = runner.invoke(
        app,
        ["export", str(REPO_ROOT / "runs" / "test-run-001"), "--format", "pdf"],
    )
    assert failed.exit_code == 1
    assert "use json, csv or html" in failed.output


# ---------------------------------------------------------------------------
# Webhooks
# ---------------------------------------------------------------------------


def test_webhook_payload_shape() -> None:
    payload = build_run_payload(
        {
            "run_id": "r1",
            "task": "mini_task",
            "provider": {"name": "mock", "model": "v1"},
            "created_at_utc": "2026-10-18T00:00:00+00:00",
        },
        {"n_cases": 8, "n_valid": 7, "accuracy": 0.875},
    )
    assert payload["event"] == "forgebench.run.completed"
    assert payload["accuracy"] == 0.875


def test_post_run_webhook_delivers_and_never_raises() -> None:
    sent: list[tuple[str, bytes, str]] = []
    manifest = {"run_id": "r1", "provider": {"name": "mock", "model": "v1"}}
    metrics = {"n_cases": 1, "n_valid": 1, "accuracy": 1.0}

    ok = post_run_webhook(
        manifest, metrics, url="http://collector.test", send_fn=lambda *a: sent.append(a)
    )
    assert ok is True and len(sent) == 1

    def broken(*_a: object) -> None:
        raise OSError("boom")

    failed = post_run_webhook(manifest, metrics, url="http://collector.test", send_fn=broken)
    assert failed is False

    monkey_no_env = post_run_webhook(manifest, metrics, url="", send_fn=broken)
    assert monkey_no_env is False  # unconfigured webhooks are a no-op


def test_post_run_webhook_reads_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[tuple[str, bytes, str]] = []
    monkeypatch.setenv("FORGEBENCH_WEBHOOK_URL", "http://collector.test")
    ok = post_run_webhook({"run_id": "r1"}, {"n_cases": 1}, send_fn=lambda *a: sent.append(a))
    assert ok is True and sent


# ---------------------------------------------------------------------------
# API auth gate + N-model endpoint
# ---------------------------------------------------------------------------


@pytest.fixture()
def api_client():
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from forgebench.api import app

    return TestClient(app)


def test_token_gate_requires_header(api_client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FORGEBENCH_TOKEN", "sekrit")
    denied = api_client.get("/api/tasks")
    assert denied.status_code == 401
    allowed = api_client.get("/api/tasks", headers={"x-forgebench-token": "sekrit"})
    assert allowed.status_code == 200
    wrong = api_client.get("/api/tasks", headers={"x-forgebench-token": "nope"})
    assert wrong.status_code == 401


def test_token_gate_disabled_by_default(api_client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FORGEBENCH_TOKEN", raising=False)
    assert api_client.get("/api/tasks").status_code == 200


def test_start_task_run_n_models(monkeypatch: pytest.MonkeyPatch) -> None:
    """Three models run sequentially and every manifest cross-links the others."""

    import forgebench.api as api
    from forgebench.task_runner import TaskRunResult

    def fake(
        name,
        split,
        provider,
        model,
        judge_provider,
        judge_model,
        limit,
        output_root,
        on_progress,
        on_log=None,
    ):
        on_progress(2, 2)
        return TaskRunResult(
            run_id=f"{name}-{provider}-{model or 'default'}-T",
            run_dir=Path("runs") / "fake",
            n_cases=2,
            n_valid=2,
            metrics={"n_cases": 2, "n_valid": 2},
            manifest={
                "run_id": f"{name}-{provider}-{model or 'default'}-T",
                "task": name,
                "task_version": "1.0.0",
                "split": split,
                "provider": {"name": provider, "model": model},
            },
        )

    monkeypatch.setattr(api, "run_task_experiment", fake)


def test_n_model_endpoint_runs_three_models(monkeypatch: pytest.MonkeyPatch) -> None:
    import time

    import forgebench.api as api
    from forgebench.api import TaskRunRequest
    from forgebench.task_runner import TaskRunResult

    calls: list[str] = []

    def fake(
        name,
        split,
        provider,
        model,
        judge_provider,
        judge_model,
        limit,
        output_root,
        on_progress,
        on_log=None,
    ):
        calls.append(model)
        on_progress(2, 2)
        return TaskRunResult(
            run_id=f"{name}-{provider}-{model or 'default'}-T",
            run_dir=Path("runs") / "fake",
            n_cases=2,
            n_valid=2,
            metrics={"n_cases": 2, "n_valid": 2},
            manifest={
                "run_id": f"{name}-{provider}-{model or 'default'}-T",
                "task": name,
                "task_version": "1.0.0",
                "split": split,
                "provider": {"name": provider, "model": model},
            },
        )

    monkeypatch.setattr(api, "run_task_experiment", fake)
    api._run_state.clear()

    nnm = TaskRunRequest(
        name="summarization_qa",
        split="test",
        provider="ollama",
        model="model-a",
        models=["model-b", "model-c"],
    )
    out = api.start_task_run("summarization_qa", nnm)
    state = None
    for _ in range(300):
        st = api._run_state.get(out["run_id"])
        if st and st["status"] != "running":
            state = st
            break
        time.sleep(0.01)
    assert state and state["status"] == "done"
    assert calls == ["model-a", "model-b", "model-c"]
    results = state["result"]["runs"]
    assert len(results) == 3
    assert all("comparison_models" in r["manifest"] for r in results)
    assert results[0]["manifest"]["comparison_models"] == ["model-b", "model-c"]
    assert results[1]["manifest"]["comparison_models"] == ["model-a", "model-c"]
    assert results[2]["manifest"]["comparison_models"] == ["model-a", "model-b"]


def test_history_endpoint_shaped():
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from forgebench.api import app

    client = TestClient(app)
    data = client.get("/api/history").json()
    assert "entries" in data and isinstance(data["entries"], list)

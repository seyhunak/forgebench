"""A run must bill fairly and its manifest must say what actually happened."""

from __future__ import annotations

import hashlib
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from forgebench import credits
from forgebench.cli import app
from forgebench.config import JudgeSection, ProviderSection
from forgebench.runner import run_experiment
from forgebench.task_runner import run_task_experiment
from tests.test_features import _write_minimal_task

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def ledger(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Meter runs in observe mode against a throwaway ledger."""
    path = tmp_path / "credits.json"
    monkeypatch.setenv("FORGEBENCH_CREDITS_PATH", str(path))
    monkeypatch.setenv("FORGEBENCH_CREDITS_MODE", "observe")
    return path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ------------------------------------------------------------------ billing --


def test_benchmark_with_unknown_dataset_costs_nothing(
    mock_config, tiny_dataset: Path, tmp_path: Path, ledger: Path
) -> None:
    mock_config.experiment.dataset = "no_such_dataset"
    with pytest.raises(FileNotFoundError):
        run_experiment(mock_config, datasets_root=tiny_dataset, output_root=tmp_path)
    assert credits.load(ledger)["usage"] == []


def test_benchmark_whose_provider_cannot_be_built_costs_nothing(
    mock_config, tiny_dataset: Path, tmp_path: Path, ledger: Path
) -> None:
    mock_config.provider = ProviderSection(name="no_such_provider", model="m")
    with pytest.raises(Exception, match="unknown provider"):
        run_experiment(mock_config, datasets_root=tiny_dataset, output_root=tmp_path)
    assert credits.load(ledger)["usage"] == []


def test_successful_benchmark_is_charged_once(
    mock_config, tiny_dataset: Path, tmp_path: Path, ledger: Path, deterministic_provider
) -> None:
    run_experiment(mock_config, datasets_root=tiny_dataset, output_root=tmp_path)
    usage = credits.load(ledger)["usage"]
    assert [row["credits"] for row in usage] == [credits.BENCHMARK_RUN_CREDITS]


def test_enforced_empty_balance_stops_benchmark_before_inference(
    mock_config,
    tiny_dataset: Path,
    tmp_path: Path,
    ledger: Path,
    deterministic_provider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FORGEBENCH_CREDITS_MODE", "enforce")
    with pytest.raises(credits.CreditsError):
        run_experiment(mock_config, datasets_root=tiny_dataset, output_root=tmp_path)
    assert deterministic_provider["n"] == 0


def test_task_whose_provider_cannot_be_built_costs_nothing(tmp_path: Path, ledger: Path) -> None:
    _write_minimal_task(tmp_path / "tasks")
    with pytest.raises(Exception, match="unknown provider"):
        run_task_experiment(
            "mini_task",
            provider="no_such_provider",
            model="m",
            output_root=tmp_path / "runs",
            tasks_root=tmp_path / "tasks",
        )
    assert credits.load(ledger)["usage"] == []


# ------------------------------------------------------- provider substitution --


def test_real_provider_config_records_no_substitution(
    mock_config, tiny_dataset: Path, tmp_path: Path, deterministic_provider
) -> None:
    result = run_experiment(mock_config, datasets_root=tiny_dataset, output_root=tmp_path)
    assert "provider_substitution" not in result.manifest


def test_mock_config_records_the_substitution(
    mock_config,
    tiny_dataset: Path,
    tmp_path: Path,
    deterministic_provider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "placeholder")
    mock_config.provider = ProviderSection(name="mock", model="rule-mock-v1")
    result = run_experiment(mock_config, datasets_root=tiny_dataset, output_root=tmp_path)

    substitution = result.manifest["provider_substitution"]
    assert substitution["requested"] == {"name": "mock", "model": "rule-mock-v1"}
    assert substitution["resolved"]["name"] == "openrouter"
    assert "rule-mock-v1" in (result.run_dir / "report.md").read_text(encoding="utf-8")


def test_cli_warns_before_running_a_mock_config(
    tiny_dataset: Path,
    tmp_path: Path,
    deterministic_provider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "placeholder")
    config = tmp_path / "mock.yaml"
    config.write_text(
        "experiment: {name: unit, dataset: tiny_v1}\n"
        "provider: {name: mock, model: rule-mock-v1}\n"
        "evaluation: {metrics: [accuracy]}\n",
        encoding="utf-8",
    )
    result = CliRunner().invoke(
        app,
        [
            "run",
            "--config",
            str(config),
            "--datasets-root",
            str(tiny_dataset),
            "--output-root",
            str(tmp_path / "runs"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "warning" in result.output
    assert "openrouter" in result.output


def test_api_tells_the_runner_a_mock_config_was_replaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("fastapi")
    from forgebench import api

    config = tmp_path / "mock.yaml"
    config.write_text(
        "experiment: {name: unit, dataset: tiny_v1}\n"
        "provider: {name: mock, model: rule-mock-v1}\n"
        "evaluation: {metrics: [accuracy]}\n",
        encoding="utf-8",
    )
    called = threading.Event()
    seen: dict = {}

    def fake_run(experiment, **kwargs):
        seen.update(kwargs, provider=experiment.provider.name)
        called.set()
        return SimpleNamespace(run_id="r", run_dir=tmp_path, metrics={}, manifest={})

    monkeypatch.setattr(api, "run_experiment", fake_run)
    monkeypatch.setattr(api, "_configured_provider", lambda: "openrouter")
    monkeypatch.setattr(api, "_configured_model", lambda _name: "some/model")

    api.start_run(api.RunRequest(config=str(config), run_id="integrity-test"))

    assert called.wait(5)
    assert seen["provider"] == "openrouter"
    assert seen["requested_provider"].name == "mock"
    assert seen["requested_provider"].model == "rule-mock-v1"


# -------------------------------------------------------------------- judges --


def test_benchmark_records_why_a_configured_judge_did_not_run(
    mock_config, tiny_dataset: Path, tmp_path: Path, deterministic_provider
) -> None:
    mock_config.evaluation.judge = JudgeSection(provider="no_such_provider", model="j")
    result = run_experiment(mock_config, datasets_root=tiny_dataset, output_root=tmp_path)

    judge = result.manifest["judge"]
    assert (judge["name"], judge["model"]) == ("no_such_provider", "j")
    assert "unknown provider" in judge["warning"]
    report = (result.run_dir / "report.md").read_text(encoding="utf-8")
    assert "**Judge:**" not in report
    assert "**Judge unavailable:**" in report


def test_task_without_judge_rules_records_no_judge(tmp_path: Path) -> None:
    _write_minimal_task(tmp_path / "tasks")
    result = run_task_experiment(
        "mini_task",
        provider="mock",
        model="rule-mock-v1",
        output_root=tmp_path / "runs",
        tasks_root=tmp_path / "tasks",
    )
    assert "judge" not in result.manifest
    assert "**Judge" not in (result.run_dir / "report.md").read_text(encoding="utf-8")


def test_task_records_why_a_required_judge_did_not_run(tmp_path: Path) -> None:
    _write_minimal_task(tmp_path / "tasks", with_judge=True)
    result = run_task_experiment(
        "mini_task",
        provider="mock",
        model="rule-mock-v1",
        judge_provider="no_such_provider",
        judge_model="j",
        output_root=tmp_path / "runs",
        tasks_root=tmp_path / "tasks",
    )
    judge = result.manifest["judge"]
    assert (judge["name"], judge["model"]) == ("no_such_provider", "j")
    assert "unknown provider" in judge["warning"]


# ------------------------------------------------------------- task manifests --


def test_task_manifest_pins_inputs_and_environment(tmp_path: Path) -> None:
    tasks_root = tmp_path / "tasks"
    _write_minimal_task(tasks_root)
    result = run_task_experiment(
        "mini_task",
        provider="mock",
        model="rule-mock-v1",
        limit=3,
        output_root=tmp_path / "runs",
        tasks_root=tasks_root,
    )
    manifest = result.manifest
    task_dir = tasks_root / "mini_task"

    assert manifest["task_sha256"] == _sha256(task_dir / "task.yaml")
    assert manifest["split_sha256"] == _sha256(task_dir / "test.jsonl")
    assert manifest["limit"] == 3
    assert len(manifest["prompt"]["effective_sha256"]) == 64
    assert manifest["environment"]["forgebench_version"]
    assert manifest["environment"]["python_version"]
    assert "git_sha" in manifest["environment"]
    assert "command" in manifest


def test_task_manifest_hash_changes_with_the_scored_data(tmp_path: Path) -> None:
    tasks_root = tmp_path / "tasks"
    _write_minimal_task(tasks_root)
    options = {
        "provider": "mock",
        "model": "rule-mock-v1",
        "limit": 1,
        "output_root": tmp_path / "runs",
        "tasks_root": tasks_root,
    }
    before = run_task_experiment("mini_task", **options).manifest["split_sha256"]
    with (tasks_root / "mini_task" / "test.jsonl").open("a", encoding="utf-8") as handle:
        handle.write("\n")
    after = run_task_experiment("mini_task", **options).manifest["split_sha256"]
    assert before != after


# ----------------------------------------------------------- frozen datasets --

#: These two datasets have no generator in the repo, so regeneration cannot
#: protect them. Their bytes are pinned instead: any edit needs a new version.
FROZEN_SPLITS = {
    "healthcare_v1/train.jsonl": "bbe2e5c8e801623e63f719d35be8e22d021dd82416d52e2ea33d81eae057c833",
    "healthcare_v1/dev.jsonl": "49e06df8f50037dd5f3bbeda7119eb966e83cf37a2afaf7e4ca0091b681df64a",
    "healthcare_v1/test.jsonl": "4cebcc8bb221609834788ed81f17883097b0ab5723c1815c11803632128bc0ed",
    "ecommerce_v1/train.jsonl": "6e51ce34eea24d3aca1ee0e3677a5cdbd6b41f8c617987341c12e217aba570c7",
    "ecommerce_v1/dev.jsonl": "0563b6bf242d8a16f8eeed39fe52cbebcbbd9f0a1ce83e2bc0a0feb209fbd636",
    "ecommerce_v1/test.jsonl": "1316c0abb1c2c3c5c4d7e6c8acdf1a4b1e7c5379458bdcd6c4341dbe8cb7d9ec",
}


@pytest.mark.parametrize("relative_path", sorted(FROZEN_SPLITS))
def test_datasets_without_a_generator_stay_byte_identical(relative_path: str) -> None:
    assert _sha256(REPO_ROOT / "datasets" / relative_path) == FROZEN_SPLITS[relative_path]

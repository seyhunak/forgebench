"""CLI end-to-end tests through typer's runner (no subprocess needed)."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from forgebench.cli import app

REPO_ROOT = Path(__file__).resolve().parents[1]
runner = CliRunner()


def test_list_datasets() -> None:
    result = runner.invoke(app, ["list-datasets"])
    assert result.exit_code == 0
    assert "finance_v1" in result.output


def test_validate_dataset_ok() -> None:
    result = runner.invoke(app, ["validate-dataset", "finance_v1"])
    assert result.exit_code == 0
    assert "OK: dataset is valid." in result.output


def test_validate_unknown_dataset_fails() -> None:
    result = runner.invoke(app, ["validate-dataset", "nope_v9"])
    assert result.exit_code == 1


def test_run_compare_report_cycle(tmp_path: Path) -> None:
    baseline = runner.invoke(
        app,
        [
            "run",
            "--config",
            str(REPO_ROOT / "configs" / "baseline.yaml"),
            "--run-id",
            "cli-baseline",
            "--output-root",
            str(tmp_path),
            "--limit",
            "20",
        ],
    )
    assert baseline.exit_code == 0, baseline.output
    assert "artifacts:" in baseline.output
    run_dir = tmp_path / "cli-baseline"
    assert (run_dir / "metrics.json").exists()

    improved = runner.invoke(
        app,
        [
            "run",
            "--config",
            str(REPO_ROOT / "configs" / "experiments" / "prompt_v1.yaml"),
            "--run-id",
            "cli-prompt",
            "--output-root",
            str(tmp_path),
            "--limit",
            "20",
        ],
    )
    assert improved.exit_code == 0, improved.output

    comparison = runner.invoke(app, ["compare", str(run_dir), str(tmp_path / "cli-prompt")])
    assert comparison.exit_code == 0
    assert "Δ vs baseline" in comparison.output

    report = runner.invoke(app, ["report", str(run_dir)])
    assert report.exit_code == 0
    assert "Limitations" in report.output


def test_run_with_missing_config_fails(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["run", "--config", str(tmp_path / "missing.yaml"), "--output-root", str(tmp_path)]
    )
    assert result.exit_code == 1
    combined = result.output + (result.stderr or "")
    assert "error:" in combined


def test_compare_needs_two_runs(tmp_path: Path) -> None:
    result = runner.invoke(app, ["compare", str(tmp_path)])
    assert result.exit_code == 2

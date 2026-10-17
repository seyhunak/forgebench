"""CLI end-to-end tests through typer's runner (no subprocess needed)."""

from __future__ import annotations

from pathlib import Path

import pytest
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


def test_run_compare_report_cycle(tmp_path: Path, deterministic_provider: dict) -> None:
    """run -> run -> compare -> report, entirely offline (fake provider)."""
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
    assert deterministic_provider["n"] == 40  # 20 cases per run, no network

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


def test_set_key_lifecycle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """save -> show (masked) -> clear, all inside a throwaway directory."""
    monkeypatch.chdir(tmp_path)
    # The environment must not answer for the saved file: a CI job that exports
    # *_MODEL would otherwise mask what this test actually wrote to .env.
    for variable in ("MISTRAL_API_KEY", "MISTRAL_MODEL", "OPENROUTER_MODEL"):
        monkeypatch.delenv(variable, raising=False)

    saved = runner.invoke(
        app,
        [
            "set-key",
            "--provider",
            "mistral",
            "--key",
            "sk-test-abcdef123456",
            "--model",
            "ministral-8b-2512",
            "--no-verify",
        ],
    )
    assert saved.exit_code == 0, saved.output
    assert "chmod 600" in saved.output
    assert (tmp_path / ".env").exists()
    assert "sk-test-abcdef123456" in (tmp_path / ".env").read_text()
    assert "MISTRAL_MODEL=ministral-8b-2512" in (tmp_path / ".env").read_text()

    shown = runner.invoke(app, ["set-key", "--provider", "mistral", "--show"])
    assert shown.exit_code == 0
    assert "sk-test-abcdef123456" not in shown.output  # never the full secret
    assert "sk-********3456" in shown.output  # masked form keeps prefix + suffix
    assert "ministral-8b-2512" in shown.output

    cleared = runner.invoke(app, ["set-key", "--provider", "mistral", "--clear"])
    assert cleared.exit_code == 0
    assert "MISTRAL_API_KEY=" not in (tmp_path / ".env").read_text()
    assert "cleared" in cleared.output


def test_set_key_saves_storage_only_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """BYOK covers providers with no adapter yet — the Setup screen lists them."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)

    saved = runner.invoke(
        app,
        ["set-key", "--provider", "ollama", "--key", "ollama-local-abc123", "--no-verify"],
    )
    assert saved.exit_code == 0, saved.output
    assert "OLLAMA_API_KEY=ollama-local-abc123" in (tmp_path / ".env").read_text(encoding="utf-8")

    cleared = runner.invoke(app, ["set-key", "--provider", "ollama", "--clear"])
    assert cleared.exit_code == 0, cleared.output
    assert "OLLAMA_API_KEY" not in (tmp_path / ".env").read_text(encoding="utf-8")


def test_set_key_rejects_empty_input(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    result = runner.invoke(app, ["set-key", "--no-verify"], input="\n")
    # click aborts an empty hidden prompt; either way exit 1 and nothing saved.
    assert result.exit_code == 1
    combined = result.output + (result.stderr or "")
    assert "empty key" in combined or "Aborted" in combined
    assert not (tmp_path / ".env").exists()


def test_prompt_save_list_show_and_label(tmp_path: Path) -> None:
    """Registry lifecycle from the terminal: save -> list -> show -> label."""
    root = tmp_path / "prompts"
    body = tmp_path / "body.md"
    body.write_text("Classify the case.", encoding="utf-8")
    opts = ["--prompts-root", str(root)]

    saved = runner.invoke(
        app, ["prompt-save", "classify", "--file", str(body), "--note", "seed", *opts]
    )
    assert saved.exit_code == 0, saved.output
    assert "saved classify@v1" in saved.output

    body.write_text("Classify the case, carefully.", encoding="utf-8")
    second = runner.invoke(app, ["prompt-save", "classify", "--file", str(body), *opts])
    assert second.exit_code == 0, second.output
    assert "saved classify@v2" in second.output

    listing = runner.invoke(app, ["prompt-list", *opts])
    assert listing.exit_code == 0
    assert "classify" in listing.output
    assert "latest=v2" in listing.output

    shown = runner.invoke(app, ["prompt-show", "classify", "--version", "1", *opts])
    assert shown.exit_code == 0
    assert "Classify the case." in shown.output

    latest = runner.invoke(app, ["prompt-show", "classify", *opts])
    assert latest.exit_code == 0
    assert "carefully" in latest.output

    labelled = runner.invoke(app, ["prompt-label", "classify", "production", "2", *opts])
    assert labelled.exit_code == 0, labelled.output
    assert "production=v2" in labelled.output


def test_prompt_show_of_unknown_prompt_fails(tmp_path: Path) -> None:
    result = runner.invoke(app, ["prompt-show", "ghost", "--prompts-root", str(tmp_path)])
    assert result.exit_code == 1
    assert "error:" in result.output

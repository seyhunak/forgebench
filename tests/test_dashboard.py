"""Dashboard helpers: testable without starting Streamlit."""

from __future__ import annotations

from pathlib import Path

import pytest

from forgebench.dashboard import list_configs, list_runs, read_predictions

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_list_configs_finds_shipped_experiments() -> None:
    configs = list_configs(REPO_ROOT)
    labels = [str(path.relative_to(REPO_ROOT)) for path in configs]
    assert "configs/baseline.yaml" in labels
    assert "configs/mistral_baseline.yaml" in labels
    assert any(label.startswith("configs/experiments/") for label in labels)
    assert len(configs) >= 4
    assert configs == sorted(configs)


def test_list_configs_handles_missing_directory(tmp_path: Path) -> None:
    assert list_configs(tmp_path) == []


def test_list_runs_only_returns_complete_runs(tmp_path: Path) -> None:
    (tmp_path / "real-run").mkdir()
    (tmp_path / "real-run" / "manifest.json").write_text("{}")
    (tmp_path / "incomplete").mkdir()
    (tmp_path / "not-a-dir.txt").write_text("x")
    runs = list_runs(tmp_path)
    assert [path.name for path in runs] == ["real-run"]


def test_list_runs_missing_directory(tmp_path: Path) -> None:
    assert list_runs(tmp_path / "nope") == []


def test_read_predictions_roundtrip(tmp_path: Path) -> None:
    from forgebench.schemas import Category

    from .conftest import make_record

    record = make_record(Category.MATCHED, None, ok=False, error_kind="malformed_json")
    (tmp_path / "predictions.jsonl").write_text(record.model_dump_json() + "\n")
    loaded = read_predictions(tmp_path)
    assert len(loaded) == 1
    assert loaded[0].case_id == "FIN-0001"


def test_read_predictions_missing_file(tmp_path: Path) -> None:
    assert read_predictions(tmp_path) == []


def test_streamlit_is_optional_at_import_time() -> None:
    """Importing the dashboard must not require streamlit (helpers are pure)."""
    import sys

    import forgebench.dashboard  # noqa: F401

    assert "streamlit" not in sys.modules


def test_dashboard_command_fails_helpfully_without_streamlit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from typer.testing import CliRunner

    from forgebench.cli import app

    real_import = __import__

    def fake_import(name: str, *args, **kwargs):
        if name == "streamlit":
            raise ImportError("streamlit disabled for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    result = CliRunner().invoke(app, ["dashboard", "--no-open"])
    assert result.exit_code == 1
    combined = result.output + (result.stderr or "")
    assert 'pip install -e ".[ui]"' in combined

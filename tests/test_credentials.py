"""BYOK storage tests: .env hygiene, lookup order, masking."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from forgebench.credentials import (
    delete_value,
    find_env_file,
    get_value,
    mask,
    set_value,
    source_of,
)


def test_set_value_creates_env_file_with_owner_only_permissions(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    path = set_value("MISTRAL_API_KEY", "sk-test-1234567890")
    assert path == tmp_path / ".env"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert get_value("MISTRAL_API_KEY") == "sk-test-1234567890"


def test_set_value_upserts_without_duplicating_or_clobbering(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("# keep me\nFOO=bar\nMISTRAL_API_KEY=old-key\n")
    set_value("MISTRAL_API_KEY", "new-key")
    text = (tmp_path / ".env").read_text()
    assert "# keep me" in text
    assert "FOO=bar" in text
    assert text.count("MISTRAL_API_KEY=") == 1
    assert "new-key" in text and "old-key" not in text


def test_find_env_file_walks_up_from_subdirectories(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    root_env = set_value("MISTRAL_API_KEY", "sk-upstairs", path=tmp_path / ".env")
    nested = tmp_path / "src" / "deep"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)
    assert find_env_file() == root_env
    assert get_value("MISTRAL_API_KEY") == "sk-upstairs"


def test_process_environment_beats_the_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    set_value("MISTRAL_API_KEY", "sk-from-file")
    monkeypatch.setenv("MISTRAL_API_KEY", "sk-from-env")
    assert get_value("MISTRAL_API_KEY") == "sk-from-env"
    assert source_of("MISTRAL_API_KEY") == "environment"


def test_delete_value_removes_only_the_target_line(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    set_value("MISTRAL_API_KEY", "sk-x")
    set_value("MISTRAL_MODEL", "ministral-8b-2512")
    delete_value("MISTRAL_API_KEY")
    text = (tmp_path / ".env").read_text()
    assert "MISTRAL_API_KEY" not in text
    assert "MISTRAL_MODEL" in text
    assert get_value("MISTRAL_API_KEY") is None
    delete_value("MISTRAL_API_KEY")  # idempotent


def test_awkward_values_round_trip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MISTRAL_MODEL", raising=False)
    set_value("MISTRAL_MODEL", "model with space # and hash")
    assert get_value("MISTRAL_MODEL") == "model with space # and hash"


def test_mask_never_reveals_the_secret() -> None:
    secret = "sk-verysecretkeyvalue1234"
    masked = mask(secret)
    assert secret not in masked
    assert masked.startswith("sk-")
    assert masked.endswith("1234")
    assert mask("") == "(not set)"
    assert mask(None) == "(not set)"
    assert mask("short") == "*****"


def test_invalid_variable_name_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        set_value("not a var", "x", path=tmp_path / ".env")


def test_source_of_reports_file_path(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    set_value("MISTRAL_API_KEY", "sk-file-source")
    assert source_of("MISTRAL_API_KEY") == str(tmp_path / ".env")
    os.environ.pop("MISTRAL_API_KEY", None)

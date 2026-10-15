"""Ollama install/running probe: deterministic with a faked binary + daemon."""

from __future__ import annotations

import json

import pytest

from forgebench import ollama_probe


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


def test_status_without_binary_or_daemon_reports_not_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _no_daemon(_request: object, timeout: float | None = None) -> object:
        raise OSError("connection refused")

    monkeypatch.setattr(ollama_probe.shutil, "which", lambda _name: None)
    monkeypatch.setattr(ollama_probe.urllib.request, "urlopen", _no_daemon)

    status = ollama_probe.ollama_status()
    assert status["binary"] is None
    assert status["installed"] is False
    assert status["running"] is False
    assert status["models"] == []
    assert "no binary" in status["detail"]


def test_status_with_binary_but_stopped_daemon_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _down(_request: object, timeout: float | None = None) -> object:
        raise ConnectionRefusedError("refused")

    monkeypatch.setattr(ollama_probe.shutil, "which", lambda _name: "/opt/homebrew/bin/ollama")
    monkeypatch.setattr(ollama_probe.urllib.request, "urlopen", _down)

    status = ollama_probe.ollama_status()
    assert status["installed"] is True
    assert status["running"] is False
    assert "not answering" in status["detail"]


def test_status_lists_local_models_from_the_daemon(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _tags(_request: object, timeout: float | None = None) -> _FakeResponse:
        return _FakeResponse({"models": [{"name": "llama3.1:8b"}, {"name": "qwen3:4b"}]})

    # Binary off PATH must still count as installed once the daemon answers.
    monkeypatch.setattr(ollama_probe.shutil, "which", lambda _name: None)
    monkeypatch.setattr(ollama_probe.urllib.request, "urlopen", _tags)

    status = ollama_probe.ollama_status()
    assert status["installed"] is True
    assert status["running"] is True
    assert status["models"] == ["llama3.1:8b", "qwen3:4b"]
    assert status["binary"] is None


def test_host_normalizes_ollama_host_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_HOST", "192.168.1.10:11434")
    assert ollama_probe.ollama_host() == "http://192.168.1.10:11434"
    monkeypatch.setenv("OLLAMA_HOST", "https://ollama.example.com/")
    assert ollama_probe.ollama_host() == "https://ollama.example.com"
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    assert ollama_probe.ollama_host() == "http://127.0.0.1:11434"


def test_ollama_verdict_presentation_follows_daemon_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify: running → presented "ok"; down → presented "error"; CLI keeps the pair."""
    from forgebench.providers.verify import ollama_verdict, verify_provider_key

    monkeypatch.setattr(
        ollama_probe,
        "ollama_status",
        lambda timeout=1.5: {
            "binary": "/usr/local/bin/ollama",
            "installed": True,
            "running": True,
            "host": "http://127.0.0.1:11434",
            "models": ["llama3.1:8b", "qwen3:4b"],
            "detail": "daemon answering",
        },
    )
    accepted, detail, presented = ollama_verdict()
    assert accepted is None  # nothing about a key can be accepted or rejected
    assert presented == "ok"
    assert "2 local model(s)" in detail
    # The CLI path goes through verify_provider_key and stays a two-tuple.
    assert verify_provider_key("ollama", "ignored") == (accepted, detail)

    monkeypatch.setattr(
        ollama_probe,
        "ollama_status",
        lambda timeout=1.5: {
            "binary": None,
            "installed": False,
            "running": False,
            "host": "http://127.0.0.1:11434",
            "models": [],
            "detail": "down",
        },
    )
    accepted, detail, presented = ollama_verdict()
    assert presented == "error"
    assert "not reachable" in detail

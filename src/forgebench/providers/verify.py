"""Provider API-key verification, shared by the CLI and the dashboard API.

Every verifier returns ``(True, detail)`` when the provider accepted the key,
``(False, detail)`` when it rejected it, and ``(None, detail)`` when the verdict
is unknown (offline, SDK missing, unexpected status). None of them raise: a
flaky network must never block saving a key, so the caller can always report a
verdict — including "could not verify".
"""

from __future__ import annotations

_REJECT_MARKERS = ("401", "unauthorized", "invalid api key")


def _classify_sdk_error(exc: Exception, endpoint: str) -> tuple[bool | None, str]:
    text = str(exc)
    if any(marker in text or marker in text.lower() for marker in _REJECT_MARKERS):
        return False, f"rejected: {type(exc).__name__}"
    return None, f"could not verify ({type(exc).__name__}: {text[:160]}) [{endpoint}]"


def verify_provider_key(provider: str, key: str) -> tuple[bool | None, str]:
    """Best-effort check of ``key`` against ``provider``'s API."""
    if provider == "mistral":
        from .mistral import verify_api_key  # noqa: PLC0415

        return verify_api_key(key)
    if provider == "openrouter":
        from .openrouter import verify_api_key  # noqa: PLC0415

        return verify_api_key(key)
    if provider == "openai":
        return _verify_openai(key)
    if provider == "anthropic":
        return _verify_anthropic(key)
    if provider == "google":
        return _verify_google(key)
    if provider == "ollama":
        accepted, detail, _presented = ollama_verdict()
        return accepted, detail
    return None, "verification not supported for this provider"


def ollama_verdict() -> tuple[bool | None, str, str]:
    """Ollama's "key check" is a daemon check: ``(verdict, detail, presented)``.

    Local models ignore keys, so there is no accepted/rejected answer — the
    useful question is whether the daemon is up. ``presented`` tells callers
    how a human should read the detail: ``"ok"`` when the daemon is running,
    ``"error"`` when it is not reachable. Never raises: the probe degrades to
    "not reachable" on its own.
    """
    from ..ollama_probe import ollama_status  # noqa: PLC0415

    state = ollama_status()
    if state["running"]:
        detail = (
            f"ollama daemon is running on {state['host']} with "
            f"{len(state['models'])} local model(s); local models ignore the key"
        )
        return None, detail, "ok"
    detail = f"ollama daemon is not reachable at {state['host']} — start it with `ollama serve`"
    return None, detail, "error"


def _verify_openai(key: str) -> tuple[bool | None, str]:
    try:
        from openai import OpenAI  # noqa: PLC0415
    except ImportError:
        return None, "the 'openai' package is not installed"
    try:
        OpenAI(api_key=key, timeout=15).models.list()
        return True, "accepted by api.openai.com"
    except Exception as exc:  # noqa: BLE001 - SDK error types vary by version
        return _classify_sdk_error(exc, "api.openai.com")


def _verify_anthropic(key: str) -> tuple[bool | None, str]:
    try:
        from anthropic import Anthropic  # noqa: PLC0415
    except ImportError:
        return None, "the 'anthropic' package is not installed"
    try:
        Anthropic(api_key=key, timeout=15).messages.create(
            model="claude-3-haiku",
            max_tokens=1,
            messages=[{"role": "user", "content": "hi"}],
        )
        return True, "accepted by api.anthropic.com"
    except Exception as exc:  # noqa: BLE001 - SDK error types vary by version
        return _classify_sdk_error(exc, "api.anthropic.com")


def _verify_google(key: str) -> tuple[bool | None, str]:
    try:
        import google.generativeai as genai  # noqa: PLC0415
    except ImportError:
        return None, "the 'google-generativeai' package is not installed"
    try:
        genai.configure(api_key=key)
        genai.GenerativeModel("gemini-1.5-flash").generate_content("hi")
        return True, "accepted by generativelanguage.googleapis.com"
    except Exception as exc:  # noqa: BLE001 - SDK error types vary by version
        return _classify_sdk_error(exc, "generativelanguage.googleapis.com")

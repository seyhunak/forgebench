"""OpenRouter adapter — one key, every hosted model.

OpenRouter (https://openrouter.ai) puts an OpenAI-compatible chat-completions
API in front of hundreds of models from many vendors, addressing each as
``vendor/model`` (e.g. ``anthropic/claude-3.5-sonnet``, ``openai/gpt-4o``,
``meta-llama/llama-3.1-70b-instruct``, ``google/gemini-2.5-pro``). The full
catalog is available from ``GET /api/v1/models`` — see :func:`list_models`.

Design notes:

* The REST API is spoken directly with the standard library, so this adapter
  works on a bare ``pip install forgebench`` (no provider SDK, nothing to keep
  in sync with a vendor's package).
* The runner never sees HTTP: it gets ``ProviderResponse`` like every other
  provider, so scoring, validation and reporting stay identical.
* ``temperature`` is optional — some OpenRouter models reject it — and is
  omitted from the request when ``None``.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

from ..credentials import get_value
from ..schemas import BenchmarkCase, Category, ProviderResponse
from .base import ProviderError

API_KEY_ENV = "OPENROUTER_API_KEY"
_DEFAULT_BASE = "https://openrouter.ai/api/v1"
_TITLE = "ForgeBench"

_CATEGORY_LIST = ", ".join(c.value for c in Category)

DEFAULT_SYSTEM_PROMPT = f"""You are a financial operations assistant that reconciles
bank entries against ledger entries.

Classify each reconciliation case into exactly one category:
- matched: bank and ledger agree on amount, date and reference
- amount_mismatch: the amounts differ
- date_mismatch: the dates differ but amounts agree
- reference_mismatch: the references differ but amounts agree
- duplicate: the same transaction appears more than once on one side
- ambiguous: signals conflict and a human must decide

Respond with ONE JSON object and nothing else, using exactly this shape:
{{"category": "<{_CATEGORY_LIST}>", "requires_review": <true|false>,
"reason": "<one sentence>", "evidence_fields": ["<field name from the case input>"]}}

Rules:
- "requires_review" must be false only for "matched".
- "evidence_fields" may only name fields present in the case input.
- A plausible explanation does not make an incorrect category correct.
"""


def _base() -> str:
    """API base URL, overridable for self-hosted proxies and tests."""
    return os.environ.get("OPENROUTER_API_BASE", _DEFAULT_BASE).rstrip("/")


def _few_shot_block(examples: list[dict[str, Any]]) -> str:
    lines = ["\nExamples of correct outputs (same JSON shape):"]
    for example in examples:
        lines.append(f"Case input:\n{json.dumps(example['input'], indent=2)}")
        lines.append(f"Correct output:\n{json.dumps(example['prediction'])}")
    return "\n".join(lines)


def _describe(exc: Exception | None) -> str:
    """Human-readable detail for an HTTP or transport error."""
    if isinstance(exc, urllib.error.HTTPError):
        detail = ""
        try:
            body = exc.read().decode("utf-8", "replace")
        except Exception:  # noqa: BLE001 - body may already be consumed
            body = ""
        try:
            parsed = json.loads(body)
            error = parsed.get("error")
            if isinstance(error, dict):
                detail = str(error.get("message", ""))
            elif isinstance(error, str):
                detail = error
            else:
                detail = str(parsed.get("message", ""))
        except (json.JSONDecodeError, AttributeError):
            detail = body[:200]
        suffix = f": {detail}" if detail else ""
        return f"HTTP {exc.code} {exc.reason}{suffix}"
    if exc is None:
        return "unknown error"
    return f"{type(exc).__name__}: {exc}"


def _content_text(content: Any) -> str:
    """Normalize ``message.content`` to a string.

    Chat-completions usually returns a string, but multimodal models may return
    a list of parts (``[{"type": "text", "text": "..."}]``); flatten those and
    ignore non-text parts so downstream parsing always sees text.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and part.get("text"):
                parts.append(str(part["text"]))
        return "".join(parts)
    return str(content)


def _to_response(data: dict[str, Any], latency_ms: float, model: str) -> ProviderResponse:
    try:
        content = _content_text(data["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError(f"unexpected response shape from OpenRouter: {data!r}") from exc
    usage = data.get("usage") or {}
    return ProviderResponse(
        content=content,
        latency_ms=latency_ms,
        input_tokens=usage.get("prompt_tokens"),
        output_tokens=usage.get("completion_tokens"),
        model=data.get("model") or model,
    )


class OpenRouterProvider:
    """Chat-completions provider for any model in the OpenRouter catalog."""

    name = "openrouter"

    def __init__(
        self,
        model: str,
        *,
        api_key: str | None = None,
        system_prompt: str | None = None,
        examples: list[dict[str, Any]] | None = None,
        temperature: float | None = 0.0,
        max_retries: int = 2,
        timeout_seconds: float = 60.0,
        max_tokens: int | None = 1024,
        site_url: str | None = None,
        app_name: str | None = None,
    ) -> None:
        key = api_key or os.environ.get(API_KEY_ENV) or get_value(API_KEY_ENV)
        if not key:
            raise ProviderError(
                f"{API_KEY_ENV} is not set. Export {API_KEY_ENV} or save it with "
                "`forgebench set-key --provider openrouter --key ...`."
            )
        if not model:
            raise ProviderError(
                "OpenRouter needs a model id, e.g. --model anthropic/claude-3.5-sonnet. "
                "List them with: forgebench models --provider openrouter"
            )
        self.model = model
        self.temperature = temperature
        self.max_retries = max(0, max_retries)
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens
        self.system_prompt = (system_prompt or DEFAULT_SYSTEM_PROMPT) + (
            _few_shot_block(examples) if examples else ""
        )
        self._headers: dict[str, str] = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            # Optional attribution OpenRouter surfaces on its rankings page.
            "HTTP-Referer": site_url
            or os.environ.get("OPENROUTER_SITE_URL", "")
            or "https://github.com/seyhunak/forgebench",
            "X-Title": app_name or os.environ.get("OPENROUTER_APP_NAME", "") or _TITLE,
        }

    # -- contract ------------------------------------------------------------

    def predict(self, case: BenchmarkCase) -> ProviderResponse:
        messages = [
            {"role": "system", "content": self.system_prompt},
            {
                "role": "user",
                "content": (
                    "Classify this reconciliation case. Answer with the JSON object only.\n\n"
                    f"{json.dumps(case.input, indent=2)}"
                ),
            },
        ]
        return self._chat(messages, label="openrouter call", case_id=case.id)

    def predict_text(self, prompt: str, system: str | None = None) -> ProviderResponse:
        """Free-text completion for LLM-as-judge calls (not benchmark cases)."""
        messages = [
            {"role": "system", "content": system or self.system_prompt},
            {"role": "user", "content": prompt},
        ]
        return self._chat(messages, label="openrouter judge call")

    # -- transport -----------------------------------------------------------

    def _chat(
        self, messages: list[dict[str, str]], *, label: str, case_id: str | None = None
    ) -> ProviderResponse:
        payload: dict[str, Any] = {"model": self.model, "messages": messages}
        if self.temperature is not None:
            payload["temperature"] = self.temperature
        if self.max_tokens is not None:
            payload["max_tokens"] = self.max_tokens

        url = f"{_base()}/chat/completions"
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            started = time.perf_counter()
            try:
                data = self._post_json(url, payload)
                return _to_response(data, (time.perf_counter() - started) * 1000, self.model)
            except Exception as exc:  # urllib error types vary by failure mode
                last_error = exc
                if attempt >= self.max_retries or not self._retryable(exc):
                    break
                time.sleep(min(2.0**attempt, 8.0))
        where = f" for case {case_id}" if case_id else ""
        attempts = self.max_retries + 1
        raise ProviderError(
            f"{label}{where} failed after {attempts} attempt(s): {_describe(last_error)}"
        ) from last_error

    def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(url, data=body, headers=self._headers, method="POST")
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            raw = response.read().decode("utf-8")
        return json.loads(raw)

    @staticmethod
    def _retryable(exc: Exception) -> bool:
        if isinstance(exc, urllib.error.HTTPError):
            return exc.code in (408, 409, 429, 500, 502, 503, 504)
        if isinstance(exc, urllib.error.URLError):
            return True
        name = type(exc).__name__.lower()
        text = str(exc).lower()
        markers = ("ratelimit", "timeout", "connection", "unavailable", "429", "500", "502", "503")
        return any(marker in name or marker in text for marker in markers)


def verify_api_key(api_key: str) -> tuple[bool | None, str]:
    """Check a key against OpenRouter with one free, authenticated call.

    Hits ``GET /key`` (auth required, no tokens billed). Returns ``(True, ...)``
    when accepted, ``(False, ...)`` when rejected, and ``(None, ...)`` when the
    verdict is unknown (offline or unexpected status). Never raises: a flaky
    network must not block saving a key.
    """
    request = urllib.request.Request(
        f"{_base()}/key", headers={"Authorization": f"Bearer {api_key}"}
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            if response.status == 200:
                return True, "accepted by openrouter.ai"
            return None, f"unexpected status {response.status} from openrouter.ai"
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return False, f"rejected: HTTP {exc.code}"
        return None, f"could not verify (HTTP {exc.code})"
    except Exception as exc:  # noqa: BLE001 - network/SSL/DNS failures
        return None, f"could not verify ({type(exc).__name__}: {str(exc)[:160]})"


def list_models(
    api_key: str | None = None, *, timeout_seconds: float = 20.0
) -> list[dict[str, Any]]:
    """Return the live OpenRouter catalog.

    The catalog is public (no auth needed) and changes often, so callers that
    want the absolute latest should prefer this over the pinned models.dev
    snapshot served by the dashboard. Each entry carries at least ``id`` and
    ``name``; most also include ``context_length``, ``pricing`` and
    ``supported_parameters``.
    """
    headers = {"Content-Type": "application/json"}
    key = api_key or os.environ.get(API_KEY_ENV) or get_value(API_KEY_ENV)
    if key:
        headers["Authorization"] = f"Bearer {key}"
    request = urllib.request.Request(f"{_base()}/models", headers=headers)
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        data = json.loads(response.read().decode("utf-8"))
    models = data.get("data") if isinstance(data, dict) else data
    return list(models or [])

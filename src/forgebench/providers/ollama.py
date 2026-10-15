"""Ollama adapter — runs whatever the user has pulled locally.

Ollama exposes an OpenAI-style chat-completions endpoint at
``/api/chat`` (and a native generate endpoint too), so a pulled model
reads, prompts and responds identically to every other provider here.
The host is discovered through :func:`forgebench.ollama_probe.ollama_host`
(``OLLAMA_HOST`` override included), and NO API key is required — Ollama
is a local daemon.

Design notes:

* The REST API is spoken directly with the standard library, so this
  adapter works on a bare ``pip install forgebench`` (no provider SDK).
* The runner never sees HTTP: it gets ``ProviderResponse`` like every other
  provider, so scoring, validation and reporting stay identical.
* Like OpenRouter, ``temperature`` is optional and is omitted when ``None``.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

from ..credentials import get_value
from ..ollama_probe import ollama_host, ollama_status
from ..schemas import BenchmarkCase, ProviderResponse
from .base import ProviderError

_CATEGORY_LIST = "matched, amount_mismatch, date_mismatch, reference_mismatch, duplicate, ambiguous"

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
{{"category": "<one of: {_CATEGORY_LIST}>", "requires_review": <true|false>,
"reason": "<one sentence>", "evidence_fields": ["<field name from the case input>"]}}

Rules:
- "requires_review" must be false only for "matched".
- "evidence_fields" may only name fields present in the case input.
- A plausible explanation does not make an incorrect category correct.
"""


def _few_shot_block(examples: list[dict[str, Any]]) -> str:
    lines = ["\nExamples of correct outputs (same JSON shape):"]
    for example in examples:
        lines.append(f"Case input:\n{json.dumps(example['input'], indent=2)}")
        lines.append(f"Correct output:\n{json.dumps(example['prediction'])}")
    return "\n".join(lines)


def _describe(exc: Exception | None) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        detail = ""
        try:
            body = exc.read().decode("utf-8", "replace")
        except Exception:  # noqa: BLE001 - body may already be consumed
            body = ""
        try:
            parsed = json.loads(body)
            if isinstance(parsed, dict):
                detail = str(parsed.get("error", "") or parsed.get("message", ""))
        except (json.JSONDecodeError, AttributeError):
            detail = body[:200]
        suffix = f": {detail}" if detail else ""
        return f"HTTP {exc.code} {exc.reason}{suffix}"
    if exc is None:
        return "unknown error"
    return f"{type(exc).__name__}: {exc}"


class OllamaProvider:
    """Chat-completions provider for any model served by the local Ollama daemon."""

    name = "ollama"

    def __init__(
        self,
        model: str = "",
        *,
        api_key: str | None = None,  # accepted for uniformity; local Ollama ignores it
        system_prompt: str | None = None,
        examples: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_retries: int = 2,
        timeout_seconds: float = 120.0,
        max_tokens: int | None = None,  # local models: leave output length unconstrained
    ) -> None:

        resolved = (
            (model or "").strip()
            or os.environ.get("OLLAMA_MODEL", "").strip()
            or get_value("OLLAMA_MODEL")
            or "llama3.1:8b"
        )
        if not resolved:
            raise ProviderError("Ollama needs a model id, e.g. --model llama3.1:8b.")
        self.model = resolved
        self.base_url = ollama_host().rstrip("/")
        self.temperature = temperature
        self.max_retries = max(0, max_retries)
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens
        self.system_prompt = (system_prompt or DEFAULT_SYSTEM_PROMPT) + (
            _few_shot_block(examples) if examples else ""
        )
        self._headers = {"Content-Type": "application/json"}

    # -- contract -----------------------------------------------------------

    def predict(self, case: BenchmarkCase) -> ProviderResponse:
        user_prompt = (
            "Classify this reconciliation case. Answer with the JSON object only.\n\n"
            f"{json.dumps(case.input, indent=2)}"
        )
        return self._generate(self.system_prompt, user_prompt, label="ollama call", case_id=case.id)

    def predict_text(self, prompt: str, system: str | None = None) -> ProviderResponse:
        """Free-text completion for LLM-as-judge calls (not benchmark cases)."""
        return self._generate(system or self.system_prompt, prompt, label="ollama judge call")

    # -- transport ----------------------------------------------------------

    def _generate(
        self, system: str, prompt: str, *, label: str, case_id: str | None = None
    ) -> ProviderResponse:
        url_chat = f"{self.base_url}/api/chat"
        url_generate = f"{self.base_url}/api/generate"
        payload_chat: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "format": "json",
        }
        options: dict[str, Any] = {}
        if self.temperature is not None:
            options["temperature"] = self.temperature
        if self.max_tokens is not None:
            options["num_predict"] = self.max_tokens
        if options:
            payload_chat["options"] = options

        payload_generate: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "system": system,
            "stream": False,
            "format": "json",
        }
        if options:
            payload_generate["options"] = options

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            started = time.perf_counter()
            try:
                data = self._post_with_fallback(
                    url_chat, payload_chat, url_generate, payload_generate
                )
                latency_ms = (time.perf_counter() - started) * 1000
                return self._to_response(data, latency_ms, self.model)
            except Exception as exc:  # noqa: BLE001 - error types vary
                last_error = exc
                if attempt >= self.max_retries or not self._retryable(exc):
                    break
                time.sleep(min(2.0**attempt, 8.0))
        where = f" for case {case_id}" if case_id else ""
        attempts = self.max_retries + 1
        raise ProviderError(
            f"{label}{where} failed after {attempts} attempt(s): {_describe(last_error)}"
        ) from last_error

    def _post_with_fallback(
        self,
        url_chat: str,
        payload_chat: dict[str, Any],
        url_generate: str,
        payload_generate: dict[str, Any],
    ) -> dict[str, Any]:
        # Some pulled models back the chat endpoint, others the native generate
        # endpoint. Try chat first (richer) and fall back on a 400/404 so a
        # single adapter covers both shapes without the caller knowing.
        try:
            return self._post_json(url_chat, payload_chat)
        except urllib.error.HTTPError as exc:
            if exc.code not in (400, 404, 405):
                raise
        try:
            return self._post_json(url_generate, payload_generate)
        except urllib.error.HTTPError as exc:
            if exc.code not in (400, 404, 405):
                raise
            # Both endpoints refused; re-raise the original generate error.
            raise

    def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(url, data=body, headers=self._headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.URLError as exc:
            # Ollama sometimes drops the connection mid-stream; surface the cause.
            raise ProviderError(f"ollama daemon not answering at {self.base_url}: {exc}") from exc
        return json.loads(raw)

    @staticmethod
    def _retryable(exc: Exception) -> bool:
        if isinstance(exc, urllib.error.HTTPError):
            return exc.code in (408, 409, 429, 500, 502, 503, 504)
        if isinstance(exc, urllib.error.URLError):
            return True
        name = type(exc).__name__.lower()
        text = str(exc).lower()
        markers = ("timeout", "connection", "unavailable", "refused")
        return any(marker in name or marker in text for marker in markers)

    @staticmethod
    def _to_response(data: dict[str, Any], latency_ms: float, model: str) -> ProviderResponse:
        content = None
        if isinstance(data.get("message"), dict):
            content = data["message"].get("content")
        if content is None and isinstance(data.get("response"), str):
            content = data["response"]
        if content is None:
            raise ProviderError(f"unexpected response shape from Ollama: {data!r}")
        if not isinstance(content, str):
            content = str(content)
        usage = data.get("prompt_eval_count")
        output_usage = data.get("eval_count")
        return ProviderResponse(
            content=content,
            latency_ms=latency_ms,
            input_tokens=usage,
            output_tokens=output_usage,
            model=data.get("model") or model,
        )


def list_local_models(timeout_seconds: float = 5.0) -> list[dict[str, str]]:
    """Names of models pulled in the running daemon, for the CLI selector."""
    status = ollama_status(timeout=min(timeout_seconds, 5.0))
    if not status.get("running"):
        raise ProviderError(
            f"ollama daemon is not answering at {status.get('host')}: "
            f"{status.get('detail', 'unknown error')}"
        )
    return [{"id": name, "name": name} for name in status.get("models") or []]

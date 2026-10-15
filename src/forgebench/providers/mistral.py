"""Mistral adapter built on the official ``mistralai`` Python SDK.

Design notes:

* The import is lazy, so the rest of ForgeBench (and its test suite) works
  without the SDK installed or credentials configured.
* The runner never talks to the SDK: it sees ``ProviderResponse`` like with
  every other provider, so scoring, validation and reporting stay identical.
* Prompt variants (baseline / explicit-schema / few-shot) are constructor
  arguments, which is what makes Day-5 style comparisons just configs.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from ..credentials import get_value
from ..schemas import BenchmarkCase, Category, ProviderResponse
from .base import ProviderError

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


def _few_shot_block(examples: list[dict[str, Any]]) -> str:
    lines = ["\nExamples of correct outputs (same JSON shape):"]
    for example in examples:
        lines.append(f"Case input:\n{json.dumps(example['input'], indent=2)}")
        lines.append(f"Correct output:\n{json.dumps(example['prediction'])}")
    return "\n".join(lines)


class MistralProvider:
    """Chat-completions provider for Mistral models."""

    name = "mistral"

    def __init__(
        self,
        model: str,
        *,
        api_key: str | None = None,
        system_prompt: str | None = None,
        examples: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_retries: int = 2,
        timeout_seconds: float = 30.0,
        max_tokens: int | None = 1024,
    ) -> None:
        key = api_key or os.environ.get("MISTRAL_API_KEY") or get_value("MISTRAL_API_KEY")
        if not key:
            raise ProviderError(
                "MISTRAL_API_KEY is not set. Run `forgebench set-key` to save one, "
                "export MISTRAL_API_KEY, or use the mock provider (--provider mock)."
            )
        self.model = model
        self.temperature = temperature
        self.max_retries = max(0, max_retries)
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens
        self.system_prompt = (system_prompt or DEFAULT_SYSTEM_PROMPT) + (
            _few_shot_block(examples) if examples else ""
        )
        try:
            from mistralai import Mistral  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise ProviderError(
                "The 'mistralai' package is not installed. Run: pip install mistralai"
            ) from exc
        try:
            self._client = Mistral(api_key=key, timeout=timeout_seconds)
        except TypeError:  # pragma: no cover - older SDK signatures
            self._client = Mistral(api_key=key)

    def _messages(self, case: BenchmarkCase) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": self.system_prompt},
            {
                "role": "user",
                "content": (
                    "Classify this reconciliation case. Answer with the JSON object only.\n\n"
                    f"{json.dumps(case.input, indent=2)}"
                ),
            },
        ]

    def predict(self, case: BenchmarkCase) -> ProviderResponse:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            started = time.perf_counter()
            try:
                request: dict[str, Any] = {
                    "model": self.model,
                    "messages": self._messages(case),
                    "temperature": self.temperature,
                }
                if self.max_tokens is not None:
                    request["max_tokens"] = self.max_tokens
                response = self._client.chat.complete(**request)
                latency_ms = (time.perf_counter() - started) * 1000
                return self._to_response(response, latency_ms)
            except Exception as exc:  # SDK error types vary by version
                last_error = exc
                if attempt >= self.max_retries or not self._retryable(exc):
                    break
                time.sleep(min(2.0**attempt, 8.0))
        attempts = self.max_retries + 1
        raise ProviderError(
            f"mistral call failed for case {case.id} after {attempts} attempt(s): {last_error}"
        ) from last_error

    @staticmethod
    def _retryable(exc: Exception) -> bool:
        name = type(exc).__name__.lower()
        text = str(exc).lower()
        markers = ("ratelimit", "timeout", "connection", "unavailable", "429", "500", "502", "503")
        return any(marker in name or marker in text for marker in markers)

    @staticmethod
    def _to_response(response: Any, latency_ms: float) -> ProviderResponse:
        try:
            content = response.choices[0].message.content or ""
        except (AttributeError, IndexError, TypeError) as exc:
            raise ProviderError(
                f"unexpected response shape from Mistral SDK: {response!r}"
            ) from exc
        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "prompt_tokens", None) if usage else None
        output_tokens = getattr(usage, "completion_tokens", None) if usage else None
        if input_tokens is None and usage is not None:
            input_tokens = getattr(usage, "input_tokens", None)
        if output_tokens is None and usage is not None:
            output_tokens = getattr(usage, "output_tokens", None)
        return ProviderResponse(
            content=content,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=getattr(response, "model", "") or "",
        )


def verify_api_key(api_key: str) -> tuple[bool | None, str]:
    """Check a key against the API with one free, authenticated call.

    Returns ``(True, detail)`` when accepted, ``(False, detail)`` when the API
    rejected it, and ``(None, detail)`` when validity could not be determined
    (offline, SDK missing, or an unexpected failure). Never raises: saving a
    key must not be blocked by a flaky network.
    """
    try:
        from mistralai import Mistral  # noqa: PLC0415
    except ImportError:  # pragma: no cover - depends on environment
        return None, "the 'mistralai' package is not installed"
    try:
        client = Mistral(api_key=api_key, timeout=15)
        client.models.list()
        return True, "accepted by api.mistral.ai"
    except Exception as exc:  # SDK error types vary by version
        text = str(exc)
        if "401" in text or "unauthorized" in text.lower() or "invalid api key" in text.lower():
            return False, f"rejected: {type(exc).__name__}"
        return None, f"could not verify ({type(exc).__name__}: {text[:160]})"

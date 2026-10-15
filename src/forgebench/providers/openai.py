"""OpenAI adapter built on the official ``openai`` Python SDK.

Supports GPT-4o, GPT-4o-mini, o1, o3-mini, and other OpenAI chat models.
The SDK import is lazy so ForgeBench works without it installed.
"""

from __future__ import annotations

import json
import os
from typing import Any

from ..credentials import get_value
from ..schemas import BenchmarkCase, ProviderResponse
from .base import ProviderError

DEFAULT_SYSTEM_PROMPT = """You are a financial operations assistant that reconciles
bank entries against ledger entries.

Classify each reconciliation case into exactly one category:
- matched: bank and ledger agree on amount, date and reference
- amount_mismatch: the amounts differ
- date_mismatch: the dates differ but amounts agree
- reference_mismatch: the references differ but amounts agree
- duplicate: the same transaction appears more than once on one side
- ambiguous: signals conflict and a human must decide

Respond with ONE JSON object and nothing else, using exactly this shape:
{"category": "<matched|amount_mismatch|date_mismatch|reference_mismatch|duplicate|ambiguous>",
 "requires_review": <true|false>,
 "reason": "<one sentence>",
 "evidence_fields": ["<field name from the case input>"]}

Rules:
- "requires_review" must be false only for "matched".
- "evidence_fields" may only name fields present in the case input.
- A plausible explanation does not make an incorrect category correct.
"""


def _few_shot_block(examples: list[dict[str, Any]]) -> str:
    lines = ["\nExamples of correct outputs (same JSON shape):"]
    for example in examples:
        lines.append(f"Case input:\\n{json.dumps(example['input'], indent=2)}")
        lines.append(f"Correct output:\\n{json.dumps(example['prediction'])}")
    return "\\n".join(lines)


class OpenAIProvider:
    """Chat-completions provider for OpenAI models."""

    name = "openai"

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
        max_tokens: int | None = 4096,
    ) -> None:
        key = api_key or os.environ.get("OPENAI_API_KEY") or get_value("OPENAI_API_KEY")
        if not key:
            raise ProviderError(
                "OPENAI_API_KEY is not set. Export OPENAI_API_KEY or save it with "
                "`forgebench set-key --provider openai --key ...`."
            )
        try:
            from openai import OpenAI  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise ProviderError(
                "The 'openai' package is not installed. Run: pip install openai"
            ) from exc
        self.model = model
        self.temperature = temperature
        self.max_retries = max(0, max_retries)
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens
        self.system_prompt = (system_prompt or DEFAULT_SYSTEM_PROMPT) + (
            _few_shot_block(examples) if examples else ""
        )
        self._client = OpenAI(api_key=key, timeout=timeout_seconds)

    def predict(self, case: BenchmarkCase) -> ProviderResponse:
        import time

        messages = [
            {"role": "system", "content": self.system_prompt},
            {
                "role": "user",
                "content": (
                    "Classify this reconciliation case. Answer with the JSON object only.\\n\\n"
                    f"{json.dumps(case.input, indent=2)}"
                ),
            },
        ]

        started = time.perf_counter()
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                request: dict[str, Any] = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": self.temperature,
                }
                if self.max_tokens is not None:
                    request["max_tokens"] = self.max_tokens
                response = self._client.chat.completions.create(**request)
                latency_ms = (time.perf_counter() - started) * 1000
                content = response.choices[0].message.content or ""
                usage = getattr(response, "usage", None)
                input_tokens = getattr(usage, "prompt_tokens", None) if usage else None
                output_tokens = (
                    getattr(usage, "completion_tokens", None) if usage else None
                )
                return ProviderResponse(
                    content=content,
                    latency_ms=latency_ms,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    model=getattr(response, "model", self.model) or self.model,
                )
            except Exception as exc:  # SDK error types vary by version
                last_error = exc
                if attempt >= self.max_retries or not self._retryable(exc):
                    break
                time.sleep(min(2.0**attempt, 8.0))
        attempts = self.max_retries + 1
        raise ProviderError(
            f"openai call failed for case {case.id} after {attempts} attempt(s): {last_error}"
        ) from last_error

    @staticmethod
    def _retryable(exc: Exception) -> bool:
        name = type(exc).__name__.lower()
        text = str(exc).lower()
        markers = ("ratelimit", "timeout", "connection", "unavailable", "429", "500", "502", "503")
        return any(marker in name or marker in text for marker in markers)
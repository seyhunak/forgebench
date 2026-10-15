"""Anthropic adapter built on the official ``anthropic`` Python SDK.

Supports Claude 3.5 Sonnet, Claude 3 Opus, Claude 3 Haiku, Claude 4, and other
Anthropic models. The SDK import is lazy so ForgeBench works without it installed.
"""

from __future__ import annotations

import json
import os
import time
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


class AnthropicProvider:
    """Messages API provider for Anthropic Claude models."""

    name = "anthropic"

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
        key = (
            api_key
            or os.environ.get("ANTHROPIC_API_KEY")
            or get_value("ANTHROPIC_API_KEY")
        )
        if not key:
            raise ProviderError(
                "ANTHROPIC_API_KEY is not set. Export ANTHROPIC_API_KEY or save it with "
                "`forgebench set-key --provider anthropic --key ...`."
            )
        try:
            from anthropic import Anthropic  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise ProviderError(
                "The 'anthropic' package is not installed. Run: pip install anthropic"
            ) from exc
        self.model = model
        self.temperature = temperature
        self.max_retries = max(0, max_retries)
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self.examples = examples or []
        self._client = Anthropic(api_key=key, timeout=timeout_seconds)

    def predict(self, case: BenchmarkCase) -> ProviderResponse:
        started = time.perf_counter()
        last_error: Exception | None = None

        # Build the user message, prepending few-shot examples as a conversation prefix.
        user_content = (
            "Classify this reconciliation case. Answer with the JSON object only.\\n\\n"
            f"{json.dumps(case.input, indent=2)}"
        )

        for attempt in range(self.max_retries + 1):
            try:
                # Anthropic puts system prompt in a separate parameter, not in messages.
                # Few-shot examples are prepended as prior user/assistant turns.
                messages: list[dict[str, Any]] = []
                for example in self.examples:
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "Classify this reconciliation case. Answer with the JSON object only.\\n\\n"
                                f"{json.dumps(example['input'], indent=2)}"
                            ),
                        }
                    )
                    messages.append(
                        {
                            "role": "assistant",
                            "content": json.dumps(example["prediction"]),
                        }
                    )
                messages.append({"role": "user", "content": user_content})

                response = self._client.messages.create(
                    model=self.model,
                    system=self.system_prompt,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens or 4096,
                )
                latency_ms = (time.perf_counter() - started) * 1000
                content = "".join(
                    block.text for block in response.content if hasattr(block, "text")
                )
                usage = getattr(response, "usage", None)
                input_tokens = getattr(usage, "input_tokens", None) if usage else None
                output_tokens = (
                    getattr(usage, "output_tokens", None) if usage else None
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
            f"anthropic call failed for case {case.id} after {attempts} attempt(s): {last_error}"
        ) from last_error

    @staticmethod
    def _retryable(exc: Exception) -> bool:
        name = type(exc).__name__.lower()
        text = str(exc).lower()
        markers = ("ratelimit", "timeout", "connection", "unavailable", "429", "500", "502", "503")
        return any(marker in name or marker in text for marker in markers)
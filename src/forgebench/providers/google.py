"""Google adapter built on the official ``google-generativeai`` Python SDK.

Supports Gemini 2.5 Pro, Gemini 2.0 Flash, Gemini 1.5 Pro/Flash, and other
Google models. The SDK import is lazy so ForgeBench works without it installed.
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


class GoogleProvider:
    """Generative AI provider for Google Gemini models."""

    name = "google"

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
        key = api_key or os.environ.get("GOOGLE_API_KEY") or get_value("GOOGLE_API_KEY")
        if not key:
            raise ProviderError(
                "GOOGLE_API_KEY is not set. Export GOOGLE_API_KEY or save it with "
                "`forgebench set-key --provider google --key ...`."
            )
        try:
            import google.generativeai as genai  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise ProviderError(
                "The 'google-generativeai' package is not installed. "
                "Run: pip install google-generativeai"
            ) from exc
        self.model = model
        self.temperature = temperature
        self.max_retries = max(0, max_retries)
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self.examples = examples or []
        genai.configure(api_key=key)
        self._client = genai.GenerativeModel(model)

    def predict(self, case: BenchmarkCase) -> ProviderResponse:
        started = time.perf_counter()
        last_error: Exception | None = None

        user_content = (
            "Classify this reconciliation case. Answer with the JSON object only.\\n\\n"
            f"{json.dumps(case.input, indent=2)}"
        )

        # Build few-shot history as alternating user/model turns.
        history: list[dict[str, Any]] = []
        for example in self.examples:
            history.append(
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": (
                                "Classify this reconciliation case. "
                                "Answer with the JSON object only.\n\n"
                                f"{json.dumps(example['input'], indent=2)}"
                            )
                        }
                    ],
                }
            )
            history.append(
                {
                    "role": "model",
                    "parts": [{"text": json.dumps(example["prediction"])}],
                }
            )

        for attempt in range(self.max_retries + 1):
            try:
                # Combine system prompt + few-shot history into the generation config.
                full_prompt = self.system_prompt
                if history:
                    full_prompt += "\\n\\n" + "\\n\\n".join(
                        f"{'User' if h['role'] == 'user' else 'Model'}: {h['parts'][0]['text']}"
                        for h in history
                    )
                full_prompt += f"\\n\\nUser: {user_content}"

                response = self._client.generate_content(
                    full_prompt,
                    generation_config={
                        "temperature": self.temperature,
                        "max_output_tokens": self.max_tokens or 4096,
                    },
                    request_options={"timeout": self.timeout_seconds},
                )
                latency_ms = (time.perf_counter() - started) * 1000
                content = response.text or ""
                # Gemini usage metadata may not always be present.
                usage = getattr(response, "usage_metadata", None)
                input_tokens = getattr(usage, "prompt_token_count", None) if usage else None
                output_tokens = getattr(usage, "candidates_token_count", None) if usage else None
                return ProviderResponse(
                    content=content,
                    latency_ms=latency_ms,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    model=self.model,
                )
            except Exception as exc:  # SDK error types vary by version
                last_error = exc
                if attempt >= self.max_retries or not self._retryable(exc):
                    break
                time.sleep(min(2.0**attempt, 8.0))
        attempts = self.max_retries + 1
        raise ProviderError(
            f"google call failed for case {case.id} after {attempts} attempt(s): {last_error}"
        ) from last_error

    @staticmethod
    def _retryable(exc: Exception) -> bool:
        name = type(exc).__name__.lower()
        text = str(exc).lower()
        markers = ("ratelimit", "timeout", "connection", "unavailable", "429", "500", "502", "503")
        return any(marker in name or marker in text for marker in markers)

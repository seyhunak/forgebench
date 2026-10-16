"""LLM-as-judge: route subjective scoring through any configured provider.

DeepEval's key insight (G-Eval): let an LLM judge subjective criteria, but
constrain it with explicit rubrics + strict JSON output + retry/parse logic.
ForgeBench routes the judge call through the same provider adapters used for
benchmarking, so any provider (mistral, openai, anthropic, google, mock)
can serve as judge. CI stays green offline because the mock provider returns
deterministic verdicts.
"""

from __future__ import annotations

import json
from typing import Any

from .providers.base import ProviderError
from .schemas import ProviderResponse

JUDGE_SYSTEM_PROMPT = (
    "You are a strict evaluation judge. "
    "Score the model output against the given criterion and expected answer. "
    "Respond with ONE JSON object and nothing else, using exactly this shape:\n"
    '{"score": <0.0-1.0>, "reason": "<one sentence>", "pass": <true|false>}'
)


def build_judge_prompt(
    criterion: str,
    *,
    input_text: str | None = None,
    actual_output: Any = None,
    expected_output: Any = None,
    evaluation_steps: list[str] | None = None,
) -> str:
    """Assemble a G-Eval-style judge prompt with chain-of-thought steps."""
    lines = [
        f"Criterion: {criterion}",
        "",
    ]
    if evaluation_steps:
        lines.append("Evaluation steps (follow them in order):")
        for i, step in enumerate(evaluation_steps, start=1):
            lines.append(f"  {i}. {step}")
        lines.append("")
    if input_text is not None:
        lines.append(f"Input:\n{input_text}\n")
    lines.append(f"Actual output:\n{_dump(actual_output)}\n")
    if expected_output is not None:
        lines.append(f"Expected output:\n{_dump(expected_output)}\n")
    lines.append(
        "Score from 0.0 (worst) to 1.0 (best). "
        'Set "pass" true only when the output clearly satisfies the criterion. '
        "Respond with JSON only."
    )
    return "\n".join(lines)


def _dump(value: Any) -> str:
    if value is None:
        return "(none provided)"
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, indent=2, default=str)
    except (TypeError, ValueError):
        return str(value)


def parse_judge_response(content: str) -> tuple[float, bool, str]:
    """Extract (score, pass, reason) from a judge's raw text.

    Tolerant of code-fence wrapping and leading/trailing prose: finds the
    first JSON object in the content.
    """
    cleaned = content.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"judge returned no JSON object: {content[:200]!r}")
    try:
        data = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError(f"judge returned malformed JSON: {content[:200]!r}") from exc
    try:
        score = float(data["score"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"judge JSON missing numeric 'score': {data!r}") from exc
    score = max(0.0, min(1.0, score))
    verdict = bool(data.get("pass", score >= 0.5))
    reason = str(data.get("reason", ""))[:500]
    return score, verdict, reason


def call_judge(
    provider: Any,
    prompt: str,
    max_retries: int = 2,
) -> tuple[float, bool, str, ProviderResponse]:
    """Call a provider as judge; parse its verdict. Returns (score, pass, reason, response).

    ``provider`` must expose ``predict_text(prompt) -> ProviderResponse``.
    Raises ProviderError only when no judge answer could be obtained at all.
    """
    last_error: Exception | None = None
    for _ in range(max(1, max_retries + 1)):
        try:
            response = provider.predict_text(prompt)
        except AttributeError as exc:
            raise ProviderError(
                f"provider {getattr(provider, 'name', '?')} does not support "
                "text judging (missing predict_text)"
            ) from exc
        except Exception as exc:
            last_error = exc
            continue
        try:
            score, verdict, reason = parse_judge_response(response.content)
        except ValueError as exc:
            last_error = exc
            continue
        return score, verdict, reason, response
    raise ProviderError(f"judge produced no parseable verdict: {last_error}") from last_error


__all__ = [
    "JUDGE_SYSTEM_PROMPT",
    "build_judge_prompt",
    "call_judge",
    "parse_judge_response",
]

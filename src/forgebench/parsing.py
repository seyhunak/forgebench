"""Parse a model's raw text into a validated :class:`Prediction`.

LLMs emit JSON wrapped in prose or fences often enough that "just json.loads"
is not a strategy. This module isolates that messiness so the runner and the
metric engine only ever see validated predictions or a structured error kind.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from .schemas import BenchmarkCase, Prediction

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)

#: Stable error kinds so runs can be aggregated and compared.
ERROR_MALFORMED_JSON = "malformed_json"
ERROR_SCHEMA_VIOLATION = "schema_violation"
ERROR_UNKNOWN_CATEGORY = "unknown_category"
ERROR_UNKNOWN_EVIDENCE_FIELD = "unknown_evidence_field"
ERROR_EMPTY = "empty_response"


def extract_json_text(text: str) -> str | None:
    """Best-effort extraction of one JSON object from raw model text.

    Tries, in order: the whole string, fenced ```json blocks, then the first
    balanced ``{...}`` region. Returns None when nothing looks like an object.
    """
    stripped = text.strip()
    if not stripped:
        return None
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped
    for match in _FENCE_RE.finditer(text):
        candidate = match.group(1).strip()
        if candidate.startswith("{"):
            return candidate
    start = stripped.find("{")
    if start == -1:
        return None
    depth = 0
    for offset, char in enumerate(stripped[start:], start=start):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return stripped[start : offset + 1]
    return None


def _classify_validation_error(exc: ValidationError) -> str:
    for error in exc.errors():
        if error["loc"] and error["loc"][0] == "category":
            return ERROR_UNKNOWN_CATEGORY
    return ERROR_SCHEMA_VIOLATION


def parse_prediction(
    text: str, case: BenchmarkCase
) -> tuple[Prediction | None, str | None, str | None]:
    """Validate ``text`` as a prediction for ``case``.

    Returns ``(prediction, error_kind, error_message)``. On success the first
    element is set and the other two are None; on failure the first is None.
    """
    if not text.strip():
        return None, ERROR_EMPTY, "provider returned an empty response"

    json_text = extract_json_text(text)
    if json_text is None:
        return None, ERROR_MALFORMED_JSON, "no JSON object found in response"

    try:
        payload: Any = json.loads(json_text)
    except json.JSONDecodeError as exc:
        return None, ERROR_MALFORMED_JSON, f"invalid JSON: {exc}"

    try:
        prediction = Prediction.model_validate(payload)
    except ValidationError as exc:
        return None, _classify_validation_error(exc), f"schema violation: {exc}"

    unknown = sorted(set(prediction.evidence_fields) - set(case.input))
    if unknown:
        return (
            None,
            ERROR_UNKNOWN_EVIDENCE_FIELD,
            f"evidence_fields not present in case input: {unknown}",
        )
    return prediction, None, None

"""Artifact writers. Every run leaves a reviewable, machine-readable trail."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..schemas import PredictionRecord


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_predictions(records: list[PredictionRecord], path: Path) -> None:
    lines = [record.model_dump_json() for record in records]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_json(payload: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")

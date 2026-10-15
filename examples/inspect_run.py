#!/usr/bin/env python3
"""Inspect a ForgeBench run: per-family accuracy, worst categories, worst cases.

Usage:
    python examples/inspect_run.py runs/baseline
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from forgebench.schemas import PredictionRecord  # noqa: E402


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    run_dir = Path(sys.argv[1])
    metrics = json.loads((run_dir / "metrics.json").read_text())
    manifest = json.loads((run_dir / "manifest.json").read_text())
    records = [
        PredictionRecord.model_validate_json(line)
        for line in (run_dir / "predictions.jsonl").read_text().splitlines()
        if line.strip()
    ]

    print(f"run:      {manifest['run_id']}")
    print(f"model:    {manifest['provider']['model']}")
    print(f"dataset:  {manifest['dataset']['name']} v{manifest['dataset']['version']}")
    print(f"cases:    {metrics['n_cases']} ({metrics['n_valid']} valid)")
    print()

    print("per-family accuracy:")
    for family, stats in metrics.get("family_breakdown", {}).items():
        bar = "#" * round(stats["accuracy"] * 20)
        print(f"  {family:<20} {stats['accuracy']:.2f} {bar}")
    print()

    errors = Counter()
    for record in records:
        if not record.ok or not record.correct:
            key = f"{record.expected_category.value} -> " + (
                record.category.value if record.category else f"<{record.error_kind}>"
            )
            errors[key] += 1
    print("most common confusions:")
    for confusion, count in errors.most_common(8):
        print(f"  {count}x {confusion}")


if __name__ == "__main__":
    main()

"""Run history: the time-series view over every run in ``runs/``.

A comparison answers "did candidate B beat baseline A"; history answers the
question you ask a month later — "is this task (or dataset) getting better as
I keep working on it". Runs are grouped by what they measured (task name or
dataset name) and sorted chronologically; each entry carries its headline
score and the delta against the previous run of the same group.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def collect_history(runs_root: Path | None = None) -> list[dict[str, Any]]:
    """Every readable run in ``runs_root``, oldest first, grouped-ready."""
    root = runs_root or Path("runs")
    entries: list[dict[str, Any]] = []
    if not root.is_dir():
        return entries
    for path in sorted(root.iterdir()):
        if not path.is_dir():
            continue
        manifest_path = path / "manifest.json"
        metrics_path = path / "metrics.json"
        if not (manifest_path.exists() and metrics_path.exists()):
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        task = manifest.get("task")
        dataset = manifest.get("dataset", {}) or {}
        provider = manifest.get("provider", {}) or {}
        n_cases = metrics.get("n_cases")
        n_valid = metrics.get("n_valid")
        if isinstance(n_cases, int) and isinstance(n_valid, int) and n_cases > 0:
            valid_rate = round(n_valid / n_cases, 4)
        else:
            valid_rate = None
        created = manifest.get("created_at_utc") or ""
        entries.append(
            {
                "run_id": manifest.get("run_id", path.name),
                "path": str(path),
                "created_at": created,
                "group": task or (f"dataset:{dataset.get('name')}" if dataset.get("name") else "?"),
                "kind": "task" if task else "benchmark",
                "provider": provider.get("name"),
                "model": provider.get("model"),
                "split": dataset.get("split") or manifest.get("split"),
                "n_cases": n_cases,
                "n_valid": n_valid,
                "accuracy": metrics.get("accuracy"),
                "valid_rate": valid_rate,
                "macro_f1": metrics.get("macro_f1"),
                "schema_validity": metrics.get("schema_validity"),
            }
        )
    entries.sort(key=lambda e: (e["group"], e["created_at"], e["run_id"]))
    _attach_deltas(entries)
    return entries


def _attach_deltas(entries: list[dict[str, Any]]) -> None:
    """Delta of the headline score against the previous run of the same group."""
    previous: dict[str, dict[str, Any]] = {}
    for entry in entries:
        group = entry["group"]
        prev = previous.get(group)
        headline = entry.get("accuracy")
        if headline is None:
            headline = entry.get("valid_rate")
        if prev is not None and headline is not None:
            prev_headline = prev.get("accuracy")
            if prev_headline is None:
                prev_headline = prev.get("valid_rate")
            if prev_headline is not None:
                entry["delta_vs_previous"] = round(headline - prev_headline, 4)
        else:
            entry["delta_vs_previous"] = None
        previous[group] = entry


def render_history(entries: list[dict[str, Any]]) -> str:
    """Markdown rendering of ``collect_history`` output."""
    if not entries:
        return "No runs yet. `forgebench run` or `forgebench task-run` writes the first one.\n"
    lines = ["# ForgeBench history", ""]
    lines.append(
        "_Per group (task/dataset), the delta column compares each run "
        "with the previous run of the same group._"
    )
    lines.append("")
    lines.append("| Group | Run | Date (UTC) | Model | Cases | Valid | Score | Δ vs previous |")
    lines.append("| --- | --- | --- | --- | ---: | ---: | ---: | ---: |")
    for e in entries:
        score = e.get("accuracy")
        if score is None:
            score = e.get("valid_rate")
        delta = e.get("delta_vs_previous")
        delta_text = "-" if delta is None else f"{delta:+.4f}"
        created = str(e.get("created_at", "")).replace("T", " ")[:16] or "-"
        lines.append(
            f"| {e['group']} | `{e['run_id']}` | {created} | {e.get('model') or '-'} | "
            f"{e.get('n_cases')} | {e.get('n_valid')} | "
            f"{'-' if score is None else f'{score:.4f}'} | {delta_text} |"
        )
    lines.append("")
    return "\n".join(lines)


__all__ = ["collect_history", "render_history"]

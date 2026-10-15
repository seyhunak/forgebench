"""Human-readable Markdown rendering: single-run report and run comparison."""

from __future__ import annotations

import json
from typing import Any

from ..schemas import PredictionRecord

_LIMITATIONS = """\
## Limitations (read before quoting any number)

- The dataset is synthetic. Strong results here do **not** imply production
  readiness on real banking data, which contains messier encodings, partial
  payments, and jurisdiction-specific rules.
- Classification metrics cover schema-valid predictions only; invalid outputs
  are counted separately in schema validity. A model can look accurate while
  being unreliable to integrate.
- Estimated cost uses a historical price table and a chars/4 token fallback
  when the provider did not report usage. Verify current pricing before
  publishing cost claims, and label them with the measurement date.
- A small test set cannot separate small differences from noise. Report the
  sample size and per-class results with every comparison.
- The mock provider is a rule engine, not a model. Its numbers validate the
  pipeline, nothing else.
"""


def _fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".") if value else "0"
    return str(value)


def render_report(
    manifest: dict[str, Any],
    metrics: dict[str, Any],
    records: list[PredictionRecord],
    failures: int = 0,
    case_inputs: dict[str, dict[str, Any]] | None = None,
) -> str:
    """Render one run as Markdown. Deterministic for identical inputs."""
    lines: list[str] = []
    dataset = manifest.get("dataset", {})
    provider = manifest.get("provider", {})
    lines.append(f"# ForgeBench report: {manifest.get('run_id', 'unknown-run')}")
    lines.append("")
    experiment = manifest.get("experiment_name") or manifest.get("task")
    lines.append(f"- **Task / experiment:** {experiment}")
    provider_name = provider.get("name", "unknown").title()
    lines.append(f"- **Provider / model:** {provider_name} / `{provider.get('model')}`")
    comparison_model = manifest.get("comparison_model")
    if comparison_model:
        lines.append(f"- **Comparison model:** `{comparison_model}`")
    comparison_models = manifest.get("comparison_models") or []
    if len(comparison_models) > 1:
        joined = ", ".join(f"`{m}`" for m in comparison_models)
        lines.append(f"- **Comparison models:** {joined}")
    primary_model = manifest.get("primary_model")
    if primary_model:
        lines.append(f"- **Primary model:** `{primary_model}`")
    judge = manifest.get("judge", {}) or {}
    if judge.get("model"):
        judge_name = (judge.get("name") or "unknown").title()
        lines.append(f"- **Judge:** {judge_name} / `{judge.get('model')}`")
    if dataset.get("name"):
        sha = str(dataset.get("split_sha256", ""))[:12]
        lines.append(
            f"- **Dataset:** {dataset.get('name')} v{dataset.get('version')} "
            f"(split: {dataset.get('split')}, sha256: `{sha}…`)"
        )
    lines.append(f"- **Cases:** {metrics.get('n_cases')} ({metrics.get('n_valid')} schema-valid)")
    lines.append(f"- **Run at (UTC):** {manifest.get('created_at_utc')}")
    environment = manifest.get("environment", {})
    lines.append(
        f"- **forgebench:** {environment.get('forgebench_version')} / "
        f"Python {environment.get('python_version')}"
    )
    lines.append("")

    lines.append("## Headline metrics")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("| --- | ---: |")
    headline = [
        ("accuracy", "Accuracy"),
        ("macro_f1", "Macro-F1"),
        ("critical_false_match_rate", "Critical false-match rate"),
        ("escalation_recall", "Escalation recall"),
        ("schema_validity", "Schema validity"),
    ]
    for key, label in headline:
        if key in metrics:
            lines.append(f"| {label} | {_fmt(metrics[key])} |")
    latency = metrics.get("latency")
    if isinstance(latency, dict):
        lines.append(f"| p50 latency | {_fmt(latency['p50_ms'])} ms |")
        lines.append(f"| p95 latency | {_fmt(latency['p95_ms'])} ms |")
    cost = metrics.get("estimated_cost")
    if isinstance(cost, dict):
        lines.append(f"| Est. cost / 1,000 cases | ${_fmt(cost['usd_per_1000_cases'])} |")
    judge = metrics.get("judge")
    if isinstance(judge, dict):
        lines.append(f"| Judge avg score | {_fmt(judge.get('avg_score', 0))} |")
        lines.append(f"| Judge pass rate | {_fmt(judge.get('pass_rate', 0))} |")
    lines.append("")

    per_rule = metrics.get("per_rule") or {}
    if per_rule:
        lines.append("## Per-rule results (custom task)")
        lines.append("")
        lines.append("| Output field | Cases | Pass | Pass rate |")
        lines.append("| --- | ---: | ---: | ---: |")
        for field, stats in per_rule.items():
            lines.append(
                f"| {field} | {stats.get('n_cases', 0)} | {stats.get('n_pass', 0)} | "
                f"{_fmt(stats.get('pass_rate', 0))} |"
            )
        lines.append("")

    per_class = metrics.get("per_class") or {}
    if per_class:
        lines.append("## Per-class results (schema-valid predictions)")
        lines.append("")
        lines.append("| Category | Support | Precision | Recall | F1 |")
        lines.append("| --- | ---: | ---: | ---: | ---: |")
        for category, stats in per_class.items():
            lines.append(
                f"| {category} | {stats['support']} | {_fmt(stats['precision'])} | "
                f"{_fmt(stats['recall'])} | {_fmt(stats['f1'])} |"
            )
        lines.append("")

    family = metrics.get("family_breakdown") or {}
    if family:
        lines.append("## Results by scenario family")
        lines.append("")
        lines.append("| Family | Cases | Valid | Accuracy (valid) |")
        lines.append("| --- | ---: | ---: | ---: |")
        for name, stats in family.items():
            lines.append(
                f"| {name} | {stats['n']} | {stats['n_valid']} | {_fmt(stats['accuracy'])} |"
            )
        lines.append("")

    errors = metrics.get("error_breakdown") or {}
    if errors or failures:
        lines.append("## Output validity")
        lines.append("")
        lines.append("| Failure kind | Count |")
        lines.append("| --- | ---: |")
        for kind, count in errors.items():
            lines.append(f"| {kind} | {count} |")
        lines.append("")

    shown = [r for r in records if not r.ok or r.correct is False][:8]
    if shown:
        lines.append("## Error examples (first 8)")
        lines.append("")
        for record in shown:
            expected = record.expected_category.value
            predicted = record.category.value if record.category else f"<{record.error_kind}>"
            lines.append(
                f"- **{record.case_id}** ({record.scenario_family}): expected "
                f"`{expected}`, predicted `{predicted}`"
                + (f" — {record.error}" if record.error else "")
            )
        lines.append("")

    # Per-case results (full detail, including test data when available).
    if records:
        lines.append("## Per-case results")
        lines.append("")
        lines.append("| Case ID | Input | Expected | Predicted | Correct | OK | Error |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- |")
        for record in records:
            expected = record.expected_category.value if record.expected_category else "—"
            predicted = record.category.value if record.category else (record.error_kind or "—")
            correct = "✅" if record.correct is True else ("❌" if record.correct is False else "—")
            ok = "✅" if record.ok else "❌"
            err = record.error_kind or "—"
            inp = "—"
            if case_inputs and record.case_id in case_inputs:
                ci = case_inputs[record.case_id]
                inp_dict = ci.get("input", ci)
                if isinstance(inp_dict, dict):
                    inp = "; ".join(f"{k}={v}" for k, v in inp_dict.items())
                else:
                    inp = str(inp_dict)
                if len(inp) > 80:
                    inp = inp[:77] + "…"
            row = (
                f"| {record.case_id} | {inp} | {expected} | {predicted} | "
                f"{correct} | {ok} | {err} |"
            )
            lines.append(row)
        lines.append("")

    if isinstance(cost, dict):
        lines.append("## Cost assumptions")
        lines.append("")
        lines.append(f"- Basis: {cost.get('price_basis')}")
        if cost.get("tokens_estimated_when_missing"):
            lines.append(
                "- Token counts were **estimated** (chars/4) for at least one "
                "response because the provider did not report usage."
            )
        note = cost.get("price_note")
        if note:
            lines.append(f"- Note: {note}")
        lines.append("")

    lines.append(_LIMITATIONS)
    return "\n".join(lines)


def _scope_of(manifest: dict[str, Any]) -> str:
    """What a run measured: a task (custom) or a dataset version (benchmark)."""
    task = manifest.get("task")
    if task:
        split = manifest.get("split")
        return f"task {task} ({split})" if split else f"task {task}"
    dataset = manifest.get("dataset", {})
    if dataset.get("name"):
        return f"{dataset.get('name')} v{dataset.get('version')}"
    return manifest.get("experiment_name", "?")


#: Two-level metric dicts that must NOT be exploded into dotted rows.
#: Family/per-class tables are wide and unreadable in a comparison grid.
_COMPARE_HARVEST_EXCLUDE = {"family_breakdown", "per_class", "config", "inference", "prompt"}


def collect_metric_keys(entries: list[dict[str, Any]]) -> list[str]:
    """Every comparable scalar metric key across runs, dotted for nested blocks.

    ``per_rule.<field>.pass_rate`` and friends become flat keys so structured
    consumers (the API's comparison table) and Markdown render identically.
    """
    keys: dict[str, None] = {}  # ordered set

    def _harvest(prefix: str, block: dict[str, Any]) -> None:
        if len(prefix.split(".")) >= 4:
            return
        for part, value in block.items():
            if isinstance(value, (int, float)):
                keys[f"{prefix}{part}"] = None
            elif isinstance(value, dict) and value:
                _harvest(f"{prefix}{part}.", value)

    for entry in entries:
        for key, value in entry["metrics"].items():
            if key in ("n_cases", "n_valid"):
                continue
            if isinstance(value, (int, float)):
                keys[key] = None
            elif isinstance(value, dict) and key not in _COMPARE_HARVEST_EXCLUDE:
                _harvest(f"{key}.", value)
    return list(keys)


def resolve_metric(entry: dict[str, Any], key: str) -> float | None:
    """Look one dotted metric key up in a run entry; ``None`` when absent."""
    value: Any = entry["metrics"]
    for part in key.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return float(value) if isinstance(value, (int, float)) else None


def render_comparison(entries: list[dict[str, Any]]) -> str:
    """Compare N runs — benchmark runs and custom-task runs, side by side.

    The first run is the baseline other runs are measured against. Works even
    when the runs measured different things: rows with missing values render
    as ``-`` rather than silently disappearing.
    """
    if not entries:
        return "No runs to compare.\n"
    lines = ["# ForgeBench comparison", ""]
    names = [e["run_id"] for e in entries]
    lines.append("| Run | Model | Scope | Cases | Valid |")
    lines.append("| --- | --- | --- | ---: | ---: |")
    for entry in entries:
        m, manifest = entry["metrics"], entry["manifest"]
        lines.append(
            f"| {entry['run_id']} | `{manifest.get('provider', {}).get('model')}` | "
            f"{_scope_of(manifest)} | "
            f"{m.get('n_cases')} | {m.get('n_valid')} |"
        )
    lines.append("")

    scalar_keys = collect_metric_keys(entries)

    # Build metric rows with deltas vs baseline (first run). Runs that lack a
    # metric render "—" instead of silently dropping the row.
    header = "| Metric | " + " | ".join(names) + " | Δ vs baseline |"
    lines.append(header)
    lines.append("| --- | " + " | ".join("---:" for _ in names) + " | ---: |")
    for key in scalar_keys:
        values = [resolve_metric(entry, key) for entry in entries]
        if all(v is None for v in values):
            continue
        cells = " | ".join("-" if v is None else _fmt(v) for v in values)
        present = [v for v in values if v is not None]
        delta = f"{present[-1] - present[0]:+.4f}" if len(present) > 1 else "0"
        lines.append(f"| {key} | {cells} | {delta} |")
    lines.append("")
    lines.append(
        "_Deltas compare the last run against the baseline (first run). "
        "With small test sets, treat differences within a few points as noise; "
        "inspect per-rule and error examples before concluding anything._"
    )
    lines.append("")
    return "\n".join(lines)


def load_run(run_dir: str) -> dict[str, Any]:
    """Load one run's manifest + metrics from disk (used by compare/report)."""
    from pathlib import Path

    base = Path(run_dir)
    manifest_path = base / "manifest.json"
    metrics_path = base / "metrics.json"
    for path in (manifest_path, metrics_path):
        if not path.exists():
            raise FileNotFoundError(f"not a ForgeBench run directory (missing {path.name}): {base}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    return {"run_id": manifest.get("run_id", base.name), "manifest": manifest, "metrics": metrics}

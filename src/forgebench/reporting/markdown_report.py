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


def _fmt_pct(value: float | None) -> str:
    """Format as percentage."""
    if value is None:
        return "—"
    return f"{value * 100:.1f}%"


def _fmt_usd(value: float | None) -> str:
    """Format as USD."""
    if value is None:
        return "—"
    if value == 0:
        return "$0.00"
    if value < 0.01:
        return f"${value:.6f}"
    return f"${value:.4f}"


def _fmt_ms(value: float | None) -> str:
    """Format as milliseconds."""
    if value is None:
        return "—"
    return f"{value:.1f} ms"


def _winner_badge(
    baseline_val: float | None, current_val: float | None, higher_is_better: bool = True
) -> str:
    """Return a badge indicating winner/loser."""
    if baseline_val is None or current_val is None:
        return ""
    if higher_is_better:
        if current_val > baseline_val:
            return " 🏆"
        elif current_val < baseline_val:
            return " 📉"
    else:
        if current_val < baseline_val:
            return " 🏆"
        elif current_val > baseline_val:
            return " 📉"
    return " ➖"


def _delta_str(
    baseline_val: float | None, current_val: float | None, higher_is_better: bool = True
) -> str:
    """Return formatted delta with direction indicator."""
    if baseline_val is None or current_val is None:
        return "—"
    delta = current_val - baseline_val
    if higher_is_better:
        sign = "+" if delta > 0 else ""
    else:
        sign = "+" if delta < 0 else ""
        delta = -delta
    return f"{sign}{delta:.4f}"


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
    substitution = manifest.get("provider_substitution")
    if substitution:
        requested = substitution["requested"]
        lines.append(
            f"- **Provider substituted:** the config asked for {requested['name']} / "
            f"`{requested['model']}`"
        )
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
        if judge.get("warning"):
            lines.append(
                f"- **Judge unavailable:** {judge_name} / `{judge.get('model')}` "
                f"({judge['warning']})"
            )
        else:
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
    """Compare N runs -- benchmark runs and custom-task runs, side by side.

    The first run is the baseline other runs are measured against. Works even
    when the runs measured different things: rows with missing values render
    as ``-`` rather than silently disappearing.
    """
    if not entries:
        return "No runs to compare.\n"

    baseline = entries[0]
    baseline_metrics = baseline["metrics"]
    baseline_manifest = baseline["manifest"]
    baseline_name = entries[0]["run_id"]

    lines = ["# ForgeBench Comparison Report", ""]

    lines.append("## Test Dataset")
    lines.append("")

    dataset = baseline_manifest.get("dataset", {})
    task = baseline_manifest.get("task") or baseline_manifest.get("experiment_name", "unknown")

    lines.append("- **Task / Experiment:** " + task)
    if dataset.get("name"):
        sha = str(dataset.get("split_sha256", ""))[:12]
        lines.append(
            "- **Dataset:** " + dataset.get("name") + " v" + dataset.get("version") + " "
            "(split: " + dataset.get("split") + ", SHA256: `" + sha + "...`)"
        )
    lines.append("- **Total Cases:** " + str(baseline_metrics.get("n_cases", "N/A")))
    lines.append("- **Baseline Run:** `" + baseline_name + "`")
    lines.append("- **Comparison Runs:** " + str(len(entries) - 1))
    lines.append("")

    lines.append("## Models Compared")
    lines.append("")

    header_cols = ["Run ID", "Provider", "Model", "Cases", "Valid", "Schema Validity"]
    lines.append("| " + " | ".join(header_cols) + " |")
    lines.append("| " + " | ".join(["---"] * len(header_cols)) + " |")

    for entry in entries:
        manifest = entry["manifest"]
        metrics = entry["metrics"]
        provider = manifest.get("provider", {})
        provider_name = provider.get("name", "unknown").title()
        model = provider.get("model", "unknown")
        schema_valid = metrics.get("schema_validity", 0)
        schema_str = _fmt_pct(schema_valid) if schema_valid else "--"

        lines.append(
            "| "
            + entry["run_id"]
            + " | "
            + provider_name
            + " | `"
            + model
            + "` | "
            + str(metrics.get("n_cases", "N/A"))
            + " | "
            + str(metrics.get("n_valid", "N/A"))
            + " | "
            + schema_str
            + " |"
        )
    lines.append("")
    lines.append("## Accuracy Metrics")
    lines.append("")

    acc_metrics = [
        ("accuracy", "Accuracy", True),
        ("macro_f1", "Macro F1", True),
        ("critical_false_match_rate", "Critical False Match Rate", False),
        ("escalation_recall", "Escalation Recall", True),
        ("schema_validity", "Schema Validity", True),
    ]

    lines.append(
        "| Metric | "
        + " | ".join([e["run_id"] for e in entries])
        + " | Delta vs Baseline | Winner |"
    )
    lines.append("| --- | " + " | ".join(["---:"] * len(entries)) + " | ---: | --- |")

    for key, label, higher_better in acc_metrics:
        baseline_val = baseline_metrics.get(key)
        row_cells = []
        winner = ""
        for i, entry in enumerate(entries):
            val = entry["metrics"].get(key)
            if val is not None:
                cell = _fmt(val)
                if i > 0:
                    badge = _winner_badge(baseline_val, val, higher_better)
                    cell += badge
                row_cells.append(cell)
            else:
                row_cells.append("--")

        delta = ""
        if len(entries) > 1:
            current_val = entries[-1]["metrics"].get(key)
            delta = _delta_str(baseline_val, current_val, higher_better)

        if len(entries) > 1:
            valid_entries = [
                (i, e["metrics"].get(key))
                for i, e in enumerate(entries)
                if e["metrics"].get(key) is not None
            ]
            if len(valid_entries) > 1:
                if higher_better:
                    best_idx = max(valid_entries, key=lambda x: x[1])[0]
                else:
                    best_idx = min(valid_entries, key=lambda x: x[1])[0]
                winner = "Run " + str(best_idx + 1)

        lines.append(
            "| **" + label + "** | " + " | ".join(row_cells) + " | " + delta + " | " + winner + " |"
        )

    lines.append("")
    lines.append("*Winner badge: 🏆 = beats baseline | 📉 = worse than baseline | ➖ = tied*")
    lines.append("")

    lines.append("## LLM Performance")
    lines.append("")

    perf_metrics = [
        ("latency.p50_ms", "Latency P50", False),
        ("latency.p95_ms", "Latency P95", False),
        ("latency.mean_ms", "Latency Mean", False),
        ("provider_error_rate", "Provider Error Rate", False),
    ]

    lines.append(
        "| Metric | "
        + " | ".join([e["run_id"] for e in entries])
        + " | Delta vs Baseline | Winner |"
    )
    lines.append("| --- | " + " | ".join(["---:"] * len(entries)) + " | ---: | --- |")

    for key, label, higher_better in perf_metrics:
        baseline_val = resolve_metric(baseline, key)
        row_cells = []
        for i, entry in enumerate(entries):
            val = resolve_metric(entry, key)
            if val is not None:
                cell = (
                    _fmt_ms(val)
                    if "latency" in key
                    else (
                        _fmt_pct(val)
                        if key == "provider_error_rate"
                        else (f"{val:.4f}" if isinstance(val, float) else str(val))
                    )
                )
                if i > 0:
                    badge = _winner_badge(baseline_val, val, higher_better)
                    cell += badge
                row_cells.append(cell)
            else:
                row_cells.append("--")

        delta = ""
        if len(entries) > 1:
            current_val = resolve_metric(entries[-1], key)
            delta = _delta_str(baseline_val, current_val, higher_better)

        winner = ""
        if len(entries) > 1:
            valid_entries = [
                (i, resolve_metric(e, key))
                for i, e in enumerate(entries)
                if resolve_metric(e, key) is not None
            ]
            if len(valid_entries) > 1:
                if higher_better:
                    best_idx = max(valid_entries, key=lambda x: x[1])[0]
                else:
                    best_idx = min(valid_entries, key=lambda x: x[1])[0]
                winner = "Run " + str(best_idx + 1)

        lines.append(
            "| **" + label + "** | " + " | ".join(row_cells) + " | " + delta + " | " + winner + " |"
        )

    lines.append("")
    lines.append("## Token Cost Analysis")
    lines.append("")

    cost_metrics = [
        ("estimated_cost.total_input_tokens", "Total Input Tokens", False),
        ("estimated_cost.total_output_tokens", "Total Output Tokens", False),
        ("estimated_cost.usd_total", "Total Cost (USD)", False),
        ("estimated_cost.usd_per_case", "Cost per Case (USD)", False),
        ("estimated_cost.usd_per_1000_cases", "Cost per 1K Cases (USD)", False),
    ]

    lines.append(
        "| Metric | "
        + " | ".join([e["run_id"] for e in entries])
        + " | Delta vs Baseline | Winner |"
    )
    lines.append("| --- | " + " | ".join(["---:"] * len(entries)) + " | ---: | --- |")

    for key, label, higher_better in cost_metrics:
        baseline_val = resolve_metric(baseline, key)
        row_cells = []
        for i, entry in enumerate(entries):
            val = resolve_metric(entry, key)
            if val is not None:
                if "usd" in key.lower() or key.endswith("_usd"):
                    cell = _fmt_usd(val)
                else:
                    cell = (
                        f"{int(val):,}" if isinstance(val, float) and val == int(val) else str(val)
                    )
                if i > 0:
                    badge = _winner_badge(baseline_val, val, higher_better)
                    cell += badge
                row_cells.append(cell)
            else:
                row_cells.append("--")

        delta = ""
        if len(entries) > 1:
            current_val = resolve_metric(entries[-1], key)
            delta = _delta_str(baseline_val, current_val, higher_better)

        winner = ""
        if len(entries) > 1:
            valid_entries = [
                (i, resolve_metric(e, key))
                for i, e in enumerate(entries)
                if resolve_metric(e, key) is not None
            ]
            if len(valid_entries) > 1:
                if higher_better:
                    best_idx = max(valid_entries, key=lambda x: x[1])[0]
                else:
                    best_idx = min(valid_entries, key=lambda x: x[1])[0]
                winner = "Run " + str(best_idx + 1)

        lines.append(
            "| **" + label + "** | " + " | ".join(row_cells) + " | " + delta + " | " + winner + " |"
        )

    cost_info = baseline_metrics.get("estimated_cost", {})
    if cost_info.get("price_basis"):
        lines.append("")
        lines.append("*Price basis: " + cost_info["price_basis"] + "*")
        if cost_info.get("price_note"):
            lines.append("*Note: " + cost_info["price_note"] + "*")
        if cost_info.get("tokens_estimated_when_missing"):
            lines.append("*Token usage was estimated (provider did not report usage)*")

    lines.append("")
    baseline_per_class = baseline_metrics.get("per_class", {})
    if baseline_per_class and len(entries) > 1:
        lines.append("## Per-Class Comparison")
        lines.append("")

        all_classes = set()
        for entry in entries:
            all_classes.update(entry["metrics"].get("per_class", {}).keys())

        if all_classes:
            lines.append("### Precision")
            lines.append("")
            header = "| Class | " + " | ".join([e["run_id"] for e in entries]) + " |"
            lines.append(header)
            lines.append("| " + " | ".join(["---"] + ["---:"] * len(entries)) + " |")

            for cls in sorted(all_classes):
                baseline_val = baseline_per_class.get(cls, {}).get("precision")
                row_cells = []
                for i, entry in enumerate(entries):
                    val = entry["metrics"].get("per_class", {}).get(cls, {}).get("precision")
                    if val is not None:
                        cell = _fmt(val)
                        if i > 0:
                            badge = _winner_badge(baseline_val, val, True)
                            cell += badge
                        row_cells.append(cell)
                    else:
                        row_cells.append("--")
                lines.append("| " + cls + " | " + " | ".join(row_cells) + " |")

            lines.append("")

            lines.append("### Recall")
            lines.append("")
            header = "| Class | " + " | ".join([e["run_id"] for e in entries]) + " |"
            lines.append(header)
            lines.append("| " + " | ".join(["---"] + ["---:"] * len(entries)) + " |")

            for cls in sorted(all_classes):
                baseline_val = baseline_per_class.get(cls, {}).get("recall")
                row_cells = []
                for i, entry in enumerate(entries):
                    val = entry["metrics"].get("per_class", {}).get(cls, {}).get("recall")
                    if val is not None:
                        cell = _fmt(val)
                        if i > 0:
                            badge = _winner_badge(baseline_val, val, True)
                            cell += badge
                        row_cells.append(cell)
                    else:
                        row_cells.append("--")
                lines.append("| " + cls + " | " + " | ".join(row_cells) + " |")

            lines.append("")

            lines.append("### F1 Score")
            lines.append("")
            header = "| Class | " + " | ".join([e["run_id"] for e in entries]) + " |"
            lines.append(header)
            lines.append("| " + " | ".join(["---"] + ["---:"] * len(entries)) + " |")

            for cls in sorted(all_classes):
                baseline_val = baseline_per_class.get(cls, {}).get("f1")
                row_cells = []
                for i, entry in enumerate(entries):
                    val = entry["metrics"].get("per_class", {}).get(cls, {}).get("f1")
                    if val is not None:
                        cell = _fmt(val)
                        if i > 0:
                            badge = _winner_badge(baseline_val, val, True)
                            cell += badge
                        row_cells.append(cell)
                    else:
                        row_cells.append("--")
                lines.append("| " + cls + " | " + " | ".join(row_cells) + " |")

            lines.append("")
    has_errors = any(entry["metrics"].get("error_breakdown") for entry in entries)

    if has_errors:
        lines.append("## Error Analysis")
        lines.append("")

        all_error_types = set()
        for entry in entries:
            all_error_types.update(entry["metrics"].get("error_breakdown", {}).keys())

        if all_error_types:
            lines.append("| Error Type | " + " | ".join([e["run_id"] for e in entries]) + " |")
            lines.append("| --- | " + " | ".join(["---:"] * len(entries)) + " |")

            for err_type in sorted(all_error_types):
                row_cells = []
                for entry in entries:
                    count = entry["metrics"].get("error_breakdown", {}).get(err_type, 0)
                    row_cells.append(str(count))
                lines.append("| " + err_type + " | " + " | ".join(row_cells) + " |")

            lines.append("")

    if len(entries) > 1:
        lines.append("## Winner / Loser Summary")
        lines.append("")

        wins = {i: 0 for i in range(len(entries))}
        losses = {i: 0 for i in range(len(entries))}

        key_metrics = [
            ("accuracy", True),
            ("macro_f1", True),
            ("critical_false_match_rate", False),
            ("escalation_recall", True),
            ("schema_validity", True),
            ("latency.p50_ms", False),
            ("latency.p95_ms", False),
            ("estimated_cost.usd_per_1000_cases", False),
            ("provider_error_rate", False),
        ]

        for key, higher_better in key_metrics:
            valid_entries = [
                (i, resolve_metric(e, key))
                for i, e in enumerate(entries)
                if resolve_metric(e, key) is not None
            ]
            if len(valid_entries) >= 2:
                if higher_better:
                    best = max(valid_entries, key=lambda x: x[1])[0]
                    worst = min(valid_entries, key=lambda x: x[1])[0]
                else:
                    best = min(valid_entries, key=lambda x: x[1])[0]
                    worst = max(valid_entries, key=lambda x: x[1])[0]
                wins[best] += 1
                losses[worst] += 1

        lines.append("| Run | Model | Wins | Losses | Net Score | Verdict |")
        lines.append("| --- | --- | ---: | ---: | ---: | --- |")

        for i, entry in enumerate(entries):
            manifest = entry["manifest"]
            provider = manifest.get("provider", {})
            model = provider.get("model", "unknown")
            net = wins[i] - losses[i]

            if i == 0:
                verdict = "Baseline"
            elif net > 0:
                verdict = "WINNER"
            elif net < 0:
                verdict = "Loser"
            else:
                verdict = "Tied"

            lines.append(
                "| "
                + entry["run_id"]
                + " | `"
                + model
                + "` | "
                + str(wins[i])
                + " | "
                + str(losses[i])
                + " | "
                + str(net)
                + " | "
                + verdict
                + " |"
            )

        lines.append("")

    lines.append(_LIMITATIONS)

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

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
) -> str:
    """Render one run as Markdown. Deterministic for identical inputs."""
    lines: list[str] = []
    dataset = manifest.get("dataset", {})
    provider = manifest.get("provider", {})
    lines.append(f"# ForgeBench report: {manifest.get('run_id', 'unknown-run')}")
    lines.append("")
    lines.append(f"- **Experiment:** {manifest.get('experiment_name')}")
    provider_name = provider.get("name", "unknown").title()
    lines.append(f"- **Provider / model:** {provider_name} / `{provider.get('model')}`")
    lines.append(
        f"- **Dataset:** {dataset.get('name')} v{dataset.get('version')} "
        f"(split: {dataset.get('split')}, sha256: `{str(dataset.get('split_sha256', ''))[:12]}…`)"
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


def render_comparison(entries: list[dict[str, Any]]) -> str:
    """Compare N runs. The first run is the baseline other runs are measured against."""
    if not entries:
        return "No runs to compare.\n"
    lines = ["# ForgeBench comparison", ""]
    names = [e["run_id"] for e in entries]
    lines.append("| Run | Model | Dataset | Cases | Valid |")
    lines.append("| --- | --- | --- | ---: | ---: |")
    for entry in entries:
        m, manifest = entry["metrics"], entry["manifest"]
        dataset = manifest.get("dataset", {})
        lines.append(
            f"| {entry['run_id']} | `{manifest.get('provider', {}).get('model')}` | "
            f"{dataset.get('name')} v{dataset.get('version')} | "
            f"{m.get('n_cases')} | {m.get('n_valid')} |"
        )
    lines.append("")

    scalar_keys: list[str] = []
    for entry in entries:
        for key, value in entry["metrics"].items():
            if (
                isinstance(value, (int, float))
                and key not in ("n_cases", "n_valid")
                and key not in scalar_keys
            ):
                scalar_keys.append(key)
    latency_keys = []
    if all(isinstance(e["metrics"].get("latency"), dict) for e in entries):
        latency_keys = ["latency.p50_ms", "latency.p95_ms"]
    cost_keys = []
    if all(isinstance(e["metrics"].get("estimated_cost"), dict) for e in entries):
        cost_keys = ["estimated_cost.usd_per_1000_cases"]

    def resolve(entry: dict[str, Any], key: str) -> float | None:
        if "." in key:
            section, sub = key.split(".", 1)
            value = entry["metrics"].get(section)
            return value.get(sub) if isinstance(value, dict) else None
        value = entry["metrics"].get(key)
        return float(value) if isinstance(value, (int, float)) else None

    header = "| Metric | " + " | ".join(names) + " | Δ vs baseline |"
    lines.append(header)
    lines.append("| --- | " + " | ".join("---:" for _ in names) + " | ---: |")
    for key in scalar_keys + latency_keys + cost_keys:
        values = [resolve(entry, key) for entry in entries]
        if any(v is None for v in values):
            continue
        cells = " | ".join(_fmt(v) for v in values)
        delta = (values[-1] - values[0]) if len(values) > 1 else 0.0
        lines.append(f"| {key} | {cells} | {delta:+.4f} |")
    lines.append("")
    lines.append(
        "_Deltas compare the last run against the baseline (first run). "
        "With small test sets, treat differences within a few points as noise; "
        "inspect per-class results and error examples before concluding anything._"
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

# Changelog

All notable changes to ForgeBench are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-10-18

### Added
- **LLM-as-judge for benchmark runs**: `evaluation.judge` in experiment
  configs (`provider`, `model`, optional `options` and `criteria`). Judge
  scores every schema-valid prediction's `reason`; aggregates land in
  `metrics["judge"]` and the manifest/report show the judge identity.
- **N-model task comparison**: `forgebench task-run --models "a,b,c"` runs
  each model, cross-links manifests, and writes a `comparison.md` matrix.
  The HTTP task-run endpoint accepts an arbitrary `models` list.
- **Run history**: `forgebench history` and `GET /api/history` — a
  chronological trend table grouped by task/dataset with per-group deltas.
  The dashboard gains a "History" view.
- **Standalone HTML report export**: `forgebench export` gains `--format html`
  (sanitized, self-contained page, no external assets).
- **Optional dashboard auth**: set `FORGEBENCH_TOKEN` and every `/api/*`
  request requires the `x-forgebench-token` header; the UI prompts once.
- **Webhooks**: set `FORGEBENCH_WEBHOOK_URL` and every completed run POSTs a
  compact summary JSON; delivery failures never break a run.
- **Per-rule scoring metrics for custom tasks**: `metrics["per_rule"]` with
  pass rate per output-field rule; comparisons and history use it.
- **Richer task-run artifacts**: `report.md` (with per-case test data) and
  `trace.jsonl` now ship with every task run, matching benchmark runs.
- **Regression-on-PR template**: `templates/regression.yml`.

### Fixed
- Mock provider now honours the task `output_schema` passed via constructor
  options (mock task runs through the shared engine produced empty JSON).
- `forgebench compare` works across task runs and benchmark runs, renders
  task scopes correctly, and shows `-` instead of dropping rows with missing
  values.
- Benchmark run reports (and all task-run reports) include the per-case test
  data next to the predictions.

## [0.1.0] - 2026-10-15

### Added
- Reproducible financial exception-classification benchmark (`finance_v1`
  plus `ecommerce_v1`, `legal_v1`, `payments_v1`, `procurement_v1`,
  `subscriptions_v1`).
- Provider adapters: mistral, openai, anthropic, google, openrouter, ollama,
  and an offline deterministic mock.
- Runner, custom task engine, tracing (span waterfall), regression view with
  pinned baselines, Markdown/JSON reports, predictions and metrics artifacts.
- FastAPI dashboard (report/predictions/trace/regression modals, dataset
  browser, config editor, prompt registry, Ollama detection) and CLI
  (`run`, `task-run`, `compare`, `report`, `task-validate`, `prompt-*`).
- CI: lint, format, tests, dataset reproducibility, optional e2e on secrets.

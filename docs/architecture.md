# Architecture

```
CLI / Python API
      │  selects dataset, provider, experiment config
      ▼
Benchmark runner ──► load → validate → infer → score → record
      │
      ├── Dataset registry      cases, labels, splits, versions, SHA-256 hashes
      ├── Provider adapters     Mistral API, deterministic mock, (future: local)
      ├── Metric engine         task quality, validity, latency, estimated cost
      └── Experiment recorder   config, versions, predictions, failures
                                        │
                                        ▼
                          predictions.jsonl · metrics.json ·
                          manifest.json · report.md
```

## Design decisions

| Concern | Decision | Reason |
| --- | --- | --- |
| Inference | Provider abstraction (`ModelProvider` protocol) | No vendor lock-in; the runner never imports an SDK |
| Scoring | Deterministic Python | Never judge a model with another model |
| Data | Synthetic, versioned fixtures with hashes | No customer data; results traceable to exact bytes |
| Execution | Sequential first | Predictable rate limits, reproducible latency, easy debugging |
| Storage | JSONL + JSON + Markdown | Portable, reviewable, Git-friendly |
| UI | CLI first | Protects the deadline; a dashboard can sit on top later |
| Config | YAML with `${ENV_VAR}` expansion | Reproducible experiments, secrets stay outside the repo |
| Training | Out of scope; a separate optional experiment | Inference benchmarking must not depend on training infra |

## Module map (`src/forgebench/`)

| Module | Responsibility |
| --- | --- |
| `schemas.py` | The only contracts: `BenchmarkCase`, `Prediction`, `PredictionRecord`, `ProviderResponse` |
| `parsing.py` | Raw model text → validated `Prediction` or a structured error kind |
| `providers/base.py` | `ModelProvider` protocol + `ProviderError` |
| `providers/mock.py` | Deterministic rule engine; optional seeded defect/invalid injection |
| `providers/mistral.py` | Official SDK adapter: retries, timeouts, token usage, prompt variants |
| `metrics/` | classification, reliability, performance, pricing registry |
| `registry.py` | Dataset discovery, loading, hashing, validation; `ModelArtifact` for future adapters |
| `runner.py` | The one orchestration path: load → infer → score → record |
| `reporting/` | Artifact writers + Markdown rendering + run comparison |
| `config.py` | Strict experiment config schema + env interpolation |
| `cli.py` | Thin typer layer over the above |

## Key invariants

1. **The runner owns validation.** Providers return raw text; only the runner
   decides whether it is a valid prediction. Every provider is scored by the
   same code path.
2. **Ground truth is never a model.** Labels come from deterministic rules in
   `scripts/generate_dataset.py`; the generator asserts its own rules hold.
3. **Every run is self-describing.** `manifest.json` contains the config, the
   dataset split hash, the model id, versions, and timestamps, so a result can
   always be reproduced or refuted.
4. **Errors are data.** Provider failures and invalid outputs become
   `PredictionRecord`s with error kinds — they are scored and reported, never
   silently dropped.

## Three separate concepts

- **Model provider** — how a model receives inputs and returns predictions.
- **Training experiment** — how a model was adapted (data, config, lineage).
  Represented by `registry.ModelArtifact`; not executed by ForgeBench.
- **Evaluation run** — how one artifact performed on one fixed test set.

Keeping these separate is what lets a future fine-tuned model, a prompt
variant, and a baseline share one scoring engine.

## Where concurrency would go

`runner.run_experiment` iterates sequentially. A future threaded/async
variant would wrap `provider.predict` calls only; scoring, recording, and
reporting stay untouched. Latency percentiles must then be labeled as
measured under concurrent execution.

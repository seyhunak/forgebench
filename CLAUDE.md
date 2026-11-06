# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

ForgeBench is a reproducible, provider-agnostic LLM evaluation harness (Python 3.11+, typer CLI, FastAPI dashboard). Its credibility rests on results being traceable to exact bytes of data, prompt, and config.

## Commands

```bash
pip install -e ".[dev]"              # add ".[ui]" for `forgebench dashboard`
pytest                               # whole suite, about 2s
pytest tests/test_metrics.py::test_hand_computed_confusion   # one test
pytest -k few_shot                   # by name
ruff check src tests scripts examples
ruff format src tests scripts examples
```

CI (`.github/workflows/tests.yml`) also runs `ruff format --check` and requires generated data to match what's committed:

```bash
make check-data    # rewrites datasets/ and tasks/ in place, fails if git sees a change
```

Run it with a clean `datasets/` and `tasks/`, because it fails on any uncommitted change there.

`ruff check` currently fails on existing `E501` errors, mostly in `scripts/generate_guardrails_task.py` and `scripts/generate_rag_task.py`. Check that your change adds none rather than expecting a clean exit.

### Commands that spend money

The docs are out of date here. `Makefile`, `CONTRIBUTING.md`, and `docs/architecture.md` describe mock runs as free and offline, but **benchmark runs never use the mock provider**. `runner._resolve_provider_and_model` (and `/api/run` in `api.py`) replaces `mock` with the first provider that has a key, defaulting to OpenRouter. The CLI warns when this happens, and the manifest records it as `provider_substitution`.

- `make demo` and `forgebench run` call a real provider, whatever the config says.
- `pytest` includes one live test, `test_live_run_produces_a_real_trace`. It skips unless `OPENROUTER_API_KEY` is set, and importing the CLI loads `.env`, so a key there can enable it. To be sure, add `--deselect tests/test_runner.py::test_live_run_produces_a_real_trace`.
- The real offline path is custom tasks, which still accept the mock:

```bash
forgebench task-run sentiment_analysis --provider mock --limit 2 --output-root /tmp/fb-runs
```

Mock output is not meant to score well. It only validates the pipeline.

Pass `--output-root` for throwaway runs. `runs/` is git-ignored, but about 120 older artifacts are still tracked there, so don't delete or rewrite them casually.

## Architecture

### Two evaluation pipelines

They share providers, tracing, reporting, and credits, but score differently. Both write the same artifacts to `runs/<run_id>/`: `predictions.jsonl`, `metrics.json`, `manifest.json`, `trace.jsonl`, `report.md`.

| | Benchmark | Custom task |
| --- | --- | --- |
| Entry point | `runner.run_experiment` | `task_runner.run_task_experiment` |
| Data | `datasets/<name>_vN/` (`registry.py`) | `tasks/<name>/task.yaml` + JSONL (`tasks.py`) |
| Provider call | `provider.predict(case)` | `provider.predict_text(prompt)` |
| Scoring | `parsing.parse_prediction`, then `metrics/` | `scoring_rules` in `task.yaml` |
| Output shape | Fixed `Category` enum in `schemas.py` | User-defined `output_schema` |
| Price when metered | 30 credits per run | 1 credit per case |

- `forgebench run --config` chooses the pipeline: a config sets exactly one of `experiment.dataset` or `experiment.task` (`config.py`).
- The CLI and FastAPI app both call these functions. `api.py` also uses `dashboard.py` for helpers that list configs and read runs; the Streamlit entry point in that file is legacy.
- `task_runner.py` imports `_build_task_prompt` and `_score_task_output` from `cli.py`, so task scoring logic lives in `cli.py` (`_apply_scoring_rule` and below). `cli.py` only imports `task_runner` inside functions to avoid a cycle; keep it that way.

### Invariants

- **The runner owns validation.** Providers return raw text. They raise `ProviderError` only when no answer could be obtained, never for a bad answer.
- **Errors are data.** Provider failures and invalid output become `PredictionRecord`s with an `error_kind`. They are scored and reported, never dropped.
- **Ground truth is never a model.** Labels come from deterministic rules in `scripts/`. The LLM judge (`judge.py`) is optional and advisory: a broken judge must not fail a run, and its results stay in `metrics["judge"]`, separate from the rule-based metrics.
- **Manifests must not lie.** `manifest.json` records what actually ran, including `effective_sha256`, the hash of the system prompt the provider really holds. Providers need to expose a `system_prompt` attribute for this to work.
- **Few-shot examples come from the train split only** (`build_few_shot_examples`). The test split must never reach a prompt.

### Versioned data is immutable

- **Datasets:** never edit one in place. Bump the version (`finance_v2`) and keep the old one, or results stop being comparable.
- **Prompts:** `prompts/<name>/vN.md` bodies are immutable, so an edit means a new version. When `prompt.name` is set, the registry body overrides inline `prompt.system`.
- **Generators:** each dataset comes from a seeded script. They write into `datasets/` or `tasks/` by default, so check `git diff` after running one.
  - `generate_dataset.py`: `finance_v1`
  - `generate_multi_dataset.py`: legal, insurance, support, payments, procurement, subscriptions
  - `generate_more_datasets.py`: saas_billing, telecom, travel
  - `generate_rag_task.py`, `generate_guardrails_task.py`: the `rag_knowledge` and `guardrails_tester` tasks
  - `healthcare_v1` and `ecommerce_v1` have no generator, so `tests/test_run_integrity.py` pins their hashes. Ignore the `generator` field in their `dataset.json`, which names a script that doesn't produce them.

### Extending

- **Provider:** add an adapter in `src/forgebench/providers/`, then register it in `build_provider` and `PROVIDER_ENV_VARS` (`providers/__init__.py`). Don't edit the runner. It must implement `predict`, plus `predict_text` to work with custom tasks. Real adapters reject unknown kwargs, which is why `task_provider_options` and `runner._make_provider` filter options. Model contract tests on `tests/test_provider_contract.py`, which doesn't cover `predict_text`, so test that separately.
- **Metric:** a pure function over `list[PredictionRecord]`. State the denominator in the module docstring and add a hand-computed test to `tests/test_metrics.py`.
- **Task scoring method:** add it to `_apply_scoring_rule` in `cli.py`. Valid methods are also listed in the `ScoringRule` description in `schemas.py`.

### Testing

Pipeline tests must stay offline. Use the `deterministic_provider` fixture in `tests/conftest.py`, which replaces `runner._make_provider` with a fake, and the `tiny_dataset` fixture. Pass `output_root=tmp_path` so nothing lands in `runs/`. `conftest.py` forces `FORGEBENCH_CREDITS_MODE=off`; metering tests set their own mode and ledger with `monkeypatch`.

### Dashboard

`api.py` serves a vanilla JS single-page app from `src/forgebench/static/`, with no build step. `index.html` loads scripts with a cache-busting query (`app.js?v=30`), and history shows it bumped when the JS changes. `forgebench dashboard` defaults to port 8501, though the README says 8502. Setting `FORGEBENCH_TOKEN` requires an `x-forgebench-token` header on `/api/*`.

### Credits and configuration

- `consume_run` meters both pipelines after the data loads and the provider is built, but before inference, so a run that can't start costs nothing. `FORGEBENCH_CREDITS_MODE` is `off` (default), `observe`, or `enforce`. The ledger is `.forgebench/credits.json`, which is git-ignored.
- `services/stripe_webhook/` is a separate FastAPI process on `:8583` that turns Stripe checkouts into voucher codes (`make stripe`). It isn't part of the harness.
- Test and tooling path overrides: `FORGEBENCH_DATASETS_ROOT`, `FORGEBENCH_TASKS_ROOT`, `FORGEBENCH_PROMPTS_ROOT`, `FORGEBENCH_CREDITS_PATH`.
- Config YAML expands `${ENV_VAR}` and fails loudly if the variable is missing. All config sections use `extra="forbid"`, so an unknown key is an error.

`promo-video/` (Remotion) and `presentation/` are marketing assets, unrelated to the harness.

# ForgeBench

**Measure domain adaptation, not just model intelligence.**

ForgeBench is a small, reproducible benchmark for answering one question: did
customizing a model — a better prompt, few-shot examples, structured output, a
fine-tune — actually improve performance on a specific domain task, or did it
just make the pipeline more complicated?

The first benchmark domain is **financial operations**: synthetic banking and
accounting scenarios (transaction exception classification and reconciliation
triage). No private data, no GPU, no API key required to run the pipeline.

## Why this exists

Teams routinely customize language models and then show a few impressive
examples as "proof" it worked. That is not evidence. ForgeBench provides:

- A **fixed, versioned synthetic test set** with deterministic ground truth.
- A **pluggable provider interface** (deterministic mock + Mistral adapter today).
- **Strict output validation** — a plausible explanation is not a correct answer.
- Metrics chosen for financial operations risk, not just accuracy:
  critical false-match rate and escalation recall are tracked separately.
- **Full run manifests**: dataset hash, config, model id, versions, timestamps.
- **Machine-readable results** (JSON/JSONL) plus a Markdown report.

ForgeBench does *not* claim to replace Mistral's Forge evaluation system or
any enterprise platform. It is a lightweight, transparent harness that makes
experiments reviewable and comparable, with a clean seam where a
customization-trained model can plug in later (see
[docs/forge_integration.md](docs/forge_integration.md)).

## Quickstart

Requires Python 3.11+.

```bash
git clone https://github.com/your-org/forgebench
cd forgebench
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# The whole pipeline, offline, in three commands:
forgebench validate-dataset finance_v1
forgebench run --config configs/baseline.yaml --run-id baseline
forgebench run --config configs/experiments/prompt_v1.yaml --run-id prompt-v1
forgebench compare runs/baseline runs/prompt-v1
```

Each run writes `predictions.jsonl`, `metrics.json`, `manifest.json`, and
`report.md` under `runs/<run-id>/`.

### Running against a real Mistral model (bring your own key)

```bash
# Paste your key at a hidden prompt; it is saved to the git-ignored .env (chmod 600)
# and verified against api.mistral.ai. Never committed, never in run artifacts.
forgebench set-key
forgebench set-key --model ministral-8b-2512   # also save the default model id
forgebench set-key --show                      # masked status + where it's stored
forgebench set-key --clear                     # remove it

forgebench run --config configs/mistral_baseline.yaml --limit 5 --run-id smoke
forgebench run --config configs/mistral_baseline.yaml --run-id mistral-baseline
```

An exported `MISTRAL_API_KEY` in your shell still works and takes precedence
over `.env`. Config references like `${MISTRAL_MODEL}` resolve from either.

### Local dashboard (optional UI)

```bash
pip install -e ".[ui]"     # installs Streamlit once
forgebench dashboard       # opens http://127.0.0.1:8501
```

Three tabs: **API key** (paste, save, verify, remove — same `.env` storage as
`set-key`), **Run** (pick a config, optional case limit, live progress), and
**Results** (single-run report or N-way comparison). The UI calls the exact
same runner and reporting code as the CLI, so artifacts are identical.

## CLI

| Command | What it does |
| --- | --- |
| `forgebench list-datasets` | Show datasets in the registry |
| `forgebench validate-dataset NAME` | Schema, id, split, family, and class checks |
| `forgebench run --config CFG` | Run one experiment, write all artifacts |
| `forgebench set-key` | Save/show/clear a Mistral API key in the git-ignored `.env` |
| `forgebench dashboard` | Local web UI: paste key, run benchmarks, compare results |
| `forgebench compare RUN_A RUN_B` | Metric table with deltas vs. a baseline run |
| `forgebench report RUN` | (Re)generate the Markdown report for a run |

## Metrics

| Metric | Definition | Why it matters |
| --- | --- | --- |
| Accuracy | Correct / schema-valid classifications | Overall performance |
| Macro-F1 | Mean F1 across classes with ground truth | Common classes can't dominate |
| Critical false-match rate | Truly non-matching cases wrongly called `matched` | The financially dangerous error |
| Escalation recall | Cases requiring review that were escalated | Missed exceptions |
| Schema validity | Structured outputs / all outputs | Integration reliability |
| p50 / p95 latency | Median and tail response time | Operational performance |
| Cost per 1,000 cases | Estimated inference cost (historical price table) | Budget comparison |

Denominator conventions and evaluation rules are specified in
[docs/benchmark_protocol.md](docs/benchmark_protocol.md).

## The benchmark task

Each case shows one bank line item next to its ledger counterpart. The model
must return JSON classifying the exception:

```json
{
  "category": "amount_mismatch",
  "requires_review": true,
  "reason": "The bank and ledger amounts differ.",
  "evidence_fields": ["bank_amount", "ledger_amount"]
}
```

Allowed categories: `matched`, `amount_mismatch`, `date_mismatch`,
`reference_mismatch`, `duplicate`, `ambiguous`. Unknown categories, malformed
JSON, and evidence fields not present in the case are all rejected and counted
against schema validity.

## Dataset

`datasets/finance_v1` — 200 fully synthetic cases (100 train / 40 dev / 60
test) across six scenario families, generated by deterministic rules in
`scripts/generate_dataset.py`. Same seed, byte-identical files. See
[datasets/finance_v1/dataset_card.md](datasets/finance_v1/dataset_card.md).

## Repository layout

```
configs/           experiment configs (dataset + provider + prompt + metrics)
datasets/          versioned synthetic datasets + dataset cards
src/forgebench/    CLI, runner, registry, providers, metrics, reporting
scripts/           deterministic dataset generator
tests/             unit + end-to-end tests (no API key needed)
docs/              architecture, protocol, integration notes, results
runs/              local run artifacts (git-ignored by default)
```

## Limitations

- Synthetic data. Good results here do **not** imply production readiness on
  real banking data.
- With a 60-case test set, small differences are noise. Report sample sizes,
  per-class results, and error examples with any comparison.
- Cost estimates use a historical price table; verify current pricing and
  label results with the measurement date.
- The mock provider is a deterministic rule engine. It validates the
  pipeline, not model quality.
- Nothing here is a production finance system: no approvals, audit trail, or
  access control. Deterministic rules own matching thresholds and money math;
  the model classifies and explains.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Good first contributions: additional
provider adapters, synthetic datasets for new domains, metrics, and
independently reproduced runs.

## License

Code: [Apache-2.0](LICENSE). Model weights and third-party datasets carry
their own terms — check each model card and license independently.

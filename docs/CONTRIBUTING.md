# Contributing to ForgeBench

Thanks for helping. This project's credibility rests on reproducibility, so
contributions are small, tested, and documented by default.

## Ground rules

1. **Benchmark data and evaluation code stay versioned.** Never change an
   existing dataset in place; bump the version (e.g. `finance_v2`) and keep
   the old one, or results become incomparable.
2. **Record what you measured.** Any published result must include the run
   manifest: model id, dataset version + split hash, config, timestamp.
3. **Publish failures too.** A negative result about a prompt variant or
   adapter is as valuable as a positive one.
4. **Disclose differences.** Never present a comparison without showing the
   model, dataset, inference settings, and (for local models) hardware.
5. **No secrets, ever.** `.env`, API keys, and raw logs containing credentials
   do not belong in commits.

## Development setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
make test        # pytest — fully offline, uses the mock provider
make lint        # ruff check
make data        # regenerate the dataset (deterministic; must be a no-op diff)
make demo        # end-to-end mock run + comparison
```

## Adding things

### A provider adapter

Implement the `ModelProvider` contract in `src/forgebench/providers/`:

```python
def predict(self, case: BenchmarkCase) -> ProviderResponse: ...
```

Raise `ProviderError` only when no answer could be obtained (network, auth);
a bad model answer is not an error — the runner scores it. Add a factory entry
in `providers/__init__.py` and contract tests mirroring
`tests/test_provider_contract.py`.

### A metric

Metrics are pure functions over `list[PredictionRecord]`. Document the
denominator explicitly in the module docstring and add a hand-computed unit
test in `tests/test_metrics.py`.

### A dataset

Generate it with deterministic rules (no model labels), write a dataset card,
and make `forgebench validate-dataset` pass. Document the ground-truth rules
and any precedence between overlapping signals.

## Pull requests

- One concern per PR. A new provider, a new metric, and a dataset re-shuffle
  are three PRs.
- Tests accompany behavior changes. The suite must pass offline.
- Update the docs you touched (`docs/`, README) in the same PR.
- Config and report changes: attach the relevant `report.md` or comparison
  table to the PR description.

## Reporting issues

Include: the run manifest (`manifest.json`), the config file, your platform
and Python version, and the exact command. For result disagreements, attach
`predictions.jsonl` (it contains model outputs — redact anything sensitive).

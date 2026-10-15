# Results

This file records published runs. Every entry links its artifacts; nothing
here is a claim about model quality unless a real model produced it.

## Mock-provider reference runs (pipeline validation, 2026-10-15)

**These are not model results.** The mock provider is a deterministic rule
engine with a seeded defect rate. Its purpose is proving the harness works
end to end offline. The numbers below are what the pipeline produces for two
offline configs, and they double as the expected output of `make demo`.

Setup: `finance_v1` v1.0.0, test split (60 cases, sha256 `be681ada35cb…`),
sequential execution, Python 3.15, forgebench 0.1.0.

| Metric | baseline (defect 0.10) | prompt-v1 (defect 0.04) | Δ |
| --- | ---: | ---: | ---: |
| Accuracy | 0.8214 | 0.8667 | +0.0452 |
| Macro-F1 | 0.7334 | 0.7776 | +0.0442 |
| Critical false-match rate | 0.0952 | 0.0667 | −0.0286 |
| Escalation recall | 0.9048 | 0.9333 | +0.0286 |
| Schema validity | 0.9333 | 1.0000 | +0.0667 |
| p50 / p95 latency | 26.5 / 40.6 ms | 26.5 / 40.6 ms | 0 |
| Est. cost / 1,000 cases | $0 (mock) | $0 (mock) | 0 |

## What the errors actually show

Per-family accuracy for the baseline run:

| Family | Accuracy | Comment |
| --- | ---: | --- |
| date_mismatch | 1.00 | Rule-representable; trivially handled |
| matched | 1.00 | Same |
| amount_mismatch | 0.91 | One injected defect + one malformed output |
| reference_mismatch | 0.89 | Defects; also the main source of false matches |
| duplicate | 0.80 | Small support (6 cases); one malformed output |
| ambiguous | 0.00 | **By construction** — a rule engine cannot resolve it |

The interesting number is not the 0.82 accuracy. It is:

- **`ambiguous` F1 = 0.** The task family that requires judgment is exactly
  where a rules-only approach fails, which is the honest case for testing
  model customization. A customized model's value would show up *here*.
- **Critical false-match rate ≈ 0.09.** Wrongly declaring a discrepancy
  "matched" is the financially dangerous error; it is tracked separately
  from accuracy so improvements elsewhere cannot mask it.
- **12.5% of failures are output-format failures**, not judgment failures.
  Schema validity catches what accuracy alone would hide.

## Reproducing

```bash
make demo
# or, artifact by artifact:
forgebench run --config configs/baseline.yaml --run-id baseline-v1-mock
forgebench run --config configs/experiments/prompt_v1.yaml --run-id prompt-v1-mock
forgebench compare runs/baseline-v1-mock runs/prompt-v1-mock
python examples/inspect_run.py runs/baseline-v1-mock
```

Regeneration is deterministic: same seed, same predictions, same metrics.

## Not yet published

- **Real Mistral baseline.** Requires `MISTRAL_API_KEY`. Run
  `configs/mistral_baseline.yaml` (start with `--limit 5`), then add the run
  id, model id, timestamp, and full per-class table here. Do not publish a
  cost or latency number without its price basis and measurement date.
- **Prompt-variant comparisons on a real model.** Same procedure, then one
  `forgebench compare` table plus an error analysis of what actually changed.
- **Customized-model results.** Blocked on the workflow described in
  [forge_integration.md](forge_integration.md).

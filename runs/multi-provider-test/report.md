# ForgeBench report: multi-provider-test

- **Experiment:** baseline
- **Provider / model:** mock / `rule-mock-v1`
- **Dataset:** finance_v1 v1.0.0 (split: test, sha256: `be681ada35cb…`)
- **Cases:** 5 (5 schema-valid)
- **Run at (UTC):** 2026-10-15T19:52:20+00:00
- **forgebench:** 0.1.0 / Python 3.15.0

## Headline metrics

| Metric | Value |
| --- | ---: |
| Accuracy | 0.8 |
| Macro-F1 | 0.6667 |
| Critical false-match rate | 0 |
| Escalation recall | 1 |
| Schema validity | 1 |
| p50 latency | 34.78 ms |
| p95 latency | 40.36 ms |
| Est. cost / 1,000 cases | $0 |

## Per-class results (schema-valid predictions)

| Category | Support | Precision | Recall | F1 |
| --- | ---: | ---: | ---: | ---: |
| matched | 1 | 1 | 1 | 1 |
| amount_mismatch | 2 | 1 | 1 | 1 |
| reference_mismatch | 1 | 0.5 | 1 | 0.6667 |
| ambiguous | 1 | 0 | 0 | 0 |

## Results by scenario family

| Family | Cases | Valid | Accuracy (valid) |
| --- | ---: | ---: | ---: |
| ambiguous | 1 | 1 | 0 |
| amount_mismatch | 2 | 2 | 1 |
| matched | 1 | 1 | 1 |
| reference_mismatch | 1 | 1 | 1 |

## Error examples (first 8)

- **FIN-0145** (ambiguous): expected `ambiguous`, predicted `reference_mismatch`

## Cost assumptions

- Basis: input $0.0/Mtok, output $0.0/Mtok, as of n/a
- Note: mock provider incurs no API cost

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

# ForgeBench report: mock-override-test

- **Experiment:** baseline
- **Provider / model:** Mock / `rule-mock-v1`
- **Dataset:** finance_v1 v1.0.0 (split: test, sha256: `be681ada35cb…`)
- **Cases:** 3 (3 schema-valid)
- **Run at (UTC):** 2026-10-15T20:00:42+00:00
- **forgebench:** 0.1.0 / Python 3.15.0

## Headline metrics

| Metric | Value |
| --- | ---: |
| Accuracy | 1 |
| Macro-F1 | 1 |
| Critical false-match rate | 0 |
| Escalation recall | 1 |
| Schema validity | 1 |
| p50 latency | 34.78 ms |
| p95 latency | 35.22 ms |
| Est. cost / 1,000 cases | $0 |

## Per-class results (schema-valid predictions)

| Category | Support | Precision | Recall | F1 |
| --- | ---: | ---: | ---: | ---: |
| matched | 1 | 1 | 1 | 1 |
| amount_mismatch | 1 | 1 | 1 | 1 |
| reference_mismatch | 1 | 1 | 1 | 1 |

## Results by scenario family

| Family | Cases | Valid | Accuracy (valid) |
| --- | ---: | ---: | ---: |
| amount_mismatch | 1 | 1 | 1 |
| matched | 1 | 1 | 1 |
| reference_mismatch | 1 | 1 | 1 |

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

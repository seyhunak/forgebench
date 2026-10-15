# ForgeBench report: legal-baseline

- **Experiment:** legal-baseline
- **Provider / model:** Mock / `rule-mock-v1`
- **Dataset:** legal_v1 v1.0.0 (split: test, sha256: `8442441055bf…`)
- **Cases:** 42 (38 schema-valid)
- **Run at (UTC):** 2026-10-16T09:30:09+00:00
- **forgebench:** 0.1.0 / Python 3.15.0

## Headline metrics

| Metric | Value |
| --- | ---: |
| Accuracy | 0.5 |
| Macro-F1 | 0.3618 |
| Critical false-match rate | 0.4483 |
| Escalation recall | 0.5517 |
| Schema validity | 0.9048 |
| p50 latency | 28.58 ms |
| p95 latency | 40.83 ms |
| Est. cost / 1,000 cases | $0 |

## Per-class results (schema-valid predictions)

| Category | Support | Precision | Recall | F1 |
| --- | ---: | ---: | ---: | ---: |
| matched | 9 | 0.381 | 0.8889 | 0.5333 |
| amount_mismatch | 8 | 0 | 0 | 0 |
| date_mismatch | 6 | 0.8571 | 1 | 0.9231 |
| reference_mismatch | 5 | 0.5556 | 1 | 0.7143 |
| duplicate | 6 | 0 | 0 | 0 |
| ambiguous | 4 | 0 | 0 | 0 |

## Results by scenario family

| Family | Cases | Valid | Accuracy (valid) |
| --- | ---: | ---: | ---: |
| ambiguous | 4 | 4 | 0 |
| amount_mismatch | 8 | 8 | 0 |
| date_mismatch | 6 | 6 | 1 |
| duplicate | 6 | 6 | 0 |
| matched | 11 | 9 | 0.8889 |
| reference_mismatch | 7 | 5 | 1 |

## Output validity

| Failure kind | Count |
| --- | ---: |
| malformed_json | 4 |

## Error examples (first 8)

- **LG-0048** (amount_mismatch): expected `amount_mismatch`, predicted `matched`
- **LG-0036** (amount_mismatch): expected `amount_mismatch`, predicted `matched`
- **LG-0099** (ambiguous): expected `ambiguous`, predicted `reference_mismatch`
- **LG-0042** (amount_mismatch): expected `amount_mismatch`, predicted `matched`
- **LG-0090** (duplicate): expected `duplicate`, predicted `matched`
- **LG-0091** (duplicate): expected `duplicate`, predicted `matched`
- **LG-0044** (amount_mismatch): expected `amount_mismatch`, predicted `matched`
- **LG-0096** (ambiguous): expected `ambiguous`, predicted `reference_mismatch`

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

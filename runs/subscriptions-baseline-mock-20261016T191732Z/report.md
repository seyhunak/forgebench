# ForgeBench report: subscriptions-baseline-mock-20261016T191732Z

- **Experiment:** subscriptions-baseline
- **Provider / model:** Mock / `rule-mock-v1`
- **Dataset:** subscriptions_v1 v1.0.0 (split: test, sha256: `a97f0c3dccd1…`)
- **Cases:** 42 (38 schema-valid)
- **Run at (UTC):** 2026-10-16T19:17:32+00:00
- **forgebench:** 0.1.0 / Python 3.15.0

## Headline metrics

| Metric | Value |
| --- | ---: |
| Accuracy | 0.5526 |
| Macro-F1 | 0.3676 |
| Critical false-match rate | 0.3846 |
| Escalation recall | 0.6154 |
| Schema validity | 0.9048 |
| p50 latency | 24.67 ms |
| p95 latency | 40.55 ms |
| Est. cost / 1,000 cases | $0 |

## Per-class results (schema-valid predictions)

| Category | Support | Precision | Recall | F1 |
| --- | ---: | ---: | ---: | ---: |
| matched | 12 | 0.5455 | 1 | 0.7059 |
| amount_mismatch | 7 | 0 | 0 | 0 |
| date_mismatch | 3 | 0.6 | 1 | 0.75 |
| reference_mismatch | 6 | 0.6 | 1 | 0.75 |
| duplicate | 5 | 0 | 0 | 0 |
| ambiguous | 5 | 0 | 0 | 0 |

## Results by scenario family

| Family | Cases | Valid | Accuracy (valid) |
| --- | ---: | ---: | ---: |
| ambiguous | 5 | 5 | 0 |
| amount_mismatch | 9 | 7 | 0 |
| date_mismatch | 3 | 3 | 1 |
| duplicate | 5 | 5 | 0 |
| matched | 14 | 12 | 1 |
| reference_mismatch | 6 | 6 | 1 |

## Output validity

| Failure kind | Count |
| --- | ---: |
| malformed_json | 4 |

## Error examples (first 8)

- **SB-0089** (duplicate): expected `duplicate`, predicted `matched`
- **SB-0011** (matched): expected `matched`, predicted `<malformed_json>` — no JSON object found in response
- **SB-0098** (ambiguous): expected `ambiguous`, predicted `reference_mismatch`
- **SB-0097** (ambiguous): expected `ambiguous`, predicted `reference_mismatch`
- **SB-0038** (amount_mismatch): expected `amount_mismatch`, predicted `matched`
- **SB-0022** (matched): expected `matched`, predicted `<malformed_json>` — no JSON object found in response
- **SB-0046** (amount_mismatch): expected `amount_mismatch`, predicted `matched`
- **SB-0039** (amount_mismatch): expected `amount_mismatch`, predicted `<malformed_json>` — no JSON object found in response

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

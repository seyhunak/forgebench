# ForgeBench report: prompt-v1-mock

- **Experiment:** prompt-v1
- **Provider / model:** mock / `rule-mock-v1`
- **Dataset:** finance_v1 v1.0.0 (split: test, sha256: `be681ada35cb…`)
- **Cases:** 60 (60 schema-valid)
- **Run at (UTC):** 2026-10-15T17:21:25+00:00
- **forgebench:** 0.1.0 / Python 3.15.0

## Headline metrics

| Metric | Value |
| --- | ---: |
| Accuracy | 0.8667 |
| Macro-F1 | 0.7776 |
| Critical false-match rate | 0.0667 |
| Escalation recall | 0.9333 |
| Schema validity | 1 |
| p50 latency | 26.53 ms |
| p95 latency | 40.57 ms |
| Est. cost / 1,000 cases | $0 |

## Per-class results (schema-valid predictions)

| Category | Support | Precision | Recall | F1 |
| --- | ---: | ---: | ---: | ---: |
| matched | 15 | 0.8333 | 1 | 0.9091 |
| amount_mismatch | 12 | 1 | 0.9167 | 0.9565 |
| date_mismatch | 10 | 1 | 1 | 1 |
| reference_mismatch | 10 | 0.6667 | 1 | 0.8 |
| duplicate | 6 | 1 | 1 | 1 |
| ambiguous | 7 | 0 | 0 | 0 |

## Results by scenario family

| Family | Cases | Valid | Accuracy (valid) |
| --- | ---: | ---: | ---: |
| ambiguous | 7 | 7 | 0 |
| amount_mismatch | 12 | 12 | 0.9167 |
| date_mismatch | 10 | 10 | 1 |
| duplicate | 6 | 6 | 1 |
| matched | 15 | 15 | 1 |
| reference_mismatch | 10 | 10 | 1 |

## Error examples (first 8)

- **FIN-0145** (ambiguous): expected `ambiguous`, predicted `reference_mismatch`
- **FIN-0152** (ambiguous): expected `ambiguous`, predicted `reference_mismatch`
- **FIN-0164** (ambiguous): expected `ambiguous`, predicted `matched`
- **FIN-0168** (ambiguous): expected `ambiguous`, predicted `reference_mismatch`
- **FIN-0169** (amount_mismatch): expected `amount_mismatch`, predicted `reference_mismatch`
- **FIN-0176** (ambiguous): expected `ambiguous`, predicted `reference_mismatch`
- **FIN-0184** (ambiguous): expected `ambiguous`, predicted `matched`
- **FIN-0187** (ambiguous): expected `ambiguous`, predicted `matched`

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

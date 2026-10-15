# ForgeBench report: ui-base

- **Experiment:** baseline
- **Provider / model:** Ollama / `nemotron-3-nano:4b`
- **Dataset:** finance_v1 v1.0.0 (split: test, sha256: `be681ada35cb…`)
- **Cases:** 6 (5 schema-valid)
- **Run at (UTC):** 2026-10-17T09:06:31+00:00
- **forgebench:** 0.1.0 / Python 3.15.0

## Headline metrics

| Metric | Value |
| --- | ---: |
| Accuracy | 1 |
| Macro-F1 | 1 |
| Critical false-match rate | 0 |
| Escalation recall | 0.25 |
| Schema validity | 0.8333 |
| p50 latency | 3827.11 ms |
| p95 latency | 8125.92 ms |
| Est. cost / 1,000 cases | $0 |

## Per-class results (schema-valid predictions)

| Category | Support | Precision | Recall | F1 |
| --- | ---: | ---: | ---: | ---: |
| matched | 1 | 1 | 1 | 1 |
| amount_mismatch | 2 | 1 | 1 | 1 |
| reference_mismatch | 1 | 1 | 1 | 1 |
| duplicate | 1 | 1 | 1 | 1 |

## Results by scenario family

| Family | Cases | Valid | Accuracy (valid) |
| --- | ---: | ---: | ---: |
| ambiguous | 1 | 0 | 0 |
| amount_mismatch | 2 | 2 | 1 |
| duplicate | 1 | 1 | 1 |
| matched | 1 | 1 | 1 |
| reference_mismatch | 1 | 1 | 1 |

## Output validity

| Failure kind | Count |
| --- | ---: |
| unknown_category | 1 |

## Error examples (first 8)

- **FIN-0145** (ambiguous): expected `ambiguous`, predicted `<unknown_category>` — schema violation: 1 validation error for Prediction
category
  Input should be 'matched', 'amount_mismatch', 'date_mismatch', 'reference_mismatch', 'duplicate' or 'ambiguous' [type=enum, input_value='date_amatch', input_type=str]
    For further information visit https://errors.pydantic.dev/2.14/v/enum

## Cost assumptions

- Basis: input $0.0/Mtok, output $0.0/Mtok, as of unknown
- Note: no price table entry; cost reported as 0 with a warning

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

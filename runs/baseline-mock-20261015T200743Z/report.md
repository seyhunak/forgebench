# ForgeBench report: baseline-mock-20261015T200743Z

- **Experiment:** baseline
- **Provider / model:** Mock / `rule-mock-v1`
- **Dataset:** finance_v1 v1.0.0 (split: test, sha256: `be681ada35cb…`)
- **Cases:** 60 (56 schema-valid)
- **Run at (UTC):** 2026-10-15T20:07:43+00:00
- **forgebench:** 0.1.0 / Python 3.15.0

## Headline metrics

| Metric | Value |
| --- | ---: |
| Accuracy | 0.8214 |
| Macro-F1 | 0.7334 |
| Critical false-match rate | 0.0952 |
| Escalation recall | 0.9048 |
| Schema validity | 0.9333 |
| p50 latency | 26.53 ms |
| p95 latency | 40.57 ms |
| Est. cost / 1,000 cases | $0 |

## Per-class results (schema-valid predictions)

| Category | Support | Precision | Recall | F1 |
| --- | ---: | ---: | ---: | ---: |
| matched | 14 | 0.7778 | 1 | 0.875 |
| amount_mismatch | 11 | 0.9091 | 0.9091 | 0.9091 |
| date_mismatch | 10 | 1 | 1 | 1 |
| reference_mismatch | 9 | 0.6154 | 0.8889 | 0.7273 |
| duplicate | 5 | 1 | 0.8 | 0.8889 |
| ambiguous | 7 | 0 | 0 | 0 |

## Results by scenario family

| Family | Cases | Valid | Accuracy (valid) |
| --- | ---: | ---: | ---: |
| ambiguous | 7 | 7 | 0 |
| amount_mismatch | 12 | 11 | 0.9091 |
| date_mismatch | 10 | 10 | 1 |
| duplicate | 6 | 5 | 0.8 |
| matched | 15 | 14 | 1 |
| reference_mismatch | 10 | 9 | 0.8889 |

## Output validity

| Failure kind | Count |
| --- | ---: |
| malformed_json | 3 |
| unknown_evidence_field | 1 |

## Error examples (first 8)

- **FIN-0145** (ambiguous): expected `ambiguous`, predicted `reference_mismatch`
- **FIN-0152** (ambiguous): expected `ambiguous`, predicted `reference_mismatch`
- **FIN-0155** (amount_mismatch): expected `amount_mismatch`, predicted `<malformed_json>` — no JSON object found in response
- **FIN-0156** (reference_mismatch): expected `reference_mismatch`, predicted `amount_mismatch`
- **FIN-0160** (duplicate): expected `duplicate`, predicted `<malformed_json>` — no JSON object found in response
- **FIN-0164** (ambiguous): expected `ambiguous`, predicted `matched`
- **FIN-0168** (ambiguous): expected `ambiguous`, predicted `reference_mismatch`
- **FIN-0169** (amount_mismatch): expected `amount_mismatch`, predicted `matched`

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

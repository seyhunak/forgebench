# ForgeBench report: subscriptions-baseline-mistral-20261018T093118Z

- **Task / experiment:** subscriptions-baseline
- **Provider / model:** Mistral / `openai/gpt-4o-mini`
- **Dataset:** subscriptions_v1 v1.0.0 (split: test, sha256: `a97f0c3dccd1…`)
- **Cases:** 42 (0 schema-valid)
- **Run at (UTC):** 2026-10-18T09:31:18+00:00
- **forgebench:** 0.1.0 / Python 3.15.0

## Headline metrics

| Metric | Value |
| --- | ---: |
| Accuracy | 0 |
| Macro-F1 | 0 |
| Critical false-match rate | 0 |
| Escalation recall | 0 |
| Schema validity | 0 |
| p50 latency | 0 ms |
| p95 latency | 0 ms |
| Est. cost / 1,000 cases | $0 |

## Results by scenario family

| Family | Cases | Valid | Accuracy (valid) |
| --- | ---: | ---: | ---: |
| ambiguous | 5 | 0 | 0 |
| amount_mismatch | 9 | 0 | 0 |
| date_mismatch | 3 | 0 | 0 |
| duplicate | 5 | 0 | 0 |
| matched | 14 | 0 | 0 |
| reference_mismatch | 6 | 0 | 0 |

## Output validity

| Failure kind | Count |
| --- | ---: |
| provider_error | 42 |

## Error examples (first 8)

- **SB-0010** (matched): expected `matched`, predicted `<provider_error>` — mistral call failed for case SB-0010 after 3 attempt(s): API error occurred: Status 400. Body: {"object":"error","message":"Invalid model: openai/gpt-4o-mini","type":"invalid_model","param":null,"code":"1500","raw_status_code":400}
- **SB-0089** (duplicate): expected `duplicate`, predicted `<provider_error>` — mistral call failed for case SB-0089 after 3 attempt(s): API error occurred: Status 400. Body: {"object":"error","message":"Invalid model: openai/gpt-4o-mini","type":"invalid_model","param":null,"code":"1500","raw_status_code":400}
- **SB-0011** (matched): expected `matched`, predicted `<provider_error>` — mistral call failed for case SB-0011 after 3 attempt(s): API error occurred: Status 400. Body: {"object":"error","message":"Invalid model: openai/gpt-4o-mini","type":"invalid_model","param":null,"code":"1500","raw_status_code":400}
- **SB-0098** (ambiguous): expected `ambiguous`, predicted `<provider_error>` — mistral call failed for case SB-0098 after 3 attempt(s): API error occurred: Status 400. Body: {"object":"error","message":"Invalid model: openai/gpt-4o-mini","type":"invalid_model","param":null,"code":"1500","raw_status_code":400}
- **SB-0097** (ambiguous): expected `ambiguous`, predicted `<provider_error>` — mistral call failed for case SB-0097 after 3 attempt(s): API error occurred: Status 400. Body: {"object":"error","message":"Invalid model: openai/gpt-4o-mini","type":"invalid_model","param":null,"code":"1500","raw_status_code":400}
- **SB-0038** (amount_mismatch): expected `amount_mismatch`, predicted `<provider_error>` — mistral call failed for case SB-0038 after 3 attempt(s): API error occurred: Status 400. Body: {"object":"error","message":"Invalid model: openai/gpt-4o-mini","type":"invalid_model","param":null,"code":"1500","raw_status_code":400}
- **SB-0069** (reference_mismatch): expected `reference_mismatch`, predicted `<provider_error>` — mistral call failed for case SB-0069 after 3 attempt(s): API error occurred: Status 400. Body: {"object":"error","message":"Invalid model: openai/gpt-4o-mini","type":"invalid_model","param":null,"code":"1500","raw_status_code":400}
- **SB-0022** (matched): expected `matched`, predicted `<provider_error>` — mistral call failed for case SB-0022 after 3 attempt(s): API error occurred: Status 400. Body: {"object":"error","message":"Invalid model: openai/gpt-4o-mini","type":"invalid_model","param":null,"code":"1500","raw_status_code":400}

## Cost assumptions

- Basis: input $0.0/Mtok, output $0.0/Mtok, as of unknown
- Token counts were **estimated** (chars/4) for at least one response because the provider did not report usage.
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

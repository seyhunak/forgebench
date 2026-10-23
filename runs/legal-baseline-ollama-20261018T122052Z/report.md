# ForgeBench report: legal-baseline-ollama-20261018T122052Z

- **Task / experiment:** legal-baseline
- **Provider / model:** Ollama / `openai/gpt-4o-mini`
- **Dataset:** legal_v1 v1.0.0 (split: test, sha256: `8442441055bf…`)
- **Cases:** 42 (0 schema-valid)
- **Run at (UTC):** 2026-10-18T12:20:52+00:00
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
| ambiguous | 4 | 0 | 0 |
| amount_mismatch | 8 | 0 | 0 |
| date_mismatch | 6 | 0 | 0 |
| duplicate | 6 | 0 | 0 |
| matched | 11 | 0 | 0 |
| reference_mismatch | 7 | 0 | 0 |

## Output validity

| Failure kind | Count |
| --- | ---: |
| provider_error | 42 |

## Error examples (first 8)

- **LG-0078** (reference_mismatch): expected `reference_mismatch`, predicted `<provider_error>` — ollama call for case LG-0078 failed after 3 attempt(s): ProviderError: ollama daemon not answering at http://127.0.0.1:11434: HTTP Error 404: Not Found
- **LG-0025** (matched): expected `matched`, predicted `<provider_error>` — ollama call for case LG-0025 failed after 3 attempt(s): ProviderError: ollama daemon not answering at http://127.0.0.1:11434: HTTP Error 404: Not Found
- **LG-0011** (matched): expected `matched`, predicted `<provider_error>` — ollama call for case LG-0011 failed after 3 attempt(s): ProviderError: ollama daemon not answering at http://127.0.0.1:11434: HTTP Error 404: Not Found
- **LG-0048** (amount_mismatch): expected `amount_mismatch`, predicted `<provider_error>` — ollama call for case LG-0048 failed after 3 attempt(s): ProviderError: ollama daemon not answering at http://127.0.0.1:11434: HTTP Error 404: Not Found
- **LG-0036** (amount_mismatch): expected `amount_mismatch`, predicted `<provider_error>` — ollama call for case LG-0036 failed after 3 attempt(s): ProviderError: ollama daemon not answering at http://127.0.0.1:11434: HTTP Error 404: Not Found
- **LG-0066** (reference_mismatch): expected `reference_mismatch`, predicted `<provider_error>` — ollama call for case LG-0066 failed after 3 attempt(s): ProviderError: ollama daemon not answering at http://127.0.0.1:11434: HTTP Error 404: Not Found
- **LG-0059** (date_mismatch): expected `date_mismatch`, predicted `<provider_error>` — ollama call for case LG-0059 failed after 3 attempt(s): ProviderError: ollama daemon not answering at http://127.0.0.1:11434: HTTP Error 404: Not Found
- **LG-0099** (ambiguous): expected `ambiguous`, predicted `<provider_error>` — ollama call for case LG-0099 failed after 3 attempt(s): ProviderError: ollama daemon not answering at http://127.0.0.1:11434: HTTP Error 404: Not Found

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

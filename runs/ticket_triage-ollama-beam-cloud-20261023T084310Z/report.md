# ForgeBench report: ticket_triage-ollama-beam-cloud-20261023T084310Z

- **Task / experiment:** ticket_triage
- **Provider / model:** Ollama / `beam:cloud`
- **Judge:** Ollama / `beam:cloud`
- **Cases:** 3 (0 schema-valid)
- **Run at (UTC):** 2026-10-23T08:43:10+00:00
- **forgebench:** None / Python None

## Headline metrics

| Metric | Value |
| --- | ---: |
| Accuracy | 0 |

## Per-rule results (custom task)

| Output field | Cases | Pass | Pass rate |
| --- | ---: | ---: | ---: |
| priority | 3 | 3 | 1 |
| reason | 3 | 0 | 0 |
| response_sla_hours | 3 | 2 | 0.6667 |
| team | 3 | 2 | 0.6667 |

## Error examples (first 8)

- **TX-0006** (custom): expected `matched`, predicted `<None>`
- **TX-0007** (custom): expected `matched`, predicted `<None>`
- **TX-0008** (custom): expected `matched`, predicted `<None>`

## Per-case results

| Case ID | Input | Expected | Predicted | Correct | OK | Error |
| --- | --- | --- | --- | --- | --- | --- |
| TX-0006 | subject=Outage; body=Service down for all users | matched | — | ❌ | ❌ | — |
| TX-0007 | subject=Billing question; body=How do I upgrade plan | matched | — | ❌ | ❌ | — |
| TX-0008 | subject=Late delivery; body=Package not delivered, need help | matched | — | ❌ | ❌ | — |

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

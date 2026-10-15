# Benchmark protocol

The rules that make two runs comparable. Deviating from this protocol is
allowed — silently comparing a deviation against a conforming run is not.

## Task

**Transaction exception classification.** Input: one bank line item and its
ledger counterpart (amounts, references, dates, vendor, optional occurrence
counts). Output: a JSON object classifying the exception and whether a human
must review it.

Output contract (validated with Pydantic; anything else is invalid):

```json
{
  "category": "amount_mismatch",
  "requires_review": true,
  "reason": "one sentence",
  "evidence_fields": ["bank_amount", "ledger_amount"]
}
```

Rules:

- `category` must be one of: `matched`, `amount_mismatch`, `date_mismatch`,
  `reference_mismatch`, `duplicate`, `ambiguous`.
- `requires_review` must be `true` for every category except `matched`.
- `evidence_fields` must name only fields present in the case input.
- Prose, fences, or extra JSON keys around/inside the object: extraction is
  attempted (see `parsing.py`); everything else is a schema violation.

## Ground truth

Labels are produced by deterministic rules in `scripts/generate_dataset.py`,
never by a model. When multiple signals fire, precedence is:

**duplicate > amount > reference > date**

`ambiguous` is reserved for constructed conflicts a rule engine cannot
resolve (e.g. one-character reference difference plus a one-day date shift).
Its ground truth is always "escalate to a human".

## Evaluation

1. **Split discipline.** Report on `test` only. Few-shot examples and prompt
   development use `train` (and `dev` for iteration). Never tune on `test`.
2. **Inference settings are recorded.** Temperature, retries, timeouts, max
   tokens, prompt text, and few-shot count live in the config and land in the
   manifest.
3. **Determinism.** Temperature 0 where supported. The mock provider is
   hash-deterministic per case id.
4. **Sequential execution** for reported runs, unless concurrency is disclosed.

## Metrics and denominators

| Metric | Numerator / Denominator |
| --- | --- |
| Accuracy | correct / **schema-valid** predictions |
| Macro-F1 | mean F1 over categories **with ground truth in the evaluated slice** |
| Critical false-match rate | predicted `matched` / truly non-matching cases (**schema-valid only**) |
| Escalation recall | predicted review / cases with `requires_review=true` (**schema-valid only**) |
| Schema validity | valid outputs / all outputs (invalid and provider errors included) |
| p50 / p95 latency | over all attempts, including failed ones' wall time where recorded |
| Cost per 1,000 cases | estimated from recorded (or chars/4-estimated) tokens × price table |

Invalid outputs are deliberately excluded from classification metrics and
counted separately. A model must not look accurate by failing loudly on hard
cases — but it must not look reliable either; read both numbers together.

## What a valid comparison requires

- Same dataset name, version, and split hash (see the manifests).
- Disclosed differences in provider, model, prompt, and inference settings.
- Reported sample size, per-class results, and error examples — not just
  headline numbers.
- Cost and latency claims labeled with measurement date and price basis.
- Small test sets (like the 60-case `finance_v1` test split): treat
  differences of a few points as noise unless per-class evidence says
  otherwise.

## Regression protocol

A change is a regression, not an improvement, if any of the following worsens
beyond noise while the headline metric improves:

- critical false-match rate (financial control risk),
- schema validity (integration reliability).


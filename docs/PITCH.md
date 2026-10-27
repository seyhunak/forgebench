# ForgeBench — Business Pitch

> **Tagline:** *Measure domain adaptation, not just model intelligence.*
>
> ForgeBench is a reproducible, provider-agnostic benchmark harness for one question:
> **did customizing a model — a better prompt, few-shot examples, structured output, a
> fine-tune — actually improve performance on the domain task, or did it just make the
> pipeline more complicated?**

---

## 1. Value proposition

**For teams shipping AI in finance, healthcare, legal, insurance, payments, procurement
and support operations:** ForgeBench turns "we think the new prompt is better" into a
pinned, auditable, cost-measured comparison on a fixed test set — before the change
reaches production.

| | Without ForgeBench | With ForgeBench |
|---|---|---|
| Model choice | Vendor decks and personal preference | One config, every provider scored by the same code; accuracy, risk metrics, latency and **cost per 1,000 cases** side by side |
| Prompt changes | Merged on vibes; regressions found in prod | Pin a baseline, compare a candidate, see exactly **which cases got worse**; fail the PR in CI past a tolerance |
| Model lifecycle | Some pasted prompt in a dashboard somewhere | A prompt registry with immutable versions and SHA-256 hashes — a run's manifest records the exact instructions it used |
| Domain fit | Generic MMLU scores that say nothing about the business task | Rule-generated ground truth in **9 operational domains**, with risk metrics matching the expensive errors |

**One-line value statement:** *To adopt an AI model, teams need numbers like this — ForgeBench is the tool that produces those numbers, on evidence that can be reproduced or refuted.*

---

## 2. Problems solved

1. **A demo is not an evaluation.** Teams pick a model, wire it in, and discover the
   misclassifications in production — where a false "matched" means money assumed
   reconciled. ForgeBench measures the model on a fixed, versioned test set first.
2. **Accuracy hides the expensive errors.** A model can hit 92% accuracy and still
   wrongly clear non-matching transactions. Critical false-match rate and escalation
   recall are tracked as separate, first-class metrics.
3. **Prompt drift is invisible.** Nobody can say which prompt version a past run used.
   ForgeBench's prompt registry + run manifests make the instructions provable.
4. **Benchmark claims can't be trusted.** Blog benchmarks use different data, prompts
   and scoring per experiment. Every ForgeBench run is self-describing (dataset hash,
   config, model, git SHA) — results can be reproduced or refuted.
5. **Cost is discovered from the invoice.** ForgeBench reports estimated cost per 1,000
   cases per run, from actual token usage with dated pricing — before the commitment.
6. **Structured output failures are silent.** Malformed JSON and unknown categories are
   rejected, scored as errors, and reported — a plausible-sounding model that can't emit
   valid output is flagged as useless in a pipeline.

---

## 3. Business value & benefits

| Business benefit | How it lands |
|---|---|
| **Lower model cost** | Pick the cheapest model that clears the risk metrics; cost per 1,000 cases is a headline metric. Sub-$0.10/M models exist in the default catalog — a 10× cost difference becomes a visible table, not a debate. |
| **Fewer production incidents and safer rollouts** | Regression gating on PR: accuracy drops beyond tolerance ⇒ the change fails CI, not customers. Critical false-match rate is the financially dangerous error, measured up front. |
| **Faster model decisions** | Swap providers without changing config (`--provider openai / anthropic / google / openrouter / ollama`). Decisions move from week-long evaluations to one afternoon. |
| **No ML infrastructure needed** | No GPU, no database, no paid platform. Python 3.11, flat files, bring-your-own-key. Use a hosted provider on one end or fully local (Ollama) with zero egress. |
| **Compliance-ready evidence** | Deterministic synthetic ground truth (no customer PII in the test path), SHA-256 dataset manifests, sanitized self-contained PDF-quality HTML exports safe to attach to a ticket or an audit file. Strong fit for regulated domains. |
| **Team adoption with near-zero training** | A CLI (`forgebench run`, `compare`, `history`) plus a local dashboard with key entry, dataset browsing, run launching and comparisons. Everything is a file — readable, diffable, shippable. |
| **Developer productivity** | Fourteen ready-made eval tasks run without code; custom tasks are YAML, not a new eval framework. The offline test path costs nothing to validate a pipeline change. |

---

## 4. How it costs

**Cost to run the self-hosted Community tier:**

| Cost item | What it looks like |
|---|---|
| ForgeBench itself | Community tier is free for internal evaluation; the product is proprietary — paid usage is credits ($0.10/run): packs of 50–500, dataset pack, Enterprise Unlimited $5,000. |
| Model spend | Bring-your-own-key; you pay the provider you configured, for exactly the tokens used. Cloud model defaults (e.g. Ollama `beam:cloud`) run on cloud-served hardware with no local GPU. Sub-dollar runs are normal with `--limit N` sampling during iteration. |
| Fully local path | $0 marginal spend — the Ollama adapter runs the whole harness on internal hardware with zero egress to third parties. |
| Cost per 1,000 cases | Reported directly in every run, comparison and history view from actual token usage with dated model pricing — so budget conversations have numbers attached. |
| Infrastructure | Flat JSONL/JSON files under `runs/` — nothing to provision, back up or migrate. A run directory is the deployment unit. |

**Commercial model (built in-repo, live when the Stripe account is configured):** the repo is closed-source; the Community tier is free for internal evaluation and **monetization is credits, not seats —

- **1 credit = $0.10.** Benchmark runs cost **30 credits ($3.00) flat** per run (one price whatever the case limit); custom-task runs cost **1 credit ($0.10) per case** (each case is one model call). Runs are counted by the local ledger (`.forgebench/credits.json`).
- **Packs — Starter 50/$5, Growth 100/$10, Scale 250/$25, Max 500/$50.** Stripe checkout → webhook voucher → `forgebench redeem` → local balance.
- **Domain dataset pack — 250 credits / $25**, from the same wallet.
- **Enterprise Unlimited — $5,000 one-time.** Unlimited runs, SSO/on-prem priorities, shapes the shared-backend roadmap.

This keeps community use free and unmodified while paid usage is measured exactly where value is produced: the runs themselves. Current state: the webhook listener, catalog, voucher store and redeem flow are implemented and tested (`services/stripe_webhook/`); billing stays dark until Stripe keys and payment links are configured.

This keeps the free self-hosted tier genuinely usable (adoption engine) while revenue lives where businesses need it: team scale, compliance, and CI automation.

---

## 5. Pricing positioning (relative to alternatives)

| Alternative | What it costs a business beyond dollars |
|---|---|
| Hand-rolled eval scripts | Weeks of engineering time; every team rebuilds it; nobody trusts someone else's numbers; no manifests, no regression gating. |
| Vendor "AI model eval" platforms | Per-seat SaaS with customer data on their cloud — a hard no for regulated domains, and the eval logic is a black box. |
| Generic academic benchmarks (MMLU, HumanEval) | Free but irrelevant: they don't measure the business task, the expensive errors, or the cost. |

ForgeBench's position: **Community tier free and local by design, auditable by construction, priced only when an organization needs team-scale access.**

---

## 6. Use cases (audience view)

| # | Use case | What ForgeBench gives you |
|---|----------|---------------------------|
| 1 | **Prompt / few-shot / fine-tune A/B validation** | Same fixed test set, same scoring code path, two runs, one `compare` with metric deltas *and* the exact cases that flipped. |
| 2 | **Model & provider selection** | One config, six providers (Mistral, OpenAI, Anthropic, Google, OpenRouter, Ollama) — swap `--provider`/`--model`, keep everything else identical. |
| 3 | **Regression gating in CI** | `templates/regression.yml`: offline gate (lint, tests, dataset reproducibility) + baseline-vs-candidate comparison that fails the PR past a tolerance. |
| 4 | **Regulated-domain evidence** | Nine synthetic datasets with rule-generated ground truth and SHA-256 manifests — auditable, reproducible, no customer data. |
| 5 | **Risk-aware quality measurement** | Critical false-match rate and escalation recall tracked *separately* from accuracy. |
| 6 | **Safety / red-team scanning** | `forgebench safety-scan` over prompt injection, jailbreak, PII, bias, toxicity — fully offline available. |
| 7 | **Custom evals without code** | YAML-defined tasks (input fields, output schema, weighted scoring): 14 ship in the repo. |
| 8 | **Subjective / RAG quality scoring** | G-Eval-style LLM-as-judge; RAGAS-style lexical RAG metrics with zero extra LLM calls. |
| 9 | **Independent reproduction** | Every run is self-describing → the result can be reproduced or refuted. |

---

## 7. Security (duty of care, sells itself)

- **No committed secrets.** Keys in git-ignored `.env` (chmod 600), provider-verified, masked per command. Shell-exported keys take precedence.
- **Minimal data flow.** Nothing uploaded except the configured provider — no telemetry, no analytics, no dataset egress. Every provider adapter documents its destination.
- **No private data required.** Synthetic rule-generated datasets carry no PII.
- **Optional dashboard auth** (`FORGEBENCH_TOKEN`) and exported HTML reports are Blu-sanitized, self-contained, no external assets.
- **Offline-by-design test suite** — the pipeline costs nothing and needs no network to validate.

---

## 8. DevOps (why it's trustworthy to run)

- CI runs lint, offline tests, and a byte-identical dataset reproducibility gate on every push.
- Runs record `manifest.json` (dataset SHA-256, config, model, package/git version, timestamps) — any number traces back to exact bytes.
- Everything is a file: no database migrations, no deployed state, semantic versioning, Keep-a-Changelog.

---

## 9. LLMOps summary

| Concern | Mechanism |
|---------|-----------|
| Prompt versioning | `prompts/<name>/vN.md` immutable versions + labels; runs record the SHA-256 of instructions actually sent |
| Experiment-as-code | YAML configs, `${ENV_VAR}` interpolation, fails loudly on missing config |
| Provider abstraction | One `predict(case)` contract across six providers + offline mock |
| Structured-output discipline | Malformed JSON and unknown categories rejected; schema validity is a first-class metric |
| LLM-as-judge | G-Eval criteria + steps; judge is advisory and never fails a run |
| Observability | `trace.jsonl` per run — provider call spans with token counts, parse & score, judge |
| Regression management | Pin a baseline per dataset; **Vs baseline** shows metric deltas + cases that improved/regressed; `forgebench history` gives the trend |
| Artifacts | `predictions.jsonl`, `metrics.json`, `manifest.json`, `trace.jsonl`, `report.md` + JSON/CSV/HTML export |

---

## 10. Scalability (today + designed-for path)

**Today:** sequential single-process runs on hundreds of cases (minutes), flat-file
storage, read-mostly local API. Honest and predictable.

**Designed for, not yet built:** threaded provider pool (concurrency knob at the
provider seam), shard-and-merge over JSONL, warehouse ingest (BigQuery/Snowflake/DuckDB),
real auth for multi-user access, local/air-gapped scale via Ollama.

---

## Suggested slide order

1. Problem — "did it actually get better, or just more complicated?"
2. Value proposition — the comparison table
3. Use cases (pick 3–4 per audience: ML platform vs. risk/compliance vs. product)
4. Live demo: `set-key` → `run` → `compare` (dashboard screenshots in `docs/screenshots/`)
5. Business benefits — cost, incidents, decisions, compliance
6. Security
7. DevOps
8. How it costs — the open-core model + cost-per-1,000-cases story
9. LLMOps
10. Scalability (today + growth path)
11. Roadmap / contribution invites

# Workflow Improvement Analysis — ForgeBench Benchmark Experiment

Critical workflow improvement adviser output for a real, evidence-based task: running a
ForgeBench benchmark experiment end to end and producing a defensible comparison
between a baseline model and a customized variant. All steps and artifacts below are
taken from the existing ForgeBench code, CLI, and docs — no invented data, savings or
system capabilities. Assumptions are labeled in section 6.

---

## How a person completes this task today

**Problem**  
Teams shipping AI in finance, healthcare, legal, insurance, payments, procurement or
support cannot tell whether a prompt, few-shot set, temperature change or model swap
actually improved domain-task performance. Decisions are ad-hoc, per-model and
non-reproducible; the dangerous regressions (wrongly approving a discrepancy,
"matched" when it is not) are tracked nowhere.

**Task**  
Run one reproducible benchmark experiment that compares a baseline provider/model
against a customized variant on a pinned domain test set, and report whether the
change improved the risk-aware metrics without degrading output reliability.

**Trigger**  
A developer or data scientist modifies a prompt, config, few-shot set, model or
provider and needs objective evidence before merging (typically a pull request or
release gate).

**Inputs**
- Experiment config YAML (`configs/<name>.yaml`) with experiment / provider /
  inference / prompt / evaluation sections
- A versioned dataset split (`datasets/<domain>_v1/<train|dev|test>.jsonl`) with a
  published SHA-256 in the manifest
- Provider credentials (BYOK in a git-ignored `.env`, chmod 600)
- Existing baseline run directory (`runs/<baseline>`) to compare against
- Optional: pinned prompt name@version from the prompt registry
  (`prompts/<name>/vN.md` + `labels.json`)

**Steps**
1. Validate the dataset (`forgebench validate-dataset <name>`).
2. Create or edit the experiment config (via `04 · Config` or by hand).
3. Run the baseline on the test split (`forgebench run --config configs/baseline.yaml
   --run-id baseline`). 1 credit per case for task runs, or 30 credits flat for a
   benchmark run.
4. Run the candidate variant with the same split, limit and provider.
5. Inspect artifacts: `predictions.jsonl`, `metrics.json`, `manifest.json`,
   `trace.jsonl`, `report.md`.
6. Compare runs (`forgebench compare runs/baseline runs/<candidate>`), checking
   accuracy, macro-F1, critical false-match rate, escalation recall, schema
   validity, p50/p95 latency, estimated cost.
7. Review per-case regressions and improvements in the comparison output.
8. Write the summary into `docs/results.md` (published runs) with run id, model
   id, timestamp and per-class table.
9. Decide: ship, iterate (prompt/provider/model) or stop. Gate the PR on the
   regression protocol (section 3.3 of `docs/benchmark_protocol.md`).

**Tools**
- ForgeBench CLI: `validate-dataset`, `run`, `compare`, `report`, `task-run`,
  `models`, `history`
- Dashboard (FastAPI, `forgebench dashboard`) views 01-07
- Schemas and validator: `forgebench.config.load_config`, `forgebench.registry`,
  `forgebench.tasks`
- Deterministic mock provider (rule engine) for offline pipeline validation
- GitHub Actions CI workflow (`.github/workflows/tests.yml`)
- Optional Stripe credit loop for metered runs (`services/stripe_webhook`)

**Output**
- `runs/<run-id>/` artifacts (manifest with dataset hash, config, model id,
  versions, timestamps, git SHA, prompt hash; `predictions.jsonl`, `metrics.json`,
  `trace.jsonl`, `report.md`)
- A comparison report with metric deltas and changed cases
- (Optional) An entry in `docs/results.md` for published runs

**Checks**
- Split discipline: report on `test` only; never tune on test
- Same dataset name + version + split hash across compared runs
- Determinism: temperature 0 where supported; sequential execution for reported runs
- Regression gate: critical false-match rate and schema validity must not worsen
  beyond noise even if headline accuracy improves
- Invalid outputs excluded from classification metrics and counted separately
  (`schema_validity`, `provider_error_rate`, `error_breakdown`)
- No secrets in artifacts (keys live in git-ignored `.env`, chmod 600)

---

## 1. STEPS — Which existing steps might be repetitive, slow or difficult?

In plain language:

- **Repetitive.** Steps 3 and 4 are nearly identical shell commands differing only in
  `--config` and `--run-id`; people run them back to back and sometimes mix up run
  names. The mock-provider path is run separately again just to confirm the
  pipeline still works.
- **Slow.** Each inference step is sequential by design (reproducibility, rate
  limits). Full splits of 42-70 cases at 30s timeout each is a lot of wall clock
  for one person, and a variant that fails the regression gate late in the run has
  already spent the time and credits.
- **Difficult.** Step 8 — writing `docs/results.md` — is manual and easy to get
  wrong (run ids, model ids, timestamps, per-class tables). Step 7 — "review per-case
  regressions" — means reading changed-case lists by hand. Step 5 — choosing which
  artifact to open — is a fork in the road (predictions vs. metrics vs. trace vs.
  report). Step 2 — editing YAML — is error prone; one typo and `load_config`
  fails loudly (which is good, but still slows you down). Task configs use a different
  CLI (`task-run`) and credential/consumption logic than benchmark configs, so
  running RAG crosses two code paths for no user-visible reason.

**Assumption.** Identified from the code paths in `forgebench/cli.py`, `runner.py`,
`task_runner.py` and the docs, not from user-observed timing. Concurrency is
deliberately unsupported today (README: "Sequential execution for reported runs
unless concurrency is disclosed").

---

## 2. KNOWLEDGE — What information would technology need to help?

To automate or assist, a helper would need to reliably know:

- **The experiment's intent** — does this run exist to compare prompt variants,
  providers, models, or agent hardening? Currently carried only in the config's
  `experiment.name` string; nothing structured.
- **Who the "baseline" is.** Which run directory is the pinned baseline for this
  dataset? That knowledge is not stored anywhere in the repository (assumption: it
  lives in the operator's head or in `docs/results.md` prose).
- **The history of prior runs** for the same task/dataset — trend and group
  deltas. `forgebench history` exists, but there is no persisted "last accepted
  run id."
- **The provider's catalog and pricing**. `configs` reference model strings like
  `openai/gpt-4o-mini`; pricing is computed from a dated price table. The helper
  must know which model ids exist and what they cost before proposing a variant.
- **The output contract** of the task (`Prediction` schema, `ScoringRule` list, judge
  criteria) so it can propose prompts or judge configs that actually score.
- **The data's error profile** — per-family accuracy, ambiguous rate, false-match
  sources — from `metrics.json`/`family_breakdown`. A helper needs this to choose
  which prompt tweak is most likely to help.
- **The guardrail thresholds** that matter for this domain (critical false-match
  rate, schema validity, escalation recall) — these are stated in docs but not
  machine-readable in repo config yet.

Nothing above asks the helper to read customer PII; datasets are synthetic and
deterministically generated. No secrets, credentials or real banking messiness are
present. (Assumption: datasets remain synthetic; `docs/benchmark_protocol.md`
already says synthetic data does not encode real-world messiness.)

---

## 3. ACTIONS — What could technology do?

Compare three levels:

- **Fixed workflow (automation of what a careful human already does).**
  - `make demo` / `forgebench run --limit N --run-id smoke` already handles most
    of steps 1-4; a single script could run baseline + variant + compare and emit
    the comparison artifact. Cheapest, deterministic, zero surprise.
  - Generate the `docs/results.md` entry from the run manifest + metrics JSON
    instead of by hand (the data is all there: run id, model id, timestamp,
    per-class table).
  - Generate a per-dataset "last accepted baseline" pointer so "compare to
    baseline" is one command with no run-dir guessing.
  - Fail CI on regression — already partly in place via `docs/benchmark_protocol.md`
    rules; needs wiring to GitHub Actions + the regression gate.
  - Move the task/benchmark split in `cli.py` so a single `run --config` works for
    both dataset and task configs (done in d337c2b), reducing "two code paths" friction.

- **AI assistant (suggests but a human runs and approves).**
  - Propose a prompt variant or few-shot count based on `family_breakdown` and
    false-match sources ("reference_mismatch has FP=…; try adding a negative
    example").
  - Summarise a comparison run in plain language and flag which metric regressed
    and which cases moved, instead of making the operator read the diff.
  - Draft the `docs/results.md` entry and the Opportunity Sheet (hypothetical
    tonight) for human approval.
  - Explain why a schema-invalid prediction broke, mapping `error_breakdown` kinds
    to concrete prompt fixes.
  - Suggest a next dataset or a task config for a user-described workflow, using
    the `forgebench` task YAML pattern.

- **AI agent (acts across steps; needs guardrails).**
  - Automatically iterate prompt variants until success criteria clear, running
    `run` + `compare` each cycle and stopping when the gate passes OR cost/credit
    budget is hit.
  - Automatically generate and run a task for a new domain problem, propose the
    YAML, generate cases, validate, run, compare, and report.
  - Pull provider catalog entries, price basis and model ids, and propose the
    cheapest model that clears the risk metrics.
  - Auto-create a regression gate per dataset and block a PR when it fails.
  - Only useful if it can call `forgebench` commands (CLI, not just chat), has a
    credit/budget limit it must respect (30 credits/run, 1 credit/case, no hard
    caps beyond that today), and records everything it did in `manifest.json`
    and `docs/results.md`.

**Recommendation.** Start with the fixed-workflow automation (the smallest reliable
step). It removes the tedious and error-prone parts (docs entries, baseline
pointers, smoke runs) without adding non-determinism. Add the AI assistant only for
summarisation/explanation after automation is stable. Defer the agent until the
regression gate and credit budget are machine-enforced.

---

## 4. DECISIONS — What must a person still verify or approve?

Regardless of helper level:

- **Dataset choice.** Which of the 12 domain datasets is the right proxy for the
  real problem. (`docs/benchmark_protocol.md`: synthetic data "does not encode real
  banking messiness"; saturating these is not production readiness.)
- **Baseline/run budget.** Credits: 30 flat per benchmark run or 1 per task case.
  Today no hard per-user budget exists beyond the ledger; a human must approve
  spend on a real provider.
- **Model and provider choice.** The helper can propose, but a human confirms
  vendor, license and result interpretation (models.dev catalog + provider TOCs).
- **Prompt content.** A human owns the system prompt and judge criterion text that
  reaches users; the model cannot self-author and self-approve user-facing prompts.
- **Regression gate acceptance.** The protocol says certain degradations beyond
  noise mean "this is a regression, not an improvement". A human must apply it to
  borderline results (especially tiny test sets — finance_v1 test is 60 cases).
- **Publish decision.** A human decides what lands in `docs/results.md` (published
  numbers) and attaches which run artifacts to an audit file.
- **Guardrail severity.** For custom tasks (e.g. `rag_knowledge`, `guardrails_tester`)
  a human must decide which boolean/lexicographic rule failure blocks shipping vs.
  is advisory.
- **Guardrail for the agent itself.** If an AI agent runs variants autonomously, an
  approval step must exist before any PR is created or change is committed.
  (Assumption: no agent exists yet in this repository; the tools are CLI + dashboard
  only.)

---

## 5. VALUE — What might improve, and how could we measure it?

Potential improvements and the exact ForgeBench numbers to track against baseline
(the changed cases are in `docs/results.md` / the comparison report):

| Improvement | How to measure (ForgeBench metric) |
|-------------|-------------------------------------|
| Fewer wrong "matched" approvals | `critical_false_match_rate` (primary) |
| Safer escalation | `escalation_recall` |
| Fewer integration breakages | `schema_validity`, `provider_error_rate` |
| Better class coverage | `macro_f1` and per-class F1 for the smallest classes |
| Lower real cost per case | `estimated_cost` / 1,000 cases |
| Faster time to evidence | wall-clock: run start to comparison report complete (not yet a tracked metric — **assumption**, would need measuring) |
| Fewer doc entry errors | presence/validity of `docs/results.md` entries (manual today) |
| Less wasted compute on regressions | count of runs that fail the regression gate (not tracked today) |

**Measurement hygiene.** Follow `docs/benchmark_protocol.md`: report on `test`
only, keep split hashes identical, temperature 0 where supported, disclose
concurrency, label cost/latency with date and price basis, treat 1-3 point
deltas on small sets (e.g. finance_v1 test = 60 cases) as noise unless
per-class evidence says otherwise.

**Hypothesis to test (labelled, not assumed as fact):** automating steps 8 and the
smoke runs could shorten the evidence loop; the measurable check is "hours from PR
open to published comparison entry". This is not currently tracked (assumption).

---

## 6. CHALLENGE — What assumptions need checking? What could go wrong? Could a simpler solution work?

**Assumptions to check**
- A. *Dataset coverage ≈ production coverage.* Synthetic, rule-labeled data does not
  encode real-world messiness (partial payments with remittance advice,
  multi-currency rounding, multi-jurisdiction rules). If the real problem differs, the
  benchmark is misleading. Check by sampling real records and mapping their failure
  modes against the six families.
- B. *The six exception categories are the right taxonomy.* They come from the
  original finance seed; domains like `healthcare_v1` or `legal_v1` might need new
  families (e.g., coding/billing-code mismatch). Check each new dataset against
  domain-expert labels before promoting a run to "published."
- C. *The mock provider's defect distribution matches a real model's error shape.*
  The mock is a useful offline pipeline test, not a predictor of real-model
  behavior. Do not compare mock runs to real runs as if equivalent.
- D. *Operator time savings from automation are real.* No measurement exists today;
  the proxy "run wall clock" is not a proxy for human effort.

**What could go wrong**
- *Rapid spend.* Real-provider runs consume credits; an agent loop without a hard
  budget and a run count cap could drain a balance quickly. Today the ledger is
  flat and there is no per-task budget ceiling.
- *Ground-truth leaks.* A helper that optimises a prompt to the test set is
  textbook overfitting. Split discipline (train/dev only for iteration) must be
  enforced by the tool, not trust.
- *Non-determinism.* Real providers drift; the harness pins temperature 0 but does
  not pin provider infra. Reproducibility claims need re-checking over time.
- *Doc rot.* `docs/results.md` is hand-edited. An auto-generated file can go out
  of sync with excluded/aborted runs if a human re-runs.
- *Scope creep into the agent.* The framing "we are an agency now" turns a
  useful, publishable rules-vs-models benchmark into an autonomous coding pipeline;
  the gain only shows where per-case reviews (like the `ambient-*` task list) pay
  for themselves relative to sequential effort.

**Could a simpler solution work?** Yes, and it usually does:
- If your workflow has a deterministic rule that already reaches the critical
  false-match rate threshold, do not build an agent — codify the rule and gate it.
- If only one provider is in use and one model, the comparison runner is overkill;
  a single `run` plus `schema_validity` and `critical_false_match_rate` is enough.
- If the volume is low (tens of cases), a human with a spreadsheet and the
  dataset's rule precedence (`duplicate > amount > reference > date`) can be
  cheaper than any model cost.
- ForgeBench's first value is not "a better model" but "a known, dated,
  checksummed answer to 'did this change anything?'" — a rules-only consumer that
  uses manifests, SHA-256 splits, and the report template is 80% of the benefit
  for a fraction of the cost.

**Recommendation:** use a fixed-workflow automation (smoke run, baseline pointer,
auto-generated comparison and `results.md` entry), keep decision-making human,
do not ship an autonomous agent loop until the regression gate and credit budget
are enforced by the tool.

---

## 7. Three questions to ask real users

1. When you last changed a prompt or model, how did you decide whether the new
   version was actually better than the old one, and what evidence did you show
   to your team or to leadership?
2. What is the real cost — in money, time, or audit findings — of a wrong
   "matched" approval in your current workflow, and how often does it happen today?
3. If a tool could run the old and new model side by side and hand you a
   pass/fail on the financially dangerous errors, would you actually merge on that
   result, or would you still re-test manually before shipping?

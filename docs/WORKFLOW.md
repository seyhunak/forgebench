# Workflow Improvement Analysis — Benchmark Experiment Run

This document fills the workflow-analysis template for one real ForgeBench task so it can be
used as-is: no placeholders, no invented data, assumptions labelled explicitly.
No real data, savings, permissions or system capabilities have been assumed; everything
marked "Assumption" must be verified with users or measured before acting.

---

## Mapped current workflow

**Problem**
Teams shipping AI in finance, healthcare, legal, insurance, payments, procurement or
support cannot tell whether a change to a prompt, few-shot set, temperature, model or
provider actually improved domain-task performance. Decisions are ad-hoc, vendor-specific
and non-reproducible, and the dangerous failure mode — wrongly approving a discrepancy
(a false "matched") — is not tracked as a first-class signal anywhere. Cost per case,
validity and latency are argued about rather than measured.

**Task**
Run one reproducible, evidence-based benchmark experiment that compares a baseline
provider/model against a customized variant on a pinned domain test set, then report
whether the change improved risk-aware metrics without degrading output reliability,
and decide ship / iterate / stop.

**Trigger**
A developer or data scientist modifies a prompt, `configs/<name>.yaml`, few-shot count,
model id or provider and needs objective evidence before merging a pull request or
cutting a release — or before approving a credit-billed run against real data.

**Inputs**
- Experiment config YAML (`configs/<name>.yaml`) with experiment / provider /
  inference / prompt / evaluation sections; `experiment.name` must follow
  `^[a-z0-9][a-z0-9._-]*$`.
- A versioned dataset split `datasets/<domain>_v1/<train|dev|test>.jsonl` whose
  SHA-256 is recorded in `dataset.json`; e.g. `datasets/payments_v1/test.jsonl`.
- A BYOK credential in a git-ignored `.env` (chmod 600) for the chosen provider, or a
  local Ollama daemon for the zero-cost path.
- For task-based runs: `tasks/<name>/task.yaml` + `train/dev/test.jsonl` (the RAG and
  guardrails domains use this path, run via `forgebench task-run` or `forgebench run
  --config` since run command dispatches on `experiment.task`).
- An existing baseline run directory `runs/<baseline>` to compare against.
- Optional: a pinned prompt name@version from `prompts/<name>/vN.md` + `labels.json`.

**Steps**
1. Validate the dataset (`forgebench validate-dataset <name>`); inspect
   `datasets/<name>/<split>.jsonl` (3–10 lines).
2. Create or edit the experiment config (dashboard view 04 or by hand).
3. Run the baseline on the test split:
   `forgebench run --config configs/baseline.yaml --run-id baseline`.
4. Run the candidate variant with the same split and provider.
5. Open artifacts in `runs/<run-id>/`: `predictions.jsonl`, `metrics.json`,
   `manifest.json`, `trace.jsonl`, `report.md`.
6. Compare runs:
   `forgebench compare runs/baseline runs/<candidate>`.
7. Review per-case regressions and improvements in the comparison output.
8. Record the run in `docs/results.md` for published runs (run id, model id,
   timestamp, per-class table, cost and latency with their price basis).
9. Apply the regression gate (`docs/benchmark_protocol.md` §3.3) and decide ship /
   iterate / stop; gate the PR on it.

**Tools**
- CLI: `validate-dataset`, `run`, `compare`, `report`, `task-run`, `models`,
  `history`, `list-datasets`, `set-key`.
- Dashboard (FastAPI, `forgebench dashboard`): views 01-07 — setup, API key,
  datasets, config, run, results, tasks.
- Schemas / validator: `forgebench.config.load_config`, `forgebench.registry`,
  `forgebench.tasks`; pydantic `Extra="forbid"` for strict schemas.
- Mock provider (rule engine with seeded defect rate) for offline, zero-cost
  pipeline validation.
- Deterministic dataset generators: `scripts/generate_dataset.py`,
  `scripts/generate_multi_dataset.py`, `scripts/generate_more_datasets.py`,
  `scripts/generate_guardrails_task.py`, `scripts/generate_rag_task.py`.
- Versioned prompt registry (`prompts/<name>/vN.md` + `labels.json`).
- Optional: `services/stripe_webhook` credit loop (metered runs).
- Automation: `.github/workflows/tests.yml`, `Makefile` (`make demo`).

**Output**
- `runs/<run-id>/`: `predictions.jsonl`, `metrics.json`, `manifest.json`,
  `trace.jsonl`, `report.md`.
- Comparison report with metric deltas and changed cases.
- Entry in `docs/results.md` for published runs.
- SHA-256 split hashes and manifest (`dataset.json` name, version, split,
  families, generator seed) so any run can be traced to exact inputs.

**Checks**
- Split discipline: report on `test` only; use `train`/`dev` for iteration; never tune
  on `test`.
- Equivalent: same `dataset.name`, `dataset.version`, split and split SHA-256 across
  compared runs.
- Determinism: temperature 0 where supported; sequential execution for reported runs;
  same seed → byte-identical predictions.
- Regression gate: if any of these worsens beyond noise while headline accuracy
  improves, it is a regression: critical false-match rate, schema validity.
- Invalid outputs excluded from classification metrics and counted separately
  (`schema_validity`, `provider_error_rate`, `error_breakdown`).
- No secrets in artifacts (keys in git-ignored `.env`, chmod 600, never committed).

---

## Questions and answers from the critical adviser

### 1. STEPS — Which existing steps might be repetitive, slow or difficult?

Repetitive: re-running the near-identical baseline then candidate commands with
different `--run-id` labels; switching between YAML, shell and `docs/results.md`.
These are the same class of manual copy-and-edit each cycle.

Slow: each real run is sequential by design for reproducibility and rate-limit
safety. A full split is 42–70 cases; a variant that fails the regression gate
late has already spent credits and wall-clock. The mock offline run must also be
re-run to confirm nothing structural broke.

Difficult: hand-writing the `docs/results.md` entry (run id, model id, timestamp,
per-class tables, cost basis) is error-prone and has no verifier. Reviewing whether
the changed-case list means regressions requires opening JSON manually. Choosing
between dataset configs and task configs is two CLI paths with different credit
accounting (30 credits flat per benchmark run vs. 1 credit per task case).

Assumption: these friction points are inferred from the CLI flow and docs, not
from measured operator timing. Concurrency is deliberately unsupported today
(`docs/benchmark_protocol.md`: sequential execution unless disclosed).

### 2. KNOWLEDGE — What information would technology need to help?

- The experiment's intent: prompt variant vs. model swap vs. guardrail hardening. Today
  this lives only in the free-text `experiment.name`.
- Which run is the pinned baseline for this dataset. **Assumption:** it is carried
  by the operator or implied by `docs/results.md` prose, not stored as data.
- Provider model catalog and current prices, keyed by run date, so a variant can
  be proposed cheaply.
- Per-family error profile from `metrics.json` (which classes regress) to guide prompt
  edits. `forgebench history` exists for trends but no "last accepted run id" record.
- Task output contract and judge criteria (`task.yaml`, `ScoringRule`) so a draft
  prompt produces an answer a scorer can grade.
- Guardrail thresholds that mark "pass" for this domain (critical false-match rate,
  schema validity, escalation recall). Present in docs but not machine-readable in
  repo config today.
- Source data format and the six required input keys; the eight (or seeded)
  exception families. Datasets are synthetic with deterministic ground truth.

### 3. ACTIONS — What could technology do?

Compare three levels:

Fixed workflow (automate the deterministic steps)
- Run baseline + variant + compare as one sequence with pinned `--run-id` labels and
  output the comparison artifact (`make demo` already hints at this).
- Generate the `docs/results.md` entry from `manifest.json` + `metrics.json` instead
  of by hand; the values exist, only the formatting is manual.
- Track a per-dataset "last accepted baseline" pointer in the run folder so
  `forgebench compare` needs no manual run-dir lookup.
- Fail CI on regression gate above; run the mock provider on every PR.
- Unify task and benchmark configs behind a single `forgebench run --config` (done
  in commit d337c2b).

AI assistant (draft or suggest; human decides)
- Propose a prompt or few-shot change from `family_breakdown` and false-match
  sources (e.g. reference_mismatch FP).
- Summarise a comparison run in plain language and name which metric, and which
  cases, moved.
- Draft the `docs/results.md` entry and a candidate Opportunity Sheet, pending
  approval.
- Explain a schema-invalid prediction from `error_breakdown` to a concrete prompt
  fix.

AI agent (plan, use tools, loop)
- Iterate prompt variants until success criteria clear, running run + compare each
  cycle, stopping when the gate passes or the credit budget is reached.
- Generate a task YAML and cases for a new domain, validate, run, compare, report.
- Propose the cheapest model that clears the risk metrics from the models.dev catalog.
- Only appropriate if it respects a credit/budget limit (30 credits/run or 1
  credit/case today there is no hard cap), records actions in the manifest, and
  requires approval before any PR or commit. (Assumption: no such agent exists in
  the repo today; only CLI + dashboard exist.)

Recommendation: start with fixed-workflow automation; it removes error-prone steps
without adding non-determinism. Add the assistant only for summarisation after that
works. Defer the agent until regression gate and credit budget are machine-enforced.

### 4. DECISIONS — What must a person still verify or approve?

- Which dataset genuinely represents their domain problem. Synthetic, rule-labeled
  data does not encode real-world messiness; saturating it is not production
  readiness.
- Credit spend ceiling per variant and per release; no hard budget cap exists today,
  so a human must approve real-provider spend.
- Provider and model choice (vendor, license, model id; verified against
  models.dev and the provider TOC).
- System prompt and judge criterion text reaching users; the model must not author
  and self-approve user-facing copy.
- Application of the regression gate to borderline results on small splits —
  finance_v1 test has 60 cases; 1-3 point deltas are noise unless per-class
  evidence supports them.
- Publish verdict: what numbers are published in `docs/results.md`, which artifacts
  are attached to an audit file.
- For custom tasks (e.g. `rag_knowledge`, `guardrails_tester`), which failures
  block shipping vs. are advisory.
- Agent self-approval: if an agent ever runs variants, an approval step must exist
  before a PR is opened.

### 5. VALUE — What might improve, and how could we measure it?

Possible improvements, each with a metric or artifact already tracked (pass thresholds
deferred — these are assumptions until measured):

- Fewer wrong "matched" approvals: `critical_false_match_rate` (primary).
- Faster, safer escalation: `escalation_recall`.
- Fewer integration breakages on consumer code: `schema_validity`,
  `provider_error_rate`, `error_breakdown`.
- Better coverage on rare classes: `macro_f1` plus per-class stats from
  `per_class`/`family_breakdown`.
- Lower real cost per case: `estimated_cost` / 1,000 cases.
- Shorter wall clock to evidence: run start to comparison report written.
  (Assumption — not currently a tracked metric.)
- fewer `docs/results.md` entry errors: presence/validity of the entry after a run
  (this does not exist today; manual).
- Less wasted compute on regressions: number of runs flagged by the regression
  protocol (not currently recorded).

Measure with: baseline time per task (wall clock, manually logged first), error rate
observed by users, number of revision rounds, completion rate, satisfaction. Define
success criteria before piloting. Apply the noise rules of
`docs/benchmark_protocol.md` to every reported number.

### 6. CHALLENGE — Assumptions to check; what could go wrong; simpler alternative

Assumptions to check:
- A. Dataset coverage approximates production coverage. Synthetic labeled data
  does not encode real messiness (partial payments with remittance advice,
  multi-currency rounding, jurisdiction rules). Check by mapping real-world failure
  modes against the six scenario families.
- B. The six exception families fit every domain. They carry over from the finance
  seed; healthcare or legal may need new families. Check each dataset's families
  against domain-expert labels before publishing a run.
- C. The mock provider's defect distribution resembles a real model's error shape.
  It is an offline pipeline test, not a predictor. Do not compare mock to real as
  equivalent.
- D. Any automation's time savings are real. No measurement exists; "wall clock"
  is not "human effort."

What could go wrong:
- Rapid credit spend if an agent loop runs without budget and run-count caps; the
  ledger has no hard per-user ceiling today.
- Ground-truth leakage via over-tuning the test set — split discipline must be
  enforced by the tooling, not by trust (train/dev for iteration, test only for
  reporting).
- Provider drift over time even at temperature 0; re-verify reproducibility
  periodically.
- Auto-generated documentation going out of sync with aborted or excluded runs.
- Scope creep: turning a benchmark-with-regression-gates tool into an autonomous
  pipeline only pays for itself where the per-case reviews (e.g. RAG, guardrails)
  are genuinely more numerous than the human effort they save.

Simpler solution that may deliver most of the value before any AI is involved:
a single run on `configs/<domain>_baseline.yaml` with `schema_validity` and
`critical_false_match_rate` plus the published report; a rules-only gate coded from
`docs/benchmark_protocol.md`'s regression list; or, for low volume, a spreadsheet
plus the dataset rule-precedence rules. Test the simpler option first and measure.

Recommended simplest suitable approach: fixed-workflow automation (baseline
pointer + auto-generated comparison and `results.md` entry), human reviewers
retaining every decision in section 4, and no autonomous agent loop until regression
gate and credit budget are machine-enforced.

---

## Three questions to ask real users

1. When you last changed a prompt or model, how did you decide the new version was
   actually better than the old one, and what evidence did you show your team or
   leadership?
2. What is the real cost — in money, time or audit findings — of one wrong
   "matched" approval in your current workflow, and how often does it happen today?
3. If a tool ran the old and new models side by side and gave you pass/fail on the
   financially dangerous errors, would you merge on that result, or would you still
   re-test manually before shipping?

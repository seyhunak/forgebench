# AI Agents Championship — Opportunity Framework for ForgeBench

A concrete framework for turning a real-world problem into a testable ForgeBench benchmark opportunity. Every step names an actual ForgeBench artifact you can reach for right now — no templates, no placeholders.

> **Key takeaway:** Validate the problem and the workflow before deciding to build an AI agent. ForgeBench exists to measure domain adaptation on a pinned test set — it does not tell you whether the problem is worth solving. That is this document's job.

---

## 1. The Five-Step Framework

### 01 — SPOT: Find the Problem

Identify a recurring, costly problem that fits ForgeBench's domain: structured exception classification over tabular or document pairs where ground truth is deterministic.

**ForgeBench-suitable problems have these traits:**
- Two records (bank vs. ledger, claim vs. EOB, invoice vs. contract, ticket vs. system record) that should agree.
- A small closed set of exception categories: matched, amount_mismatch, date_mismatch, reference_mismatch, duplicate, ambiguous.
- Errors have a real cost: wrongly approving a discrepancy ("matched" when it is not) is the financially dangerous error; missing a review is an operational cost.
- Today the work is done by people with rules or scripts that already exist but are brittle.

**ForgeBench is NOT the right fit for:** free-form chat, open-ended generation, creative writing, multimodal tasks, or anything without a verifiable correct answer.

**Ask:**
- Who experiences this problem? (e.g. a payments ops clerk, a claims adjuster, an AP analyst)
- How often? (daily volume, per case)
- What does a wrong answer cost? (overpayment, under-detection, audit exposure, escalation load)

---

### 02 — MAP: Understand the Current Workflow

Document the work exactly as it happens today, mapping each element to a ForgeBench counterpart:

| Workflow element | ForgeBench equivalent |
|------------------|----------------------|
| People | human reviewer who escalates or approves |
| Tools | the current rule engine, spreadsheet, or legacy app |
| Data | bank_amount, ledger_amount, bank_reference, ledger_reference, bank_date, ledger_date (the six required input keys) |
| Decisions | the exception category and requires_review flag |
| Handoffs | escalation to a human when requires_review is true |

**Concrete check:** open an existing dataset and see if your workflow's records fit its input schema:

```bash
forgebench validate-dataset finance_v1
head -n 5 datasets/finance_v1/test.jsonl
```

If your records need different fields, ForgeBench tasks (`tasks/<name>/task.yaml`) let you define arbitrary input fields and output schema without code — but start by checking whether one of the 12 shipped datasets already matches:

```
datasets/ecommerce_v1, finance_v1, healthcare_v1, insurance_v1, legal_v1,
payments_v1, procurement_v1, saas_billing_v1, subscriptions_v1,
support_v1, telecom_v1, travel_v1
```

**Ask:**
- Where are the bottlenecks? (volume, latency of human review)
- Where are the repetitive tasks? (category labeling, reconciliation)
- Where are the failure points? (wrong category, missed review, malformed output)

---

### 03 — QUALIFY: Test the Opportunity

Run the existing pipeline against your data before writing anything. ForgeBench gives you a deterministic offline path — no API key, no GPU:

```bash
# Validate one of the shipped datasets
forgebench validate-dataset support_v1

# Run the offline mock provider end to end (zero cost)
forgebench run --config configs/support_baseline.yaml --run-id support-mock-smoke --limit 25
```

The mock provider is a rule engine seeded with a small defect rate; it proves the harness works and shows you what the artifacts look like before you spend tokens on a real model.

**Qualify on these axes, with ForgeBench metrics:**

| Axis | ForgeBench metric or artifact | Pass threshold |
|------|------------------------------|----------------|
| Value | critical false-match rate (false "matched" on truly non-matching cases) | lower than today's human error rate |
| Feasibility | schema_validity (fraction of outputs that parse and match the contract) | >= 0.95 |
| Reliability | per_class stats / family_breakdown | accuracy acceptable in every family, especially ambiguous |
| Human oversight | escalation_recall (of cases requiring review, how many were flagged) | near 1.0 for non-matched cases |
| Errors & risks | provider_error_rate, error_breakdown | near zero; no silent failures |
| Simpler solution | compare against a rule baseline first | if rules already hit the threshold, you do not need an agent |

**Ask:**
- Does this genuinely need an AI agent? Or would a rule, script, or conventional application work better? Run `forgebench run` against the mock provider and compare its rule-based accuracy against your current process. If the mock already clears your bar, the opportunity is "automate the rule," not "build an agent."

---

### 04 — CHOOSE: Prioritise One Opportunity

Compare candidates on measurable benefit at acceptable risk. ForgeBench gives you comparable numbers across datasets because every run records the same manifest (dataset hash, config, model id, prompt hash, timestamps, git SHA).

**Decision inputs (all real, from ForgeBench runs):**
- Accuracy on the test split (never tune on test; train/dev are for iteration)
- Critical false-match rate — the expensive error
- Schema validity — integration reliability
- Cost per 1,000 cases — from actual token usage with dated pricing
- p50/p95 latency

**Candidate shortlist (shipped datasets to run first):**

| Dataset | Domain | Good first opportunity if… |
|---------|--------|---------------------------|
| finance_v1 | bank/ledger reconciliation | transaction ops clerks misclassify exceptions |
| payments_v1 | payment exception triage | AP teams match payments to invoices |
| support_v1 | support ticket reconciliation | support agents reconcile ticket state vs. system |
| healthcare_v1 | medical claims vs. EOB | claims adjusters match claims to explanations |
| insurance_v1 | insurance reconciliation | underwriters match policies to endorsements |
| legal_v1 | contract vs. invoice clauses | legal ops match contract terms to invoices |
| saas_billing_v1 | SaaS subscription billing | billing ops reconcile subscription invoices |
| telecom_v1 | telecom billing | telecom ops reconcile usage invoices |
| travel_v1 | travel expense | finance teams reconcile travel receipts |
| ecommerce_v1 | ecommerce | ops reconcile orders vs. shipments |

Run each baseline, record the four headline numbers, and pick the one where closing the gap to your current process is clearly worth the model cost.

**Ask:**
- Which option delivers the clearest measurable benefit at an acceptable level of risk?

---

### 05 — FRAME: Define a Testable Hypothesis

Turn the selected opportunity into one experiment with success criteria and a next test. Use a ForgeBench experiment config as the hypothesis container.

**Example hypothesis (fill in your dataset and numbers):**

> "For `payments_v1`, switching from the rule-based mock provider to `openai/gpt-4o-mini` via OpenRouter will reduce the critical false-match rate from the mock's baseline to <= 0.02 while keeping schema_validity >= 0.98, at <= $4.00 per 1,000 cases."

**Write it as a config** (`configs/<your-opportunity>.yaml`):

```yaml
experiment:
  name: payments-agent-v1
  dataset: payments_v1
  dataset_version: "1.0.0"
  split: test
  seed: 42
provider:
  name: openrouter
  model: openai/gpt-4o-mini
  options:
    temperature: 0
inference:
  temperature: 0
  max_retries: 2
  timeout_seconds: 30
  max_tokens: 1024
prompt:
  system: null
  name: null
  version: null
  few_shot_count: 0
evaluation:
  metrics:
    - accuracy
    - macro_f1
    - critical_false_match_rate
    - escalation_recall
    - schema_validity
    - latency
    - estimated_cost
  judge: null
```

**Success criteria (pick two or three, numeric):**
- critical false-match rate <= [your threshold]
- schema_validity >= 0.95
- escalation_recall >= 0.98
- cost per 1,000 cases <= [your budget]

**Next test:** the smallest experiment that validates the hypothesis. Run the baseline config first, then one variant:

```bash
forgebench run --config configs/baseline.yaml --run-id payments-baseline
forgebench run --config configs/payments-agent-v1.yaml --run-id payments-agent-v1
forgebench compare runs/payments-baseline runs/payments-agent-v1
```

If the variant clears every success criterion on the test split, the opportunity is qualified to build. If not, iterate on prompt, few-shot, or provider — or stop.

**Ask:**
- What evidence would convince us that this solution works? The comparison report is that evidence.

---

## 2. The Opportunity Sheet (ForgeBench edition)

Use this canvas to document the opportunity before writing code. Every field maps to a ForgeBench artifact you can point at.

| Component | What to capture | ForgeBench location |
|-----------|----------------|---------------------|
| **User & Problem** | Who has the problem, the pain, and the cost of a wrong answer | Written here; dataset name chosen below |
| **Workflow Map** | Current process, systems, data, decisions, handoffs | Mapped to ForgeBench input keys and exception categories |
| **Human Control** | Approval points, escalation, intervention | `requires_review` flag; escalation_recall metric |
| **Choice** | Selected dataset, provider, model, prompt; why it is preferable | `configs/<name>.yaml`, provider/model from `forgebench models` |
| **Evidence** | Baseline metrics, research, supporting observations | `runs/<baseline>/metrics.json`, `report.md`, manifest |
| **Next Test** | Smallest experiment to validate the hypothesis | `forgebench run --config configs/<name>.yaml --run-id <id>` |

**Filled example:**

| Component | Entry |
|-----------|-------|
| User & Problem | AP clerk reconciles 200 payment invoices/day; wrong category causes overpayment |
| Workflow Map | Invoice PDF → AP clerk reads amount/date/reference → matches to bank ledger → category → escalate if mismatch |
| Human Control | Clerk approves matched; mismatches escalate to senior AP. ForgeBench: `requires_review=true` for every non-matched category |
| Choice | `payments_v1` dataset, OpenRouter `openai/gpt-4o-mini`, temperature 0, no few-shot |
| Evidence | Mock baseline run: accuracy 0.82, critical false-match rate 0.09, schema_validity 0.93 (see `runs/payments-mock-baseline/`) |
| Next Test | Run `configs/payments-agent-v1.yaml`, require critical false-match rate <= 0.02 and schema_validity >= 0.95 |

---

## 3. How to Run This Framework (commands)

```bash
# 0. Clone and install
git clone https://github.com/seyhunak/forgebench
cd forgebench
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 1. SPOT + MAP — pick a dataset that matches your workflow
forgebench list-datasets
forgebench validate-dataset <dataset>
head -n 5 datasets/<dataset>/test.jsonl

# 2. QUALIFY — run the offline pipeline (no key, no cost)
forgebench run --config configs/<dataset>_baseline.yaml --run-id <dataset>-mock-baseline --limit 25

# 3. CHOOSE — run a few baselines, compare headline numbers
forgebench compare runs/<a> runs/<b>

# 4. FRAME — write configs/<your-opportunity>.yaml with success criteria
#    Save a real key if you will use a real model:
forgebench set-key --provider openrouter

# 5. Execute — run your hypothesis config and compare to baseline
forgebench run --config configs/<your-opportunity>.yaml --run-id <your-opportunity>
forgebench compare runs/<dataset>-mock-baseline runs/<your-opportunity>
```

Every run writes `predictions.jsonl`, `metrics.json`, `manifest.json`, `trace.jsonl`, and `report.md` under `runs/<run-id>/`. The comparison report is your evidence.

**Rule:** document the filled Opportunity Sheet before writing any code or spending tokens on a real model. If you cannot fill the Evidence and Next Test columns with real ForgeBench numbers, you are not ready to build.

# ForgeBench — Presentation Deck Notes

> **Tagline:** *Measure domain adaptation, not just model intelligence.*
>
> ForgeBench is a reproducible, provider-agnostic benchmark harness that answers one
> question: **did customizing a model — a better prompt, few-shot examples, structured
> output, a fine-tune — actually improve performance on a domain task, or did it just
> make the pipeline more complicated?**

Use this file as the speaker-notes/source for the presentation. Each section below is a
slide group; bullet lines are meant to be lifted straight onto a slide.

---

## 1. Use cases

**Slide — "Who runs this and why"**

| # | Use case | What ForgeBench gives you |
|---|----------|---------------------------|
| 1 | **Prompt / few-shot / fine-tune A/B validation** | Same fixed test set, same scoring code path, two runs, one `compare` with metric deltas *and* the exact cases that flipped. |
| 2 | **Model & provider selection** | One config, six providers (Mistral, OpenAI, Anthropic, Google, OpenRouter, Ollama) + a deterministic offline mock — swap `--provider`/`--model`, keep everything else identical. |
| 3 | **Regression gating in CI** | `templates/regression.yml`: lint + tests + dataset reproducibility, then a pinned baseline run vs. a fresh candidate run with a tolerance (fails the PR past −0.05 accuracy by default). |
| 4 | **Regulated-domain evidence (finance, healthcare, legal, insurance, payments, procurement)** | Nine synthetic datasets with rule-generated ground truth and SHA-256 manifests — no customer data, but auditable, reproducible results. |
| 5 | **Risk-aware quality measurement** | Critical false-match rate and escalation recall tracked *separately* from accuracy — accuracy alone hides the expensive errors. |
| 6 | **Safety / red-team scanning** | `forgebench safety-scan` over prompt injection, jailbreak, PII, bias, toxicity — fully offline via the mock provider. |
| 7 | **Custom evals without writing code** | Define an evaluation task in YAML (input fields, output schema, weighted scoring rules) → `forgebench task-run`. |
| 8 | **Subjective / RAG quality scoring** | G-Eval-style LLM-as-judge for reason quality; RAGAS-style lexical RAG metrics (faithfulness, answer relevancy, contextual relevancy) with zero extra LLM calls. |
| 9 | **Independent reproduction of published claims** | Every run is self-describing: config, dataset hash, prompt digest, model id, git SHA, environment → the result can be reproduced *or refuted*. |

**One-liner for the slide:** *If you cannot point at a pinned baseline run, you do not
know whether your last change helped.*

---

## 2. Tech stack

**Slide — "Small, boring, inspectable"**

| Layer | Choice | Why |
|-------|--------|-----|
| Language | Python 3.11+ (3.11 / 3.12 tested) | The ecosystem every eval team already runs. |
| Config | YAML + `${ENV_VAR}` interpolation, validated by **Pydantic** | Reproducible experiments; secrets stay outside the repo; missing vars fail loudly. |
| CLI | **Typer** (`forgebench …`) | CLI-first: the dashboard is a client of the same runner, never a parallel implementation. |
| HTTP / API | **FastAPI** + uvicorn; **httpx** in tests | Local dashboard backend and JSON API (`/api/runs`, `/api/history`, `/api/datasets`, `/api/baselines`). |
| Frontend | Single-page static app (`src/forgebench/static/`: HTML/CSS/JS), dark-first Cobalt theme, ⌘K palette | No Node build step; served by the same FastAPI process. |
| Providers | `ModelProvider` protocol; OpenRouter adapter speaks REST via the **standard library** (no SDK); Mistral/OpenAI/Anthropic/Google/Ollama adapters optional | Bare install runs end-to-end; the runner never imports a vendor SDK. |
| Rendering / sanitization | `markdown-it-py`, `mdit-py-plugins`, **bleach** | Reports render to Markdown/HTML; the HTML export is sanitized and self-contained (no external assets). |
| Data format | JSONL + JSON + Markdown artifacts per run | Portable, diffable, git-friendly, warehouse-friendly. |
| Quality gates | **ruff** (lint + format), **pytest** | Fast, deterministic, offline test suite. |
| Integrations | `FORGEBENCH_WEBHOOK_URL` (Slack/CI/collector), `FORGEBENCH_TOKEN` (dashboard auth), `models.dev` model catalog | Fits into an existing team's plumbing instead of replacing it. |

**Architecture one-liner:** `load → validate → infer → score → record` — one orchestration
path, so every provider is scored by exactly the same code.

---

## 3. Security

**Slide — "Offline by design, secrets never leave your machine"**

- **No committed secrets.** Keys live only in a git-ignored `.env` written by
  `forgebench set-key` with owner-only permissions (`chmod 600`), verified against the
  provider API, and shown masked afterwards (`set-key --show`).
- **Keys are read at call time**, never written into configs, `manifest.json`, or run
  artifacts. Shell-exported `*_API_KEY` takes precedence over `.env`.
- **Minimal data flow.** By design ForgeBench uploads nothing anywhere except the model
  provider you explicitly configured — no telemetry, no dataset egress, no third-party
  analytics. Any new provider adapter must document its destination and data flow in the
  module docstring and PR (`SECURITY.md`).
- **No private data needed.** Datasets are synthetic and generated by rules in this repo
  (Apache-2.0) — no PII, no customer records, no GPU.
- **Optional auth when exposed.** `FORGEBENCH_TOKEN=$(openssl rand -hex 24)` makes every
  `/api/*` request require `x-forgebench-token`; the UI prompts once and stores it.
- **Sanitized exports.** HTML reports are bleach-sanitized, self-contained, and carry no
  external asset loads — safe to attach to a ticket or email.
- **Artifacts are local and git-ignored.** `runs/` may contain full model outputs; it is
  excluded by default, and `manifest.json` records configuration and versions, never
  credentials.
- **Coordinated disclosure.** `SECURITY.md` — private GitHub vulnerability report, ack
  within days, honest scope/timeline assessment.
- **Test suite spends no credits.** Tests inject a deterministic fake at the provider
  seam; one smoke test hits a real provider and skips unless a key is present.

---

## 4. Scalability

**Slide — "Honest today, explicit growth path"**

**Runs today (v0.2.0):**

| Dimension | Current behaviour |
|-----------|-------------------|
| Execution | Sequential, single-process (`runner.run_experiment`) — chosen deliberately for predictable rate limits, reproducible latency, easy debugging. |
| Dataset scale | Hundreds of cases per split (100–200 case datasets); runs finish in minutes. |
| Storage | Flat files per run under `runs/<run-id>/` — no database to provision, migrate, or back up. |
| API layer | Read-mostly local FastAPI over the filesystem (`list_runs`, `read_predictions`, `read_trace` shared as one data layer). |
| State | Everything a run needs is in its directory → runs are trivially shippable and replayable. |

**Growth path (designed for, not yet built):**

| Lever | Where it lands |
|-------|----------------|
| **Concurrency** | The architecture doc already reserves the spot: wrap `provider.predict` in a threaded/async pool; scoring, recording and reporting stay untouched. Latency percentiles then get relabelled as "measured under concurrency". |
| **Sharding** | Artifacts are JSONL keyed by case id → split a dataset across workers/containers and merge by id. |
| **Horizontal scale-out** | The runner is stateless between cases; a queue worker can own one case range each and write into a shared `runs/` (object storage or NFS). |
| **Warehouse / lake ingest** | `predictions.jsonl` + `metrics.json` + `manifest.json` stream straight into Snowflake/BigQuery/duckdb for org-wide trend analysis. |
| **Multi-user** | Stateless FastAPI + `FORGEBENCH_TOKEN` is the seam for real auth/multi-tenancy; no session state to migrate. |
| **Local / air-gapped scale** | Ollama adapter runs the whole harness on-prem with zero egress and zero API cost. |
| **Cost scaling** | `--limit N` case sampling for cheap smoke runs; full set reserved for release gates. |

**Slide line:** *Scale the calls, not the architecture — files and JSONL shard and merge
naturally; the runner's provider seam is the only place concurrency has to touch.*

---

## 5. DevOps

**Slide — "Reproducibility is a CI feature"**

- **CI (`.github/workflows/tests.yml`)** on every push/PR, Python 3.11 **and** 3.12:
  1. `ruff check` + `ruff format --check`
  2. `pytest` (offline; optional e2e only if `OPENROUTER_API_KEY` secret exists — no
     secret ⇒ skip, never fail)
  3. **Dataset reproducibility gate** — regenerate `finance_v1` from seed 42 and
     `diff -r` against the committed files. Byte-identical or the build fails.
  4. Optional end-to-end demo: run baseline + prompt variant, then `forgebench compare`.
- **Regression-on-PR template** (`templates/regression.yml`, copy-in): an
  `offline-gate` job (lint/tests/reproducibility) and a `task-regression` job that
  materializes the pinned baseline from `main`, runs a candidate, and fails the PR if
  accuracy drops beyond tolerance.
- **Everything is a file.** No database migrations, no deployed state, no infrastructure
  to break — a run directory is the whole deployment unit.
- **Manifests as provenance.** Each `manifest.json` captures dataset SHA-256, config,
  model id, package/git versions, timestamps, git SHA and environment → any result can be
  traced to exact bytes.
- **Release discipline.** Semantic Versioning + Keep a Changelog (`CHANGELOG.md`);
  Apache-2.0; `Makefile` targets for install / test / lint / data / demo / dashboard.
- **Integration-friendly.** `FORGEBENCH_WEBHOOK_URL` POSTs a compact JSON run summary
  (`run_id`, model, dataset/task, cases, accuracy) to Slack or a CI listener — delivery
  failures warn on stderr and never fail the run.

**Slide line:** *Lint, test, prove the dataset is byte-identical, then gate the model —
in that order, on every pull request.*

---

## 6. LLMOps

**Slide — "The model lifecycle, versioned like code"**

| Concern | Mechanism |
|---------|-----------|
| **Prompt versioning** | `prompts/<name>/vN.md` — immutable versions with named labels (`production`); pinned via config `prompt: {name, version}` or the dashboard. The run records `name@version`, the file's SHA-256, *and* the digest of the bytes actually sent — two runs can be **proven** to have used the same instructions. |
| **Experiment-as-code** | YAML configs under `configs/` (provider, model, temperature, retries, timeout, prompt, metrics) → identical reruns, diffable in PRs. |
| **Provider abstraction** | One `predict(case) -> ProviderResponse` contract across Mistral / OpenAI / Anthropic / Google / OpenRouter / Ollama + offline mock. BYOK; OpenRouter is the default (one key, hundreds of models). Model catalog, pricing and context windows synced from `models.dev`. |
| **Structured-output discipline** | A plausible explanation is not a correct answer: unknown categories, malformed JSON and invalid evidence fields are **rejected**. `schema_validity` is a first-class metric. |
| **Metrics that match risk** | accuracy, macro-F1, **critical false-match rate**, **escalation recall**, schema validity, latency p50/p95, estimated cost — denominators specified in `docs/benchmark_protocol.md`. |
| **LLM-as-judge** | G-Eval-style criteria + evaluation steps per rule; `evaluation.judge` in configs. The judge is **advisory** — a broken judge is counted in `metrics["judge"]["n_failures"]` and never fails a run. |
| **Observability** | `trace.jsonl` per run: wall-clock spans per case (provider call with token counts, parse & score, judge) rendered as a waterfall — "which step cost the time" is an answer, not a guess. |
| **Regression management** | Pin one run per dataset as baseline (`runs/baselines.json`), then **Vs baseline** shows metric deltas *plus* the cases that improved/regressed. `forgebench history` gives the month-later view: is this task getting better over time? |
| **Safety** | `safety-scan` red-team task (injection, jailbreak, PII, bias, toxicity) wired into the same runner and artifacts. |
| **Artifacts** | `predictions.jsonl`, `metrics.json`, `manifest.json`, `trace.jsonl`, `report.md` — plus JSON/CSV/sanitized-HTML export. |
| **Failure handling** | *Errors are data*: provider failures and invalid outputs become records with error kinds — scored and reported, never silently dropped. |

**Slide line:** *Ground truth is never a model, the judge never blocks a run, and every
number ships with the prompt hash that produced it.*

---

## 7. FinOps

**Slide — "Cost is a metric, not an afterthought"**

- **Estimated cost per 1,000 cases** is a headline metric alongside accuracy — provider
  pricing × actual tokens used, reported per run and in every comparison.
- **Dated price table** (`metrics/pricing.py`): input / output / cache-read $/M tokens
  per model, each entry carrying an `as_of` date — every cost claim is labelled with its
  measurement date; unknown models report `0` **with a warning**, never a silent
  fabricated number.
- **Live pricing sync** from `models.dev` (pricing, context windows, capabilities) into
  `forgebench models` and the dashboard's model picker — you see the price *before* you
  run.
- **Token-level attribution.** `trace.jsonl` records token counts per provider call, so
  cost can be broken down per case, per step, per run — not just per invoice.
- **Cheapest-path defaults:**
  - **Zero-cost offline mode:** mock provider + rule engine for tests and pipeline
    validation — no key, no GPU, no spend.
  - **Local inference:** Ollama runs the full benchmark on your own hardware ($0 marginal).
  - **Free-tier / cheap models:** OpenRouter default catalog includes sub-$0.10/M options.
  - **`--limit N`** for sampling runs during iteration; full splits reserved for release gates.
- **Budget decision support.** `forgebench compare` and N-way dashboard comparison put
  accuracy, latency and estimated cost side by side — the classic decision "is the 10×
  model worth it here?" becomes a table, not a debate.
- **No training spend.** Fine-tuning is explicitly out of scope: inference benchmarking
  never depends on training infrastructure.

**Slide line:** *Pick the cheapest model that clears the risk metrics — and prove it with
a dated cost figure attached to the run.*

---

## Suggested slide order

1. Problem — "did it actually get better, or just more complicated?"
2. Use cases (pick 3–4 for the audience: ML platform vs. risk/compliance vs. product)
3. Tech stack + architecture (`load → validate → infer → score → record`)
4. Live demo: `set-key` → `run` → `compare` (dashboard screenshots in `docs/screenshots/`)
5. LLMOps (prompt registry, manifests, trace, regression view)
6. Security (offline-by-design, BYOK, token auth)
7. DevOps (CI gates + regression-on-PR)
8. FinOps (cost per 1,000 cases, price table, zero-cost path)
9. Scalability (today + growth path)
10. Roadmap / contribution invites (new adapters, domains, metrics, reproduced runs)

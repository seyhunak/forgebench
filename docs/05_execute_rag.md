# 05 · Execute — RAG Testing with Guardrails

Run RAG (retrieval-augmented generation) evaluations through ForgeBench using
the same provider/model defaults as the benchmark, with guardrails and
response-quality hardening built in.

## What this phase covers

| Step | Artifact | Purpose |
|------|----------|---------|
| Knowledge dataset | `tasks/rag_knowledge/` | Synthetic knowledge-base QA cases with ground-truth context (`context`) and actual retrieval (`retrieval_context`) |
| Experiment config | `configs/rag_knowledge_baseline.yaml` | Provider/model selection (openrouter + openai/gpt-4o-mini, same as benchmark) |
| Guardrails | `grounded` scoring rule + `faithfulness` | Block ungrounded/hallucinated answers before they reach a user |
| Response-quality hardening | `tests/test_rag_task.py` | Deterministic tests that regressions in faithfulness/relevancy/groundedness are caught |

## 1. Knowledge dataset — `tasks/rag_knowledge/`

A custom task (not a reconciliation dataset) because RAG cases carry
`context` (RAG goldens) and `retrieval_context` (what the pipeline actually
retrieved) — fields that exist on `TaskCase` but not on `BenchmarkCase`.

```
tasks/rag_knowledge/
├── task.yaml            # input/output schema + scoring rules
├── train.jsonl          # 20 cases
├── dev.jsonl            # 10 cases
└── test.jsonl           # 15 cases
```

Each case:
- `input.question` — the user question
- `input.retrieval_context` — chunks the RAG pipeline retrieved (shown to the model)
- `expected.answer` — the ground-truth answer
- `expected.grounded` — guardrail: is the answer supported by context?
- `expected.citations` — chunk indices the answer should cite
- `context` — ideal ground-truth context (TaskCase field)
- `retrieval_context` — actual retrieval (TaskCase field, used by RAG metrics)

Split: 20 train / 10 dev / 15 test (45 cases total). Mix of grounded,
ungrounded, contradictory, and refusal cases.

Validate:
```bash
forgebench task-validate rag_knowledge
```

## 2. Config — same provider/model as the benchmark

`configs/rag_knowledge_baseline.yaml` uses `openrouter` + `openai/gpt-4o-mini`,
the same defaults as `configs/baseline.yaml`. Run:

```bash
forgebench task-run --name rag_knowledge --provider openrouter --model openai/gpt-4o-mini --split test
```

The config documents the intended settings:
```yaml
provider:
  name: openrouter
  model: openai/gpt-4o-mini
inference:
  temperature: 0
  max_retries: 2
  timeout_seconds: 30
  max_tokens: 1024
evaluation:
  metrics:
    - accuracy
    - schema_validity
    - latency
    - estimated_cost
```

Task-run results write to `runs/<task>-<provider>-<model>-<timestamp>/` with
`predictions.jsonl`, `metrics.json`, `manifest.json`, `report.md`, and
`trace.jsonl`.

## 3. Guardrails

Two scoring rules act as guardrails on every RAG answer:

| Rule | Field | Method | What it catches |
|------|-------|--------|-----------------|
| `grounded` | `grounded` | `boolean` | Answer claims support that the expected ground truth says is unsupported |
| `faithfulness` | `answer` | `faithfulness` (lexical) | Answer sentences not grounded in retrieved context (< 30% grounded fails) |

Plus `answer_relevancy` and `contextual_relevancy` to detect answers that don't
address the question or retrieval that isn't relevant.

A run is "hardened" when:
- `grounded` pass rate is high (ungrounded answers blocked)
- `faithfulness` pass rate is high (no hallucinations)
- `schema_validity` is high (answers match the output contract)

## 4. Harden response quality with tests

`tests/test_rag_task.py` runs deterministically offline (no API key). It
asserts:

- The task validates and all 45 cases are unique across splits
- Every case carries `retrieval_context` and `context`
- Faithfulness > 0.5 for grounded answers, == 0.0 for ungrounded
- Answer relevancy > 0 when the answer uses question vocabulary
- Contextual relevancy == 0.0 for irrelevant chunks
- The grounded boolean rule matches expected/predicted
- The config uses openrouter + openai/gpt-4o-mini (same as benchmark)
- The output schema declares `answer`, `grounded`, `citations`

Run the hardening tests:

```bash
PYTHONPATH=src python3 -m pytest tests/test_rag_task.py tests/test_rag_metrics.py -q
```

## 5. Full RAG execution example

```bash
# 1. Validate the task
forgebench task-validate rag_knowledge

# 2. Run on the test split with the benchmark provider/model
forgebench task-run --name rag_knowledge \
    --provider openrouter \
    --model openai/gpt-4o-mini \
    --split test \
    --run-id rag-baseline-v1

# 3. Inspect the report
cat runs/rag-baseline-v1*/report.md

# 4. Run the hardening tests (offline, no key needed)
PYTHONPATH=src python3 -m pytest tests/test_rag_task.py -q
```

## Offline validation without an API key

The mock provider supports task runs end to end:
```bash
forgebench task-run --name rag_knowledge --provider mock --split test --run-id rag-mock-smoke
```
This exercises the full pipeline (prompt building, scoring, artifacts) without
calling a real model — useful for CI and for proving guardrails fire before
spending tokens on a real provider.

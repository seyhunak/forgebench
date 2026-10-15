# Forge integration: the customization path

## Status

**Not implemented. No live integration exists today.** This document defines
the contract ForgeBench *will* use, so a customization-trained model can be
evaluated without touching the scoring engine. Do not treat anything here as
documentation of an actual Forge API — confirm the supported training and
artifact-export workflow with Mistral before writing an adapter.

## Why a contract first

ForgeBench's value is a stable evaluation surface. If the harness depended on
one training platform's API, it could not compare that platform's models
against baselines, other fine-tunes, or pure-prompting approaches. So the
integration point is a *data contract*, not an SDK call.

## The three concepts, again

| Concept | Lives in | Represented by |
| --- | --- | --- |
| Model provider (inference) | `forgebench.providers` | `ModelProvider.predict(case) -> ProviderResponse` |
| Training experiment (adaptation) | outside ForgeBench | `registry.ModelArtifact` |
| Evaluation run (measurement) | `forgebench.runner` | run directory with manifest + metrics |

```python
@dataclass(frozen=True)
class ModelArtifact:
    name: str
    version: str
    dataset_version: str
    training_config_hash: str
    provider: str
```

The artifact records *how* a model was trained well enough to reproduce the
training run; the evaluation run records *how it performed* on a fixed test
set. Neither can borrow credibility from the other.

## The first experiment this enables

> Does domain customization reduce financial exception-classification errors
> without increasing critical false matches or invalid outputs?

Concretely, three runs on the same `finance_v1` test split:

1. `baseline` — stock model, plain prompt.
2. `prompt-v1` — improved system prompt (Day-5 style).
3. `customized-v1` — customization-trained model, identical prompt to (1).

Pass criterion: (3) improves macro-F1 over (1) while **not** worsening
critical false-match rate or schema validity, per the regression protocol in
[benchmark_protocol.md](benchmark_protocol.md).

## Adapter checklist, once the interface is confirmed

- [ ] The trained model is reachable through a `ModelProvider` (its own
      adapter, or a Mistral-compatible endpoint using the existing adapter).
- [ ] `ModelArtifact` fields are filled from the training run: dataset
      version, training config hash, provider.
- [ ] The artifact id is recorded in the run `manifest.json` next to the
      model id.
- [ ] Training data is disclosed and provably disjoint from the `test` split.
- [ ] Comparison runs use identical inference settings and prompts.

## What ForgeBench will not do

- Train or fine-tune models (no training infrastructure here).
- Claim Forge-parity features: lineage graphs, KPI-based enterprise
  evaluation, or lifecycle management belong to the platform, not this
  harness.
- Compare results across undisclosed differences in models, data, or
  hardware.

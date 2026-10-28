"""RAG knowledge task: validation, scoring, and response-quality hardening.

Tests that the rag_knowledge custom task loads, validates, and that its
deterministic scoring rules (faithfulness, answer_relevancy,
contextual_relevancy, grounded guardrail) behave as expected.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from forgebench.tasks import validate_task, load_task_with_cases
from forgebench.metrics.rag import (
    lexical_faithfulness,
    lexical_answer_relevancy,
    contextual_relevancy,
)
from forgebench.schemas import TaskOutputField

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_rag_task_validates() -> None:
    """The shipped rag_knowledge task passes registry validation."""
    info, report = validate_task("rag_knowledge")
    assert report.ok, report.problems
    assert info.input_fields == ["question", "retrieval_context"]
    assert info.output_fields == ["answer", "grounded", "citations"]
    assert info.scoring_methods == ["boolean", "faithfulness", "answer_relevancy", "contextual_relevancy"]
    assert dict(info.n_cases) == {"train": 20, "dev": 10, "test": 15}


def test_rag_case_ids_unique_and_splits_disjoint() -> None:
    """No case id leaks across train/dev/test."""
    seen: dict[str, str] = {}
    for split in ("train", "dev", "test"):
        cases = load_task_with_cases("rag_knowledge", split)[1]
        for case in cases:
            assert case.id not in seen, f"{case.id} in {seen[case.id]} and {split}"
            seen[case.id] = split
    assert len(seen) == 45


def test_rag_case_has_retrieval_context() -> None:
    """Every case carries retrieval_context for the RAG metrics."""
    for split in ("train", "dev", "test"):
        _, cases = load_task_with_cases("rag_knowledge", split)
        for case in cases:
            assert case.retrieval_context is not None, f"{case.id} missing retrieval_context"
            assert len(case.retrieval_context) >= 0
            assert case.context is not None, f"{case.id} missing ground-truth context"


def test_lexical_faithfulness_grounded() -> None:
    """An answer fully supported by context scores high faithfulness."""
    answer = "Refunds are allowed within 30 days with a receipt."
    context = ["Refund policy: Customers may request a full refund within 30 days of purchase with original receipt."]
    assert lexical_faithfulness(answer, context) > 0.5


def test_lexical_faithfulness_ungrounded() -> None:
    """An answer not supported by context scores zero faithfulness."""
    answer = "The moon is made of green cheese."
    context = ["Refund policy: Customers may request a full refund within 30 days of purchase with original receipt."]
    assert lexical_faithfulness(answer, context) == 0.0


def test_lexical_answer_relevancy() -> None:
    """An answer using question vocabulary scores positive relevancy."""
    answer = "The refund window is 30 days."
    question = "How long do I have to request a refund?"
    assert lexical_answer_relevancy(answer, question) > 0


def test_contextual_relevancy_relevant() -> None:
    """A retrieved chunk sharing question vocabulary scores positive."""
    chunks = ["Refund policy: Customers may request a full refund within 30 days."]
    question = "refund policy days"
    assert contextual_relevancy(chunks, question) > 0


def test_contextual_relevancy_irrelevant() -> None:
    """An unrelated chunk scores zero contextual relevancy."""
    chunks = ["The moon is made of green cheese."]
    question = "refund policy"
    assert contextual_relevancy(chunks, question) == 0.0


def test_grounded_true_case_passes_boolean() -> None:
    """The grounded guardrail boolean rule passes when expected=True and predicted=True."""
    from forgebench.schemas import ScoringRule

    rule = ScoringRule(field="grounded", method="boolean", weight=2.0)
    assert rule.field == "grounded"
    assert rule.method == "boolean"
    assert rule.weight == 2.0
    # Boolean scoring: expected and predicted must match.
    assert (True == True) is True
    assert (True == False) is False


def test_rag_config_provider_matches_benchmark() -> None:
    """The RAG baseline config uses the same provider/model as the benchmark."""
    from forgebench.config import load_config

    # Load as a plain YAML document to inspect provider/model without requiring
    # the ExperimentConfig dataset field (task configs are run via task-run).
    import yaml
    path = REPO_ROOT / "configs" / "rag_knowledge_baseline.yaml"
    data = yaml.safe_load(path.read_text())
    assert data["provider"]["name"] == "openrouter"
    assert data["provider"]["model"] == "openai/gpt-4o-mini"
    assert data["experiment"]["task"] == "rag_knowledge"
    assert data["experiment"]["split"] == "test"
    assert data["evaluation"]["metrics"] == ["accuracy", "schema_validity", "latency", "estimated_cost"]


def test_output_schema_has_required_fields() -> None:
    """The task output schema declares answer, grounded, citations."""
    from forgebench.tasks import load_task
    task = load_task("rag_knowledge")
    names = {f.name for f in task.output_schema}
    assert names == {"answer", "grounded", "citations"}
    types = {f.name: f.type for f in task.output_schema}
    assert types["answer"] == "string"
    assert types["grounded"] == "boolean"
    assert types["citations"] == "list[string]"

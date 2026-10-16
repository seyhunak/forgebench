"""Unit tests for deterministic RAG metrics (DeepEval RAGAS style)."""

from __future__ import annotations

from forgebench.metrics.rag import (
    contextual_relevancy,
    lexical_answer_relevancy,
    lexical_faithfulness,
    tokenize,
)


def test_tokenize_strips_stopwords() -> None:
    tokens = tokenize("The cat sat on the mat.")
    assert "cat" in tokens
    assert "sat" in tokens
    assert "mat" in tokens
    assert "the" not in tokens
    assert "on" not in tokens


def test_lexical_faithfulness_grounded() -> None:
    score = lexical_faithfulness("Paris is in France.", ["Paris is the capital of France."])
    assert score > 0.5


def test_lexical_faithfulness_ungrounded() -> None:
    score = lexical_faithfulness("The moon is made of cheese.", ["Paris is the capital of France."])
    assert score == 0.0


def test_lexical_faithfulness_no_context() -> None:
    assert lexical_faithfulness("anything", []) == 0.0


def test_lexical_answer_relevancy() -> None:
    score = lexical_answer_relevancy("The capital is Paris.", "capital of France")
    assert score > 0


def test_contextual_relevancy() -> None:
    score = contextual_relevancy(["Paris is the capital of France."], "capital of France")
    assert score > 0
    assert contextual_relevancy(["unrelated chunk"], "capital of France") == 0.0

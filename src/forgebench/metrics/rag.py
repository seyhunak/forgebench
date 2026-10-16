"""Deterministic RAG metrics (no LLM calls): lexical faithfulness,
answer relevancy, contextual relevancy.

DeepEval's RAGAS-style metrics (faithfulness, answer relevancy, contextual
precision/recall) normally need an LLM. These lexical variants run offline and
give fast, explainable first-pass signals over retrieval_context / context
fields. LLM-judged variants live in the task scorer via llm_judge rules.
"""

from __future__ import annotations

import re

__all__ = [
    "tokenize",
    "claim_support",
    "lexical_faithfulness",
    "lexical_answer_relevancy",
    "contextual_relevancy",
]

_WORD_RE = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")

_STOPWORDS = frozenset(
    "a an the and or but of to in on for with is are was were be been have has had "
    "do does did will would can could should may might must this that these those "
    "it its as at by from into over after before between".split()
)


def tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric tokens minus English stopwords."""
    tokens = _WORD_RE.findall(text.lower())
    return [t for t in tokens if t not in _STOPWORDS and len(t) > 1]


def claim_support(claim: str, contexts: list[str]) -> float:
    """Fraction of claim content-words that appear in any context chunk."""
    claim_tokens = set(tokenize(claim))
    if not claim_tokens:
        return 1.0
    context_tokens: set[str] = set()
    for chunk in contexts:
        context_tokens.update(tokenize(chunk))
    if not context_tokens:
        return 0.0
    return len(claim_tokens & context_tokens) / len(claim_tokens)


def lexical_faithfulness(answer: str, retrieval_context: list[str]) -> float:
    """Share of answer sentences grounded (>=50% tokens) in retrieved context.

    Returns 1.0 for empty answers, 0.0 when no context was retrieved.
    """
    sentences = [s.strip() for s in re.split(r"[.!?]+", answer) if s.strip()]
    if not sentences:
        return 1.0
    if not retrieval_context:
        return 0.0
    grounded = sum(1 for s in sentences if claim_support(s, retrieval_context) >= 0.5)
    return grounded / len(sentences)


def lexical_answer_relevancy(answer: str, question: str) -> float:
    """Jaccard overlap between answer and question content-words.

    Cheap proxy for DeepEval's AnswerRelevancyMetric: an answer that shares
    vocabulary with the question is more likely to address it.
    """
    answer_tokens = set(tokenize(answer))
    question_tokens = set(tokenize(question))
    if not answer_tokens and not question_tokens:
        return 1.0
    if not answer_tokens or not question_tokens:
        return 0.0
    return len(answer_tokens & question_tokens) / len(answer_tokens | question_tokens)


def contextual_relevancy(retrieval_context: list[str], question: str) -> float:
    """Share of retrieved chunks with any content-word overlap with the question."""
    if not retrieval_context:
        return 0.0
    relevant = sum(1 for chunk in retrieval_context if claim_support(chunk, [question]) > 0)
    return relevant / len(retrieval_context)

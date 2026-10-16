"""Unit tests for LLM-as-judge (DeepEval G-Eval style)."""

from __future__ import annotations

from forgebench.judge import build_judge_prompt, parse_judge_response


def test_build_judge_prompt_includes_criterion() -> None:
    prompt = build_judge_prompt("Check facts match.")
    assert "Criterion: Check facts match." in prompt


def test_build_judge_prompt_includes_steps_and_io() -> None:
    prompt = build_judge_prompt(
        "Criterion here.",
        input_text="Q: capital of France?",
        actual_output="Paris",
        expected_output="Paris",
        evaluation_steps=["Step one", "Step two"],
    )
    assert "Step one" in prompt
    assert "Step two" in prompt
    assert "Q: capital of France?" in prompt
    assert "Paris" in prompt


def test_parse_judge_response_happy_path() -> None:
    score, verdict, reason = parse_judge_response(
        '{"score": 0.9, "reason": "Matches.", "pass": true}'
    )
    assert score == 0.9
    assert verdict is True
    assert reason == "Matches."


def test_parse_judge_response_tolerates_code_fence() -> None:
    raw = '```json\n{"score": 0.4, "reason": "partial", "pass": false}\n```'
    score, verdict, reason = parse_judge_response(raw)
    assert score == 0.4
    assert verdict is False
    assert reason == "partial"


def test_parse_judge_response_clips_score() -> None:
    score, _, _ = parse_judge_response('{"score": 1.5, "reason": "too high", "pass": true}')
    assert score == 1.0

    score, _, _ = parse_judge_response('{"score": -0.2, "reason": "too low", "pass": true}')
    assert score == 0.0

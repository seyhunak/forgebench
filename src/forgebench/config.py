"""Experiment configuration: YAML in, validated pydantic config out.

Configs are the reproducibility unit of ForgeBench. Everything that can
change a score lives in the config file: dataset + split, provider + model,
inference settings, prompt variant, and the metric list.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

_ENV_RE = re.compile(r"\$\{([A-Z0-9_]+)\}")


class ExperimentSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$", max_length=60)
    #: Either a versioned benchmark dataset (``dataset``) or a user-defined
    #: custom task (``task``). Exactly one must be set.
    dataset: str | None = None
    dataset_version: str | None = None
    task: str | None = Field(default=None, max_length=60)
    task_version: str | None = Field(default=None, max_length=20)
    split: str = "test"
    seed: int = 42

    @model_validator(mode="after")
    def _check_dataset_or_task(self) -> ExperimentSection:
        has_dataset = self.dataset is not None
        has_task = self.task is not None
        if has_dataset == has_task:
            raise ValueError(
                "experiment must specify exactly one of 'dataset' or 'task'"
            )
        return self


class ProviderSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    model: str
    options: dict[str, Any] = Field(default_factory=dict)


class InferenceSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    temperature: float = 0.0
    max_retries: int = 2
    timeout_seconds: float = 30.0
    max_tokens: int | None = 1024


class PromptSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system: str | None = None
    #: Registry-managed prompt: when set, its body replaces ``system``.
    name: str | None = Field(default=None, max_length=60)
    #: Pin a version (``null``/omitted = latest).
    version: int | None = Field(default=None, ge=1)
    few_shot_count: int = Field(default=0, ge=0, le=20)

    @model_validator(mode="after")
    def _check_name(self) -> PromptSection:
        if self.name is not None and not re.match(r"^[a-z0-9][a-z0-9._-]*$", self.name):
            raise ValueError(f"prompt.name {self.name!r} must use letters, digits, '.', '_' or '-'")
        if self.version is not None and not self.name:
            raise ValueError("prompt.version requires prompt.name")
        return self


class JudgeSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(
        description="Judge provider: mistral, openai, anthropic, google, openrouter, ollama."
    )
    model: str = Field(description="Judge model id. Prefer a cheap model (e.g. gpt-4o-mini).")
    options: dict[str, Any] = Field(
        default_factory=dict,
        description="Provider constructor options (e.g. mock judge_mode).",
    )
    criteria: str = Field(
        default=(
            "Assess whether the model's stated reason is factually grounded in the "
            "given input and correctly justifies the predicted category."
        ),
        description="G-Eval-style criterion the judge scores against.",
    )


class EvaluationSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metrics: list[str] = Field(min_length=1)
    #: Optional LLM-as-judge (G-Eval style) on top of the rule-based metrics.
    #: When set, every schema-valid prediction's ``reason`` is additionally
    #: scored by the chosen provider/model; results land in the run's
    #: ``metrics["judge"]`` block and the manifest shows the judge identity.
    judge: JudgeSection | None = None


class ExperimentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experiment: ExperimentSection
    provider: ProviderSection
    inference: InferenceSection = Field(default_factory=InferenceSection)
    prompt: PromptSection = Field(default_factory=PromptSection)
    evaluation: EvaluationSection


def _interpolate_env(raw: str, env: dict[str, str]) -> str:
    """Expand ${VAR} references. Missing variables fail loudly, never silently."""

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in env:
            raise ValueError(
                f"config references ${{{name}}} but it is not set in the environment. "
                f"Export {name} or edit the config."
            )
        return env[name]

    return _ENV_RE.sub(replace, raw)


def load_config(path: str | Path, env: dict[str, str] | None = None) -> ExperimentConfig:
    """Load and validate an experiment config, expanding ${ENV_VAR} references."""
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"config not found: {config_path}")
    raw = config_path.read_text(encoding="utf-8")
    expanded = _interpolate_env(raw, env if env is not None else dict(os.environ))
    data = yaml.safe_load(expanded)
    if not isinstance(data, dict):
        raise ValueError(f"config {config_path} must be a YAML mapping")
    return ExperimentConfig.model_validate(data)

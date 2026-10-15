"""Config loading: env interpolation and strict schemas."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from forgebench.config import ExperimentConfig, load_config

REPO_ROOT = Path(__file__).resolve().parents[1]

MINIMAL = """
experiment:
  name: unit-config
  dataset: finance_v1
provider:
  name: mock
  model: rule-mock-v1
evaluation:
  metrics: [accuracy]
"""


def test_minimal_config_loads_with_defaults(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(MINIMAL)
    config = load_config(path, env={})
    assert config.experiment.split == "test"
    assert config.inference.temperature == 0.0
    assert config.prompt.few_shot_count == 0


def test_env_interpolation(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(MINIMAL.replace("model: rule-mock-v1", 'model: "${MY_MODEL}"'))
    config = load_config(path, env={"MY_MODEL": "mistral-small-latest"})
    assert config.provider.model == "mistral-small-latest"


def test_missing_env_variable_fails_loudly(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(MINIMAL.replace("model: rule-mock-v1", 'model: "${NOPE_NOT_SET}"'))
    with pytest.raises(ValueError, match="NOPE_NOT_SET"):
        load_config(path, env={})


def test_unknown_top_level_keys_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(MINIMAL + "\nsecrets: banana\n")
    with pytest.raises(ValidationError):
        load_config(path, env={})


def test_shipped_configs_are_valid() -> None:
    configs = [
        REPO_ROOT / "configs" / "baseline.yaml",
        REPO_ROOT / "configs" / "mistral_baseline.yaml",
        *sorted((REPO_ROOT / "configs" / "experiments").glob("*.yaml")),
    ]
    assert len(configs) >= 4
    for path in configs:
        env = {"MISTRAL_MODEL": "open-mistral-7b"}
        config = load_config(path, env=env)
        assert isinstance(config, ExperimentConfig)
        assert config.experiment.dataset == "finance_v1"

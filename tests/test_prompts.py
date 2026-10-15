"""Prompt registry: immutable versions, labels, resolution, and provenance."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from forgebench.config import (
    EvaluationSection,
    ExperimentConfig,
    ExperimentSection,
    ProviderSection,
)
from forgebench.prompts import (
    PromptNotFound,
    list_prompt_names,
    list_versions,
    load_prompt,
    load_prompt_reference,
    prompt_catalog,
    resolve_system_prompt,
    save_prompt_version,
    set_label,
)


@pytest.fixture()
def registry(tmp_path: Path) -> Path:
    root = tmp_path / "prompts"
    root.mkdir()
    return root


def test_first_version_is_v1_and_latest(registry: Path) -> None:
    saved = save_prompt_version("classify", "You are a grader.", root=registry)
    assert saved.version == 1
    assert saved.body == "You are a grader."
    assert len(saved.sha256) == 64
    assert list_versions("classify", registry) == [1]
    assert load_prompt("classify", root=registry).body == "You are a grader."


def test_versions_are_immutable_and_increment(registry: Path) -> None:
    save_prompt_version("classify", "v1 body", root=registry)
    second = save_prompt_version("classify", "v2 body", note="tightened", root=registry)
    assert second.version == 2
    assert second.note == "tightened"

    # Editing never rewrites history: v1 still holds its original bytes.
    assert load_prompt("classify", 1, root=registry).body == "v1 body"
    assert load_prompt("classify", None, root=registry).body == "v2 body"


def test_unknown_prompt_and_version_raise_not_found(registry: Path) -> None:
    with pytest.raises(PromptNotFound):
        load_prompt("nope", root=registry)
    save_prompt_version("classify", "body", root=registry)
    with pytest.raises(PromptNotFound):
        load_prompt("classify", 7, root=registry)


def test_labels_point_at_versions(registry: Path) -> None:
    save_prompt_version("classify", "v1", root=registry)
    v2 = save_prompt_version("classify", "v2", root=registry)

    set_label("classify", "production", 1, root=registry)
    labels = set_label("classify", "latest-candidate", v2.version, root=registry)
    assert labels == {"production": 1, "latest-candidate": 2}
    assert "production" in load_prompt("classify", 1, root=registry).labels

    # Removing a label leaves the version intact.
    assert set_label("classify", "production", None, root=registry) == {"latest-candidate": 2}
    assert load_prompt("classify", 1, root=registry).labels == ()


def test_label_version_must_exist(registry: Path) -> None:
    save_prompt_version("classify", "v1", root=registry)
    with pytest.raises(PromptNotFound):
        set_label("classify", "production", 9, root=registry)


def test_invalid_prompt_names_are_rejected(registry: Path) -> None:
    with pytest.raises(ValueError):
        save_prompt_version("../escape", "body", root=registry)
    with pytest.raises(ValueError):
        save_prompt_version("Bad Name", "body", root=registry)


def test_reference_syntax_resolves(registry: Path) -> None:
    save_prompt_version("classify", "v1", root=registry)
    save_prompt_version("classify", "v2", root=registry)

    assert load_prompt_reference("classify", root=registry).version == 2
    assert load_prompt_reference("classify@latest", root=registry).version == 2
    assert load_prompt_reference("classify@1", root=registry).body == "v1"
    with pytest.raises(PromptNotFound):
        load_prompt_reference("classify@one", root=registry)


def test_catalog_summarises_names_versions_labels(registry: Path) -> None:
    save_prompt_version("b_prompt", "b", root=registry)
    save_prompt_version("a_prompt", "a1", root=registry)
    save_prompt_version("a_prompt", "a2", root=registry)
    set_label("a_prompt", "production", 2, root=registry)

    catalog = prompt_catalog(registry)
    assert [entry["name"] for entry in catalog] == ["a_prompt", "b_prompt"]
    a = catalog[0]
    assert a["versions"] == [1, 2]
    assert a["latest"] == 2
    assert a["labels"] == {"production": 2}
    assert list_prompt_names(registry) == ["a_prompt", "b_prompt"]


def test_resolve_prefers_registry_body_over_inline(registry: Path) -> None:
    save_prompt_version("classify", "registry text", root=registry)
    text, meta = resolve_system_prompt("classify", None, "inline text", root=registry)
    assert text == "registry text"
    assert meta is not None
    assert meta["source"] == "registry"
    assert meta["name"] == "classify"
    assert meta["version"] == 1


def test_resolve_falls_back_to_inline_when_no_name(registry: Path) -> None:
    text, meta = resolve_system_prompt(None, None, "inline text", root=registry)
    assert text == "inline text"
    assert meta is not None
    assert meta["source"] == "inline"


def test_resolve_reports_missing_registry_prompt(registry: Path) -> None:
    with pytest.raises(PromptNotFound):
        resolve_system_prompt("ghost", None, "inline text", root=registry)


def test_config_accepts_prompt_name_and_version() -> None:
    config = ExperimentConfig(
        experiment=ExperimentSection(name="unit", dataset="finance_v1"),
        provider=ProviderSection(name="openrouter", model="openai/gpt-4o-mini"),
        prompt={"name": "classify", "version": 2},
        evaluation=EvaluationSection(metrics=["accuracy"]),
    )
    assert config.prompt.name == "classify"
    assert config.prompt.version == 2


def test_config_rejects_version_without_name_and_bad_names() -> None:
    base = dict(
        experiment=ExperimentSection(name="unit", dataset="finance_v1"),
        provider=ProviderSection(name="openrouter", model="openai/gpt-4o-mini"),
        evaluation=EvaluationSection(metrics=["accuracy"]),
    )
    with pytest.raises(ValueError):
        ExperimentConfig.model_validate({**base, "prompt": {"version": 2}})
    with pytest.raises(ValueError):
        ExperimentConfig.model_validate({**base, "prompt": {"name": "Bad Name"}})


def test_run_manifest_records_prompt_provenance(
    tmp_path: Path, mock_config, tiny_dataset, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    from forgebench.runner import run_experiment

    class FakeProvider:
        name = "fake"
        model = "fake-1"
        system_prompt = "the prompt actually sent"

        def predict(self, case):  # noqa: ANN001
            return SimpleNamespace(
                content='{"category": "matched", "requires_review": false}',
                latency_ms=1.0,
                input_tokens=1,
                output_tokens=1,
            )

    monkeypatch.setattr("forgebench.runner._make_provider", lambda *a, **k: FakeProvider())

    result = run_experiment(mock_config, datasets_root=tiny_dataset, output_root=tmp_path, limit=1)
    manifest = json.loads((result.run_dir / "manifest.json").read_text(encoding="utf-8"))

    prompt_meta = manifest["prompt"]
    # No prompt configured -> the provider's own default is what really ran,
    # and the manifest says so instead of claiming an inline prompt.
    assert prompt_meta["source"] == "provider_default"
    assert (
        prompt_meta["effective_sha256"]
        == __import__("hashlib").sha256(b"the prompt actually sent").hexdigest()
    )
    assert manifest["prompt_build_ms"] >= 0


def test_run_uses_registry_prompt_body(
    tmp_path: Path, mock_config, tiny_dataset, registry_stub: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    from forgebench.runner import run_experiment

    save_prompt_version("classify", "registry body wins", root=registry_stub)
    monkeypatch.setenv("FORGEBENCH_PROMPTS_ROOT", str(registry_stub))

    class FakeProvider:
        name = "fake"
        model = "fake-1"

        def __init__(self) -> None:
            self.system_prompt = "registry body wins"

        def predict(self, case):  # noqa: ANN001
            return SimpleNamespace(
                content='{"category": "matched", "requires_review": false}',
                latency_ms=1.0,
                input_tokens=1,
                output_tokens=1,
            )

    captured: dict[str, object] = {}

    def fake_make_provider(config, examples, system_text=None):  # noqa: ANN001
        captured["system_text"] = system_text
        return FakeProvider()

    monkeypatch.setattr("forgebench.runner._make_provider", fake_make_provider)
    mock_config.prompt.name = "classify"

    result = run_experiment(mock_config, datasets_root=tiny_dataset, output_root=tmp_path, limit=1)
    assert captured["system_text"] == "registry body wins"

    manifest = json.loads((result.run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["prompt"]["source"] == "registry"
    assert manifest["prompt"]["version"] == 1
    assert manifest["prompt"]["sha256"] == manifest["prompt"]["effective_sha256"]


@pytest.fixture()
def registry_stub(tmp_path: Path) -> Path:
    root = tmp_path / "prompts"
    root.mkdir()
    return root

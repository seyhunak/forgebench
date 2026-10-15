"""The committed finance_v1 dataset: validity, hygiene, and determinism."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from forgebench.registry import default_datasets_root, load_split, validate_dataset
from forgebench.schemas import Category

REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATOR = REPO_ROOT / "scripts" / "generate_dataset.py"


def test_dataset_validates_clean() -> None:
    report = validate_dataset("finance_v1")
    assert report.ok, report.problems
    assert report.counts["train"] == 100
    assert report.counts["dev"] == 40
    assert report.counts["test"] == 60


def test_all_scenario_families_and_classes_present() -> None:
    cases = [case for split in ("train", "dev", "test") for case in load_split("finance_v1", split)]
    families = {case.scenario_family for case in cases}
    assert families >= {
        "matched",
        "amount_mismatch",
        "date_mismatch",
        "reference_mismatch",
        "duplicate",
        "ambiguous",
    }
    classes = {case.expected.category for case in cases}
    assert classes == set(Category)


def test_ids_are_unique_and_splits_disjoint() -> None:
    seen: dict[str, str] = {}
    for split in ("train", "dev", "test"):
        for case in load_split("finance_v1", split):
            assert case.id not in seen, f"{case.id} duplicated in {split} and {seen.get(case.id)}"
            seen[case.id] = split
    assert len(seen) == 200


def test_requires_review_matches_category() -> None:
    for split in ("train", "dev", "test"):
        for case in load_split("finance_v1", split):
            assert case.expected.requires_review == (case.expected.category is not Category.MATCHED)


def test_regeneration_is_byte_identical(tmp_path: Path) -> None:
    """Same seed, same bytes: the reproducibility guarantee the project rests on."""
    subprocess.run(
        [
            sys.executable,
            str(GENERATOR),
            "--seed",
            "42",
            "--train",
            "100",
            "--dev",
            "40",
            "--test",
            "60",
            "--out",
            str(tmp_path),
        ],
        check=True,
        capture_output=True,
    )
    committed = default_datasets_root() / "finance_v1"
    for name in ("train.jsonl", "dev.jsonl", "test.jsonl", "dataset.json", "dataset_card.md"):
        assert (tmp_path / name).read_bytes() == (committed / name).read_bytes(), f"{name} differs"


def test_ground_truth_follows_documented_precedence() -> None:
    """Non-ambiguous cases must match the deterministic rule set exactly."""
    from scripts.generate_dataset import rule_precedence  # type: ignore[import-not-found]

    for split in ("train", "dev", "test"):
        for case in load_split("finance_v1", split):
            if case.scenario_family == "ambiguous":
                continue
            assert rule_precedence(case.input) is case.expected.category, case.id

"""Dataset registry: locate, load, hash, and validate benchmark datasets.

Datasets are plain directories under ``datasets/`` with a ``dataset.json``
manifest and JSONL split files. The registry records a SHA-256 of every split
so a run can always be traced back to the exact bytes it evaluated.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from .schemas import BenchmarkCase, Category

_SPLIT_FILES = ("train.jsonl", "dev.jsonl", "test.jsonl")
_REQUIRED_FAMILIES = ("matched", "amount_mismatch", "ambiguous")


def default_datasets_root() -> Path:
    """The repo's ``datasets/`` directory (src layout: src/forgebench -> repo)."""
    import os

    override = os.environ.get("FORGEBENCH_DATASETS_ROOT")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2] / "datasets"


@dataclass(frozen=True)
class DatasetInfo:
    name: str
    version: str
    task: str
    license: str
    families: list[str]
    splits: dict[str, int]
    split_hashes: dict[str, str]
    card_path: Path


@dataclass(frozen=True)
class ModelArtifact:
    """How a *trained* model is identified, kept separate from evaluation runs.

    This is the seam where a future Forge-trained model plugs in: the
    benchmark only needs to know which artifact produced a set of predictions.
    """

    name: str
    version: str
    dataset_version: str
    training_config_hash: str
    provider: str


@dataclass
class DatasetValidationReport:
    name: str
    ok: bool = True
    problems: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    class_distribution: dict[str, int] = field(default_factory=dict)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def list_datasets(root: Path | None = None) -> list[str]:
    base = root or default_datasets_root()
    if not base.exists():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_dir() and (p / "dataset.json").exists())


def _dataset_dir(name: str, root: Path | None) -> Path:
    base = root or default_datasets_root()
    directory = base / name
    if not directory.is_dir():
        available = list_datasets(base)
        raise FileNotFoundError(
            f"dataset '{name}' not found under {base}. Available: {available or 'none'}"
        )
    return directory


def load_split(name: str, split: str, root: Path | None = None) -> list[BenchmarkCase]:
    """Load and validate one JSONL split. Every line must be a valid case."""
    directory = _dataset_dir(name, root)
    path = directory / f"{split}.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"split '{split}' not found for dataset '{name}': {path}")
    cases: list[BenchmarkCase] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            cases.append(BenchmarkCase.model_validate_json(line))
        except Exception as exc:
            raise ValueError(f"{path}:{line_number}: invalid case: {exc}") from exc
    return cases


def load_dataset(
    name: str, split: str, root: Path | None = None
) -> tuple[list[BenchmarkCase], DatasetInfo]:
    directory = _dataset_dir(name, root)
    meta_path = directory / "dataset.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"dataset manifest missing: {meta_path}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    cases = load_split(name, split, root)
    split_counts: dict[str, int] = {}
    split_hashes: dict[str, str] = {}
    for split_name in meta.get("splits", {}):
        split_path = directory / f"{split_name}.jsonl"
        if split_path.exists():
            split_counts[split_name] = sum(
                1 for line in split_path.read_text(encoding="utf-8").splitlines() if line.strip()
            )
            split_hashes[split_name] = sha256_file(split_path)
    info = DatasetInfo(
        name=meta["name"],
        version=str(meta["version"]),
        task=meta.get("task", "exception_classification"),
        license=meta.get("license", "see dataset_card.md"),
        families=meta.get("families", []),
        splits=split_counts,
        split_hashes=split_hashes,
        card_path=directory / "dataset_card.md",
    )
    return cases, info


def validate_dataset(name: str, root: Path | None = None) -> DatasetValidationReport:
    """Full-dataset validation: schema, id hygiene, splits, families, classes."""
    report = DatasetValidationReport(name=name)
    try:
        directory = _dataset_dir(name, root)
    except FileNotFoundError as exc:
        report.ok = False
        report.problems.append(str(exc))
        return report

    if not (directory / "dataset.json").exists():
        report.ok = False
        report.problems.append("missing dataset.json manifest")
    if not (directory / "dataset_card.md").exists():
        report.ok = False
        report.problems.append("missing dataset_card.md")

    seen_ids: dict[str, str] = {}
    family_names: set[str] = set()
    for split in ("train", "dev", "test"):
        path = directory / f"{split}.jsonl"
        if not path.exists():
            report.ok = False
            report.problems.append(f"missing split file: {path.name}")
            continue
        cases = load_split(name, split, root)
        report.counts[split] = len(cases)
        if not cases:
            report.ok = False
            report.problems.append(f"split '{split}' is empty")
        for case in cases:
            family_names.add(case.scenario_family)
            if case.id in seen_ids:
                report.ok = False
                report.problems.append(
                    f"duplicate case id {case.id} appears in '{seen_ids[case.id]}' and '{split}'"
                )
            seen_ids[case.id] = split
            if case.expected.requires_review and case.expected.category is Category.MATCHED:
                report.ok = False
                report.problems.append(f"{case.id}: matched cases must not require review")

    missing_families = [f for f in _REQUIRED_FAMILIES if f not in family_names]
    if missing_families:
        report.ok = False
        report.problems.append(f"missing scenario families: {missing_families}")

    all_cases = [
        case
        for split in ("train", "dev", "test")
        for case in (
            load_split(name, split, root) if (directory / f"{split}.jsonl").exists() else []
        )
    ]
    for category in Category:
        count = sum(1 for c in all_cases if c.expected.category is category)
        if count:
            report.class_distribution[category.value] = count
    if len(all_cases) < 100:
        report.ok = False
        report.problems.append(f"dataset has {len(all_cases)} cases; the floor is 100")
    return report

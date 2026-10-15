"""Task registry: locate, load, hash, and validate user-defined evaluation tasks.

Custom tasks live under ``tasks/`` with a ``task.yaml`` manifest and JSONL
case files. Unlike datasets (which are versioned synthetic benchmarks), tasks
are user-defined evaluation specs: input fields, output schema, and scoring
rules. Any domain can be evaluated without writing code.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .schemas import (
    TaskCase,
    TaskDefinition,
)


def default_tasks_root() -> Path:
    """The repo's ``tasks/`` directory."""
    import os

    override = os.environ.get("FORGEBENCH_TASKS_ROOT")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2] / "tasks"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def list_tasks(root: Path | None = None) -> list[str]:
    base = root or default_tasks_root()
    if not base.exists():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_dir() and (p / "task.yaml").exists())


def _task_dir(name: str, root: Path | None) -> Path:
    base = root or default_tasks_root()
    directory = base / name
    if not directory.is_dir():
        available = list_tasks(base)
        raise FileNotFoundError(
            f"task '{name}' not found under {base}. Available: {available or 'none'}"
        )
    return directory


def load_task(name: str, root: Path | None = None) -> TaskDefinition:
    directory = _task_dir(name, root)
    path = directory / "task.yaml"
    if not path.exists():
        raise FileNotFoundError(f"task manifest not found: {path}")
    raw = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise ValueError(f"task manifest {path} must be a YAML mapping")
    return TaskDefinition.model_validate(data)


def load_cases(name: str, split: str, root: Path | None = None) -> list[TaskCase]:
    directory = _task_dir(name, root)
    path = directory / f"{split}.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"split '{split}' not found for task '{name}': {path}")
    cases: list[TaskCase] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            cases.append(TaskCase.model_validate_json(line))
        except Exception as exc:
            raise ValueError(f"{path}:{line_number}: invalid case: {exc}") from exc
    return cases


def load_task_with_cases(
    name: str, split: str, root: Path | None = None
) -> tuple[TaskDefinition, list[TaskCase]]:
    task = load_task(name, root)
    cases = load_cases(name, split, root)
    return task, cases


@dataclass(frozen=True)
class TaskInfo:
    name: str
    version: str
    description: str
    input_fields: list[str]
    output_fields: list[str]
    scoring_methods: list[str]
    n_cases: dict[str, int]
    case_hashes: dict[str, str]
    task_path: Path


@dataclass
class TaskValidationReport:
    name: str
    ok: bool = True
    problems: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)


def validate_task(name: str, root: Path | None = None) -> tuple[TaskInfo, TaskValidationReport]:
    report = TaskValidationReport(name=name)
    try:
        directory = _task_dir(name, root)
    except FileNotFoundError as exc:
        report.ok = False
        report.problems.append(str(exc))
        return None, report  # type: ignore[return-value]

    if not (directory / "task.yaml").exists():
        report.ok = False
        report.problems.append("missing task.yaml manifest")
        return None, report  # type: ignore[return-value]

    try:
        task = load_task(name, root)
    except Exception as exc:
        report.ok = False
        report.problems.append(f"invalid task.yaml: {exc}")
        return None, report  # type: ignore[return-value]

    # Validate scoring rules reference existing output fields
    output_field_names = {f.name for f in task.output_schema}
    for rule in task.scoring_rules:
        if rule.field not in output_field_names:
            report.ok = False
            report.problems.append(
                f"scoring rule references unknown output field '{rule.field}'"
            )

    # Validate splits and cases
    seen_ids: dict[str, str] = {}
    for split in ("train", "dev", "test"):
        path = directory / f"{split}.jsonl"
        if not path.exists():
            continue
        try:
            cases = load_cases(name, split, root)
        except Exception as exc:
            report.ok = False
            report.problems.append(f"invalid split '{split}': {exc}")
            continue
        report.counts[split] = len(cases)
        for case in cases:
            missing_inputs = [f for f in task.input_fields if f not in case.input]
            if missing_inputs:
                report.ok = False
                report.problems.append(
                    f"{case.id}: missing input fields {missing_inputs}"
                )
            expected_names = {f.name for f in task.output_schema}
            missing_expected = [f for f in expected_names if f not in case.expected]
            if missing_expected:
                report.ok = False
                report.problems.append(
                    f"{case.id}: missing expected fields {missing_expected}"
                )
            if case.id in seen_ids:
                report.ok = False
                report.problems.append(
                    f"duplicate case id {case.id} in '{seen_ids[case.id]}' and '{split}'"
                )
            seen_ids[case.id] = split

    total = sum(report.counts.values())
    if total < 5:
        report.ok = False
        report.problems.append(f"task has {total} cases; minimum is 5")

    split_hashes: dict[str, str] = {}
    for split_name in report.counts:
        split_path = directory / f"{split_name}.jsonl"
        if split_path.exists():
            split_hashes[split_name] = sha256_file(split_path)

    return TaskInfo(
        name=task.name,
        version=task.version,
        description=task.description,
        input_fields=task.input_fields,
        output_fields=[f.name for f in task.output_schema],
        scoring_methods=[r.method for r in task.scoring_rules],
        n_cases=report.counts,
        case_hashes=split_hashes,
        task_path=directory,
    ), report


__all__ = [
    "default_tasks_root",
    "list_tasks",
    "load_task",
    "load_cases",
    "load_task_with_cases",
    "validate_task",
    "TaskInfo",
    "TaskValidationReport",
]
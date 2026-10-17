"""Versioned prompt registry: prompts are files, versions are immutable.

Layout (mirrors how datasets are stored — plain files the repo can diff)::

    prompts/
      classify_v1/
        v1.md          # body of version 1
        v2.md          # body of version 2 (the highest number is "latest")
        labels.json    # {"production": 1}  — named pointers, Langfuse-style
        v2.meta.json   # optional: {"note": "...", "created_at": "..."}

Why files rather than a database: a prompt that changed a benchmark score
must be reviewable in the same diff as the code that changed. Version bodies
are immutable once written — edits create a new version — so a manifest that
names ``classify_v1@2`` always resolves to the exact bytes that were run.

Resolution contract used by the runner:

* ``prompt.name`` set  -> the registry body wins (``prompt.system`` ignored).
* ``prompt.name`` null -> inline ``prompt.system`` as before; no registry read.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$", re.IGNORECASE)
_VERSION_RE = re.compile(r"^v(\d+)\.md$")


def default_prompts_root() -> Path:
    """The repo's ``prompts/`` directory (overridable for tests)."""
    override = os.environ.get("FORGEBENCH_PROMPTS_ROOT")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2] / "prompts"


@dataclass(frozen=True)
class PromptVersion:
    """One immutable body of prompt text."""

    name: str
    version: int
    body: str
    sha256: str
    note: str = ""
    created_at: str = ""
    labels: tuple[str, ...] = ()

    @property
    def chars(self) -> int:
        return len(self.body)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "sha256": self.sha256,
            "note": self.note,
            "created_at": self.created_at,
            "labels": list(self.labels),
            "chars": self.chars,
            "body": self.body,
        }

    @property
    def reference(self) -> str:
        """``name@version`` — the form recorded in a run manifest."""
        return f"{self.name}@{self.version}"


class PromptNotFound(FileNotFoundError):
    """Raised when a prompt name or version does not exist."""


def _check_name(name: str) -> str:
    if not _NAME_RE.match(name) or len(name) > 60:
        raise ValueError(f"invalid prompt name {name!r}: use letters, digits, . _ - (max 60)")
    return name


def _prompt_dir(name: str, root: Path | None) -> Path:
    return (root or default_prompts_root()) / _check_name(name)


def _read_labels(directory: Path) -> dict[str, int]:
    path = directory / "labels.json"
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return {str(k): int(v) for k, v in raw.items()} if isinstance(raw, dict) else {}


def _write_labels(directory: Path, labels: dict[str, int]) -> None:
    path = directory / "labels.json"
    if labels:
        path.write_text(json.dumps(dict(sorted(labels.items())), indent=2) + "\n", encoding="utf-8")
    elif path.is_file():
        path.unlink()


def list_prompt_names(root: Path | None = None) -> list[str]:
    """Every prompt name in the registry, sorted."""
    base = root or default_prompts_root()
    if not base.is_dir():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_dir() and list_versions(p.name, base))


def list_versions(name: str, root: Path | None = None) -> list[int]:
    """Version numbers for one prompt, ascending. ``[]`` when unknown."""
    directory = _prompt_dir(name, root)
    if not directory.is_dir():
        return []
    versions = []
    for path in directory.iterdir():
        match = _VERSION_RE.match(path.name)
        if match:
            versions.append(int(match.group(1)))
    return sorted(versions)


def load_prompt(
    name: str, version: int | None = None, *, root: Path | None = None
) -> PromptVersion:
    """Load one prompt version; ``version=None`` resolves the label ``latest``.

    ``latest`` means the highest version number, not a label file — a pointer
    that must be moved by hand is a pointer that goes stale.
    """
    directory = _prompt_dir(name, root)
    available = list_versions(name, root)
    if not available:
        raise PromptNotFound(f"prompt {name!r} not found (registry: {directory.parent})")
    if version is None:
        version = available[-1]
    if version not in available:
        raise PromptNotFound(
            f"prompt {name!r} has no version {version} (available: {available})"
        )

    body = (directory / f"v{version}.md").read_text(encoding="utf-8")
    note, created_at = "", ""
    meta_path = directory / f"v{version}.meta.json"
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            note = str(meta.get("note", "") or "")
            created_at = str(meta.get("created_at", "") or "")
        except json.JSONDecodeError:
            pass
    labels = tuple(sorted(k for k, v in _read_labels(directory).items() if v == version))
    return PromptVersion(
        name=name,
        version=version,
        body=body,
        sha256=hashlib.sha256(body.encode("utf-8")).hexdigest(),
        note=note,
        created_at=created_at,
        labels=labels,
    )


def load_prompt_reference(reference: str, *, root: Path | None = None) -> PromptVersion:
    """Resolve ``name``, ``name@latest`` or ``name@2``."""
    name, _, tag = reference.partition("@")
    version: int | None = None
    if tag and tag != "latest":
        if not tag.isdigit():
            raise PromptNotFound(f"bad prompt reference {reference!r}: expected name@N")
        version = int(tag)
    return load_prompt(name, version, root=root)


def save_prompt_version(
    name: str,
    body: str,
    *,
    note: str = "",
    root: Path | None = None,
) -> PromptVersion:
    """Write the next immutable version of a prompt.

    Refuses to overwrite: a version that could be rewritten is a version a
    manifest can no longer trust.
    """
    directory = _prompt_dir(name, root)
    directory.mkdir(parents=True, exist_ok=True)
    existing = list_versions(name, root)
    version = (existing[-1] + 1) if existing else 1

    path = directory / f"v{version}.md"
    if path.exists():
        raise FileExistsError(f"{path} already exists; versions are immutable")
    path.write_text(body, encoding="utf-8")
    (directory / f"v{version}.meta.json").write_text(
        json.dumps(
            {"note": note, "created_at": datetime.now(UTC).isoformat(timespec="seconds")},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return load_prompt(name, version, root=root)


def set_label(
    name: str, label: str, version: int | None, *, root: Path | None = None
) -> dict[str, int]:
    """Point ``label`` at ``version`` (or remove it when ``version`` is None)."""
    if not _NAME_RE.match(label):
        raise ValueError(f"invalid label {label!r}")
    directory = _prompt_dir(name, root)
    if not list_versions(name, root):
        raise PromptNotFound(f"prompt {name!r} not found")
    labels = _read_labels(directory)
    if version is None:
        labels.pop(label, None)
    else:
        if version not in list_versions(name, root):
            raise PromptNotFound(f"prompt {name!r} has no version {version}")
        labels[label] = version
    _write_labels(directory, labels)
    return labels


def prompt_catalog(root: Path | None = None) -> list[dict[str, Any]]:
    """Everything the UI/CLI needs to list prompts: versions + labels + notes."""
    entries: list[dict[str, Any]] = []
    for name in list_prompt_names(root):
        versions = list_versions(name, root)
        labels = _read_labels(_prompt_dir(name, root))
        latest = load_prompt(name, None, root=root)
        entries.append(
            {
                "name": name,
                "latest": versions[-1],
                "versions": versions,
                "labels": labels,
                "latest_sha256": latest.sha256,
                "latest_note": latest.note,
                "chars": latest.chars,
            }
        )
    return entries


def resolve_system_prompt(
    name: str | None,
    version: int | None,
    inline: str | None,
    *,
    root: Path | None = None,
) -> tuple[str | None, dict[str, Any] | None]:
    """Resolve the system prompt a run should send, plus how it was sourced.

    Returns ``(text, meta)`` where ``meta`` records the provenance a manifest
    needs: ``{"source": "registry"|"inline", "name", "version", "sha256",
    "chars"}``. Registry prompts win over ``prompt.system``; with no ``name``
    the inline text is returned untouched and no file is read.
    """
    if not name:
        if inline is None:
            return None, {"source": "none", "chars": 0}
        return inline, {"source": "inline", "chars": len(inline)}

    prompt = load_prompt(name, version, root=root)
    meta = {
        "source": "registry",
        "name": prompt.name,
        "version": prompt.version,
        "sha256": prompt.sha256,
        "chars": prompt.chars,
        "note": prompt.note,
        "labels": list(prompt.labels),
    }
    return prompt.body, meta


__all__ = [
    "PromptNotFound",
    "PromptVersion",
    "default_prompts_root",
    "list_prompt_names",
    "list_versions",
    "load_prompt",
    "load_prompt_reference",
    "prompt_catalog",
    "resolve_system_prompt",
    "save_prompt_version",
    "set_label",
]

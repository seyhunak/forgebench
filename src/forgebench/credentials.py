"""Bring-your-own-key storage: a git-ignored ``.env`` file, mode 0600.

Rules this module exists to enforce:

* Keys never appear in configs, manifests, run artifacts, or Git.
* Lookup order is process environment first, then the nearest ``.env``
  walking up from the working directory (so runs work from any subdirectory).
* The file is created with owner-only permissions.

``forgebench set-key`` is the user-facing command; everything here is the
machinery behind it and the fallback used by provider adapters.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from dotenv import dotenv_values

ENV_FILENAME = ".env"
_LINE_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=")


def find_env_file(start: Path | None = None) -> Path | None:
    """Nearest ``.env`` at ``start`` or any parent directory."""
    base = (start or Path.cwd()).resolve()
    for directory in (base, *base.parents):
        candidate = directory / ENV_FILENAME
        if candidate.is_file():
            return candidate
    return None


def env_file_for_write(start: Path | None = None) -> Path:
    """Update an existing ``.env`` if one exists nearby, else create at ``start``."""
    return find_env_file(start) or (start or Path.cwd()).resolve() / ENV_FILENAME


def _format_line(name: str, value: str) -> str:
    if any(char in value for char in " #\"'\t") or not value:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'{name}="{escaped}"'
    return f"{name}={value}"


def set_value(name: str, value: str, path: Path | None = None) -> Path:
    """Upsert ``name=value`` in the target ``.env``, preserving other lines.

    The file is re-chmodded to 0600 on every write, in case it was created
    more permissively elsewhere.
    """
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise ValueError(f"invalid variable name: {name!r}")
    target = path or env_file_for_write()
    lines = target.read_text(encoding="utf-8").splitlines() if target.exists() else []
    output: list[str] = []
    replaced = False
    for line in lines:
        match = _LINE_RE.match(line)
        if match and match.group(1) == name:
            output.append(_format_line(name, value))
            replaced = True
        else:
            output.append(line)
    if not replaced:
        output.append(_format_line(name, value))
    target.write_text("\n".join(output) + "\n", encoding="utf-8")
    os.chmod(target, 0o600)
    return target


def delete_value(name: str, path: Path | None = None) -> Path | None:
    """Remove ``name`` from the target ``.env``. Returns the file, or None."""
    target = path or find_env_file()
    if target is None or not target.exists():
        return None
    lines = target.read_text(encoding="utf-8").splitlines()
    kept = [line for line in lines if not (m := _LINE_RE.match(line)) or m.group(1) != name]
    if len(kept) == len(lines):
        return target
    target.write_text("\n".join(kept) + "\n" if kept else "", encoding="utf-8")
    os.chmod(target, 0o600)
    return target


def source_of(name: str) -> str:
    """Where a variable would be read from: 'environment', a file path, or 'not set'."""
    if os.environ.get(name):
        return "environment"
    env_file = find_env_file()
    if env_file and (dotenv_values(env_file).get(name) or "").strip():
        return str(env_file)
    return "not set"


def load_env_files() -> Path | None:
    """Load the nearest ``.env`` (working directory upward) into the environment.

    Variables already present in the process environment win. Used by both the
    CLI and the dashboard so credentials behave identically in each.
    """
    from dotenv import find_dotenv, load_dotenv  # local import keeps module light

    path = find_dotenv(usecwd=True)
    if path:
        load_dotenv(path)
        return Path(path)
    return None


def get_value(name: str) -> str | None:
    """Environment first, then the nearest ``.env``."""
    value = os.environ.get(name)
    if value:
        return value
    env_file = find_env_file()
    if env_file:
        stored = (dotenv_values(env_file).get(name) or "").strip()
        if stored:
            return stored
    return None


def mask(value: str | None) -> str:
    """Display form for a secret: never the whole thing."""
    if not value:
        return "(not set)"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:3]}{'*' * 8}{value[-4:]}"

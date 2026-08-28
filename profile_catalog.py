"""Filesystem-backed discovery helpers for saved KeyClick profiles."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from engine import Action, RunSettings, load_profile


ProfileLoader = Callable[[str | Path], tuple[list[Action], RunSettings]]


def normalize_path(path: str | Path) -> str:
    return str(Path(path).expanduser().resolve())


def default_profile_directory() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def profile_name(path: str | Path) -> str:
    name = Path(path).name
    if name.lower().endswith(".kca.json"):
        return name[:-9]
    if name.lower().endswith(".json"):
        return name[:-5]
    return name


def modified_label(timestamp: float, now: datetime | None = None) -> str:
    modified = datetime.fromtimestamp(timestamp)
    current = now or datetime.now()
    time_label = modified.strftime("%I:%M %p").lstrip("0")
    if modified.date() == current.date():
        return f"Today · {time_label}"
    return f"{modified.strftime('%b %d, %Y')} · {time_label}"


def profile_entry(
    path: Path,
    profile_loader: ProfileLoader = load_profile,
) -> dict[str, Any] | None:
    try:
        timestamp = path.stat().st_mtime
    except OSError:
        return None

    entry: dict[str, Any] = {
        "path": normalize_path(path),
        "name": profile_name(path),
        "actionCount": 0,
        "activeCount": 0,
        "modified": modified_label(timestamp),
        "modifiedTimestamp": timestamp,
        "valid": False,
        "error": "",
    }
    try:
        actions, _settings = profile_loader(path)
        entry["actionCount"] = len(actions)
        entry["activeCount"] = sum(action.enabled for action in actions)
        entry["valid"] = True
    except (AttributeError, OSError, TypeError, ValueError) as exc:
        # Plain JSON files may share the folder. Only surface invalid files
        # that explicitly use KeyClick's profile suffix.
        if not path.name.lower().endswith(".kca.json"):
            return None
        entry["error"] = str(exc) or "This profile could not be read."
    return entry


def list_profile_entries(
    directory: str | Path,
    profile_loader: ProfileLoader = load_profile,
) -> list[dict[str, Any]]:
    root = Path(directory)
    if not root.is_dir():
        return []
    try:
        candidates = [
            path
            for path in root.iterdir()
            if path.is_file() and path.name.lower().endswith(".json")
        ]
    except OSError:
        return []

    entries = [
        entry
        for path in candidates
        if (entry := profile_entry(path, profile_loader)) is not None
    ]
    entries.sort(
        key=lambda entry: (-float(entry["modifiedTimestamp"]), entry["name"].lower())
    )
    return entries

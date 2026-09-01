"""Keep the previous versions of a profile so a save is never the end of it.

Saving overwrites in place, which makes it the most destructive action in the
app while looking like the safest. A stray click emptied two real profiles in a
single session with no way back. Every save now snapshots what was on disk
first, into a hidden folder beside the profile.
"""
from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

HISTORY_DIR_NAME = ".keyclick-history"
KEEP_VERSIONS = 10
_STAMP = "%Y%m%d-%H%M%S"
_SNAPSHOT = re.compile(r"^(?P<stem>.+)__(?P<stamp>\d{8}-\d{6})\.kca\.json$")


@dataclass(frozen=True)
class Version:
    path: Path
    saved_at: datetime
    action_count: int

    @property
    def label(self) -> str:
        return self.saved_at.strftime("%d %b %Y · %H:%M:%S")

    def as_entry(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "savedAt": self.saved_at.isoformat(timespec="seconds"),
            "label": self.label,
            "actionCount": self.action_count,
        }


def history_directory(profile_path: str | Path) -> Path:
    return Path(profile_path).parent / HISTORY_DIR_NAME


def _count_actions(path: Path) -> int:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return -1
    actions = payload.get("actions")
    return len(actions) if isinstance(actions, list) else -1


def snapshot(profile_path: str | Path, now: datetime | None = None, keep: int = KEEP_VERSIONS) -> Path | None:
    """Copy the profile as it currently is on disk. Returns None if there is none yet."""
    source = Path(profile_path)
    if not source.is_file():
        return None  # a brand new profile has no previous version to keep
    directory = history_directory(source)
    directory.mkdir(parents=True, exist_ok=True)
    stem = source.name[: -len(".kca.json")] if source.name.endswith(".kca.json") else source.stem
    stamp = (now or datetime.now()).strftime(_STAMP)
    destination = directory / f"{stem}__{stamp}.kca.json"
    if destination.exists():
        return destination  # same second, same content: nothing new to keep
    shutil.copy2(source, destination)
    _prune(source, keep)
    return destination


def versions(profile_path: str | Path) -> list[Version]:
    """Saved versions of this profile, newest first."""
    source = Path(profile_path)
    directory = history_directory(source)
    if not directory.is_dir():
        return []
    stem = source.name[: -len(".kca.json")] if source.name.endswith(".kca.json") else source.stem
    found: list[Version] = []
    for candidate in directory.glob("*.kca.json"):
        match = _SNAPSHOT.match(candidate.name)
        if not match or match.group("stem") != stem:
            continue
        try:
            saved_at = datetime.strptime(match.group("stamp"), _STAMP)
        except ValueError:
            continue
        found.append(Version(candidate, saved_at, _count_actions(candidate)))
    return sorted(found, key=lambda version: version.saved_at, reverse=True)


def _prune(profile_path: str | Path, keep: int) -> None:
    for stale in versions(profile_path)[keep:]:
        stale.path.unlink(missing_ok=True)


def restore(profile_path: str | Path, version_path: str | Path) -> Path:
    """Put a version back, snapshotting the current file first so this is undoable."""
    source = Path(version_path)
    destination = Path(profile_path)
    if not source.is_file():
        raise OSError("That version is no longer available.")
    snapshot(destination)
    shutil.copy2(source, destination)
    return destination

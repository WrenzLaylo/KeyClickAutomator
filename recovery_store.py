"""Atomic persistence helpers for KeyClick's autosaved recovery draft."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from engine import Action, RunSettings


def read_recovery_payload(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Recovery copy is invalid.")
    return payload


def describe_recovery_draft(path: str | Path) -> str:
    try:
        payload = read_recovery_payload(path)
        actions = payload.get("actions", [])
        count = len(actions) if isinstance(actions, list) else 0
        name = str(payload.get("profile_name") or "Untitled sequence")
        noun = "action" if count == 1 else "actions"
        return f"{name} · {count} {noun}"
    except (OSError, ValueError, TypeError):
        return "A recovery copy from the previous session is available."


def write_recovery_draft(
    path: str | Path,
    actions: list[Action],
    settings: RunSettings,
    profile_name: str,
    profile_path: str | None,
) -> None:
    destination = Path(path)
    payload = {
        "version": 1,
        "profile_name": profile_name,
        "profile_path": profile_path,
        "actions": [asdict(action) for action in actions],
        "settings": asdict(settings),
    }
    temporary = destination.with_name(destination.name + ".tmp")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary.replace(destination)


def remove_recovery_draft(path: str | Path) -> None:
    destination = Path(path)
    destination.unlink(missing_ok=True)
    destination.with_name(destination.name + ".tmp").unlink(missing_ok=True)

"""Shortcut presentation and pynput adapter helpers."""
from __future__ import annotations

from typing import Any

from engine import HOTKEY_NAMED_KEYS, validate_global_hotkey


def global_shortcut_conflicts(
    start_hotkey: str,
    capture_hotkey: str,
    stop_hotkey: str,
) -> dict[str, Any]:
    """Describe duplicate global controls while their form is being edited."""
    entries = (
        ("startConflict", "Start / toggle", start_hotkey),
        ("captureConflict", "Record pointer", capture_hotkey),
        ("stopConflict", "Emergency stop", stop_hotkey),
    )
    result: dict[str, Any] = {
        "hasConflict": False,
        "message": "",
        "startConflict": False,
        "captureConflict": False,
        "stopConflict": False,
    }
    groups: dict[str, list[tuple[str, str]]] = {}
    for flag, label, value in entries:
        try:
            canonical = validate_global_hotkey(value, label)
        except (TypeError, ValueError):
            # General syntax errors are surfaced when settings are applied.
            continue
        groups.setdefault(canonical, []).append((flag, label))

    conflict = next(
        (
            (shortcut, members)
            for shortcut, members in groups.items()
            if len(members) > 1
        ),
        None,
    )
    if conflict is None:
        return result

    shortcut, members = conflict
    result["hasConflict"] = True
    for flag, _label in members:
        result[flag] = True
    labels = [label for _flag, label in members]
    if len(labels) == 2:
        result["message"] = (
            f"{labels[0]} and {labels[1]} cannot use the same shortcut "
            f"({shortcut.upper()})."
        )
    else:
        result["message"] = (
            f"All three global shortcuts currently use {shortcut.upper()}. "
            "Choose a different shortcut for each action."
        )
    return result


def pynput_hotkey(value: str) -> str:
    aliases = {
        "control": "ctrl",
        "escape": "esc",
        "return": "enter",
        "windows": "cmd",
        "win": "cmd",
    }
    formatted = []
    for raw in value.lower().replace(" ", "").split("+"):
        part = aliases.get(raw, raw)
        is_function_key = part.startswith("f") and part[1:].isdigit()
        formatted.append(f"<{part}>" if part in HOTKEY_NAMED_KEYS or is_function_key else part)
    return "+".join(formatted)

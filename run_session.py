"""Runtime state for one KeyClick automation profile.

The controller owns orchestration, while each session owns the mutable state that
used to live on the controller as one global worker and stop event.  Keeping this
state together makes sequential queues safe now and leaves a clean boundary for
parallel background-window sessions later.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from engine import Action, RunSettings


@dataclass
class RunSession:
    profile_name: str
    profile_path: str
    actions: list[Action]
    action_indices: list[int]
    settings: RunSettings
    completion_message: str
    status_verb: str = "Running"
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    target_hwnd: int = 0
    state: str = "queued"
    status: str = "Queued"
    tone: str = "neutral"
    progress: float = 0.0
    running_action_index: int = -1
    error: str = ""
    stop_requested_by_user: bool = False
    reserved_shortcuts: set[str] = field(default_factory=set, repr=False)
    stop_event: threading.Event = field(default_factory=threading.Event, repr=False)
    pause_event: threading.Event = field(default_factory=threading.Event, repr=False)
    worker: threading.Thread | None = field(default=None, repr=False)

    @property
    def target_label(self) -> str:
        if self.settings.target_mode == "desktop":
            return "Desktop"
        return (
            self.settings.target_window_title
            or (
                Path(self.settings.target_executable).stem
                if self.settings.target_executable
                else ""
            )
            or self.settings.target_window_class
            or "Background window"
        )

    @property
    def active_action_count(self) -> int:
        return len(self.actions)

    def reset(self) -> None:
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.worker = None
        self.target_hwnd = 0
        self.reserved_shortcuts = set()
        self.state = "queued"
        self.status = "Queued"
        self.tone = "neutral"
        self.progress = 0.0
        self.running_action_index = -1
        self.error = ""
        self.stop_requested_by_user = False

    def as_entry(self, position: int, total: int) -> dict[str, Any]:
        return {
            "id": self.session_id,
            "profileName": self.profile_name,
            "profilePath": self.profile_path,
            "position": position,
            "total": total,
            "actionCount": self.active_action_count,
            "target": self.target_label,
            "targetMode": self.settings.target_mode,
            "state": self.state,
            "status": self.status,
            "tone": self.tone,
            "progress": self.progress,
            "error": self.error,
            "paused": self.pause_event.is_set(),
        }

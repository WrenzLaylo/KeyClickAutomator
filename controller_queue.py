"""Building a run: the profile queue, target validation, and preflight."""
from __future__ import annotations

import copy
import os
import threading
from pathlib import Path
from typing import Any

import pyautogui
from PySide6.QtCore import Property, QStandardPaths, QTimer, Slot
from pynput import keyboard

from capture_overlay import PositionCaptureOverlay
from chrome_backend import (
    ChromeTabBackend,
    ChromeTargetError,
    browser_available,
    find_tab,
    launch_chrome,
    list_tabs,
    wait_for_browser,
)
from engine import (
    Action,
    AutomationRunner,
    RunSettings,
    canonical_global_shortcuts,
    load_profile,
    save_profile,
)
from preflight import Check, blocking_failures, looks_like_a_browser, preflight
from profile_catalog import default_profile_directory, normalize_path, profile_name
from profile_history import restore as restore_version, snapshot, versions
from recovery_store import (
    describe_recovery_draft,
    read_recovery_payload,
    remove_recovery_draft,
    write_recovery_draft,
)
from run_session import RunSession
from shortcut_service import global_shortcut_conflicts, pynput_hotkey
from window_backend import (
    WindowInfo,
    WindowMessageBackend,
    WindowSelector,
    WindowTargetError,
    Win32WindowService,
)

from controller_signals import ControllerSignals

# Eight parallel sessions is the point where distinct targets stop being
# plausible and the browser's own throttling dominates.
MAX_PARALLEL_SESSIONS = 8

class QueueMixin(ControllerSignals):
    """What to run, and whether it can work at all."""

    @staticmethod
    def _path_key(path: str | Path) -> str:
        return os.path.normcase(normalize_path(path))

    def _load_profile_session(
        self,
        path: str | Path,
        existing: RunSession | None = None,
    ) -> RunSession:
        normalized = normalize_path(path)
        if not Path(normalized).is_file():
            raise OSError("That profile file is no longer available.")
        actions, settings = load_profile(normalized)
        indexed_actions = [
            (index, copy.deepcopy(action))
            for index, action in enumerate(actions)
            if action.enabled
        ]
        if not indexed_actions:
            raise ValueError("Add or enable at least one action before queuing this profile.")
        session = existing or RunSession(
            profile_name=profile_name(normalized),
            profile_path=normalized,
            actions=[],
            action_indices=[],
            settings=copy.deepcopy(settings),
            completion_message=f"{profile_name(normalized)} complete",
        )
        session.profile_name = profile_name(normalized)
        session.profile_path = normalized
        session.actions = [action for _, action in indexed_actions]
        session.action_indices = [index for index, _ in indexed_actions]
        session.settings = copy.deepcopy(settings)
        session.completion_message = f"{session.profile_name} complete"
        session.status_verb = "Running"
        session.reset()
        return session

    @Slot(str, result=bool)
    def enqueueProfile(self, path: str) -> bool:
        if self._running or self._queue_active:
            self.toast.emit("Stop the current run before changing the queue.", "error")
            return False
        normalized = normalize_path(path)
        if (
            self._current_profile_path
            and self._path_key(normalized) == self._path_key(self._current_profile_path)
            and (self._dirty or self._run_settings_pending)
        ):
            self.toast.emit("Save this profile before adding it to the run queue.", "error")
            return False
        if any(
            self._path_key(session.profile_path) == self._path_key(normalized)
            for session in self._run_queue
        ):
            self.toast.emit(f"{profile_name(normalized)} is already in the run queue.", "neutral")
            return False
        if len(self._run_queue) >= 50:
            self.toast.emit("A run queue can contain up to 50 profiles.", "error")
            return False
        try:
            session = self._load_profile_session(normalized)
        except (OSError, ValueError, TypeError) as exc:
            self.toast.emit(f"Could not queue {profile_name(normalized)}: {exc}", "error")
            return False
        self._run_queue.append(session)
        self.runQueueChanged.emit()
        self.toast.emit(f"Queued {session.profile_name}", "success")
        return True

    @Slot(str, result=bool)
    def setRunQueueMode(self, mode: str) -> bool:
        normalized = str(mode).strip().casefold()
        if normalized not in {"sequential", "parallel"}:
            return False
        if self._running or self._queue_active:
            self.toast.emit("Stop the queue before changing its run mode.", "error")
            return False
        if normalized == self._queue_mode:
            return True
        self._queue_mode = normalized
        self.runQueueModeChanged.emit()
        return True

    @Slot(int, result=bool)
    def removeQueuedProfile(self, index: int) -> bool:
        if self._running or self._queue_active or not 0 <= index < len(self._run_queue):
            return False
        removed = self._run_queue.pop(index)
        self.runQueueChanged.emit()
        self.toast.emit(f"Removed {removed.profile_name} from the queue", "neutral")
        return True

    @Slot(int, int, result=bool)
    def moveQueuedProfile(self, index: int, delta: int) -> bool:
        target = int(index) + int(delta)
        if (
            self._running
            or self._queue_active
            or not 0 <= index < len(self._run_queue)
            or not 0 <= target < len(self._run_queue)
        ):
            return False
        session = self._run_queue.pop(index)
        self._run_queue.insert(target, session)
        self.runQueueChanged.emit()
        return True

    @Slot(result=bool)
    def clearRunQueue(self) -> bool:
        if self._running or self._queue_active:
            self.toast.emit("Stop the queue before clearing it.", "error")
            return False
        if not self._run_queue:
            return False
        self._run_queue.clear()
        self.runQueueChanged.emit()
        self.toast.emit("Run queue cleared", "neutral")
        return True

    def _prepare_run_target(
        self,
        actions: list[Action],
        action_indices: list[int],
        settings: RunSettings,
        preferred_hwnd: int = 0,
        remember_target: bool = False,
    ) -> int:
        mouse_kinds = {"left_click", "right_click", "double_click", "middle_click", "scroll", "drag"}
        expected_space = {
            "window": "window",
            "browser": "viewport",
        }.get(settings.target_mode, "screen")
        for sequence_index, action in enumerate(actions):
            if action.kind not in mouse_kinds or action.coordinate_space == expected_space:
                continue
            if action.use_current_pointer:
                # The click follows the live pointer, so it has no recorded
                # position that could belong to the wrong target.
                continue
            source_index = action_indices[sequence_index] if sequence_index < len(action_indices) else sequence_index
            destination = {
                "window": "the selected window",
                "viewport": "the selected browser tab",
            }.get(expected_space, "the desktop")
            raise ValueError(
                f"Step {source_index + 1} was recorded for a different target. "
                f"Open it and record its position again for {destination}."
            )
        if settings.target_mode == "desktop":
            return 0
        if settings.target_mode == "browser":
            # Fail here rather than inside the worker, so the queue can report it.
            self._resolve_browser_tab(settings)
            return 0
        if not self._window_selector(settings).selected:
            raise WindowTargetError("Choose a target window in Run settings before starting background mode.")
        return self._resolve_target_info(
            settings,
            preferred_hwnd=preferred_hwnd,
            remember=remember_target,
        ).hwnd

    def _validate_run_payload(
        self,
        actions: list[Action],
        action_indices: list[int],
        settings: RunSettings,
        reserved_shortcuts: set[str] | None = None,
        preferred_hwnd: int = 0,
        remember_target: bool = False,
    ) -> int:
        if not actions:
            raise ValueError("Add or enable at least one action before starting.")
        settings.validate()
        if reserved_shortcuts is None:
            reserved_shortcuts = canonical_global_shortcuts(
                (settings.start_hotkey, settings.capture_hotkey, settings.stop_hotkey)
            )
        for action in actions:
            action.validate(reserved_shortcuts)
        # Refuse combinations that run perfectly and deliver nothing -- an
        # unrecorded click, or window messages aimed at a browser.
        for failure in blocking_failures(self.runPreflight(actions, settings)):
            raise ValueError(
                f"{failure.detail} {failure.remedy}".strip()
                if failure.remedy
                else failure.detail
            )
        return self._prepare_run_target(
            actions,
            action_indices,
            settings,
            preferred_hwnd=preferred_hwnd,
            remember_target=remember_target,
        )

    def runPreflight(
        self, actions: list[Action] | None = None, settings: RunSettings | None = None
    ) -> list[Check]:
        chosen = settings or self._run_settings
        sequence = actions if actions is not None else [a for a in self.actions if a.enabled]

        def resolve_window():
            return self._resolve_target_info(chosen, remember=False)

        def resolve_tab():
            return self._resolve_browser_tab(chosen)

        return preflight(
            sequence,
            chosen,
            resolve_window=resolve_window if chosen.target_mode == "window" else None,
            resolve_tab=resolve_tab if chosen.target_mode == "browser" else None,
        )

    @Property("QVariantList", notify=ControllerSignals.preflightChanged)
    def preflightChecks(self) -> list[dict[str, str]]:
        try:
            return [check.as_entry() for check in self.runPreflight()]
        except Exception as exc:  # a probe must never break the UI
            return [{"name": "Target", "status": "fail", "detail": str(exc), "remedy": ""}]

    @Property(bool, notify=ControllerSignals.preflightChanged)
    def preflightBlocked(self) -> bool:
        return any(check.get("status") == "fail" for check in self.preflightChecks)

    @Property(str, notify=ControllerSignals.preflightChanged)
    def preflightSummary(self) -> str:
        for check in self.preflightChecks:
            if check.get("status") == "fail":
                return check.get("detail", "This sequence cannot run yet.")
        return ""

    @Slot(result=bool)
    def refreshPreflight(self) -> bool:
        self.preflightChanged.emit()
        return True


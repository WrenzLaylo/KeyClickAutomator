"""Executing a run: starting sessions and the workers that drive them."""
from __future__ import annotations

import copy
import os
import threading
from pathlib import Path
from typing import Any

import pyautogui
from PySide6.QtCore import Property, QStandardPaths, Slot
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


class RunningMixin(ControllerSignals):
    """Starting, pausing, and stopping runs. Reporting on them is ProgressMixin."""

    def _queue_reserved_shortcuts(self) -> set[str]:
        return self._reserved_shortcuts() | {"f9"}

    def _session_is_queued(self, session: RunSession) -> bool:
        return any(queued is session for queued in self._run_queue)

    def _session_by_id(self, session_id: str) -> RunSession | None:
        if self._active_session is not None and self._active_session.session_id == session_id:
            return self._active_session
        return self._parallel_sessions.get(session_id)

    def _mark_queue_ui_dirty(self) -> None:
        """Request a queue repaint from the run hot path, at most ~14 times a second."""
        self._queue_ui_dirty = True
        if not self._queue_ui_timer.isActive():
            self._queue_ui_timer.start()

    def _flush_queue_ui(self) -> None:
        if not self._queue_ui_dirty:
            return
        self._queue_ui_dirty = False
        self.runQueueChanged.emit()
        if self._parallel_sessions:
            self._update_parallel_status()

    def _is_parallel_session(self, session: RunSession) -> bool:
        """Report how this session actually runs, not which mode is selected.

        ``_queue_mode`` is a preference that survives while the app is idle, so a
        plain single run can happen with "parallel" still chosen.  Only sessions
        registered in ``_parallel_sessions`` share the aggregate status line.
        """
        return session.session_id in self._parallel_sessions

    def _start_session(self, session: RunSession, parallel: bool = False) -> bool:
        if parallel:
            if self._active_session is not None or session.session_id in self._parallel_sessions:
                return False
        elif self._active_session is not None or self._parallel_sessions:
            return False
        self.cancelPositionCapture(announce=False)
        self.cancelWindowPick(announce=False)
        session.stop_event.clear()
        session.pause_event.clear()
        session.state = "armed"
        session.status = "Armed"
        session.tone = "accent"
        session.progress = 0.0
        session.running_action_index = -1
        session.error = ""
        if parallel:
            self._parallel_sessions[session.session_id] = session
        else:
            self._active_session = session
        self._set_running_action_index(-1)
        self._set_running(True)
        if not parallel:
            self._set_status(
                f"{session.profile_name} · Armed" if self._queue_active else "Armed",
                "accent",
            )
            self._set_progress(0.0)
        session.worker = threading.Thread(
            target=self._run_worker,
            args=(session,),
            daemon=True,
        )
        if self._session_is_queued(session):
            self.runQueueChanged.emit()
        session.worker.start()
        return True

    def _begin_run(
        self,
        actions: list[Action],
        action_indices: list[int],
        settings: RunSettings,
        completion_message: str,
        status_verb: str = "Running",
    ) -> bool:
        if self._running or self._queue_active:
            return False
        try:
            target_hwnd = self._validate_run_payload(
                actions,
                action_indices,
                settings,
                preferred_hwnd=self._target_hwnd,
                remember_target=True,
            )
        except (ValueError, WindowTargetError) as exc:
            self.toast.emit(str(exc), "error")
            return False
        session = RunSession(
            profile_name=self._current_profile_name,
            profile_path=self._current_profile_path or "",
            actions=copy.deepcopy(actions),
            action_indices=list(action_indices),
            settings=copy.deepcopy(settings),
            completion_message=completion_message,
            status_verb=status_verb,
            target_hwnd=target_hwnd,
            reserved_shortcuts=canonical_global_shortcuts(
                (settings.start_hotkey, settings.capture_hotkey, settings.stop_hotkey)
            ),
        )
        return self._start_session(session)

    def _run_from_index(self, index: int = 0) -> bool:
        index = max(0, int(index))
        indexed_actions = [
            (action_index, copy.deepcopy(action))
            for action_index, action in enumerate(self.actions[index:], start=index)
            if action.enabled
        ]
        return self._begin_run(
            [action for _, action in indexed_actions],
            [action_index for action_index, _ in indexed_actions],
            copy.deepcopy(self._run_settings),
            "Run complete" if index == 0 else f"Run from step {index + 1} complete",
        )

    @Slot()
    def startRun(self) -> None:
        if self._run_settings_pending:
            self.toast.emit("Apply the edited Run settings before using the global Start shortcut.", "error")
            return
        self._run_from_index(0)

    @Slot(result=bool)
    def startRunQueue(self) -> bool:
        if self._running or self._queue_active:
            self.toast.emit("A run is already active.", "error")
            return False
        if not self._run_queue:
            self.toast.emit("Add at least one saved profile to the run queue.", "error")
            return False
        if self._queue_mode == "parallel" and len(self._run_queue) < 2:
            self.toast.emit("Parallel mode needs at least two background-window profiles.", "error")
            return False
        if self._queue_mode == "parallel" and len(self._run_queue) > MAX_PARALLEL_SESSIONS:
            self.toast.emit(
                f"Parallel mode can run up to {MAX_PARALLEL_SESSIONS} profiles at once.",
                "error",
            )
            return False

        problem: tuple[RunSession, str] | None = None
        reserved_shortcuts = self._queue_reserved_shortcuts()
        resolved_targets: dict[tuple[str, Any], list[RunSession]] = {}
        for index, session in enumerate(self._run_queue):
            try:
                self._load_profile_session(session.profile_path, existing=session)
                if (
                    self._queue_mode == "sequential"
                    and session.settings.repeat_forever
                    and index < len(self._run_queue) - 1
                ):
                    raise ValueError(
                        "This profile repeats forever, so nothing below it would "
                        "ever start. Move it to the end of the queue, turn off "
                        "Repeat forever, or switch to Parallel to run these "
                        "profiles at the same time."
                    )
                if self._queue_mode == "parallel" and session.settings.target_mode == "desktop":
                    raise ValueError(
                        "Parallel mode supports background-window and browser-tab "
                        "profiles only, because Desktop profiles share one pointer."
                    )
                session.target_hwnd = self._validate_run_payload(
                    session.actions,
                    session.action_indices,
                    session.settings,
                    reserved_shortcuts=reserved_shortcuts,
                )
                session.reserved_shortcuts = set(reserved_shortcuts)
                if self._queue_mode == "parallel":
                    if session.settings.target_mode == "browser":
                        # Two profiles driving one tab would interleave their clicks.
                        key = ("tab", session.settings.target_tab_url)
                    else:
                        self._get_window_service().ensure_responsive(session.target_hwnd)
                        key = ("window", session.target_hwnd)
                    resolved_targets.setdefault(key, []).append(session)
            except (OSError, ValueError, TypeError, WindowTargetError) as exc:
                session.state = "error"
                session.status = "Needs attention"
                session.tone = "danger"
                session.error = str(exc)
                problem = problem or (session, str(exc))

        if self._queue_mode == "parallel":
            for sessions in resolved_targets.values():
                if len(sessions) < 2:
                    continue
                names = " and ".join(session.profile_name for session in sessions[:2])
                noun = "browser tab" if sessions[0].settings.target_mode == "browser" else "target window"
                message = (
                    f"{names} resolve to the same {noun}. "
                    f"Choose a different {noun} for one profile."
                )
                for session in sessions:
                    session.state = "error"
                    session.status = "Target conflict"
                    session.tone = "danger"
                    session.error = message
                problem = problem or (sessions[0], message)

        self.runQueueChanged.emit()
        if problem is not None:
            session, message = problem
            self._set_status("Queue needs attention", "danger")
            self.toast.emit(f"{session.profile_name}: {message}", "error")
            return False

        if self._hotkeys_enabled and not self._install_hotkeys(
            self._run_settings,
            queue_stop=True,
        ):
            self._set_status("Queue could not start", "danger")
            return False

        self.cancelPositionCapture(announce=False)
        self.cancelWindowPick(announce=False)
        self._queue_stop_requested = False
        self._queue_active = True
        self.runQueueRunningChanged.emit()
        self._set_running(True)
        self._set_status("Starting queue", "accent")
        self._set_progress(0.0)
        if self._queue_mode == "parallel":
            return self._start_parallel_queue()
        return self._start_next_queued_session()

    @Slot("QVariantMap", result=bool)
    def startRunWithSettings(self, data: dict[str, Any]) -> bool:
        if not self._apply_run_settings(data, announce=False):
            return False
        return self._run_from_index(0)

    @Slot(int, "QVariantMap", result=bool)
    def startRunFromWithSettings(self, index: int, data: dict[str, Any]) -> bool:
        if not 0 <= index < len(self.actions):
            self.toast.emit("Select an action to choose where the run begins.", "error")
            return False
        if not self._apply_run_settings(data, announce=False):
            return False
        return self._run_from_index(index)

    @Slot(int, "QVariantMap", result=bool)
    def testActionWithSettings(self, index: int, data: dict[str, Any]) -> bool:
        if not 0 <= index < len(self.actions):
            self.toast.emit("Select an action to test.", "error")
            return False
        if not self._apply_run_settings(data, announce=False):
            return False
        action = copy.deepcopy(self.actions[index])
        action.enabled = True
        action.repeats = 1
        action.delay_after = 0
        settings = copy.deepcopy(self._run_settings)
        settings.repeat_count = 1
        settings.repeat_forever = False
        settings.start_delay = 3.0
        settings.cycle_interval = 0
        settings.delay_jitter = 0
        return self._begin_run(
            [action],
            [index],
            settings,
            "Action test complete",
            status_verb="Testing",
        )

    @Slot()
    def _toggle_run(self) -> None:
        if self._running:
            self.stopRun()
        else:
            self.startRun()

    def queueStartToggle(self) -> None:
        """Thread-safe entry point used by pynput's listener thread."""
        self.hotkeyToggleRequested.emit()

    def queueCapture(self) -> None:
        self.hotkeyCaptureRequested.emit()

    def queueStop(self) -> None:
        self.hotkeyStopRequested.emit()

    def _start_parallel_queue(self) -> bool:
        # Every session starts: startRunQueue reloads each one, which resets its
        # state to "queued", bails out if any of them failed to load, and only
        # gets here with nothing else running. There is no "none of them
        # started" case left to recover from.
        if not self._queue_active or self._queue_mode != "parallel":
            return False
        for session in self._run_queue:
            if session.state == "queued":
                self._start_session(session, parallel=True)
        self._update_parallel_status()
        return True


    def _start_next_queued_session(self) -> bool:
        if (
            not self._queue_active
            or self._queue_mode != "sequential"
            or self._active_session is not None
        ):
            return False
        session = next(
            (candidate for candidate in self._run_queue if candidate.state == "queued"),
            None,
        )
        if session is None:
            stopped = self._queue_stop_requested
            self._queue_active = False
            self.runQueueRunningChanged.emit()
            self._set_running(False)
            self._set_status(
                "Queue stopped" if stopped else "Queue complete",
                "danger" if stopped else "success",
            )
            self._set_progress(0.0 if stopped else 1.0)
            self.toast.emit(
                "Queue stopped safely"
                if stopped
                else f"Queue complete · {len(self._run_queue)} profiles",
                "neutral" if stopped else "success",
            )
            self._queue_stop_requested = False
            self._restore_standard_hotkeys()
            return True
        return self._start_session(session)


    def _run_worker(self, session: RunSession) -> None:
        browser_backend: ChromeTabBackend | None = None
        try:
            if session.settings.target_mode == "browser":
                browser_backend = ChromeTabBackend(self._resolve_browser_tab(session.settings))
                browser_backend.begin_verification()
                backend = browser_backend
            elif session.settings.target_mode == "window":
                backend = WindowMessageBackend(session.target_hwnd, self._get_window_service())
            else:
                backend = pyautogui
            complete = AutomationRunner(backend).run(
                session.actions,
                session.settings,
                session.stop_event,
                lambda phase, current, total: self.progressFromWorker.emit(
                    session.session_id,
                    phase,
                    current,
                    total,
                ),
                session.pause_event,
                session.reserved_shortcuts or None,
            )
            base = session.completion_message if complete else "Stopped safely"
            self.finishedFromWorker.emit(
                session.session_id,
                complete,
                self._delivery_report(base, browser_backend),
            )
        except pyautogui.FailSafeException:
            self.finishedFromWorker.emit(
                session.session_id,
                False,
                "Stopped by corner fail-safe",
            )
        except Exception as exc:
            self.finishedFromWorker.emit(
                session.session_id,
                False,
                f"Automation error: {exc}",
            )
        finally:
            # The debugger socket is per-run; leaving it open pins the tab.
            if browser_backend is not None:
                browser_backend.close()

    @Slot()
    def stopRun(self) -> None:
        if self._queue_active:
            self.stopAllRuns()
            return
        session = self._active_session
        if session is None:
            return
        session.stop_event.set()
        session.state = "stopping"
        session.status = "Stopping"
        session.tone = "danger"
        self._set_status("Stopping", "danger")

    @Slot(str, result=bool)
    def stopRunSession(self, session_id: str) -> bool:
        session = self._session_by_id(str(session_id))
        if session is None or session.state not in {"armed", "running", "paused"}:
            return False
        session.stop_requested_by_user = True
        session.pause_event.clear()
        session.stop_event.set()
        session.state = "stopping"
        session.status = "Stopping"
        session.tone = "danger"
        self.runQueueChanged.emit()
        if self._is_parallel_session(session):
            self._update_parallel_status()
        else:
            self._set_status(f"Stopping {session.profile_name}", "danger")
        return True

    @Slot(str, result=bool)
    def toggleRunSessionPaused(self, session_id: str) -> bool:
        session = self._session_by_id(str(session_id))
        if session is None or session.state not in {"armed", "running", "paused"}:
            return False
        if session.pause_event.is_set():
            session.pause_event.clear()
            session.state = "running"
            session.status = "Resuming"
            session.tone = "success"
        else:
            session.pause_event.set()
            session.state = "paused"
            session.status = "Paused"
            session.tone = "accent"
        self.runQueueChanged.emit()
        if self._is_parallel_session(session):
            self._update_parallel_status()
        else:
            self._set_status(
                f"{session.profile_name} · {session.status}",
                session.tone,
            )
        return True

    @Slot()
    def stopAllRuns(self) -> None:
        if not self._queue_active:
            self.stopRun()
            return
        self._queue_stop_requested = True
        for session in self._run_queue:
            if session.state == "queued":
                session.state = "cancelled"
                session.status = "Not run"
                session.tone = "neutral"
        active_sessions = list(self._parallel_sessions.values())
        if self._active_session is not None:
            active_sessions.append(self._active_session)
        for session in active_sessions:
            session.pause_event.clear()
            session.stop_event.set()
            session.state = "stopping"
            session.status = "Stopping"
            session.tone = "danger"
        self._set_status("Stopping queue", "danger")
        self.runQueueChanged.emit()



"""Executing a run: sessions, workers, progress, and completion."""
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

class RunningMixin(ControllerSignals):
    """Starting, pausing, stopping, and reporting on runs."""

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

    def _update_parallel_status(self) -> None:
        active = len(self._parallel_sessions)
        paused = sum(session.pause_event.is_set() for session in self._parallel_sessions.values())
        if active == 0:
            return
        if paused == active:
            self._set_status(f"{active} profiles paused", "accent")
        elif paused:
            self._set_status(f"{active - paused} running · {paused} paused", "success")
        else:
            self._set_status(
                f"{active} profile{'s' if active != 1 else ''} running in parallel",
                "success",
            )

        progress_values = []
        indefinite = False
        for session in self._run_queue:
            if session.state == "complete":
                progress_values.append(1.0)
            elif session.state in {"armed", "running", "paused", "stopping"}:
                if session.progress < 0:
                    indefinite = True
                else:
                    progress_values.append(max(0.0, min(1.0, session.progress)))
            elif session.state in {"error", "stopped", "cancelled"}:
                progress_values.append(0.0)
        self._set_progress(
            -1.0
            if indefinite
            else sum(progress_values) / max(1, len(self._run_queue))
        )

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

    @staticmethod
    def _delivery_report(message: str, backend: ChromeTabBackend | None) -> str:
        """Say what actually landed, not just that the loop finished."""
        if backend is None:
            return message
        sent = backend.delivered_input
        if not sent:
            return message
        confirmed = backend.confirmed_input()
        if confirmed is None:
            return f"{message} · {sent} sent"
        if confirmed == 0:
            return (
                f"{message} · {sent} sent, but the page received none of them. "
                "Check the recorded position is still over the right element."
            )
        where = ""
        target = getattr(backend, "confirmed_target", lambda: "")()
        if target:
            where = f" on {target}"
        if confirmed < sent:
            return f"{message} · {sent} sent, {confirmed} received by the page{where}"
        return f"{message} · {sent} confirmed{where}"

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

    @Slot(str, str, int, int)
    def _handle_progress(
        self,
        session_id: str,
        phase: str,
        current: int,
        total: int,
    ) -> None:
        session = self._session_by_id(session_id)
        if session is None:
            return
        parallel_session = self._is_parallel_session(session)
        if session.stop_event.is_set() or session.state == "stopping":
            session.state = "stopping"
            session.status = "Stopping"
            session.tone = "danger"
            if self._session_is_queued(session):
                self._mark_queue_ui_dirty()
            return
        if session.pause_event.is_set():
            session.state = "paused"
            session.status = "Paused"
            session.tone = "accent"
            if self._session_is_queued(session):
                self._mark_queue_ui_dirty()
            if parallel_session:
                self._update_parallel_status()
            return
        if phase == "timer":
            session.state = "armed"
            session.status = "Countdown"
            session.tone = "accent"
            session.progress = 0.0
            if not parallel_session:
                self._set_status(
                    f"{session.profile_name} · Countdown" if self._queue_active else "Countdown",
                    "accent",
                )
                self._set_progress(0.0)
        elif phase == "action":
            if 0 <= current < len(session.action_indices):
                source_index = session.action_indices[current]
                session.state = "running"
                session.status = f"Step {source_index + 1}"
                session.tone = "success"
                session.running_action_index = source_index
                same_profile = bool(
                    session.profile_path
                    and self._current_profile_path
                    and self._path_key(session.profile_path)
                    == self._path_key(self._current_profile_path)
                )
                self._set_running_action_index(
                    source_index
                    if not self._queue_active
                    or (not parallel_session and same_profile)
                    else -1
                )
                status = f"{session.status_verb} step {source_index + 1}"
                if self._queue_active and not parallel_session:
                    status = f"{session.profile_name} · {status}"
                if not parallel_session:
                    self._set_status(status, "success")
        else:
            session.state = "running"
            session.status = "Running" if total == 0 else f"Cycle {current} of {total}"
            session.tone = "success"
            session.progress = -1.0 if total == 0 else current / total
            if not parallel_session:
                status = session.status_verb
                if self._queue_active:
                    status = f"{session.profile_name} · {session.status}"
                self._set_status(status, "success")
                self._set_progress(session.progress)
        if self._session_is_queued(session):
            self._mark_queue_ui_dirty()
        elif parallel_session:
            self._update_parallel_status()

    @Slot(str, bool, str)
    def _finish_run(self, session_id: str, complete: bool, message: str) -> None:
        session = self._session_by_id(session_id)
        if session is None:
            return
        parallel_session = self._is_parallel_session(session)
        queued_session = self._queue_active and self._session_is_queued(session)
        failed = message.startswith("Automation error:")
        session.worker = None
        session.pause_event.clear()
        session.running_action_index = -1
        session.progress = 1.0 if complete else 0.0
        if complete:
            session.state = "complete"
            session.status = "Complete"
            session.tone = "success"
        elif failed:
            session.state = "error"
            session.status = "Error"
            session.tone = "danger"
            session.error = message.removeprefix("Automation error:").strip()
        else:
            session.state = "stopped"
            session.status = "Stopped"
            session.tone = "danger"
        self._set_running_action_index(-1)
        if parallel_session:
            self._parallel_sessions.pop(session_id, None)
        elif self._active_session is session:
            self._active_session = None

        if queued_session and parallel_session:
            self.runQueueChanged.emit()
            if failed:
                self.toast.emit(f"{session.profile_name}: {message}", "error")
            if self._parallel_sessions:
                self._update_parallel_status()
                return

            self._queue_active = False
            self.runQueueRunningChanged.emit()
            self._set_running(False)
            errors = sum(candidate.state == "error" for candidate in self._run_queue)
            stopped = sum(candidate.state == "stopped" for candidate in self._run_queue)
            if self._queue_stop_requested:
                self._set_status("Parallel run stopped", "danger")
                self._set_progress(0.0)
                self.toast.emit("All parallel profiles stopped safely", "neutral")
            elif errors:
                self._set_status(
                    f"Parallel run finished with {errors} error{'s' if errors != 1 else ''}",
                    "danger",
                )
                self._set_progress(0.0)
            elif stopped:
                self._set_status(
                    f"Parallel run complete · {stopped} stopped",
                    "accent",
                )
                self._set_progress(1.0)
                self.toast.emit("Parallel run finished", "neutral")
            else:
                self._set_status("Parallel run complete", "success")
                self._set_progress(1.0)
                self.toast.emit(
                    f"Parallel run complete · {len(self._run_queue)} profiles",
                    "success",
                )
            self._queue_stop_requested = False
            self._restore_standard_hotkeys()
            return

        if queued_session:
            self.runQueueChanged.emit()
            next_session = next(
                (candidate for candidate in self._run_queue if candidate.state == "queued"),
                None,
            )
            if complete and not self._queue_stop_requested and next_session is not None:
                self._set_status(f"{session.profile_name} complete", "success")
                QTimer.singleShot(0, self._start_next_queued_session)
                return
            if (
                not complete
                and not failed
                and session.stop_requested_by_user
                and not self._queue_stop_requested
                and next_session is not None
            ):
                self._set_status(f"{session.profile_name} stopped · Continuing queue", "accent")
                QTimer.singleShot(0, self._start_next_queued_session)
                return

            if not complete:
                for pending in self._run_queue:
                    if pending.state == "queued":
                        pending.state = "cancelled"
                        pending.status = "Not run"
                        pending.tone = "neutral"
                self.runQueueChanged.emit()

            self._queue_active = False
            self.runQueueRunningChanged.emit()
            self._set_running(False)
            stopped_count = sum(
                candidate.state == "stopped" for candidate in self._run_queue
            )
            if complete:
                self._set_status(
                    f"Queue complete · {stopped_count} stopped"
                    if stopped_count
                    else "Queue complete",
                    "accent" if stopped_count else "success",
                )
                self._set_progress(1.0)
                self.toast.emit(
                    "Queue finished"
                    if stopped_count
                    else f"Queue complete · {len(self._run_queue)} profiles",
                    "neutral" if stopped_count else "success",
                )
            elif failed:
                self._set_status("Queue error", "danger")
                self._set_progress(0.0)
                self.toast.emit(f"{session.profile_name}: {message}", "error")
            elif session.stop_requested_by_user and not self._queue_stop_requested:
                self._set_status(
                    f"Queue complete · {max(1, stopped_count)} stopped",
                    "accent",
                )
                self._set_progress(1.0)
                self.toast.emit("Queue finished", "neutral")
            else:
                self._set_status("Queue stopped", "danger")
                self._set_progress(0.0)
                self.toast.emit("Queue stopped safely", "neutral")
            self._queue_stop_requested = False
            self._restore_standard_hotkeys()
            return

        self._set_running(False)
        self._set_status(
            "Complete" if complete else "Error" if failed else "Stopped",
            "success" if complete else "danger",
        )
        self._set_progress(1.0 if complete else 0.0)
        self.toast.emit(
            message,
            "success" if complete else "error" if failed else "neutral",
        )

    def _set_running(self, value: bool) -> None:
        if self._running != value:
            self._running = value
            self.runningChanged.emit()

    def _set_status(self, text: str, tone: str) -> None:
        self._status, self._status_tone = text, tone
        self.statusChanged.emit()

    def _set_progress(self, value: float) -> None:
        self._progress = value
        self.progressChanged.emit()


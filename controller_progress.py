"""Reporting a run: what it is doing now, and what it did when it stopped."""
from __future__ import annotations

from PySide6.QtCore import QTimer, Slot

from chrome_backend import ChromeTabBackend
from controller_signals import ControllerSignals


class ProgressMixin(ControllerSignals):
    """Status, progress, and the completion report.

    Split from RunningMixin because starting a session and describing one are
    different jobs: everything here runs after the worker is already going,
    and most of it exists to say what actually landed rather than that the
    loop finished.
    """

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

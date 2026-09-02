from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from pynput import keyboard
from PySide6.QtCore import (
    QFileSystemWatcher,
    QObject,
    Property,
    QStandardPaths,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtWidgets import QFileDialog

from capture_overlay import PositionCaptureOverlay
from engine import (
    Action,
    AutomationRunner,
    RunSettings,
    canonical_global_shortcuts,
    load_profile,
    save_profile,
)
from profile_catalog import (
    default_profile_directory,
    list_profile_entries,
    normalize_path,
    profile_name,
)
from recovery_store import (
    describe_recovery_draft,
    read_recovery_payload,
    remove_recovery_draft,
    write_recovery_draft,
)
from chrome_backend import DEFAULT_PORT as BROWSER_PORT
from preflight import Check, blocking_failures, preflight
from profile_history import restore as restore_version, snapshot, versions
from controller_actions import ActionListModel, ActionsMixin
from controller_capture import CaptureMixin
from controller_signals import ControllerSignals
from controller_profiles import ProfilesMixin
from controller_queue import QueueMixin
from controller_running import MAX_PARALLEL_SESSIONS, RunningMixin
from controller_targeting import TargetingMixin
from run_session import RunSession
from shortcut_service import global_shortcut_conflicts, pynput_hotkey
from window_backend import WindowInfo, WindowMessageBackend


APP_VERSION = "3.5.0"


class AutomatorController(
    ActionsMixin,
    TargetingMixin,
    QueueMixin,
    RunningMixin,
    CaptureMixin,
    ProfilesMixin,
    QObject,
):

    def __init__(
        self,
        start_hotkeys: bool = True,
        recovery_path: str | Path | None = None,
        enable_recovery: bool | None = None,
        window_service: Any | None = None,
        profile_directory: str | Path | None = None,
    ) -> None:
        super().__init__()
        self.actions: list[Action] = []
        self._model = ActionListModel(self)
        self._selected_index = -1
        self._running = False
        self._status = "Ready"
        self._status_tone = "neutral"
        self._progress = 0.0
        self._running_action_index = -1
        self._active_session: RunSession | None = None
        self._parallel_sessions: dict[str, RunSession] = {}
        self._run_queue: list[RunSession] = []
        self._queue_mode = "sequential"
        self._queue_active = False
        self._queue_stop_requested = False
        # A zero-delay run reports progress ~44 times a second per profile. Emitting a
        # full model reset for each one rebuilds every queue card on the UI thread and
        # makes the window stutter, so repaints are coalesced onto this timer.
        self._browser_tabs: list[dict[str, Any]] = []
        self._browser_capture_thread: threading.Thread | None = None
        self._browser_ready = False
        self._queue_ui_dirty = False
        self._queue_ui_timer = QTimer(self)
        self._queue_ui_timer.setSingleShot(True)
        self._queue_ui_timer.setInterval(70)
        self._queue_ui_timer.timeout.connect(self._flush_queue_ui)
        self._listener: keyboard.GlobalHotKeys | None = None
        self._capture_listener: keyboard.Listener | None = None
        self._action_capture_mode = ""
        self._run_settings = RunSettings()
        self._run_settings_pending = False
        self._current_profile_name = "Untitled sequence"
        self._current_profile_path: str | None = None
        self._profile_directory = normalize_path(
            profile_directory or default_profile_directory()
        )
        self._profile_entries: list[dict[str, Any]] = []
        self._profile_watcher = QFileSystemWatcher(self)
        self._profile_watcher.directoryChanged.connect(
            lambda _path: self.refreshProfiles()
        )
        if Path(self._profile_directory).is_dir():
            self._profile_watcher.addPath(self._profile_directory)
        self.refreshProfiles()
        self._dirty = False
        self._undo_deleted: tuple[int, Action] | None = None
        self._capture_target = -1
        self._capture_countdown = 0
        self._capture_overlay = PositionCaptureOverlay(self)
        self._capture_overlay.selected.connect(self._capture_overlay_selected)
        self._capture_overlay.cancelled.connect(self.cancelPositionCapture)
        self._capture_overlay.failed.connect(self._capture_overlay_failed)
        self._window_service = window_service
        self._target_hwnd = 0
        self._window_pick_countdown = 0
        self._window_entries: list[dict[str, Any]] = []
        self._window_candidates: dict[int, WindowInfo] = {}
        self._desktop_preview_url = ""
        self._recovery_enabled = start_hotkeys if enable_recovery is None else bool(enable_recovery)
        default_recovery_root = Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))
        self._recovery_path = Path(recovery_path) if recovery_path else default_recovery_root / "recovery-draft.kca.json"
        self._draft_available = self._recovery_enabled and self._recovery_path.is_file()
        self._draft_summary = self._describe_draft() if self._draft_available else ""
        self._hotkeys_enabled = start_hotkeys
        # The checklist is only useful if it tracks what the user just changed.
        for signal in (
            self.windowEntriesChanged,
            self.browserTabsChanged,
        ):
            signal.connect(self.targetsChanged)
        self.targetsChanged.connect(self.preflightChanged)
        for signal in (
            self.actionsChanged,
            self.targetSettingsChanged,
            self.runSettingsChanged,
            self.browserTabsChanged,
        ):
            signal.connect(self.preflightChanged)
        self.progressFromWorker.connect(self._handle_progress)
        self.finishedFromWorker.connect(self._finish_run)
        self.browserPointCaptured.connect(self._finish_browser_point_capture)
        self.hotkeyToggleRequested.connect(self._toggle_run)
        self.hotkeyCaptureRequested.connect(lambda: self.startPositionCapture(0))
        self.hotkeyStopRequested.connect(self.stopRun)
        self.actionKeyCaptured.connect(self._on_action_key_captured)
        self.actionHotkeyCaptured.connect(self._on_action_hotkey_captured)
        self.shortcutCaptured.connect(self._on_shortcut_captured)
        if start_hotkeys:
            self._restart_hotkeys()


    @Property(str, notify=ControllerSignals.currentProfileNameChanged)
    def currentProfileName(self) -> str:
        return self._current_profile_name

    @Property(str, notify=ControllerSignals.currentProfilePathChanged)
    def currentProfilePath(self) -> str:
        return self._current_profile_path or ""

    @Property(str, notify=ControllerSignals.profileDirectoryChanged)
    def profileDirectory(self) -> str:
        return self._profile_directory

    @Property("QVariantList", notify=ControllerSignals.profileEntriesChanged)
    def profileEntries(self) -> list[dict[str, Any]]:
        return self._profile_entries

    @Property("QVariantList", notify=ControllerSignals.runQueueChanged)
    def runQueueEntries(self) -> list[dict[str, Any]]:
        total = len(self._run_queue)
        return [
            session.as_entry(index + 1, total)
            for index, session in enumerate(self._run_queue)
        ]

    @Property("QVariantList", notify=ControllerSignals.runQueueChanged)
    def runQueuePaths(self) -> list[str]:
        return [session.profile_path for session in self._run_queue]

    @Property(int, notify=ControllerSignals.runQueueChanged)
    def runQueueCount(self) -> int:
        return len(self._run_queue)

    @Property(bool, notify=ControllerSignals.runQueueRunningChanged)
    def runQueueRunning(self) -> bool:
        return self._queue_active

    @Property(str, notify=ControllerSignals.runQueueModeChanged)
    def runQueueMode(self) -> str:
        return self._queue_mode

    @Slot()
    def refreshProfiles(self) -> None:
        entries = list_profile_entries(self._profile_directory)
        if entries != self._profile_entries:
            self._profile_entries = entries
            self.profileEntriesChanged.emit()

    def _set_profile_directory(self, path: str | Path) -> bool:
        normalized = normalize_path(path)
        if not Path(normalized).is_dir():
            self.toast.emit("That profile folder is no longer available.", "error")
            return False
        if normalized == self._profile_directory:
            self.refreshProfiles()
            return True
        watched = self._profile_watcher.directories()
        if watched:
            self._profile_watcher.removePaths(watched)
        self._profile_directory = normalized
        self._profile_watcher.addPath(normalized)
        self.profileDirectoryChanged.emit()
        self.refreshProfiles()
        return True

    @Slot(str, result=bool)
    def setProfileDirectory(self, path: str) -> bool:
        if not self._set_profile_directory(path):
            return False
        self.toast.emit(f"Profile folder: {Path(path).name}", "success")
        return True

    @Slot(result=bool)
    def chooseProfileFolder(self) -> bool:
        path = QFileDialog.getExistingDirectory(
            None,
            "Choose KeyClick profile folder",
            self._profile_directory,
            QFileDialog.ShowDirsOnly,
        )
        return bool(path) and self.setProfileDirectory(path)

    def _set_current_profile(self, path: str | None) -> None:
        normalized = normalize_path(path) if path else None
        if normalized != self._current_profile_path:
            self._current_profile_path = normalized
            self.currentProfilePathChanged.emit()
        name = profile_name(normalized) if normalized else ""
        name = name or "Untitled sequence"
        if name != self._current_profile_name:
            self._current_profile_name = name
            self.currentProfileNameChanged.emit()

    @Property(bool, notify=ControllerSignals.dirtyChanged)
    def dirty(self) -> bool:
        return self._dirty

    @Property(bool, constant=True)
    def recoveryEnabled(self) -> bool:
        return self._recovery_enabled

    @Property(bool, notify=ControllerSignals.draftAvailableChanged)
    def draftAvailable(self) -> bool:
        return self._draft_available

    @Property(str, notify=ControllerSignals.draftAvailableChanged)
    def draftSummary(self) -> str:
        return self._draft_summary

    @Property(bool, notify=ControllerSignals.undoChanged)
    def canUndo(self) -> bool:
        return self._undo_deleted is not None

    @Property(bool, notify=ControllerSignals.runSettingsPendingChanged)
    def runSettingsPending(self) -> bool:
        return self._run_settings_pending

    @Property(bool, notify=ControllerSignals.captureStateChanged)
    def capturePending(self) -> bool:
        return self._capture_target >= 0

    @Property(int, notify=ControllerSignals.captureStateChanged)
    def captureCountdown(self) -> int:
        return self._capture_countdown

    @Property(int, notify=ControllerSignals.captureStateChanged)
    def captureTarget(self) -> int:
        return self._capture_target

    @Property(str, notify=ControllerSignals.actionCaptureStateChanged)
    def actionCaptureMode(self) -> str:
        return self._action_capture_mode


    @Property(int, notify=ControllerSignals.runningActionIndexChanged)
    def runningActionIndex(self) -> int:
        return self._running_action_index

    def _describe_draft(self) -> str:
        return describe_recovery_draft(self._recovery_path)

    def _set_draft_available(self, value: bool) -> None:
        value = bool(value)
        summary = self._describe_draft() if value else ""
        if value != self._draft_available or summary != self._draft_summary:
            self._draft_available = value
            self._draft_summary = summary
            self.draftAvailableChanged.emit()

    def _write_recovery_draft(self) -> None:
        if not self._recovery_enabled:
            return
        try:
            write_recovery_draft(
                self._recovery_path,
                self.actions,
                self._run_settings,
                self._current_profile_name,
                self._current_profile_path,
            )
            self._set_draft_available(True)
        except OSError as exc:
            self.toast.emit(f"Recovery copy could not be saved: {exc}", "error")

    def _remove_recovery_draft(self) -> None:
        if not self._recovery_enabled:
            return
        try:
            remove_recovery_draft(self._recovery_path)
            self._set_draft_available(False)
        except OSError as exc:
            self.toast.emit(f"Recovery copy could not be removed: {exc}", "error")

    def _set_dirty(self, value: bool) -> None:
        value = bool(value)
        changed = value != self._dirty
        self._dirty = value
        if changed:
            self.dirtyChanged.emit()
        if value:
            self._write_recovery_draft()
        else:
            self._remove_recovery_draft()

    def _clear_undo(self) -> None:
        if self._undo_deleted is not None:
            self._undo_deleted = None
            self.undoChanged.emit()

    def _set_run_settings_pending(self, value: bool) -> None:
        value = bool(value)
        if value != self._run_settings_pending:
            self._run_settings_pending = value
            self.runSettingsPendingChanged.emit()

    def _set_running_action_index(self, value: int) -> None:
        value = int(value)
        if value != self._running_action_index:
            self._running_action_index = value
            self.runningActionIndexChanged.emit()


    @Property(bool, notify=ControllerSignals.runningChanged)
    def running(self) -> bool:
        return self._running

    @Property(str, notify=ControllerSignals.statusChanged)
    def status(self) -> str:
        return self._status

    @Property(str, notify=ControllerSignals.statusChanged)
    def statusTone(self) -> str:
        return self._status_tone

    @Property(float, notify=ControllerSignals.progressChanged)
    def progress(self) -> float:
        return self._progress


    @Property("QVariantMap", notify=ControllerSignals.runSettingsChanged)
    def runSettings(self) -> dict[str, Any]:
        s = self._run_settings
        return {
            "repeatCount": s.repeat_count,
            "repeatForever": s.repeat_forever,
            "startDelay": s.start_delay,
            "cycleInterval": s.cycle_interval,
            "textInterval": s.text_key_interval,
            "jitter": s.delay_jitter,
            "startHotkey": s.start_hotkey,
            "captureHotkey": s.capture_hotkey,
            "stopHotkey": s.stop_hotkey,
        }


    def _apply_run_settings(self, data: dict[str, Any], announce: bool = True) -> bool:
        if self._running:
            self.toast.emit("Stop the current run before changing Run settings.", "error")
            return False
        current = self._run_settings
        try:
            settings = RunSettings(
                repeat_count=int(data.get("repeatCount", current.repeat_count)),
                repeat_forever=bool(data.get("repeatForever", current.repeat_forever)),
                start_delay=float(data.get("startDelay", current.start_delay)),
                cycle_interval=float(data.get("cycleInterval", current.cycle_interval)),
                text_key_interval=float(data.get("textInterval", current.text_key_interval)),
                delay_jitter=float(data.get("jitter", current.delay_jitter)),
                start_hotkey=str(data.get("startHotkey", current.start_hotkey)).lower(),
                capture_hotkey=str(data.get("captureHotkey", current.capture_hotkey)).lower(),
                stop_hotkey=str(data.get("stopHotkey", current.stop_hotkey)).lower(),
                target_mode=current.target_mode,
                target_window_title=current.target_window_title,
                target_window_class=current.target_window_class,
                target_executable=current.target_executable,
                # Carried over for the same reason as the window fields: this form
                # edits timing and shortcuts, never the chosen target.
                target_tab_url=current.target_tab_url,
                target_tab_title=current.target_tab_title,
                browser_port=current.browser_port,
            )
            settings.validate()
        except (ValueError, TypeError) as exc:
            self.toast.emit(str(exc), "error")
            return False
        changed = settings != self._run_settings
        if changed and self._hotkeys_enabled and not self._install_hotkeys(settings):
            return False
        self._run_settings = settings
        self._set_run_settings_pending(False)
        self.runSettingsChanged.emit()
        if changed:
            self._clear_undo()
            self._set_dirty(True)
        if announce:
            self.toast.emit("Run settings applied", "success")
        return True

    @Slot()
    def markRunSettingsPending(self) -> None:
        self._set_run_settings_pending(True)

    @Slot(str, str, str, result="QVariantMap")
    def globalShortcutConflicts(
        self,
        start_hotkey: str,
        capture_hotkey: str,
        stop_hotkey: str,
    ) -> dict[str, Any]:
        return global_shortcut_conflicts(start_hotkey, capture_hotkey, stop_hotkey)

    @Slot("QVariantMap", result=bool)
    def applyRunSettings(self, data: dict[str, Any]) -> bool:
        return self._apply_run_settings(data)

    def _reserved_shortcuts(self) -> set[str]:
        return canonical_global_shortcuts((
            self._run_settings.start_hotkey,
            self._run_settings.capture_hotkey,
            self._run_settings.stop_hotkey,
        ))

    @staticmethod
    def _pynput_hotkey(value: str) -> str:
        return pynput_hotkey(value)

    def _install_hotkeys(
        self,
        settings: RunSettings,
        queue_stop: bool = False,
    ) -> bool:
        """Start a replacement before retiring known-good shortcuts."""
        try:
            mapping = {
                self._pynput_hotkey(settings.start_hotkey): self.queueStartToggle,
                self._pynput_hotkey(settings.capture_hotkey): self.queueCapture,
                self._pynput_hotkey(settings.stop_hotkey): self.queueStop,
            }
            if queue_stop:
                mapping[self._pynput_hotkey("f9")] = self.queueStop
            replacement = keyboard.GlobalHotKeys(mapping)
            replacement.start()
        except Exception as exc:
            self.toast.emit(f"Shortcut error: {exc}", "error")
            return False

        previous = self._listener
        self._listener = replacement
        if previous:
            previous.stop()
        return True

    def _restart_hotkeys(self) -> bool:
        return self._install_hotkeys(self._run_settings)

    def _restore_standard_hotkeys(self) -> None:
        if self._hotkeys_enabled:
            self._restart_hotkeys()

    @Slot()
    def shutdown(self) -> None:
        if self._active_session is not None:
            self._active_session.stop_event.set()
        for session in self._parallel_sessions.values():
            session.pause_event.clear()
            session.stop_event.set()
        self._parallel_sessions.clear()
        self._queue_stop_requested = True
        self._queue_active = False
        watched = self._profile_watcher.directories()
        if watched:
            self._profile_watcher.removePaths(watched)
        self._capture_overlay.finish()
        self._capture_target = -1
        self._capture_countdown = 0
        self._window_pick_countdown = 0
        if self._capture_listener:
            self._capture_listener.stop()
            self._capture_listener = None
        self._action_capture_mode = ""
        if self._listener:
            self._listener.stop()
            self._listener = None

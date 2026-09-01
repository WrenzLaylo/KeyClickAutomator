from __future__ import annotations

import copy
import os
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pyautogui
from pynput import keyboard
from PySide6.QtCore import (
    QAbstractListModel,
    QByteArray,
    QFileSystemWatcher,
    QModelIndex,
    QObject,
    Property,
    QStandardPaths,
    QTimer,
    Qt,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import QGuiApplication
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
from run_session import RunSession
from shortcut_service import global_shortcut_conflicts, pynput_hotkey
from window_backend import (
    Win32WindowService,
    WindowInfo,
    WindowMessageBackend,
    WindowSelector,
    WindowTargetError,
)


APP_VERSION = "3.5.0"
MAX_PARALLEL_SESSIONS = 8


class ActionListModel(QAbstractListModel):
    TitleRole = Qt.UserRole + 1
    SubtitleRole = Qt.UserRole + 2
    KindRole = Qt.UserRole + 3
    EnabledRole = Qt.UserRole + 4
    IndexRole = Qt.UserRole + 5
    IconRole = Qt.UserRole + 6

    def __init__(self, controller: "AutomatorController") -> None:
        super().__init__()
        self.controller = controller

    def roleNames(self) -> dict[int, QByteArray]:
        return {
            self.TitleRole: QByteArray(b"title"),
            self.SubtitleRole: QByteArray(b"subtitle"),
            self.KindRole: QByteArray(b"kind"),
            self.EnabledRole: QByteArray(b"actionEnabled"),
            self.IndexRole: QByteArray(b"actionIndex"),
            self.IconRole: QByteArray(b"actionIcon"),
        }

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.controller.actions)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid() or not 0 <= index.row() < len(self.controller.actions):
            return None
        action = self.controller.actions[index.row()]
        if role == self.TitleRole:
            return self._title(action)
        if role == self.SubtitleRole:
            return self._subtitle(action)
        if role == self.KindRole:
            return action.kind
        if role == self.EnabledRole:
            return action.enabled
        if role == self.IndexRole:
            return index.row()
        if role == self.IconRole:
            return self._icon(action.kind)
        return None

    @staticmethod
    def _title(action: Action) -> str:
        if action.kind == "key":
            return f"Press {action.value.upper()}"
        if action.kind == "hotkey":
            return f"Shortcut {action.value.upper()}"
        if action.kind == "text":
            preview = action.value.replace("\n", " ↵ ")
            return f"Type “{preview[:28]}{'…' if len(preview) > 28 else ''}”"
        names = {
            "left_click": "Left click",
            "right_click": "Right click",
            "double_click": "Double click",
            "middle_click": "Middle click",
            "scroll": "Scroll",
            "drag": "Drag pointer",
        }
        return names.get(action.kind, action.kind.replace("_", " ").title())

    @staticmethod
    def _subtitle(action: Action) -> str:
        parts: list[str] = []
        click_actions = {"left_click", "right_click", "double_click", "middle_click"}
        if action.kind in click_actions and action.use_current_pointer:
            parts.append("current pointer")
        elif action.kind in {*click_actions, "scroll", "drag"}:
            prefix = "window " if action.coordinate_space == "window" else ""
            parts.append(f"{prefix}{action.x}, {action.y}")
            if action.coordinate_space == "window" and action.reference_width and action.reference_height:
                parts.append("scales with window")
        if action.kind == "drag":
            parts[-1] += f" → {action.x2}, {action.y2}"
        if action.kind == "scroll":
            parts.append(f"{action.amount:+d} steps")
        if action.repeats > 1:
            parts.append(f"repeat {action.repeats}×")
        parts.append(f"wait {action.delay_after:g}s")
        return "  ·  ".join(parts)

    @staticmethod
    def _icon(kind: str) -> str:
        return {
            "key": "K",
            "hotkey": "⌘",
            "text": "T",
            "left_click": "↖",
            "right_click": "↗",
            "double_click": "×2",
            "middle_click": "●",
            "scroll": "↕",
            "drag": "↗",
        }.get(kind, "•")

    def mutate(self, callback) -> None:
        self.beginResetModel()
        callback()
        self.endResetModel()

    def move_row(self, source: int, target: int) -> bool:
        count = self.rowCount()
        if not (0 <= source < count and 0 <= target < count) or source == target:
            return False

        # Qt expects destination_child in the model's pre-move coordinates.
        destination_child = target + 1 if target > source else target
        if not self.beginMoveRows(
            QModelIndex(), source, source, QModelIndex(), destination_child
        ):
            return False
        action = self.controller.actions.pop(source)
        self.controller.actions.insert(target, action)
        self.endMoveRows()

        first = min(source, target)
        last = max(source, target)
        self.dataChanged.emit(
            self.index(first, 0), self.index(last, 0), [self.IndexRole]
        )
        return True

    def notify_row(self, row: int, roles: list[int]) -> None:
        if not 0 <= row < self.rowCount():
            return
        model_index = self.index(row, 0)
        self.dataChanged.emit(model_index, model_index, roles)


class AutomatorController(QObject):
    actionsChanged = Signal()
    summaryChanged = Signal()
    selectedIndexChanged = Signal()
    runningChanged = Signal()
    statusChanged = Signal()
    progressChanged = Signal()
    runSettingsChanged = Signal()
    runSettingsPendingChanged = Signal()
    currentProfileNameChanged = Signal()
    currentProfilePathChanged = Signal()
    profileDirectoryChanged = Signal()
    profileEntriesChanged = Signal()
    dirtyChanged = Signal()
    draftAvailableChanged = Signal()
    undoChanged = Signal()
    captureStateChanged = Signal()
    actionCaptureStateChanged = Signal()
    targetSettingsChanged = Signal()
    windowPickStateChanged = Signal()
    windowEntriesChanged = Signal()
    runningActionIndexChanged = Signal()
    runQueueChanged = Signal()
    runQueueRunningChanged = Signal()
    runQueueModeChanged = Signal()
    toast = Signal(str, str)
    positionCaptured = Signal(int, int, int, str, int, int)
    actionKeyCaptured = Signal(str)
    actionHotkeyCaptured = Signal(str)
    shortcutCaptured = Signal(str, str)
    progressFromWorker = Signal(str, str, int, int)
    finishedFromWorker = Signal(str, bool, str)
    hotkeyToggleRequested = Signal()
    hotkeyCaptureRequested = Signal()
    hotkeyStopRequested = Signal()

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
        self.progressFromWorker.connect(self._handle_progress)
        self.finishedFromWorker.connect(self._finish_run)
        self.hotkeyToggleRequested.connect(self._toggle_run)
        self.hotkeyCaptureRequested.connect(lambda: self.startPositionCapture(0))
        self.hotkeyStopRequested.connect(self.stopRun)
        self.actionKeyCaptured.connect(self._on_action_key_captured)
        self.actionHotkeyCaptured.connect(self._on_action_hotkey_captured)
        self.shortcutCaptured.connect(self._on_shortcut_captured)
        if start_hotkeys:
            self._restart_hotkeys()

    @Property(QObject, constant=True)
    def actionModel(self):
        return self._model

    @Property(str, notify=currentProfileNameChanged)
    def currentProfileName(self) -> str:
        return self._current_profile_name

    @Property(str, notify=currentProfilePathChanged)
    def currentProfilePath(self) -> str:
        return self._current_profile_path or ""

    @Property(str, notify=profileDirectoryChanged)
    def profileDirectory(self) -> str:
        return self._profile_directory

    @Property("QVariantList", notify=profileEntriesChanged)
    def profileEntries(self) -> list[dict[str, Any]]:
        return self._profile_entries

    @Property("QVariantList", notify=runQueueChanged)
    def runQueueEntries(self) -> list[dict[str, Any]]:
        total = len(self._run_queue)
        return [
            session.as_entry(index + 1, total)
            for index, session in enumerate(self._run_queue)
        ]

    @Property("QVariantList", notify=runQueueChanged)
    def runQueuePaths(self) -> list[str]:
        return [session.profile_path for session in self._run_queue]

    @Property(int, notify=runQueueChanged)
    def runQueueCount(self) -> int:
        return len(self._run_queue)

    @Property(bool, notify=runQueueRunningChanged)
    def runQueueRunning(self) -> bool:
        return self._queue_active

    @Property(str, notify=runQueueModeChanged)
    def runQueueMode(self) -> str:
        return self._queue_mode

    @Property(int, notify=runQueueChanged)
    def runQueueActiveCount(self) -> int:
        return sum(
            session.state in {"armed", "running", "paused", "stopping"}
            for session in self._run_queue
        )

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

    @Property(bool, notify=dirtyChanged)
    def dirty(self) -> bool:
        return self._dirty

    @Property(bool, constant=True)
    def recoveryEnabled(self) -> bool:
        return self._recovery_enabled

    @Property(bool, notify=draftAvailableChanged)
    def draftAvailable(self) -> bool:
        return self._draft_available

    @Property(str, notify=draftAvailableChanged)
    def draftSummary(self) -> str:
        return self._draft_summary

    @Property(bool, notify=undoChanged)
    def canUndo(self) -> bool:
        return self._undo_deleted is not None

    @Property(bool, notify=runSettingsPendingChanged)
    def runSettingsPending(self) -> bool:
        return self._run_settings_pending

    @Property(bool, notify=captureStateChanged)
    def capturePending(self) -> bool:
        return self._capture_target >= 0

    @Property(int, notify=captureStateChanged)
    def captureCountdown(self) -> int:
        return self._capture_countdown

    @Property(int, notify=captureStateChanged)
    def captureTarget(self) -> int:
        return self._capture_target

    @Property(str, notify=actionCaptureStateChanged)
    def actionCaptureMode(self) -> str:
        return self._action_capture_mode

    @Property(bool, notify=windowPickStateChanged)
    def windowPickPending(self) -> bool:
        return self._window_pick_countdown > 0

    @Property(int, notify=windowPickStateChanged)
    def windowPickCountdown(self) -> int:
        return self._window_pick_countdown

    @Property("QVariantList", notify=windowEntriesChanged)
    def windowEntries(self) -> list[dict[str, Any]]:
        return self._window_entries

    @Property(str, notify=windowEntriesChanged)
    def desktopPreviewUrl(self) -> str:
        return self._desktop_preview_url

    @Property("QVariantMap", notify=targetSettingsChanged)
    def targetSettings(self) -> dict[str, Any]:
        settings = self._run_settings
        selector = WindowSelector(
            settings.target_window_title,
            settings.target_window_class,
            settings.target_executable,
        )
        return {
            "mode": settings.target_mode,
            "windowSelected": selector.selected,
            "windowTitle": settings.target_window_title,
            "windowClass": settings.target_window_class,
            "executable": settings.target_executable,
            "displayName": settings.target_window_title
            or (Path(settings.target_executable).stem if settings.target_executable else settings.target_window_class)
            or "No window selected",
        }

    def _get_window_service(self):
        if self._window_service is None:
            self._window_service = Win32WindowService()
        return self._window_service

    @staticmethod
    def _window_selector(settings: RunSettings) -> WindowSelector:
        return WindowSelector(
            settings.target_window_title,
            settings.target_window_class,
            settings.target_executable,
        )

    def _resolve_target_info(
        self,
        settings: RunSettings | None = None,
        preferred_hwnd: int | None = None,
        remember: bool | None = None,
    ) -> WindowInfo:
        selected_settings = settings or self._run_settings
        selected_preference = self._target_hwnd if preferred_hwnd is None else int(preferred_hwnd)
        info = self._get_window_service().resolve_window(
            self._window_selector(selected_settings),
            selected_preference,
        )
        self._get_window_service().ensure_usable(info.hwnd)
        should_remember = settings is None if remember is None else bool(remember)
        if should_remember:
            self._target_hwnd = info.hwnd
        return info

    @staticmethod
    def _window_app_name(info: WindowInfo) -> str:
        stem = Path(info.executable).stem if info.executable else info.class_name
        aliases = {
            "chrome": "Google Chrome",
            "msedge": "Microsoft Edge",
            "firefox": "Mozilla Firefox",
            "discord": "Discord",
            "zoom": "Zoom",
            "slack": "Slack",
            "teams": "Microsoft Teams",
            "ms-teams": "Microsoft Teams",
            "applicationframehost": "Windows app",
        }
        return aliases.get(stem.casefold(), stem.replace("_", " ").strip().title() or "Application")

    def _window_preview(self, hwnd: int, name: str) -> str:
        app = QGuiApplication.instance()
        if not isinstance(app, QGuiApplication) or QGuiApplication.platformName().casefold() == "offscreen":
            return ""
        screen = app.primaryScreen()
        if screen is None:
            return ""
        try:
            pixmap = screen.grabWindow(int(hwnd))
            if pixmap.isNull():
                return ""
            cache_dir = Path(QStandardPaths.writableLocation(QStandardPaths.CacheLocation)) / "window-previews"
            cache_dir.mkdir(parents=True, exist_ok=True)
            path = cache_dir / f"{name}-{int(hwnd)}.png"
            preview = pixmap.scaled(
                420,
                236,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            if not preview.save(str(path), "PNG"):
                return ""
            return QUrl.fromLocalFile(str(path)).toString() + f"?v={path.stat().st_mtime_ns}"
        except Exception:
            return ""

    def _refresh_window_selection(self) -> None:
        selected = self._target_hwnd if self._run_settings.target_mode == "window" else 0
        self._window_entries = [
            {**entry, "selected": int(entry["handle"]) == selected}
            for entry in self._window_entries
        ]
        self.windowEntriesChanged.emit()

    @Slot(result=bool)
    def refreshWindowEntries(self) -> bool:
        if self._running:
            self.toast.emit("Stop the automation before changing its target.", "error")
            return False
        try:
            service = self._get_window_service()
            candidates = service.list_windows(excluded_process_id=os.getpid())[:18]
        except Exception as exc:
            self._window_candidates = {}
            self._window_entries = []
            self._desktop_preview_url = ""
            self.windowEntriesChanged.emit()
            self.toast.emit(f"Open windows could not be listed: {exc}", "error")
            return False

        if self._run_settings.target_mode == "window" and self._window_selector(self._run_settings).selected:
            try:
                resolved = service.resolve_window(self._window_selector(self._run_settings), self._target_hwnd)
                self._target_hwnd = resolved.hwnd
            except Exception:
                # The list is still useful when a saved target is closed or
                # ambiguous; the user can choose a replacement visually.
                pass

        self._window_candidates = {info.hwnd: info for info in candidates}
        self._desktop_preview_url = self._window_preview(0, "desktop")
        self._window_entries = [
            {
                "handle": str(info.hwnd),
                "title": info.title,
                "appName": self._window_app_name(info),
                "previewUrl": "" if info.is_minimized else self._window_preview(info.hwnd, "window"),
                "minimized": info.is_minimized,
                "selected": self._run_settings.target_mode == "window" and info.hwnd == self._target_hwnd,
            }
            for info in candidates
        ]
        self.windowEntriesChanged.emit()
        return True

    def _set_window_target(self, info: WindowInfo) -> None:
        self._target_hwnd = info.hwnd
        self._run_settings.target_mode = "window"
        self._run_settings.target_window_title = info.title
        self._run_settings.target_window_class = info.class_name
        self._run_settings.target_executable = info.executable
        self.targetSettingsChanged.emit()
        self._refresh_window_selection()
        self._clear_undo()
        self._set_dirty(True)
        self.toast.emit(f"Target set to {info.display_name}", "success")

    @Slot(str, result=bool)
    def selectWindowTarget(self, handle: str) -> bool:
        if self._running:
            self.toast.emit("Stop the automation before choosing a target window.", "error")
            return False
        try:
            hwnd = int(str(handle))
            info = self._window_candidates.get(hwnd)
            if info is None:
                raise WindowTargetError("That window is no longer available. Refresh the list and try again.")
            self._get_window_service().ensure_usable(info.hwnd)
        except (TypeError, ValueError, WindowTargetError) as exc:
            self.toast.emit(f"Target window could not be selected: {exc}", "error")
            return False
        self.cancelPositionCapture(announce=False)
        self._set_window_target(info)
        return True

    @Slot(str, result=bool)
    def setTargetMode(self, mode: str) -> bool:
        normalized = str(mode).strip().lower()
        if normalized not in {"desktop", "window"}:
            return False
        if self._running:
            self.toast.emit("Stop the current run before changing its target.", "error")
            return False
        if normalized == self._run_settings.target_mode:
            return True
        self._cancel_action_capture(announce=False)
        self.cancelPositionCapture(announce=False)
        self.cancelWindowPick(announce=False)
        self._run_settings.target_mode = normalized
        self.targetSettingsChanged.emit()
        self._refresh_window_selection()
        self._clear_undo()
        self._set_dirty(True)
        if normalized == "window":
            self.toast.emit("Background window mode selected · choose a target window", "neutral")
        else:
            self.toast.emit("Desktop mode selected", "success")
        return True

    @Slot(result=bool)
    def startWindowPick(self) -> bool:
        if self._running:
            self.toast.emit("Stop the automation before choosing a target window.", "error")
            return False
        self._cancel_action_capture(announce=False)
        if self._capture_listener is not None:
            self.toast.emit("Finish recording the current key or shortcut first.", "error")
            return False
        self.cancelPositionCapture(announce=False)
        self.cancelWindowPick(announce=False)
        return self.refreshWindowEntries()

    @Slot()
    def cancelWindowPick(self, announce: bool = True) -> None:
        self._window_pick_countdown = 0
        self.windowPickStateChanged.emit()

    @Slot()
    def captureWindowTarget(self) -> None:
        self.cancelWindowPick(announce=False)
        try:
            point = pyautogui.position()
            info = self._get_window_service().window_at_point(int(point.x), int(point.y))
            if info.process_id == os.getpid():
                raise WindowTargetError("Move the pointer over the app you want to automate, not KeyClick itself.")
        except Exception as exc:
            self.toast.emit(f"Target window could not be selected: {exc}", "error")
            return
        self._set_window_target(info)

    @Property(int, notify=runningActionIndexChanged)
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

    @Property(str, notify=summaryChanged)
    def summary(self) -> str:
        active = [a for a in self.actions if a.enabled]
        operations = sum(a.repeats for a in active)
        if not self.actions:
            return "No actions yet"
        return f"{len(active)} active  ·  {operations} operations / cycle"

    @Property(int, notify=selectedIndexChanged)
    def selectedIndex(self) -> int:
        return self._selected_index

    @selectedIndex.setter
    def selectedIndex(self, value: int) -> None:
        value = int(value)
        if value != self._selected_index:
            self._selected_index = value
            self.selectedIndexChanged.emit()

    @Property(bool, notify=runningChanged)
    def running(self) -> bool:
        return self._running

    @Property(str, notify=statusChanged)
    def status(self) -> str:
        return self._status

    @Property(str, notify=statusChanged)
    def statusTone(self) -> str:
        return self._status_tone

    @Property(float, notify=progressChanged)
    def progress(self) -> float:
        return self._progress

    @Property(bool, notify=actionsChanged)
    def canRun(self) -> bool:
        return any(action.enabled for action in self.actions)

    @Property("QVariantMap", notify=runSettingsChanged)
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

    @Slot(int, result="QVariantMap")
    def actionAt(self, index: int) -> dict[str, Any]:
        if not 0 <= index < len(self.actions):
            return {}
        data = asdict(self.actions[index])
        data["delay"] = data.pop("delay_after")
        return data

    @staticmethod
    def _to_action(data: dict[str, Any]) -> Action:
        def integer(name: str, default: int = 0) -> int:
            value = data.get(name, default)
            return int(value if value not in (None, "") else default)

        def floating(name: str, default: float = 0.0) -> float:
            value = data.get(name, default)
            return float(value if value not in (None, "") else default)

        kind = str(data.get("kind", "key"))
        mouse = kind in {"left_click", "right_click", "double_click", "middle_click", "scroll", "drag"}
        click = kind in {"left_click", "right_click", "double_click", "middle_click"}
        use_current_pointer = bool(data.get("useCurrentPointer", data.get("use_current_pointer", False)))
        return Action(
            kind=kind,
            value=str(data.get("value", "")),
            x=integer("x") if mouse and not (click and use_current_pointer) else None,
            y=integer("y") if mouse and not (click and use_current_pointer) else None,
            x2=integer("x2") if kind == "drag" else None,
            y2=integer("y2") if kind == "drag" else None,
            amount=integer("amount", -3),
            duration=floating("duration", 0.4),
            repeats=integer("repeats", 1),
            delay_after=floating("delay", 0.1),
            enabled=bool(data.get("enabled", True)),
            use_current_pointer=use_current_pointer,
            coordinate_space=str(data.get("coordinateSpace", data.get("coordinate_space", "screen"))).lower(),
            reference_width=integer("referenceWidth", integer("reference_width")),
            reference_height=integer("referenceHeight", integer("reference_height")),
            reference_width2=integer("referenceWidth2", integer("reference_width2")),
            reference_height2=integer("referenceHeight2", integer("reference_height2")),
        )

    def _notify_actions(self) -> None:
        self.actionsChanged.emit()
        self.summaryChanged.emit()

    @Slot("QVariantMap", result=bool)
    def addAction(self, data: dict[str, Any]) -> bool:
        try:
            action = self._to_action(data)
            action.validate(self._reserved_shortcuts())
        except (ValueError, TypeError) as exc:
            self.toast.emit(str(exc), "error")
            return False
        self._model.mutate(lambda: self.actions.append(action))
        self._selected_index = len(self.actions) - 1
        self._clear_undo()
        self._notify_actions()
        self.selectedIndexChanged.emit()
        self._set_dirty(True)
        self.toast.emit("Action added", "success")
        return True

    @Slot(int, "QVariantMap", result=bool)
    def updateAction(self, index: int, data: dict[str, Any]) -> bool:
        if not 0 <= index < len(self.actions):
            return False
        try:
            action = self._to_action(data)
            action.enabled = self.actions[index].enabled
            action.validate(self._reserved_shortcuts())
        except (ValueError, TypeError) as exc:
            self.toast.emit(str(exc), "error")
            return False
        self._model.mutate(lambda: self.actions.__setitem__(index, action))
        self._clear_undo()
        self._notify_actions()
        self._set_dirty(True)
        self.toast.emit("Action updated", "success")
        return True

    @Slot(int)
    def deleteAction(self, index: int) -> None:
        if 0 <= index < len(self.actions):
            self._undo_deleted = (index, copy.deepcopy(self.actions[index]))
            self.undoChanged.emit()
            self._model.mutate(lambda: self.actions.pop(index))
            self._selected_index = min(index, len(self.actions) - 1)
            self._notify_actions()
            self.selectedIndexChanged.emit()
            self._set_dirty(True)
            self.toast.emit("Action deleted · Undo is available", "neutral")

    @Slot()
    def undoDelete(self) -> None:
        if self._undo_deleted is None or self._running:
            return
        index, action = self._undo_deleted
        index = min(max(0, index), len(self.actions))
        self._model.mutate(lambda: self.actions.insert(index, action))
        self._selected_index = index
        self._undo_deleted = None
        self.undoChanged.emit()
        self._notify_actions()
        self.selectedIndexChanged.emit()
        self._set_dirty(True)
        self.toast.emit("Deleted action restored", "success")

    @Slot(int)
    def duplicateAction(self, index: int) -> None:
        if 0 <= index < len(self.actions):
            duplicate = copy.deepcopy(self.actions[index])
            self._model.mutate(lambda: self.actions.insert(index + 1, duplicate))
            self._selected_index = index + 1
            self._clear_undo()
            self._notify_actions()
            self.selectedIndexChanged.emit()
            self._set_dirty(True)

    @Slot(int, int)
    def moveAction(self, index: int, delta: int) -> None:
        self.moveActionTo(index, index + delta)

    @Slot(int, int)
    def moveActionTo(self, source: int, target: int) -> None:
        if self._running or not self._model.move_row(source, target):
            return

        previous_selection = self._selected_index
        if previous_selection == source:
            self._selected_index = target
        elif source < previous_selection <= target:
            self._selected_index -= 1
        elif target <= previous_selection < source:
            self._selected_index += 1

        self._clear_undo()
        self._notify_actions()
        if self._selected_index != previous_selection:
            self.selectedIndexChanged.emit()
        self._set_dirty(True)
        self.toast.emit(f"Action moved to step {target + 1}", "success")

    @Slot(int, bool)
    def setActionEnabled(self, index: int, enabled: bool) -> None:
        if 0 <= index < len(self.actions):
            enabled = bool(enabled)
            if self.actions[index].enabled == enabled:
                return
            self.actions[index].enabled = enabled
            self._clear_undo()
            self._model.notify_row(index, [ActionListModel.EnabledRole])
            self._notify_actions()
            self._set_dirty(True)

    @Slot()
    def clearActions(self) -> None:
        if self._running:
            return
        self._model.mutate(self.actions.clear)
        self._set_current_profile(None)
        self._selected_index = -1
        self._clear_undo()
        self._set_run_settings_pending(False)
        self._notify_actions()
        self.selectedIndexChanged.emit()
        self._set_dirty(False)

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

    @Slot(result=bool)
    def enqueueCurrentProfile(self) -> bool:
        if not self._current_profile_path:
            self.toast.emit("Save this profile before adding it to the run queue.", "error")
            return False
        return self.enqueueProfile(self._current_profile_path)

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
        expected_space = "window" if settings.target_mode == "window" else "screen"
        for sequence_index, action in enumerate(actions):
            if action.kind not in mouse_kinds or action.coordinate_space == expected_space:
                continue
            if action.use_current_pointer:
                # The click follows the live pointer, so it has no recorded
                # position that could belong to the wrong target.
                continue
            source_index = action_indices[sequence_index] if sequence_index < len(action_indices) else sequence_index
            destination = "the selected window" if expected_space == "window" else "the desktop"
            raise ValueError(
                f"Step {source_index + 1} was recorded for a different target. "
                f"Open it and record its position again for {destination}."
            )
        if settings.target_mode == "desktop":
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
        return self._prepare_run_target(
            actions,
            action_indices,
            settings,
            preferred_hwnd=preferred_hwnd,
            remember_target=remember_target,
        )

    def _queue_reserved_shortcuts(self) -> set[str]:
        return self._reserved_shortcuts() | {"f9"}

    def _session_is_queued(self, session: RunSession) -> bool:
        return any(queued is session for queued in self._run_queue)

    def _session_by_id(self, session_id: str) -> RunSession | None:
        if self._active_session is not None and self._active_session.session_id == session_id:
            return self._active_session
        return self._parallel_sessions.get(session_id)

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
        resolved_targets: dict[int, list[RunSession]] = {}
        for index, session in enumerate(self._run_queue):
            try:
                self._load_profile_session(session.profile_path, existing=session)
                if (
                    self._queue_mode == "sequential"
                    and session.settings.repeat_forever
                    and index < len(self._run_queue) - 1
                ):
                    raise ValueError(
                        "A profile that loops indefinitely must be last in the queue."
                    )
                if self._queue_mode == "parallel" and session.settings.target_mode != "window":
                    raise ValueError(
                        "Parallel mode supports background-window profiles only."
                    )
                session.target_hwnd = self._validate_run_payload(
                    session.actions,
                    session.action_indices,
                    session.settings,
                    reserved_shortcuts=reserved_shortcuts,
                )
                session.reserved_shortcuts = set(reserved_shortcuts)
                if self._queue_mode == "parallel":
                    self._get_window_service().ensure_responsive(session.target_hwnd)
                    resolved_targets.setdefault(session.target_hwnd, []).append(session)
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
                message = (
                    f"{names} resolve to the same target window. "
                    "Choose a different window for one profile."
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
        if not self._queue_active or self._queue_mode != "parallel":
            return False
        started = 0
        for session in self._run_queue:
            if session.state == "queued" and self._start_session(session, parallel=True):
                started += 1
        if started == 0:
            self._queue_active = False
            self.runQueueRunningChanged.emit()
            self._set_running(False)
            self._restore_standard_hotkeys()
            return False
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

    def _run_worker(self, session: RunSession) -> None:
        try:
            backend = (
                WindowMessageBackend(session.target_hwnd, self._get_window_service())
                if session.settings.target_mode == "window"
                else pyautogui
            )
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
            self.finishedFromWorker.emit(
                session.session_id,
                complete,
                session.completion_message if complete else "Stopped safely",
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
                self.runQueueChanged.emit()
            return
        if session.pause_event.is_set():
            session.state = "paused"
            session.status = "Paused"
            session.tone = "accent"
            if self._session_is_queued(session):
                self.runQueueChanged.emit()
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
            self.runQueueChanged.emit()
        if parallel_session:
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

    @Slot(int, result=bool)
    def startPositionCapture(self, target: int = 0) -> bool:
        if target not in {0, 1}:
            return False
        if self._running:
            self.toast.emit("Stop the automation before recording a pointer position.", "error")
            return False
        self._cancel_action_capture(announce=False)
        if self._capture_listener is not None:
            self.toast.emit("Finish recording the current key or shortcut first.", "error")
            return False
        if self._run_settings.target_mode == "window":
            try:
                self._resolve_target_info()
            except WindowTargetError as exc:
                self.toast.emit(str(exc), "error")
                return False
        self.cancelWindowPick(announce=False)
        self.cancelPositionCapture(announce=False)
        self._capture_target = target
        self._capture_countdown = 0
        self.captureStateChanged.emit()
        self._set_status("Pick a point", "accent")
        title = "Pick the drag destination" if target == 1 else "Pick the pointer position"
        if not self._capture_overlay.begin(title):
            self._capture_target = -1
            self.captureStateChanged.emit()
            self._set_status("Ready", "neutral")
            return False
        return True

    def _end_position_capture(self) -> None:
        self._capture_overlay.finish()
        self._capture_target = -1
        self._capture_countdown = 0
        self.captureStateChanged.emit()
        self._set_status("Ready", "neutral")

    @Slot()
    def _capture_overlay_selected(self) -> None:
        if self._capture_target < 0:
            return
        point = pyautogui.position()
        self.commitPositionCapture(int(point.x), int(point.y))

    @Slot(str)
    def _capture_overlay_failed(self, message: str) -> None:
        self._end_position_capture()
        self.toast.emit(message, "error")

    @Slot()
    def cancelPositionCapture(self, announce: bool = True) -> None:
        if self._capture_target < 0:
            return
        self._end_position_capture()
        if announce:
            self.toast.emit("Pointer recording cancelled", "neutral")

    def _record_position_at(self, target: int, x: int, y: int, verify_target: bool) -> bool:
        coordinate_space = "screen"
        reference_width = 0
        reference_height = 0
        try:
            if self._run_settings.target_mode == "window":
                info = self._resolve_target_info()
                if verify_target:
                    pointed_window = self._get_window_service().window_at_point(x, y)
                    if pointed_window.hwnd != info.hwnd:
                        raise WindowTargetError(
                            "The pointer was not over the selected target window. Bring it into view and record again."
                        )
                x, y = self._get_window_service().screen_to_client(info.hwnd, x, y)
                self._get_window_service().mouse_target(info.hwnd, x, y)
                reference_width, reference_height = self._get_window_service().client_size(info.hwnd)
                coordinate_space = "window"
        except Exception as exc:
            self.toast.emit(f"Pointer position could not be recorded: {exc}", "error")
            return False
        self.positionCaptured.emit(
            target,
            x,
            y,
            coordinate_space,
            reference_width,
            reference_height,
        )
        label = "responsive window position" if coordinate_space == "window" else "pointer"
        self.toast.emit(f"Recorded {label} at {x}, {y}", "success")
        return True

    @Slot(int, int, result=bool)
    def commitPositionCapture(self, x: int, y: int) -> bool:
        if self._capture_target < 0:
            return False
        target = self._capture_target
        recorded = self._record_position_at(target, int(x), int(y), verify_target=False)
        self._end_position_capture()
        return recorded

    @Slot(int)
    def capturePosition(self, target: int = 0) -> None:
        self.cancelPositionCapture(announce=False)
        point = pyautogui.position()
        self._record_position_at(target, int(point.x), int(point.y), verify_target=True)

    @staticmethod
    def keyName(key: keyboard.Key | keyboard.KeyCode) -> str:
        if isinstance(key, keyboard.KeyCode):
            char = key.char
            if char:
                if len(char) == 1:
                    codepoint = ord(char)
                    if 1 <= codepoint <= 26:
                        return chr(ord("a") + codepoint - 1)
                    if char == " ":
                        return "space"
                if char.isprintable():
                    return char.lower()

            virtual_key = getattr(key, "vk", None)
            if isinstance(virtual_key, int):
                if 0x41 <= virtual_key <= 0x5A:
                    return chr(virtual_key).lower()
                if 0x30 <= virtual_key <= 0x39:
                    return chr(virtual_key)
                virtual_key_names = {
                    0x20: "space",
                    0xBA: ";",
                    0xBB: "=",
                    0xBC: ",",
                    0xBD: "-",
                    0xBE: ".",
                    0xBF: "/",
                    0xC0: "`",
                    0xDB: "[",
                    0xDC: "\\",
                    0xDD: "]",
                    0xDE: "'",
                }
                if virtual_key in virtual_key_names:
                    return virtual_key_names[virtual_key]
        return getattr(key, "name", str(key).replace("Key.", "")).lower()

    def _set_action_capture_mode(self, mode: str) -> None:
        if self._action_capture_mode == mode:
            return
        self._action_capture_mode = mode
        self.actionCaptureStateChanged.emit()

    def _prepare_action_capture(self, mode: str, prompt: str) -> bool:
        if self._capture_listener is not None:
            return False
        self.cancelPositionCapture(announce=False)
        self.cancelWindowPick(announce=False)
        if self._listener:
            self._listener.stop()
            self._listener = None
        self._set_action_capture_mode(mode)
        self.toast.emit(prompt, "neutral")
        return True

    def _action_capture_failed(self, message: str) -> None:
        self._capture_listener = None
        self._set_action_capture_mode("")
        self.toast.emit(message, "error")
        if self._hotkeys_enabled:
            self._restart_hotkeys()

    @Slot(result=bool)
    def recordActionKey(self) -> bool:
        if not self._prepare_action_capture("key", "Press the key you want to record"):
            return False

        def on_press(key) -> bool:
            self.actionKeyCaptured.emit(self.keyName(key))
            return False

        try:
            self._capture_listener = keyboard.Listener(on_press=on_press)
            self._capture_listener.start()
        except Exception as exc:
            self._action_capture_failed(f"Key recorder error: {exc}")
            return False
        return True

    @Slot(result=bool)
    def recordActionHotkey(self) -> bool:
        if not self._prepare_action_capture(
            "hotkey", "Hold a modifier, then press the hotkey you want to record"
        ):
            return False
        modifiers: set[str] = set()

        def on_press(key) -> bool | None:
            modifier = self._shortcut_modifier(key)
            if modifier:
                modifiers.add(modifier)
                return None
            ordered = [
                name
                for name in ("ctrl", "alt", "shift", "cmd", "alt_gr")
                if name in modifiers
            ]
            if not ordered:
                self.toast.emit(
                    "A Hotkey needs Ctrl, Alt, Shift, or Win plus another key.",
                    "error",
                )
                return None
            self.actionHotkeyCaptured.emit(
                "+".join([*ordered, self.keyName(key)])
            )
            return False

        def on_release(key) -> None:
            modifier = self._shortcut_modifier(key)
            if modifier:
                modifiers.discard(modifier)

        try:
            self._capture_listener = keyboard.Listener(
                on_press=on_press, on_release=on_release
            )
            self._capture_listener.start()
        except Exception as exc:
            self._action_capture_failed(f"Hotkey recorder error: {exc}")
            return False
        return True

    def _finish_action_capture(self, mode: str, value: str) -> None:
        if self._action_capture_mode != mode:
            return
        self._capture_listener = None
        self._set_action_capture_mode("")
        self.toast.emit(f"Recorded {value.upper()}", "success")
        if self._hotkeys_enabled:
            self._restart_hotkeys()

    @Slot(str)
    def _on_action_key_captured(self, value: str) -> None:
        self._finish_action_capture("key", value)

    @Slot(str)
    def _on_action_hotkey_captured(self, value: str) -> None:
        self._finish_action_capture("hotkey", value)

    def _cancel_action_capture(self, announce: bool) -> bool:
        if self._action_capture_mode not in {"key", "hotkey"}:
            return False
        listener = self._capture_listener
        self._capture_listener = None
        if listener is not None:
            listener.stop()
        self._set_action_capture_mode("")
        if self._hotkeys_enabled:
            self._restart_hotkeys()
        if announce:
            self.toast.emit("Action input recording cancelled", "neutral")
        return True

    @Slot(result=bool)
    def cancelActionCapture(self) -> bool:
        return self._cancel_action_capture(announce=True)

    @staticmethod
    def _shortcut_modifier(key: keyboard.Key | keyboard.KeyCode) -> str | None:
        name = AutomatorController.keyName(key)
        aliases = {
            "ctrl": "ctrl", "ctrl_l": "ctrl", "ctrl_r": "ctrl",
            "shift": "shift", "shift_l": "shift", "shift_r": "shift",
            "alt": "alt", "alt_l": "alt", "alt_r": "alt",
            "cmd": "cmd", "cmd_l": "cmd", "cmd_r": "cmd",
            "alt_gr": "alt_gr",
        }
        return aliases.get(name)

    @Slot(str, result=bool)
    def recordGlobalShortcut(self, target: str) -> bool:
        if target not in {"start", "capture", "stop"} or self._capture_listener is not None:
            return False
        self.cancelPositionCapture(announce=False)
        self.cancelWindowPick(announce=False)
        if self._listener:
            self._listener.stop()
            self._listener = None
        modifiers: set[str] = set()
        self.toast.emit("Press the shortcut you want to record", "neutral")

        def on_press(key) -> bool | None:
            modifier = self._shortcut_modifier(key)
            if modifier:
                modifiers.add(modifier)
                return None
            key_name = self.keyName(key)
            ordered = [name for name in ("ctrl", "alt", "shift", "cmd", "alt_gr") if name in modifiers]
            self.shortcutCaptured.emit(target, "+".join([*ordered, key_name]))
            return False

        def on_release(key) -> None:
            modifier = self._shortcut_modifier(key)
            if modifier:
                modifiers.discard(modifier)

        try:
            self._capture_listener = keyboard.Listener(on_press=on_press, on_release=on_release)
            self._capture_listener.start()
        except Exception as exc:
            self._capture_listener = None
            self.toast.emit(f"Shortcut recorder error: {exc}", "error")
            if self._hotkeys_enabled:
                self._restart_hotkeys()
            return False
        return True

    @Slot(str, str)
    def _on_shortcut_captured(self, target: str, value: str) -> None:
        self._capture_listener = None
        if self._hotkeys_enabled:
            self._restart_hotkeys()

    @Slot(str, str)
    def notifyShortcutCaptureResult(self, value: str, error_message: str) -> None:
        if error_message:
            self.toast.emit(error_message, "error")
        else:
            self.toast.emit(f"Recorded {value.upper()}", "success")

    @Slot(result=bool)
    def recoverDraft(self) -> bool:
        if not self._draft_available:
            return False
        try:
            payload = read_recovery_payload(self._recovery_path)
            actions, settings = load_profile(self._recovery_path)
            if self._hotkeys_enabled and not self._install_hotkeys(settings):
                return False
        except (OSError, ValueError, TypeError) as exc:
            self.toast.emit(f"Recovery copy could not be opened: {exc}", "error")
            return False
        self._model.mutate(lambda: setattr(self, "actions", actions))
        self._run_settings = settings
        self._target_hwnd = 0
        recovered_name = str(payload.get("profile_name") or "Untitled sequence")
        if self._current_profile_path is not None:
            self._current_profile_path = None
            self.currentProfilePathChanged.emit()
        self._current_profile_name = f"Recovered — {recovered_name}"
        self.currentProfileNameChanged.emit()
        self._selected_index = 0 if actions else -1
        self._clear_undo()
        self._set_run_settings_pending(False)
        self._notify_actions()
        self.selectedIndexChanged.emit()
        self.runSettingsChanged.emit()
        self.targetSettingsChanged.emit()
        self._set_dirty(True)
        self.toast.emit("Recovery copy restored", "success")
        return True

    @Slot()
    def discardDraft(self) -> None:
        self._remove_recovery_draft()

    @Slot(result=bool)
    def saveProfile(self) -> bool:
        if self._current_profile_path:
            return self._save_profile_path(self._current_profile_path)
        return self.saveProfileAs()

    @Slot(result=bool)
    def saveProfileAs(self) -> bool:
        suggested_name = self._current_profile_name.strip() or "Untitled sequence"
        for character in '<>:"/\\|?*':
            suggested_name = suggested_name.replace(character, "_")
        suggested_path = self._current_profile_path or str(
            Path(self._profile_directory) / f"{suggested_name}.kca.json"
        )
        path, _ = QFileDialog.getSaveFileName(
            None,
            "Save automation profile",
            suggested_path,
            "KeyClick profiles (*.kca.json);;JSON (*.json)",
        )
        if not path:
            return False
        if not path.lower().endswith((".json", ".kca.json")):
            path += ".kca.json"
        return self._save_profile_path(path)

    def _save_profile_path(self, path: str | Path) -> bool:
        normalized = normalize_path(path)
        try:
            save_profile(normalized, self.actions, self._run_settings)
            self._set_profile_directory(Path(normalized).parent)
            self._set_current_profile(normalized)
            self._set_dirty(False)
            self.refreshProfiles()
            self.toast.emit(f"Saved {Path(normalized).name}", "success")
            return True
        except OSError as exc:
            self.toast.emit(str(exc), "error")
            return False

    @Slot(result=bool)
    def openProfile(self) -> bool:
        path, _ = QFileDialog.getOpenFileName(
            None,
            "Open automation profile",
            self._profile_directory,
            "KeyClick profiles (*.kca.json *.json)",
        )
        if not path:
            return False
        return self.openProfilePath(path)

    @Slot(str, result=bool)
    def openProfilePath(self, path: str) -> bool:
        if self._running:
            self.toast.emit("Stop the current run before switching profiles.", "error")
            return False
        normalized = normalize_path(path)
        if not Path(normalized).is_file():
            self.toast.emit("That profile file is no longer available. Refresh the list.", "error")
            self.refreshProfiles()
            return False
        try:
            actions, settings = load_profile(normalized)
            if self._hotkeys_enabled and not self._install_hotkeys(settings):
                return False
            self._model.mutate(lambda: setattr(self, "actions", actions))
            self._run_settings = settings
            self._target_hwnd = 0
            self._set_profile_directory(Path(normalized).parent)
            self._set_current_profile(normalized)
            self._selected_index = 0 if actions else -1
            self._clear_undo()
            self._set_run_settings_pending(False)
            self._notify_actions()
            self.selectedIndexChanged.emit()
            self.runSettingsChanged.emit()
            self.targetSettingsChanged.emit()
            self._set_dirty(False)
            self.toast.emit(f"Opened {Path(normalized).name}", "success")
            return True
        except (OSError, ValueError, TypeError) as exc:
            self.toast.emit(str(exc), "error")
            return False

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

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
from chrome_backend import (
    ChromeTabBackend,
    ChromeTargetError,
    DEFAULT_PORT as BROWSER_PORT,
    browser_available,
    find_tab,
    launch_chrome,
    list_tabs,
    wait_for_browser,
)
from preflight import Check, blocking_failures, looks_like_a_browser, preflight
from profile_history import restore as restore_version, snapshot, versions
from controller_capture import CaptureMixin
from controller_signals import ControllerSignals
from controller_profiles import ProfilesMixin
from controller_queue import QueueMixin
from controller_running import MAX_PARALLEL_SESSIONS, RunningMixin
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


class AutomatorController(
    QueueMixin, RunningMixin, CaptureMixin, ProfilesMixin, QObject
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

    @Property(QObject, constant=True)
    def actionModel(self):
        return self._model

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

    @Property(int, notify=ControllerSignals.runQueueChanged)
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

    @Property(bool, notify=ControllerSignals.windowPickStateChanged)
    def windowPickPending(self) -> bool:
        return self._window_pick_countdown > 0

    @Property(int, notify=ControllerSignals.windowPickStateChanged)
    def windowPickCountdown(self) -> int:
        return self._window_pick_countdown

    @Property("QVariantList", notify=ControllerSignals.windowEntriesChanged)
    def windowEntries(self) -> list[dict[str, Any]]:
        return self._window_entries

    @Property(str, notify=ControllerSignals.windowEntriesChanged)
    def desktopPreviewUrl(self) -> str:
        return self._desktop_preview_url

    @Property("QVariantMap", notify=ControllerSignals.targetSettingsChanged)
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
            "tabSelected": bool(settings.target_tab_url.strip()),
            "tabUrl": settings.target_tab_url,
            "tabTitle": settings.target_tab_title,
            "tabName": settings.target_tab_title or settings.target_tab_url or "No tab selected",
            "browserPort": settings.browser_port,
        }

    # -- browser tab targeting -------------------------------------------------

    @Property("QVariantList", notify=ControllerSignals.browserTabsChanged)
    def browserTabs(self) -> list[dict[str, Any]]:
        return self._browser_tabs

    @Property(bool, notify=ControllerSignals.browserTabsChanged)
    def browserReady(self) -> bool:
        return self._browser_ready

    @Slot(result=bool)
    def refreshBrowserTabs(self) -> bool:
        """List the tabs the debuggable browser is exposing right now."""
        port = self._run_settings.browser_port
        self._browser_ready = browser_available(port)
        if not self._browser_ready:
            self._browser_tabs = []
            self.browserTabsChanged.emit()
            return False
        try:
            tabs = list_tabs(port)
        except ChromeTargetError as exc:
            self._browser_tabs = []
            self.browserTabsChanged.emit()
            self.toast.emit(str(exc), "error")
            return False
        current = self._run_settings.target_tab_url
        self._browser_tabs = [
            {
                "id": tab.target_id,
                "title": tab.title or tab.url,
                "url": tab.url,
                "current": bool(current) and tab.url == current,
            }
            for tab in tabs
        ]
        self.browserTabsChanged.emit()
        return True

    @Slot(result=bool)
    def startBrowser(self) -> bool:
        """Launch a debuggable browser in KeyClick's own persistent profile."""
        port = self._run_settings.browser_port
        if browser_available(port):
            self.refreshBrowserTabs()
            return True
        chrome = self._chrome_executable()
        if not chrome:
            self.toast.emit(
                "Could not find Google Chrome. Install it, or open a browser with "
                f"--remote-debugging-port={port} yourself.",
                "error",
            )
            return False
        try:
            launch_chrome(chrome, self._browser_profile_root(), port=port)
        except OSError as exc:
            self.toast.emit(f"Could not start the browser: {exc}", "error")
            return False
        if not wait_for_browser(port, timeout=30.0):
            self.toast.emit("The browser did not open its debug port in time.", "error")
            return False
        self.refreshBrowserTabs()
        self.toast.emit("Browser ready for automation", "success")
        return True

    @Slot(str, result=bool)
    def selectBrowserTab(self, target_id: str) -> bool:
        if self._running:
            self.toast.emit("Stop the current run before changing its target.", "error")
            return False
        if not self._browser_tabs:
            # Selecting without having listed first is legitimate: refresh once
            # rather than failing on an empty cache.
            self.refreshBrowserTabs()
        chosen = next(
            (tab for tab in self._browser_tabs if tab["id"] == str(target_id)), None
        )
        if chosen is None:
            self.toast.emit("That tab is no longer open. Refresh the list.", "error")
            self.refreshBrowserTabs()
            return False
        self._run_settings.target_tab_url = chosen["url"]
        self._run_settings.target_tab_title = chosen["title"]
        self._set_dirty(True)
        self.targetSettingsChanged.emit()
        self.refreshBrowserTabs()
        self.toast.emit(f"Targeting {chosen['title'][:48]}", "success")
        return True

    def _start_browser_point_capture(self, target: int) -> bool:
        """Record a viewport point by asking the page which pixel was clicked."""
        try:
            tab = self._resolve_browser_tab(self._run_settings)
        except WindowTargetError as exc:
            self.toast.emit(str(exc), "error")
            return False
        try:
            backend = ChromeTabBackend(tab)
        except ChromeTargetError as exc:
            self.toast.emit(str(exc), "error")
            return False

        self._set_status("Pick a point", "accent")
        self.toast.emit("Click the spot in the browser tab", "neutral")

        def worker() -> None:
            picked = None
            try:
                picked = backend.capture_click_point(timeout=45.0)
            except ChromeTargetError:
                picked = None
            finally:
                backend.close()
            self.browserPointCaptured.emit(target, *(picked or (-1, -1, 0, 0)))

        self._browser_capture_thread = threading.Thread(target=worker, daemon=True)
        self._browser_capture_thread.start()
        return True

    @Slot(int, int, int, int, int)
    def _finish_browser_point_capture(
        self, target: int, x: int, y: int, width: int, height: int
    ) -> None:
        if x < 0 or y < 0:
            self._set_status("Ready", "neutral")
            self.toast.emit("Nothing was picked in the browser tab.", "neutral")
            return
        self._set_status("Ready", "neutral")
        self.positionCaptured.emit(target, x, y, "viewport", width, height)
        self.toast.emit(f"Recorded {x}, {y} in the tab", "success")

    # -- one list of everything you could automate ------------------------------

    @Property("QVariantList", notify=ControllerSignals.targetsChanged)
    def automationTargets(self) -> list[dict[str, Any]]:
        """Windows and browser tabs together, so the user picks a thing, not a mechanism.

        Pairing a target with the wrong delivery mechanism was the failure that
        cost a whole session: a browser window chosen in background-window mode
        runs perfectly and delivers nothing. Choosing the mechanism here makes
        that combination unreachable rather than merely detected.
        """
        settings = self._run_settings
        entries: list[dict[str, Any]] = [
            {
                "kind": "desktop",
                "id": "desktop",
                "previewUrl": self._desktop_preview_url,
                "minimized": False,
                "title": "This computer",
                "subtitle": "Uses your real mouse and keyboard",
                "current": settings.target_mode == "desktop",
                "advice": "",
            }
        ]

        for tab in self._browser_tabs:
            entries.append(
                {
                    "kind": "browser",
                    "id": tab["id"],
                    "previewUrl": "",
                    "minimized": False,
                    "title": tab["title"] or tab["url"],
                    "subtitle": tab["url"],
                    "current": settings.target_mode == "browser"
                    and tab["url"] == settings.target_tab_url,
                    "advice": "",
                }
            )

        for entry in self._window_entries:
            info = self._window_candidates.get(int(entry.get("handle", 0) or 0))
            executable = getattr(info, "executable", "")
            is_browser = looks_like_a_browser(
                entry.get("title", ""), getattr(info, "class_name", ""), executable
            )
            entries.append(
                {
                    "kind": "window",
                    "id": str(entry.get("handle", "")),
                    "title": entry.get("title", "") or entry.get("appName", ""),
                    "subtitle": entry.get("appName", "") or "Open window",
                    # Carried through so the picker can still show you the window
                    # rather than only naming it.
                    "previewUrl": entry.get("previewUrl", ""),
                    "minimized": entry.get("minimized", False),
                    "current": settings.target_mode == "window"
                    and entry.get("selected", False),
                    # Offered, but never silently: a browser window cannot receive
                    # background messages at all.
                    "advice": "Pick this app's tab instead — page clicks never reach a browser window"
                    if is_browser
                    else "",
                }
            )
        return entries

    @Slot(result=bool)
    def refreshAutomationTargets(self) -> bool:
        self.refreshWindowEntries()
        self.refreshBrowserTabs()
        self.targetsChanged.emit()
        return True

    @Slot(str, str, result=bool)
    def selectAutomationTarget(self, kind: str, identifier: str) -> bool:
        """Choose what to automate; KeyClick decides how to reach it."""
        if self._running or self._queue_active:
            self.toast.emit("Stop the current run before changing its target.", "error")
            return False
        kind = str(kind).strip().lower()
        if kind == "desktop":
            self.setTargetMode("desktop")
            self.targetsChanged.emit()
            return True
        if kind == "browser":
            if not self.setTargetMode("browser"):
                return False
            chosen = self.selectBrowserTab(identifier)
            self.targetsChanged.emit()
            return chosen
        if kind == "window":
            if not self.setTargetMode("window"):
                return False
            chosen = self.selectWindowTarget(identifier)
            self.targetsChanged.emit()
            return chosen
        return False

    @Property(str, notify=ControllerSignals.targetsChanged)
    def targetSummary(self) -> str:
        settings = self._run_settings
        if settings.target_mode == "desktop":
            return "This computer"
        if settings.target_mode == "browser":
            return settings.target_tab_title or settings.target_tab_url or "No tab chosen"
        return self.targetSettings["displayName"]

    def _browser_profile_root(self) -> Path:
        return Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))

    @staticmethod
    def _chrome_executable() -> str:
        for candidate in (
            os.environ.get("KEYCLICK_CHROME", ""),
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ):
            if candidate and Path(candidate).is_file():
                return candidate
        return ""

    def _resolve_browser_tab(self, settings: RunSettings):
        try:
            return find_tab(
                port=settings.browser_port,
                url=settings.target_tab_url,
                title=settings.target_tab_title,
            )
        except ChromeTargetError as exc:
            raise WindowTargetError(str(exc)) from exc

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
        if normalized not in {"desktop", "window", "browser"}:
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

    @Property(str, notify=ControllerSignals.summaryChanged)
    def summary(self) -> str:
        active = [a for a in self.actions if a.enabled]
        operations = sum(a.repeats for a in active)
        if not self.actions:
            return "No actions yet"
        return f"{len(active)} active  ·  {operations} operations / cycle"

    @Property(int, notify=ControllerSignals.selectedIndexChanged)
    def selectedIndex(self) -> int:
        return self._selected_index

    @selectedIndex.setter
    def selectedIndex(self, value: int) -> None:
        value = int(value)
        if value != self._selected_index:
            self._selected_index = value
            self.selectedIndexChanged.emit()

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

    @Property(bool, notify=ControllerSignals.actionsChanged)
    def canRun(self) -> bool:
        return any(action.enabled for action in self.actions)

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

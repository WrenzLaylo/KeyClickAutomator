from __future__ import annotations

import copy
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pyautogui
from pynput import keyboard
from PySide6.QtCore import (
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    QObject,
    Property,
    Qt,
    Signal,
    Slot,
)
from PySide6.QtWidgets import QFileDialog

from engine import HOTKEY_NAMED_KEYS, Action, AutomationRunner, RunSettings, load_profile, save_profile


APP_VERSION = "3.0.8"


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
        if action.kind in {"left_click", "right_click", "double_click", "middle_click", "scroll", "drag"}:
            parts.append(f"{action.x}, {action.y}")
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
    currentProfileNameChanged = Signal()
    toast = Signal(str, str)
    positionCaptured = Signal(int, int, int)
    actionKeyCaptured = Signal(str)
    shortcutCaptured = Signal(str, str)
    progressFromWorker = Signal(str, int, int)
    finishedFromWorker = Signal(bool, str)
    hotkeyToggleRequested = Signal()
    hotkeyCaptureRequested = Signal()
    hotkeyStopRequested = Signal()

    def __init__(self, start_hotkeys: bool = True) -> None:
        super().__init__()
        self.actions: list[Action] = []
        self._model = ActionListModel(self)
        self._selected_index = -1
        self._running = False
        self._status = "Ready"
        self._status_tone = "neutral"
        self._progress = 0.0
        self._stop_event = threading.Event()
        self._worker: threading.Thread | None = None
        self._listener: keyboard.GlobalHotKeys | None = None
        self._capture_listener: keyboard.Listener | None = None
        self._run_settings = RunSettings()
        self._current_profile_name = "Untitled sequence"
        self._hotkeys_enabled = start_hotkeys
        self.progressFromWorker.connect(self._handle_progress)
        self.finishedFromWorker.connect(self._finish_run)
        self.hotkeyToggleRequested.connect(self._toggle_run)
        self.hotkeyCaptureRequested.connect(lambda: self.capturePosition(0))
        self.hotkeyStopRequested.connect(self.stopRun)
        self.actionKeyCaptured.connect(self._on_action_key_captured)
        self.shortcutCaptured.connect(self._on_shortcut_captured)
        if start_hotkeys:
            self._restart_hotkeys()

    @Property(QObject, constant=True)
    def actionModel(self):
        return self._model

    @Property(str, notify=currentProfileNameChanged)
    def currentProfileName(self) -> str:
        return self._current_profile_name

    def _set_current_profile(self, path: str | None) -> None:
        name = Path(path).name if path else ""
        if name.lower().endswith(".kca.json"):
            name = name[:-9]
        elif name.lower().endswith(".json"):
            name = name[:-5]
        name = name or "Untitled sequence"
        if name != self._current_profile_name:
            self._current_profile_name = name
            self.currentProfileNameChanged.emit()

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
        return Action(
            kind=kind,
            value=str(data.get("value", "")),
            x=integer("x") if mouse else None,
            y=integer("y") if mouse else None,
            x2=integer("x2") if kind == "drag" else None,
            y2=integer("y2") if kind == "drag" else None,
            amount=integer("amount", -3),
            duration=floating("duration", 0.4),
            repeats=integer("repeats", 1),
            delay_after=floating("delay", 0.1),
            enabled=bool(data.get("enabled", True)),
        )

    def _notify_actions(self) -> None:
        self.actionsChanged.emit()
        self.summaryChanged.emit()

    @Slot("QVariantMap")
    def addAction(self, data: dict[str, Any]) -> None:
        try:
            action = self._to_action(data)
            action.validate(self._reserved_keys())
        except (ValueError, TypeError) as exc:
            self.toast.emit(str(exc), "error")
            return
        self._model.mutate(lambda: self.actions.append(action))
        self._selected_index = len(self.actions) - 1
        self._notify_actions()
        self.selectedIndexChanged.emit()
        self.toast.emit("Action added", "success")

    @Slot(int, "QVariantMap")
    def updateAction(self, index: int, data: dict[str, Any]) -> None:
        if not 0 <= index < len(self.actions):
            return
        try:
            action = self._to_action(data)
            action.enabled = self.actions[index].enabled
            action.validate(self._reserved_keys())
        except (ValueError, TypeError) as exc:
            self.toast.emit(str(exc), "error")
            return
        self._model.mutate(lambda: self.actions.__setitem__(index, action))
        self._notify_actions()
        self.toast.emit("Action updated", "success")

    @Slot(int)
    def deleteAction(self, index: int) -> None:
        if 0 <= index < len(self.actions):
            self._model.mutate(lambda: self.actions.pop(index))
            self._selected_index = min(index, len(self.actions) - 1)
            self._notify_actions()
            self.selectedIndexChanged.emit()

    @Slot(int)
    def duplicateAction(self, index: int) -> None:
        if 0 <= index < len(self.actions):
            duplicate = copy.deepcopy(self.actions[index])
            self._model.mutate(lambda: self.actions.insert(index + 1, duplicate))
            self._selected_index = index + 1
            self._notify_actions()
            self.selectedIndexChanged.emit()

    @Slot(int, int)
    def moveAction(self, index: int, delta: int) -> None:
        target = index + delta
        if 0 <= index < len(self.actions) and 0 <= target < len(self.actions):
            def swap() -> None:
                self.actions[index], self.actions[target] = self.actions[target], self.actions[index]
            self._model.mutate(swap)
            self._selected_index = target
            self._notify_actions()
            self.selectedIndexChanged.emit()

    @Slot(int, bool)
    def setActionEnabled(self, index: int, enabled: bool) -> None:
        if 0 <= index < len(self.actions):
            enabled = bool(enabled)
            if self.actions[index].enabled == enabled:
                return
            self.actions[index].enabled = enabled
            self._model.notify_row(index, [ActionListModel.EnabledRole])
            self._notify_actions()

    @Slot()
    def clearActions(self) -> None:
        if self._running:
            return
        self._model.mutate(self.actions.clear)
        self._set_current_profile(None)
        self._selected_index = -1
        self._notify_actions()
        self.selectedIndexChanged.emit()

    @Slot("QVariantMap")
    def applyRunSettings(self, data: dict[str, Any]) -> None:
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
            )
            settings.validate()
        except (ValueError, TypeError) as exc:
            self.toast.emit(str(exc), "error")
            return
        if self._hotkeys_enabled and not self._install_hotkeys(settings):
            return
        self._run_settings = settings
        self.runSettingsChanged.emit()
        self.toast.emit("Run settings applied", "success")

    @Slot()
    def startRun(self) -> None:
        if self._running:
            return
        active = [copy.deepcopy(a) for a in self.actions if a.enabled]
        if not active:
            self.toast.emit("Add or enable at least one action before starting.", "error")
            return
        try:
            self._run_settings.validate()
            for action in active:
                action.validate(self._reserved_keys())
        except ValueError as exc:
            self.toast.emit(str(exc), "error")
            return
        self._stop_event.clear()
        self._set_running(True)
        self._set_status("Armed", "accent")
        self._set_progress(0.0)
        self._worker = threading.Thread(target=self._run_worker, args=(active, copy.deepcopy(self._run_settings)), daemon=True)
        self._worker.start()

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

    def _run_worker(self, actions: list[Action], settings: RunSettings) -> None:
        try:
            complete = AutomationRunner(pyautogui).run(actions, settings, self._stop_event, self.progressFromWorker.emit)
            self.finishedFromWorker.emit(complete, "Run complete" if complete else "Stopped safely")
        except pyautogui.FailSafeException:
            self.finishedFromWorker.emit(False, "Stopped by corner fail-safe")
        except Exception as exc:
            self.finishedFromWorker.emit(False, f"Automation error: {exc}")

    @Slot()
    def stopRun(self) -> None:
        self._stop_event.set()
        if self._running:
            self._set_status("Stopping", "danger")

    @Slot(str, int, int)
    def _handle_progress(self, phase: str, current: int, total: int) -> None:
        if phase == "timer":
            self._set_status("Countdown", "accent")
            self._set_progress(0.0)
        else:
            self._set_status("Running", "success")
            self._set_progress(-1.0 if total == 0 else current / total)

    @Slot(bool, str)
    def _finish_run(self, complete: bool, message: str) -> None:
        self._set_running(False)
        self._set_status("Complete" if complete else "Stopped", "success" if complete else "danger")
        self._set_progress(1.0 if complete else 0.0)
        self.toast.emit(message, "success" if complete else "neutral")

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

    @Slot(int)
    def capturePosition(self, target: int = 0) -> None:
        point = pyautogui.position()
        self.positionCaptured.emit(target, int(point.x), int(point.y))
        self.toast.emit(f"Captured {point.x}, {point.y}", "success")

    @staticmethod
    def keyName(key: keyboard.Key | keyboard.KeyCode) -> str:
        if isinstance(key, keyboard.KeyCode) and key.char:
            return key.char.lower()
        return getattr(key, "name", str(key).replace("Key.", "")).lower()

    @Slot()
    def recordActionKey(self) -> None:
        if self._capture_listener is not None:
            return
        if self._listener:
            self._listener.stop()
            self._listener = None
        self.toast.emit("Press the key you want to record", "neutral")

        def on_press(key) -> bool:
            self.actionKeyCaptured.emit(self.keyName(key))
            return False

        self._capture_listener = keyboard.Listener(on_press=on_press)
        self._capture_listener.start()

    @Slot(str)
    def _on_action_key_captured(self, value: str) -> None:
        self._capture_listener = None
        self.toast.emit(f"Recorded {value.upper()}", "success")
        if self._hotkeys_enabled:
            self._restart_hotkeys()

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
        self.toast.emit(f"Recorded {value.upper()}", "success")
        if self._hotkeys_enabled:
            self._restart_hotkeys()

    @Slot()
    def saveProfile(self) -> None:
        path, _ = QFileDialog.getSaveFileName(None, "Save automation profile", "", "KeyClick profiles (*.kca.json);;JSON (*.json)")
        if path:
            if not path.lower().endswith((".json", ".kca.json")):
                path += ".kca.json"
            try:
                save_profile(path, self.actions, self._run_settings)
                self._set_current_profile(path)
                self.toast.emit(f"Saved {Path(path).name}", "success")
            except OSError as exc:
                self.toast.emit(str(exc), "error")

    @Slot()
    def openProfile(self) -> None:
        path, _ = QFileDialog.getOpenFileName(None, "Open automation profile", "", "KeyClick profiles (*.kca.json *.json)")
        if not path:
            return
        try:
            actions, settings = load_profile(path)
            if self._hotkeys_enabled and not self._install_hotkeys(settings):
                return
            self._model.mutate(lambda: setattr(self, "actions", actions))
            self._run_settings = settings
            self._set_current_profile(path)
            self._selected_index = 0 if actions else -1
            self._notify_actions()
            self.selectedIndexChanged.emit()
            self.runSettingsChanged.emit()
            self.toast.emit(f"Opened {Path(path).name}", "success")
        except (OSError, ValueError, TypeError) as exc:
            self.toast.emit(str(exc), "error")

    def _reserved_keys(self) -> set[str]:
        return {
            part.strip().lower()
            for shortcut in (self._run_settings.start_hotkey, self._run_settings.capture_hotkey, self._run_settings.stop_hotkey)
            for part in shortcut.split("+")
            if part.strip()
        }

    @staticmethod
    def _pynput_hotkey(value: str) -> str:
        aliases = {"control": "ctrl", "escape": "esc", "return": "enter", "windows": "cmd", "win": "cmd"}
        special = HOTKEY_NAMED_KEYS
        formatted = []
        for raw in value.lower().replace(" ", "").split("+"):
            part = aliases.get(raw, raw)
            formatted.append(f"<{part}>" if part in special or (part.startswith("f") and part[1:].isdigit()) else part)
        return "+".join(formatted)

    def _install_hotkeys(self, settings: RunSettings) -> bool:
        """Start a replacement before retiring known-good shortcuts."""
        try:
            mapping = {
                self._pynput_hotkey(settings.start_hotkey): self.queueStartToggle,
                self._pynput_hotkey(settings.capture_hotkey): self.queueCapture,
                self._pynput_hotkey(settings.stop_hotkey): self.queueStop,
            }
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

    @Slot()
    def shutdown(self) -> None:
        self._stop_event.set()
        if self._capture_listener:
            self._capture_listener.stop()
            self._capture_listener = None
        if self._listener:
            self._listener.stop()
            self._listener = None

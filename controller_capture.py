"""Recording pointer positions, action keys, and global shortcuts."""
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


class CaptureMixin(ControllerSignals):
    """Every 'listen for input' flow the editor offers."""

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
        if self._run_settings.target_mode == "browser":
            # The page reports the click itself, so there is no screen overlay and
            # no screen-to-viewport arithmetic to get wrong.
            return self._start_browser_point_capture(target)
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
        name = CaptureMixin.keyName(key)
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

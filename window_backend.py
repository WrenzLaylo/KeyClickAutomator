"""Delivering keyboard and mouse input to one background window."""
from __future__ import annotations

import ctypes
import time
from ctypes import wintypes
from typing import Callable

# Re-exported so callers keep importing targets and delivery from one place.
from window_types import *  # noqa: F401,F403
from window_types import (
    _USER32,
    BM_CLICK,
    EM_REPLACESEL,
    MK_LBUTTON,
    MK_MBUTTON,
    MK_RBUTTON,
    WM_CHAR,
    WM_KEYDOWN,
    WM_KEYUP,
    WM_LBUTTONDBLCLK,
    WM_LBUTTONDOWN,
    WM_LBUTTONUP,
    WM_MBUTTONDOWN,
    WM_MBUTTONUP,
    WM_MOUSEMOVE,
    WM_MOUSEWHEEL,
    WM_NULL,
    WM_RBUTTONDOWN,
    WM_RBUTTONUP,
    WM_SYSKEYDOWN,
    WM_SYSKEYUP,
    WindowInfo,
    WindowSelector,
    WindowTargetError,
)
from window_service import Win32WindowService  # noqa: F401


def _packed_point(x: int, y: int) -> int:
    return (int(x) & 0xFFFF) | ((int(y) & 0xFFFF) << 16)


def _packed_wheel(key_flags: int, delta: int) -> int:
    return (int(key_flags) & 0xFFFF) | ((int(delta) & 0xFFFF) << 16)


class WindowMessageBackend:
    """PyAutoGUI-compatible backend that posts input to one background HWND."""

    DEFAULT_MESSAGE_INTERVAL = 0.015
    RESPONSIVENESS_PROBE_INTERVAL = 0.25
    EDIT_TEXT_CHUNK_SIZE = 256

    _BUTTON_MESSAGES = {
        "left": (WM_LBUTTONDOWN, WM_LBUTTONUP, MK_LBUTTON),
        "right": (WM_RBUTTONDOWN, WM_RBUTTONUP, MK_RBUTTON),
        "middle": (WM_MBUTTONDOWN, WM_MBUTTONUP, MK_MBUTTON),
    }
    _EXTENDED_KEYS = {
        0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28,
        0x2D, 0x2E, VK_LWIN, 0x5D, VK_RMENU,
    }

    def __init__(
        self,
        root_hwnd: int,
        service: WindowService | None = None,
        *,
        message_interval: float = DEFAULT_MESSAGE_INTERVAL,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.root_hwnd = int(root_hwnd)
        self.service = service or Win32WindowService()
        self._message_interval = max(0.0, float(message_interval))
        self._clock = clock
        self._sleep = sleeper
        self._last_message_at: float | None = None
        self._last_probe_at: float | None = None
        self._point: tuple[int, int] | None = None
        self._held_button: str | None = None
        self._drag_target: int = 0
        self.service.ensure_responsive(self.root_hwnd)
        self._last_probe_at = self._clock()

    def _ensure_target_ready(self) -> None:
        now = self._clock()
        if self._last_probe_at is None or now - self._last_probe_at >= self.RESPONSIVENESS_PROBE_INTERVAL:
            self.service.ensure_responsive(self.root_hwnd)
            self._last_probe_at = self._clock()
        else:
            self.service.ensure_usable(self.root_hwnd)

    def _pace_message(self) -> None:
        if self._last_message_at is not None and self._message_interval > 0:
            remaining = self._message_interval - (self._clock() - self._last_message_at)
            if remaining > 0:
                self._sleep(remaining)

    def _post_message(self, hwnd: int, message: int, wparam: int, lparam: int) -> None:
        self._ensure_target_ready()
        self._pace_message()
        self.service.post_message(hwnd, message, wparam, lparam)
        self._last_message_at = self._clock()

    def _replace_edit_text(self, hwnd: int, text: str) -> None:
        self._ensure_target_ready()
        self._pace_message()
        self.service.replace_edit_text(hwnd, text)
        self._last_message_at = self._clock()

    def scale_point(
        self,
        x: int,
        y: int,
        reference_width: int = 0,
        reference_height: int = 0,
    ) -> tuple[int, int]:
        """Scale a recorded client point to the target's current client size."""
        if reference_width <= 0 or reference_height <= 0:
            return int(x), int(y)
        width, height = self.service.client_size(self.root_hwnd)

        def scale(value: int, old_size: int, new_size: int) -> int:
            if old_size <= 1 or new_size <= 1:
                return 0
            return max(0, min(new_size - 1, round(int(value) * (new_size - 1) / (old_size - 1))))

        return scale(x, reference_width, width), scale(y, reference_height, height)

    def _key_lparam(self, virtual_key: int, released: bool = False, system_context: bool = False) -> int:
        scan_code = self.service.scan_code(virtual_key)
        value = 1 | ((scan_code & 0xFF) << 16)
        if virtual_key in self._EXTENDED_KEYS or scan_code & 0xFF00:
            value |= 1 << 24
        if system_context:
            value |= 1 << 29
        if released:
            value |= 1 << 30 | 1 << 31
        return value

    def _post_chord(self, keys: tuple[str, ...]) -> None:
        sequence: list[int] = []
        for key in keys:
            virtual_key, implicit_modifiers = self.service.virtual_key(key)
            for modifier in implicit_modifiers:
                if modifier not in sequence:
                    sequence.append(modifier)
            sequence.append(virtual_key)
        if not sequence:
            return
        target = self.service.keyboard_target(self.root_hwnd)
        alt_keys = {VK_MENU, VK_RMENU}
        alt_down = False
        for virtual_key in sequence:
            is_alt = virtual_key in alt_keys
            system_message = alt_down or is_alt
            self._post_message(
                target,
                WM_SYSKEYDOWN if system_message else WM_KEYDOWN,
                virtual_key,
                self._key_lparam(virtual_key, system_context=alt_down and not is_alt),
            )
            if is_alt:
                alt_down = True
        for virtual_key in reversed(sequence):
            is_alt = virtual_key in alt_keys
            system_message = alt_down or is_alt
            self._post_message(
                target,
                WM_SYSKEYUP if system_message else WM_KEYUP,
                virtual_key,
                self._key_lparam(virtual_key, released=True, system_context=alt_down and not is_alt),
            )
            if is_alt:
                alt_down = False

    def press(self, key: str) -> None:
        self._post_chord((key,))

    def hotkey(self, *keys: str) -> None:
        self._post_chord(tuple(keys))

    def write(self, text: str, interval: float = 0.0, _pause: bool = True) -> None:
        target = self.service.keyboard_target(self.root_hwnd)
        if self.service.is_edit_control(target):
            chunk_size = 1 if interval > 0 else self.EDIT_TEXT_CHUNK_SIZE
            for offset in range(0, len(text), chunk_size):
                self._replace_edit_text(target, text[offset:offset + chunk_size])
                if interval > 0:
                    self._sleep(interval)
            return
        for character in text:
            units = character.encode("utf-16-le", errors="surrogatepass")
            for offset in range(0, len(units), 2):
                code_unit = int.from_bytes(units[offset:offset + 2], "little")
                self._post_message(target, WM_CHAR, code_unit, 1)
            if interval > 0:
                self._sleep(interval)

    def _target_for_point(self, x: int, y: int) -> tuple[int, int, int]:
        if self._drag_target:
            local_x, local_y = self.service.map_root_point(self.root_hwnd, self._drag_target, x, y)
            return self._drag_target, local_x, local_y
        return self.service.mouse_target(self.root_hwnd, x, y)

    def moveTo(self, x: int, y: int, _pause: bool = True) -> None:
        self._point = (int(x), int(y))
        target, local_x, local_y = self._target_for_point(*self._point)
        flags = self._BUTTON_MESSAGES[self._held_button][2] if self._held_button else 0
        self._post_message(target, WM_MOUSEMOVE, flags, _packed_point(local_x, local_y))

    def click(self, x: int | None = None, y: int | None = None, button: str = "left") -> None:
        if x is None or y is None:
            raise WindowTargetError(
                "Follow current pointer is available only in Desktop mode. Record a window position for background mode."
            )
        if button not in self._BUTTON_MESSAGES:
            raise WindowTargetError(f"Unsupported background mouse button: {button}")
        self._point = (int(x), int(y))
        target, local_x, local_y = self.service.mouse_target(self.root_hwnd, *self._point)
        if button == "left" and self.service.is_button_control(target):
            self._post_message(target, BM_CLICK, 0, 0)
            return
        down, up, flag = self._BUTTON_MESSAGES[button]
        packed = _packed_point(local_x, local_y)
        self._post_message(target, WM_MOUSEMOVE, 0, packed)
        self._post_message(target, down, flag, packed)
        self._post_message(target, up, 0, packed)

    def doubleClick(self, x: int | None = None, y: int | None = None, button: str = "left") -> None:
        if button != "left":
            self.click(x, y, button=button)
            self.click(x, y, button=button)
            return
        if x is None or y is None:
            raise WindowTargetError(
                "Follow current pointer is available only in Desktop mode. Record a window position for background mode."
            )
        self._point = (int(x), int(y))
        target, local_x, local_y = self.service.mouse_target(self.root_hwnd, *self._point)
        if self.service.is_button_control(target):
            self._post_message(target, BM_CLICK, 0, 0)
            self._post_message(target, BM_CLICK, 0, 0)
            return
        packed = _packed_point(local_x, local_y)
        self._post_message(target, WM_MOUSEMOVE, 0, packed)
        self._post_message(target, WM_LBUTTONDOWN, MK_LBUTTON, packed)
        self._post_message(target, WM_LBUTTONUP, 0, packed)
        self._post_message(target, WM_LBUTTONDBLCLK, MK_LBUTTON, packed)
        self._post_message(target, WM_LBUTTONUP, 0, packed)

    def scroll(self, amount: int) -> None:
        if self._point is None:
            raise WindowTargetError("Record a window position before adding a background scroll action.")
        target, local_x, local_y = self.service.mouse_target(self.root_hwnd, *self._point)
        screen_x, screen_y = self.service.client_to_screen(self.root_hwnd, *self._point)
        self._post_message(target, WM_MOUSEMOVE, 0, _packed_point(local_x, local_y))
        direction = 1 if amount > 0 else -1
        for _ in range(abs(int(amount))):
            self._post_message(
                target,
                WM_MOUSEWHEEL,
                _packed_wheel(0, direction * WHEEL_DELTA),
                _packed_point(screen_x, screen_y),
            )

    def mouseDown(self, button: str = "left", _pause: bool = True) -> None:
        if self._point is None:
            raise WindowTargetError("Record a window position before adding a background drag action.")
        if button not in self._BUTTON_MESSAGES:
            raise WindowTargetError(f"Unsupported background mouse button: {button}")
        target, local_x, local_y = self.service.mouse_target(self.root_hwnd, *self._point)
        down, _up, flag = self._BUTTON_MESSAGES[button]
        self._held_button = button
        self._drag_target = target
        self._post_message(target, down, flag, _packed_point(local_x, local_y))

    def mouseUp(self, button: str = "left", _pause: bool = True) -> None:
        if self._point is None:
            return
        if button not in self._BUTTON_MESSAGES:
            raise WindowTargetError(f"Unsupported background mouse button: {button}")
        target, local_x, local_y = self._target_for_point(*self._point)
        _down, up, _flag = self._BUTTON_MESSAGES[button]
        self._post_message(target, up, 0, _packed_point(local_x, local_y))
        self._held_button = None
        self._drag_target = 0

    def dragTo(self, x: int, y: int, duration: float = 0.0, button: str = "left") -> None:
        self.mouseDown(button=button, _pause=False)
        try:
            self.moveTo(x, y, _pause=False)
            if duration > 0:
                self._sleep(duration)
        finally:
            self.mouseUp(button=button, _pause=False)


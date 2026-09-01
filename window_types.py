"""Win32 message constants, ctypes handles, and the target value types.

Shared by the service that finds windows and the backend that posts input to
them, so neither needs to import the other.
"""
from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol


WM_NULL = 0x0000
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_CHAR = 0x0102
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MBUTTONDOWN = 0x0207
WM_MBUTTONUP = 0x0208
WM_MOUSEWHEEL = 0x020A
BM_CLICK = 0x00F5
EM_REPLACESEL = 0x00C2

MK_LBUTTON = 0x0001
MK_RBUTTON = 0x0002
MK_MBUTTON = 0x0010
WHEEL_DELTA = 120

ERROR_ACCESS_DENIED = 5
ERROR_NOT_ENOUGH_QUOTA = 1816
SMTO_ABORTIFHUNG = 0x0002
SMTO_ERRORONEXIT = 0x0020

VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_LWIN = 0x5B
VK_RMENU = 0xA5


class WindowTargetError(RuntimeError):
    """Raised when a background target cannot safely receive an action."""


@dataclass(frozen=True)
class WindowSelector:
    title: str = ""
    class_name: str = ""
    executable: str = ""

    @property
    def selected(self) -> bool:
        return bool(self.title.strip() or self.class_name.strip() or self.executable.strip())


@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    title: str
    class_name: str
    executable: str
    process_id: int = 0
    is_minimized: bool = False

    @property
    def display_name(self) -> str:
        if self.title.strip():
            return self.title.strip()
        if self.executable.strip():
            return Path(self.executable).stem
        return self.class_name.strip() or "Selected window"

    @property
    def selector(self) -> WindowSelector:
        return WindowSelector(self.title, self.class_name, self.executable)


class WindowService(Protocol):
    def window_at_point(self, x: int, y: int) -> WindowInfo: ...
    def list_windows(self, excluded_process_id: int = 0) -> list[WindowInfo]: ...
    def resolve_window(self, selector: WindowSelector, preferred_hwnd: int = 0) -> WindowInfo: ...
    def ensure_usable(self, hwnd: int) -> None: ...
    def ensure_responsive(self, hwnd: int) -> None: ...
    def client_size(self, hwnd: int) -> tuple[int, int]: ...
    def screen_to_client(self, hwnd: int, x: int, y: int) -> tuple[int, int]: ...
    def client_to_screen(self, hwnd: int, x: int, y: int) -> tuple[int, int]: ...
    def mouse_target(self, root_hwnd: int, x: int, y: int) -> tuple[int, int, int]: ...
    def map_root_point(self, root_hwnd: int, target_hwnd: int, x: int, y: int) -> tuple[int, int]: ...
    def keyboard_target(self, root_hwnd: int) -> int: ...
    def is_button_control(self, hwnd: int) -> bool: ...
    def is_edit_control(self, hwnd: int) -> bool: ...
    def replace_edit_text(self, hwnd: int, text: str) -> None: ...
    def post_message(self, hwnd: int, message: int, wparam: int, lparam: int) -> None: ...
    def virtual_key(self, value: str) -> tuple[int, tuple[int, ...]]: ...
    def scan_code(self, virtual_key: int) -> int: ...


if os.name == "nt":
    _USER32 = ctypes.WinDLL("user32", use_last_error=True)
    _KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class _GUITHREADINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("flags", wintypes.DWORD),
            ("hwndActive", wintypes.HWND),
            ("hwndFocus", wintypes.HWND),
            ("hwndCapture", wintypes.HWND),
            ("hwndMenuOwner", wintypes.HWND),
            ("hwndMoveSize", wintypes.HWND),
            ("hwndCaret", wintypes.HWND),
            ("rcCaret", wintypes.RECT),
        ]

    _ENUM_WINDOWS_PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

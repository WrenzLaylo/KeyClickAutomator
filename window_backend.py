"""Windows background-window discovery and message-based automation backend."""
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


class Win32WindowService:
    """Small ctypes wrapper around the Win32 APIs needed by KeyClick."""

    GA_ROOT = 2
    CWP_SKIPINVISIBLE = 0x0001
    CWP_SKIPDISABLED = 0x0002
    CWP_SKIPTRANSPARENT = 0x0004
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    MAPVK_VK_TO_VSC = 0

    _NAMED_KEYS = {
        "backspace": 0x08,
        "tab": 0x09,
        "enter": 0x0D,
        "return": 0x0D,
        "shift": VK_SHIFT,
        "ctrl": VK_CONTROL,
        "control": VK_CONTROL,
        "alt": VK_MENU,
        "alt_gr": VK_RMENU,
        "pause": 0x13,
        "caps_lock": 0x14,
        "capslock": 0x14,
        "esc": 0x1B,
        "escape": 0x1B,
        "space": 0x20,
        "page_up": 0x21,
        "pageup": 0x21,
        "page_down": 0x22,
        "pagedown": 0x22,
        "end": 0x23,
        "home": 0x24,
        "left": 0x25,
        "up": 0x26,
        "right": 0x27,
        "down": 0x28,
        "insert": 0x2D,
        "delete": 0x2E,
        "menu": 0x5D,
        "num_lock": 0x90,
        "scroll_lock": 0x91,
        "cmd": VK_LWIN,
        "win": VK_LWIN,
        "windows": VK_LWIN,
    }

    def __init__(self) -> None:
        if os.name != "nt":
            raise WindowTargetError("Background window mode is available only on Windows.")
        self._configure_api()

    @staticmethod
    def _configure_api() -> None:
        _USER32.IsWindow.argtypes = [wintypes.HWND]
        _USER32.IsWindow.restype = wintypes.BOOL
        _USER32.IsWindowVisible.argtypes = [wintypes.HWND]
        _USER32.IsWindowVisible.restype = wintypes.BOOL
        _USER32.IsIconic.argtypes = [wintypes.HWND]
        _USER32.IsIconic.restype = wintypes.BOOL
        _USER32.IsChild.argtypes = [wintypes.HWND, wintypes.HWND]
        _USER32.IsChild.restype = wintypes.BOOL
        _USER32.GetForegroundWindow.argtypes = []
        _USER32.GetForegroundWindow.restype = wintypes.HWND
        _USER32.WindowFromPoint.argtypes = [wintypes.POINT]
        _USER32.WindowFromPoint.restype = wintypes.HWND
        _USER32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        _USER32.GetAncestor.restype = wintypes.HWND
        _USER32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        _USER32.GetWindowTextLengthW.restype = ctypes.c_int
        _USER32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        _USER32.GetWindowTextW.restype = ctypes.c_int
        _USER32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        _USER32.GetClassNameW.restype = ctypes.c_int
        _USER32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        _USER32.GetWindowThreadProcessId.restype = wintypes.DWORD
        _USER32.EnumWindows.argtypes = [_ENUM_WINDOWS_PROC, wintypes.LPARAM]
        _USER32.EnumWindows.restype = wintypes.BOOL
        _USER32.ScreenToClient.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
        _USER32.ScreenToClient.restype = wintypes.BOOL
        _USER32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
        _USER32.ClientToScreen.restype = wintypes.BOOL
        _USER32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        _USER32.GetClientRect.restype = wintypes.BOOL
        _USER32.ChildWindowFromPointEx.argtypes = [wintypes.HWND, wintypes.POINT, wintypes.UINT]
        _USER32.ChildWindowFromPointEx.restype = wintypes.HWND
        _USER32.MapWindowPoints.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.POINTER(wintypes.POINT), wintypes.UINT]
        _USER32.MapWindowPoints.restype = ctypes.c_int
        _USER32.GetGUIThreadInfo.argtypes = [wintypes.DWORD, ctypes.POINTER(_GUITHREADINFO)]
        _USER32.GetGUIThreadInfo.restype = wintypes.BOOL
        _USER32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        _USER32.PostMessageW.restype = wintypes.BOOL
        _USER32.SendMessageTimeoutW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
            wintypes.UINT,
            wintypes.UINT,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        _USER32.SendMessageTimeoutW.restype = wintypes.LPARAM
        _USER32.VkKeyScanW.argtypes = [wintypes.WCHAR]
        _USER32.VkKeyScanW.restype = ctypes.c_short
        _USER32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
        _USER32.MapVirtualKeyW.restype = wintypes.UINT
        _KERNEL32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        _KERNEL32.OpenProcess.restype = wintypes.HANDLE
        _KERNEL32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        _KERNEL32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        _KERNEL32.CloseHandle.argtypes = [wintypes.HANDLE]
        _KERNEL32.CloseHandle.restype = wintypes.BOOL

    @staticmethod
    def _window_text(hwnd: int) -> str:
        length = _USER32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(max(1, length + 1))
        _USER32.GetWindowTextW(hwnd, buffer, len(buffer))
        return buffer.value

    @staticmethod
    def _class_name(hwnd: int) -> str:
        buffer = ctypes.create_unicode_buffer(512)
        _USER32.GetClassNameW(hwnd, buffer, len(buffer))
        return buffer.value

    @classmethod
    def _process_path(cls, process_id: int) -> str:
        handle = _KERNEL32.OpenProcess(cls.PROCESS_QUERY_LIMITED_INFORMATION, False, process_id)
        if not handle:
            return ""
        try:
            buffer = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(buffer))
            if not _KERNEL32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                return ""
            return buffer.value
        finally:
            _KERNEL32.CloseHandle(handle)

    @classmethod
    def describe_window(cls, hwnd: int) -> WindowInfo:
        root = int(_USER32.GetAncestor(hwnd, cls.GA_ROOT) or hwnd)
        if not root or not _USER32.IsWindow(root):
            raise WindowTargetError("No application window was found at that position.")
        process_id = wintypes.DWORD()
        _USER32.GetWindowThreadProcessId(root, ctypes.byref(process_id))
        return WindowInfo(
            hwnd=root,
            title=cls._window_text(root),
            class_name=cls._class_name(root),
            executable=cls._process_path(int(process_id.value)),
            process_id=int(process_id.value),
            is_minimized=bool(_USER32.IsIconic(root)),
        )

    def window_at_point(self, x: int, y: int) -> WindowInfo:
        hwnd = int(_USER32.WindowFromPoint(wintypes.POINT(int(x), int(y))) or 0)
        if not hwnd:
            raise WindowTargetError("No application window was found under the pointer.")
        return self.describe_window(hwnd)

    def list_windows(self, excluded_process_id: int = 0) -> list[WindowInfo]:
        """Return ordinary visible application windows for the visual picker."""
        windows: list[WindowInfo] = []
        foreground = int(_USER32.GetForegroundWindow() or 0)

        @_ENUM_WINDOWS_PROC
        def collect(hwnd, _lparam):
            numeric_hwnd = int(hwnd)
            if not _USER32.IsWindowVisible(hwnd):
                return True
            try:
                info = self.describe_window(numeric_hwnd)
            except WindowTargetError:
                return True
            if (
                info.hwnd != numeric_hwnd
                or not info.title.strip()
                or (excluded_process_id and info.process_id == excluded_process_id)
                or info.class_name in {"Progman", "WorkerW", "Shell_TrayWnd"}
            ):
                return True
            try:
                width, height = self.client_size(info.hwnd)
            except WindowTargetError:
                return True
            if width < 120 or height < 80:
                return True
            windows.append(info)
            return True

        _USER32.EnumWindows(collect, 0)
        windows.sort(
            key=lambda info: (
                0 if info.hwnd == foreground else 1,
                1 if info.is_minimized else 0,
                info.display_name.casefold(),
            )
        )
        return windows

    @staticmethod
    def _normalized_path(value: str) -> str:
        return os.path.normcase(os.path.normpath(value)) if value else ""

    @classmethod
    def _base_match(cls, info: WindowInfo, selector: WindowSelector) -> bool:
        if selector.executable and cls._normalized_path(info.executable) != cls._normalized_path(selector.executable):
            return False
        if selector.class_name and info.class_name != selector.class_name:
            return False
        if not selector.executable and not selector.class_name and selector.title:
            return info.title == selector.title
        return True

    def resolve_window(self, selector: WindowSelector, preferred_hwnd: int = 0) -> WindowInfo:
        if not selector.selected:
            raise WindowTargetError("Choose a target window before starting background mode.")
        if preferred_hwnd and _USER32.IsWindow(preferred_hwnd):
            preferred = self.describe_window(preferred_hwnd)
            if self._base_match(preferred, selector):
                return preferred

        matches: list[WindowInfo] = []

        @_ENUM_WINDOWS_PROC
        def collect(hwnd, _lparam):
            if not _USER32.IsWindowVisible(hwnd):
                return True
            try:
                info = self.describe_window(int(hwnd))
            except WindowTargetError:
                return True
            if self._base_match(info, selector):
                matches.append(info)
            return True

        _USER32.EnumWindows(collect, 0)
        exact_title = [info for info in matches if selector.title and info.title == selector.title]
        if len(exact_title) == 1:
            return exact_title[0]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            closest = self._closest_by_title(matches, selector.title)
            if closest is not None:
                return closest
            raise WindowTargetError(
                "Several open windows match this profile's saved target. "
                "Open the profile and pick the window again."
            )
        raise WindowTargetError("The target window is not open. Open it, then try again.")

    @staticmethod
    def _title_affinity(saved: str, candidate: str) -> int:
        """Score how much of a saved title survives in a candidate title.

        Many apps write live data into their title bar -- Cookie Clicker leads
        with the cookie count -- so the saved title never matches exactly again
        and matching decays to class plus executable, which selects every window
        of that browser.  Scoring the stable head and tail of the title keeps the
        right window identifiable while the volatile middle drifts.
        """
        if not saved or not candidate:
            return 0
        limit = min(len(saved), len(candidate))
        prefix = 0
        while prefix < limit and saved[prefix] == candidate[prefix]:
            prefix += 1
        suffix = 0
        while (
            suffix < limit - prefix
            and saved[len(saved) - 1 - suffix] == candidate[len(candidate) - 1 - suffix]
        ):
            suffix += 1
        return prefix + suffix

    @classmethod
    def _closest_by_title(cls, matches: list[WindowInfo], saved_title: str) -> WindowInfo | None:
        """Return the single clearly-closest window, or None if it stays ambiguous."""
        saved_title = saved_title.strip()
        if not saved_title:
            return None
        scored = sorted(
            ((cls._title_affinity(saved_title, info.title), info) for info in matches),
            key=lambda pair: pair[0],
            reverse=True,
        )
        best, runner_up = scored[0][0], scored[1][0]
        # Only claim a winner when it shares a real span with the saved title and
        # beats every rival outright; a tie means we genuinely cannot tell.
        if best <= runner_up or best < max(8, len(saved_title) // 4):
            return None
        return scored[0][1]

    @staticmethod
    def ensure_usable(hwnd: int) -> None:
        if not hwnd or not _USER32.IsWindow(hwnd):
            raise WindowTargetError("The target window closed. Open it, then try again.")
        if _USER32.IsIconic(hwnd):
            raise WindowTargetError("Restore the target window first. It can stay behind other windows while KeyClick runs.")
        rect = wintypes.RECT()
        if not _USER32.GetClientRect(hwnd, ctypes.byref(rect)) or rect.right <= rect.left or rect.bottom <= rect.top:
            raise WindowTargetError("The target window has no usable content area. Restore or resize it, then try again.")

    @classmethod
    def ensure_responsive(cls, hwnd: int) -> None:
        """Fail before input is queued when the target is closed or not pumping messages."""
        cls.ensure_usable(hwnd)
        result = ctypes.c_size_t()
        ctypes.set_last_error(0)
        delivered = _USER32.SendMessageTimeoutW(
            hwnd,
            WM_NULL,
            0,
            0,
            SMTO_ABORTIFHUNG | SMTO_ERRORONEXIT,
            350,
            ctypes.byref(result),
        )
        if delivered:
            return
        error = ctypes.get_last_error()
        if not _USER32.IsWindow(hwnd):
            raise WindowTargetError("The target window closed. Open it, then try again.")
        if error == ERROR_ACCESS_DENIED:
            raise WindowTargetError(
                "Windows blocked the target check because the app has higher privileges. "
                "Run KeyClick at the same privilege level as the target app."
            )
        raise WindowTargetError(
            "The target window is not responding, so KeyClick stopped before sending more background input."
        )

    @staticmethod
    def screen_to_client(hwnd: int, x: int, y: int) -> tuple[int, int]:
        point = wintypes.POINT(int(x), int(y))
        if not _USER32.ScreenToClient(hwnd, ctypes.byref(point)):
            raise WindowTargetError("The pointer position could not be converted for the target window.")
        return int(point.x), int(point.y)

    @staticmethod
    def client_to_screen(hwnd: int, x: int, y: int) -> tuple[int, int]:
        point = wintypes.POINT(int(x), int(y))
        if not _USER32.ClientToScreen(hwnd, ctypes.byref(point)):
            raise WindowTargetError("The target position could not be converted to screen coordinates.")
        return int(point.x), int(point.y)

    @staticmethod
    def client_size(hwnd: int) -> tuple[int, int]:
        rect = wintypes.RECT()
        if not _USER32.GetClientRect(hwnd, ctypes.byref(rect)):
            raise WindowTargetError("The target window content area could not be read.")
        return int(rect.right - rect.left), int(rect.bottom - rect.top)

    def map_root_point(self, root_hwnd: int, target_hwnd: int, x: int, y: int) -> tuple[int, int]:
        point = wintypes.POINT(int(x), int(y))
        _USER32.MapWindowPoints(root_hwnd, target_hwnd, ctypes.byref(point), 1)
        return int(point.x), int(point.y)

    def mouse_target(self, root_hwnd: int, x: int, y: int) -> tuple[int, int, int]:
        self.ensure_usable(root_hwnd)
        width, height = self.client_size(root_hwnd)
        if not 0 <= x < width or not 0 <= y < height:
            raise WindowTargetError(
                f"Window position {x}, {y} is outside the target's current {width} x {height} content area. "
                "Resize it or record the position again."
            )

        current = int(root_hwnd)
        current_point = (int(x), int(y))
        root_process_id = wintypes.DWORD()
        _USER32.GetWindowThreadProcessId(root_hwnd, ctypes.byref(root_process_id))
        flags = self.CWP_SKIPINVISIBLE | self.CWP_SKIPDISABLED | self.CWP_SKIPTRANSPARENT
        for _ in range(16):
            child = int(_USER32.ChildWindowFromPointEx(current, wintypes.POINT(*current_point), flags) or 0)
            if not child or child == current:
                break
            child_process_id = wintypes.DWORD()
            _USER32.GetWindowThreadProcessId(child, ctypes.byref(child_process_id))
            if child_process_id.value != root_process_id.value:
                # Embedded cross-process surfaces must opt in through their own
                # automation API. Sending raw input messages to them is unsafe.
                break
            current = child
            current_point = self.map_root_point(root_hwnd, current, x, y)
        return current, current_point[0], current_point[1]

    @staticmethod
    def keyboard_target(root_hwnd: int) -> int:
        thread_id = _USER32.GetWindowThreadProcessId(root_hwnd, None)
        info = _GUITHREADINFO()
        info.cbSize = ctypes.sizeof(_GUITHREADINFO)
        if thread_id and _USER32.GetGUIThreadInfo(thread_id, ctypes.byref(info)):
            focused = int(info.hwndFocus or 0)
            if focused and (focused == root_hwnd or _USER32.IsChild(root_hwnd, focused)):
                return focused
        return int(root_hwnd)

    @classmethod
    def is_button_control(cls, hwnd: int) -> bool:
        return cls._class_name(hwnd).casefold() == "button"

    @classmethod
    def is_edit_control(cls, hwnd: int) -> bool:
        class_name = cls._class_name(hwnd).casefold()
        return class_name == "edit" or class_name.startswith("richedit") or class_name == "msftedit"

    @classmethod
    def replace_edit_text(cls, hwnd: int, text: str) -> None:
        buffer = ctypes.create_unicode_buffer(text)
        result = ctypes.c_size_t()
        ctypes.set_last_error(0)
        delivered = _USER32.SendMessageTimeoutW(
            hwnd,
            EM_REPLACESEL,
            1,
            ctypes.cast(buffer, ctypes.c_void_p).value or 0,
            0x0002,  # SMTO_ABORTIFHUNG
            2000,
            ctypes.byref(result),
        )
        if delivered:
            return
        error = ctypes.get_last_error()
        if error == ERROR_ACCESS_DENIED:
            raise WindowTargetError(
                "Windows blocked background text because the target has higher privileges. "
                "Run KeyClick at the same privilege level as the target app."
            )
        if error == 1460:
            raise WindowTargetError("The target text control stopped responding. Restore it, then try again.")
        detail = f" (Windows error {error})" if error else ""
        raise WindowTargetError(f"The target text control rejected background text{detail}.")

    @staticmethod
    def post_message(hwnd: int, message: int, wparam: int, lparam: int) -> None:
        ctypes.set_last_error(0)
        if _USER32.PostMessageW(hwnd, message, wparam, lparam):
            return
        error = ctypes.get_last_error()
        if error == ERROR_ACCESS_DENIED:
            raise WindowTargetError(
                "Windows blocked background input because the target has higher privileges. "
                "Run KeyClick at the same privilege level as the target app."
            )
        if error == ERROR_NOT_ENOUGH_QUOTA:
            raise WindowTargetError(
                "The target is not processing background input quickly enough. "
                "KeyClick stopped before its Windows message queue could overflow."
            )
        detail = f" (Windows error {error})" if error else ""
        raise WindowTargetError(f"The target window rejected a background input message{detail}.")

    @classmethod
    def virtual_key(cls, value: str) -> tuple[int, tuple[int, ...]]:
        normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
        if normalized in cls._NAMED_KEYS:
            return cls._NAMED_KEYS[normalized], ()
        if normalized.startswith("f") and normalized[1:].isdigit():
            number = int(normalized[1:])
            if 1 <= number <= 24:
                return 0x70 + number - 1, ()
        if len(value) == 1:
            packed = int(_USER32.VkKeyScanW(value))
            if packed != -1:
                packed &= 0xFFFF
                modifiers = []
                shift_state = (packed >> 8) & 0xFF
                if shift_state & 1:
                    modifiers.append(VK_SHIFT)
                if shift_state & 2:
                    modifiers.append(VK_CONTROL)
                if shift_state & 4:
                    modifiers.append(VK_MENU)
                return packed & 0xFF, tuple(modifiers)
        raise WindowTargetError(f"Background window mode does not support the key '{value}'.")

    @staticmethod
    def scan_code(virtual_key: int) -> int:
        return int(_USER32.MapVirtualKeyW(int(virtual_key), Win32WindowService.MAPVK_VK_TO_VSC))


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

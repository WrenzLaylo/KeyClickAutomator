"""Finding and describing the window a profile targets."""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

from window_types import (
    _ENUM_WINDOWS_PROC,
    _GUITHREADINFO,
    _KERNEL32,
    _USER32,
    EM_REPLACESEL,
    VK_CONTROL,
    VK_LWIN,
    VK_MENU,
    VK_RMENU,
    VK_SHIFT,
    WM_NULL,
    WindowInfo,
    WindowSelector,
    WindowTargetError,
)


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



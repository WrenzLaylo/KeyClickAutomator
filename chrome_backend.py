"""Chrome DevTools Protocol backend: drive one browser tab, and only that tab.

Windows message delivery cannot reach browser page content at all -- Chrome paints
the page with its own compositor and leaves no child window under it to receive a
WM_LBUTTONDOWN. CDP instead dispatches input straight into a named page target, so
the click lands on exactly one tab while every other tab, window, Chrome profile,
and application on the desktop is untouched. It also keeps working while that tab
is hidden behind another tab and while its window is minimised.
"""
from __future__ import annotations

import json
import socket
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol


class ChromeTargetError(RuntimeError):
    """Raised when a browser target cannot be reached or used."""


DEFAULT_PORT = 9222
# Chrome 136 and newer refuse --remote-debugging-port against the default profile
# directory, so automation always runs in its own persistent profile. That also
# isolates it from the user's signed-in windows instead of disturbing them.
PROFILE_DIR_NAME = "chrome-automation-profile"

_BUTTONS = {"left": "left", "right": "right", "middle": "middle"}
_MODIFIER_BITS = {"alt": 1, "ctrl": 2, "control": 2, "meta": 4, "cmd": 4, "win": 4, "shift": 8}

# key name -> (windowsVirtualKeyCode, key, code, text)
_NAMED_KEYS: dict[str, tuple[int, str, str, str]] = {
    "backspace": (8, "Backspace", "Backspace", ""),
    "tab": (9, "Tab", "Tab", "\t"),
    "enter": (13, "Enter", "Enter", "\r"),
    "return": (13, "Enter", "Enter", "\r"),
    "shift": (16, "Shift", "ShiftLeft", ""),
    "ctrl": (17, "Control", "ControlLeft", ""),
    "control": (17, "Control", "ControlLeft", ""),
    "alt": (18, "Alt", "AltLeft", ""),
    "pause": (19, "Pause", "Pause", ""),
    "caps_lock": (20, "CapsLock", "CapsLock", ""),
    "esc": (27, "Escape", "Escape", ""),
    "escape": (27, "Escape", "Escape", ""),
    "space": (32, " ", "Space", " "),
    "page_up": (33, "PageUp", "PageUp", ""),
    "page_down": (34, "PageDown", "PageDown", ""),
    "end": (35, "End", "End", ""),
    "home": (36, "Home", "Home", ""),
    "left": (37, "ArrowLeft", "ArrowLeft", ""),
    "up": (38, "ArrowUp", "ArrowUp", ""),
    "right": (39, "ArrowRight", "ArrowRight", ""),
    "down": (40, "ArrowDown", "ArrowDown", ""),
    "insert": (45, "Insert", "Insert", ""),
    "delete": (46, "Delete", "Delete", ""),
    "win": (91, "Meta", "MetaLeft", ""),
    "cmd": (91, "Meta", "MetaLeft", ""),
    "num_lock": (144, "NumLock", "NumLock", ""),
    "scroll_lock": (145, "ScrollLock", "ScrollLock", ""),
}
for _n in range(1, 13):
    _NAMED_KEYS[f"f{_n}"] = (111 + _n, f"F{_n}", f"F{_n}", "")


@dataclass(frozen=True)
class ChromeTab:
    target_id: str
    title: str
    url: str
    websocket_url: str

    @property
    def label(self) -> str:
        return self.title.strip() or self.url or self.target_id


class CdpConnection(Protocol):
    def send(self, method: str, **params: Any) -> dict[str, Any]: ...
    def close(self) -> None: ...


class WebSocketCdpConnection:
    """One request/response DevTools socket. Kept synchronous: runs on a worker."""

    def __init__(self, websocket_url: str, timeout: float = 15.0):
        try:
            import websocket  # provided by websocket-client
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise ChromeTargetError(
                "Browser control needs the websocket-client package. "
                "Reinstall the app requirements."
            ) from exc
        try:
            # Chrome rejects a browser-style Origin on the debugger socket; sending
            # none is safer than relaxing it with --remote-allow-origins=*.
            # TCP_NODELAY matters enormously here: every CDP call is a small write
            # followed by a blocking read, which is exactly the pattern Nagle's
            # algorithm delays. Without it a click costs well over a second.
            self._ws = websocket.create_connection(
                websocket_url,
                timeout=timeout,
                suppress_origin=True,
                sockopt=((socket.IPPROTO_TCP, socket.TCP_NODELAY, 1),),
            )
        except Exception as exc:
            raise ChromeTargetError(f"Could not attach to the browser tab: {exc}") from exc
        self._next_id = 0

    def send(self, method: str, **params: Any) -> dict[str, Any]:
        self._next_id += 1
        message_id = self._next_id
        try:
            self._ws.send(json.dumps({"id": message_id, "method": method, "params": params}))
            while True:
                payload = json.loads(self._ws.recv())
                if payload.get("id") != message_id:
                    continue  # an unsolicited event; keep reading for our reply
                if "error" in payload:
                    raise ChromeTargetError(
                        f"{method} failed: {payload['error'].get('message', payload['error'])}"
                    )
                return payload.get("result", {})
        except ChromeTargetError:
            raise
        except Exception as exc:
            raise ChromeTargetError(f"Lost the connection to the browser tab: {exc}") from exc

    def close(self) -> None:
        try:
            self._ws.close()
        except Exception:
            pass


def _fetch(port: int, path: str, timeout: float = 4.0) -> Any:
    url = f"http://127.0.0.1:{port}{path}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise ChromeTargetError(
            f"No debuggable browser is listening on port {port}. Start it from KeyClick first."
        ) from exc
    return json.loads(body) if body.strip() else {}


def browser_available(port: int = DEFAULT_PORT) -> bool:
    try:
        _fetch(port, "/json/version", timeout=1.5)
        return True
    except ChromeTargetError:
        return False


def list_tabs(port: int = DEFAULT_PORT) -> list[ChromeTab]:
    """Every page target the debug port exposes, newest Chrome first."""
    tabs: list[ChromeTab] = []
    for entry in _fetch(port, "/json"):
        if entry.get("type") != "page":
            continue
        websocket_url = entry.get("webSocketDebuggerUrl", "")
        if not websocket_url:
            continue  # already attached elsewhere, or not debuggable
        tabs.append(
            ChromeTab(
                target_id=str(entry.get("id", "")),
                title=str(entry.get("title", "")),
                url=str(entry.get("url", "")),
                websocket_url=websocket_url,
            )
        )
    return tabs


def find_tab(port: int = DEFAULT_PORT, target_id: str = "", url: str = "", title: str = "") -> ChromeTab:
    """Re-find a saved tab. Target ids die with the tab, so URL is the stable key."""
    tabs = list_tabs(port)
    if not tabs:
        raise ChromeTargetError("The browser has no open tabs to automate.")
    for tab in tabs:
        if target_id and tab.target_id == target_id:
            return tab
    if url:
        exact = [tab for tab in tabs if tab.url == url]
        if len(exact) == 1:
            return exact[0]
        if len(exact) > 1:
            raise ChromeTargetError(
                "Several tabs have that address open. Close the duplicates or pick the tab again."
            )
    if title:
        named = [tab for tab in tabs if tab.title == title]
        if len(named) == 1:
            return named[0]
    raise ChromeTargetError("That tab is no longer open. Pick the browser tab again.")


def profile_directory(root: str | Path) -> Path:
    return Path(root) / PROFILE_DIR_NAME


def launch_chrome(
    chrome_path: str | Path,
    profile_root: str | Path,
    port: int = DEFAULT_PORT,
    start_url: str = "",
    runner: Callable[..., Any] = subprocess.Popen,
) -> Any:
    """Start a debuggable Chrome in its own persistent profile."""
    directory = profile_directory(profile_root)
    directory.mkdir(parents=True, exist_ok=True)
    command = [
        str(chrome_path),
        f"--remote-debugging-port={port}",
        f"--user-data-dir={directory}",
        "--no-first-run",
        "--no-default-browser-check",
        # Chrome throttles renderers in hidden or occluded windows to about 4Hz,
        # which is the whole point of this feature -- automating a tab you are not
        # looking at. Without these the same click costs ~270ms instead of ~15ms.
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        "--disable-features=CalculateNativeWinOcclusion",
    ]
    if start_url:
        command.append(start_url)
    return runner(command)


def wait_for_browser(port: int = DEFAULT_PORT, timeout: float = 25.0, sleeper=time.sleep) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if browser_available(port):
            return True
        sleeper(0.25)
    return False


class ChromeTabBackend:
    """AutomationBackend that dispatches input into a single Chrome tab.

    Coordinates are CSS pixels relative to that tab's viewport, so they stay valid
    no matter where the browser window sits on screen or whether it is minimised.
    """

    def __init__(
        self,
        tab: ChromeTab,
        connection: CdpConnection | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        self.tab = tab
        self._cdp = connection if connection is not None else WebSocketCdpConnection(tab.websocket_url)
        self._clock = clock
        self._sleep = sleeper
        self._x = 0.0
        self._y = 0.0
        self._held_button: str | None = None
        self._viewport: tuple[int, int] | None = None
        self._viewport_at = 0.0
        self._delivered = 0
        self._verifying = False

    def close(self) -> None:
        if self._held_button:
            self.mouseUp(self._held_button)
        self._cdp.close()

    # -- delivery confirmation --------------------------------------------------

    def begin_verification(self) -> None:
        """Count input the page genuinely receives, not just what we sent.

        Dispatching an event always "succeeds"; it says nothing about whether the
        page got it. A capture-phase listener on the document is the cheapest
        honest answer, and works on any page.
        """
        self._delivered = 0
        try:
            self._cdp.send(
                "Runtime.evaluate",
                expression=(
                    "window.__keyclickHits=0;window.__keyclickTarget='';"
                    "if(!window.__keyclickCounter){"
                    # A document listener alone fires even for a click far outside
                    # the viewport, which reports success for input that hit
                    # nothing. Only count events that reached a real element.
                    "window.__keyclickCounter=function(e){"
                    "var t=e.target;"
                    "if(!t||t===document.documentElement||t===document.body)return;"
                    "window.__keyclickHits++;"
                    "if(!window.__keyclickTarget)window.__keyclickTarget="
                    "t.tagName.toLowerCase()+(t.id?'#'+t.id:'');};"
                    "document.addEventListener('mousedown',window.__keyclickCounter,true);"
                    "document.addEventListener('keydown',window.__keyclickCounter,true);"
                    "document.addEventListener('wheel',window.__keyclickCounter,true);}1"
                ),
                returnByValue=True,
            )
            self._verifying = True
        except ChromeTargetError:
            self._verifying = False

    def confirmed_input(self) -> int | None:
        """How much of what we sent the page actually saw, or None if unknown."""
        if not self._verifying:
            return None
        try:
            result = self._cdp.send(
                "Runtime.evaluate", expression="window.__keyclickHits", returnByValue=True
            )
        except ChromeTargetError:
            return None
        value = result.get("result", {}).get("value")
        return int(value) if isinstance(value, (int, float)) else None

    def confirmed_target(self) -> str:
        """The first element the page handed our input to, for the run report."""
        if not self._verifying:
            return ""
        try:
            result = self._cdp.send(
                "Runtime.evaluate", expression="window.__keyclickTarget", returnByValue=True
            )
        except ChromeTargetError:
            return ""
        value = result.get("result", {}).get("value")
        return str(value) if isinstance(value, str) else ""

    @property
    def delivered_input(self) -> int:
        return self._delivered

    # -- viewport ---------------------------------------------------------------

    def viewport_size(self, max_age: float = 1.0) -> tuple[int, int]:
        """Current CSS viewport size, cached so a fast run does not re-query it."""
        now = self._clock()
        if self._viewport is None or now - self._viewport_at >= max_age:
            result = self._cdp.send(
                "Runtime.evaluate",
                expression="({w: window.innerWidth, h: window.innerHeight})",
                returnByValue=True,
            )
            value = result.get("result", {}).get("value") or {}
            self._viewport = (int(value.get("w", 0)), int(value.get("h", 0)))
            self._viewport_at = now
        return self._viewport

    def scale_point(
        self, x: int, y: int, reference_width: int, reference_height: int
    ) -> tuple[int, int]:
        """Keep a recorded point on the same spot after the page is resized."""
        if not reference_width or not reference_height:
            return int(x), int(y)
        width, height = self.viewport_size()
        if not width or not height:
            return int(x), int(y)
        return (
            round(x * width / reference_width),
            round(y * height / reference_height),
        )

    def capture_click_point(self, timeout: float = 30.0) -> tuple[int, int, int, int] | None:
        """Wait for the user to click in the page; return the point and viewport size.

        Recording through the page itself is exact -- no screen-to-viewport
        arithmetic and no guessing where the browser's own chrome ends.
        """
        self._cdp.send(
            "Runtime.evaluate",
            expression=(
                "window.__keyclickPick=null;"
                "window.__keyclickHandler=function(e){"
                "window.__keyclickPick={x:Math.round(e.clientX),y:Math.round(e.clientY),"
                "w:window.innerWidth,h:window.innerHeight};"
                "e.preventDefault();e.stopPropagation();"
                "window.removeEventListener('mousedown',window.__keyclickHandler,true);};"
                "window.addEventListener('mousedown',window.__keyclickHandler,true);1"
            ),
            returnByValue=True,
        )
        deadline = self._clock() + timeout
        while self._clock() < deadline:
            picked = self._cdp.send(
                "Runtime.evaluate", expression="window.__keyclickPick", returnByValue=True
            ).get("result", {}).get("value")
            if picked:
                return (
                    int(picked["x"]), int(picked["y"]),
                    int(picked["w"]), int(picked["h"]),
                )
            self._sleep(0.1)
        self.cancel_click_capture()
        return None

    def cancel_click_capture(self) -> None:
        self._cdp.send(
            "Runtime.evaluate",
            expression=(
                "if(window.__keyclickHandler)"
                "window.removeEventListener('mousedown',window.__keyclickHandler,true);"
                "window.__keyclickPick=null;1"
            ),
            returnByValue=True,
        )

    # -- helpers ---------------------------------------------------------------

    @staticmethod
    def _button(button: str) -> str:
        resolved = _BUTTONS.get(button)
        if resolved is None:
            raise ChromeTargetError(f"Unsupported mouse button: {button}")
        return resolved

    def _mouse(self, event: str, button: str = "none", clicks: int = 0, **extra: Any) -> None:
        self._cdp.send(
            "Input.dispatchMouseEvent",
            type=event,
            x=self._x,
            y=self._y,
            button=button,
            clickCount=clicks,
            **extra,
        )

    def _point(self, x: int | None, y: int | None) -> None:
        if x is not None and y is not None:
            self._x, self._y = float(x), float(y)

    @staticmethod
    def _key_parts(name: str) -> tuple[int, str, str, str]:
        key = name.strip().lower()
        if key in _NAMED_KEYS:
            return _NAMED_KEYS[key]
        if len(key) == 1:
            return ord(key.upper()), key, f"Key{key.upper()}" if key.isalpha() else key, key
        raise ChromeTargetError(f"Unsupported key for browser mode: {name}")

    def _key_event(self, event: str, name: str, modifiers: int = 0) -> None:
        code_point, key, code, text = self._key_parts(name)
        params: dict[str, Any] = {
            "type": event,
            "windowsVirtualKeyCode": code_point,
            "nativeVirtualKeyCode": code_point,
            "key": key,
            "code": code,
            "modifiers": modifiers,
        }
        # Only a keyDown that produces a character carries text, and never while a
        # non-shift modifier is held or the page receives a stray character.
        if event == "keyDown" and text and not (modifiers & ~_MODIFIER_BITS["shift"]):
            params["text"] = text
            params["unmodifiedText"] = text
        self._cdp.send("Input.dispatchKeyEvent", **params)

    # -- AutomationBackend -----------------------------------------------------

    def press(self, key: str) -> None:
        self._key_event("keyDown", key)
        self._key_event("keyUp", key)
        self._delivered += 1

    def hotkey(self, *keys: str) -> None:
        names = [key.strip().lower() for key in keys if key.strip()]
        if len(names) < 2:
            raise ChromeTargetError("A hotkey needs at least two keys.")
        modifiers = [name for name in names if name in _MODIFIER_BITS]
        finals = [name for name in names if name not in _MODIFIER_BITS]
        mask = 0
        for name in modifiers:
            mask |= _MODIFIER_BITS[name]
        try:
            for name in modifiers:
                self._key_event("keyDown", name, mask)
            for name in finals:
                self._key_event("keyDown", name, mask)
                self._key_event("keyUp", name, mask)
        finally:
            for name in reversed(modifiers):
                self._key_event("keyUp", name, 0)

    def write(self, text: str, interval: float = 0.0, _pause: bool = True) -> None:
        if not text:
            return
        # insertText is the reliable path for arbitrary text; per-key synthesis
        # cannot represent every character and drops non-ASCII input.
        self._cdp.send("Input.insertText", text=text)
        if interval:
            self._sleep(interval)

    def click(self, x: int | None = None, y: int | None = None, button: str = "left") -> None:
        name = self._button(button)
        self._point(x, y)
        self._mouse("mouseMoved")
        self._mouse("mousePressed", name, 1)
        self._mouse("mouseReleased", name, 1)
        self._delivered += 1

    def doubleClick(self, x: int | None = None, y: int | None = None, button: str = "left") -> None:
        name = self._button(button)
        self._point(x, y)
        self._mouse("mouseMoved")
        self._mouse("mousePressed", name, 1)
        self._mouse("mouseReleased", name, 1)
        self._mouse("mousePressed", name, 2)
        self._mouse("mouseReleased", name, 2)
        self._delivered += 2

    def moveTo(self, x: int, y: int, _pause: bool = True) -> None:
        self._point(x, y)
        self._mouse("mouseMoved", self._held_button or "none")

    def dragTo(self, x: int, y: int, duration: float = 0.0, button: str = "left") -> None:
        name = self._button(button)
        self.mouseDown(name)
        try:
            start_x, start_y = self._x, self._y
            steps = max(1, int(max(0.0, duration) / 0.02)) if duration else 1
            for step in range(1, steps + 1):
                self._x = start_x + (float(x) - start_x) * step / steps
                self._y = start_y + (float(y) - start_y) * step / steps
                self._mouse("mouseMoved", name)
                if duration:
                    self._sleep(duration / steps)
        finally:
            self._point(x, y)
            self.mouseUp(name)

    def scroll(self, amount: int) -> None:
        if not amount:
            return
        # Match the desktop backend: one standard notch at a time, positive is up.
        notches = abs(int(amount))
        delta = -120 if amount > 0 else 120
        for _ in range(notches):
            self._mouse("mouseWheel", deltaX=0, deltaY=delta)
            self._delivered += 1

    def mouseDown(self, button: str = "left", _pause: bool = True) -> None:
        name = self._button(button)
        self._held_button = name
        self._mouse("mousePressed", name, 1)

    def mouseUp(self, button: str = "left", _pause: bool = True) -> None:
        name = self._button(button)
        self._held_button = None
        self._mouse("mouseReleased", name, 1)

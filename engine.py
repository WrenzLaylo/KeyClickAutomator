"""Core automation engine for KeyClick Automator."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
import random
import re
import threading
import time
from pathlib import Path
from typing import Callable, Iterable, Protocol


VALID_ACTIONS = {
    "key", "hotkey", "text", "left_click", "right_click",
    "double_click", "middle_click", "scroll", "drag",
}
DEFAULT_RESERVED_SHORTCUTS = {"f6", "f8", "f9"}
KEY_RE = re.compile(r"^[a-zA-Z0-9_+\-.,/\\;='\[\]` ]+$")
HOTKEY_NAMED_KEYS = {
    "alt", "alt_gr", "backspace", "caps_lock", "cmd", "ctrl", "delete",
    "down", "end", "enter", "esc", "home", "insert", "left", "menu",
    "num_lock", "page_down", "page_up", "pause", "right", "scroll_lock",
    "shift", "space", "tab", "up",
}
HOTKEY_MODIFIERS = {"alt", "alt_gr", "cmd", "ctrl", "shift"}
HOTKEY_ALIASES = {
    "control": "ctrl", "escape": "esc", "return": "enter",
    "windows": "cmd", "win": "cmd",
}


def _canonicalize_hotkey_parts(parts: Iterable[str]) -> str:
    modifier_order = {name: index for index, name in enumerate(("ctrl", "alt", "shift", "cmd", "alt_gr"))}
    canonical = sorted(parts, key=lambda part: (0, modifier_order[part]) if part in modifier_order else (1, part))
    return "+".join(canonical)


class AutomationBackend(Protocol):
    def press(self, key: str) -> None: ...
    def hotkey(self, *keys: str) -> None: ...
    def write(self, text: str, interval: float = 0.0, _pause: bool = True) -> None: ...
    def click(self, x: int | None = None, y: int | None = None, button: str = "left") -> None: ...
    def doubleClick(self, x: int | None = None, y: int | None = None, button: str = "left") -> None: ...
    def moveTo(self, x: int, y: int, _pause: bool = True) -> None: ...
    def dragTo(self, x: int, y: int, duration: float = 0.0, button: str = "left") -> None: ...
    def scroll(self, amount: int) -> None: ...
    def mouseDown(self, button: str = "left", _pause: bool = True) -> None: ...
    def mouseUp(self, button: str = "left", _pause: bool = True) -> None: ...


def validate_global_hotkey(value: str, label: str = "Hotkey") -> str:
    """Validate the subset accepted by pynput's Windows global-hotkey parser."""
    normalized = value.strip().lower().replace(" ", "")
    parts = normalized.split("+")
    if not normalized or any(not part for part in parts):
        raise ValueError(f"{label} is invalid.")
    parts = [HOTKEY_ALIASES.get(part, part) for part in parts]

    def valid_part(part: str) -> bool:
        if part in HOTKEY_NAMED_KEYS:
            return True
        if re.fullmatch(r"f(?:[1-9]|1[0-9]|2[0-4])", part):
            return True
        return len(part) == 1 and bool(re.fullmatch(r"[a-z0-9\-.,/\\;='\[\]`]", part))

    if any(not valid_part(part) for part in parts) or all(part in HOTKEY_MODIFIERS for part in parts):
        raise ValueError(f"{label} is invalid.")
    if len(set(parts)) != len(parts):
        raise ValueError(f"{label} is invalid.")
    return _canonicalize_hotkey_parts(parts)


def canonical_global_shortcuts(values: Iterable[str]) -> set[str]:
    """Return complete canonical chords reserved by the global controls."""
    return {validate_global_hotkey(value) for value in values}


@dataclass
class Action:
    kind: str
    value: str = ""
    x: int | None = None
    y: int | None = None
    x2: int | None = None
    y2: int | None = None
    amount: int = 0
    duration: float = 0.4
    repeats: int = 1
    delay_after: float = 0.1
    enabled: bool = True
    use_current_pointer: bool = False
    coordinate_space: str = "screen"
    reference_width: int = 0
    reference_height: int = 0
    reference_width2: int = 0
    reference_height2: int = 0

    def validate(self, reserved_shortcuts: set[str] | None = None) -> None:
        if self.kind not in VALID_ACTIONS:
            raise ValueError(f"Unsupported action: {self.kind}")
        if not 0 <= self.delay_after <= 3600:
            raise ValueError("Delay after each action must be between 0 and 3600 seconds.")
        if not 1 <= self.repeats <= 10_000:
            raise ValueError("Per-action repeats must be from 1 to 10,000.")
        if self.kind in {"key", "hotkey"}:
            value = self.value.strip()
            if not value or not KEY_RE.fullmatch(value):
                raise ValueError("Enter a valid key or hotkey, such as space, enter, a, or ctrl+shift+s.")
            raw_parts = [part.strip().lower() for part in value.split("+")]
            if self.kind == "key" and len(raw_parts) != 1:
                raise ValueError("A key action accepts one key only. Use a Hotkey action for combinations like ctrl+s.")
            if self.kind == "hotkey" and (len(raw_parts) < 2 or any(not part for part in raw_parts)):
                raise ValueError("A hotkey action requires at least two keys separated by +.")
            key_parts = [HOTKEY_ALIASES.get(part, part) for part in raw_parts]
            if len(set(key_parts)) != len(key_parts):
                raise ValueError("A key or hotkey cannot repeat the same key.")
            reserved = DEFAULT_RESERVED_SHORTCUTS if reserved_shortcuts is None else reserved_shortcuts
            action_parts = set(key_parts)
            conflicts = sorted(
                shortcut for shortcut in reserved
                if set(shortcut.split("+")).issubset(action_parts)
            )
            if conflicts:
                names = ", ".join(shortcut.upper() for shortcut in conflicts)
                raise ValueError(
                    f"{names} is reserved by the app's global controls and cannot be an action."
                )
        if self.kind == "text" and len(self.value) > 10_000:
            raise ValueError("Text actions are limited to 10,000 characters.")
        click_actions = {"left_click", "right_click", "double_click", "middle_click"}
        if self.coordinate_space not in {"screen", "window"}:
            raise ValueError("Mouse coordinate space must be screen or window.")
        if self.use_current_pointer and self.kind not in click_actions:
            raise ValueError("Follow current pointer is available only for click actions.")
        if self.use_current_pointer and self.coordinate_space != "screen":
            raise ValueError("Follow current pointer is available only for Desktop actions.")
        if self.reference_width < 0 or self.reference_height < 0:
            raise ValueError("Recorded window size cannot be negative.")
        if bool(self.reference_width) != bool(self.reference_height):
            raise ValueError("Recorded window size needs both width and height.")
        if self.reference_width2 < 0 or self.reference_height2 < 0:
            raise ValueError("Recorded destination window size cannot be negative.")
        if bool(self.reference_width2) != bool(self.reference_height2):
            raise ValueError("Recorded destination window size needs both width and height.")
        if self.kind in {"scroll", "drag"} or (self.kind in click_actions and not self.use_current_pointer):
            if self.x is None or self.y is None or self.x < 0 or self.y < 0:
                raise ValueError("Mouse actions need a recorded non-negative X/Y position.")
        if self.kind == "scroll":
            if self.amount == 0:
                raise ValueError("Scroll amount cannot be zero. Use a positive number for up or negative for down.")
            if abs(self.amount) > 1_000:
                raise ValueError("Scroll amount must be between -1000 and 1000 steps.")
        if self.kind == "drag":
            if self.x2 is None or self.y2 is None or self.x2 < 0 or self.y2 < 0:
                raise ValueError("Drag actions need a non-negative destination X/Y position.")
            if not 0 <= self.duration <= 60:
                raise ValueError("Drag duration must be between 0 and 60 seconds.")

    @property
    def label(self) -> str:
        names = {
            "key": "Key press",
            "hotkey": "Hotkey",
            "text": "Type text",
            "left_click": "Left click",
            "right_click": "Right click",
            "double_click": "Double click",
            "middle_click": "Middle click",
            "scroll": "Scroll",
            "drag": "Drag",
        }
        if self.kind == "drag":
            target = f"({self.x}, {self.y}) → ({self.x2}, {self.y2})"
        elif self.kind == "scroll":
            target = f"{self.amount:+d} at ({self.x}, {self.y})"
        elif self.kind in {"left_click", "right_click", "double_click", "middle_click"}:
            target = "current pointer" if self.use_current_pointer else f"({self.x}, {self.y})"
        else:
            target = self.value.replace("\n", "\\n")
            if len(target) > 36:
                target = target[:33] + "..."
        repeat = f" ×{self.repeats}" if self.repeats > 1 else ""
        return f"{names[self.kind]}{repeat}  {target}  | wait {self.delay_after:g}s"


@dataclass
class RunSettings:
    repeat_count: int = 1
    start_delay: float = 3.0
    cycle_interval: float = 0.0
    text_key_interval: float = 0.02
    delay_jitter: float = 0.0
    repeat_forever: bool = False
    start_hotkey: str = "f6"
    capture_hotkey: str = "f8"
    stop_hotkey: str = "f9"
    target_mode: str = "desktop"
    target_window_title: str = ""
    target_window_class: str = ""
    target_executable: str = ""

    def validate(self) -> None:
        if self.target_mode not in {"desktop", "window"}:
            raise ValueError("Target mode must be Desktop or Background window.")
        if not self.repeat_forever and not 1 <= self.repeat_count <= 1_000_000:
            raise ValueError("Repeat count must be from 1 to 1,000,000.")
        hotkeys = {
            "Start hotkey": self.start_hotkey,
            "Capture hotkey": self.capture_hotkey,
            "Stop hotkey": self.stop_hotkey,
        }
        normalized = []
        for label, value in hotkeys.items():
            normalized.append(validate_global_hotkey(value, label))
        if len(set(normalized)) != len(normalized):
            raise ValueError("Start, capture, and stop hotkeys must be different.")
        for label, value in {
            "Start timer": self.start_delay,
            "Cycle interval": self.cycle_interval,
            "Text key interval": self.text_key_interval,
            "Timing variation": self.delay_jitter,
        }.items():
            if not 0 <= value <= 3600:
                raise ValueError(f"{label} must be between 0 and 3600 seconds.")


def interruptible_sleep(seconds: float, stop_event: threading.Event) -> bool:
    """Sleep in short increments. Return False when cancellation is requested."""
    deadline = time.monotonic() + max(0.0, seconds)
    while True:
        if stop_event.is_set():
            return False
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return True
        stop_event.wait(min(remaining, 0.05))


def wait_until_resumed(
    stop_event: threading.Event,
    pause_event: threading.Event | None,
) -> bool:
    """Wait while paused and remain immediately cancellable."""
    while pause_event is not None and pause_event.is_set():
        if stop_event.wait(0.05):
            return False
    return not stop_event.is_set()


def pausable_sleep(
    seconds: float,
    stop_event: threading.Event,
    pause_event: threading.Event | None,
) -> bool:
    """Count only active time while respecting pause and cancellation events."""
    if pause_event is None:
        return interruptible_sleep(seconds, stop_event)

    remaining = max(0.0, seconds)
    previous = time.monotonic()
    while remaining > 0:
        if pause_event.is_set():
            if not wait_until_resumed(stop_event, pause_event):
                return False
            previous = time.monotonic()
            continue
        if stop_event.is_set():
            return False
        now = time.monotonic()
        remaining -= max(0.0, now - previous)
        previous = now
        if remaining <= 0:
            return True
        if stop_event.wait(min(remaining, 0.05)):
            return False
    return not stop_event.is_set()


class AutomationRunner:
    def __init__(self, backend: AutomationBackend, randomizer: Callable[[float, float], float] = random.uniform):
        self.backend = backend
        self.randomizer = randomizer

    def _jittered(self, seconds: float, jitter: float) -> float:
        if jitter <= 0:
            return seconds
        return max(0.0, seconds + self.randomizer(-jitter, jitter))

    def _release_drag_mouse(self, x: int, y: int) -> None:
        """Release a held button even when PyAutoGUI's corner fail-safe is active."""
        try:
            self.backend.mouseUp(button="left", _pause=False)
        except Exception:
            raw_release = getattr(getattr(self.backend, "_pyautogui_win", None), "_mouseUp", None)
            if raw_release is None:
                raise
            raw_release(x, y, "left")

    def _point_for_action(self, action: Action, destination: bool = False) -> tuple[int, int]:
        x = action.x2 if destination else action.x
        y = action.y2 if destination else action.y
        if x is None or y is None:
            raise ValueError("Mouse actions need a recorded X/Y position.")
        scaler = getattr(self.backend, "scale_point", None)
        if action.coordinate_space == "window" and callable(scaler):
            reference_width = action.reference_width2 if destination and action.reference_width2 else action.reference_width
            reference_height = action.reference_height2 if destination and action.reference_height2 else action.reference_height
            return scaler(x, y, reference_width, reference_height)
        return int(x), int(y)

    def execute_action(self, action: Action, text_key_interval: float, reserved_shortcuts: set[str] | None = None) -> None:
        action.validate(reserved_shortcuts)
        if action.kind == "key":
            self.backend.press(action.value.strip().lower())
        elif action.kind == "hotkey":
            keys = [part.strip().lower() for part in action.value.split("+") if part.strip()]
            if len(keys) < 2:
                raise ValueError("A hotkey requires at least two keys separated by +.")
            self.backend.hotkey(*keys)
        elif action.kind == "text":
            self.backend.write(action.value, interval=text_key_interval)
        elif action.kind == "left_click":
            point = (None, None) if action.use_current_pointer else self._point_for_action(action)
            self.backend.click(*point, button="left")
        elif action.kind == "right_click":
            point = (None, None) if action.use_current_pointer else self._point_for_action(action)
            self.backend.click(*point, button="right")
        elif action.kind == "double_click":
            point = (None, None) if action.use_current_pointer else self._point_for_action(action)
            self.backend.doubleClick(*point, button="left")
        elif action.kind == "middle_click":
            point = (None, None) if action.use_current_pointer else self._point_for_action(action)
            self.backend.click(*point, button="middle")
        elif action.kind == "scroll":
            self.backend.moveTo(*self._point_for_action(action))
            self.backend.scroll(action.amount)
        elif action.kind == "drag":
            self.backend.moveTo(*self._point_for_action(action))
            self.backend.dragTo(*self._point_for_action(action, destination=True), duration=action.duration, button="left")

    def _execute_interruptibly(
        self,
        action: Action,
        text_key_interval: float,
        stop_event: threading.Event,
        reserved_shortcuts: set[str],
        pause_event: threading.Event | None = None,
    ) -> bool:
        """Execute long actions in cancellable chunks and always release held input."""
        if action.kind == "text":
            action.validate(reserved_shortcuts)
            for character in action.value:
                if not wait_until_resumed(stop_event, pause_event):
                    return False
                self.backend.write(character, interval=0, _pause=False)
                if not pausable_sleep(text_key_interval, stop_event, pause_event):
                    return False
            return True

        if action.kind == "drag":
            action.validate(reserved_shortcuts)
            start_x, start_y = self._point_for_action(action)
            end_x, end_y = self._point_for_action(action, destination=True)
            self.backend.moveTo(start_x, start_y, _pause=False)
            self.backend.mouseDown(button="left", _pause=False)
            try:
                steps = max(1, math.ceil(action.duration / 0.02))
                step_delay = action.duration / steps
                for step in range(1, steps + 1):
                    # Finish an in-flight drag before pausing so a held mouse
                    # button is never left down indefinitely.
                    if stop_event.is_set():
                        return False
                    x = round(start_x + (end_x - start_x) * step / steps)
                    y = round(start_y + (end_y - start_y) * step / steps)
                    self.backend.moveTo(x, y, _pause=False)
                    if not interruptible_sleep(step_delay, stop_event):
                        return False
                return True
            finally:
                self._release_drag_mouse(end_x, end_y)

        if not wait_until_resumed(stop_event, pause_event):
            return False
        self.execute_action(action, text_key_interval, reserved_shortcuts)
        return not stop_event.is_set()

    def run(
        self,
        actions: list[Action],
        settings: RunSettings,
        stop_event: threading.Event,
        progress: Callable[[str, int, int], None] | None = None,
        pause_event: threading.Event | None = None,
        reserved_shortcuts: set[str] | None = None,
    ) -> bool:
        if not actions:
            raise ValueError("Add at least one action before starting.")
        settings.validate()
        if reserved_shortcuts is None:
            reserved_shortcuts = canonical_global_shortcuts(
                (settings.start_hotkey, settings.capture_hotkey, settings.stop_hotkey)
            )
        for action in actions:
            action.validate(reserved_shortcuts)

        total_cycles = 0 if settings.repeat_forever else settings.repeat_count
        if progress:
            progress("timer", 0, total_cycles)
        if not pausable_sleep(settings.start_delay, stop_event, pause_event):
            return False

        cycle = 0
        while settings.repeat_forever or cycle < settings.repeat_count:
            if not wait_until_resumed(stop_event, pause_event):
                return False
            cycle += 1
            if progress:
                progress("running", cycle, total_cycles)
            for action_index, action in enumerate(actions):
                if not action.enabled:
                    continue
                if not wait_until_resumed(stop_event, pause_event):
                    return False
                if progress:
                    progress("action", action_index, len(actions))
                for _ in range(action.repeats):
                    if not wait_until_resumed(stop_event, pause_event):
                        return False
                    if not self._execute_interruptibly(
                        action,
                        settings.text_key_interval,
                        stop_event,
                        reserved_shortcuts,
                        pause_event,
                    ):
                        return False
                    delay = self._jittered(action.delay_after, settings.delay_jitter)
                    if not pausable_sleep(delay, stop_event, pause_event):
                        return False
            cycle_delay = self._jittered(settings.cycle_interval, settings.delay_jitter)
            has_next_cycle = settings.repeat_forever or cycle < settings.repeat_count
            if has_next_cycle and not pausable_sleep(
                cycle_delay,
                stop_event,
                pause_event,
            ):
                return False
        return True


def save_profile(path: str | Path, actions: list[Action], settings: RunSettings) -> None:
    payload = {
        "version": 1,
        "actions": [asdict(a) for a in actions],
        "settings": asdict(settings),
    }
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_profile(path: str | Path) -> tuple[list[Action], RunSettings]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("version") != 1:
        raise ValueError("Unsupported profile version.")
    settings = RunSettings(**payload.get("settings", {}))
    actions = [Action(**item) for item in payload.get("actions", [])]
    settings.validate()
    reserved_shortcuts = canonical_global_shortcuts(
        (settings.start_hotkey, settings.capture_hotkey, settings.stop_hotkey)
    )
    for action in actions:
        action.validate(reserved_shortcuts)
    return actions, settings

"""Core automation engine for KeyClick Automator."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import random
import re
import threading
import time
from pathlib import Path
from typing import Callable, Protocol


VALID_ACTIONS = {
    "key", "hotkey", "text", "left_click", "right_click",
    "double_click", "middle_click", "scroll", "drag",
}
DEFAULT_RESERVED_KEYS = {"f6", "f8", "f9"}
KEY_RE = re.compile(r"^[a-zA-Z0-9_+\-.,/\\;='\[\]` ]+$")


class AutomationBackend(Protocol):
    def press(self, key: str) -> None: ...
    def hotkey(self, *keys: str) -> None: ...
    def write(self, text: str, interval: float = 0.0) -> None: ...
    def click(self, x: int, y: int, button: str = "left") -> None: ...
    def doubleClick(self, x: int, y: int, button: str = "left") -> None: ...
    def moveTo(self, x: int, y: int) -> None: ...
    def dragTo(self, x: int, y: int, duration: float = 0.0, button: str = "left") -> None: ...
    def scroll(self, amount: int) -> None: ...


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

    def validate(self, reserved_keys: set[str] | None = None) -> None:
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
            key_parts = {part.strip().lower() for part in value.split("+")}
            reserved = key_parts & (DEFAULT_RESERVED_KEYS if reserved_keys is None else reserved_keys)
            if reserved:
                names = ", ".join(sorted(key.upper() for key in reserved))
                raise ValueError(f"{names} is reserved by the app's global controls and cannot be an action.")
        if self.kind == "text" and len(self.value) > 10_000:
            raise ValueError("Text actions are limited to 10,000 characters.")
        if self.kind in {"left_click", "right_click", "double_click", "middle_click", "scroll", "drag"}:
            if self.x is None or self.y is None or self.x < 0 or self.y < 0:
                raise ValueError("Mouse actions need a recorded non-negative X/Y position.")
        if self.kind == "scroll" and self.amount == 0:
            raise ValueError("Scroll amount cannot be zero. Use a positive number for up or negative for down.")
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
            target = f"({self.x}, {self.y})"
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

    def validate(self) -> None:
        if not self.repeat_forever and not 1 <= self.repeat_count <= 1_000_000:
            raise ValueError("Repeat count must be from 1 to 1,000,000.")
        hotkeys = {
            "Start hotkey": self.start_hotkey,
            "Capture hotkey": self.capture_hotkey,
            "Stop hotkey": self.stop_hotkey,
        }
        normalized = []
        for label, value in hotkeys.items():
            value = value.strip().lower()
            if not value or not KEY_RE.fullmatch(value):
                raise ValueError(f"{label} is invalid.")
            normalized.append(value)
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


class AutomationRunner:
    def __init__(self, backend: AutomationBackend, randomizer: Callable[[float, float], float] = random.uniform):
        self.backend = backend
        self.randomizer = randomizer

    def _jittered(self, seconds: float, jitter: float) -> float:
        if jitter <= 0:
            return seconds
        return max(0.0, seconds + self.randomizer(-jitter, jitter))

    def execute_action(self, action: Action, text_key_interval: float, reserved_keys: set[str] | None = None) -> None:
        action.validate(reserved_keys)
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
            self.backend.click(action.x, action.y, button="left")
        elif action.kind == "right_click":
            self.backend.click(action.x, action.y, button="right")
        elif action.kind == "double_click":
            self.backend.doubleClick(action.x, action.y, button="left")
        elif action.kind == "middle_click":
            self.backend.click(action.x, action.y, button="middle")
        elif action.kind == "scroll":
            self.backend.moveTo(action.x, action.y)
            self.backend.scroll(action.amount)
        elif action.kind == "drag":
            self.backend.moveTo(action.x, action.y)
            self.backend.dragTo(action.x2, action.y2, duration=action.duration, button="left")

    def run(
        self,
        actions: list[Action],
        settings: RunSettings,
        stop_event: threading.Event,
        progress: Callable[[str, int, int], None] | None = None,
    ) -> bool:
        if not actions:
            raise ValueError("Add at least one action before starting.")
        settings.validate()
        reserved_keys = {
            part.strip().lower()
            for shortcut in (settings.start_hotkey, settings.capture_hotkey, settings.stop_hotkey)
            for part in shortcut.split("+")
        }
        for action in actions:
            action.validate(reserved_keys)

        total_cycles = 0 if settings.repeat_forever else settings.repeat_count
        if progress:
            progress("timer", 0, total_cycles)
        if not interruptible_sleep(settings.start_delay, stop_event):
            return False

        cycle = 0
        while settings.repeat_forever or cycle < settings.repeat_count:
            cycle += 1
            if progress:
                progress("running", cycle, total_cycles)
            for action in actions:
                if not action.enabled:
                    continue
                for _ in range(action.repeats):
                    if stop_event.is_set():
                        return False
                    self.execute_action(action, settings.text_key_interval, reserved_keys)
                    delay = self._jittered(action.delay_after, settings.delay_jitter)
                    if not interruptible_sleep(delay, stop_event):
                        return False
            cycle_delay = self._jittered(settings.cycle_interval, settings.delay_jitter)
            has_next_cycle = settings.repeat_forever or cycle < settings.repeat_count
            if has_next_cycle and not interruptible_sleep(cycle_delay, stop_event):
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
    reserved_keys = {
        part.strip().lower()
        for shortcut in (settings.start_hotkey, settings.capture_hotkey, settings.stop_hotkey)
        for part in shortcut.split("+")
    }
    for action in actions:
        action.validate(reserved_keys)
    settings.validate()
    return actions, settings

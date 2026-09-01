"""Answer "will this actually work?" before a run, instead of after it.

KeyClick's worst failure mode is not crashing -- it is running perfectly and
delivering nothing: a click recorded at (0, 0), or window messages posted at a
browser that cannot receive them. Both report Complete. These checks turn that
class of silent failure into something the user is told before they commit.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from engine import Action, RunSettings, canonical_global_shortcuts

PASS = "pass"
WARN = "warn"
FAIL = "fail"

MOUSE_KINDS = {"left_click", "right_click", "double_click", "middle_click", "scroll", "drag"}

# Browsers paint page content with their own compositor, leaving no child window
# under it to receive a posted mouse message. Targeting them in window mode looks
# like it works and delivers nothing.
_BROWSER_EXECUTABLES = {
    "chrome", "msedge", "firefox", "brave", "opera", "vivaldi", "chromium", "arc"
}
_BROWSER_WINDOW_CLASSES = {"Chrome_WidgetWin_1", "MozillaWindowClass"}

_EXPECTED_SPACE = {"desktop": "screen", "window": "window", "browser": "viewport"}
_SPACE_NAME = {
    "screen": "the desktop",
    "window": "the selected window",
    "viewport": "the selected browser tab",
}


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: str
    remedy: str = ""

    @property
    def blocking(self) -> bool:
        return self.status == FAIL

    def as_entry(self) -> dict[str, str]:
        return {
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
            "remedy": self.remedy,
        }


def looks_like_a_browser(window_title: str = "", window_class: str = "", executable: str = "") -> bool:
    if window_class in _BROWSER_WINDOW_CLASSES:
        return True
    stem = Path(executable).stem.lower() if executable else ""
    return stem in _BROWSER_EXECUTABLES


def _check_actions(actions: Iterable[Action]) -> Check:
    enabled = [action for action in actions if action.enabled]
    if not enabled:
        return Check(
            "Actions", FAIL,
            "No enabled actions in this sequence.",
            "Add an action, or switch one back on.",
        )
    return Check("Actions", PASS, f"{len(enabled)} enabled.")


def _check_positions(actions: Iterable[Action]) -> Check:
    missing: list[int] = []
    for index, action in enumerate(actions, start=1):
        if not action.enabled or action.kind not in MOUSE_KINDS:
            continue
        if action.use_current_pointer:
            continue
        if action.x is None or action.y is None:
            missing.append(index)
        elif action.x == 0 and action.y == 0 and not action.reference_width:
            # The editor defaults X and Y to 0, so an unrecorded click looks valid
            # and lands on the target's top-left corner.
            missing.append(index)
    if missing:
        steps = ", ".join(str(index) for index in missing)
        return Check(
            "Positions", FAIL,
            f"Step {steps} has no recorded position, so it would click the target's corner.",
            "Open the step and use Pick pointer position.",
        )
    return Check("Positions", PASS, "Every pointer action has a recorded position.")


def _check_coordinate_space(actions: Iterable[Action], settings: RunSettings) -> Check:
    expected = _EXPECTED_SPACE.get(settings.target_mode, "screen")
    mismatched: list[int] = []
    for index, action in enumerate(actions, start=1):
        if not action.enabled or action.kind not in MOUSE_KINDS:
            continue
        if action.use_current_pointer:
            continue
        if action.coordinate_space != expected:
            mismatched.append(index)
    if mismatched:
        steps = ", ".join(str(index) for index in mismatched)
        return Check(
            "Recorded for this target", FAIL,
            f"Step {steps} was recorded for a different target.",
            f"Record those positions again for {_SPACE_NAME[expected]}.",
        )
    return Check("Recorded for this target", PASS, f"Positions match {_SPACE_NAME[expected]}.")


def _check_shortcuts(actions: Iterable[Action], settings: RunSettings) -> Check:
    reserved = canonical_global_shortcuts(
        (settings.start_hotkey, settings.capture_hotkey, settings.stop_hotkey)
    )
    for index, action in enumerate(actions, start=1):
        if not action.enabled:
            continue
        try:
            action.validate(reserved)
        except ValueError as exc:
            return Check("Shortcuts", FAIL, f"Step {index}: {exc}", "Choose a different key.")
    return Check("Shortcuts", PASS, "No action collides with the global controls.")


def _check_target(
    settings: RunSettings,
    resolve_window: Callable[[], object] | None,
    resolve_tab: Callable[[], object] | None,
) -> list[Check]:
    if settings.target_mode == "desktop":
        return [
            Check("Target", PASS, "The desktop, using your real pointer."),
            Check(
                "Delivery", WARN,
                "Desktop actions move your physical mouse and keyboard.",
                "Keep your hands clear, or use a window or browser-tab target.",
            ),
        ]

    if settings.target_mode == "browser":
        if not settings.target_tab_url.strip():
            return [Check("Target", FAIL, "No browser tab chosen.", "Pick a tab in Run settings.")]
        if resolve_tab is None:
            return [Check("Target", PASS, settings.target_tab_title or settings.target_tab_url)]
        try:
            tab = resolve_tab()
        except Exception as exc:
            return [Check("Target", FAIL, str(exc), "Open the tab, then Refresh the tab list.")]
        label = getattr(tab, "title", "") or getattr(tab, "url", "") or "the selected tab"
        return [
            Check("Target", PASS, label),
            Check("Delivery", PASS, "Input goes to this tab only; your pointer stays free."),
        ]

    # Background-window mode.
    if not any((settings.target_window_title, settings.target_window_class, settings.target_executable)):
        return [Check("Target", FAIL, "No window chosen.", "Pick a window in Run settings.")]

    checks: list[Check] = []
    info = None
    if resolve_window is not None:
        try:
            info = resolve_window()
        except Exception as exc:
            return [Check("Target", FAIL, str(exc), "Open the window, then pick it again.")]
    title = getattr(info, "title", settings.target_window_title)
    window_class = getattr(info, "class_name", settings.target_window_class)
    executable = getattr(info, "executable", settings.target_executable)
    checks.append(Check("Target", PASS, title or window_class or "the selected window"))

    if looks_like_a_browser(title, window_class, executable):
        checks.append(
            Check(
                "Delivery", FAIL,
                "This is a browser window. Browsers draw pages with their own "
                "compositor, so background messages never reach the page.",
                "Switch this profile to Browser tab mode and pick the tab.",
            )
        )
    else:
        checks.append(
            Check(
                "Delivery", WARN,
                "Background messages suit standard Windows controls. Games and "
                "custom-drawn apps may ignore them.",
                "Use Test once before trusting a long run.",
            )
        )
    return checks


def preflight(
    actions: list[Action],
    settings: RunSettings,
    resolve_window: Callable[[], object] | None = None,
    resolve_tab: Callable[[], object] | None = None,
) -> list[Check]:
    """Every check, in the order a user would reason about them."""
    checks = [
        _check_actions(actions),
        _check_positions(actions),
        _check_coordinate_space(actions, settings),
        _check_shortcuts(actions, settings),
    ]
    checks.extend(_check_target(settings, resolve_window, resolve_tab))
    return checks


def blocking_failures(checks: Iterable[Check]) -> list[Check]:
    return [check for check in checks if check.blocking]


def summarize(checks: Iterable[Check]) -> str:
    checks = list(checks)
    failures = blocking_failures(checks)
    if failures:
        return failures[0].detail
    if any(check.status == WARN for check in checks):
        return "Ready, with cautions"
    return "Ready"

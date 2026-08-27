import json
import threading
from pathlib import Path

import pytest
import pyautogui

from engine import Action, AutomationRunner, RunSettings, load_profile, save_profile


class FakeBackend:
    def __init__(self):
        self.calls = []

    def press(self, key):
        self.calls.append(("press", key))

    def hotkey(self, *keys):
        self.calls.append(("hotkey", *keys))

    def write(self, text, interval=0.0, _pause=True):
        self.calls.append(("write", text, interval))

    def click(self, x, y, button="left"):
        self.calls.append(("click", x, y, button))

    def doubleClick(self, x, y, button="left"):
        self.calls.append(("doubleClick", x, y, button))

    def moveTo(self, x, y, _pause=True):
        self.calls.append(("moveTo", x, y))

    def dragTo(self, x, y, duration=0.0, button="left"):
        self.calls.append(("dragTo", x, y, duration, button))

    def scroll(self, amount):
        self.calls.append(("scroll", amount))

    def mouseDown(self, button="left", _pause=True):
        self.calls.append(("mouseDown", button))

    def mouseUp(self, button="left", _pause=True):
        self.calls.append(("mouseUp", button))


def test_action_validation():
    assert Action("key", "space").value == "space"
    Action("key", value="space").validate()
    Action("hotkey", value="ctrl+shift+s").validate()
    Action("left_click", x=100, y=200).validate()
    with pytest.raises(ValueError):
        Action("left_click", x=None, y=2).validate()
    with pytest.raises(ValueError):
        Action("key", value="").validate()
    with pytest.raises(ValueError):
        Action("key", value="f9").validate()
    with pytest.raises(ValueError):
        Action("hotkey", value="ctrl+f8").validate()


def test_runner_executes_sequence_exact_number_of_times():
    backend = FakeBackend()
    runner = AutomationRunner(backend)
    actions = [
        Action("key", value="A", delay_after=0),
        Action("hotkey", value="ctrl+s", delay_after=0),
        Action("text", value="hello", delay_after=0),
        Action("left_click", x=12, y=34, delay_after=0),
        Action("right_click", x=56, y=78, delay_after=0),
    ]
    done = runner.run(actions, RunSettings(repeat_count=2, start_delay=0, cycle_interval=0, text_key_interval=0.03), threading.Event())
    assert done is True
    expected_once = [
        ("press", "a"),
        ("hotkey", "ctrl", "s"),
        ("write", "h", 0),
        ("write", "e", 0),
        ("write", "l", 0),
        ("write", "l", 0),
        ("write", "o", 0),
        ("click", 12, 34, "left"),
        ("click", 56, 78, "right"),
    ]
    assert backend.calls == expected_once * 2


def test_runner_honors_preexisting_stop():
    backend = FakeBackend()
    stop = threading.Event()
    stop.set()
    done = AutomationRunner(backend).run([Action("key", value="x")], RunSettings(start_delay=0), stop)
    assert done is False
    assert backend.calls == []


def test_profile_round_trip(tmp_path: Path):
    path = tmp_path / "demo.kca.json"
    original_actions = [Action("right_click", x=321, y=654, delay_after=0.25)]
    original_settings = RunSettings(repeat_count=7, start_delay=1.5, cycle_interval=0.2, text_key_interval=0.04)
    save_profile(path, original_actions, original_settings)
    actions, settings = load_profile(path)
    assert actions == original_actions
    assert settings == original_settings
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 1


def test_advanced_mouse_actions():
    backend = FakeBackend()
    runner = AutomationRunner(backend)
    actions = [
        Action("double_click", x=10, y=20, delay_after=0),
        Action("middle_click", x=30, y=40, delay_after=0),
        Action("scroll", x=50, y=60, amount=-4, delay_after=0),
        Action("drag", x=70, y=80, x2=170, y2=180, duration=0, delay_after=0),
    ]
    assert runner.run(actions, RunSettings(start_delay=0), threading.Event()) is True
    assert backend.calls == [
        ("doubleClick", 10, 20, "left"),
        ("click", 30, 40, "middle"),
        ("moveTo", 50, 60),
        ("scroll", -4),
        ("moveTo", 70, 80),
        ("mouseDown", "left"),
        ("moveTo", 170, 180),
        ("mouseUp", "left"),
    ]


def test_window_mouse_actions_use_resize_aware_coordinates_at_execution_time():
    class ResponsiveBackend(FakeBackend):
        def scale_point(self, x, y, reference_width, reference_height):
            self.calls.append(("scale_point", x, y, reference_width, reference_height))
            return x // 2, y // 2

    backend = ResponsiveBackend()
    action = Action(
        "left_click",
        x=600,
        y=400,
        coordinate_space="window",
        reference_width=1200,
        reference_height=800,
        delay_after=0,
    )

    assert AutomationRunner(backend).run([action], RunSettings(start_delay=0), threading.Event()) is True
    assert backend.calls == [
        ("scale_point", 600, 400, 1200, 800),
        ("click", 300, 200, "left"),
    ]


def test_drag_points_keep_independent_window_size_references():
    class ResponsiveDragBackend(FakeBackend):
        def scale_point(self, x, y, reference_width, reference_height):
            self.calls.append(("scale_point", x, y, reference_width, reference_height))
            return round(x * 1000 / reference_width), round(y * 1000 / reference_height)

    backend = ResponsiveDragBackend()
    action = Action(
        "drag",
        x=600,
        y=400,
        x2=300,
        y2=200,
        duration=0,
        coordinate_space="window",
        reference_width=1200,
        reference_height=800,
        reference_width2=600,
        reference_height2=400,
        delay_after=0,
    )

    assert AutomationRunner(backend).run([action], RunSettings(start_delay=0), threading.Event()) is True
    assert backend.calls[:2] == [
        ("scale_point", 600, 400, 1200, 800),
        ("scale_point", 300, 200, 600, 400),
    ]
    assert backend.calls[2:] == [
        ("moveTo", 500, 500),
        ("mouseDown", "left"),
        ("moveTo", 500, 500),
        ("mouseUp", "left"),
    ]


def test_click_actions_can_follow_the_live_pointer():
    backend = FakeBackend()
    actions = [
        Action("left_click", use_current_pointer=True, delay_after=0),
        Action("right_click", use_current_pointer=True, delay_after=0),
        Action("double_click", use_current_pointer=True, delay_after=0),
        Action("middle_click", use_current_pointer=True, delay_after=0),
    ]

    assert AutomationRunner(backend).run(actions, RunSettings(start_delay=0), threading.Event()) is True
    assert backend.calls == [
        ("click", None, None, "left"),
        ("click", None, None, "right"),
        ("doubleClick", None, None, "left"),
        ("click", None, None, "middle"),
    ]
    with pytest.raises(ValueError, match="only for click actions"):
        Action("scroll", amount=-1, use_current_pointer=True).validate()


def test_scroll_amount_is_bounded_to_prevent_accidental_message_floods():
    Action("scroll", x=10, y=20, amount=-1_000).validate()
    Action("scroll", x=10, y=20, amount=1_000).validate()
    with pytest.raises(ValueError, match="between -1000 and 1000"):
        Action("scroll", x=10, y=20, amount=1_001).validate()


def test_progress_reports_the_action_being_executed():
    events = []
    actions = [
        Action("key", value="x", enabled=False, delay_after=0),
        Action("key", value="y", delay_after=0),
    ]

    assert AutomationRunner(FakeBackend()).run(
        actions,
        RunSettings(start_delay=0),
        threading.Event(),
        lambda phase, current, total: events.append((phase, current, total)),
    ) is True
    assert ("action", 1, 2) in events
    assert not any(event == ("action", 0, 2) for event in events)


def test_per_action_repeat_runs_only_that_action_multiple_times():
    backend = FakeBackend()
    actions = [Action("key", value="x", repeats=3, delay_after=0)]
    assert AutomationRunner(backend).run(actions, RunSettings(start_delay=0), threading.Event()) is True
    assert backend.calls == [("press", "x"), ("press", "x"), ("press", "x")]


def test_timing_jitter_uses_injected_randomizer(monkeypatch):
    sleeps = []
    monkeypatch.setattr("engine.interruptible_sleep", lambda seconds, stop: sleeps.append(seconds) or True)
    backend = FakeBackend()
    runner = AutomationRunner(backend, randomizer=lambda low, high: high)
    actions = [Action("key", value="x", delay_after=1.0)]
    settings = RunSettings(repeat_count=2, start_delay=0, cycle_interval=2.0, delay_jitter=0.25)
    assert runner.run(actions, settings, threading.Event()) is True
    assert sleeps == [0, 1.25, 2.25, 1.25]


def test_disabled_actions_are_preserved_but_not_executed():
    backend = FakeBackend()
    actions = [
        Action("key", value="x", enabled=False, delay_after=0),
        Action("key", value="y", enabled=True, delay_after=0),
    ]
    assert AutomationRunner(backend).run(actions, RunSettings(start_delay=0), threading.Event()) is True
    assert backend.calls == [("press", "y")]


def test_repeat_forever_runs_until_cancelled():
    backend = FakeBackend()
    stop = threading.Event()

    class StoppingRunner(AutomationRunner):
        def execute_action(self, action, text_key_interval, reserved_keys=None):
            super().execute_action(action, text_key_interval, reserved_keys)
            if len(backend.calls) == 3:
                stop.set()

    settings = RunSettings(start_delay=0, repeat_forever=True)
    assert StoppingRunner(backend).run([Action("key", value="x", delay_after=0)], settings, stop) is False
    assert backend.calls == [("press", "x"), ("press", "x"), ("press", "x")]


def test_run_settings_reject_duplicate_hotkeys():
    with pytest.raises(ValueError, match="must be different"):
        RunSettings(start_hotkey="f6", capture_hotkey="f6", stop_hotkey="f9").validate()


def test_run_settings_accept_legacy_hotkey_aliases_and_detects_alias_duplicates():
    RunSettings(start_hotkey="control+s", capture_hotkey="escape", stop_hotkey="f9").validate()
    with pytest.raises(ValueError, match="must be different"):
        RunSettings(start_hotkey="control+s", capture_hotkey="ctrl+s", stop_hotkey="f9").validate()
    with pytest.raises(ValueError, match="must be different"):
        RunSettings(start_hotkey="ctrl+s", capture_hotkey="s+control", stop_hotkey="f9").validate()


def test_global_hotkey_rejects_repeated_components():
    with pytest.raises(ValueError, match="invalid"):
        RunSettings(start_hotkey="ctrl+ctrl+s").validate()


@pytest.mark.parametrize("hotkey", ["foo", "ctrl++s", "f25"])
def test_run_settings_reject_hotkeys_that_pynput_cannot_parse(hotkey):
    with pytest.raises(ValueError, match="hotkey is invalid"):
        RunSettings(start_hotkey=hotkey).validate()


def test_long_text_action_can_be_stopped_between_characters():
    stop = threading.Event()

    class StoppingTextBackend(FakeBackend):
        def write(self, text, interval=0.0, _pause=True):
            super().write(text, interval, _pause)
            stop.set()

    backend = StoppingTextBackend()
    done = AutomationRunner(backend).run(
        [Action("text", value="dangerously long", delay_after=0)],
        RunSettings(start_delay=0, text_key_interval=0),
        stop,
    )
    assert done is False
    assert backend.calls == [("write", "d", 0)]


def test_drag_releases_mouse_when_emergency_stop_occurs_mid_drag():
    stop = threading.Event()

    class StoppingDragBackend(FakeBackend):
        def mouseDown(self, button="left", _pause=True):
            super().mouseDown(button, _pause)
            stop.set()

    backend = StoppingDragBackend()
    done = AutomationRunner(backend).run(
        [Action("drag", x=0, y=0, x2=500, y2=500, duration=5, delay_after=0)],
        RunSettings(start_delay=0),
        stop,
    )
    assert done is False
    assert backend.calls == [("moveTo", 0, 0), ("mouseDown", "left"), ("mouseUp", "left")]


def test_chunked_text_and_drag_disable_pyautogui_global_pause():
    class PauseAwareBackend(FakeBackend):
        def __init__(self):
            super().__init__()
            self.pause_flags = []

        def write(self, text, interval=0.0, _pause=True):
            self.pause_flags.append(_pause)
            super().write(text, interval, _pause)

        def moveTo(self, x, y, _pause=True):
            self.pause_flags.append(_pause)
            super().moveTo(x, y, _pause)

        def mouseDown(self, button="left", _pause=True):
            self.pause_flags.append(_pause)
            super().mouseDown(button, _pause)

        def mouseUp(self, button="left", _pause=True):
            self.pause_flags.append(_pause)
            super().mouseUp(button, _pause)

    backend = PauseAwareBackend()
    actions = [
        Action("text", value="ab", delay_after=0),
        Action("drag", x=0, y=0, x2=10, y2=10, duration=0, delay_after=0),
    ]
    assert AutomationRunner(backend).run(actions, RunSettings(start_delay=0, text_key_interval=0), threading.Event()) is True
    assert backend.pause_flags == [False, False, False, False, False, False]


def test_drag_fail_safe_uses_raw_mouse_release_cleanup():
    raw_releases = []

    class RawWindowsBackend:
        @staticmethod
        def _mouseUp(x, y, button):
            raw_releases.append((x, y, button))

    class FailSafeBackend(FakeBackend):
        _pyautogui_win = RawWindowsBackend()

        def moveTo(self, x, y, _pause=True):
            if self.calls:
                raise pyautogui.FailSafeException("corner")
            super().moveTo(x, y, _pause)

        def mouseUp(self, button="left", _pause=True):
            raise pyautogui.FailSafeException("corner")

    backend = FailSafeBackend()
    with pytest.raises(pyautogui.FailSafeException):
        AutomationRunner(backend).run(
            [Action("drag", x=0, y=0, x2=10, y2=10, duration=0, delay_after=0)],
            RunSettings(start_delay=0),
            threading.Event(),
        )
    assert raw_releases == [(10, 10, "left")]


def test_old_profile_defaults_new_run_settings(tmp_path: Path):
    path = tmp_path / "old.kca.json"
    path.write_text(json.dumps({
        "version": 1,
        "actions": [{"kind": "key", "value": "a"}],
        "settings": {"repeat_count": 2},
    }), encoding="utf-8")
    _, settings = load_profile(path)
    assert settings.repeat_forever is False
    assert (settings.start_hotkey, settings.capture_hotkey, settings.stop_hotkey) == ("f6", "f8", "f9")


def test_custom_shortcuts_allow_old_default_key_as_action(tmp_path: Path):
    path = tmp_path / "custom.kca.json"
    actions = [Action("key", value="f6", delay_after=0)]
    settings = RunSettings(start_delay=0, start_hotkey="f10", capture_hotkey="f11", stop_hotkey="f12")
    save_profile(path, actions, settings)
    loaded_actions, loaded_settings = load_profile(path)
    backend = FakeBackend()
    assert AutomationRunner(backend).run(loaded_actions, loaded_settings, threading.Event()) is True
    assert backend.calls == [("press", "f6")]


def test_mouse_coordinate_space_is_explicit_and_live_pointer_stays_desktop_only():
    Action("left_click", x=10, y=20, coordinate_space="window").validate()
    Action(
        "left_click",
        x=10,
        y=20,
        coordinate_space="window",
        reference_width=800,
        reference_height=600,
    ).validate()
    with pytest.raises(ValueError, match="screen or window"):
        Action("left_click", x=10, y=20, coordinate_space="unknown").validate()
    with pytest.raises(ValueError, match="only for Desktop"):
        Action("left_click", use_current_pointer=True, coordinate_space="window").validate()
    with pytest.raises(ValueError, match="both width and height"):
        Action("left_click", x=10, y=20, coordinate_space="window", reference_width=800).validate()


def test_background_target_round_trips_with_window_relative_actions(tmp_path: Path):
    path = tmp_path / "background.kca.json"
    actions = [Action(
        "left_click",
        x=45,
        y=67,
        coordinate_space="window",
        reference_width=1024,
        reference_height=768,
    )]
    settings = RunSettings(
        target_mode="window",
        target_window_title="Calculator",
        target_window_class="ApplicationFrameWindow",
        target_executable=r"C:\\Windows\\System32\\ApplicationFrameHost.exe",
    )

    save_profile(path, actions, settings)
    loaded_actions, loaded_settings = load_profile(path)

    assert loaded_actions == actions
    assert loaded_settings == settings


def test_legacy_profile_defaults_to_desktop_screen_coordinates(tmp_path: Path):
    path = tmp_path / "legacy-mouse.kca.json"
    path.write_text(json.dumps({
        "version": 1,
        "actions": [{"kind": "left_click", "x": 12, "y": 34}],
        "settings": {},
    }), encoding="utf-8")

    actions, settings = load_profile(path)

    assert actions[0].coordinate_space == "screen"
    assert actions[0].reference_width == 0
    assert actions[0].reference_height == 0
    assert actions[0].reference_width2 == 0
    assert actions[0].reference_height2 == 0
    assert settings.target_mode == "desktop"

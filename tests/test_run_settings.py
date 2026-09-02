"""What a profile stores: run settings, global shortcuts, and coordinate space.

Nothing here starts a run -- these are about what survives being written to a
file and read back."""

from pathlib import Path
import json

import pytest

from engine import Action
from engine import RunSettings
from engine import load_profile
from engine import save_profile


def test_profile_round_trip(tmp_path: Path):
    path = tmp_path / "demo.kca.json"
    original_actions = [Action("right_click", x=321, y=654, delay_after=0.25)]
    original_settings = RunSettings(repeat_count=7, start_delay=1.5, cycle_interval=0.2, text_key_interval=0.04)
    save_profile(path, original_actions, original_settings)
    actions, settings = load_profile(path)
    assert actions == original_actions
    assert settings == original_settings
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 1

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
    with pytest.raises(ValueError, match="screen, window, or viewport"):
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

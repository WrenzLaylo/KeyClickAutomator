import json
import os

from engine import Action, RunSettings, save_profile
from profile_catalog import list_profile_entries, profile_name
from recovery_store import (
    describe_recovery_draft,
    read_recovery_payload,
    remove_recovery_draft,
    write_recovery_draft,
)
from shortcut_service import global_shortcut_conflicts, pynput_hotkey


def test_profile_catalog_filters_plain_json_and_sorts_newest_first(tmp_path):
    older = tmp_path / "Older.kca.json"
    newer = tmp_path / "Newer.kca.json"
    save_profile(older, [Action("key", value="a", enabled=False)], RunSettings())
    save_profile(newer, [Action("key", value="b")], RunSettings())
    (tmp_path / "unrelated.json").write_text("not a profile", encoding="utf-8")
    (tmp_path / "Broken.kca.json").write_text("not a profile", encoding="utf-8")
    os.utime(older, (100, 100))
    os.utime(newer, (200, 200))

    entries = list_profile_entries(tmp_path)

    assert [entry["name"] for entry in entries] == ["Broken", "Newer", "Older"]
    assert entries[1]["actionCount"] == 1
    assert entries[1]["activeCount"] == 1
    assert entries[2]["activeCount"] == 0
    assert entries[0]["valid"] is False
    assert profile_name("Example.kca.json") == "Example"


def test_recovery_store_round_trip_and_cleanup(tmp_path):
    path = tmp_path / "state" / "recovery-draft.kca.json"
    actions = [Action("hotkey", value="ctrl+c")]
    settings = RunSettings(start_delay=0)

    write_recovery_draft(path, actions, settings, "Morning", None)

    payload = read_recovery_payload(path)
    assert payload["profile_name"] == "Morning"
    assert payload["actions"][0]["value"] == "ctrl+c"
    assert describe_recovery_draft(path) == "Morning · 1 action"
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 1

    remove_recovery_draft(path)
    assert path.exists() is False


def test_shortcut_service_canonicalizes_conflicts_and_pynput_syntax():
    result = global_shortcut_conflicts("control+s", "s+ctrl", "f9")

    assert result["hasConflict"] is True
    assert result["startConflict"] is True
    assert result["captureConflict"] is True
    assert result["stopConflict"] is False
    assert pynput_hotkey("control+shift+s") == "<ctrl>+<shift>+s"

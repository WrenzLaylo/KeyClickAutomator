import json
from datetime import datetime

import pytest

from engine import Action, RunSettings, load_profile, save_profile
from profile_history import (
    HISTORY_DIR_NAME,
    history_directory,
    restore,
    snapshot,
    versions,
)


def write(path, values):
    save_profile(path, [Action("key", value=v) for v in values], RunSettings(start_delay=0))


def test_a_new_profile_has_nothing_to_snapshot(tmp_path):
    assert snapshot(tmp_path / "Nothing.kca.json") is None
    assert versions(tmp_path / "Nothing.kca.json") == []


def test_saving_over_a_profile_keeps_what_was_there_before(tmp_path):
    path = tmp_path / "Mine.kca.json"
    write(path, ["a", "b"])

    snapshot(path, now=datetime(2026, 9, 1, 10, 0, 0))
    write(path, [])  # the accident: overwritten with an empty sequence

    kept = versions(path)
    assert len(kept) == 1
    assert kept[0].action_count == 2
    actions, _settings = load_profile(kept[0].path)
    assert [action.value for action in actions] == ["a", "b"]


def test_restoring_brings_the_actions_back_and_is_itself_undoable(tmp_path):
    path = tmp_path / "Mine.kca.json"
    write(path, ["a", "b"])
    snapshot(path, now=datetime(2026, 9, 1, 10, 0, 0))
    write(path, [])

    restore(path, versions(path)[0].path)

    actions, _settings = load_profile(path)
    assert [action.value for action in actions] == ["a", "b"]
    # The emptied state was itself kept, so a mistaken restore is recoverable.
    assert any(version.action_count == 0 for version in versions(path))


def test_versions_are_newest_first_and_capped(tmp_path):
    path = tmp_path / "Mine.kca.json"
    write(path, ["a"])
    for minute in range(14):
        snapshot(path, now=datetime(2026, 9, 1, 10, minute, 0), keep=10)

    kept = versions(path)
    assert len(kept) == 10
    assert kept[0].saved_at > kept[-1].saved_at


def test_history_stays_out_of_the_profile_library(tmp_path):
    path = tmp_path / "Mine.kca.json"
    write(path, ["a"])
    snapshot(path, now=datetime(2026, 9, 1, 10, 0, 0))

    assert history_directory(path).name == HISTORY_DIR_NAME
    # The library lists *.kca.json beside the profile; snapshots must not appear.
    assert [p.name for p in tmp_path.glob("*.kca.json")] == ["Mine.kca.json"]


def test_one_profiles_history_never_mixes_with_anothers(tmp_path):
    mine = tmp_path / "Mine.kca.json"
    yours = tmp_path / "Yours.kca.json"
    write(mine, ["a"])
    write(yours, ["b", "c"])
    snapshot(mine, now=datetime(2026, 9, 1, 10, 0, 0))
    snapshot(yours, now=datetime(2026, 9, 1, 10, 0, 1))

    assert [v.action_count for v in versions(mine)] == [1]
    assert [v.action_count for v in versions(yours)] == [2]


def test_an_unreadable_snapshot_is_listed_rather_than_crashing(tmp_path):
    path = tmp_path / "Mine.kca.json"
    write(path, ["a"])
    snapshot(path, now=datetime(2026, 9, 1, 10, 0, 0))
    kept = versions(path)[0]
    kept.path.write_text("{ not json", encoding="utf-8")

    assert versions(path)[0].action_count == -1


def test_restoring_a_missing_version_is_refused(tmp_path):
    path = tmp_path / "Mine.kca.json"
    write(path, ["a"])

    with pytest.raises(OSError):
        restore(path, tmp_path / "gone.kca.json")

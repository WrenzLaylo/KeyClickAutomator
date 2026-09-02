"""Saved profiles: the library, opening and saving, deleting, and version history."""

from engine import Action
from engine import RunSettings
from engine import load_profile
from engine import save_profile
from qt_controller import AutomatorController
import profile_catalog
import qt_controller


def test_deleting_a_profile_removes_the_file_and_dequeues_it(tmp_path):
    keep = tmp_path / "Keep.kca.json"
    doomed = tmp_path / "Doomed.kca.json"
    save_profile(keep, [Action("key", value="a")], RunSettings(start_delay=0))
    save_profile(doomed, [Action("key", value="b")], RunSettings(start_delay=0))

    controller = AutomatorController(start_hotkeys=False, profile_directory=tmp_path)
    assert controller.enqueueProfile(str(doomed)) is True
    assert controller.enqueueProfile(str(keep)) is True

    assert controller.deleteProfilePath(str(doomed)) is True

    assert doomed.exists() is False
    assert keep.exists() is True
    # A queued entry must not be left pointing at a file that no longer exists.
    assert controller.runQueuePaths == [str(keep.resolve())]
    assert [entry["name"] for entry in controller.profileEntries] == ["Keep"]
    controller.shutdown()

def test_deleting_the_open_profile_keeps_the_sequence_on_screen(tmp_path):
    path = tmp_path / "Open.kca.json"
    save_profile(path, [Action("key", value="a")], RunSettings(start_delay=0))
    controller = AutomatorController(start_hotkeys=False, profile_directory=tmp_path)
    assert controller.openProfilePath(str(path)) is True
    assert controller.currentProfileName == "Open"

    assert controller.deleteProfilePath(str(path)) is True

    # The work stays in the editor; it just stops being a saved profile.
    assert [action.value for action in controller.actions] == ["a"]
    assert controller.currentProfilePath == ""
    assert controller.currentProfileName == "Untitled sequence"
    assert controller.dirty is True
    controller.shutdown()

def test_a_profile_cannot_be_deleted_while_a_run_is_active(tmp_path):
    path = tmp_path / "Busy.kca.json"
    save_profile(path, [Action("key", value="a")], RunSettings(start_delay=0))
    controller = AutomatorController(start_hotkeys=False, profile_directory=tmp_path)
    controller._set_running(True)

    assert controller.deleteProfilePath(str(path)) is False
    assert path.exists() is True
    controller.shutdown()

def test_open_profile_exposes_sequence_name_and_new_sequence_resets_it(monkeypatch, tmp_path):
    path = tmp_path / "Morning routine.kca.json"
    save_profile(path, [Action("key", value="a")], RunSettings())
    monkeypatch.setattr(qt_controller.QFileDialog, "getOpenFileName", lambda *args: (str(path), ""))

    controller = AutomatorController(start_hotkeys=False)
    assert controller.currentProfileName == "Untitled sequence"
    controller.openProfile()
    assert controller.currentProfileName == "Morning routine"
    controller.clearActions()
    assert controller.currentProfileName == "Untitled sequence"
    controller.shutdown()

def test_profile_library_discovers_profiles_and_marks_corrupt_keyclick_files(tmp_path):
    first = tmp_path / "Morning routine.kca.json"
    second = tmp_path / "Night.json"
    corrupt = tmp_path / "Broken.kca.json"
    unrelated = tmp_path / "settings.json"
    save_profile(
        first,
        [Action("key", value="a"), Action("text", value="hello", enabled=False)],
        RunSettings(),
    )
    save_profile(second, [Action("key", value="b")], RunSettings())
    corrupt.write_text("{not valid json", encoding="utf-8")
    unrelated.write_text('{"theme": "light"}', encoding="utf-8")

    controller = AutomatorController(
        start_hotkeys=False,
        profile_directory=tmp_path,
    )
    entries = {entry["name"]: entry for entry in controller.profileEntries}

    assert set(entries) == {"Morning routine", "Night", "Broken"}
    assert entries["Morning routine"]["actionCount"] == 2
    assert entries["Morning routine"]["activeCount"] == 1
    assert entries["Morning routine"]["valid"] is True
    assert entries["Night"]["valid"] is True
    assert entries["Broken"]["valid"] is False
    assert entries["Broken"]["error"]
    assert "Today" in entries["Morning routine"]["modified"]
    controller.shutdown()

def test_profile_library_opens_a_selected_path_and_follows_its_folder(tmp_path):
    initial_folder = tmp_path / "initial"
    selected_folder = tmp_path / "selected"
    initial_folder.mkdir()
    selected_folder.mkdir()
    path = selected_folder / "Click loop.kca.json"
    save_profile(path, [Action("left_click", x=10, y=20)], RunSettings())

    controller = AutomatorController(
        start_hotkeys=False,
        profile_directory=initial_folder,
    )
    assert controller.openProfilePath(str(path)) is True

    assert controller.currentProfileName == "Click loop"
    assert controller.currentProfilePath == str(path.resolve())
    assert controller.profileDirectory == str(selected_folder.resolve())
    assert [entry["name"] for entry in controller.profileEntries] == ["Click loop"]
    assert controller.actions[0].kind == "left_click"
    controller.shutdown()

def test_save_profile_reuses_the_current_path_and_refreshes_the_library(monkeypatch, tmp_path):
    path = tmp_path / "Reusable.kca.json"
    monkeypatch.setattr(
        qt_controller.QFileDialog,
        "getSaveFileName",
        lambda *args: (str(path), ""),
    )
    controller = AutomatorController(
        start_hotkeys=False,
        profile_directory=tmp_path,
    )
    controller.addAction({"kind": "key", "value": "a"})

    assert controller.saveProfile() is True
    assert controller.currentProfilePath == str(path.resolve())
    assert [entry["name"] for entry in controller.profileEntries] == ["Reusable"]

    controller.addAction({"kind": "key", "value": "b"})
    monkeypatch.setattr(
        qt_controller.QFileDialog,
        "getSaveFileName",
        lambda *args: (_ for _ in ()).throw(AssertionError("Save dialog reopened")),
    )
    assert controller.saveProfile() is True
    actions, _settings = load_profile(path)
    assert [action.value for action in actions] == ["a", "b"]
    assert controller.dirty is False
    controller.shutdown()

def test_profile_folder_picker_refreshes_the_library(monkeypatch, tmp_path):
    first_folder = tmp_path / "first"
    second_folder = tmp_path / "second"
    first_folder.mkdir()
    second_folder.mkdir()
    save_profile(
        second_folder / "Second folder.kca.json",
        [Action("key", value="s")],
        RunSettings(),
    )
    monkeypatch.setattr(
        qt_controller.QFileDialog,
        "getExistingDirectory",
        lambda *args: str(second_folder),
    )
    controller = AutomatorController(
        start_hotkeys=False,
        profile_directory=first_folder,
    )

    assert controller.chooseProfileFolder() is True
    assert controller.profileDirectory == str(second_folder.resolve())
    assert [entry["name"] for entry in controller.profileEntries] == ["Second folder"]
    controller.shutdown()

def test_packaged_app_uses_the_executable_folder_as_its_profile_library(monkeypatch, tmp_path):
    executable = tmp_path / "KeyClickAutomator-Portable.exe"
    monkeypatch.setattr(profile_catalog.sys, "frozen", True, raising=False)
    monkeypatch.setattr(profile_catalog.sys, "executable", str(executable))

    controller = AutomatorController(start_hotkeys=False)

    assert controller.profileDirectory == str(tmp_path.resolve())
    controller.shutdown()

def test_saving_over_a_profile_keeps_the_previous_version(tmp_path):
    """The accident that emptied two real profiles is now recoverable."""
    path = tmp_path / "Mine.kca.json"
    save_profile(path, [Action("key", value="a"), Action("key", value="b")],
                 RunSettings(start_delay=0))
    controller = AutomatorController(start_hotkeys=False, profile_directory=tmp_path)
    assert controller.openProfilePath(str(path)) is True

    controller.clearActions()
    controller.addAction({"kind": "key", "value": "z"})
    assert controller._save_profile_path(str(path)) is True

    history = controller.profileVersions(str(path))
    assert history and history[0]["actionCount"] == 2

    assert controller.restoreProfileVersion(str(path), history[0]["path"]) is True
    assert [action.value for action in controller.actions] == ["a", "b"]
    controller.shutdown()

def test_deleting_a_profile_keeps_a_recoverable_copy(tmp_path):
    path = tmp_path / "Doomed.kca.json"
    save_profile(path, [Action("key", value="a")], RunSettings(start_delay=0))
    controller = AutomatorController(start_hotkeys=False, profile_directory=tmp_path)

    assert controller.deleteProfilePath(str(path)) is True

    assert path.exists() is False
    assert controller.profileVersions(str(path))[0]["actionCount"] == 1
    controller.shutdown()

def test_a_version_cannot_be_restored_while_a_run_is_active(tmp_path):
    path = tmp_path / "Busy.kca.json"
    save_profile(path, [Action("key", value="a")], RunSettings(start_delay=0))
    controller = AutomatorController(start_hotkeys=False, profile_directory=tmp_path)
    controller._save_profile_path(str(path))
    version = controller.profileVersions(str(path))[0]["path"]
    controller._set_running(True)

    assert controller.restoreProfileVersion(str(path), version) is False
    controller.shutdown()

def test_saved_versions_never_appear_in_the_profile_library(tmp_path):
    path = tmp_path / "Mine.kca.json"
    save_profile(path, [Action("key", value="a")], RunSettings(start_delay=0))
    controller = AutomatorController(start_hotkeys=False, profile_directory=tmp_path)
    controller._save_profile_path(str(path))
    controller._save_profile_path(str(path))

    assert [entry["name"] for entry in controller.profileEntries] == ["Mine"]
    controller.shutdown()

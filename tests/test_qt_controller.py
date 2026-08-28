import threading
from types import SimpleNamespace

from pynput import keyboard
from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtTest import QSignalSpy, QTest

import qt_controller
import profile_catalog
from engine import Action, RunSettings, load_profile, save_profile
from qt_controller import ActionListModel, AutomatorController
from window_backend import WindowInfo


_app = QCoreApplication.instance() or QCoreApplication([])


class FakeWindowService:
    def __init__(self):
        self.info = WindowInfo(
            hwnd=444,
            title="Target App",
            class_name="TargetWindow",
            executable=r"C:\\Apps\\target.exe",
            process_id=987654,
        )

    def window_at_point(self, x, y):
        return self.info

    def list_windows(self, excluded_process_id=0):
        return [self.info]

    def resolve_window(self, selector, preferred_hwnd=0):
        return self.info

    def ensure_usable(self, hwnd):
        return None

    def ensure_responsive(self, hwnd):
        return None

    def client_size(self, hwnd):
        return 800, 600

    def screen_to_client(self, hwnd, x, y):
        return x - 100, y - 200

    def mouse_target(self, root_hwnd, x, y):
        return root_hwnd, x, y


def test_add_action_updates_model_and_summary():
    controller = AutomatorController(start_hotkeys=False)
    assert controller.addAction({"kind": "key", "value": "space", "delay": 0.1, "repeats": 2}) is True
    assert controller.actionModel.rowCount() == 1
    index = controller.actionModel.index(0, 0)
    assert controller.actionModel.data(index, ActionListModel.TitleRole) == "Press SPACE"
    assert controller.summary == "1 active  ·  2 operations / cycle"
    controller.shutdown()


def test_invalid_add_reports_failure_without_mutating_the_sequence():
    controller = AutomatorController(start_hotkeys=False)

    assert controller.addAction({"kind": "key", "value": ""}) is False
    assert controller.actionModel.rowCount() == 0

    controller.shutdown()


def test_can_run_tracks_whether_any_action_is_enabled():
    controller = AutomatorController(start_hotkeys=False)
    assert controller.canRun is False
    controller.addAction({"kind": "key", "value": "space", "enabled": False})
    assert controller.canRun is False
    controller.setActionEnabled(0, True)
    assert controller.canRun is True
    controller.setActionEnabled(0, False)
    assert controller.canRun is False
    controller.shutdown()


def test_follow_pointer_click_does_not_require_fixed_coordinates():
    controller = AutomatorController(start_hotkeys=False)
    controller.addAction({"kind": "left_click", "useCurrentPointer": True})
    index = controller.actionModel.index(0, 0)

    assert controller.actions[0].use_current_pointer is True
    assert controller.actions[0].x is None
    assert controller.actionModel.data(index, ActionListModel.SubtitleRole).startswith("current pointer")
    controller.shutdown()


def test_action_toggle_updates_its_role_without_resetting_the_list_model():
    controller = AutomatorController(start_hotkeys=False)
    controller.addAction({"kind": "key", "value": "space"})
    model = controller.actionModel
    reset_spy = QSignalSpy(model.modelReset)
    changed_spy = QSignalSpy(model.dataChanged)

    controller.setActionEnabled(0, False)

    assert bytes(model.roleNames()[ActionListModel.EnabledRole]) == b"actionEnabled"
    assert controller.actions[0].enabled is False
    assert reset_spy.count() == 0
    assert changed_spy.count() == 1
    assert changed_spy.at(0)[2] == [ActionListModel.EnabledRole]
    controller.shutdown()


def test_reorder_and_duplicate_actions():
    controller = AutomatorController(start_hotkeys=False)
    controller.addAction({"kind": "key", "value": "a"})
    controller.addAction({"kind": "key", "value": "b"})
    controller.moveAction(1, -1)
    assert controller.actions[0].value == "b"
    controller.duplicateAction(0)
    assert [action.value for action in controller.actions] == ["b", "b", "a"]
    controller.shutdown()


def test_drag_style_reorder_moves_rows_without_resetting_the_model():
    controller = AutomatorController(start_hotkeys=False)
    for value in ("a", "b", "c"):
        controller.addAction({"kind": "key", "value": value})
    model = controller.actionModel
    reset_spy = QSignalSpy(model.modelReset)
    moved_spy = QSignalSpy(model.rowsMoved)
    index_changed_spy = QSignalSpy(model.dataChanged)

    controller.selectedIndex = 1
    controller.moveActionTo(0, 2)

    assert [action.value for action in controller.actions] == ["b", "c", "a"]
    assert controller.selectedIndex == 0
    assert reset_spy.count() == 0
    assert moved_spy.count() == 1
    assert index_changed_spy.count() == 1
    assert index_changed_spy.at(0)[2] == [ActionListModel.IndexRole]

    controller.selectedIndex = 2
    controller.moveActionTo(2, 0)
    assert [action.value for action in controller.actions] == ["a", "b", "c"]
    assert controller.selectedIndex == 0
    assert moved_spy.count() == 2
    controller.shutdown()


def test_delete_is_dirty_and_recoverable_with_one_step_undo():
    controller = AutomatorController(start_hotkeys=False)
    controller.addAction({"kind": "key", "value": "a"})
    assert controller.dirty is True
    assert controller.canUndo is False

    controller.deleteAction(0)
    assert controller.actionModel.rowCount() == 0
    assert controller.canUndo is True

    controller.undoDelete()
    assert [action.value for action in controller.actions] == ["a"]
    assert controller.selectedIndex == 0
    assert controller.canUndo is False
    controller.shutdown()


def test_indefinite_setting_is_explicitly_preserved():
    controller = AutomatorController(start_hotkeys=False)
    controller.applyRunSettings({"repeatForever": True, "repeatCount": 9, "startDelay": 0})
    assert controller.runSettings["repeatForever"] is True
    assert controller.runSettings["repeatCount"] == 9
    controller.shutdown()


def test_pending_run_settings_block_the_global_start_shortcut():
    controller = AutomatorController(start_hotkeys=False)
    controller.addAction({"kind": "key", "value": "a"})
    toast_spy = QSignalSpy(controller.toast)

    controller.markRunSettingsPending()
    controller.startRun()

    assert controller.runSettingsPending is True
    assert controller.running is False
    assert "Apply the edited Run settings" in toast_spy.at(toast_spy.count() - 1)[0]
    controller.shutdown()


def test_test_action_forces_one_repeat_and_a_three_second_safety_delay(monkeypatch):
    controller = AutomatorController(start_hotkeys=False)
    controller.addAction({"kind": "key", "value": "a", "repeats": 9, "delay": 4})
    captured = {}

    def fake_begin(actions, indices, settings, message, status_verb="Running"):
        captured.update(actions=actions, indices=indices, settings=settings, message=message, verb=status_verb)
        return True

    monkeypatch.setattr(controller, "_begin_run", fake_begin)
    assert controller.testActionWithSettings(0, {
        "repeatCount": 7,
        "repeatForever": True,
        "startDelay": 0,
        "jitter": 2,
    }) is True

    assert captured["indices"] == [0]
    assert captured["actions"][0].repeats == 1
    assert captured["actions"][0].delay_after == 0
    assert captured["settings"].repeat_count == 1
    assert captured["settings"].repeat_forever is False
    assert captured["settings"].start_delay == 3
    assert captured["settings"].delay_jitter == 0
    assert captured["verb"] == "Testing"
    controller.shutdown()


def test_run_from_here_maps_progress_back_to_the_original_step(monkeypatch):
    controller = AutomatorController(start_hotkeys=False)
    controller.addAction({"kind": "key", "value": "a"})
    controller.addAction({"kind": "key", "value": "b", "enabled": False})
    controller.addAction({"kind": "key", "value": "c"})
    captured = {}

    def fake_begin(actions, indices, settings, message, status_verb="Running"):
        captured.update(actions=actions, indices=indices)
        return True

    monkeypatch.setattr(controller, "_begin_run", fake_begin)
    assert controller.startRunFromWithSettings(1, {"startDelay": 0}) is True
    assert [action.value for action in captured["actions"]] == ["c"]
    assert captured["indices"] == [2]

    controller._run_action_indices = [2]
    controller._handle_progress("action", 0, 1)
    assert controller.runningActionIndex == 2
    assert controller.status == "Running step 3"
    controller.shutdown()


def test_frozen_pointer_picker_waits_for_an_explicit_click(monkeypatch):
    monkeypatch.setattr(qt_controller.pyautogui, "position", lambda: SimpleNamespace(x=321, y=654))
    controller = AutomatorController(start_hotkeys=False)
    captured = QSignalSpy(controller.positionCaptured)

    assert controller.startPositionCapture(1) is True
    assert controller.capturePending is True
    assert controller.captureTarget == 1
    assert controller.captureCountdown == 0
    assert captured.count() == 0
    assert controller.commitPositionCapture(321, 654) is True

    assert captured.count() == 1
    assert captured.at(0) == [1, 321, 654, "screen", 0, 0]
    assert controller.capturePending is False
    assert controller.captureCountdown == 0
    controller.shutdown()


def test_dirty_sequence_is_autosaved_and_can_be_recovered(tmp_path):
    recovery_path = tmp_path / "recovery-draft.kca.json"
    first = AutomatorController(
        start_hotkeys=False,
        recovery_path=recovery_path,
        enable_recovery=True,
    )
    first.addAction({"kind": "left_click", "useCurrentPointer": True})
    first.applyRunSettings({"repeatCount": 4, "startDelay": 1})

    assert first.dirty is True
    assert first.draftAvailable is True
    assert recovery_path.is_file()
    first.shutdown()

    restored = AutomatorController(
        start_hotkeys=False,
        recovery_path=recovery_path,
        enable_recovery=True,
    )
    assert restored.draftAvailable is True
    assert "1 action" in restored.draftSummary
    assert restored.recoverDraft() is True
    assert restored.actions[0].use_current_pointer is True
    assert restored.runSettings["repeatCount"] == 4
    assert restored.dirty is True

    restored.discardDraft()
    assert restored.draftAvailable is False
    assert recovery_path.exists() is False
    restored.shutdown()


def test_hotkey_toggle_is_queued_back_to_the_qt_thread():
    controller = AutomatorController(start_hotkeys=False)
    toast_spy = QSignalSpy(controller.toast)
    failures = []

    def invoke_from_listener_thread():
        try:
            controller.queueStartToggle()
        except Exception as exc:
            failures.append(exc)

    worker = threading.Thread(target=invoke_from_listener_thread)
    worker.start()
    worker.join()
    QTest.qWait(80)
    assert failures == []
    assert toast_spy.count() == 1
    controller.shutdown()


def test_recorded_key_names_are_stable_for_character_and_special_keys():
    assert AutomatorController.keyName(keyboard.KeyCode.from_char("a")) == "a"
    assert AutomatorController.keyName(keyboard.Key.space) == "space"


def test_action_key_capture_is_cancelled_before_pointer_recording(monkeypatch):
    listeners = []

    class Listener:
        def __init__(self, on_press=None, on_release=None):
            self.on_press = on_press
            self.on_release = on_release
            self.stopped = False

        def start(self):
            listeners.append(self)

        def stop(self):
            self.stopped = True

    monkeypatch.setattr(qt_controller.keyboard, "Listener", Listener)
    controller = AutomatorController(start_hotkeys=False)

    assert controller.recordActionKey() is True
    assert controller.actionCaptureMode == "key"
    assert controller.startPositionCapture(0) is True
    assert listeners[-1].stopped is True
    assert controller.actionCaptureMode == ""
    assert controller.capturePending is True

    controller.cancelPositionCapture(announce=False)
    controller.shutdown()


def test_action_hotkey_recorder_waits_for_a_modifier_combination(monkeypatch):
    listeners = []

    class Listener:
        def __init__(self, on_press=None, on_release=None):
            self.on_press = on_press
            self.on_release = on_release

        def start(self):
            listeners.append(self)

        def stop(self):
            pass

    monkeypatch.setattr(qt_controller.keyboard, "Listener", Listener)
    controller = AutomatorController(start_hotkeys=False)
    captured = QSignalSpy(controller.actionHotkeyCaptured)

    assert controller.recordActionHotkey() is True
    listener = listeners[-1]
    assert controller.actionCaptureMode == "hotkey"
    assert listener.on_press(keyboard.KeyCode.from_char("a")) is None
    assert captured.count() == 0
    assert controller.actionCaptureMode == "hotkey"
    assert listener.on_press(keyboard.Key.ctrl_l) is None
    assert listener.on_press(keyboard.Key.shift) is None
    assert listener.on_press(keyboard.KeyCode.from_char("s")) is False

    assert captured.count() == 1
    assert captured.at(0) == ["ctrl+shift+s"]
    assert controller.actionCaptureMode == ""
    controller.shutdown()


def test_global_shortcut_recorder_captures_modifier_combination_without_applying(monkeypatch):
    listeners = []

    class Listener:
        def __init__(self, on_press=None, on_release=None):
            self.on_press = on_press
            self.on_release = on_release
            self.started = False

        def start(self):
            self.started = True
            listeners.append(self)

        def stop(self):
            self.started = False

    monkeypatch.setattr(qt_controller.keyboard, "Listener", Listener)
    controller = AutomatorController(start_hotkeys=False)
    captured = QSignalSpy(controller.shortcutCaptured)

    assert controller.recordGlobalShortcut("start") is True
    listener = listeners[-1]
    assert listener.on_press(keyboard.Key.ctrl_l) is None
    assert listener.on_press(keyboard.Key.shift) is None
    assert listener.on_press(keyboard.KeyCode.from_char("s")) is False
    QTest.qWait(20)

    assert captured.count() == 1
    assert captured.at(0) == ["start", "ctrl+shift+s"]
    assert controller.runSettings["startHotkey"] == "f6"
    controller.shutdown()


def test_global_shortcut_recorder_rejects_unknown_target():
    controller = AutomatorController(start_hotkeys=False)
    assert controller.recordGlobalShortcut("unknown") is False
    controller.shutdown()


def test_global_shortcut_recording_restores_known_good_listener_until_apply(monkeypatch):
    global_listeners = []
    capture_listeners = []

    class GlobalListener:
        def __init__(self, mapping):
            self.mapping = mapping
            self.stopped = False

        def start(self):
            global_listeners.append(self)

        def stop(self):
            self.stopped = True

    class CaptureListener:
        def __init__(self, on_press=None, on_release=None):
            self.on_press = on_press
            self.on_release = on_release

        def start(self):
            capture_listeners.append(self)

        def stop(self):
            pass

    monkeypatch.setattr(qt_controller.keyboard, "GlobalHotKeys", GlobalListener)
    monkeypatch.setattr(qt_controller.keyboard, "Listener", CaptureListener)
    controller = AutomatorController(start_hotkeys=True)
    known_good = global_listeners[-1]

    assert controller.recordGlobalShortcut("start") is True
    assert known_good.stopped is True
    assert capture_listeners[-1].on_press(keyboard.Key.f10) is False
    QTest.qWait(20)

    assert controller.runSettings["startHotkey"] == "f6"
    assert controller._listener is global_listeners[-1]
    assert controller._listener is not known_good
    assert "<f6>" in controller._listener.mapping
    controller.shutdown()


def test_all_accepted_named_global_keys_are_formatted_for_pynput():
    for value in ("caps_lock", "insert", "menu", "num_lock", "pause", "scroll_lock", "alt_gr"):
        keyboard.HotKey.parse(AutomatorController._pynput_hotkey(value))


def test_editing_disabled_action_preserves_disabled_state():
    controller = AutomatorController(start_hotkeys=False)
    controller.addAction({"kind": "key", "value": "a", "enabled": False})
    controller.updateAction(0, {"kind": "key", "value": "b", "enabled": True})
    assert controller.actions[0].value == "b"
    assert controller.actions[0].enabled is False
    controller.shutdown()


def test_failed_hotkey_replacement_keeps_known_good_listener(monkeypatch):
    class Listener:
        def __init__(self, fail=False):
            self.fail = fail
            self.stopped = False

        def start(self):
            if self.fail:
                raise RuntimeError("registration failed")

        def stop(self):
            self.stopped = True

    controller = AutomatorController(start_hotkeys=False)
    old_listener = Listener()
    controller._listener = old_listener
    controller._hotkeys_enabled = True
    monkeypatch.setattr(qt_controller.keyboard, "GlobalHotKeys", lambda mappings: Listener(fail=True))

    controller.applyRunSettings({"startHotkey": "f5", "captureHotkey": "f7", "stopHotkey": "f10"})

    assert controller._listener is old_listener
    assert old_listener.stopped is False
    assert controller.runSettings["startHotkey"] == "f6"
    controller._hotkeys_enabled = False
    controller.shutdown()


def test_reordered_duplicate_shortcuts_do_not_replace_known_good_settings():
    controller = AutomatorController(start_hotkeys=False)
    toast_spy = QSignalSpy(controller.toast)

    controller.applyRunSettings({
        "startHotkey": "ctrl+s",
        "captureHotkey": "s+control",
        "stopHotkey": "f9",
    })

    assert controller.runSettings["startHotkey"] == "f6"
    assert controller.runSettings["captureHotkey"] == "f8"
    assert toast_spy.count() == 1
    assert "must be different" in toast_spy.at(0)[0]
    controller.shutdown()


def test_global_shortcut_conflicts_identify_duplicate_fields_and_aliases():
    controller = AutomatorController(start_hotkeys=False)

    conflict = controller.globalShortcutConflicts("control+s", "s+ctrl", "f9")
    assert conflict == {
        "hasConflict": True,
        "message": "Start / toggle and Record pointer cannot use the same shortcut (CTRL+S).",
        "startConflict": True,
        "captureConflict": True,
        "stopConflict": False,
    }
    assert controller.globalShortcutConflicts("f6", "f8", "f9")["hasConflict"] is False
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


def test_visual_window_picker_lists_and_selects_an_open_window(monkeypatch):
    monkeypatch.setattr(qt_controller.pyautogui, "position", lambda: SimpleNamespace(x=700, y=420))
    controller = AutomatorController(start_hotkeys=False, window_service=FakeWindowService())

    assert controller.setTargetMode("window") is True
    assert controller.startWindowPick() is True
    assert controller.windowPickPending is False
    assert len(controller.windowEntries) == 1
    assert controller.windowEntries[0]["appName"] == "Target"
    assert controller.selectWindowTarget(controller.windowEntries[0]["handle"]) is True

    assert controller.targetSettings["mode"] == "window"
    assert controller.targetSettings["windowSelected"] is True
    assert controller.targetSettings["displayName"] == "Target App"
    controller.shutdown()


def test_background_position_recording_converts_to_selected_window_coordinates(monkeypatch):
    monkeypatch.setattr(qt_controller.pyautogui, "position", lambda: SimpleNamespace(x=321, y=654))
    controller = AutomatorController(start_hotkeys=False, window_service=FakeWindowService())
    controller.setTargetMode("window")
    controller.captureWindowTarget()
    captured = QSignalSpy(controller.positionCaptured)

    controller.capturePosition(0)

    assert captured.count() == 1
    assert captured.at(0) == [0, 221, 454, "window", 800, 600]
    controller.shutdown()


def test_run_blocks_mouse_positions_recorded_for_the_other_target(monkeypatch):
    monkeypatch.setattr(qt_controller.pyautogui, "position", lambda: SimpleNamespace(x=321, y=654))
    controller = AutomatorController(start_hotkeys=False, window_service=FakeWindowService())
    controller.addAction({"kind": "left_click", "x": 10, "y": 20, "coordinateSpace": "screen"})
    controller.setTargetMode("window")
    controller.captureWindowTarget()
    toasts = QSignalSpy(controller.toast)

    assert controller.startRunWithSettings({"startDelay": 0}) is False
    assert controller.running is False
    assert "different target" in toasts.at(toasts.count() - 1)[0]
    controller.shutdown()

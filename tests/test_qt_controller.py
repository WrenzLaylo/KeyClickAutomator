import threading

from pynput import keyboard
from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtTest import QSignalSpy, QTest

import qt_controller
from engine import Action, RunSettings, save_profile
from qt_controller import ActionListModel, AutomatorController


_app = QCoreApplication.instance() or QCoreApplication([])


def test_add_action_updates_model_and_summary():
    controller = AutomatorController(start_hotkeys=False)
    controller.addAction({"kind": "key", "value": "space", "delay": 0.1, "repeats": 2})
    assert controller.actionModel.rowCount() == 1
    index = controller.actionModel.index(0, 0)
    assert controller.actionModel.data(index, ActionListModel.TitleRole) == "Press SPACE"
    assert controller.summary == "1 active  ·  2 operations / cycle"
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


def test_reorder_and_duplicate_actions():
    controller = AutomatorController(start_hotkeys=False)
    controller.addAction({"kind": "key", "value": "a"})
    controller.addAction({"kind": "key", "value": "b"})
    controller.moveAction(1, -1)
    assert controller.actions[0].value == "b"
    controller.duplicateAction(0)
    assert [action.value for action in controller.actions] == ["b", "b", "a"]
    controller.shutdown()


def test_indefinite_setting_is_explicitly_preserved():
    controller = AutomatorController(start_hotkeys=False)
    controller.applyRunSettings({"repeatForever": True, "repeatCount": 9, "startDelay": 0})
    assert controller.runSettings["repeatForever"] is True
    assert controller.runSettings["repeatCount"] == 9
    controller.shutdown()


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

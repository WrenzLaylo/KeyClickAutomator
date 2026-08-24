import threading

from pynput import keyboard
from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtTest import QSignalSpy, QTest

import qt_controller
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

"""Recording things: pointer positions, action keys, and global shortcuts."""

from types import SimpleNamespace
import threading

from PySide6.QtTest import QSignalSpy
from PySide6.QtTest import QTest
from pynput import keyboard
import pyautogui

from qt_controller import AutomatorController
import qt_controller


def test_frozen_pointer_picker_waits_for_an_explicit_click(monkeypatch):
    monkeypatch.setattr(pyautogui, "position", lambda: SimpleNamespace(x=321, y=654))
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
    assert listener.on_press(keyboard.KeyCode.from_char("\x03")) is False

    assert captured.count() == 1
    assert captured.at(0) == ["ctrl+shift+c"]
    assert controller.actionCaptureMode == ""

    assert controller.recordActionHotkey() is True
    listener = listeners[-1]
    assert listener.on_press(keyboard.Key.alt_l) is None
    assert listener.on_press(keyboard.Key.ctrl_l) is None
    assert listener.on_press(keyboard.KeyCode.from_vk(67)) is False
    assert captured.count() == 2
    assert captured.at(1) == ["ctrl+alt+c"]
    controller.shutdown()

def test_key_name_normalizes_modified_printable_windows_keys():
    assert AutomatorController.keyName(keyboard.KeyCode.from_char("\x03")) == "c"
    assert AutomatorController.keyName(keyboard.KeyCode.from_vk(67)) == "c"
    assert AutomatorController.keyName(keyboard.KeyCode.from_vk(88)) == "x"

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
    assert listener.on_press(keyboard.KeyCode.from_char("\x13")) is False
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

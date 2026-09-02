"""The inspector: the action editor, its recorders, and what it refuses to add."""

from types import SimpleNamespace

from PySide6.QtCore import QMetaObject
from PySide6.QtCore import QObject
from PySide6.QtCore import QPointF
from PySide6.QtCore import Qt
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest
import pyautogui

from qt_app import build_engine
import qt_controller

from qml_harness import app, PickerWindowService, visual_children_named


def test_action_type_popup_opens_below_and_aligned_with_its_picker():
    engine, controller = build_engine(start_hotkeys=False)
    window = engine.rootObjects()[0]
    window.setWidth(1920)
    window.setHeight(1016)
    app.processEvents()
    QTest.qWait(260)
    picker = window.findChild(QQuickItem, "actionTypePicker")
    popup = window.findChild(QObject, "actionTypePopup")
    assert picker is not None and popup is not None
    QMetaObject.invokeMethod(popup, "open", Qt.DirectConnection)
    QTest.qWait(80)
    picker_position = picker.mapToScene(QPointF(0, 0))
    popup_position = popup.property("background").mapToScene(QPointF(0, 0))
    assert abs(popup_position.x() - picker_position.x()) < 1
    assert abs(popup_position.y() - (picker_position.y() + picker.height() + 6)) < 1
    assert popup.property("width") == picker.width()
    window.close()
    controller.shutdown()

def test_compact_shortcuts_fit_their_dock_and_run_controls_are_balanced():
    engine, controller = build_engine(start_hotkeys=False)
    window = engine.rootObjects()[0]
    window.setWidth(900)
    window.setHeight(840)
    app.processEvents()
    QTest.qWait(240)

    dock = window.findChild(QQuickItem, "shortcutDock")
    assert dock is not None
    shortcuts = visual_children_named(dock, "shortcutHint_")
    assert len(shortcuts) == 3
    assert [(item.property("keyText"), item.property("labelText")) for item in shortcuts] == [
        ("f6", "Start"),
        ("f8", "Record"),
        ("f9", "Stop"),
    ]
    assert len({(item.width(), item.height()) for item in shortcuts}) == 1
    for item in shortcuts:
        position = item.mapToItem(dock, QPointF(0, 0))
        assert position.x() >= 0
        assert position.x() + item.width() <= dock.width()
        assert position.y() >= 0
        assert position.y() + item.height() <= dock.height()

    group = window.findChild(QQuickItem, "runControlGroup")
    stop_button = window.findChild(QQuickItem, "runStopButton")
    start_button = window.findChild(QQuickItem, "runStartButton")
    progress = window.findChild(QQuickItem, "runProgressTrack")
    assert all(item is not None for item in (group, stop_button, start_button, progress))
    assert start_button.width() > stop_button.width()
    assert stop_button.height() == start_button.height()
    assert stop_button.property("keyHint") == "f9"
    assert start_button.property("keyHint") == "f6"
    assert start_button.isEnabled() is False
    assert progress.isVisible() is False
    controller.addAction({"kind": "key", "value": "space"})
    controller.markRunSettingsPending()
    QTest.qWait(80)
    assert start_button.isEnabled() is True
    assert start_button.property("text") == "Apply & start"
    key_hint = window.findChild(QQuickItem, "runStartButton_keyHint")
    assert key_hint is not None
    hint_position = key_hint.mapToItem(start_button, QPointF(0, 0))
    assert hint_position.x() >= 0
    assert hint_position.x() + key_hint.width() <= start_button.width()
    window.close()
    controller.shutdown()

def test_run_inspector_reserves_a_gutter_between_fields_and_scrollbar():
    engine, controller = build_engine(start_hotkeys=False)
    window = engine.rootObjects()[0]
    window.setWidth(1360)
    window.setHeight(640)
    window.setProperty("activeInspectorTab", 1)
    app.processEvents()
    QTest.qWait(160)

    flick = window.findChild(QQuickItem, "runSettingsFlick")
    form = window.findChild(QQuickItem, "runSettingsForm")
    scroll_bar = window.findChild(QQuickItem, "runSettingsScrollBar")
    assert flick is not None and form is not None and scroll_bar is not None
    form_position = form.mapToItem(flick, QPointF(0, 0))
    scroll_position = scroll_bar.mapToItem(flick, QPointF(0, 0))
    gutter = scroll_position.x() - (form_position.x() + form.width())
    assert gutter >= 8

    window.close()
    controller.shutdown()

def test_click_action_can_be_added_in_follow_current_pointer_mode():
    engine, controller = build_engine(start_hotkeys=False)
    window = engine.rootObjects()[0]
    picker = window.findChild(QQuickItem, "actionTypePicker")
    follow_pointer = window.findChild(QQuickItem, "followPointerSwitch")
    commit = window.findChild(QQuickItem, "actionCommitButton")
    assert all(item is not None for item in (picker, follow_pointer, commit))

    picker.setProperty("currentIndex", 3)
    follow_pointer.setProperty("checked", True)
    app.processEvents()
    QMetaObject.invokeMethod(commit, "click", Qt.DirectConnection)
    QTest.qWait(80)

    assert controller.actionModel.rowCount() == 1
    assert controller.actions[0].kind == "left_click"
    assert controller.actions[0].use_current_pointer is True
    assert controller.actions[0].x is None
    window.close()
    controller.shutdown()

def test_a_click_cannot_be_added_before_its_position_is_recorded():
    """An unrecorded click silently lands at (0,0) -- the target's corner."""
    engine, controller = build_engine(start_hotkeys=False)
    window = engine.rootObjects()[0]
    picker = window.findChild(QQuickItem, "actionTypePicker")
    commit = window.findChild(QQuickItem, "actionCommitButton")
    notice = window.findChild(QQuickItem, "pointerMissingNotice")
    assert all(item is not None for item in (picker, commit, notice))

    picker.setProperty("currentIndex", 3)  # Left click
    app.processEvents()
    QTest.qWait(60)
    assert commit.property("enabled") is False
    assert notice.isVisible() is True

    QMetaObject.invokeMethod(commit, "click", Qt.DirectConnection)
    QTest.qWait(60)
    assert controller.actionModel.rowCount() == 0

    # Recording a position releases it.
    controller.positionCaptured.emit(0, 640, 480, "screen", 0, 0)
    app.processEvents()
    QTest.qWait(60)
    assert commit.property("enabled") is True
    assert notice.isVisible() is False

    QMetaObject.invokeMethod(commit, "click", Qt.DirectConnection)
    QTest.qWait(80)
    assert controller.actionModel.rowCount() == 1
    assert (controller.actions[0].x, controller.actions[0].y) == (640, 480)

    window.close()
    controller.shutdown()

def test_a_follow_pointer_click_needs_no_recorded_position():
    engine, controller = build_engine(start_hotkeys=False)
    window = engine.rootObjects()[0]
    picker = window.findChild(QQuickItem, "actionTypePicker")
    follow = window.findChild(QQuickItem, "followPointerSwitch")
    commit = window.findChild(QQuickItem, "actionCommitButton")

    picker.setProperty("currentIndex", 3)
    app.processEvents()
    assert commit.property("enabled") is False

    follow.setProperty("checked", True)
    app.processEvents()
    QTest.qWait(60)
    assert commit.property("enabled") is True

    window.close()
    controller.shutdown()

def test_window_click_can_switch_to_follow_pointer_without_recording_again():
    """Switching a window-recorded click to Desktop + follow must not demand a re-record."""
    engine, controller = build_engine(start_hotkeys=False)
    controller._window_service = PickerWindowService()
    window = engine.rootObjects()[0]

    controller.setTargetMode("window")
    controller.selectWindowTarget("1001")
    controller.addAction(
        {
            "kind": "left_click",
            "x": "300",
            "y": "220",
            "coordinateSpace": "window",
            "referenceWidth": "800",
            "referenceHeight": "600",
        }
    )
    QTest.qWait(40)
    assert controller.actions[0].coordinate_space == "window"

    # The user now points the run at the desktop and wants the click to follow the mouse.
    controller.setTargetMode("desktop")
    controller.selectedIndex = 0
    QTest.qWait(40)

    follow_pointer = window.findChild(QQuickItem, "followPointerSwitch")
    commit = window.findChild(QQuickItem, "actionCommitButton")
    assert follow_pointer is not None and commit is not None

    follow_pointer.setProperty("checked", True)
    app.processEvents()
    assert commit.property("enabled") is True

    QMetaObject.invokeMethod(commit, "click", Qt.DirectConnection)
    QTest.qWait(80)

    saved = controller.actions[0]
    assert saved.use_current_pointer is True
    assert saved.coordinate_space == "screen"
    assert saved.reference_width == 0 and saved.reference_height == 0
    assert saved.x is None and saved.y is None
    window.close()
    controller.shutdown()

def test_inspector_tracks_the_selected_action_after_deletion():
    engine, controller = build_engine(start_hotkeys=False)
    window = engine.rootObjects()[0]
    controller.addAction({"kind": "key", "value": "a"})
    controller.addAction({"kind": "key", "value": "b"})
    QTest.qWait(40)
    assert window.property("editorIndex") == 1

    controller.deleteAction(1)
    QTest.qWait(40)
    assert controller.selectedIndex == 0
    assert window.property("editorIndex") == 0

    window.close()
    controller.shutdown()

def test_record_pointer_button_arms_a_frozen_picker_until_a_point_is_clicked(monkeypatch):
    monkeypatch.setattr(pyautogui, "position", lambda: SimpleNamespace(x=700, y=420))
    engine, controller = build_engine(start_hotkeys=False)
    window = engine.rootObjects()[0]
    picker = window.findChild(QQuickItem, "actionTypePicker")
    button = window.findChild(QQuickItem, "recordPointerPosition")
    assert picker is not None and button is not None

    picker.setProperty("currentIndex", 3)
    app.processEvents()
    QMetaObject.invokeMethod(button, "click", Qt.DirectConnection)
    QTest.qWait(30)
    assert controller.capturePending is True
    assert controller.captureCountdown == 0
    assert button.property("text") == "Cancel point picker"

    assert controller.commitPositionCapture(700, 420) is True
    QTest.qWait(30)
    assert controller.capturePending is False
    assert button.property("text") == "Pick pointer position"
    window.close()
    controller.shutdown()

def test_changing_action_type_cancels_key_recording_and_unblocks_pointer_picker(monkeypatch):
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
    engine, controller = build_engine(start_hotkeys=False)
    window = engine.rootObjects()[0]
    picker = window.findChild(QQuickItem, "actionTypePicker")
    key_record = window.findChild(QQuickItem, "recordActionKey")
    pointer_record = window.findChild(QQuickItem, "recordPointerPosition")
    assert all(item is not None for item in (picker, key_record, pointer_record))

    QMetaObject.invokeMethod(key_record, "click", Qt.DirectConnection)
    assert controller.actionCaptureMode == "key"
    picker.setProperty("currentIndex", 3)
    app.processEvents()
    QTest.qWait(40)

    assert listeners[-1].stopped is True
    assert controller.actionCaptureMode == ""
    assert pointer_record.isEnabled() is True
    QMetaObject.invokeMethod(pointer_record, "click", Qt.DirectConnection)
    QTest.qWait(30)
    assert controller.capturePending is True

    controller.cancelPositionCapture(announce=False)
    window.close()
    controller.shutdown()

def test_hotkey_action_has_a_recorder_that_populates_the_action_field(monkeypatch):
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
    engine, controller = build_engine(start_hotkeys=False)
    window = engine.rootObjects()[0]
    picker = window.findChild(QQuickItem, "actionTypePicker")
    recorder = window.findChild(QQuickItem, "recordActionHotkey")
    value_field = window.findChild(QQuickItem, "actionValueField")
    assert all(item is not None for item in (picker, recorder, value_field))

    picker.setProperty("currentIndex", 1)
    app.processEvents()
    QMetaObject.invokeMethod(recorder, "click", Qt.DirectConnection)
    assert controller.actionCaptureMode == "hotkey"
    assert recorder.property("text") == "Cancel hotkey recording"
    listener = listeners[-1]
    assert listener.on_press(qt_controller.keyboard.Key.ctrl_l) is None
    assert listener.on_press(qt_controller.keyboard.Key.shift) is None
    assert listener.on_press(qt_controller.keyboard.KeyCode.from_char("\x03")) is False
    QTest.qWait(40)

    assert controller.actionCaptureMode == ""
    assert value_field.property("text") == "ctrl+shift+c"
    assert recorder.property("text") == "Record hotkey"
    window.close()
    controller.shutdown()

def test_start_button_discloses_when_visible_run_settings_will_be_applied():
    engine, controller = build_engine(start_hotkeys=False)
    window = engine.rootObjects()[0]
    start = window.findChild(QQuickItem, "runStartButton")
    assert start is not None
    controller.addAction({"kind": "key", "value": "space"})
    controller.markRunSettingsPending()
    QTest.qWait(40)
    assert start.property("text") == "Apply & start"
    window.close()
    controller.shutdown()

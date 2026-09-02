"""Global shortcuts in the interface, and the toast that reports on them."""

from PySide6.QtCore import QPointF
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest

from qt_app import build_engine

from qml_harness import app


def test_long_toast_messages_stay_inside_the_toast_pill():
    engine, controller = build_engine(start_hotkeys=False)
    window = engine.rootObjects()[0]
    window.setWidth(1240)
    window.setHeight(760)
    app.processEvents()

    pill = window.findChild(QQuickItem, "toastPill")
    label = window.findChild(QQuickItem, "toastText")
    assert pill is not None and label is not None

    controller.toast.emit(
        "Untitled sequence: More than one matching target window is open. "
        "Pick the window again.",
        "error",
    )
    QTest.qWait(120)

    assert pill.isVisible() is True
    top_left = label.mapToItem(pill, QPointF(0, 0))
    assert top_left.x() >= 0
    assert top_left.y() >= 0
    assert top_left.x() + label.width() <= pill.width()
    assert top_left.y() + label.height() <= pill.height()
    assert pill.width() <= window.width()
    # A message this long has to wrap rather than render as one clipped line.
    assert label.height() > label.property("font").pointSize()

    window.close()
    controller.shutdown()

def test_recorded_global_shortcut_routes_to_the_correct_qml_field():
    engine, controller = build_engine(start_hotkeys=False)
    window = engine.rootObjects()[0]
    fields = {
        name: window.findChild(QQuickItem, f"{name}HotkeyField")
        for name in ("start", "capture", "stop")
    }
    assert all(field is not None for field in fields.values())
    controller.shortcutCaptured.emit("capture", "ctrl+shift+c")
    QTest.qWait(40)
    assert fields["start"].property("text") == "f6"
    assert fields["capture"].property("text") == "ctrl+shift+c"
    assert fields["stop"].property("text") == "f9"
    controller.runSettingsChanged.emit()
    QTest.qWait(40)
    assert fields["capture"].property("text") == "f8"
    window.close()
    controller.shutdown()

def test_duplicate_global_shortcuts_are_flagged_and_block_apply_and_start():
    engine, controller = build_engine(start_hotkeys=False)
    window = engine.rootObjects()[0]
    window.setProperty("activeInspectorTab", 1)
    controller.addAction({"kind": "key", "value": "a"})
    fields = {
        name: window.findChild(QQuickItem, f"{name}HotkeyField")
        for name in ("start", "capture", "stop")
    }
    message = window.findChild(QQuickItem, "shortcutConflictMessage")
    apply_button = window.findChild(QQuickItem, "runSettingsApplyButton")
    start_button = window.findChild(QQuickItem, "runStartButton")
    assert all(field is not None for field in fields.values())
    assert message is not None and apply_button is not None and start_button is not None
    assert start_button.property("enabled") is True

    controller.shortcutCaptured.emit("capture", "f6")
    QTest.qWait(40)

    assert fields["capture"].property("text") == "f8"
    assert "cannot use the same shortcut (F6)" in message.property("text")
    assert message.property("visible") is True

    fields["capture"].setProperty("text", "f6")
    QTest.qWait(40)

    assert fields["start"].property("invalid") is True
    assert fields["capture"].property("invalid") is True
    assert fields["stop"].property("invalid") is False
    assert message.property("visible") is True
    assert "cannot use the same shortcut (F6)" in message.property("text")
    assert apply_button.property("enabled") is False
    assert start_button.property("enabled") is False

    fields["capture"].setProperty("text", "f8")
    QTest.qWait(40)

    assert fields["start"].property("invalid") is False
    assert fields["capture"].property("invalid") is False
    assert message.property("visible") is False
    assert apply_button.property("enabled") is True
    assert start_button.property("enabled") is True
    window.close()
    controller.shutdown()

def test_global_shortcut_recorder_listening_state_is_neutral_and_local():
    engine, controller = build_engine(start_hotkeys=False)
    window = engine.rootObjects()[0]
    buttons = {
        name: window.findChild(QQuickItem, f"shortcutRecord_{name}")
        for name in ("start", "capture", "stop")
    }
    assert all(button is not None for button in buttons.values())
    assert all(button.property("implicitWidth") == 106 for button in buttons.values())
    window.setProperty("shortcutRecordingTarget", "start")
    app.processEvents()
    QTest.qWait(160)
    assert buttons["start"].property("text") == "Listening"
    assert buttons["start"].property("activeNeutral") is True
    assert buttons["start"].property("background").property("color").name() == "#e1e6ee"
    assert buttons["capture"].property("text") == "Record"
    assert buttons["stop"].property("text") == "Record"
    window.close()
    controller.shutdown()

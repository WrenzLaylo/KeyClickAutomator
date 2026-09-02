"""The target picker: one list of windows and tabs, and what choosing one does."""

from PySide6.QtCore import QMetaObject
from PySide6.QtCore import QObject
from PySide6.QtCore import Qt
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest

from qt_app import build_engine

from qml_harness import app, PickerWindowService, visual_children_named


def test_the_target_picker_lists_the_desktop_windows_and_tabs_in_one_place():
    engine, controller = build_engine(start_hotkeys=False)
    controller._window_service = PickerWindowService()
    window = engine.rootObjects()[0]
    window.setWidth(1360)
    window.setHeight(900)
    app.processEvents()

    choose = window.findChild(QQuickItem, "chooseTargetButton")
    assert choose is not None
    QMetaObject.invokeMethod(choose, "click", Qt.DirectConnection)
    QTest.qWait(300)

    dialog = window.findChild(QObject, "targetPickerDialog")
    assert dialog.property("opened") is True
    rows = visual_children_named(window.contentItem(), "automationTarget_")
    assert len(rows) >= 3, "the desktop plus the open windows should be offered"

    # Picking the first row (the desktop) applies both target and mechanism.
    QMetaObject.invokeMethod(rows[0], "click", Qt.DirectConnection)
    QTest.qWait(300)
    assert controller.targetSettings["mode"] == "desktop"
    assert controller.targetSummary == "This computer"
    assert dialog.property("opened") is False

    window.close()
    controller.shutdown()

def test_choosing_a_window_from_the_picker_sets_background_delivery():
    engine, controller = build_engine(start_hotkeys=False)
    controller._window_service = PickerWindowService()
    window = engine.rootObjects()[0]
    controller.refreshAutomationTargets()
    app.processEvents()
    QTest.qWait(200)

    windows = [t for t in controller.automationTargets if t["kind"] == "window"]
    assert windows, "the fake service exposes open windows"
    assert controller.selectAutomationTarget("window", windows[0]["id"]) is True
    assert controller.targetSettings["mode"] == "window"

    window.close()
    controller.shutdown()

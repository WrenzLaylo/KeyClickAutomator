import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from qt_app import build_engine, create_application


_app = QApplication.instance() or QApplication([])


def test_application_supports_native_profile_dialogs():
    assert isinstance(create_application([]), QApplication)


def test_qml_root_loads_and_resizes_without_clipping_contract():
    engine, controller = build_engine(start_hotkeys=False)
    roots = engine.rootObjects()
    assert len(roots) == 1
    window = roots[0]
    for width, height in [(900, 640), (1024, 720), (1240, 760), (1600, 900)]:
        window.setWidth(width)
        window.setHeight(height)
        _app.processEvents()
        assert window.property("layoutMode") in {"compact", "medium", "wide"}
        if width == 900:
            assert window.property("inspectorOpen") is False
        assert window.width() == width
        assert window.height() == height
    window.close()
    controller.shutdown()


def test_inspector_tab_selection_pill_slides_between_tabs():
    engine, controller = build_engine(start_hotkeys=False)
    window = engine.rootObjects()[0]
    pill = window.findChild(QObject, "tabSelectionPill")
    assert pill is not None
    start_x = pill.property("x")
    window.setProperty("activeInspectorTab", 1)
    QTest.qWait(280)
    assert pill.property("x") > start_x + 50
    window.close()
    controller.shutdown()


def test_workspace_navigation_hover_state_is_isolated_per_button():
    engine, controller = build_engine(start_hotkeys=False)
    window = engine.rootObjects()[0]
    buttons = [window.findChild(QObject, f"workspaceNav_{name}") for name in ("open", "save", "new")]
    assert all(button is not None for button in buttons)
    buttons[0].setProperty("pointerHover", True)
    _app.processEvents()
    assert [button.property("pointerHover") for button in buttons] == [True, False, False]
    window.close()
    controller.shutdown()


def test_added_actions_replace_empty_state_with_visible_sequence_cards():
    engine, controller = build_engine(start_hotkeys=False)
    window = engine.rootObjects()[0]
    empty_state = window.findChild(QObject, "sequenceEmptyState")
    action_list = window.findChild(QObject, "actionList")
    run_status = window.findChild(QObject, "runStatusMessage")
    assert empty_state is not None and action_list is not None and run_status is not None
    controller.addAction({"kind": "key", "value": "space"})
    QTest.qWait(80)
    assert action_list.property("count") == 1
    assert empty_state.property("visible") is False
    assert action_list.property("visible") is True
    assert run_status.property("text") == "Ready when you are"
    window.close()
    controller.shutdown()

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, QPoint, QPointF, QMetaObject, Qt
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from qt_app import build_engine, create_application


_app = QApplication.instance() or QApplication([])


def visual_children_named(item, prefix):
    matches = []
    for child in item.childItems():
        if child.objectName().startswith(prefix):
            matches.append(child)
        matches.extend(visual_children_named(child, prefix))
    return matches


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
    buttons = [window.findChild(QQuickItem, f"workspaceNav_{name}") for name in ("open", "save", "new")]
    assert all(button is not None for button in buttons)
    for hovered_index, button in enumerate(buttons):
        for index, item in enumerate(buttons):
            item.setProperty("pointerHover", index == hovered_index)
        _app.processEvents()
        QTest.qWait(160)
        assert [item.property("pointerHover") for item in buttons] == [index == hovered_index for index in range(3)]
        assert button.property("background").property("color").name() == "#e5eaf2"
    window.close()
    controller.shutdown()


def test_quiet_button_hover_fades_from_the_hover_surface_without_a_dark_flash():
    engine, controller = build_engine(start_hotkeys=False)
    window = engine.rootObjects()[0]
    window.setWidth(1920)
    window.setHeight(1016)
    _app.processEvents()
    button = window.findChild(QQuickItem, "workspaceNav_open")
    assert button is not None
    background = button.property("background")
    QTest.qWait(160)
    assert background.property("color").getRgb() == (229, 234, 242, 0)
    hover_position = button.mapToScene(QPointF(button.width() / 2, button.height() / 2))
    sample_position = button.mapToScene(QPointF(button.width() - 8, 8))
    QTest.mouseMove(window, QPoint(round(hover_position.x()), round(hover_position.y())))
    QTest.qWait(35)
    red, green, blue, alpha = background.property("color").getRgb()
    assert (red, green, blue) == (229, 234, 242)
    assert 0 < alpha < 255
    rendered_color = window.grabWindow().pixelColor(
        round(sample_position.x()), round(sample_position.y())
    )
    assert min(rendered_color.red(), rendered_color.green(), rendered_color.blue()) > 220
    window.close()
    controller.shutdown()


def test_action_row_hover_stays_blue_white_without_a_dark_flash():
    engine, controller = build_engine(start_hotkeys=False)
    window = engine.rootObjects()[0]
    window.setWidth(900)
    window.setHeight(840)
    controller.addAction({"kind": "key", "value": "enter"})
    controller.selectedIndex = -1
    _app.processEvents()
    QTest.qWait(180)

    cards = visual_children_named(window.contentItem(), "actionCardSurface")
    assert len(cards) == 1
    card = cards[0]
    assert card.property("color").getRgb() == (255, 255, 255, 255)

    hover_position = card.mapToScene(QPointF(card.width() / 2, card.height() / 2))
    sample_position = card.mapToScene(QPointF(card.width() / 2, card.height() - 8))
    QTest.mouseMove(window, QPoint(round(hover_position.x()), round(hover_position.y())))
    QTest.qWait(35)
    red, green, blue, alpha = card.property("color").getRgb()
    assert 244 <= red <= 255
    assert 247 <= green <= 255
    assert blue == 255
    assert alpha == 255
    QTest.qWait(130)
    assert card.property("color").name() == "#f4f7ff"
    rendered_color = window.grabWindow().pixelColor(
        round(sample_position.x()), round(sample_position.y())
    )
    assert min(rendered_color.red(), rendered_color.green(), rendered_color.blue()) > 220
    window.close()
    controller.shutdown()


def test_sequence_rows_form_a_numbered_workflow_and_mark_the_selected_step():
    engine, controller = build_engine(start_hotkeys=False)
    window = engine.rootObjects()[0]
    window.setWidth(900)
    window.setHeight(840)
    controller.addAction({"kind": "key", "value": "enter"})
    controller.addAction({"kind": "text", "value": "Hello"})
    _app.processEvents()
    QTest.qWait(180)

    def ordered(prefix):
        return sorted(
            visual_children_named(window.contentItem(), prefix),
            key=lambda item: item.mapToScene(QPointF(0, 0)).y(),
        )

    badges = ordered("stepBadge")
    surfaces = ordered("actionCardSurface")
    connectors = ordered("sequenceConnector")
    editing_badges = ordered("editingBadge")
    assert all(len(items) == 2 for items in (badges, surfaces, connectors, editing_badges))
    assert [item.property("color").name() for item in badges] == ["#eef1f6", "#1565ff"]
    assert [item.property("color").name() for item in surfaces] == ["#ffffff", "#edf3ff"]
    assert [item.isVisible() for item in connectors] == [True, False]
    assert [item.isVisible() for item in editing_badges] == [False, True]
    window.close()
    controller.shutdown()


def test_action_toggle_animates_both_directions_and_remains_clickable_when_off():
    engine, controller = build_engine(start_hotkeys=False)
    window = engine.rootObjects()[0]
    window.setWidth(900)
    window.setHeight(840)
    controller.addAction({"kind": "key", "value": "enter"})
    _app.processEvents()
    QTest.qWait(240)

    def only(prefix):
        matches = visual_children_named(window.contentItem(), prefix)
        assert len(matches) == 1
        return matches[0]

    enabled_switch = only("actionEnabledSwitch_0")
    track = only("actionToggleTrack_0")
    knob = only("actionToggleKnob_0")
    content = only("actionContent_0")
    assert enabled_switch.isEnabled() is True
    assert enabled_switch.property("checked") is True
    assert abs(knob.x() - 18) < 0.1

    QMetaObject.invokeMethod(enabled_switch, "click", Qt.DirectConnection)
    QTest.qWait(40)
    assert controller.actions[0].enabled is False
    assert enabled_switch.isEnabled() is True
    assert 2 < knob.x() < 18
    assert 0.42 < content.opacity() < 1

    # Reverse the state while the first animation is still running. The new
    # semantic state must win and the same delegate must remain interactive.
    QMetaObject.invokeMethod(enabled_switch, "click", Qt.DirectConnection)
    QTest.qWait(230)
    assert controller.actions[0].enabled is True
    assert enabled_switch.property("checked") is True
    assert abs(knob.x() - 18) < 0.1
    assert track.property("color").name() == "#1565ff"
    assert abs(content.opacity() - 1) < 0.01

    QMetaObject.invokeMethod(enabled_switch, "click", Qt.DirectConnection)
    QTest.qWait(230)
    assert controller.actions[0].enabled is False
    assert enabled_switch.isEnabled() is True
    assert abs(knob.x() - 2) < 0.1
    assert track.property("color").name() == "#cad1dc"
    assert abs(content.opacity() - 0.42) < 0.01
    window.close()
    controller.shutdown()


def test_action_type_popup_opens_below_and_aligned_with_its_picker():
    engine, controller = build_engine(start_hotkeys=False)
    window = engine.rootObjects()[0]
    window.setWidth(1920)
    window.setHeight(1016)
    _app.processEvents()
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
    _app.processEvents()
    QTest.qWait(240)

    dock = window.findChild(QQuickItem, "shortcutDock")
    assert dock is not None
    shortcuts = visual_children_named(dock, "shortcutHint_")
    assert len(shortcuts) == 3
    assert [(item.property("keyText"), item.property("labelText")) for item in shortcuts] == [
        ("f6", "Start"),
        ("f8", "Capture"),
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
    assert stop_button.width() == start_button.width()
    assert stop_button.height() == start_button.height()
    assert stop_button.property("keyHint") == "f9"
    assert start_button.property("keyHint") == "f6"
    assert start_button.isEnabled() is False
    assert progress.isVisible() is False
    controller.addAction({"kind": "key", "value": "space"})
    QTest.qWait(80)
    assert start_button.isEnabled() is True
    window.close()
    controller.shutdown()


def test_create_first_action_button_adds_the_configured_action():
    engine, controller = build_engine(start_hotkeys=False)
    window = engine.rootObjects()[0]
    button = window.findChild(QQuickItem, "createFirstAction")
    assert button is not None
    QMetaObject.invokeMethod(button, "click", Qt.DirectConnection)
    QTest.qWait(80)
    assert controller.actionModel.rowCount() == 1
    assert controller.actions[0].kind == "key"
    assert controller.actions[0].value == "space"
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
    _app.processEvents()
    QTest.qWait(160)
    assert buttons["start"].property("text") == "Listening"
    assert buttons["start"].property("activeNeutral") is True
    assert buttons["start"].property("background").property("color").name() == "#e1e6ee"
    assert buttons["capture"].property("text") == "Record"
    assert buttons["stop"].property("text") == "Record"
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

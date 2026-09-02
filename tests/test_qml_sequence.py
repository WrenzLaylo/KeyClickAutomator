"""The sequence page: cards, dragging, toggles, scrollbars, and the empty state."""

from PySide6.QtCore import QMetaObject
from PySide6.QtCore import QObject
from PySide6.QtCore import QPoint
from PySide6.QtCore import QPointF
from PySide6.QtCore import Qt
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest

from qt_app import build_engine

from qml_harness import app, show_tab, visual_children_named


def test_sequence_rows_form_a_numbered_workflow_and_mark_the_selected_step():
    engine, controller = build_engine(start_hotkeys=False)
    window = engine.rootObjects()[0]
    window.setWidth(900)
    window.setHeight(840)
    controller.addAction({"kind": "key", "value": "enter"})
    controller.addAction({"kind": "text", "value": "Hello"})
    app.processEvents()
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

def test_sequence_drag_handle_reorders_actions_and_marks_the_drop_position():
    engine, controller = build_engine(start_hotkeys=False)
    window = engine.rootObjects()[0]
    window.setWidth(900)
    window.setHeight(840)
    for value in ("a", "b", "c"):
        controller.addAction({"kind": "key", "value": value})
    app.processEvents()
    QTest.qWait(180)

    handles = visual_children_named(window.contentItem(), "actionDragHandle_")
    assert len(handles) == 3
    first_handle = next(item for item in handles if item.objectName() == "actionDragHandle_0")
    ordered = lambda prefix: sorted(
        visual_children_named(window.contentItem(), prefix),
        key=lambda item: item.mapToScene(QPointF(0, 0)).y(),
    )
    timeline_badge_positions = [
        badge.mapToScene(QPointF(0, 0)).y() for badge in ordered("stepBadge")
    ]
    timeline_connector_positions = [
        connector.mapToScene(QPointF(0, 0)).y()
        for connector in ordered("sequenceConnector")
    ]
    first_badge = ordered("stepBadge")[0]
    first_connector = ordered("sequenceConnector")[0]
    first_surface = ordered("actionCardSurface")[0]
    badge_y = first_badge.mapToScene(QPointF(0, 0)).y()
    surface_y = first_surface.mapToScene(QPointF(0, 0)).y()
    start = first_handle.mapToScene(
        QPointF(first_handle.width() / 2, first_handle.height() / 2)
    )
    start_point = QPoint(round(start.x()), round(start.y()))
    end_point = QPoint(start_point.x(), start_point.y() + 164)

    QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, start_point)
    QTest.mouseMove(window, QPoint(start_point.x(), start_point.y() + 20), 20)
    QTest.mouseMove(window, end_point, 40)
    QTest.qWait(60)
    assert window.property("draggedActionIndex") == 0
    assert window.property("dragTargetIndex") == 2
    assert abs(first_badge.mapToScene(QPointF(0, 0)).y() - badge_y) < 0.1
    assert first_connector.isVisible() is True
    assert first_surface.mapToScene(QPointF(0, 0)).y() > surface_y + 100
    indicators = visual_children_named(window.contentItem(), "sequenceDropIndicator_")
    assert sum(item.isVisible() for item in indicators) == 1

    QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, end_point)
    QTest.qWait(40)
    assert all(
        abs(current.mapToScene(QPointF(0, 0)).y() - expected) < 0.1
        for current, expected in zip(ordered("stepBadge"), timeline_badge_positions)
    )
    assert all(
        abs(current.mapToScene(QPointF(0, 0)).y() - expected) < 0.1
        for current, expected in zip(
            ordered("sequenceConnector"), timeline_connector_positions
        )
    )
    QTest.qWait(200)
    assert [action.value for action in controller.actions] == ["b", "c", "a"]
    assert controller.selectedIndex == 2
    assert window.property("draggedActionIndex") == -1
    window.close()
    controller.shutdown()

def test_action_toggle_animates_both_directions_and_remains_clickable_when_off():
    engine, controller = build_engine(start_hotkeys=False)
    window = engine.rootObjects()[0]
    window.setWidth(900)
    window.setHeight(840)
    controller.addAction({"kind": "key", "value": "enter"})
    app.processEvents()
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

def test_scrollbars_hide_without_overflow_and_sequence_cards_keep_a_gutter():
    engine, controller = build_engine(start_hotkeys=False)
    window = engine.rootObjects()[0]
    # The inspector is boxed between the tab header and the full-width run bar, so it
    # needs a taller window than the old edge-to-edge panel to show the form uncropped.
    window.setWidth(1360)
    window.setHeight(960)
    controller.addAction({"kind": "left_click", "x": 0, "y": 0})
    app.processEvents()
    QTest.qWait(80)

    editor_scrollbar = window.findChild(QQuickItem, "editorScrollBar")
    sequence_scrollbar = window.findChild(QQuickItem, "sequenceScrollBar")
    action_list = window.findChild(QQuickItem, "actionList")
    assert all(item is not None for item in (editor_scrollbar, sequence_scrollbar, action_list))
    assert editor_scrollbar.property("size") == 1
    assert editor_scrollbar.isVisible() is False
    assert sequence_scrollbar.isVisible() is False

    # Shrinking below the form's height brings the scrollbar back, and only then.
    window.setHeight(800)
    app.processEvents()
    QTest.qWait(80)
    assert editor_scrollbar.property("size") < 1
    assert editor_scrollbar.isVisible() is True

    window.setWidth(900)
    window.setHeight(640)
    for _ in range(11):
        controller.addAction({"kind": "left_click", "x": 0, "y": 0})
    app.processEvents()
    QTest.qWait(80)

    assert sequence_scrollbar.isVisible() is True
    assert sequence_scrollbar.property("size") < 1
    first_surface = visual_children_named(window.contentItem(), "actionCardSurface")[0]
    surface_position = first_surface.mapToItem(action_list, QPointF(0, 0))
    scrollbar_position = sequence_scrollbar.mapToItem(action_list, QPointF(0, 0))
    gutter = scrollbar_position.x() - (surface_position.x() + first_surface.width())
    assert gutter >= 7.9

    window.close()
    controller.shutdown()

def test_create_first_action_button_opens_the_editor_without_inserting_a_default():
    engine, controller = build_engine(start_hotkeys=False)
    window = engine.rootObjects()[0]
    button = window.findChild(QQuickItem, "createFirstAction")
    assert button is not None
    QMetaObject.invokeMethod(button, "click", Qt.DirectConnection)
    QTest.qWait(80)
    assert controller.actionModel.rowCount() == 0
    assert window.property("activeInspectorTab") == 0
    assert window.property("editorIndex") == -1
    assert window.property("inspectorOpen") is True
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

def test_editing_the_sequence_from_another_tab_lands_you_on_the_sequence(tmp_path):
    """New sequence used to wipe the sequence silently while you watched the Runner."""
    from engine import Action, RunSettings, save_profile

    path = tmp_path / "Mine.kca.json"
    save_profile(path, [Action("key", value="a"), Action("key", value="b")],
                 RunSettings(start_delay=0))
    engine, controller = build_engine(start_hotkeys=False, profile_directory=tmp_path)
    window = engine.rootObjects()[0]
    assert controller.openProfilePath(str(path)) is True
    assert controller.dirty is False

    show_tab(window, 2, settle=150)          # Runner
    new_button = window.findChild(QQuickItem, "workspaceNav_new")
    QMetaObject.invokeMethod(new_button, "click", Qt.DirectConnection)
    QTest.qWait(200)

    # The sequence is cleared, so you must be looking at it.
    assert controller.actionModel.rowCount() == 0
    assert window.property("activeTab") == 0
    assert window.findChild(QQuickItem, "runInspector").isVisible() is True

    window.close()
    controller.shutdown()

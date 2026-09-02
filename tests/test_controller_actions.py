"""Editing the sequence: adding, reordering, toggling, deleting, undoing."""

from PySide6.QtTest import QSignalSpy

from qt_controller import ActionListModel
from qt_controller import AutomatorController


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

def test_editing_disabled_action_preserves_disabled_state():
    controller = AutomatorController(start_hotkeys=False)
    controller.addAction({"kind": "key", "value": "a", "enabled": False})
    controller.updateAction(0, {"kind": "key", "value": "b", "enabled": True})
    assert controller.actions[0].value == "b"
    assert controller.actions[0].enabled is False
    controller.shutdown()

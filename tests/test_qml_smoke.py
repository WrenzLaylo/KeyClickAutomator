import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, QPoint, QPointF, QMetaObject, Q_ARG, Qt
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

import pyautogui

import qt_controller
from qt_app import build_engine, create_application
from window_backend import WindowInfo


_app = QApplication.instance() or QApplication([])


class PickerWindowService:
    def __init__(self):
        self.windows = [
            WindowInfo(1001, "Team chat", "Chrome_WidgetWin_1", r"C:\\Apps\\Discord.exe", 51),
            WindowInfo(1002, "Daily meeting - Google Meet", "Chrome_WidgetWin_1", r"C:\\Apps\\chrome.exe", 52),
        ]

    def list_windows(self, excluded_process_id=0):
        return self.windows

    def ensure_usable(self, hwnd):
        return None

    def ensure_responsive(self, hwnd):
        return None


def show_tab(window, index, settle=200):
    """Switch workspace tabs exactly the way the tab bar does."""
    assert QMetaObject.invokeMethod(
        window, "selectTab", Qt.DirectConnection, Q_ARG("QVariant", index)
    )
    _app.processEvents()
    QTest.qWait(settle)
    assert window.property("activeTab") == index


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


def test_header_status_badge_aligns_with_the_sequence_heading():
    engine, controller = build_engine(start_hotkeys=False)
    window = engine.rootObjects()[0]
    window.setWidth(1360)
    window.setHeight(840)
    _app.processEvents()

    heading = window.findChild(QQuickItem, "sequenceHeading")
    status = window.findChild(QQuickItem, "headerStatusBadge")
    header_row = window.findChild(QQuickItem, "sequenceHeaderRow")
    assert heading is not None and status is not None and header_row is not None
    heading_position = heading.mapToScene(QPointF(0, 0))
    status_position = status.mapToScene(QPointF(0, 0))
    header_position = header_row.mapToScene(QPointF(0, 0))
    assert abs(status_position.y() - heading_position.y()) < 0.1
    assert status.height() == heading.height()
    assert abs(header_row.width() - header_row.parentItem().width()) < 0.1
    assert abs(
        status_position.x() + status.width() - header_position.x() - header_row.width()
    ) <= 0.5

    window.close()
    controller.shutdown()


def test_workspace_navigation_hover_state_is_isolated_per_button():
    engine, controller = build_engine(start_hotkeys=False)
    window = engine.rootObjects()[0]
    buttons = [window.findChild(QQuickItem, f"workspaceNav_{name}") for name in ("save", "new")]
    assert all(button is not None for button in buttons)
    for hovered_index, button in enumerate(buttons):
        for index, item in enumerate(buttons):
            item.setProperty("pointerHover", index == hovered_index)
        _app.processEvents()
        QTest.qWait(160)
        assert [item.property("pointerHover") for item in buttons] == [
            index == hovered_index for index in range(len(buttons))
        ]
        assert button.property("background").property("color").name() == "#e5eaf2"
    window.close()
    controller.shutdown()


def test_workspace_tabs_switch_pages_and_collapse_labels_when_narrow():
    engine, controller = build_engine(start_hotkeys=False)
    window = engine.rootObjects()[0]
    window.setWidth(1360)
    window.setHeight(840)
    _app.processEvents()

    tabs = [
        window.findChild(QQuickItem, f"workspaceTab_{name}")
        for name in ("sequence", "profiles", "runner")
    ]
    stack = window.findChild(QQuickItem, "workspaceStack")
    inspector_pane = window.findChild(QQuickItem, "runInspector")
    assert all(tab is not None for tab in tabs)
    assert stack is not None and inspector_pane is not None

    # Exactly one tab reads as selected, and it tracks the visible page.
    for index in (0, 1, 2):
        show_tab(window, index, settle=120)
        assert [tab.property("selected") for tab in tabs] == [
            position == index for position in range(3)
        ]
        assert stack.property("currentIndex") == index
        # The inspector edits the sequence, so it only rides along with that tab.
        assert inspector_pane.isVisible() is (index == 0)

    show_tab(window, 0, settle=120)
    wide_widths = [tab.width() for tab in tabs]

    window.setWidth(960)
    _app.processEvents()
    QTest.qWait(120)
    assert window.property("layoutMode") == "compact"
    narrow_widths = [tab.width() for tab in tabs]
    for wide, narrow in zip(wide_widths, narrow_widths):
        assert narrow < wide

    window.close()
    controller.shutdown()


def test_quiet_button_hover_fades_from_the_hover_surface_without_a_dark_flash():
    engine, controller = build_engine(start_hotkeys=False)
    window = engine.rootObjects()[0]
    window.setWidth(1920)
    window.setHeight(1016)
    _app.processEvents()
    button = window.findChild(QQuickItem, "workspaceNav_save")
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


def test_sequence_drag_handle_reorders_actions_and_marks_the_drop_position():
    engine, controller = build_engine(start_hotkeys=False)
    window = engine.rootObjects()[0]
    window.setWidth(900)
    window.setHeight(840)
    for value in ("a", "b", "c"):
        controller.addAction({"kind": "key", "value": value})
    _app.processEvents()
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


def test_recovery_dialog_actions_are_sized_and_contained_in_the_modal():
    engine, controller = build_engine(start_hotkeys=False)
    window = engine.rootObjects()[0]
    window.setWidth(900)
    window.setHeight(640)
    dialog = window.findChild(QObject, "recoveryDialog")
    assert dialog is not None
    QMetaObject.invokeMethod(dialog, "open", Qt.DirectConnection)
    QTest.qWait(100)

    background = dialog.property("background")
    discard = window.findChild(QQuickItem, "recoveryDiscardButton")
    recover = window.findChild(QQuickItem, "recoveryAcceptButton")
    discard_label = visual_children_named(
        window.contentItem(), "recoveryDiscardButton_label"
    )[0]
    recover_label = visual_children_named(
        window.contentItem(), "recoveryAcceptButton_label"
    )[0]
    assert all(
        item is not None
        for item in (background, discard, recover, discard_label, recover_label)
    )
    background_position = background.mapToScene(QPointF(0, 0))
    discard_position = discard.mapToScene(QPointF(0, 0))
    recover_position = recover.mapToScene(QPointF(0, 0))
    discard_label_position = discard_label.mapToItem(discard, QPointF(0, 0))
    recover_label_position = recover_label.mapToItem(recover, QPointF(0, 0))

    assert abs(discard.width() - 88) < 0.1
    assert abs(recover.width() - 148) < 0.1
    assert abs(
        discard_label_position.x() + discard_label.width() / 2 - discard.width() / 2
    ) <= 0.5
    assert abs(
        recover_label_position.x() + recover_label.width() / 2 - recover.width() / 2
    ) <= 0.5
    assert abs(discard_position.y() - recover_position.y()) < 0.1
    assert discard_position.x() >= background_position.x() + 20
    assert recover_position.x() + recover.width() <= background_position.x() + background.width() - 20
    assert recover_position.y() + recover.height() <= background_position.y() + background.height() - 20
    assert recover_position.x() - (discard_position.x() + discard.width()) >= 7

    QMetaObject.invokeMethod(dialog, "close", Qt.DirectConnection)
    window.close()
    controller.shutdown()


def test_unsaved_dialog_actions_are_grouped_and_contained_in_the_modal():
    engine, controller = build_engine(start_hotkeys=False)
    window = engine.rootObjects()[0]
    window.setWidth(900)
    window.setHeight(640)
    dialog = window.findChild(QObject, "unsavedChangesDialog")
    assert dialog is not None
    QMetaObject.invokeMethod(dialog, "open", Qt.DirectConnection)
    QTest.qWait(100)

    background = dialog.property("background")
    cancel = window.findChild(QQuickItem, "unsavedCancelButton")
    discard = window.findChild(QQuickItem, "unsavedDiscardButton")
    save = window.findChild(QQuickItem, "unsavedSaveButton")
    assert all(item is not None for item in (background, cancel, discard, save))
    background_position = background.mapToScene(QPointF(0, 0))
    cancel_position = cancel.mapToScene(QPointF(0, 0))
    discard_position = discard.mapToScene(QPointF(0, 0))
    save_position = save.mapToScene(QPointF(0, 0))

    assert abs(cancel.width() - discard.width()) <= 1
    assert abs(discard.width() - save.width()) <= 1
    assert cancel.height() == discard.height() == save.height() == 44
    assert abs(cancel_position.y() - discard_position.y()) < 0.1
    assert abs(discard_position.y() - save_position.y()) < 0.1
    assert cancel_position.x() >= background_position.x() + 20
    assert save_position.x() + save.width() <= background_position.x() + background.width() - 20
    assert save_position.y() + save.height() <= background_position.y() + background.height() - 20
    assert discard_position.x() - (cancel_position.x() + cancel.width()) >= 7
    assert save_position.x() - (discard_position.x() + discard.width()) >= 7

    QMetaObject.invokeMethod(dialog, "close", Qt.DirectConnection)
    window.close()
    controller.shutdown()


def test_profile_library_switches_profiles_and_protects_unsaved_changes(tmp_path):
    first_path = tmp_path / "First sequence.kca.json"
    second_path = tmp_path / "Second sequence.kca.json"
    qt_controller.save_profile(
        first_path,
        [qt_controller.Action("key", value="a")],
        qt_controller.RunSettings(),
    )
    qt_controller.save_profile(
        second_path,
        [qt_controller.Action("key", value="b")],
        qt_controller.RunSettings(),
    )
    engine, controller = build_engine(
        start_hotkeys=False,
        profile_directory=tmp_path,
    )
    window = engine.rootObjects()[0]
    page = window.findChild(QQuickItem, "profileLibraryPage")
    unsaved = window.findChild(QObject, "unsavedChangesDialog")
    assert page is not None and unsaved is not None
    show_tab(window, 1, settle=280)

    runner = window.findChild(QQuickItem, "profileLibraryRunnerButton")
    save_as = window.findChild(QQuickItem, "profileLibrarySaveAsButton")
    open_file = window.findChild(QQuickItem, "profileLibraryOpenFileButton")
    assert runner is not None and save_as is not None and open_file is not None
    assert abs(runner.width() - 112) < 0.1
    assert abs(save_as.width() - 112) < 0.1
    assert abs(open_file.width() - 112) < 0.1
    runner_position = runner.mapToScene(QPointF(0, 0))
    save_position = save_as.mapToScene(QPointF(0, 0))
    open_position = open_file.mapToScene(QPointF(0, 0))
    assert save_position.x() - (runner_position.x() + runner.width()) >= 7
    assert open_position.x() - (save_position.x() + save_as.width()) >= 7

    rows = visual_children_named(window.contentItem(), "profileLibraryRow_")
    assert len(rows) == 2
    first_row = next(
        row for row in rows if row.property("profilePath") == str(first_path.resolve())
    )
    QMetaObject.invokeMethod(first_row, "click", Qt.DirectConnection)
    QTest.qWait(220)
    assert controller.currentProfileName == "First sequence"
    assert window.property("activeTab") == 0

    controller.addAction({"kind": "key", "value": "x"})
    assert controller.dirty is True
    show_tab(window, 1, settle=280)
    rows = visual_children_named(window.contentItem(), "profileLibraryRow_")
    second_row = next(
        row for row in rows if row.property("profilePath") == str(second_path.resolve())
    )
    QMetaObject.invokeMethod(second_row, "click", Qt.DirectConnection)
    QTest.qWait(100)

    assert unsaved.property("opened") is True
    assert controller.currentProfileName == "First sequence"
    assert window.property("pendingProfilePath") == str(second_path.resolve())
    discard = window.findChild(QQuickItem, "unsavedDiscardButton")
    assert discard is not None
    QMetaObject.invokeMethod(discard, "click", Qt.DirectConnection)
    QTest.qWait(240)
    assert controller.currentProfileName == "Second sequence"
    assert [action.value for action in controller.actions] == ["b"]
    assert window.property("activeTab") == 0
    window.close()
    controller.shutdown()


def test_profiles_can_be_queued_without_switching_and_reordered_in_runner(tmp_path):
    first_path = tmp_path / "First sequence.kca.json"
    second_path = tmp_path / "Second sequence.kca.json"
    qt_controller.save_profile(
        first_path,
        [qt_controller.Action("key", value="a")],
        qt_controller.RunSettings(),
    )
    qt_controller.save_profile(
        second_path,
        [qt_controller.Action("key", value="b")],
        qt_controller.RunSettings(),
    )
    engine, controller = build_engine(
        start_hotkeys=False,
        profile_directory=tmp_path,
    )
    window = engine.rootObjects()[0]
    profile_page = window.findChild(QQuickItem, "profileLibraryPage")
    queue_page = window.findChild(QQuickItem, "runQueuePage")
    assert profile_page is not None and queue_page is not None
    show_tab(window, 1, settle=240)

    rows = visual_children_named(window.contentItem(), "profileLibraryRow_")
    first_row = next(
        row for row in rows if row.property("profilePath") == str(first_path.resolve())
    )
    second_row = next(
        row for row in rows if row.property("profilePath") == str(second_path.resolve())
    )
    first_index = first_row.objectName().removeprefix("profileLibraryRow_")
    second_index = second_row.objectName().removeprefix("profileLibraryRow_")
    first_queue = visual_children_named(
        window.contentItem(), "queueProfileButton_" + first_index
    )[0]
    second_queue = visual_children_named(
        window.contentItem(), "queueProfileButton_" + second_index
    )[0]

    QMetaObject.invokeMethod(first_queue, "click", Qt.DirectConnection)
    QTest.qWait(80)
    assert controller.runQueuePaths == [str(first_path.resolve())]
    assert controller.currentProfileName == "Untitled sequence"
    assert window.property("activeTab") == 1
    assert first_queue.property("text") == "Queued"

    QMetaObject.invokeMethod(second_queue, "click", Qt.DirectConnection)
    QTest.qWait(80)
    assert controller.runQueueCount == 2
    runner_button = window.findChild(QQuickItem, "profileLibraryRunnerButton")
    assert runner_button is not None
    QMetaObject.invokeMethod(runner_button, "click", Qt.DirectConnection)
    QTest.qWait(600)
    assert window.property("activeTab") == 2

    parallel_mode = window.findChild(QQuickItem, "runQueueParallelModeButton")
    sequential_mode = window.findChild(QQuickItem, "runQueueSequentialModeButton")
    assert parallel_mode is not None and sequential_mode is not None
    QMetaObject.invokeMethod(parallel_mode, "click", Qt.DirectConnection)
    QTest.qWait(80)
    assert controller.runQueueMode == "parallel"
    assert parallel_mode.property("activeNeutral") is True
    QMetaObject.invokeMethod(sequential_mode, "click", Qt.DirectConnection)
    QTest.qWait(80)
    assert controller.runQueueMode == "sequential"

    cards = visual_children_named(window.contentItem(), "runQueueCard_")
    assert len(cards) == 2
    assert [entry["profileName"] for entry in controller.runQueueEntries] == [
        "First sequence",
        "Second sequence",
    ]
    move_down = visual_children_named(window.contentItem(), "runQueueMoveDown_0")[0]
    assert move_down.isEnabled()
    QMetaObject.invokeMethod(move_down, "click", Qt.DirectConnection)
    QTest.qWait(80)
    assert [entry["profileName"] for entry in controller.runQueueEntries] == [
        "Second sequence",
        "First sequence",
    ]

    remove_first = visual_children_named(window.contentItem(), "runQueueRemove_0")[0]
    QMetaObject.invokeMethod(remove_first, "click", Qt.DirectConnection)
    QTest.qWait(80)
    assert controller.runQueuePaths == [str(first_path.resolve())]
    window.close()
    controller.shutdown()


def test_run_queue_scrollbar_stays_inside_the_page_with_many_profiles(tmp_path):
    paths = []
    for index in range(10):
        path = tmp_path / f"Profile {index + 1:02d}.kca.json"
        qt_controller.save_profile(
            path,
            [qt_controller.Action("key", value="tab")],
            qt_controller.RunSettings(),
        )
        paths.append(path)

    engine, controller = build_engine(
        start_hotkeys=False,
        profile_directory=tmp_path,
    )
    for path in paths:
        assert controller.enqueueProfile(str(path)) is True

    window = engine.rootObjects()[0]
    window.setWidth(900)
    window.setHeight(640)
    page = window.findChild(QQuickItem, "runQueuePage")
    queue_list = window.findChild(QQuickItem, "runQueueList")
    scroll_bar = window.findChild(QQuickItem, "runQueueScrollBar")
    assert page is not None and queue_list is not None and scroll_bar is not None

    show_tab(window, 2, settle=300)
    assert scroll_bar.isVisible()
    list_position = queue_list.mapToScene(QPointF(0, 0))
    bar_position = scroll_bar.mapToScene(QPointF(0, 0))
    assert bar_position.x() >= list_position.x()
    assert bar_position.x() + scroll_bar.width() <= list_position.x() + queue_list.width()
    assert bar_position.y() >= list_position.y()
    assert bar_position.y() + scroll_bar.height() <= list_position.y() + queue_list.height()

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
    _app.processEvents()
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


def test_scrollbars_hide_without_overflow_and_sequence_cards_keep_a_gutter():
    engine, controller = build_engine(start_hotkeys=False)
    window = engine.rootObjects()[0]
    # The inspector is boxed between the tab header and the full-width run bar, so it
    # needs a taller window than the old edge-to-edge panel to show the form uncropped.
    window.setWidth(1360)
    window.setHeight(960)
    controller.addAction({"kind": "left_click", "x": 0, "y": 0})
    _app.processEvents()
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
    _app.processEvents()
    QTest.qWait(80)
    assert editor_scrollbar.property("size") < 1
    assert editor_scrollbar.isVisible() is True

    window.setWidth(900)
    window.setHeight(640)
    for _ in range(11):
        controller.addAction({"kind": "left_click", "x": 0, "y": 0})
    _app.processEvents()
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


def test_click_action_can_be_added_in_follow_current_pointer_mode():
    engine, controller = build_engine(start_hotkeys=False)
    window = engine.rootObjects()[0]
    picker = window.findChild(QQuickItem, "actionTypePicker")
    follow_pointer = window.findChild(QQuickItem, "followPointerSwitch")
    commit = window.findChild(QQuickItem, "actionCommitButton")
    assert all(item is not None for item in (picker, follow_pointer, commit))

    picker.setProperty("currentIndex", 3)
    follow_pointer.setProperty("checked", True)
    _app.processEvents()
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
    _app.processEvents()
    QTest.qWait(60)
    assert commit.property("enabled") is False
    assert notice.isVisible() is True

    QMetaObject.invokeMethod(commit, "click", Qt.DirectConnection)
    QTest.qWait(60)
    assert controller.actionModel.rowCount() == 0

    # Recording a position releases it.
    controller.positionCaptured.emit(0, 640, 480, "screen", 0, 0)
    _app.processEvents()
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
    _app.processEvents()
    assert commit.property("enabled") is False

    follow.setProperty("checked", True)
    _app.processEvents()
    QTest.qWait(60)
    assert commit.property("enabled") is True

    window.close()
    controller.shutdown()


def test_long_toast_messages_stay_inside_the_toast_pill():
    engine, controller = build_engine(start_hotkeys=False)
    window = engine.rootObjects()[0]
    window.setWidth(1240)
    window.setHeight(760)
    _app.processEvents()

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
    _app.processEvents()
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
    _app.processEvents()
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
    _app.processEvents()
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
    _app.processEvents()
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


def test_a_saved_over_profile_can_be_restored_from_the_profiles_page(tmp_path):
    """End to end for the accident that emptied two real profiles."""
    from engine import Action, RunSettings, save_profile

    path = tmp_path / "Mine.kca.json"
    save_profile(path, [Action("key", value="a"), Action("key", value="b")],
                 RunSettings(start_delay=0))
    engine, controller = build_engine(start_hotkeys=False, profile_directory=tmp_path)
    window = engine.rootObjects()[0]
    window.setWidth(1360)
    window.setHeight(900)
    controller.openProfilePath(str(path))

    # Overwrite it with an empty sequence, exactly as a stray click would.
    controller.clearActions()
    controller._save_profile_path(str(path))
    assert controller.actionModel.rowCount() == 0

    show_tab(window, 1, settle=250)
    history_button = visual_children_named(window.contentItem(), "profileHistoryButton_")[0]
    QMetaObject.invokeMethod(history_button, "click", Qt.DirectConnection)
    QTest.qWait(250)

    dialog = window.findChild(QObject, "profileHistoryDialog")
    assert dialog.property("opened") is True
    rows = visual_children_named(window.contentItem(), "profileHistoryRow_")
    assert rows, "the overwritten version should be listed"

    restore = visual_children_named(window.contentItem(), "restoreProfileVersion_")[0]
    QMetaObject.invokeMethod(restore, "click", Qt.DirectConnection)
    QTest.qWait(300)

    assert [action.value for action in controller.actions] == ["a", "b"]
    window.close()
    controller.shutdown()


def test_the_target_picker_lists_the_desktop_windows_and_tabs_in_one_place():
    engine, controller = build_engine(start_hotkeys=False)
    controller._window_service = PickerWindowService()
    window = engine.rootObjects()[0]
    window.setWidth(1360)
    window.setHeight(900)
    _app.processEvents()

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
    _app.processEvents()
    QTest.qWait(200)

    windows = [t for t in controller.automationTargets if t["kind"] == "window"]
    assert windows, "the fake service exposes open windows"
    assert controller.selectAutomationTarget("window", windows[0]["id"]) is True
    assert controller.targetSettings["mode"] == "window"

    window.close()
    controller.shutdown()

"""Profiles and the runner queue, and the dialogs that guard unsaved work."""

from PySide6.QtCore import QMetaObject
from PySide6.QtCore import QObject
from PySide6.QtCore import QPointF
from PySide6.QtCore import Qt
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest

from qt_app import build_engine
import qt_controller

from qml_harness import show_tab, visual_children_named


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

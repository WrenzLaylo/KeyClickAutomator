import threading
from types import SimpleNamespace

import pyautogui
from pynput import keyboard
from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtTest import QSignalSpy, QTest

import controller_running
import qt_controller
import profile_catalog
from engine import Action, RunSettings, load_profile, save_profile
import controller_targeting
from qt_controller import ActionListModel, AutomatorController
from run_session import RunSession
from chrome_backend import ChromeTargetError
from window_backend import WindowInfo, WindowTargetError


_app = QCoreApplication.instance() or QCoreApplication([])


class FakeWindowService:
    def __init__(self):
        self.info = WindowInfo(
            hwnd=444,
            title="Target App",
            class_name="TargetWindow",
            executable=r"C:\\Apps\\target.exe",
            process_id=987654,
        )

    def window_at_point(self, x, y):
        return self.info

    def list_windows(self, excluded_process_id=0):
        return [self.info]

    def resolve_window(self, selector, preferred_hwnd=0):
        return self.info

    def ensure_usable(self, hwnd):
        return None

    def ensure_responsive(self, hwnd):
        return None

    def client_size(self, hwnd):
        return 800, 600

    def screen_to_client(self, hwnd, x, y):
        return x - 100, y - 200

    def mouse_target(self, root_hwnd, x, y):
        return root_hwnd, x, y


class MultiWindowService(FakeWindowService):
    def __init__(self, aliases: dict[str, int] | None = None):
        self.aliases = aliases or {"Window A": 101, "Window B": 202}
        self.responsive_checks: list[int] = []

    def _info(self, title: str, hwnd: int) -> WindowInfo:
        return WindowInfo(
            hwnd=hwnd,
            title=title,
            class_name="TargetWindow",
            executable=rf"C:\\Apps\\target-{hwnd}.exe",
            process_id=hwnd + 1000,
        )

    def list_windows(self, excluded_process_id=0):
        return [self._info(title, hwnd) for title, hwnd in self.aliases.items()]

    def resolve_window(self, selector, preferred_hwnd=0):
        if selector.title not in self.aliases:
            raise WindowTargetError("The target window is not open.")
        return self._info(selector.title, self.aliases[selector.title])

    def ensure_responsive(self, hwnd):
        self.responsive_checks.append(hwnd)


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


def test_indefinite_setting_is_explicitly_preserved():
    controller = AutomatorController(start_hotkeys=False)
    controller.applyRunSettings({"repeatForever": True, "repeatCount": 9, "startDelay": 0})
    assert controller.runSettings["repeatForever"] is True
    assert controller.runSettings["repeatCount"] == 9
    controller.shutdown()


def test_pending_run_settings_block_the_global_start_shortcut():
    controller = AutomatorController(start_hotkeys=False)
    controller.addAction({"kind": "key", "value": "a"})
    toast_spy = QSignalSpy(controller.toast)

    controller.markRunSettingsPending()
    controller.startRun()

    assert controller.runSettingsPending is True
    assert controller.running is False
    assert "Apply the edited Run settings" in toast_spy.at(toast_spy.count() - 1)[0]
    controller.shutdown()


def test_test_action_forces_one_repeat_and_a_three_second_safety_delay(monkeypatch):
    controller = AutomatorController(start_hotkeys=False)
    controller.addAction({"kind": "key", "value": "a", "repeats": 9, "delay": 4})
    captured = {}

    def fake_begin(actions, indices, settings, message, status_verb="Running"):
        captured.update(actions=actions, indices=indices, settings=settings, message=message, verb=status_verb)
        return True

    monkeypatch.setattr(controller, "_begin_run", fake_begin)
    assert controller.testActionWithSettings(0, {
        "repeatCount": 7,
        "repeatForever": True,
        "startDelay": 0,
        "jitter": 2,
    }) is True

    assert captured["indices"] == [0]
    assert captured["actions"][0].repeats == 1
    assert captured["actions"][0].delay_after == 0
    assert captured["settings"].repeat_count == 1
    assert captured["settings"].repeat_forever is False
    assert captured["settings"].start_delay == 3
    assert captured["settings"].delay_jitter == 0
    assert captured["verb"] == "Testing"
    controller.shutdown()


def test_run_from_here_maps_progress_back_to_the_original_step(monkeypatch):
    controller = AutomatorController(start_hotkeys=False)
    controller.addAction({"kind": "key", "value": "a"})
    controller.addAction({"kind": "key", "value": "b", "enabled": False})
    controller.addAction({"kind": "key", "value": "c"})
    captured = {}

    def fake_begin(actions, indices, settings, message, status_verb="Running"):
        captured.update(actions=actions, indices=indices)
        return True

    monkeypatch.setattr(controller, "_begin_run", fake_begin)
    assert controller.startRunFromWithSettings(1, {"startDelay": 0}) is True
    assert [action.value for action in captured["actions"]] == ["c"]
    assert captured["indices"] == [2]

    controller._active_session = RunSession(
        profile_name="Untitled sequence",
        profile_path="",
        actions=captured["actions"],
        action_indices=[2],
        settings=RunSettings(),
        completion_message="Run complete",
    )
    controller._handle_progress(
        controller._active_session.session_id,
        "action",
        0,
        1,
    )
    assert controller.runningActionIndex == 2
    assert controller.status == "Running step 3"
    controller.shutdown()


def test_saved_profiles_can_be_queued_reordered_and_removed(tmp_path):
    first = tmp_path / "First.kca.json"
    second = tmp_path / "Second.kca.json"
    save_profile(first, [Action("key", value="a")], RunSettings())
    save_profile(second, [Action("key", value="b")], RunSettings())
    controller = AutomatorController(start_hotkeys=False, profile_directory=tmp_path)
    toasts = QSignalSpy(controller.toast)

    assert controller.enqueueProfile(str(first)) is True
    assert controller.enqueueProfile(str(first)) is False
    assert "already in the run queue" in toasts.at(toasts.count() - 1)[0]
    assert controller.enqueueProfile(str(second)) is True
    assert [entry["profileName"] for entry in controller.runQueueEntries] == [
        "First",
        "Second",
    ]
    assert controller.runQueueEntries[0]["target"] == "Desktop"
    assert controller.runQueueEntries[0]["actionCount"] == 1

    assert controller.moveQueuedProfile(1, -1) is True
    assert [entry["profileName"] for entry in controller.runQueueEntries] == [
        "Second",
        "First",
    ]
    assert controller.removeQueuedProfile(1) is True
    assert controller.runQueuePaths == [str(second.resolve())]
    assert controller.clearRunQueue() is True
    assert controller.runQueueCount == 0
    controller.shutdown()


def test_profile_queue_runs_sequentially_without_switching_the_editor(monkeypatch, tmp_path):
    first = tmp_path / "First.kca.json"
    second = tmp_path / "Second.kca.json"
    save_profile(first, [Action("key", value="a")], RunSettings(start_delay=0))
    save_profile(second, [Action("key", value="b")], RunSettings(start_delay=0))
    started: list[list[str]] = []

    class RecordingRunner:
        def __init__(self, _backend):
            pass

        def run(
            self,
            actions,
            _settings,
            _stop_event,
            progress,
            _pause_event=None,
            _reserved_shortcuts=None,
        ):
            started.append([action.value for action in actions])
            progress("running", 1, 1)
            progress("action", 0, len(actions))
            return True

    monkeypatch.setattr(controller_running, "AutomationRunner", RecordingRunner)
    controller = AutomatorController(start_hotkeys=False, profile_directory=tmp_path)
    controller.addAction({"kind": "key", "value": "x"})
    editor_values = [action.value for action in controller.actions]
    assert controller.enqueueProfile(str(first)) is True
    assert controller.enqueueProfile(str(second)) is True

    assert controller.startRunQueue() is True
    for _ in range(100):
        if not controller.runQueueRunning:
            break
        QTest.qWait(10)

    assert started == [["a"], ["b"]]
    assert [entry["state"] for entry in controller.runQueueEntries] == [
        "complete",
        "complete",
    ]
    assert controller.status == "Queue complete"
    assert controller.running is False
    assert [action.value for action in controller.actions] == editor_values
    controller.shutdown()


def test_profile_queue_stops_remaining_profiles_after_an_error(monkeypatch, tmp_path):
    first = tmp_path / "First.kca.json"
    second = tmp_path / "Second.kca.json"
    save_profile(first, [Action("key", value="a")], RunSettings(start_delay=0))
    save_profile(second, [Action("key", value="b")], RunSettings(start_delay=0))

    class FailingRunner:
        def __init__(self, _backend):
            pass

        def run(
            self,
            _actions,
            _settings,
            _stop_event,
            _progress,
            _pause_event=None,
            _reserved_shortcuts=None,
        ):
            raise RuntimeError("target stopped responding")

    monkeypatch.setattr(controller_running, "AutomationRunner", FailingRunner)
    controller = AutomatorController(start_hotkeys=False, profile_directory=tmp_path)
    controller.enqueueProfile(str(first))
    controller.enqueueProfile(str(second))

    assert controller.startRunQueue() is True
    for _ in range(100):
        if not controller.runQueueRunning:
            break
        QTest.qWait(10)

    assert [entry["state"] for entry in controller.runQueueEntries] == [
        "error",
        "cancelled",
    ]
    assert "target stopped responding" in controller.runQueueEntries[0]["error"]
    assert controller.status == "Queue error"
    controller.shutdown()


def test_stop_all_stops_the_active_profile_and_cancels_waiting_profiles(
    monkeypatch,
    tmp_path,
):
    first = tmp_path / "First.kca.json"
    second = tmp_path / "Second.kca.json"
    save_profile(first, [Action("key", value="a")], RunSettings(start_delay=0))
    save_profile(second, [Action("key", value="b")], RunSettings(start_delay=0))
    worker_started = threading.Event()

    class BlockingRunner:
        def __init__(self, _backend):
            pass

        def run(
            self,
            _actions,
            _settings,
            stop_event,
            _progress,
            _pause_event=None,
            _reserved_shortcuts=None,
        ):
            worker_started.set()
            stop_event.wait(1)
            return False

    monkeypatch.setattr(controller_running, "AutomationRunner", BlockingRunner)
    controller = AutomatorController(start_hotkeys=False, profile_directory=tmp_path)
    controller.enqueueProfile(str(first))
    controller.enqueueProfile(str(second))

    assert controller.startRunQueue() is True
    assert worker_started.wait(1)
    controller.stopAllRuns()
    for _ in range(100):
        if not controller.runQueueRunning:
            break
        QTest.qWait(10)

    assert [entry["state"] for entry in controller.runQueueEntries] == [
        "stopped",
        "cancelled",
    ]
    assert controller.status == "Queue stopped"
    assert controller.running is False
    controller.shutdown()


def test_stop_all_during_a_sequential_handoff_finishes_as_stopped(tmp_path):
    first = tmp_path / "First.kca.json"
    second = tmp_path / "Second.kca.json"
    save_profile(first, [Action("key", value="a")], RunSettings(start_delay=0))
    save_profile(second, [Action("key", value="b")], RunSettings(start_delay=0))
    controller = AutomatorController(start_hotkeys=False, profile_directory=tmp_path)
    controller.enqueueProfile(str(first))
    controller.enqueueProfile(str(second))
    controller._run_queue[0].state = "complete"
    controller._run_queue[1].state = "cancelled"
    controller._queue_active = True
    controller._queue_stop_requested = True
    controller._set_running(True)

    assert controller._start_next_queued_session() is True
    assert controller.runQueueRunning is False
    assert controller.running is False
    assert controller.status == "Queue stopped"
    controller.shutdown()


def test_stopping_one_sequential_profile_continues_with_the_next(monkeypatch, tmp_path):
    first = tmp_path / "First.kca.json"
    second = tmp_path / "Second.kca.json"
    save_profile(first, [Action("key", value="a")], RunSettings(start_delay=0))
    save_profile(second, [Action("key", value="b")], RunSettings(start_delay=0))
    first_started = threading.Event()
    started: list[str] = []

    class SkippableRunner:
        def __init__(self, _backend):
            pass

        def run(
            self,
            actions,
            _settings,
            stop_event,
            _progress,
            _pause_event=None,
            _reserved_shortcuts=None,
        ):
            started.append(actions[0].value)
            if actions[0].value == "a":
                first_started.set()
                stop_event.wait(1)
                return False
            return True

    monkeypatch.setattr(controller_running, "AutomationRunner", SkippableRunner)
    controller = AutomatorController(start_hotkeys=False, profile_directory=tmp_path)
    controller.enqueueProfile(str(first))
    controller.enqueueProfile(str(second))
    assert controller.startRunQueue() is True
    assert first_started.wait(1)

    assert controller.stopRunSession(controller.runQueueEntries[0]["id"]) is True
    for _ in range(100):
        if not controller.runQueueRunning:
            break
        QTest.qWait(10)

    assert started == ["a", "b"]
    assert [entry["state"] for entry in controller.runQueueEntries] == [
        "stopped",
        "complete",
    ]
    assert controller.status == "Queue complete · 1 stopped"
    controller.shutdown()


def test_indefinite_profile_must_be_last_in_a_sequential_queue(tmp_path):
    endless = tmp_path / "Endless.kca.json"
    next_profile = tmp_path / "Next.kca.json"
    save_profile(
        endless,
        [Action("key", value="a")],
        RunSettings(repeat_forever=True, start_delay=0),
    )
    save_profile(
        next_profile,
        [Action("key", value="b")],
        RunSettings(start_delay=0),
    )
    controller = AutomatorController(start_hotkeys=False, profile_directory=tmp_path)
    controller.enqueueProfile(str(endless))
    controller.enqueueProfile(str(next_profile))

    assert controller.startRunQueue() is False
    assert controller.runQueueEntries[0]["state"] == "error"
    # The message has to name a way out, not just state the rule.
    error = controller.runQueueEntries[0]["error"]
    assert "repeats forever" in error
    assert "end of the queue" in error and "Parallel" in error
    assert controller.running is False
    controller.shutdown()


def _background_settings(title: str, hwnd: int) -> RunSettings:
    return RunSettings(
        target_mode="window",
        target_window_title=title,
        target_window_class="TargetWindow",
        target_executable=rf"C:\\Apps\\target-{hwnd}.exe",
        start_delay=0,
    )


def test_parallel_queue_starts_distinct_background_targets_together(monkeypatch, tmp_path):
    first = tmp_path / "Window A.kca.json"
    second = tmp_path / "Window B.kca.json"
    save_profile(first, [Action("key", value="a")], _background_settings("Window A", 101))
    save_profile(second, [Action("key", value="b")], _background_settings("Window B", 202))
    service = MultiWindowService()
    release = threading.Event()
    both_started = threading.Event()
    started: list[int] = []
    lock = threading.Lock()

    class ParallelRunner:
        def __init__(self, backend):
            self.hwnd = backend.root_hwnd

        def run(
            self,
            _actions,
            _settings,
            stop_event,
            _progress,
            _pause_event=None,
            reserved_shortcuts=None,
        ):
            assert "f9" in reserved_shortcuts
            with lock:
                started.append(self.hwnd)
                if len(started) == 2:
                    both_started.set()
            while not release.is_set():
                if stop_event.wait(0.01):
                    return False
            return True

    monkeypatch.setattr(controller_running, "AutomationRunner", ParallelRunner)
    controller = AutomatorController(
        start_hotkeys=False,
        profile_directory=tmp_path,
        window_service=service,
    )
    controller.enqueueProfile(str(first))
    controller.enqueueProfile(str(second))
    assert controller.setRunQueueMode("parallel") is True

    assert controller.startRunQueue() is True
    assert both_started.wait(1)
    assert set(started) == {101, 202}
    assert controller.running is True

    release.set()
    for _ in range(100):
        if not controller.runQueueRunning:
            break
        QTest.qWait(10)

    assert [entry["state"] for entry in controller.runQueueEntries] == [
        "complete",
        "complete",
    ]
    assert controller.status == "Parallel run complete"
    assert controller.running is False
    assert {101, 202}.issubset(set(service.responsive_checks))
    controller.shutdown()


def test_parallel_queue_rejects_desktop_and_duplicate_window_targets(tmp_path):
    desktop = tmp_path / "Desktop.kca.json"
    window_a = tmp_path / "Window A.kca.json"
    window_b = tmp_path / "Window B.kca.json"
    save_profile(desktop, [Action("key", value="a")], RunSettings(start_delay=0))
    save_profile(window_a, [Action("key", value="b")], _background_settings("Window A", 101))
    save_profile(window_b, [Action("key", value="c")], _background_settings("Window B", 202))

    controller = AutomatorController(
        start_hotkeys=False,
        profile_directory=tmp_path,
        window_service=MultiWindowService(),
    )
    controller.enqueueProfile(str(desktop))
    controller.enqueueProfile(str(window_a))
    controller.setRunQueueMode("parallel")
    assert controller.startRunQueue() is False
    assert "background-window and browser-tab profiles only" in controller.runQueueEntries[0]["error"]
    controller.clearRunQueue()
    controller.enqueueProfile(str(window_a))
    controller.enqueueProfile(str(window_b))
    controller._window_service = MultiWindowService(
        {"Window A": 101, "Window B": 101}
    )

    assert controller.startRunQueue() is False
    assert all(
        entry["state"] == "error" for entry in controller.runQueueEntries
    )
    assert "same target window" in controller.runQueueEntries[0]["error"]
    controller.shutdown()


def test_parallel_queue_rejects_actions_that_use_f9_stop_all(tmp_path):
    first = tmp_path / "Window A.kca.json"
    second = tmp_path / "Window B.kca.json"
    settings_a = _background_settings("Window A", 101)
    settings_a.start_hotkey = "f10"
    settings_a.capture_hotkey = "f11"
    settings_a.stop_hotkey = "f12"
    save_profile(first, [Action("key", value="f9")], settings_a)
    save_profile(second, [Action("key", value="b")], _background_settings("Window B", 202))
    controller = AutomatorController(
        start_hotkeys=False,
        profile_directory=tmp_path,
        window_service=MultiWindowService(),
    )
    controller.enqueueProfile(str(first))
    controller.enqueueProfile(str(second))
    controller.setRunQueueMode("parallel")

    assert controller.startRunQueue() is False
    assert "reserved by the app's global controls" in controller.runQueueEntries[0]["error"]
    controller.shutdown()


def test_parallel_profile_can_be_paused_resumed_and_stopped_independently(
    monkeypatch,
    tmp_path,
):
    first = tmp_path / "Window A.kca.json"
    second = tmp_path / "Window B.kca.json"
    save_profile(first, [Action("key", value="a")], _background_settings("Window A", 101))
    save_profile(second, [Action("key", value="b")], _background_settings("Window B", 202))
    release_second = threading.Event()
    both_started = threading.Event()
    started = 0
    lock = threading.Lock()

    class BlockingParallelRunner:
        def __init__(self, backend):
            self.hwnd = backend.root_hwnd

        def run(
            self,
            _actions,
            _settings,
            stop_event,
            _progress,
            _pause_event=None,
            _reserved_shortcuts=None,
        ):
            nonlocal started
            with lock:
                started += 1
                if started == 2:
                    both_started.set()
            while True:
                if stop_event.wait(0.01):
                    return False
                if self.hwnd == 202 and release_second.is_set():
                    return True

    monkeypatch.setattr(controller_running, "AutomationRunner", BlockingParallelRunner)
    controller = AutomatorController(
        start_hotkeys=False,
        profile_directory=tmp_path,
        window_service=MultiWindowService(),
    )
    controller.enqueueProfile(str(first))
    controller.enqueueProfile(str(second))
    controller.setRunQueueMode("parallel")
    assert controller.startRunQueue() is True
    assert both_started.wait(1)
    first_id = controller.runQueueEntries[0]["id"]

    assert controller.toggleRunSessionPaused(first_id) is True
    assert controller.runQueueEntries[0]["state"] == "paused"
    assert controller.runQueueEntries[0]["paused"] is True
    assert controller.toggleRunSessionPaused(first_id) is True
    assert controller.runQueueEntries[0]["paused"] is False
    assert controller.stopRunSession(first_id) is True

    for _ in range(100):
        if controller.runQueueEntries[0]["state"] == "stopped":
            break
        QTest.qWait(10)
    assert controller.runQueueEntries[0]["state"] == "stopped"
    assert controller.runQueueRunning is True

    release_second.set()
    for _ in range(100):
        if not controller.runQueueRunning:
            break
        QTest.qWait(10)
    assert [entry["state"] for entry in controller.runQueueEntries] == [
        "stopped",
        "complete",
    ]
    assert controller.status == "Parallel run complete · 1 stopped"
    controller.shutdown()


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


def test_deleting_a_profile_removes_the_file_and_dequeues_it(tmp_path):
    keep = tmp_path / "Keep.kca.json"
    doomed = tmp_path / "Doomed.kca.json"
    save_profile(keep, [Action("key", value="a")], RunSettings(start_delay=0))
    save_profile(doomed, [Action("key", value="b")], RunSettings(start_delay=0))

    controller = AutomatorController(start_hotkeys=False, profile_directory=tmp_path)
    assert controller.enqueueProfile(str(doomed)) is True
    assert controller.enqueueProfile(str(keep)) is True

    assert controller.deleteProfilePath(str(doomed)) is True

    assert doomed.exists() is False
    assert keep.exists() is True
    # A queued entry must not be left pointing at a file that no longer exists.
    assert controller.runQueuePaths == [str(keep.resolve())]
    assert [entry["name"] for entry in controller.profileEntries] == ["Keep"]
    controller.shutdown()


def test_deleting_the_open_profile_keeps_the_sequence_on_screen(tmp_path):
    path = tmp_path / "Open.kca.json"
    save_profile(path, [Action("key", value="a")], RunSettings(start_delay=0))
    controller = AutomatorController(start_hotkeys=False, profile_directory=tmp_path)
    assert controller.openProfilePath(str(path)) is True
    assert controller.currentProfileName == "Open"

    assert controller.deleteProfilePath(str(path)) is True

    # The work stays in the editor; it just stops being a saved profile.
    assert [action.value for action in controller.actions] == ["a"]
    assert controller.currentProfilePath == ""
    assert controller.currentProfileName == "Untitled sequence"
    assert controller.dirty is True
    controller.shutdown()


def test_a_profile_cannot_be_deleted_while_a_run_is_active(tmp_path):
    path = tmp_path / "Busy.kca.json"
    save_profile(path, [Action("key", value="a")], RunSettings(start_delay=0))
    controller = AutomatorController(start_hotkeys=False, profile_directory=tmp_path)
    controller._set_running(True)

    assert controller.deleteProfilePath(str(path)) is False
    assert path.exists() is True
    controller.shutdown()


def test_all_accepted_named_global_keys_are_formatted_for_pynput():
    for value in ("caps_lock", "insert", "menu", "num_lock", "pause", "scroll_lock", "alt_gr"):
        keyboard.HotKey.parse(AutomatorController._pynput_hotkey(value))


def test_single_run_still_reports_progress_while_parallel_mode_is_selected(monkeypatch, tmp_path):
    """The queue mode preference outlives an idle app and must not mute a single run."""

    class RecordingRunner:
        def __init__(self, _backend):
            pass

        def run(
            self,
            actions,
            _settings,
            _stop_event,
            progress,
            _pause_event=None,
            _reserved_shortcuts=None,
        ):
            progress("timer", 0, 1)
            progress("action", 0, len(actions))
            progress("running", 1, 1)
            return True

    monkeypatch.setattr(controller_running, "AutomationRunner", RecordingRunner)
    controller = AutomatorController(start_hotkeys=False, profile_directory=tmp_path)
    controller.addAction({"kind": "key", "value": "x"})
    assert controller.setRunQueueMode("parallel") is True

    # Sample every status change: polling races a worker that finishes in one pass.
    statuses: list[str] = []
    controller.statusChanged.connect(lambda: statuses.append(controller.status))

    controller.startRun()
    for _ in range(100):
        if not controller.running:
            break
        QTest.qWait(10)

    assert any("step 1" in status for status in statuses), statuses
    assert controller.runQueueRunning is False
    assert controller.status == "Complete"
    assert controller.progress == 1.0


def test_queue_hotkeys_keep_the_custom_stop_and_always_add_f9(monkeypatch):
    listeners = []

    class GlobalListener:
        def __init__(self, mapping):
            self.mapping = mapping

        def start(self):
            listeners.append(self)

        def stop(self):
            pass

    monkeypatch.setattr(qt_controller.keyboard, "GlobalHotKeys", GlobalListener)
    controller = AutomatorController(start_hotkeys=False)
    settings = RunSettings(
        start_hotkey="f5",
        capture_hotkey="f7",
        stop_hotkey="f10",
    )

    assert controller._install_hotkeys(settings, queue_stop=True) is True
    assert {"<f5>", "<f7>", "<f9>", "<f10>"}.issubset(
        listeners[-1].mapping
    )
    assert listeners[-1].mapping["<f9>"] == controller.queueStop
    assert listeners[-1].mapping["<f10>"] == controller.queueStop
    controller.shutdown()


def test_editing_disabled_action_preserves_disabled_state():
    controller = AutomatorController(start_hotkeys=False)
    controller.addAction({"kind": "key", "value": "a", "enabled": False})
    controller.updateAction(0, {"kind": "key", "value": "b", "enabled": True})
    assert controller.actions[0].value == "b"
    assert controller.actions[0].enabled is False
    controller.shutdown()


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


def test_open_profile_exposes_sequence_name_and_new_sequence_resets_it(monkeypatch, tmp_path):
    path = tmp_path / "Morning routine.kca.json"
    save_profile(path, [Action("key", value="a")], RunSettings())
    monkeypatch.setattr(qt_controller.QFileDialog, "getOpenFileName", lambda *args: (str(path), ""))

    controller = AutomatorController(start_hotkeys=False)
    assert controller.currentProfileName == "Untitled sequence"
    controller.openProfile()
    assert controller.currentProfileName == "Morning routine"
    controller.clearActions()
    assert controller.currentProfileName == "Untitled sequence"
    controller.shutdown()


def test_profile_library_discovers_profiles_and_marks_corrupt_keyclick_files(tmp_path):
    first = tmp_path / "Morning routine.kca.json"
    second = tmp_path / "Night.json"
    corrupt = tmp_path / "Broken.kca.json"
    unrelated = tmp_path / "settings.json"
    save_profile(
        first,
        [Action("key", value="a"), Action("text", value="hello", enabled=False)],
        RunSettings(),
    )
    save_profile(second, [Action("key", value="b")], RunSettings())
    corrupt.write_text("{not valid json", encoding="utf-8")
    unrelated.write_text('{"theme": "light"}', encoding="utf-8")

    controller = AutomatorController(
        start_hotkeys=False,
        profile_directory=tmp_path,
    )
    entries = {entry["name"]: entry for entry in controller.profileEntries}

    assert set(entries) == {"Morning routine", "Night", "Broken"}
    assert entries["Morning routine"]["actionCount"] == 2
    assert entries["Morning routine"]["activeCount"] == 1
    assert entries["Morning routine"]["valid"] is True
    assert entries["Night"]["valid"] is True
    assert entries["Broken"]["valid"] is False
    assert entries["Broken"]["error"]
    assert "Today" in entries["Morning routine"]["modified"]
    controller.shutdown()


def test_profile_library_opens_a_selected_path_and_follows_its_folder(tmp_path):
    initial_folder = tmp_path / "initial"
    selected_folder = tmp_path / "selected"
    initial_folder.mkdir()
    selected_folder.mkdir()
    path = selected_folder / "Click loop.kca.json"
    save_profile(path, [Action("left_click", x=10, y=20)], RunSettings())

    controller = AutomatorController(
        start_hotkeys=False,
        profile_directory=initial_folder,
    )
    assert controller.openProfilePath(str(path)) is True

    assert controller.currentProfileName == "Click loop"
    assert controller.currentProfilePath == str(path.resolve())
    assert controller.profileDirectory == str(selected_folder.resolve())
    assert [entry["name"] for entry in controller.profileEntries] == ["Click loop"]
    assert controller.actions[0].kind == "left_click"
    controller.shutdown()


def test_save_profile_reuses_the_current_path_and_refreshes_the_library(monkeypatch, tmp_path):
    path = tmp_path / "Reusable.kca.json"
    monkeypatch.setattr(
        qt_controller.QFileDialog,
        "getSaveFileName",
        lambda *args: (str(path), ""),
    )
    controller = AutomatorController(
        start_hotkeys=False,
        profile_directory=tmp_path,
    )
    controller.addAction({"kind": "key", "value": "a"})

    assert controller.saveProfile() is True
    assert controller.currentProfilePath == str(path.resolve())
    assert [entry["name"] for entry in controller.profileEntries] == ["Reusable"]

    controller.addAction({"kind": "key", "value": "b"})
    monkeypatch.setattr(
        qt_controller.QFileDialog,
        "getSaveFileName",
        lambda *args: (_ for _ in ()).throw(AssertionError("Save dialog reopened")),
    )
    assert controller.saveProfile() is True
    actions, _settings = load_profile(path)
    assert [action.value for action in actions] == ["a", "b"]
    assert controller.dirty is False
    controller.shutdown()


def test_profile_folder_picker_refreshes_the_library(monkeypatch, tmp_path):
    first_folder = tmp_path / "first"
    second_folder = tmp_path / "second"
    first_folder.mkdir()
    second_folder.mkdir()
    save_profile(
        second_folder / "Second folder.kca.json",
        [Action("key", value="s")],
        RunSettings(),
    )
    monkeypatch.setattr(
        qt_controller.QFileDialog,
        "getExistingDirectory",
        lambda *args: str(second_folder),
    )
    controller = AutomatorController(
        start_hotkeys=False,
        profile_directory=first_folder,
    )

    assert controller.chooseProfileFolder() is True
    assert controller.profileDirectory == str(second_folder.resolve())
    assert [entry["name"] for entry in controller.profileEntries] == ["Second folder"]
    controller.shutdown()


def test_packaged_app_uses_the_executable_folder_as_its_profile_library(monkeypatch, tmp_path):
    executable = tmp_path / "KeyClickAutomator-Portable.exe"
    monkeypatch.setattr(profile_catalog.sys, "frozen", True, raising=False)
    monkeypatch.setattr(profile_catalog.sys, "executable", str(executable))

    controller = AutomatorController(start_hotkeys=False)

    assert controller.profileDirectory == str(tmp_path.resolve())
    controller.shutdown()


def test_visual_window_picker_lists_and_selects_an_open_window(monkeypatch):
    monkeypatch.setattr(pyautogui, "position", lambda: SimpleNamespace(x=700, y=420))
    controller = AutomatorController(start_hotkeys=False, window_service=FakeWindowService())

    assert controller.setTargetMode("window") is True
    assert controller.startWindowPick() is True
    assert controller.windowPickPending is False
    assert len(controller.windowEntries) == 1
    assert controller.windowEntries[0]["appName"] == "Target"
    assert controller.selectWindowTarget(controller.windowEntries[0]["handle"]) is True

    assert controller.targetSettings["mode"] == "window"
    assert controller.targetSettings["windowSelected"] is True
    assert controller.targetSettings["displayName"] == "Target App"
    controller.shutdown()


def test_background_position_recording_converts_to_selected_window_coordinates(monkeypatch):
    monkeypatch.setattr(pyautogui, "position", lambda: SimpleNamespace(x=321, y=654))
    controller = AutomatorController(start_hotkeys=False, window_service=FakeWindowService())
    controller.setTargetMode("window")
    controller.captureWindowTarget()
    captured = QSignalSpy(controller.positionCaptured)

    controller.capturePosition(0)

    assert captured.count() == 1
    assert captured.at(0) == [0, 221, 454, "window", 800, 600]
    controller.shutdown()


def test_run_blocks_mouse_positions_recorded_for_the_other_target(monkeypatch):
    monkeypatch.setattr(pyautogui, "position", lambda: SimpleNamespace(x=321, y=654))
    controller = AutomatorController(start_hotkeys=False, window_service=FakeWindowService())
    controller.addAction({"kind": "left_click", "x": 10, "y": 20, "coordinateSpace": "screen"})
    controller.setTargetMode("window")
    controller.captureWindowTarget()
    toasts = QSignalSpy(controller.toast)

    assert controller.startRunWithSettings({"startDelay": 0}) is False
    assert controller.running is False
    assert "different target" in toasts.at(toasts.count() - 1)[0]
    controller.shutdown()


class FakeTab:
    def __init__(self, target_id, title, url):
        self.target_id, self.title, self.url = target_id, title, url
        self.websocket_url = f"ws://127.0.0.1/{target_id}"

    @property
    def label(self):
        return self.title


def _fake_browser(monkeypatch, tabs, available=True):
    monkeypatch.setattr(controller_targeting, "browser_available", lambda port=0: available)
    monkeypatch.setattr(controller_targeting, "list_tabs", lambda port=0: tabs)

    def find(port=0, target_id="", url="", title=""):
        for tab in tabs:
            if url and tab.url == url:
                return tab
        raise ChromeTargetError("That tab is no longer open. Pick the browser tab again.")

    monkeypatch.setattr(controller_targeting, "find_tab", find)


def test_browser_tabs_are_listed_and_one_can_be_targeted(monkeypatch):
    tabs = [FakeTab("A", "Cookie Clicker", "https://example.com/cookie"),
            FakeTab("B", "Docs", "https://example.com/docs")]
    _fake_browser(monkeypatch, tabs)
    controller = AutomatorController(start_hotkeys=False)

    assert controller.refreshBrowserTabs() is True
    assert [tab["title"] for tab in controller.browserTabs] == ["Cookie Clicker", "Docs"]
    assert controller.browserReady is True

    assert controller.setTargetMode("browser") is True
    assert controller.selectBrowserTab("A") is True

    assert controller.targetSettings["tabSelected"] is True
    assert controller.targetSettings["tabName"] == "Cookie Clicker"
    # The address is what survives a browser restart, so it must be persisted.
    assert controller.runSettings["repeatForever"] in (True, False)
    assert controller._run_settings.target_tab_url == "https://example.com/cookie"
    controller.shutdown()


def test_a_browser_profile_round_trips_through_a_saved_file(monkeypatch, tmp_path):
    tabs = [FakeTab("A", "Cookie Clicker", "https://example.com/cookie")]
    _fake_browser(monkeypatch, tabs)
    controller = AutomatorController(start_hotkeys=False, profile_directory=tmp_path)
    controller.setTargetMode("browser")
    controller.selectBrowserTab("A")
    controller.addAction({"kind": "left_click", "x": 300, "y": 220,
                          "coordinateSpace": "viewport",
                          "referenceWidth": 1200, "referenceHeight": 800})

    path = tmp_path / "Browser.kca.json"
    save_profile(path, controller.actions, controller._run_settings)
    actions, settings = load_profile(path)

    assert settings.target_mode == "browser"
    assert settings.target_tab_url == "https://example.com/cookie"
    assert actions[0].coordinate_space == "viewport"
    assert (actions[0].reference_width, actions[0].reference_height) == (1200, 800)
    controller.shutdown()


def test_a_closed_browser_tab_is_reported_before_the_run_starts(monkeypatch):
    _fake_browser(monkeypatch, [FakeTab("A", "Cookie Clicker", "https://example.com/cookie")])
    controller = AutomatorController(start_hotkeys=False)
    controller.setTargetMode("browser")
    controller.selectBrowserTab("A")
    controller.addAction({"kind": "left_click", "x": 10, "y": 10, "coordinateSpace": "viewport"})

    # The tab goes away before Start is pressed.
    _fake_browser(monkeypatch, [])
    toast = QSignalSpy(controller.toast)
    controller.startRun()
    assert any("no longer open" in toast.at(i)[0] for i in range(toast.count()))
    assert controller.running is False
    controller.shutdown()


def test_a_desktop_recorded_click_is_refused_for_a_browser_target(monkeypatch):
    _fake_browser(monkeypatch, [FakeTab("A", "Cookie Clicker", "https://example.com/cookie")])
    controller = AutomatorController(start_hotkeys=False)
    controller.addAction({"kind": "left_click", "x": 900, "y": 500})  # screen space
    controller.setTargetMode("browser")
    controller.selectBrowserTab("A")

    toast = QSignalSpy(controller.toast)
    controller.startRun()
    assert controller.running is False
    assert any("browser tab" in toast.at(i)[0] for i in range(toast.count()))
    controller.shutdown()


class ChromeWindowService(FakeWindowService):
    def __init__(self):
        super().__init__()
        self.info = WindowInfo(
            hwnd=777,
            title="Cookie Clicker - Google Chrome",
            class_name="Chrome_WidgetWin_1",
            executable=r"C:\Chrome\chrome.exe",
            process_id=4242,
        )


def test_start_refuses_a_click_that_was_never_recorded(monkeypatch):
    controller = AutomatorController(start_hotkeys=False)
    # Exactly what the editor produced before the guard existed.
    controller.addAction({"kind": "left_click", "x": 0, "y": 0})
    toast = QSignalSpy(controller.toast)

    controller.startRun()

    assert controller.running is False
    messages = [toast.at(i)[0] for i in range(toast.count())]
    assert any("corner" in m for m in messages), messages
    controller.shutdown()


def test_start_refuses_window_mode_against_a_browser_window():
    """This combination runs flawlessly and delivers nothing."""
    controller = AutomatorController(
        start_hotkeys=False, window_service=ChromeWindowService()
    )
    controller.setTargetMode("window")
    controller._run_settings.target_window_title = "Cookie Clicker - Google Chrome"
    controller._run_settings.target_window_class = "Chrome_WidgetWin_1"
    controller._run_settings.target_executable = r"C:\Chrome\chrome.exe"
    controller.addAction({
        "kind": "left_click", "x": 300, "y": 200,
        "coordinateSpace": "window", "referenceWidth": 800, "referenceHeight": 600,
    })
    toast = QSignalSpy(controller.toast)

    controller.startRun()

    assert controller.running is False
    messages = [toast.at(i)[0] for i in range(toast.count())]
    assert any("Browser tab mode" in m for m in messages), messages
    controller.shutdown()


def test_preflight_reports_a_clean_desktop_sequence_as_runnable():
    controller = AutomatorController(start_hotkeys=False)
    controller.addAction({"kind": "key", "value": "a"})

    checks = {c["name"]: c for c in controller.preflightChecks}

    assert checks["Actions"]["status"] == "pass"
    assert checks["Positions"]["status"] == "pass"
    # Desktop always warns, because it drives the real pointer.
    assert checks["Delivery"]["status"] == "warn"
    assert not [c for c in checks.values() if c["status"] == "fail"]
    controller.shutdown()


class ReportBackend:
    def __init__(self, sent, confirmed, target=""):
        self.delivered_input = sent
        self._confirmed = confirmed
        self._target = target

    def confirmed_input(self):
        return self._confirmed

    def confirmed_target(self):
        return self._target


def test_the_completion_message_says_what_the_page_actually_received():
    report = AutomatorController._delivery_report

    # The failure that ran all afternoon looking like success.
    silent = report("Run complete", ReportBackend(sent=240, confirmed=0))
    assert "received none of them" in silent
    assert "recorded position" in silent

    assert report("Run complete", ReportBackend(sent=240, confirmed=240)) == (
        "Run complete · 240 confirmed"
    )
    # Naming the element proves it hit the thing you meant, not just the page.
    assert report("Run complete", ReportBackend(240, 240, "button#bigCookie")) == (
        "Run complete · 240 confirmed on button#bigCookie"
    )
    assert report("Run complete", ReportBackend(sent=240, confirmed=100)) == (
        "Run complete · 240 sent, 100 received by the page"
    )
    # Unverifiable is reported as sent-only, never as confirmed.
    assert report("Run complete", ReportBackend(sent=240, confirmed=None)) == (
        "Run complete · 240 sent"
    )
    # Desktop and window runs have no backend to ask.
    assert report("Run complete", None) == "Run complete"


def test_saving_over_a_profile_keeps_the_previous_version(tmp_path):
    """The accident that emptied two real profiles is now recoverable."""
    path = tmp_path / "Mine.kca.json"
    save_profile(path, [Action("key", value="a"), Action("key", value="b")],
                 RunSettings(start_delay=0))
    controller = AutomatorController(start_hotkeys=False, profile_directory=tmp_path)
    assert controller.openProfilePath(str(path)) is True

    controller.clearActions()
    controller.addAction({"kind": "key", "value": "z"})
    assert controller._save_profile_path(str(path)) is True

    history = controller.profileVersions(str(path))
    assert history and history[0]["actionCount"] == 2

    assert controller.restoreProfileVersion(str(path), history[0]["path"]) is True
    assert [action.value for action in controller.actions] == ["a", "b"]
    controller.shutdown()


def test_deleting_a_profile_keeps_a_recoverable_copy(tmp_path):
    path = tmp_path / "Doomed.kca.json"
    save_profile(path, [Action("key", value="a")], RunSettings(start_delay=0))
    controller = AutomatorController(start_hotkeys=False, profile_directory=tmp_path)

    assert controller.deleteProfilePath(str(path)) is True

    assert path.exists() is False
    assert controller.profileVersions(str(path))[0]["actionCount"] == 1
    controller.shutdown()


def test_a_version_cannot_be_restored_while_a_run_is_active(tmp_path):
    path = tmp_path / "Busy.kca.json"
    save_profile(path, [Action("key", value="a")], RunSettings(start_delay=0))
    controller = AutomatorController(start_hotkeys=False, profile_directory=tmp_path)
    controller._save_profile_path(str(path))
    version = controller.profileVersions(str(path))[0]["path"]
    controller._set_running(True)

    assert controller.restoreProfileVersion(str(path), version) is False
    controller.shutdown()


def test_saved_versions_never_appear_in_the_profile_library(tmp_path):
    path = tmp_path / "Mine.kca.json"
    save_profile(path, [Action("key", value="a")], RunSettings(start_delay=0))
    controller = AutomatorController(start_hotkeys=False, profile_directory=tmp_path)
    controller._save_profile_path(str(path))
    controller._save_profile_path(str(path))

    assert [entry["name"] for entry in controller.profileEntries] == ["Mine"]
    controller.shutdown()


class BrowserWindowService(FakeWindowService):
    """A desktop with one ordinary app and one browser window open."""

    def list_windows(self, excluded_process_id=0):
        return [
            WindowInfo(101, "Untitled - Notepad", "Notepad", r"C:\W\notepad.exe", 11),
            WindowInfo(202, "Cookie Clicker - Google Chrome", "Chrome_WidgetWin_1",
                       r"C:\Chrome\chrome.exe", 22),
        ]

    def resolve_window(self, selector, preferred_hwnd=0):
        for info in self.list_windows():
            if info.title == selector.title:
                return info
        raise WindowTargetError("The target window is not open.")


def test_one_list_offers_the_desktop_windows_and_tabs_together(monkeypatch):
    _fake_browser(monkeypatch, [FakeTab("T1", "Cookie Clicker", "https://example.com/cookie")])
    controller = AutomatorController(start_hotkeys=False, window_service=BrowserWindowService())

    controller.refreshAutomationTargets()
    targets = controller.automationTargets

    assert targets[0]["kind"] == "desktop"
    kinds = {t["kind"] for t in targets}
    assert kinds == {"desktop", "browser", "window"}
    assert any(t["title"] == "Cookie Clicker" and t["kind"] == "browser" for t in targets)
    controller.shutdown()


def test_a_browser_window_is_listed_but_tells_you_to_use_its_tab(monkeypatch):
    """The pairing that ran perfectly and delivered nothing all session."""
    _fake_browser(monkeypatch, [])
    controller = AutomatorController(start_hotkeys=False, window_service=BrowserWindowService())
    controller.refreshAutomationTargets()

    chrome = next(t for t in controller.automationTargets
                  if t["kind"] == "window" and "Chrome" in t["title"])
    notepad = next(t for t in controller.automationTargets
                   if t["kind"] == "window" and "Notepad" in t["title"])

    assert "tab instead" in chrome["advice"]
    assert notepad["advice"] == ""
    controller.shutdown()


def test_choosing_a_target_also_chooses_how_to_reach_it(monkeypatch):
    _fake_browser(monkeypatch, [FakeTab("T1", "Cookie Clicker", "https://example.com/cookie")])
    controller = AutomatorController(start_hotkeys=False, window_service=BrowserWindowService())
    controller.refreshAutomationTargets()

    # A tab implies browser delivery; the user never picks a mechanism.
    assert controller.selectAutomationTarget("browser", "T1") is True
    assert controller.targetSettings["mode"] == "browser"
    assert controller.targetSummary == "Cookie Clicker"

    assert controller.selectAutomationTarget("window", "101") is True
    assert controller.targetSettings["mode"] == "window"

    assert controller.selectAutomationTarget("desktop", "desktop") is True
    assert controller.targetSettings["mode"] == "desktop"
    assert controller.targetSummary == "This computer"
    controller.shutdown()


def test_the_target_cannot_be_changed_mid_run(monkeypatch):
    _fake_browser(monkeypatch, [])
    controller = AutomatorController(start_hotkeys=False, window_service=BrowserWindowService())
    controller._set_running(True)

    assert controller.selectAutomationTarget("desktop", "desktop") is False
    controller.shutdown()

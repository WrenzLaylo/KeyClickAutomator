"""The multi-profile queue: order, sequential handoff, parallel sessions, stopping."""

import threading

from PySide6.QtTest import QSignalSpy
from PySide6.QtTest import QTest

from engine import Action
from engine import RunSettings
from engine import save_profile
from qt_controller import AutomatorController
import controller_running
import qt_controller

from controller_fakes import MultiWindowService, background_settings


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

def test_parallel_queue_starts_distinct_background_targets_together(monkeypatch, tmp_path):
    first = tmp_path / "Window A.kca.json"
    second = tmp_path / "Window B.kca.json"
    save_profile(first, [Action("key", value="a")], background_settings("Window A", 101))
    save_profile(second, [Action("key", value="b")], background_settings("Window B", 202))
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
    save_profile(window_a, [Action("key", value="b")], background_settings("Window A", 101))
    save_profile(window_b, [Action("key", value="c")], background_settings("Window B", 202))

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
    settings_a = background_settings("Window A", 101)
    settings_a.start_hotkey = "f10"
    settings_a.capture_hotkey = "f11"
    settings_a.stop_hotkey = "f12"
    save_profile(first, [Action("key", value="f9")], settings_a)
    save_profile(second, [Action("key", value="b")], background_settings("Window B", 202))
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
    save_profile(first, [Action("key", value="a")], background_settings("Window A", 101))
    save_profile(second, [Action("key", value="b")], background_settings("Window B", 202))
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

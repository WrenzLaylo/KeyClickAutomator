"""Running the open sequence, and what the run reports when it finishes."""

from PySide6.QtTest import QSignalSpy
from PySide6.QtTest import QTest

from engine import RunSettings
from qt_controller import AutomatorController
from run_session import RunSession
import controller_running

from controller_fakes import ReportBackend


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

"""Choosing what to automate: windows, browser tabs, and the one picker over both."""

from types import SimpleNamespace

from PySide6.QtTest import QSignalSpy
import pyautogui

from engine import load_profile
from engine import save_profile
from qt_controller import AutomatorController

from controller_fakes import FakeWindowService, FakeTab, fake_browser, ChromeWindowService, BrowserWindowService


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

def test_browser_tabs_are_listed_and_one_can_be_targeted(monkeypatch):
    tabs = [FakeTab("A", "Cookie Clicker", "https://example.com/cookie"),
            FakeTab("B", "Docs", "https://example.com/docs")]
    fake_browser(monkeypatch, tabs)
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
    fake_browser(monkeypatch, tabs)
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
    fake_browser(monkeypatch, [FakeTab("A", "Cookie Clicker", "https://example.com/cookie")])
    controller = AutomatorController(start_hotkeys=False)
    controller.setTargetMode("browser")
    controller.selectBrowserTab("A")
    controller.addAction({"kind": "left_click", "x": 10, "y": 10, "coordinateSpace": "viewport"})

    # The tab goes away before Start is pressed.
    fake_browser(monkeypatch, [])
    toast = QSignalSpy(controller.toast)
    controller.startRun()
    assert any("no longer open" in toast.at(i)[0] for i in range(toast.count()))
    assert controller.running is False
    controller.shutdown()

def test_a_desktop_recorded_click_is_refused_for_a_browser_target(monkeypatch):
    fake_browser(monkeypatch, [FakeTab("A", "Cookie Clicker", "https://example.com/cookie")])
    controller = AutomatorController(start_hotkeys=False)
    controller.addAction({"kind": "left_click", "x": 900, "y": 500})  # screen space
    controller.setTargetMode("browser")
    controller.selectBrowserTab("A")

    toast = QSignalSpy(controller.toast)
    controller.startRun()
    assert controller.running is False
    assert any("browser tab" in toast.at(i)[0] for i in range(toast.count()))
    controller.shutdown()

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

def test_one_list_offers_the_desktop_windows_and_tabs_together(monkeypatch):
    fake_browser(monkeypatch, [FakeTab("T1", "Cookie Clicker", "https://example.com/cookie")])
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
    fake_browser(monkeypatch, [])
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
    fake_browser(monkeypatch, [FakeTab("T1", "Cookie Clicker", "https://example.com/cookie")])
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
    fake_browser(monkeypatch, [])
    controller = AutomatorController(start_hotkeys=False, window_service=BrowserWindowService())
    controller._set_running(True)

    assert controller.selectAutomationTarget("desktop", "desktop") is False
    controller.shutdown()

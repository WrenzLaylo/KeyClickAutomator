from types import SimpleNamespace

from engine import Action, RunSettings
from preflight import (
    FAIL,
    PASS,
    WARN,
    blocking_failures,
    looks_like_a_browser,
    preflight,
    summarize,
)


def named(checks, name):
    return next(check for check in checks if check.name == name)


def desktop_settings(**kwargs):
    return RunSettings(start_delay=0, **kwargs)


def window_settings(**kwargs):
    base = dict(target_mode="window", target_window_title="Notepad",
                target_window_class="Notepad", target_executable=r"C:\W\notepad.exe")
    base.update(kwargs)
    return RunSettings(start_delay=0, **base)


def browser_settings(**kwargs):
    base = dict(target_mode="browser", target_tab_url="https://example.com/game",
                target_tab_title="Game")
    base.update(kwargs)
    return RunSettings(start_delay=0, **base)


def test_an_unrecorded_click_is_reported_as_a_blocking_failure():
    # The editor defaults X/Y to 0, so this is what a never-recorded click becomes.
    actions = [Action("left_click", x=0, y=0)]

    checks = preflight(actions, desktop_settings())

    positions = named(checks, "Positions")
    assert positions.status == FAIL
    assert "corner" in positions.detail
    assert "Pick pointer position" in positions.remedy
    assert blocking_failures(checks)


def test_a_genuine_zero_zero_recorded_against_a_window_is_allowed():
    # Recording stamps the window size, which distinguishes it from the default.
    actions = [Action("left_click", x=0, y=0, coordinate_space="window",
                      reference_width=800, reference_height=600)]

    checks = preflight(actions, window_settings())

    assert named(checks, "Positions").status == PASS


def test_a_follow_pointer_click_needs_no_position():
    actions = [Action("left_click", use_current_pointer=True)]

    assert named(preflight(actions, desktop_settings()), "Positions").status == PASS


def test_window_mode_against_a_browser_is_refused_with_the_real_reason():
    """The failure that silently wasted a real session: Chrome cannot receive them."""
    actions = [Action("left_click", x=10, y=10, coordinate_space="window",
                      reference_width=800, reference_height=600)]
    chrome = SimpleNamespace(title="Cookie Clicker - Google Chrome",
                             class_name="Chrome_WidgetWin_1",
                             executable=r"C:\Chrome\chrome.exe")

    checks = preflight(actions, window_settings(), resolve_window=lambda: chrome)

    delivery = named(checks, "Delivery")
    assert delivery.status == FAIL
    assert "compositor" in delivery.detail
    assert "Browser tab mode" in delivery.remedy


def test_a_normal_window_only_warns_about_message_compatibility():
    actions = [Action("left_click", x=10, y=10, coordinate_space="window",
                      reference_width=800, reference_height=600)]
    notepad = SimpleNamespace(title="Untitled - Notepad", class_name="Notepad",
                              executable=r"C:\W\notepad.exe")

    checks = preflight(actions, window_settings(), resolve_window=lambda: notepad)

    assert named(checks, "Delivery").status == WARN
    assert not blocking_failures(checks)


def test_a_missing_window_is_reported_against_the_target_not_the_actions():
    actions = [Action("left_click", x=10, y=10, coordinate_space="window",
                      reference_width=800, reference_height=600)]

    def gone():
        raise RuntimeError("The target window is not open. Open it, then try again.")

    checks = preflight(actions, window_settings(), resolve_window=gone)

    target = named(checks, "Target")
    assert target.status == FAIL and "not open" in target.detail


def test_a_desktop_recorded_click_is_refused_for_a_browser_target():
    actions = [Action("left_click", x=900, y=400)]  # screen space

    checks = preflight(actions, browser_settings(), resolve_tab=lambda: SimpleNamespace(title="Game"))

    space = named(checks, "Recorded for this target")
    assert space.status == FAIL
    assert "browser tab" in space.remedy


def test_a_browser_target_reports_that_the_pointer_stays_free():
    actions = [Action("left_click", x=300, y=200, coordinate_space="viewport",
                      reference_width=1200, reference_height=800)]

    checks = preflight(actions, browser_settings(), resolve_tab=lambda: SimpleNamespace(title="Game"))

    assert not blocking_failures(checks)
    assert named(checks, "Delivery").status == PASS
    assert summarize(checks) == "Ready"


def test_desktop_mode_warns_that_it_takes_over_the_real_pointer():
    actions = [Action("key", value="a")]

    checks = preflight(actions, desktop_settings())

    assert named(checks, "Delivery").status == WARN
    assert summarize(checks) == "Ready, with cautions"


def test_an_empty_sequence_fails_before_anything_else_is_considered():
    checks = preflight([], desktop_settings())

    assert named(checks, "Actions").status == FAIL
    assert summarize(checks) == "No enabled actions in this sequence."


def test_a_disabled_action_does_not_satisfy_the_actions_check():
    checks = preflight([Action("key", value="a", enabled=False)], desktop_settings())

    assert named(checks, "Actions").status == FAIL


def test_an_action_colliding_with_a_global_shortcut_is_caught():
    checks = preflight([Action("key", value="f9")], desktop_settings())

    shortcuts = named(checks, "Shortcuts")
    assert shortcuts.status == FAIL and "F9" in shortcuts.detail


def test_browser_windows_are_recognised_by_class_or_executable():
    assert looks_like_a_browser(window_class="Chrome_WidgetWin_1") is True
    assert looks_like_a_browser(executable=r"C:\P\firefox.exe") is True
    assert looks_like_a_browser(executable=r"C:\P\msedge.exe") is True
    assert looks_like_a_browser(window_class="Notepad", executable=r"C:\W\notepad.exe") is False

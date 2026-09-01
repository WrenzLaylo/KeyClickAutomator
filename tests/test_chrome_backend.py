import pytest

from chrome_backend import (
    ChromeTab,
    ChromeTabBackend,
    ChromeTargetError,
    find_tab,
    launch_chrome,
    profile_directory,
)


class FakeCdp:
    def __init__(self):
        self.calls = []
        self.closed = False

    def send(self, method, **params):
        self.calls.append((method, params))
        return {}

    def close(self):
        self.closed = True

    def of(self, method):
        return [params for name, params in self.calls if name == method]


TAB = ChromeTab("T1", "Cookie Clicker", "https://example.com/cookie", "ws://127.0.0.1:9222/x")


def make():
    cdp = FakeCdp()
    return cdp, ChromeTabBackend(TAB, connection=cdp, sleeper=lambda _s: None)


def test_a_click_lands_on_the_recorded_viewport_point():
    cdp, backend = make()

    backend.click(300, 220, button="left")

    events = cdp.of("Input.dispatchMouseEvent")
    assert [e["type"] for e in events] == ["mouseMoved", "mousePressed", "mouseReleased"]
    assert all(e["x"] == 300 and e["y"] == 220 for e in events)
    assert events[1]["button"] == "left" and events[1]["clickCount"] == 1


def test_a_follow_pointer_click_reuses_the_last_point_instead_of_jumping_to_zero():
    cdp, backend = make()
    backend.moveTo(80, 90)

    backend.click(None, None, button="right")

    pressed = [e for e in cdp.of("Input.dispatchMouseEvent") if e["type"] == "mousePressed"]
    assert pressed[0]["x"] == 80 and pressed[0]["y"] == 90
    assert pressed[0]["button"] == "right"


def test_double_click_reports_the_second_click_as_count_two():
    cdp, backend = make()

    backend.doubleClick(10, 10)

    counts = [e["clickCount"] for e in cdp.of("Input.dispatchMouseEvent") if e["type"] == "mousePressed"]
    assert counts == [1, 2]


def test_scroll_sends_one_standard_notch_per_step_and_up_is_positive():
    cdp, backend = make()

    backend.scroll(3)
    wheels = [e for e in cdp.of("Input.dispatchMouseEvent") if e["type"] == "mouseWheel"]
    assert len(wheels) == 3
    assert all(e["deltaY"] == -120 for e in wheels)

    cdp.calls.clear()
    backend.scroll(-2)
    wheels = [e for e in cdp.of("Input.dispatchMouseEvent") if e["type"] == "mouseWheel"]
    assert len(wheels) == 2 and all(e["deltaY"] == 120 for e in wheels)


def test_a_drag_presses_moves_then_always_releases():
    cdp, backend = make()
    backend.moveTo(0, 0)

    backend.dragTo(100, 50, duration=0.1)

    events = cdp.of("Input.dispatchMouseEvent")
    assert events[-1]["type"] == "mouseReleased"
    assert (events[-1]["x"], events[-1]["y"]) == (100, 50)
    moves = [e for e in events if e["type"] == "mouseMoved" and e["button"] == "left"]
    assert len(moves) > 1, "a timed drag should travel in steps"


def test_a_held_button_is_released_when_the_backend_closes():
    cdp, backend = make()
    backend.mouseDown("left")

    backend.close()

    assert cdp.of("Input.dispatchMouseEvent")[-1]["type"] == "mouseReleased"
    assert cdp.closed is True


def test_text_is_inserted_rather_than_synthesised_key_by_key():
    cdp, backend = make()

    backend.write("Hello, wörld")

    assert cdp.of("Input.insertText") == [{"text": "Hello, wörld"}]
    assert cdp.of("Input.dispatchKeyEvent") == []


def test_a_key_press_sends_down_then_up_with_its_virtual_key_code():
    cdp, backend = make()

    backend.press("enter")

    events = cdp.of("Input.dispatchKeyEvent")
    assert [e["type"] for e in events] == ["keyDown", "keyUp"]
    assert events[0]["windowsVirtualKeyCode"] == 13
    assert events[0]["key"] == "Enter"


def test_a_hotkey_holds_its_modifiers_and_releases_them_in_reverse():
    cdp, backend = make()

    backend.hotkey("ctrl", "shift", "s")

    events = cdp.of("Input.dispatchKeyEvent")
    order = [(e["type"], e["key"]) for e in events]
    assert order[0] == ("keyDown", "Control")
    assert order[1] == ("keyDown", "Shift")
    assert ("keyDown", "s") in order
    assert order[-1] == ("keyUp", "Control")
    # ctrl(2) | shift(8) must be set while the final key is delivered.
    final = next(e for e in events if e["key"] == "s" and e["type"] == "keyDown")
    assert final["modifiers"] == 10
    # A modified chord must not also insert a stray character.
    assert "text" not in final


def test_a_plain_letter_still_carries_its_character():
    cdp, backend = make()

    backend.press("a")

    down = cdp.of("Input.dispatchKeyEvent")[0]
    assert down["text"] == "a"


def test_an_unsupported_key_is_rejected_rather_than_silently_skipped():
    _cdp, backend = make()

    with pytest.raises(ChromeTargetError):
        backend.press("scroll_wheel_up")


def test_finding_a_tab_prefers_the_saved_target_then_falls_back_to_its_address(monkeypatch):
    import chrome_backend

    tabs = [
        ChromeTab("A", "Cookie Clicker", "https://example.com/cookie", "ws://a"),
        ChromeTab("B", "Docs", "https://example.com/docs", "ws://b"),
    ]
    monkeypatch.setattr(chrome_backend, "list_tabs", lambda port=0: tabs)

    assert find_tab(target_id="B").target_id == "B"
    # Target ids do not survive a browser restart, so the URL is the stable key.
    assert find_tab(target_id="gone", url="https://example.com/cookie").target_id == "A"


def test_duplicate_addresses_are_reported_instead_of_guessed(monkeypatch):
    import chrome_backend

    tabs = [
        ChromeTab("A", "Cookie Clicker", "https://example.com/c", "ws://a"),
        ChromeTab("B", "Cookie Clicker", "https://example.com/c", "ws://b"),
    ]
    monkeypatch.setattr(chrome_backend, "list_tabs", lambda port=0: tabs)

    with pytest.raises(ChromeTargetError) as excinfo:
        find_tab(url="https://example.com/c")
    assert "duplicates" in str(excinfo.value)


def test_chrome_is_launched_debuggable_in_its_own_persistent_profile(tmp_path):
    recorded = {}

    def fake_runner(command):
        recorded["command"] = command
        return "process"

    result = launch_chrome("chrome.exe", tmp_path, port=9333,
                           start_url="https://example.com", runner=fake_runner)

    assert result == "process"
    command = recorded["command"]
    assert "--remote-debugging-port=9333" in command
    # Chrome 136+ refuses remote debugging on the default profile, and a separate
    # profile also keeps automation away from the user's signed-in windows.
    assert f"--user-data-dir={profile_directory(tmp_path)}" in command
    assert command[-1] == "https://example.com"
    assert profile_directory(tmp_path).is_dir()


class ViewportCdp(FakeCdp):
    def __init__(self, width=1000, height=800, pick=None):
        super().__init__()
        self.size = {"w": width, "h": height}
        self.pick = pick

    def send(self, method, **params):
        super().send(method, **params)
        if method == "Runtime.evaluate":
            expr = params.get("expression", "")
            if "innerWidth" in expr and "__keyclick" not in expr:
                return {"result": {"value": dict(self.size)}}
            if expr == "window.__keyclickPick":
                return {"result": {"value": self.pick}}
        return {}


def test_a_recorded_point_follows_the_page_when_the_viewport_is_resized():
    cdp = ViewportCdp(width=1200, height=900)
    backend = ChromeTabBackend(TAB, connection=cdp, sleeper=lambda _s: None)

    # Recorded at 600x450, replayed in a viewport twice that size.
    assert backend.scale_point(300, 225, 600, 450) == (600, 450)


def test_a_point_recorded_without_a_reference_size_is_used_verbatim():
    cdp = ViewportCdp()
    backend = ChromeTabBackend(TAB, connection=cdp, sleeper=lambda _s: None)

    assert backend.scale_point(120, 80, 0, 0) == (120, 80)


def test_the_viewport_size_is_cached_instead_of_queried_per_click():
    clock = {"t": 0.0}
    cdp = ViewportCdp()
    backend = ChromeTabBackend(
        TAB, connection=cdp, clock=lambda: clock["t"], sleeper=lambda _s: None
    )

    for _ in range(5):
        backend.viewport_size()
    assert len(cdp.of("Runtime.evaluate")) == 1

    clock["t"] = 5.0
    backend.viewport_size()
    assert len(cdp.of("Runtime.evaluate")) == 2


def test_recording_reads_the_click_back_from_the_page_itself():
    cdp = ViewportCdp(pick={"x": 314, "y": 271, "w": 1280, "h": 720})
    backend = ChromeTabBackend(TAB, connection=cdp, sleeper=lambda _s: None)

    assert backend.capture_click_point(timeout=5) == (314, 271, 1280, 720)


def test_recording_gives_up_cleanly_and_unhooks_its_listener():
    clock = {"t": 0.0}

    def tick(_seconds):
        clock["t"] += 1.0

    cdp = ViewportCdp(pick=None)
    backend = ChromeTabBackend(
        TAB, connection=cdp, clock=lambda: clock["t"], sleeper=tick
    )

    assert backend.capture_click_point(timeout=3) is None
    assert any("removeEventListener" in p.get("expression", "")
               for p in cdp.of("Runtime.evaluate"))


def test_launch_disables_the_throttling_that_slows_a_hidden_tab(tmp_path):
    recorded = {}
    launch_chrome("chrome.exe", tmp_path, runner=lambda cmd: recorded.setdefault("c", cmd))

    command = recorded["c"]
    # Automating a tab you are not looking at is the whole point, and Chrome
    # throttles renderers in hidden or occluded windows by default.
    for flag in (
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
    ):
        assert flag in command

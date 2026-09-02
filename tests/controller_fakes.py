"""Stand-ins for the things a controller talks to: windows, tabs, backends.

Shared by the controller test modules so each one describes behaviour rather
than re-declaring a fake desktop."""

from chrome_backend import ChromeTargetError
from engine import RunSettings
from window_backend import WindowInfo
from window_backend import WindowTargetError
import controller_targeting


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

def background_settings(title: str, hwnd: int) -> RunSettings:
    return RunSettings(
        target_mode="window",
        target_window_title=title,
        target_window_class="TargetWindow",
        target_executable=rf"C:\\Apps\\target-{hwnd}.exe",
        start_delay=0,
    )

class FakeTab:
    def __init__(self, target_id, title, url):
        self.target_id, self.title, self.url = target_id, title, url
        self.websocket_url = f"ws://127.0.0.1/{target_id}"

    @property
    def label(self):
        return self.title

def fake_browser(monkeypatch, tabs, available=True):
    monkeypatch.setattr(controller_targeting, "browser_available", lambda port=0: available)
    monkeypatch.setattr(controller_targeting, "list_tabs", lambda port=0: tabs)

    def find(port=0, target_id="", url="", title=""):
        for tab in tabs:
            if url and tab.url == url:
                return tab
        raise ChromeTargetError("That tab is no longer open. Pick the browser tab again.")

    monkeypatch.setattr(controller_targeting, "find_tab", find)

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

class ReportBackend:
    def __init__(self, sent, confirmed, target=""):
        self.delivered_input = sent
        self._confirmed = confirmed
        self._target = target

    def confirmed_input(self):
        return self._confirmed

    def confirmed_target(self):
        return self._target

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

from window_backend import (
    BM_CLICK,
    MK_LBUTTON,
    VK_CONTROL,
    VK_MENU,
    WM_CHAR,
    WM_KEYDOWN,
    WM_KEYUP,
    WM_LBUTTONDOWN,
    WM_LBUTTONUP,
    WM_MOUSEMOVE,
    WM_MOUSEWHEEL,
    WM_SYSKEYDOWN,
    WM_SYSKEYUP,
    Win32WindowService,
    WindowInfo,
    WindowMessageBackend,
    WindowTargetError,
    _packed_point,
    _packed_wheel,
)


class FakeWindowService:
    def __init__(self):
        self.messages = []
        self.usable = []
        self.responsive = []
        self.button_control = False
        self.edit_control = False
        self.replaced_text = []

    def ensure_usable(self, hwnd):
        self.usable.append(hwnd)

    def ensure_responsive(self, hwnd):
        self.responsive.append(hwnd)

    def keyboard_target(self, root_hwnd):
        return 222

    def virtual_key(self, value):
        mapping = {
            "a": (65, ()),
            "s": (83, ()),
            "ctrl": (VK_CONTROL, ()),
            "alt": (VK_MENU, ()),
        }
        if value not in mapping:
            raise WindowTargetError("unsupported")
        return mapping[value]

    def scan_code(self, virtual_key):
        return virtual_key

    def post_message(self, hwnd, message, wparam, lparam):
        self.messages.append((hwnd, message, wparam, lparam))

    def is_button_control(self, hwnd):
        return self.button_control

    def is_edit_control(self, hwnd):
        return self.edit_control

    def replace_edit_text(self, hwnd, text):
        self.replaced_text.append((hwnd, text))

    def mouse_target(self, root_hwnd, x, y):
        return 333, x - 10, y - 20

    def map_root_point(self, root_hwnd, target_hwnd, x, y):
        return x - 10, y - 20

    def client_to_screen(self, hwnd, x, y):
        return x + 100, y + 200

    def client_size(self, hwnd):
        return 500, 300


def test_background_click_posts_to_the_window_without_moving_the_physical_pointer():
    service = FakeWindowService()
    backend = WindowMessageBackend(111, service, message_interval=0)

    backend.click(40, 70, button="left")

    point = _packed_point(30, 50)
    assert service.messages == [
        (333, WM_MOUSEMOVE, 0, point),
        (333, WM_LBUTTONDOWN, MK_LBUTTON, point),
        (333, WM_LBUTTONUP, 0, point),
    ]


def test_background_keyboard_and_text_are_addressed_to_the_window_queue():
    service = FakeWindowService()
    backend = WindowMessageBackend(111, service, message_interval=0)

    backend.hotkey("ctrl", "s")
    backend.write("A")

    assert [(message, key) for _, message, key, _ in service.messages] == [
        (WM_KEYDOWN, VK_CONTROL),
        (WM_KEYDOWN, 83),
        (WM_KEYUP, 83),
        (WM_KEYUP, VK_CONTROL),
        (WM_CHAR, ord("A")),
    ]
    assert all(hwnd == 222 for hwnd, *_ in service.messages)


def test_native_button_controls_use_their_background_safe_click_command():
    service = FakeWindowService()
    service.button_control = True
    backend = WindowMessageBackend(111, service, message_interval=0)

    backend.click(40, 70)

    assert service.messages == [(333, BM_CLICK, 0, 0)]


def test_native_edit_controls_use_background_safe_text_replacement():
    service = FakeWindowService()
    service.edit_control = True
    backend = WindowMessageBackend(111, service, message_interval=0)

    backend.write("hello")

    assert service.replaced_text == [(222, "hello")]
    assert service.messages == []


def test_alt_shortcuts_use_system_key_messages_with_context():
    service = FakeWindowService()
    backend = WindowMessageBackend(111, service, message_interval=0)

    backend.hotkey("alt", "a")

    assert [(message, key) for _, message, key, _ in service.messages] == [
        (WM_SYSKEYDOWN, VK_MENU),
        (WM_SYSKEYDOWN, 65),
        (WM_SYSKEYUP, 65),
        (WM_SYSKEYUP, VK_MENU),
    ]
    assert service.messages[1][3] & (1 << 29)


def test_background_scroll_uses_the_saved_window_position():
    service = FakeWindowService()
    backend = WindowMessageBackend(111, service, message_interval=0)
    backend.moveTo(40, 70)
    service.messages.clear()

    backend.scroll(-3)

    assert service.messages == [
        (333, WM_MOUSEMOVE, 0, _packed_point(30, 50)),
        (333, WM_MOUSEWHEEL, _packed_wheel(0, -120), _packed_point(140, 270)),
        (333, WM_MOUSEWHEEL, _packed_wheel(0, -120), _packed_point(140, 270)),
        (333, WM_MOUSEWHEEL, _packed_wheel(0, -120), _packed_point(140, 270)),
    ]


def test_background_click_rejects_follow_current_pointer():
    backend = WindowMessageBackend(111, FakeWindowService(), message_interval=0)

    try:
        backend.click(None, None)
    except WindowTargetError as exc:
        assert "Desktop mode" in str(exc)
    else:
        raise AssertionError("Expected a WindowTargetError")


def test_recorded_window_point_scales_to_the_current_client_size():
    service = FakeWindowService()
    backend = WindowMessageBackend(111, service, message_interval=0)

    assert backend.scale_point(500, 400, 1000, 800) == (250, 150)
    assert backend.scale_point(999, 799, 1000, 800) == (499, 299)
    assert backend.scale_point(40, 70, 0, 0) == (40, 70)


def test_background_messages_are_paced_to_avoid_flooding_the_target_queue():
    service = FakeWindowService()
    now = [10.0]
    waits = []

    def clock():
        return now[0]

    def sleep(seconds):
        waits.append(seconds)
        now[0] += seconds

    backend = WindowMessageBackend(
        111,
        service,
        message_interval=0.02,
        clock=clock,
        sleeper=sleep,
    )

    backend.click(40, 70)

    assert waits == [0.02, 0.02]
    assert service.responsive == [111]


def test_long_native_edit_text_is_split_into_bounded_messages():
    service = FakeWindowService()
    service.edit_control = True
    backend = WindowMessageBackend(111, service, message_interval=0)

    backend.write("x" * 600)

    assert [len(text) for _, text in service.replaced_text] == [256, 256, 88]


def test_unresponsive_target_is_rejected_before_any_input_is_posted():
    class UnresponsiveService(FakeWindowService):
        def ensure_responsive(self, hwnd):
            raise WindowTargetError("not responding")

    service = UnresponsiveService()

    try:
        WindowMessageBackend(111, service, message_interval=0)
    except WindowTargetError as exc:
        assert "not responding" in str(exc)
    else:
        raise AssertionError("Expected a WindowTargetError")

    assert service.messages == []


def _info(hwnd, title):
    return WindowInfo(hwnd, title, "Chrome_WidgetWin_1", r"C:\Chrome\chrome.exe", 9)


def test_drifting_window_title_still_resolves_to_the_same_window():
    """Cookie Clicker writes the live cookie count into its title bar."""
    saved = "6.862 billion cookies - Cookie Clicker - Google Chrome"
    candidates = [
        _info(101, "14.152 billion cookies - Cookie Clicker - Google Chrome"),
        _info(102, "Inbox (12) - Gmail - Google Chrome"),
        _info(103, "GitHub - Google Chrome"),
    ]

    chosen = Win32WindowService._closest_by_title(candidates, saved)

    assert chosen is not None and chosen.hwnd == 101


def test_two_equally_similar_windows_stay_ambiguous():
    saved = "Report - Notepad"
    candidates = [_info(201, "Report - Notepad"), _info(202, "Report - Notepad")]

    assert Win32WindowService._closest_by_title(candidates, saved) is None


def test_an_unrelated_window_is_not_claimed_as_the_target():
    saved = "6.862 billion cookies - Cookie Clicker - Google Chrome"
    candidates = [_info(301, "Gmail"), _info(302, "Docs")]

    assert Win32WindowService._closest_by_title(candidates, saved) is None

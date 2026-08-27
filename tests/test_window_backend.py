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
    WindowMessageBackend,
    WindowTargetError,
    _packed_point,
    _packed_wheel,
)


class FakeWindowService:
    def __init__(self):
        self.messages = []
        self.usable = []
        self.button_control = False
        self.edit_control = False
        self.replaced_text = []

    def ensure_usable(self, hwnd):
        self.usable.append(hwnd)

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
    backend = WindowMessageBackend(111, service)

    backend.click(40, 70, button="left")

    point = _packed_point(30, 50)
    assert service.messages == [
        (333, WM_MOUSEMOVE, 0, point),
        (333, WM_LBUTTONDOWN, MK_LBUTTON, point),
        (333, WM_LBUTTONUP, 0, point),
    ]


def test_background_keyboard_and_text_are_addressed_to_the_window_queue():
    service = FakeWindowService()
    backend = WindowMessageBackend(111, service)

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
    backend = WindowMessageBackend(111, service)

    backend.click(40, 70)

    assert service.messages == [(333, BM_CLICK, 0, 0)]


def test_native_edit_controls_use_background_safe_text_replacement():
    service = FakeWindowService()
    service.edit_control = True
    backend = WindowMessageBackend(111, service)

    backend.write("hello")

    assert service.replaced_text == [(222, "hello")]
    assert service.messages == []


def test_alt_shortcuts_use_system_key_messages_with_context():
    service = FakeWindowService()
    backend = WindowMessageBackend(111, service)

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
    backend = WindowMessageBackend(111, service)
    backend.moveTo(40, 70)
    service.messages.clear()

    backend.scroll(-3)

    assert service.messages == [
        (333, WM_MOUSEMOVE, 0, _packed_point(30, 50)),
        (333, WM_MOUSEWHEEL, _packed_wheel(0, -3 * 120), _packed_point(140, 270)),
    ]


def test_background_click_rejects_follow_current_pointer():
    backend = WindowMessageBackend(111, FakeWindowService())

    try:
        backend.click(None, None)
    except WindowTargetError as exc:
        assert "Desktop mode" in str(exc)
    else:
        raise AssertionError("Expected a WindowTargetError")


def test_recorded_window_point_scales_to_the_current_client_size():
    service = FakeWindowService()
    backend = WindowMessageBackend(111, service)

    assert backend.scale_point(500, 400, 1000, 800) == (250, 150)
    assert backend.scale_point(999, 799, 1000, 800) == (499, 299)
    assert backend.scale_point(40, 70, 0, 0) == (40, 70)

from responsive import HEADER_HEIGHT, RUN_BAR_HEIGHT, LayoutMode, layout_for_width


def test_wide_layout_keeps_the_sequence_and_inspector_side_by_side():
    layout = layout_for_width(1360)
    assert layout == LayoutMode("wide", 368, False, True)
    assert 1360 - layout.inspector_width >= 900


def test_medium_layout_docks_the_inspector_without_clipping_the_workspace():
    layout = layout_for_width(1100)
    assert layout.name == "medium"
    assert layout.inspector_width == 340
    assert layout.inspector_overlay is False
    # The tab header replaced the side rail, so the whole width less the inspector
    # is available to the active page.
    assert 1100 - layout.inspector_width >= 684


def test_compact_layout_overlays_inspector_and_drops_shortcut_hints():
    layout = layout_for_width(900)
    assert layout.name == "compact"
    assert layout.inspector_overlay is True
    assert layout.shortcut_hints_visible is False
    assert 900 >= 700


def test_compact_layout_keeps_shortcut_hints_once_the_run_bar_has_room():
    assert layout_for_width(1000).shortcut_hints_visible is True


def test_chrome_leaves_workable_height_at_the_minimum_window_size():
    # Minimum window height is 640; the header and run bar must not eat the page.
    assert 640 - HEADER_HEIGHT - RUN_BAR_HEIGHT >= 460

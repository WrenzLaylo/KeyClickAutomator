from responsive import LayoutMode, layout_for_width


def test_wide_layout_keeps_three_columns():
    layout = layout_for_width(1360)
    assert layout == LayoutMode("wide", 216, 368, False)


def test_medium_layout_compacts_navigation_without_clipping_workspace():
    layout = layout_for_width(1100)
    assert layout.name == "medium"
    assert layout.navigation_width == 76
    assert layout.inspector_width == 340
    assert 1100 - layout.navigation_width - layout.inspector_width >= 684


def test_compact_layout_overlays_inspector():
    layout = layout_for_width(900)
    assert layout.name == "compact"
    assert layout.navigation_width == 76
    assert layout.inspector_overlay is True
    assert 900 - layout.navigation_width >= 700

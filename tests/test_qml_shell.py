"""The window itself: it loads, resizes, and the header behaves at every width."""

from PySide6.QtCore import QObject
from PySide6.QtCore import QPoint
from PySide6.QtCore import QPointF
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from qt_app import build_engine
from qt_app import create_application

from qml_harness import app, show_tab, visual_children_named


def test_application_supports_native_profile_dialogs():
    assert isinstance(create_application([]), QApplication)

def test_qml_root_loads_and_resizes_without_clipping_contract():
    engine, controller = build_engine(start_hotkeys=False)
    roots = engine.rootObjects()
    assert len(roots) == 1
    window = roots[0]
    for width, height in [(900, 640), (1024, 720), (1240, 760), (1600, 900)]:
        window.setWidth(width)
        window.setHeight(height)
        app.processEvents()
        assert window.property("layoutMode") in {"compact", "medium", "wide"}
        if width == 900:
            assert window.property("inspectorOpen") is False
        assert window.width() == width
        assert window.height() == height
    window.close()
    controller.shutdown()

def test_inspector_tab_selection_pill_slides_between_tabs():
    engine, controller = build_engine(start_hotkeys=False)
    window = engine.rootObjects()[0]
    pill = window.findChild(QObject, "tabSelectionPill")
    assert pill is not None
    start_x = pill.property("x")
    window.setProperty("activeInspectorTab", 1)
    QTest.qWait(280)
    assert pill.property("x") > start_x + 50
    window.close()
    controller.shutdown()

def test_header_status_badge_aligns_with_the_sequence_heading():
    engine, controller = build_engine(start_hotkeys=False)
    window = engine.rootObjects()[0]
    window.setWidth(1360)
    window.setHeight(840)
    app.processEvents()

    heading = window.findChild(QQuickItem, "sequenceHeading")
    status = window.findChild(QQuickItem, "headerStatusBadge")
    header_row = window.findChild(QQuickItem, "sequenceHeaderRow")
    assert heading is not None and status is not None and header_row is not None
    heading_position = heading.mapToScene(QPointF(0, 0))
    status_position = status.mapToScene(QPointF(0, 0))
    header_position = header_row.mapToScene(QPointF(0, 0))
    assert abs(status_position.y() - heading_position.y()) < 0.1
    assert status.height() == heading.height()
    assert abs(header_row.width() - header_row.parentItem().width()) < 0.1
    assert abs(
        status_position.x() + status.width() - header_position.x() - header_row.width()
    ) <= 0.5

    window.close()
    controller.shutdown()

def test_workspace_navigation_hover_state_is_isolated_per_button():
    engine, controller = build_engine(start_hotkeys=False)
    window = engine.rootObjects()[0]
    buttons = [window.findChild(QQuickItem, f"workspaceNav_{name}") for name in ("save", "new")]
    assert all(button is not None for button in buttons)
    for hovered_index, button in enumerate(buttons):
        for index, item in enumerate(buttons):
            item.setProperty("pointerHover", index == hovered_index)
        app.processEvents()
        QTest.qWait(160)
        assert [item.property("pointerHover") for item in buttons] == [
            index == hovered_index for index in range(len(buttons))
        ]
        assert button.property("background").property("color").name() == "#e5eaf2"
    window.close()
    controller.shutdown()

def test_workspace_tabs_switch_pages_and_collapse_labels_when_narrow():
    engine, controller = build_engine(start_hotkeys=False)
    window = engine.rootObjects()[0]
    window.setWidth(1360)
    window.setHeight(840)
    app.processEvents()

    tabs = [
        window.findChild(QQuickItem, f"workspaceTab_{name}")
        for name in ("sequence", "profiles", "runner")
    ]
    stack = window.findChild(QQuickItem, "workspaceStack")
    inspector_pane = window.findChild(QQuickItem, "runInspector")
    assert all(tab is not None for tab in tabs)
    assert stack is not None and inspector_pane is not None

    # Exactly one tab reads as selected, and it tracks the visible page.
    for index in (0, 1, 2):
        show_tab(window, index, settle=120)
        assert [tab.property("selected") for tab in tabs] == [
            position == index for position in range(3)
        ]
        assert stack.property("currentIndex") == index
        # The inspector edits the sequence, so it only rides along with that tab.
        assert inspector_pane.isVisible() is (index == 0)

    show_tab(window, 0, settle=120)
    wide_widths = [tab.width() for tab in tabs]

    window.setWidth(960)
    app.processEvents()
    QTest.qWait(120)
    assert window.property("layoutMode") == "compact"
    narrow_widths = [tab.width() for tab in tabs]
    for wide, narrow in zip(wide_widths, narrow_widths):
        assert narrow < wide

    window.close()
    controller.shutdown()

def test_quiet_button_hover_fades_from_the_hover_surface_without_a_dark_flash():
    engine, controller = build_engine(start_hotkeys=False)
    window = engine.rootObjects()[0]
    window.setWidth(1920)
    window.setHeight(1016)
    app.processEvents()
    button = window.findChild(QQuickItem, "workspaceNav_save")
    assert button is not None
    background = button.property("background")
    QTest.qWait(160)
    assert background.property("color").getRgb() == (229, 234, 242, 0)
    hover_position = button.mapToScene(QPointF(button.width() / 2, button.height() / 2))
    sample_position = button.mapToScene(QPointF(button.width() - 8, 8))
    QTest.mouseMove(window, QPoint(round(hover_position.x()), round(hover_position.y())))
    QTest.qWait(35)
    red, green, blue, alpha = background.property("color").getRgb()
    assert (red, green, blue) == (229, 234, 242)
    assert 0 < alpha < 255
    rendered_color = window.grabWindow().pixelColor(
        round(sample_position.x()), round(sample_position.y())
    )
    assert min(rendered_color.red(), rendered_color.green(), rendered_color.blue()) > 220
    window.close()
    controller.shutdown()

def test_action_row_hover_stays_blue_white_without_a_dark_flash():
    engine, controller = build_engine(start_hotkeys=False)
    window = engine.rootObjects()[0]
    window.setWidth(900)
    window.setHeight(840)
    controller.addAction({"kind": "key", "value": "enter"})
    controller.selectedIndex = -1
    app.processEvents()
    QTest.qWait(180)

    cards = visual_children_named(window.contentItem(), "actionCardSurface")
    assert len(cards) == 1
    card = cards[0]
    assert card.property("color").getRgb() == (255, 255, 255, 255)

    hover_position = card.mapToScene(QPointF(card.width() / 2, card.height() / 2))
    sample_position = card.mapToScene(QPointF(card.width() / 2, card.height() - 8))
    QTest.mouseMove(window, QPoint(round(hover_position.x()), round(hover_position.y())))
    QTest.qWait(35)
    red, green, blue, alpha = card.property("color").getRgb()
    assert 244 <= red <= 255
    assert 247 <= green <= 255
    assert blue == 255
    assert alpha == 255
    QTest.qWait(130)
    assert card.property("color").name() == "#f4f7ff"
    rendered_color = window.grabWindow().pixelColor(
        round(sample_position.x()), round(sample_position.y())
    )
    assert min(rendered_color.red(), rendered_color.green(), rendered_color.blue()) > 220
    window.close()
    controller.shutdown()

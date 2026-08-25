from pathlib import Path


QML = (Path(__file__).parents[1] / "qml" / "Main.qml").read_text(encoding="utf-8")
QT_APP = (Path(__file__).parents[1] / "qt_app.py").read_text(encoding="utf-8")


def test_brand_uses_packaged_logo_instead_of_placeholder_monogram():
    assert 'source: "../assets/app-logo-transparent.png"' in QML
    assert 'objectName: "brandLogo"' in QML
    assert 'text: "K"' not in QML


def test_buttons_use_isolated_pointer_hover_state_and_stop_has_icon():
    assert "property bool pointerHover" in QML
    assert "control.pointerHover" in QML
    assert 'objectName: "runStopButton"' in QML
    assert 'leading: "■"' in QML


def test_sequence_identity_and_selection_are_visible():
    assert "controller.currentProfileName" in QML
    assert 'objectName: "stepBadge"' in QML
    assert 'objectName: "sequenceConnector"' in QML
    assert 'text: String(actionCard.actionIndex + 1).padStart(2, "0")' in QML
    assert 'text: "EDITING"' in QML


def test_sequence_rows_use_numbered_blue_workflow_steps():
    assert 'readonly property color primary: "#1565FF"' in QML
    assert 'objectName: "actionCardSurface"' in QML
    assert 'controller.selectedIndex === actionCard.actionIndex ? "#EDF3FF"' in QML
    assert 'controller.selectedIndex === actionCard.actionIndex ? root.primary' in QML
    assert 'objectName: "editingBadge"' in QML
    assert 'readonly property color accent: "#B86700"' not in QML


def test_action_type_picker_uses_rounded_themed_popup():
    assert 'objectName: "actionTypePicker"' in QML
    assert "popup: Popup" in QML
    assert "clip: true" in QML
    assert 'radius: 14' in QML


def test_animated_hover_surfaces_do_not_interpolate_from_transparent_black():
    assert "component KButton: AbstractButton" in QML
    assert "component KButton: Button" not in QML
    assert 'control.quiet ? "#00E5EAF2"' in QML
    assert 'hover.hovered ? "#F4F7FF" : root.surface' in QML
    assert 'option.hovered ? "#F1F4F9" : "#00F1F4F9"' in QML


def test_status_toast_uses_theme_surfaces_not_near_black():
    assert 'color: "#F2171A21"' not in QML
    assert "toast.tone === \"error\" ? root.redSoft" in QML
    assert "root.height - 18 - runBar.height - height - 10" in QML


def test_runtime_version_uses_controller_release_constant():
    assert "from qt_controller import APP_VERSION, AutomatorController" in QT_APP
    assert "app.setApplicationVersion(APP_VERSION)" in QT_APP


def test_visible_version_labels_use_qt_runtime_version():
    assert 'title: "KeyClick Automator " + Qt.application.version' in QML
    assert 'text: "AUTOMATOR  ·  " + Qt.application.version' in QML
    assert 'KeyClick Automator 3.0"' not in QML
    assert 'AUTOMATOR  ·  3.0"' not in QML


def test_all_global_shortcuts_have_record_controls_and_signal_routing():
    for target in ("start", "capture", "stop"):
        assert f'objectName: "shortcutRecord_{target}"' in QML
        assert f'controller.recordGlobalShortcut("{target}")' in QML
    assert "function onShortcutCaptured(target, value)" in QML


def test_navigation_hover_stays_neutral_and_record_buttons_do_not_overflow():
    assert "property bool navStyle" not in QML
    assert "control.navStyle" not in QML
    assert QML.count("implicitWidth: 106") == 3
    assert QML.count("activeNeutral: root.shortcutRecordingTarget ===") == 3
    assert 'text: root.shortcutRecordingTarget === "start" ? "Listening" : "Record"' in QML


def test_compact_shortcut_dock_and_run_controls_have_stable_visual_contracts():
    assert "component ShortcutHint: Rectangle" in QML
    assert 'objectName: "shortcutDock"' in QML
    assert 'objectName: "runControlGroup"' in QML
    assert 'objectName: "runStartButton"' in QML
    assert 'keyHint: controller.runSettings.startHotkey' in QML
    assert 'keyHint: controller.runSettings.stopHotkey' in QML
    assert "enabled: !controller.running && controller.canRun" in QML

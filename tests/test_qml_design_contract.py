from pathlib import Path


QML = (Path(__file__).parents[1] / "qml" / "Main.qml").read_text(encoding="utf-8")
QT_APP = (Path(__file__).parents[1] / "qt_app.py").read_text(encoding="utf-8")


def test_brand_uses_packaged_logo_instead_of_placeholder_monogram():
    assert 'source: "../assets/app-logo.png"' in QML
    assert 'text: "K"' not in QML


def test_buttons_use_isolated_pointer_hover_state_and_stop_has_icon():
    assert "property bool pointerHover" in QML
    assert "control.pointerHover" in QML
    assert 'text: "Stop"; leading: "■"' in QML


def test_sequence_identity_and_selection_are_visible():
    assert "controller.currentProfileName" in QML
    assert 'text: "Sequence " + (actionCard.actionIndex + 1)' in QML
    assert "selectedStripe" in QML


def test_action_type_picker_uses_rounded_themed_popup():
    assert 'objectName: "actionTypePicker"' in QML
    assert "popup: Popup" in QML
    assert "clip: true" in QML
    assert 'radius: 14' in QML


def test_status_toast_uses_theme_surfaces_not_near_black():
    assert 'color: "#F2171A21"' not in QML
    assert "toast.tone === \"error\" ? root.redSoft" in QML


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
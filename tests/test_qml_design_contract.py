from pathlib import Path


QML = (Path(__file__).parents[1] / "qml" / "Main.qml").read_text(encoding="utf-8")
APP_BUTTON = (Path(__file__).parents[1] / "qml" / "components" / "AppButton.qml").read_text(encoding="utf-8")
APP_SCROLLBAR = (Path(__file__).parents[1] / "qml" / "components" / "AppScrollBar.qml").read_text(encoding="utf-8")
QT_APP = (Path(__file__).parents[1] / "qt_app.py").read_text(encoding="utf-8")
CAPTURE_OVERLAY = (Path(__file__).parents[1] / "capture_overlay.py").read_text(encoding="utf-8")


def test_brand_uses_packaged_logo_instead_of_placeholder_monogram():
    assert 'source: "../assets/app-logo-transparent.png"' in QML
    assert 'objectName: "brandLogo"' in QML
    assert 'text: "K"' not in QML


def test_buttons_use_isolated_pointer_hover_state_and_stop_has_icon():
    assert "property bool pointerHover" in APP_BUTTON
    assert "control.pointerHover" in APP_BUTTON
    assert 'objectName: "runStopButton"' in QML
    assert 'leading: "■"' in QML


def test_sequence_identity_and_selection_are_visible():
    assert "controller.currentProfileName" in QML
    assert 'objectName: "stepBadge"' in QML
    assert 'objectName: "sequenceConnector"' in QML
    assert 'text: String(actionCard.actionIndex + 1).padStart(2, "0")' in QML
    assert '? "RUNNING" : "EDITING"' in QML


def test_sequence_rows_use_numbered_blue_workflow_steps():
    assert 'readonly property color primary: "#1565FF"' in QML
    assert 'objectName: "actionCardSurface"' in QML
    assert 'controller.selectedIndex === actionCard.actionIndex ? "#EDF3FF"' in QML
    assert 'controller.selectedIndex === actionCard.actionIndex ? root.primary' in QML
    assert 'objectName: "editingBadge"' in QML
    assert 'readonly property color accent: "#B86700"' not in QML


def test_action_toggle_animates_without_disabling_its_delegate():
    assert "required property bool actionEnabled" in QML
    assert "required property bool enabled" not in QML
    assert "checked: actionCard.actionEnabled" in QML
    assert 'objectName: "actionToggleTrack_" + actionCard.actionIndex' in QML
    assert 'objectName: "actionToggleKnob_" + actionCard.actionIndex' in QML
    assert "easing.type: Easing.OutBack" in QML
    assert "opacity: actionCard.actionEnabled ? 1 : 0.42" in QML


def test_action_type_picker_uses_rounded_themed_popup():
    assert 'objectName: "actionTypePicker"' in QML
    assert "popup: Popup" in QML
    assert "clip: true" in QML
    assert 'radius: 14' in QML


def test_animated_hover_surfaces_do_not_interpolate_from_transparent_black():
    assert "component KButton: Components.AppButton" in QML
    assert "AbstractButton" in APP_BUTTON
    assert "component KButton: Button" not in QML
    assert '? "#00E5EAF2"' in APP_BUTTON
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
    assert "enabled: !controller.running && controller.canRun &&" in QML


def test_pointer_recording_uses_a_cancellable_frozen_screen_picker():
    assert 'objectName: "recordPointerPosition"' in QML
    assert 'text: "Capture current pointer"' not in QML
    assert "controller.startPositionCapture(0)" in QML
    assert "freezes and dims the screen" in QML
    assert 'sequence: "Esc"' in QML
    assert 'self.setObjectName("positionCaptureOverlay")' in CAPTURE_OVERLAY
    assert "screen.grabWindow(0)" in CAPTURE_OVERLAY
    assert "Click to record" in CAPTURE_OVERLAY


def test_action_key_and_hotkey_recorders_are_visible_and_cancellable():
    assert 'objectName: "recordActionKey"' in QML
    assert 'objectName: "recordActionHotkey"' in QML
    assert "controller.recordActionHotkey()" in QML
    assert "controller.cancelActionCapture()" in QML
    assert 'function onActionHotkeyCaptured(value)' in QML


def test_click_actions_offer_live_pointer_targeting():
    assert 'objectName: "followPointerSwitch"' in QML
    assert 'text: "Follow current pointer"' in QML
    assert "useCurrentPointer: clickAction && followPointerSwitch.checked && desktopTarget" in QML


def test_safe_editing_controls_cover_recovery_undo_and_targeted_runs():
    assert 'objectName: "recoveryDialog"' in QML
    assert 'objectName: "recoveryDiscardButton"' in QML
    assert 'objectName: "recoveryAcceptButton"' in QML
    assert 'Layout.preferredWidth: 88' in QML
    assert 'Layout.preferredWidth: 148' in QML
    assert 'id: buttonContent' in APP_BUTTON
    assert 'anchors.centerIn: parent' in APP_BUTTON
    assert 'objectName: control.objectName + "_label"' in APP_BUTTON
    assert 'objectName: "unsavedChangesDialog"' in QML
    assert 'objectName: "unsavedCancelButton"' in QML
    assert 'objectName: "unsavedDiscardButton"' in QML
    assert 'objectName: "unsavedSaveButton"' in QML
    assert QML.count("implicitHeight: 44") >= 4
    assert 'objectName: "undoDeleteButton"' in QML
    assert 'objectName: "testActionButton"' in QML
    assert 'objectName: "runFromHereButton"' in QML
    assert "controller.startRunWithSettings(runForm.payload())" in QML


def test_in_app_profile_library_supports_switching_and_folder_management():
    assert 'objectName: "profileLibraryDrawer"' in QML
    assert 'objectName: "profileLibraryList"' in QML
    assert 'objectName: "profileLibraryEmptyState"' in QML
    assert 'objectName: "chooseProfileFolderButton"' in QML
    assert 'objectName: "profileLibrarySaveAsButton"' in QML
    assert 'objectName: "profileLibraryOpenFileButton"' in QML
    assert QML.count("Layout.preferredWidth: 112") >= 2
    assert "model: controller.profileEntries" in QML
    assert "modelData.path === controller.currentProfilePath" in QML
    assert "root.requestProfileOpen(modelData.path)" in QML
    assert 'sequence: "Ctrl+O"' in QML
    assert 'sequence: "Ctrl+Shift+S"' in QML
    assert 'objectName: "profileLibraryScrollBar"' in QML


def test_sequence_status_uses_the_full_header_width():
    assert 'objectName: "sequenceHeaderRow"' in QML
    assert "Layout.preferredWidth: parent.width" in QML
    assert "property bool hamburgerIcon" in APP_BUTTON
    assert "hamburgerIcon: true" in QML
    assert 'text: "Refresh"' in QML


def test_sequence_actions_support_pointer_dragging_and_button_reordering():
    assert 'objectName: "actionDragHandle_" + actionCard.actionIndex' in QML
    assert 'objectName: "sequenceDropIndicator_" + actionCard.actionIndex' in QML
    assert "DragHandler" in QML
    assert "root.beginSequenceDrag(actionCard.actionIndex)" in QML
    assert "root.updateSequenceDrag(actionCard.actionIndex, translation.y)" in QML
    assert "controller.moveActionTo(index, target)" in QML
    assert "controller.moveAction(controller.selectedIndex, -1)" in QML
    assert "controller.moveAction(controller.selectedIndex, 1)" in QML
    assert "visible: actionCard.actionIndex < actionList.count - 1" in QML
    assert "transform: Translate { y: reorderDrag.active ? reorderDrag.translation.y : 0 }" in QML
    assert "move: Transition" not in QML
    assert "moveDisplaced: Transition" not in QML


def test_scrollbars_only_render_for_overflow_and_lists_reserve_a_gutter():
    assert "size < 0.999" in APP_SCROLLBAR
    assert "interactive: visible" in APP_SCROLLBAR
    assert 'objectName: "sequenceScrollBar"' in QML
    assert "sequenceScrollBar.visible ? sequenceScrollBar.width + 8 : 0" in QML
    assert "profileScrollBar.visible ? profileScrollBar.width + 8 : 0" in QML
    assert 'objectName: "windowPickerScrollBar"' in QML
    assert "topPadding: 8" in QML
    assert "bottomPadding: 14" in QML
    assert 'objectName: control.objectName + "_thumb"' in APP_SCROLLBAR


def test_window_picker_uses_a_bounded_overlay_flick_area():
    assert "parent: Overlay.overlay" in QML
    assert "id: windowPickerScroll" in QML
    assert "boundsBehavior: Flickable.StopAtBounds" in QML
    assert "windowPickerScroll.returnToBounds()" in QML
    assert "Layout.rightMargin: 6" in QML
    assert "Layout.bottomMargin: 10" in QML


def test_background_window_targeting_discloses_picker_and_compatibility_limits():
    assert 'objectName: "desktopTargetModeButton"' in QML
    assert 'objectName: "windowTargetModeButton"' in QML
    assert 'objectName: "pickWindowButton"' in QML
    assert 'objectName: "windowPickerDialog"' in QML
    assert 'objectName: "desktopWindowChoice"' in QML
    assert 'objectName: "windowChoice_" + index' in QML
    assert 'controller.setTargetMode("window")' in QML
    assert "controller.startWindowPick()" in QML
    assert "controller.selectWindowTarget(modelData.handle)" in QML
    assert "Your pointer remains free" in QML
    assert "coordinateSpace: coordinateSpace" in QML
    assert "referenceWidth: referenceWidth" in QML
    assert "referenceHeight: referenceHeight" in QML
    assert "referenceWidth2: referenceWidth2" in QML
    assert "referenceHeight2: referenceHeight2" in QML

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Effects
import qml
import "components"
import "components" as Components
import "pages" as Pages
import "dialogs" as Dialogs

ApplicationWindow {
    id: root
    objectName: "mainWindow"
    width: 1360
    height: 840
    minimumWidth: 900
    minimumHeight: 640
    visible: true
    title: "KeyClick Automator " + Qt.application.version
    color: canvas
    opacity: 0

    readonly property string layoutMode: width >= 1240 ? "wide" : (width >= 1024 ? "medium" : "compact")
    readonly property bool overlayInspector: layoutMode === "compact"
    property bool inspectorOpen: !overlayInspector
    // The inspector edits the sequence, so it only shares the screen with that tab.
    readonly property bool inspectorVisible: activeTab === 0
    readonly property bool inspectorDocked: inspectorVisible && !overlayInspector
    property int activeTab: 0
    property int activeInspectorTab: 0
    property int editorIndex: -1
    property string shortcutRecordingTarget: ""
    property string shortcutCaptureError: ""
    property string pendingDestructiveAction: ""
    property string pendingProfilePath: ""
    property bool closeConfirmed: false
    property int draggedActionIndex: -1
    property int dragTargetIndex: -1

    readonly property color ink: "#171A21"
    readonly property color ink2: "#4B5363"
    readonly property color ink3: "#7B8494"
    readonly property color canvas: "#F3F5F9"
    readonly property color surface: "#FFFFFF"
    readonly property color surface2: "#EEF1F6"
    readonly property color surface3: "#E5EAF2"
    readonly property color line: "#D9DFE8"
    readonly property color primary: "#1565FF"
    readonly property color primaryHover: "#0759EB"
    readonly property color primarySoft: "#E8F0FF"
    readonly property color green: "#148A5B"
    readonly property color red: "#D33C54"
    readonly property color redSoft: "#FFF0F3"
    readonly property color successSoft: "#E9F7F1"

    FontLoader { id: interRegular; source: "../assets/fonts/Inter-Regular.ttf" }
    FontLoader { id: interMedium; source: "../assets/fonts/Inter-Medium.ttf" }
    FontLoader { id: interSemiBold; source: "../assets/fonts/Inter-SemiBold.ttf" }
    FontLoader { id: interBold; source: "../assets/fonts/Inter-Bold.ttf" }

    font.family: interRegular.name || "Segoe UI"

    Behavior on opacity { NumberAnimation { duration: 260; easing.type: Easing.OutCubic } }
    onActiveInspectorTabChanged: {
        if (activeInspectorTab !== 0 && controller.actionCaptureMode !== "")
            controller.cancelActionCapture()
    }
    Component.onCompleted: {
        opacity = 1
        if (controller.draftAvailable)
            Qt.callLater(function() { recoveryDialog.open() })
    }
    onOverlayInspectorChanged: inspectorOpen = !overlayInspector
    onClosing: function(close) {
        if (controller.recoveryEnabled && !root.closeConfirmed && (controller.dirty || controller.runSettingsPending)) {
            close.accepted = false
            root.pendingDestructiveAction = "close"
            unsavedDialog.open()
        } else {
            controller.shutdown()
        }
    }

    function selectTab(index) {
        if (index === root.activeTab)
            return
        // Recording listeners belong to the sequence editor and must not survive
        // a move to another tab, where nothing can cancel them.
        if (controller.actionCaptureMode !== "")
            controller.cancelActionCapture()
        if (controller.capturePending)
            controller.cancelPositionCapture()
        root.activeTab = index
        if (index === 1)
            controller.refreshProfiles()
    }

    function beginNewAction() {
        if (controller.actionCaptureMode !== "")
            controller.cancelActionCapture()
        if (controller.capturePending)
            controller.cancelPositionCapture()
        if (controller.windowPickPending)
            controller.cancelWindowPick()
        controller.selectedIndex = -1
        root.editorIndex = -1
        // Anything that edits the sequence has to land you where the sequence is.
        // Doing this from another tab wiped the sequence with nothing on screen
        // to show for it, which read as "the button does nothing".
        root.selectTab(0)
        root.activeInspectorTab = 0
        root.inspectorOpen = true
        inspector.actionEditor.reset()
        Qt.callLater(function() { inspector.focusActionType() })
    }

    // The recovery dialog restores a selection the editor has not seen yet, and
    // it cannot reach the editor's id from its own file.
    function loadActionIntoEditor(index) {
        inspector.actionEditor.loadAction(index)
    }

    function saveProfileWithVisibleSettings() {
        if (controller.runSettingsPending && !inspector.runSettingsForm.apply()) {
            root.activeInspectorTab = 1
            root.inspectorOpen = true
            return false
        }
        return controller.saveProfile()
    }

    function saveProfileAsWithVisibleSettings() {
        if (controller.runSettingsPending && !inspector.runSettingsForm.apply()) {
            root.activeInspectorTab = 1
            root.inspectorOpen = true
            return false
        }
        return controller.saveProfileAs()
    }

    function performDestructiveAction(action) {
        if (action === "new") {
            controller.clearActions()
            root.beginNewAction()
        } else if (action === "open") {
            if (controller.openProfile())
                root.selectTab(0)
        } else if (action === "profile") {
            var profilePath = root.pendingProfilePath
            root.pendingProfilePath = ""
            if (controller.openProfilePath(profilePath))
                root.selectTab(0)
        } else if (action === "close") {
            controller.discardDraft()
            root.closeConfirmed = true
            root.close()
        }
    }

    function requestDestructiveAction(action) {
        if (action !== "profile")
            root.pendingProfilePath = ""
        if (controller.actionCaptureMode !== "")
            controller.cancelActionCapture()
        if (controller.capturePending)
            controller.cancelPositionCapture()
        if (controller.windowPickPending)
            controller.cancelWindowPick()
        if (controller.dirty || controller.runSettingsPending) {
            root.pendingDestructiveAction = action
            unsavedDialog.open()
        } else {
            root.performDestructiveAction(action)
        }
    }

    function requestProfileOpen(path) {
        root.pendingProfilePath = path
        root.requestDestructiveAction("profile")
    }

    function openProfileHistory(path, label) {
        if (controller.running)
            return
        profileHistoryDialog.profilePath = path
        profileHistoryDialog.profileLabel = label
        profileHistoryDialog.entries = controller.profileVersions(path)
        profileHistoryDialog.open()
    }

    function requestProfileDelete(path, label) {
        if (controller.running)
            return
        deleteProfileDialog.profilePath = path
        deleteProfileDialog.profileLabel = label
        deleteProfileDialog.open()
    }

    function openTargetPicker() {
        if (controller.running)
            return
        controller.refreshAutomationTargets()
        targetPickerDialog.open()
    }




    function beginSequenceDrag(index) {
        draggedActionIndex = index
        dragTargetIndex = index
        controller.selectedIndex = index
    }

    function updateSequenceDrag(index, offsetY) {
        if (draggedActionIndex !== index || sequencePage.actionCount < 2)
            return
        var rowSpan = 76 + sequencePage.listSpacing
        dragTargetIndex = Math.max(
            0,
            Math.min(sequencePage.actionCount - 1, index + Math.round(offsetY / rowSpan))
        )
    }

    function finishSequenceDrag(index) {
        if (draggedActionIndex !== index)
            return
        var target = dragTargetIndex
        draggedActionIndex = -1
        dragTargetIndex = -1
        if (target >= 0 && target !== index)
            controller.moveActionTo(index, target)
    }

    Shortcut {
        sequence: "Ctrl+Z"
        enabled: controller.canUndo && !controller.running
        onActivated: {
            // Restoring an action off-tab would be invisible too.
            root.selectTab(0)
            controller.undoDelete()
        }
    }
    Shortcut {
        sequence: "Ctrl+S"
        enabled: !controller.running
        onActivated: root.saveProfileWithVisibleSettings()
    }
    Shortcut {
        sequence: "Ctrl+Shift+S"
        enabled: !controller.running
        onActivated: root.saveProfileAsWithVisibleSettings()
    }
    Shortcut {
        sequence: "Ctrl+O"
        enabled: !controller.running
        onActivated: root.selectTab(1)
    }
    Shortcut {
        sequence: "Esc"
        enabled: controller.capturePending || controller.actionCaptureMode !== ""
        onActivated: {
            if (controller.capturePending)
                controller.cancelPositionCapture()
            else
                controller.cancelActionCapture()
        }
    }

    function toneColor(tone) {
        if (tone === "accent") return primary
        if (tone === "success") return green
        if (tone === "danger") return red
        return ink2
    }

















    // Cool neutral surfaces keep the original blue utility-tool character.
    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0; color: "#F3F6FB" }
            GradientStop { position: 0.58; color: "#F4F5F9" }
            GradientStop { position: 1; color: "#F7F7FA" }
        }
    }

    Item {
        id: appShell
        anchors.fill: parent

        AppHeader {
            id: appHeader
            app: root
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
        }

        Item {
            id: workspace
            anchors.left: parent.left
            anchors.right: root.inspectorDocked ? inspector.left : parent.right
            anchors.top: appHeader.bottom
            anchors.bottom: runBar.top
            anchors.bottomMargin: 12
            clip: true

            StackLayout {
                id: workspaceStack
                objectName: "workspaceStack"
                anchors.fill: parent
                currentIndex: root.activeTab

                Pages.SequencePage {
                    id: sequencePage
                    app: root
                    runForm: inspector.runSettingsForm
                }

                Pages.ProfilesPage {
                    app: root
                }

                Pages.RunnerPage {
                    app: root
                }
            }
        }

        RunBar {
            id: runBar
            app: root
            runForm: inspector.runSettingsForm
            actionCount: sequencePage.actionCount
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.leftMargin: root.layoutMode === "wide" ? 28 : 22
            anchors.rightMargin: root.layoutMode === "wide" ? 28 : 22
            anchors.bottomMargin: 18
        }
        Rectangle {
            visible: root.inspectorVisible && root.overlayInspector && root.inspectorOpen
            anchors.fill: parent
            color: "#42111A2D"
            opacity: root.inspectorOpen ? 1 : 0
            z: 9
            Behavior on opacity { NumberAnimation { duration: 160 } }
            TapHandler { onTapped: root.inspectorOpen = false }
        }

        RunInspector {
            id: inspector
            app: root
            anchors.top: appHeader.bottom
            anchors.bottom: runBar.top
            anchors.bottomMargin: 12
        }
    }


    Dialogs.RecoveryDialog {
        id: recoveryDialog
        app: root
    }


    Dialogs.TargetPickerDialog {
        id: targetPickerDialog
        app: root
    }

    Dialogs.ProfileHistoryDialog {
        id: profileHistoryDialog
        app: root
    }

    Dialogs.DeleteProfileDialog {
        id: deleteProfileDialog
        app: root
    }

    Dialogs.UnsavedChangesDialog {
        id: unsavedDialog
        app: root
    }

    Rectangle {
        id: toast
        objectName: "toastPill"
        // The text wraps inside a fixed content width, so the pill always grows to
        // hold the whole message instead of letting long errors spill past its edge.
        readonly property int toastTextLimit: Math.max(180, Math.min(360, root.width - 120))
        width: Math.min(toastTextLimit + 54, toastText.contentWidth + 54)
        height: Math.max(48, toastText.contentHeight + 26)
        radius: 14
        color: toast.tone === "error" ? Theme.redSoft : toast.tone === "success" ? Theme.successSoft : Theme.primarySoft
        border.width: 1
        border.color: toast.tone === "error" ? "#F3B8C2" : toast.tone === "success" ? "#A9DFC9" : "#B9CEFA"
        anchors.horizontalCenter: parent.horizontalCenter
        y: visible ? root.height - 18 - runBar.height - height - 10 : parent.height + 16
        z: 30
        visible: opacity > 0
        opacity: 0
        property string message: ""
        property string tone: "neutral"
        Behavior on y { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
        Behavior on opacity { NumberAnimation { duration: 170 } }
        Row {
            anchors.centerIn: parent
            spacing: 9
            Rectangle { width: 8; height: 8; radius: 4; color: toast.tone === "error" ? Theme.red : toast.tone === "success" ? Theme.green : Theme.primary; anchors.verticalCenter: parent.verticalCenter }
            Text {
                id: toastText
                objectName: "toastText"
                width: Math.min(toast.toastTextLimit, implicitWidth)
                text: toast.message
                wrapMode: Text.WordWrap
                maximumLineCount: 3
                elide: Text.ElideRight
                color: toast.tone === "error" ? Theme.red : toast.tone === "success" ? Theme.green : Theme.ink
                font.family: Theme.semiBold
                font.pixelSize: 12
                anchors.verticalCenter: parent.verticalCenter
            }
        }
        Timer { id: toastTimer; interval: 2600; onTriggered: toast.opacity = 0 }
    }

    Connections {
        target: controller
        function onToast(message, tone) {
            toast.message = message
            toast.tone = tone
            toast.opacity = 1
            toastTimer.restart()
        }
    }
}

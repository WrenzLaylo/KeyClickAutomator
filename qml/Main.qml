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
        editor.reset()
        Qt.callLater(function() { actionType.forceActiveFocus() })
    }

    function saveProfileWithVisibleSettings() {
        if (controller.runSettingsPending && !runForm.apply()) {
            root.activeInspectorTab = 1
            root.inspectorOpen = true
            return false
        }
        return controller.saveProfile()
    }

    function saveProfileAsWithVisibleSettings() {
        if (controller.runSettingsPending && !runForm.apply()) {
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
        if (draggedActionIndex !== index || actionList.count < 2)
            return
        var rowSpan = 76 + actionList.spacing
        dragTargetIndex = Math.max(
            0,
            Math.min(actionList.count - 1, index + Math.round(offsetY / rowSpan))
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

        Rectangle {
            id: appHeader
            objectName: "appHeader"
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            height: 72
            color: Theme.surface

            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                height: 1
                color: Theme.line
            }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 20
                anchors.rightMargin: 14
                spacing: 12

                Image {
                    id: brandLogo
                    objectName: "brandLogo"
                    Layout.preferredWidth: 34
                    Layout.preferredHeight: 34
                    source: "../assets/app-logo-transparent.png"
                    fillMode: Image.PreserveAspectFit
                    smooth: true
                    mipmap: true
                }

                ColumnLayout {
                    visible: root.layoutMode !== "compact"
                    spacing: 1
                    Text {
                        text: "KeyClick"
                        color: Theme.ink
                        font.family: Theme.bold
                        font.pixelSize: 16
                        font.weight: Font.Bold
                    }
                    Text {
                        text: "AUTOMATOR  ·  " + Qt.application.version
                        color: Theme.ink3
                        font.family: Theme.semiBold
                        font.pixelSize: 9
                        font.letterSpacing: 0.6
                    }
                }

                Rectangle {
                    objectName: "workspaceTabs"
                    Layout.leftMargin: root.layoutMode === "compact" ? 2 : 14
                    Layout.preferredWidth: workspaceTabRow.implicitWidth + 8
                    Layout.preferredHeight: 46
                    radius: 14
                    color: Theme.surface2

                    Row {
                        id: workspaceTabRow
                        anchors.centerIn: parent
                        spacing: 4
                        WorkspaceTab {
                            app: root
                            objectName: "workspaceTab_sequence"
                            tabIndex: 0
                            label: "Sequence"
                        }
                        WorkspaceTab {
                            app: root
                            objectName: "workspaceTab_profiles"
                            tabIndex: 1
                            label: "Profiles"
                            badge: controller.profileEntries.length > 0
                                   ? String(controller.profileEntries.length)
                                   : ""
                        }
                        WorkspaceTab {
                            app: root
                            objectName: "workspaceTab_runner"
                            tabIndex: 2
                            label: "Runner"
                            badge: controller.runQueueCount > 0 ? String(controller.runQueueCount) : ""
                        }
                    }
                }

                Item { Layout.fillWidth: true }

                KButton {
                    objectName: "workspaceNav_save"
                    implicitWidth: root.layoutMode === "compact" ? 42 : 112
                    implicitHeight: 40
                    text: root.layoutMode === "compact" ? "" : "Save profile"
                    leading: "↓"
                    quiet: true
                    enabled: !controller.running
                    // Only worth a tooltip when the label itself is collapsed away.
                    Accessible.name: "Save profile"
                    onClicked: root.saveProfileWithVisibleSettings()
                }
                KButton {
                    objectName: "workspaceNav_new"
                    implicitWidth: root.layoutMode === "compact" ? 42 : 122
                    implicitHeight: 40
                    text: root.layoutMode === "compact" ? "" : "New sequence"
                    leading: "+"
                    quiet: true
                    enabled: !controller.running
                    Accessible.name: "New sequence"
                    onClicked: root.requestDestructiveAction("new")
                }
            }
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

                Item {
                    objectName: "sequencePage"

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.leftMargin: root.layoutMode === "wide" ? 28 : 22
                        anchors.rightMargin: root.layoutMode === "wide" ? 28 : 22
                        anchors.topMargin: 20
                        anchors.bottomMargin: 4
                        spacing: 12

                        Item {
                            objectName: "sequenceHeaderRow"
                            Layout.fillWidth: true
                            Layout.preferredWidth: parent.width
                            Layout.preferredHeight: 68
                            ColumnLayout {
                                anchors.left: parent.left
                                anchors.right: inspectorToggleButton.visible
                                             ? inspectorToggleButton.left
                                             : statusBadge.left
                                anchors.rightMargin: 12
                                anchors.top: parent.top
                                height: implicitHeight
                                spacing: 3
                                Text {
                                    // The tab already says "Sequence", so the heading
                                    // names the profile you are actually editing.
                                    objectName: "sequenceHeading"
                                    Layout.fillWidth: true
                                    text: controller.currentProfileName
                                    elide: Text.ElideRight
                                    color: Theme.ink
                                    font.family: Theme.bold
                                    // Kept at 28 so the cap height still lines up with the
                                    // status badge on the right of this row.
                                    font.pixelSize: root.layoutMode === "compact" ? 24 : 28
                                    font.weight: Font.Bold
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: (controller.dirty ? "Unsaved  ·  " : "") + controller.summary
                                    elide: Text.ElideRight
                                    color: controller.dirty ? Theme.red : Theme.ink2
                                    font.family: Theme.regular
                                    font.pixelSize: 12
                                }
                            }
                            KButton {
                                id: inspectorToggleButton
                                objectName: "inspectorToggleButton"
                                visible: root.overlayInspector
                                anchors.right: statusBadge.left
                                anchors.rightMargin: 12
                                anchors.verticalCenter: statusBadge.verticalCenter
                                text: "Inspector"
                                leading: "⚙"
                                onClicked: root.inspectorOpen = !root.inspectorOpen
                            }
                            Rectangle {
                                id: statusBadge
                                objectName: "headerStatusBadge"
                                anchors.right: parent.right
                                anchors.top: parent.top
                                implicitWidth: statusRow.implicitWidth + 22
                                implicitHeight: 34
                                width: implicitWidth
                                height: implicitHeight
                                radius: 11
                                color: controller.statusTone === "success" ? "#E8F7F0" : controller.statusTone === "danger" ? "#FFF0F2" : controller.statusTone === "accent" ? Theme.primarySoft : Theme.surface2
                                Behavior on color { ColorAnimation { duration: 180 } }
                                Row {
                                    id: statusRow
                                    anchors.centerIn: parent
                                    spacing: 7
                                    Rectangle {
                                        width: 7; height: 7; radius: 4
                                        anchors.verticalCenter: parent.verticalCenter
                                        color: Theme.toneColor(controller.statusTone)
                                        SequentialAnimation on opacity {
                                            running: controller.running
                                            loops: Animation.Infinite
                                            NumberAnimation { to: 0.35; duration: 650 }
                                            NumberAnimation { to: 1; duration: 650 }
                                        }
                                    }
                                    Text { text: controller.status; color: Theme.toneColor(controller.statusTone); font.family: Theme.semiBold; font.pixelSize: 11 }
                                }
                            }
                        }

                        Rectangle {
                            id: sequenceToolbar
                            objectName: "sequenceToolbar"
                            Layout.fillWidth: true
                            Layout.preferredHeight: 48
                            radius: 13
                            color: Theme.surface
                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 14
                                anchors.rightMargin: 8
                                spacing: 4
                                Text {
                                    Layout.fillWidth: true
                                    text: controller.summary
                                    elide: Text.ElideRight
                                    color: Theme.ink2
                                    font.family: Theme.semiBold
                                    font.pixelSize: 11
                                }
                                KButton {
                                    objectName: "undoDeleteButton"
                                    visible: controller.canUndo
                                    enabled: !controller.running
                                    quiet: true
                                    text: workspace.width > 760 ? "Undo" : ""
                                    leading: "↶"
                                    implicitWidth: workspace.width > 760 ? 72 : 42
                                    onClicked: controller.undoDelete()
                                }
                                KButton {
                                    objectName: "testActionButton"
                                    visible: controller.selectedIndex >= 0 && workspace.width > 500
                                    enabled: !controller.running
                                    quiet: true
                                    text: workspace.width > 800 ? "Test" : ""
                                    leading: "1×"
                                    implicitWidth: workspace.width > 800 ? 68 : 42
                                    onClicked: controller.testActionWithSettings(controller.selectedIndex, runForm.payload())
                                }
                                KButton {
                                    objectName: "runFromHereButton"
                                    visible: controller.selectedIndex >= 0 && workspace.width > 540
                                    enabled: !controller.running
                                    quiet: true
                                    text: workspace.width > 860 ? "From here" : ""
                                    leading: "▶"
                                    implicitWidth: workspace.width > 860 ? 104 : 42
                                    onClicked: controller.startRunFromWithSettings(controller.selectedIndex, runForm.payload())
                                }
                                KButton { visible: controller.selectedIndex >= 0 && workspace.width > 610; enabled: !controller.running; quiet: true; text: "Up"; leading: "↑"; implicitWidth: 66; onClicked: controller.moveAction(controller.selectedIndex, -1) }
                                KButton { visible: controller.selectedIndex >= 0 && workspace.width > 680; enabled: !controller.running; quiet: true; text: "Down"; leading: "↓"; implicitWidth: 76; onClicked: controller.moveAction(controller.selectedIndex, 1) }
                                KButton { visible: controller.selectedIndex >= 0; enabled: !controller.running; quiet: true; text: workspace.width > 760 ? "Duplicate" : ""; leading: "⧉"; implicitWidth: workspace.width > 760 ? 98 : 42; onClicked: controller.duplicateAction(controller.selectedIndex) }
                                KButton { visible: controller.selectedIndex >= 0; enabled: !controller.running; danger: true; quiet: true; text: workspace.width > 760 ? "Delete" : ""; leading: "×"; implicitWidth: workspace.width > 760 ? 78 : 42; onClicked: controller.deleteAction(controller.selectedIndex) }
                            }
                        }

                        Rectangle {
                            id: sequenceCanvas
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            Layout.minimumHeight: 250
                            radius: 20
                            color: Theme.surface
                            border.width: 1
                            border.color: "#E6EAF0"

                            Column {
                                objectName: "sequenceEmptyState"
                                visible: actionList.count === 0
                                anchors.centerIn: parent
                                width: Math.min(420, parent.width - 56)
                                spacing: 12
                                Rectangle {
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    width: 62; height: 62; radius: 20
                                    gradient: Gradient {
                                        GradientStop { position: 0; color: "#EAF1FF" }
                                        GradientStop { position: 1; color: "#F0EAFE" }
                                    }
                                    Text { anchors.centerIn: parent; text: "+"; color: Theme.primary; font.family: Theme.semiBold; font.pixelSize: 28 }
                                    SequentialAnimation on scale {
                                        loops: Animation.Infinite
                                        NumberAnimation { to: 1.045; duration: 1600; easing.type: Easing.InOutSine }
                                        NumberAnimation { to: 1; duration: 1600; easing.type: Easing.InOutSine }
                                    }
                                }
                                Text { anchors.horizontalCenter: parent.horizontalCenter; text: "Build a sequence that feels effortless"; color: Theme.ink; font.family: Theme.bold; font.pixelSize: 19; font.weight: Font.Bold }
                                Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap; text: "Add keys, clicks, scrolling, text, or drag actions. Then tune timing in the inspector."; color: Theme.ink2; font.family: Theme.regular; font.pixelSize: 12; lineHeight: 1.25 }
                                KButton {
                                    objectName: "createFirstAction"
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    text: "Create first action"
                                    leading: "+"
                                     primary: true
                                     implicitWidth: 164
                                     onClicked: root.beginNewAction()
                                 }
                            }

                            ListView {
                                id: actionList
                                objectName: "actionList"
                                visible: count > 0
                                anchors.fill: parent
                                anchors.margins: 14
                                spacing: 6
                                clip: true
                                model: controller.actionModel
                                boundsBehavior: Flickable.StopAtBounds
                                ScrollBar.vertical: KScrollBar {
                                    id: sequenceScrollBar
                                    objectName: "sequenceScrollBar"
                                }
                                delegate: Rectangle {
                                    id: actionCard
                                    objectName: "actionCard"
                                    required property string title
                                    required property string subtitle
                                    required property bool actionEnabled
                                    required property int actionIndex
                                    required property string actionIcon
                                    width: ListView.view.width
                                           - (sequenceScrollBar.visible ? sequenceScrollBar.width + 8 : 0)
                                    height: 76
                                    color: "transparent"
                                    border.width: 0
                                    z: reorderDrag.active ? 20 : 0
                                    HoverHandler { id: hover }

                                    Rectangle {
                                        id: dropIndicator
                                        objectName: "sequenceDropIndicator_" + actionCard.actionIndex
                                        visible: root.draggedActionIndex >= 0
                                              && root.draggedActionIndex !== actionCard.actionIndex
                                              && root.dragTargetIndex === actionCard.actionIndex
                                        z: 30
                                        x: 46
                                        y: root.draggedActionIndex < actionCard.actionIndex ? actionCard.height - height : 0
                                        width: actionCard.width - x
                                        height: 3
                                        radius: 2
                                        color: Theme.primary
                                        Rectangle {
                                            width: 9
                                            height: 9
                                            radius: 5
                                            anchors.left: parent.left
                                            anchors.verticalCenter: parent.verticalCenter
                                            color: Theme.primary
                                        }
                                    }

                                    Rectangle {
                                        id: sequenceConnector
                                        objectName: "sequenceConnector"
                                        visible: actionCard.actionIndex < actionList.count - 1
                                        width: 2
                                        x: stepBadge.x + stepBadge.width / 2 - width / 2
                                        y: stepBadge.y + stepBadge.height + 2
                                        height: actionCard.height - stepBadge.height + actionList.spacing - 2
                                        radius: 1
                                        color: Theme.line
                                    }

                                    Rectangle {
                                        id: stepBadge
                                        objectName: "stepBadge"
                                        width: 32
                                        height: 32
                                        radius: 10
                                        anchors.left: parent.left
                                        anchors.verticalCenter: parent.verticalCenter
                                        opacity: actionCard.actionEnabled ? 1 : 0.55
                                        color: controller.runningActionIndex === actionCard.actionIndex ? Theme.green : controller.selectedIndex === actionCard.actionIndex ? Theme.primary : hover.hovered ? Theme.primarySoft : Theme.surface2
                                        border.width: controller.runningActionIndex === actionCard.actionIndex || controller.selectedIndex === actionCard.actionIndex ? 0 : 1
                                        border.color: hover.hovered ? "#B8CCF5" : Theme.line
                                        Behavior on opacity { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
                                        Behavior on color { ColorAnimation { duration: 120 } }
                                        Behavior on border.color { ColorAnimation { duration: 120 } }
                                        Text {
                                            anchors.centerIn: parent
                                            text: String(actionCard.actionIndex + 1).padStart(2, "0")
                                            color: controller.runningActionIndex === actionCard.actionIndex || controller.selectedIndex === actionCard.actionIndex ? "white" : Theme.primary
                                            font.family: Theme.semiBold
                                            font.pixelSize: 10
                                            font.letterSpacing: 0.35
                                        }
                                    }

                                    TapHandler {
                                        id: tap
                                        enabled: !controller.running
                                        onTapped: {
                                            if (controller.actionCaptureMode !== "")
                                                controller.cancelActionCapture()
                                            if (controller.capturePending)
                                                controller.cancelPositionCapture()
                                            controller.selectedIndex = actionCard.actionIndex
                                            root.activeInspectorTab = 0
                                            root.inspectorOpen = true
                                        }
                                    }

                                    Rectangle {
                                        id: actionCardSurface
                                        objectName: "actionCardSurface"
                                        anchors.left: parent.left
                                        anchors.leftMargin: 46
                                        anchors.right: parent.right
                                        anchors.verticalCenter: parent.verticalCenter
                                        height: 66
                                        radius: 14
                                        color: tap.pressed ? "#DEE9FF" : controller.runningActionIndex === actionCard.actionIndex ? Theme.successSoft : controller.selectedIndex === actionCard.actionIndex ? "#EDF3FF" : hover.hovered ? "#F4F7FF" : Theme.surface
                                        border.width: controller.selectedIndex === actionCard.actionIndex ? 2 : 1
                                        border.color: reorderDrag.active ? Theme.primary : controller.runningActionIndex === actionCard.actionIndex ? Theme.green : controller.selectedIndex === actionCard.actionIndex ? Theme.primary : hover.hovered ? "#B8CCF5" : Theme.line
                                        scale: reorderDrag.active ? 1.015 : tap.pressed ? 0.995 : 1
                                        transformOrigin: Item.Center
                                        transform: Translate { y: reorderDrag.active ? reorderDrag.translation.y : 0 }
                                        Behavior on color { ColorAnimation { duration: 120 } }
                                        Behavior on border.color { ColorAnimation { duration: 120 } }
                                        Behavior on scale { NumberAnimation { duration: 90 } }

                                        RowLayout {
                                            anchors.fill: parent
                                            anchors.leftMargin: 12
                                            anchors.rightMargin: 10
                                            spacing: 10

                                            RowLayout {
                                                id: actionContent
                                                objectName: "actionContent_" + actionCard.actionIndex
                                                Layout.fillWidth: true
                                                spacing: 10
                                                opacity: actionCard.actionEnabled ? 1 : 0.42
                                                Behavior on opacity { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }

                                                Rectangle {
                                                    Layout.preferredWidth: 36
                                                    Layout.preferredHeight: 36
                                                    radius: 11
                                                    color: controller.selectedIndex === actionCard.actionIndex ? Theme.surface : Theme.primarySoft
                                                    border.width: controller.selectedIndex === actionCard.actionIndex ? 1 : 0
                                                    border.color: "#C6D8FC"
                                                    Text {
                                                        anchors.centerIn: parent
                                                        text: actionCard.actionIcon
                                                        color: Theme.primary
                                                        font.family: Theme.bold
                                                        font.pixelSize: actionCard.actionIcon.length > 1 ? 10 : 14
                                                    }
                                                }

                                                ColumnLayout {
                                                    Layout.fillWidth: true
                                                    spacing: 3
                                                    RowLayout {
                                                        Layout.fillWidth: true
                                                        Text {
                                                            Layout.fillWidth: true
                                                            text: actionCard.title
                                                            elide: Text.ElideRight
                                                            color: Theme.ink
                                                            font.family: Theme.semiBold
                                                            font.pixelSize: 13
                                                        }
                                                        Rectangle {
                                                            objectName: "editingBadge"
                                                            visible: controller.runningActionIndex === actionCard.actionIndex || controller.selectedIndex === actionCard.actionIndex
                                                            implicitWidth: editingLabel.implicitWidth + 14
                                                            implicitHeight: 20
                                                            radius: 7
                                                            color: controller.runningActionIndex === actionCard.actionIndex ? Theme.green : Theme.primary
                                                            Text {
                                                                id: editingLabel
                                                                anchors.centerIn: parent
                                                                text: controller.runningActionIndex === actionCard.actionIndex ? "RUNNING" : "EDITING"
                                                                color: "white"
                                                                font.family: Theme.semiBold
                                                                font.pixelSize: 8
                                                                font.letterSpacing: 0.5
                                                            }
                                                        }
                                                    }
                                                    Text {
                                                        Layout.fillWidth: true
                                                        text: actionCard.subtitle
                                                        elide: Text.ElideRight
                                                        color: Theme.ink3
                                                        font.family: Theme.regular
                                                        font.pixelSize: 11
                                                    }
                                                }
                                            }

                                            Rectangle {
                                                id: actionDragHandle
                                                objectName: "actionDragHandle_" + actionCard.actionIndex
                                                Layout.preferredWidth: 32
                                                Layout.preferredHeight: 36
                                                radius: 10
                                                opacity: actionList.count > 1 && !controller.running ? 1 : 0.35
                                                color: reorderDrag.active ? Theme.primarySoft : dragHover.hovered ? Theme.surface3 : "transparent"
                                                border.width: reorderDrag.active ? 1 : 0
                                                border.color: "#B8CCF5"
                                                HoverHandler {
                                                    id: dragHover
                                                    cursorShape: reorderDrag.active ? Qt.ClosedHandCursor : Qt.OpenHandCursor
                                                }

                                                Grid {
                                                    anchors.centerIn: parent
                                                    columns: 2
                                                    spacing: 3
                                                    Repeater {
                                                        model: 6
                                                        Rectangle {
                                                            width: 3
                                                            height: 3
                                                            radius: 2
                                                            color: reorderDrag.active ? Theme.primary : Theme.ink3
                                                        }
                                                    }
                                                }

                                                DragHandler {
                                                    id: reorderDrag
                                                    enabled: actionList.count > 1 && !controller.running
                                                    target: null
                                                    xAxis.enabled: false
                                                    onActiveChanged: {
                                                        if (active) {
                                                            root.beginSequenceDrag(actionCard.actionIndex)
                                                            root.updateSequenceDrag(actionCard.actionIndex, translation.y)
                                                        } else {
                                                            root.finishSequenceDrag(actionCard.actionIndex)
                                                        }
                                                    }
                                                    onTranslationChanged: {
                                                        if (active)
                                                            root.updateSequenceDrag(actionCard.actionIndex, translation.y)
                                                    }
                                                }
                                            }

                                            Switch {
                                                id: enabledSwitch
                                                objectName: "actionEnabledSwitch_" + actionCard.actionIndex
                                                Layout.preferredWidth: 42
                                                Layout.preferredHeight: 32
                                                enabled: !controller.running
                                                checked: actionCard.actionEnabled
                                                onToggled: controller.setActionEnabled(actionCard.actionIndex, checked)
                                                contentItem: Item {}
                                                indicator: Rectangle {
                                                    id: actionToggleTrack
                                                    objectName: "actionToggleTrack_" + actionCard.actionIndex
                                                    width: 38
                                                    height: 22
                                                    radius: 11
                                                    anchors.centerIn: parent
                                                    clip: true
                                                    color: enabledSwitch.checked ? Theme.primary : "#CAD1DC"
                                                    scale: enabledSwitch.down ? 0.96 : 1
                                                    transformOrigin: Item.Center
                                                    Behavior on color {
                                                        ColorAnimation { duration: 170; easing.type: Easing.OutCubic }
                                                    }
                                                    Behavior on scale {
                                                        NumberAnimation { duration: 90; easing.type: Easing.OutCubic }
                                                    }
                                                    Rectangle {
                                                        id: actionToggleKnob
                                                        objectName: "actionToggleKnob_" + actionCard.actionIndex
                                                        width: 18; height: 18; radius: 9; y: 2
                                                        x: enabledSwitch.checked ? 18 : 2
                                                        color: "white"
                                                        scale: enabledSwitch.down ? 0.88 : 1
                                                        transformOrigin: Item.Center
                                                        Behavior on x {
                                                            NumberAnimation {
                                                                duration: 190
                                                                easing.type: Easing.OutBack
                                                                easing.overshoot: 1.25
                                                            }
                                                        }
                                                        Behavior on scale {
                                                            NumberAnimation { duration: 90; easing.type: Easing.OutCubic }
                                                        }
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                Pages.ProfilesPage {
                    app: root
                }

                Pages.RunnerPage {
                    app: root
                }
            }
        }

        Rectangle {
            id: runBar
            objectName: "runBar"
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.leftMargin: root.layoutMode === "wide" ? 28 : 22
            anchors.rightMargin: root.layoutMode === "wide" ? 28 : 22
            anchors.bottomMargin: 18
            height: 82
            z: 11
            radius: 18
            color: Theme.surface
            border.width: 1
            border.color: Theme.line
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 16
                anchors.rightMargin: 12
                spacing: 10
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 4
                    FormLabel { text: "RUN STATUS" }
                    Text {
                        objectName: "runStatusMessage"
                        Layout.fillWidth: true
                        text: controller.capturePending ? "Pick a point on the frozen screen · Esc cancels" : controller.running ? controller.status : controller.preflightBlocked ? controller.preflightSummary : controller.canRun ? "Ready when you are" : (actionList.count > 0 ? "Enable an action to begin" : "Add an action to begin")
                        elide: Text.ElideRight
                        color: controller.preflightBlocked && !controller.running ? Theme.red : Theme.ink2
                        font.family: Theme.medium
                        font.pixelSize: 12
                    }
                    Item {
                        id: runProgressTrack
                        objectName: "runProgressTrack"
                        visible: controller.running
                        Layout.fillWidth: true
                        Layout.maximumWidth: 220
                        Layout.preferredHeight: 6
                        Rectangle { anchors.fill: parent; radius: 3; color: Theme.surface3 }
                        Rectangle {
                            height: parent.height; radius: 3; color: Theme.primary
                            width: controller.progress < 0 ? 34 : parent.width * Math.max(0, Math.min(1, controller.progress))
                            x: 0
                            SequentialAnimation on x {
                                running: controller.progress < 0
                                loops: Animation.Infinite
                                NumberAnimation { from: 0; to: Math.max(0, runProgressTrack.width - 34); duration: 760; easing.type: Easing.InOutCubic }
                                NumberAnimation { from: Math.max(0, runProgressTrack.width - 34); to: 0; duration: 760; easing.type: Easing.InOutCubic }
                            }
                            Behavior on width { NumberAnimation { duration: 180 } }
                        }
                    }
                }
                Rectangle {
                    id: shortcutDock
                    objectName: "shortcutDock"
                    visible: root.width >= 1000
                    Layout.preferredWidth: shortcutDockRow.implicitWidth + 26
                    Layout.preferredHeight: 50
                    radius: 15
                    color: "#F7F8FB"
                    border.width: 1
                    border.color: "#E2E6ED"
                    HoverHandler { id: shortcutDockHover }
                    Row {
                        id: shortcutDockRow
                        anchors.centerIn: parent
                        spacing: 14
                        Repeater {
                            model: [
                                {key: controller.runSettings.startHotkey, label: "Start"},
                                {key: controller.runSettings.captureHotkey, label: "Record"},
                                {key: controller.runSettings.stopHotkey, label: "Stop"}
                            ]
                            delegate: Row {
                                required property var modelData
                                required property int index
                                objectName: "shortcutHint_" + index
                                readonly property string keyText: modelData.key
                                readonly property string labelText: modelData.label
                                spacing: 7
                                KeyCap {
                                    anchors.verticalCenter: parent.verticalCenter
                                    keyText: modelData.key
                                }
                                Text {
                                    // Below the wide breakpoint the key caps speak for themselves.
                                    visible: root.layoutMode === "wide"
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: modelData.label
                                    color: Theme.ink2
                                    font.family: Theme.medium
                                    font.pixelSize: 11
                                }
                            }
                        }
                    }
                }
                Rectangle {
                    id: runControlGroup
                    objectName: "runControlGroup"
                    Layout.preferredWidth: root.layoutMode === "compact" ? 280 : 288
                    Layout.preferredHeight: 50
                    radius: 15
                    color: "#F3F6FA"
                    border.width: 1
                    border.color: "#E1E6EE"
                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 4
                        spacing: 4
                        KButton {
                            objectName: "runStopButton"
                            Layout.preferredWidth: 112
                            Layout.fillHeight: true
                            text: "Stop"
                            leading: "■"
                            keyHint: controller.runSettings.stopHotkey
                            danger: true
                            enabled: controller.running
                            onClicked: controller.stopRun()
                        }
                        KButton {
                            objectName: "runStartButton"
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            text: controller.running ? "Running" : runForm.shortcutValidation.hasConflict ? "Fix shortcuts" : controller.preflightBlocked ? "Not ready" : controller.runSettingsPending ? "Apply & start" : "Start"
                            leading: controller.running ? "●" : "▶"
                            keyHint: controller.runSettings.startHotkey
                            primary: true
                            enabled: !controller.running && controller.canRun && !controller.preflightBlocked && !runForm.shortcutValidation.hasConflict
                            onClicked: controller.startRunWithSettings(runForm.payload())
                        }
                    }
                }
            }
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

        Rectangle {
            id: inspector
            objectName: "runInspector"
            visible: root.inspectorVisible
            width: root.layoutMode === "wide" ? 368 : root.layoutMode === "medium" ? 340 : Math.min(380, root.width - 84)
            x: root.overlayInspector ? (root.inspectorOpen ? root.width - width : root.width + 8) : root.width - width
            anchors.top: appHeader.bottom
            anchors.bottom: runBar.top
            anchors.bottomMargin: 12
            color: "#FCFCFE"
            z: 10
            clip: true
            border.width: root.overlayInspector ? 1 : 0
            border.color: Theme.line
            Behavior on x { NumberAnimation { duration: 230; easing.type: Easing.OutCubic } }
            Behavior on width { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }

            ColumnLayout {
                anchors.fill: parent
                anchors.leftMargin: 18
                anchors.rightMargin: 18
                anchors.topMargin: 20
                anchors.bottomMargin: 16
                spacing: 12

                RowLayout {
                    Layout.fillWidth: true
                    Text { Layout.fillWidth: true; text: "Inspector"; color: Theme.ink; font.family: Theme.bold; font.pixelSize: 20; font.weight: Font.Bold }
                    KButton { visible: root.overlayInspector; text: ""; leading: "×"; quiet: true; implicitWidth: 38; onClicked: root.inspectorOpen = false }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 40
                    radius: 12
                    color: Theme.surface2
                    Rectangle {
                        id: tabSelectionPill
                        objectName: "tabSelectionPill"
                        x: 3 + root.activeInspectorTab * width
                        y: 3
                        width: (parent.width - 6) / 2
                        height: parent.height - 6
                        radius: 9
                        color: Theme.surface
                        layer.enabled: true
                        layer.effect: MultiEffect {
                            shadowEnabled: true
                            shadowColor: "#200B1730"
                            shadowBlur: 0.42
                            shadowVerticalOffset: 2
                        }
                        Behavior on x {
                            NumberAnimation {
                                duration: 240
                                easing.type: Easing.OutCubic
                            }
                        }
                    }
                    Row {
                        anchors.fill: parent
                        anchors.margins: 3
                        Repeater {
                            model: ["Action", "Run"]
                            delegate: Rectangle {
                                required property string modelData
                                required property int index
                                width: (parent.width) / 2
                                height: parent.height
                                radius: 9
                                color: "transparent"
                                Text { anchors.centerIn: parent; text: modelData; color: root.activeInspectorTab === index ? Theme.ink : Theme.ink3; font.family: Theme.semiBold; font.pixelSize: 12 }
                                TapHandler { onTapped: root.activeInspectorTab = index }
                            }
                        }
                    }
                }

                StackLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    currentIndex: root.activeInspectorTab

                    Flickable {
                        id: editorFlick
                        contentHeight: editor.implicitHeight
                        clip: true
                        boundsBehavior: Flickable.StopAtBounds
                        ScrollBar.vertical: KScrollBar { objectName: "editorScrollBar" }

                        ColumnLayout {
                            id: editor
                            width: editorFlick.width - 18
                            spacing: 7
                            enabled: !controller.running
                            property bool mouseAction: ["left_click", "right_click", "double_click", "middle_click", "scroll", "drag"].indexOf(kindValue()) >= 0
                            property bool clickAction: ["left_click", "right_click", "double_click", "middle_click"].indexOf(kindValue()) >= 0
                            property string coordinateSpace: "screen"
                            property int referenceWidth: 0
                            property int referenceHeight: 0
                            property int referenceWidth2: 0
                            property int referenceHeight2: 0
                            property bool desktopTarget: controller.targetSettings.mode === "desktop"
                            // Each target mode records positions in its own space.
                            readonly property string expectedSpace: controller.targetSettings.mode === "desktop"
                                                                    ? "screen"
                                                                    : controller.targetSettings.mode === "browser"
                                                                      ? "viewport"
                                                                      : "window"
                            // A follow-pointer click has no recorded position, so it can never
                            // belong to the wrong target and never needs recording again.
                            property bool followingPointer: clickAction && followPointerSwitch.checked && desktopTarget
                            property bool needsPointerPosition: mouseAction && !followingPointer
                            // A mouse action whose position was never recorded or typed
                            // silently ends up at (0, 0) -- the corner of the target,
                            // which looks like "the automation does nothing".
                            property bool pointerProvided: false
                            readonly property bool pointerMissing: needsPointerPosition && !pointerProvided
                            property bool targetMismatch: mouseAction && !followingPointer && coordinateSpace !== expectedSpace

                            function kindValue() {
                                var values = ["key", "hotkey", "text", "left_click", "right_click", "double_click", "middle_click", "scroll", "drag"]
                                return values[actionType.currentIndex]
                            }
                            function reset() {
                                root.editorIndex = -1
                                actionType.currentIndex = 0
                                valueField.text = "space"
                                xField.text = "0"; yField.text = "0"; x2Field.text = "0"; y2Field.text = "0"
                                amountField.text = "-3"; durationField.text = "0.4"; repeatsField.text = "1"; delayField.text = "0.10"
                                followPointerSwitch.checked = false
                                coordinateSpace = expectedSpace
                                referenceWidth = 0
                                referenceHeight = 0
                                referenceWidth2 = 0
                                referenceHeight2 = 0
                                pointerProvided = false
                            }
                            function loadAction(index) {
                                var a = controller.actionAt(index)
                                var kinds = ["key", "hotkey", "text", "left_click", "right_click", "double_click", "middle_click", "scroll", "drag"]
                                actionType.currentIndex = Math.max(0, kinds.indexOf(a.kind))
                                valueField.text = a.value || ""
                                xField.text = a.x === undefined || a.x === null ? "0" : a.x
                                yField.text = a.y === undefined || a.y === null ? "0" : a.y
                                x2Field.text = a.x2 === undefined || a.x2 === null ? "0" : a.x2
                                y2Field.text = a.y2 === undefined || a.y2 === null ? "0" : a.y2
                                amountField.text = a.amount || -3
                                durationField.text = a.duration === undefined || a.duration === null ? 0.4 : a.duration
                                repeatsField.text = a.repeats || 1
                                delayField.text = a.delay === undefined ? 0.1 : a.delay
                                followPointerSwitch.checked = a.use_current_pointer || false
                                coordinateSpace = a.coordinate_space || "screen"
                                referenceWidth = a.reference_width || 0
                                referenceHeight = a.reference_height || 0
                                referenceWidth2 = a.reference_width2 || 0
                                referenceHeight2 = a.reference_height2 || 0
                                pointerProvided = true
                            }
                            function payload() {
                                // Following the pointer drops the recorded position entirely, so the
                                // action becomes a plain Desktop action no matter where it was recorded.
                                return {kind: kindValue(), value: valueField.text, x: xField.text, y: yField.text, x2: x2Field.text, y2: y2Field.text, amount: amountField.text, duration: durationField.text, repeats: repeatsField.text, delay: delayField.text, enabled: true, useCurrentPointer: followingPointer, coordinateSpace: followingPointer ? "screen" : coordinateSpace, referenceWidth: followingPointer ? 0 : referenceWidth, referenceHeight: followingPointer ? 0 : referenceHeight, referenceWidth2: followingPointer ? 0 : referenceWidth2, referenceHeight2: followingPointer ? 0 : referenceHeight2}
                            }
                            Component.onCompleted: reset()

                            KButton { Layout.fillWidth: true; text: root.editorIndex >= 0 ? "Editing action " + (root.editorIndex + 1) : "New action"; leading: root.editorIndex >= 0 ? "✦" : "+"; onClicked: root.beginNewAction() }
                            FormLabel { text: "ACTION TYPE"; Layout.topMargin: 6 }
                            ComboBox {
                                id: actionType
                                objectName: "actionTypePicker"
                                Layout.fillWidth: true
                                implicitHeight: 44
                                model: ["Key press", "Hotkey", "Type text", "Left click", "Right click", "Double click", "Middle click", "Scroll", "Drag"]
                                font.family: Theme.medium
                                font.pixelSize: 13
                                leftPadding: 13
                                rightPadding: 42
                                onCurrentIndexChanged: {
                                    if (controller.actionCaptureMode !== "")
                                        controller.cancelActionCapture()
                                }
                                contentItem: Text {
                                    text: actionType.displayText
                                    color: Theme.ink
                                    font: actionType.font
                                    verticalAlignment: Text.AlignVCenter
                                    elide: Text.ElideRight
                                }
                                indicator: Text {
                                    x: actionType.width - width - 14
                                    y: (actionType.height - height) / 2
                                    text: "⌄"
                                    color: Theme.ink2
                                    font.family: Theme.semiBold
                                    font.pixelSize: 20
                                    rotation: actionType.popup.visible ? 180 : 0
                                    Behavior on rotation { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
                                }
                                background: Rectangle {
                                    radius: 11
                                    color: actionType.hovered || actionType.activeFocus ? "#FFFFFF" : "#F8F9FC"
                                    border.width: actionType.activeFocus || actionType.popup.visible ? 2 : 1
                                    border.color: actionType.activeFocus || actionType.popup.visible ? Theme.primary : actionType.hovered ? "#BFC9D8" : Theme.line
                                    Behavior on color { ColorAnimation { duration: 120 } }
                                    Behavior on border.color { ColorAnimation { duration: 120 } }
                                }
                                delegate: ItemDelegate {
                                    id: option
                                    required property var modelData
                                    required property int index
                                    width: actionType.width - 12
                                    height: 40
                                    leftPadding: 12
                                    highlighted: actionType.highlightedIndex === index
                                    contentItem: Text {
                                        text: option.modelData
                                        color: option.highlighted ? Theme.primary : Theme.ink
                                        font.family: option.highlighted ? interSemiBold.name : interMedium.name
                                        font.pixelSize: 13
                                        verticalAlignment: Text.AlignVCenter
                                    }
                                    background: Rectangle {
                                        radius: 9
                                        color: option.highlighted ? Theme.primarySoft : option.hovered ? "#F1F4F9" : "#00F1F4F9"
                                        Behavior on color { ColorAnimation { duration: 100 } }
                                    }
                                    onClicked: {
                                        actionType.currentIndex = index
                                        actionType.popup.close()
                                    }
                                }
                                popup: Popup {
                                    objectName: "actionTypePopup"
                                    x: 0
                                    y: actionType.height + 6
                                    z: 100
                                    width: actionType.width
                                    implicitHeight: Math.min(contentItem.implicitHeight + 12, 380)
                                    padding: 6
                                    clip: true
                                    contentItem: ListView {
                                        clip: true
                                        implicitHeight: contentHeight
                                        model: actionType.popup.visible ? actionType.delegateModel : null
                                        currentIndex: actionType.highlightedIndex
                                        boundsBehavior: Flickable.StopAtBounds
                                        ScrollIndicator.vertical: ScrollIndicator {}
                                    }
                                    background: Rectangle {
                                        radius: 14
                                        color: Theme.surface
                                        border.width: 1
                                        border.color: Theme.line
                                    }
                                }
                            }

                            FormLabel { visible: !editor.mouseAction; text: editor.kindValue() === "text" ? "TEXT TO TYPE" : "KEY OR SHORTCUT"; Layout.topMargin: 7 }
                            KField { id: valueField; objectName: "actionValueField"; visible: !editor.mouseAction; Layout.fillWidth: true; placeholderText: editor.kindValue() === "hotkey" ? "ctrl+shift+s" : editor.kindValue() === "text" ? "Type something…" : "space" }
                            KButton {
                                objectName: "recordActionKey"
                                visible: editor.kindValue() === "key"
                                Layout.fillWidth: true
                                text: controller.actionCaptureMode === "key"
                                      ? "Cancel key recording"
                                      : "Listen for a key"
                                leading: controller.actionCaptureMode === "key" ? "×" : "⌨"
                                activeNeutral: controller.actionCaptureMode === "key"
                                onClicked: {
                                    if (controller.actionCaptureMode === "key")
                                        controller.cancelActionCapture()
                                    else
                                        controller.recordActionKey()
                                }
                            }
                            KButton {
                                objectName: "recordActionHotkey"
                                visible: editor.kindValue() === "hotkey"
                                Layout.fillWidth: true
                                text: controller.actionCaptureMode === "hotkey"
                                      ? "Cancel hotkey recording"
                                      : "Record hotkey"
                                leading: controller.actionCaptureMode === "hotkey" ? "×" : "⌘"
                                activeNeutral: controller.actionCaptureMode === "hotkey"
                                onClicked: {
                                    if (controller.actionCaptureMode === "hotkey")
                                        controller.cancelActionCapture()
                                    else
                                        controller.recordActionHotkey()
                                }
                            }

                            Rectangle {
                                visible: editor.clickAction && editor.desktopTarget
                                Layout.fillWidth: true
                                Layout.preferredHeight: visible ? 58 : 0
                                radius: 13
                                color: Theme.surface2
                                RowLayout {
                                    anchors.fill: parent
                                    anchors.leftMargin: 13
                                    anchors.rightMargin: 10
                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: 2
                                        Text { text: "Follow current pointer"; color: Theme.ink; font.family: Theme.semiBold; font.pixelSize: 12 }
                                        Text { text: "Click wherever the pointer is during the run"; color: Theme.ink3; font.family: Theme.regular; font.pixelSize: 9 }
                                    }
                                    Switch { id: followPointerSwitch; objectName: "followPointerSwitch" }
                                }
                            }

                            Rectangle {
                                visible: editor.targetMismatch
                                Layout.fillWidth: true
                                Layout.preferredHeight: visible ? 62 : 0
                                radius: 12
                                color: Theme.redSoft
                                border.width: 1
                                border.color: "#F2C8D0"
                                Text {
                                    anchors.fill: parent
                                    anchors.margins: 11
                                    wrapMode: Text.WordWrap
                                    text: "This position was recorded for a different target. Record it again for "
                                        + (editor.expectedSpace === "screen"
                                           ? "Desktop mode"
                                           : editor.expectedSpace === "viewport"
                                             ? "the selected browser tab"
                                             : "the selected window")
                                        + " before saving or running."
                                    color: Theme.red
                                    font.family: Theme.medium
                                    font.pixelSize: 10
                                    lineHeight: 1.2
                                }
                            }

                            FormLabel { visible: editor.needsPointerPosition; text: editor.kindValue() === "drag" ? "DRAG START POSITION" : editor.desktopTarget ? "SCREEN POSITION" : "WINDOW POSITION"; Layout.topMargin: 7 }
                            RowLayout {
                                visible: editor.needsPointerPosition
                                Layout.fillWidth: true
                                KField {
                                    id: xField
                                    Layout.fillWidth: true
                                    placeholderText: "X"
                                    inputMethodHints: Qt.ImhDigitsOnly
                                    onTextEdited: editor.pointerProvided = true
                                }
                                KField {
                                    id: yField
                                    Layout.fillWidth: true
                                    placeholderText: "Y"
                                    inputMethodHints: Qt.ImhDigitsOnly
                                    onTextEdited: editor.pointerProvided = true
                                }
                            }
                            KButton {
                                objectName: "recordPointerPosition"
                                visible: editor.needsPointerPosition
                                Layout.fillWidth: true
                                text: controller.capturePending && controller.captureTarget === 0 ? "Cancel point picker" : editor.kindValue() === "drag" ? "Pick start position" : "Pick pointer position"
                                leading: controller.capturePending && controller.captureTarget === 0 ? "×" : "⌖"
                                activeNeutral: controller.capturePending && controller.captureTarget === 0
                                enabled: !controller.capturePending || controller.captureTarget === 0
                                onClicked: {
                                    if (controller.capturePending) controller.cancelPositionCapture()
                                    else controller.startPositionCapture(0)
                                }
                            }
                            Text {
                                visible: editor.needsPointerPosition
                                Layout.fillWidth: true
                                wrapMode: Text.WordWrap
                                text: controller.capturePending ? "Choose a point on the frozen screen, or press Esc to cancel." : editor.desktopTarget ? "KeyClick hides, freezes and dims the screen so you can choose the exact point without rushing." : "Choose the point on a frozen screen. It will scale with the selected window when that window is resized."
                                color: controller.capturePending ? Theme.primary : Theme.ink3
                                font.family: Theme.regular
                                font.pixelSize: 10
                                lineHeight: 1.2
                            }

                            FormLabel { visible: editor.kindValue() === "drag"; text: "DRAG DESTINATION"; Layout.topMargin: 7 }
                            RowLayout {
                                visible: editor.kindValue() === "drag"
                                Layout.fillWidth: true
                                KField { id: x2Field; Layout.fillWidth: true; placeholderText: "X"; inputMethodHints: Qt.ImhDigitsOnly }
                                KField { id: y2Field; Layout.fillWidth: true; placeholderText: "Y"; inputMethodHints: Qt.ImhDigitsOnly }
                            }
                            KButton {
                                objectName: "recordDragDestination"
                                visible: editor.kindValue() === "drag"
                                Layout.fillWidth: true
                                text: controller.capturePending && controller.captureTarget === 1 ? "Cancel point picker" : "Pick destination"
                                leading: controller.capturePending && controller.captureTarget === 1 ? "×" : "⌖"
                                activeNeutral: controller.capturePending && controller.captureTarget === 1
                                enabled: !controller.capturePending || controller.captureTarget === 1
                                onClicked: {
                                    if (controller.capturePending) controller.cancelPositionCapture()
                                    else controller.startPositionCapture(1)
                                }
                            }

                            FormLabel { visible: editor.kindValue() === "scroll"; text: "SCROLL STEPS"; Layout.topMargin: 7 }
                            KField { id: amountField; visible: editor.kindValue() === "scroll"; Layout.fillWidth: true; placeholderText: "-3" }
                            FormLabel { visible: editor.kindValue() === "drag"; text: "DRAG DURATION"; Layout.topMargin: 7 }
                            KField { id: durationField; visible: editor.kindValue() === "drag"; Layout.fillWidth: true; placeholderText: "0.4" }

                            FormLabel { text: "ACTION BEHAVIOR"; Layout.topMargin: 9 }
                            RowLayout {
                                Layout.fillWidth: true
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 4
                                    Text { text: "Repeats"; color: Theme.ink2; font.pixelSize: 11; font.family: Theme.medium }
                                    KField { id: repeatsField; Layout.fillWidth: true; text: "1" }
                                }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 4
                                    Text { text: "Wait after"; color: Theme.ink2; font.pixelSize: 11; font.family: Theme.medium }
                                    KField { id: delayField; Layout.fillWidth: true; text: "0.10" }
                                }
                            }
                            RowLayout {
                                visible: root.editorIndex >= 0
                                Layout.fillWidth: true
                                Layout.topMargin: visible ? 7 : 0
                                KButton {
                                    objectName: "inspectorTestActionButton"
                                    Layout.fillWidth: true
                                    text: "Test once"
                                    leading: "1×"
                                    enabled: !editor.targetMismatch
                                    onClicked: controller.testActionWithSettings(root.editorIndex, runForm.payload())
                                }
                                KButton {
                                    objectName: "inspectorRunFromButton"
                                    Layout.fillWidth: true
                                    text: "Run from here"
                                    leading: "▶"
                                    enabled: !editor.targetMismatch
                                    onClicked: controller.startRunFromWithSettings(root.editorIndex, runForm.payload())
                                }
                            }
                            Rectangle {
                                objectName: "pointerMissingNotice"
                                visible: editor.pointerMissing
                                Layout.fillWidth: true
                                Layout.topMargin: visible ? 8 : 0
                                Layout.preferredHeight: visible ? 54 : 0
                                radius: 12
                                color: Theme.primarySoft
                                border.width: 1
                                border.color: "#B9CEFA"
                                Text {
                                    anchors.fill: parent
                                    anchors.margins: 11
                                    wrapMode: Text.WordWrap
                                    text: "Record where this should happen first. Without a position "
                                        + "the action lands at the target's top-left corner."
                                    color: Theme.primary
                                    font.family: Theme.medium
                                    font.pixelSize: 11
                                }
                            }
                            KButton {
                                objectName: "actionCommitButton"
                                Layout.fillWidth: true
                                Layout.topMargin: 10
                                implicitHeight: 48
                                primary: true
                                enabled: !editor.targetMismatch && !editor.pointerMissing
                                text: root.editorIndex >= 0 ? "Update action" : "Add to sequence"
                                leading: root.editorIndex >= 0 ? "✓" : "+"
                                onClicked: {
                                    if (root.editorIndex >= 0) {
                                        controller.updateAction(root.editorIndex, editor.payload())
                                    } else {
                                        if (controller.addAction(editor.payload())) {
                                            controller.selectedIndex = -1
                                            editor.reset()
                                        }
                                    }
                                }
                            }
                            Item { Layout.preferredHeight: 12 }
                        }
                    }

                    Flickable {
                        id: runFlick
                        objectName: "runSettingsFlick"
                        contentHeight: runForm.implicitHeight
                        clip: true
                        boundsBehavior: Flickable.StopAtBounds
                        ScrollBar.vertical: KScrollBar { objectName: "runSettingsScrollBar" }
                        ColumnLayout {
                            id: runForm
                            objectName: "runSettingsForm"
                            width: runFlick.width - 18
                            spacing: 7
                            enabled: !controller.running
                            readonly property var shortcutValidation: controller.globalShortcutConflicts(startHotkey.text, captureHotkey.text, stopHotkey.text)
                            readonly property string shortcutMessage: shortcutValidation.hasConflict ? shortcutValidation.message : root.shortcutCaptureError
                            function payload() {
                                return {repeatForever: foreverSwitch.checked, repeatCount: repeatCount.text, startDelay: startDelay.text, cycleInterval: cycleInterval.text, textInterval: textInterval.text, jitter: jitter.text, startHotkey: startHotkey.text, captureHotkey: captureHotkey.text, stopHotkey: stopHotkey.text}
                            }
                            function apply() {
                                return controller.applyRunSettings(payload())
                            }
                            FormLabel { text: "BEFORE YOU RUN" }
                            Rectangle {
                                objectName: "preflightPanel"
                                Layout.fillWidth: true
                                Layout.preferredHeight: preflightColumn.implicitHeight + 20
                                radius: 13
                                color: Theme.surface2
                                border.width: 1
                                border.color: Theme.line

                                ColumnLayout {
                                    id: preflightColumn
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.top: parent.top
                                    anchors.margins: 10
                                    spacing: 6

                                    Repeater {
                                        model: controller.preflightChecks
                                        delegate: RowLayout {
                                            required property var modelData
                                            required property int index
                                            objectName: "preflightCheck_" + index
                                            Layout.fillWidth: true
                                            spacing: 8

                                            Rectangle {
                                                Layout.alignment: Qt.AlignTop
                                                Layout.topMargin: 2
                                                width: 14; height: 14; radius: 7
                                                color: modelData.status === "fail" ? Theme.redSoft
                                                     : modelData.status === "warn" ? "#FFF3E0"
                                                     : Theme.successSoft
                                                Text {
                                                    anchors.centerIn: parent
                                                    text: modelData.status === "fail" ? "×"
                                                        : modelData.status === "warn" ? "!" : "✓"
                                                    color: modelData.status === "fail" ? Theme.red
                                                         : modelData.status === "warn" ? "#B26A00" : Theme.green
                                                    font.family: Theme.semiBold
                                                    font.pixelSize: 9
                                                }
                                            }
                                            ColumnLayout {
                                                Layout.fillWidth: true
                                                spacing: 1
                                                Text {
                                                    Layout.fillWidth: true
                                                    text: modelData.name + "  ·  " + modelData.detail
                                                    wrapMode: Text.WordWrap
                                                    color: modelData.status === "fail" ? Theme.red : Theme.ink2
                                                    font.family: Theme.medium
                                                    font.pixelSize: 10
                                                    lineHeight: 1.2
                                                }
                                                Text {
                                                    visible: modelData.remedy !== "" && modelData.status !== "pass"
                                                    Layout.fillWidth: true
                                                    text: modelData.remedy
                                                    wrapMode: Text.WordWrap
                                                    color: Theme.ink3
                                                    font.family: Theme.regular
                                                    font.pixelSize: 10
                                                    lineHeight: 1.2
                                                }
                                            }
                                        }
                                    }
                                }
                            }

                            FormLabel { text: "TARGET"; Layout.topMargin: 6 }
                            Text { text: "What should it automate?"; color: Theme.ink; font.family: Theme.bold; font.pixelSize: 17 }
                            Text {
                                Layout.fillWidth: true
                                wrapMode: Text.WordWrap
                                text: "Pick the thing you want automated. KeyClick works out how to reach it."
                                color: Theme.ink2
                                font.family: Theme.regular
                                font.pixelSize: 11
                                lineHeight: 1.25
                            }

                            Rectangle {
                                objectName: "chosenTargetPanel"
                                Layout.fillWidth: true
                                Layout.preferredHeight: 108
                                radius: 13
                                color: Theme.surface2
                                border.width: 1
                                border.color: Theme.line
                                ColumnLayout {
                                    anchors.fill: parent
                                    anchors.margins: 12
                                    spacing: 7
                                    FormLabel { text: "AUTOMATING" }
                                    Text {
                                        Layout.fillWidth: true
                                        objectName: "chosenTargetLabel"
                                        text: controller.targetSummary
                                        elide: Text.ElideMiddle
                                        color: Theme.ink
                                        font.family: Theme.semiBold
                                        font.pixelSize: 13
                                    }
                                    KButton {
                                        objectName: "chooseTargetButton"
                                        Layout.fillWidth: true
                                        text: "Change what it automates"
                                        leading: "◈"
                                        onClicked: root.openTargetPicker()
                                    }
                                }
                            }

                            FormLabel { text: "RUN PLAN" }
                            Text { text: "Choose when it stops"; color: Theme.ink; font.family: Theme.bold; font.pixelSize: 17 }
                            Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; text: "Run a fixed number of cycles or continue until you press Stop."; color: Theme.ink2; font.family: Theme.regular; font.pixelSize: 11; lineHeight: 1.25 }
                            Rectangle {
                                Layout.fillWidth: true; Layout.preferredHeight: 52; radius: 13; color: Theme.surface2
                                RowLayout {
                                    anchors.fill: parent
                                    anchors.leftMargin: 13
                                    anchors.rightMargin: 10
                                    Text { Layout.fillWidth: true; text: "Loop indefinitely"; color: Theme.ink; font.family: Theme.semiBold; font.pixelSize: 12 }
                                    Switch { id: foreverSwitch; checked: controller.runSettings.repeatForever; onToggled: controller.markRunSettingsPending() }
                                }
                            }
                            FormLabel { text: "REPEAT CYCLES"; Layout.topMargin: 7 }
                            KField { id: repeatCount; Layout.fillWidth: true; text: controller.runSettings.repeatCount; enabled: !foreverSwitch.checked; onTextEdited: controller.markRunSettingsPending() }
                            FormLabel { text: "START COUNTDOWN"; Layout.topMargin: 7 }
                            KField { id: startDelay; Layout.fillWidth: true; text: controller.runSettings.startDelay; onTextEdited: controller.markRunSettingsPending() }
                            FormLabel { text: "BETWEEN CYCLES"; Layout.topMargin: 7 }
                            KField { id: cycleInterval; Layout.fillWidth: true; text: controller.runSettings.cycleInterval; onTextEdited: controller.markRunSettingsPending() }
                            RowLayout {
                                Layout.fillWidth: true
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 4
                                    FormLabel { text: "TYPING INTERVAL" }
                                    KField { id: textInterval; Layout.fillWidth: true; text: controller.runSettings.textInterval; onTextEdited: controller.markRunSettingsPending() }
                                }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 4
                                    FormLabel { text: "VARIATION ±" }
                                    KField { id: jitter; Layout.fillWidth: true; text: controller.runSettings.jitter; onTextEdited: controller.markRunSettingsPending() }
                                }
                            }
                            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.line; Layout.topMargin: 10; Layout.bottomMargin: 5 }
                            FormLabel { text: "GLOBAL SHORTCUTS" }
                            Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; text: "Use one key or a combination like ctrl+shift+s."; color: Theme.ink2; font.family: Theme.regular; font.pixelSize: 11 }
                            RowLayout {
                                Layout.fillWidth: true
                                Text { text: "Start / toggle"; color: Theme.ink2; font.pixelSize: 11; font.family: Theme.medium; Layout.preferredWidth: 88 }
                                KField { id: startHotkey; objectName: "startHotkeyField"; Layout.fillWidth: true; text: controller.runSettings.startHotkey; invalid: runForm.shortcutValidation.startConflict; validationMessage: invalid ? runForm.shortcutValidation.message : ""; onTextChanged: root.shortcutCaptureError = ""; onTextEdited: controller.markRunSettingsPending() }
                                KButton {
                                    objectName: "shortcutRecord_start"
                                    implicitWidth: 106
                                    text: root.shortcutRecordingTarget === "start" ? "Listening" : "Record"
                                    leading: root.shortcutRecordingTarget === "start" ? "●" : "○"
                                    activeNeutral: root.shortcutRecordingTarget === "start"
                                    onClicked: if (controller.recordGlobalShortcut("start")) root.shortcutRecordingTarget = "start"
                                }
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                Text { text: "Record pointer"; color: Theme.ink2; font.pixelSize: 11; font.family: Theme.medium; Layout.preferredWidth: 88 }
                                KField { id: captureHotkey; objectName: "captureHotkeyField"; Layout.fillWidth: true; text: controller.runSettings.captureHotkey; invalid: runForm.shortcutValidation.captureConflict; validationMessage: invalid ? runForm.shortcutValidation.message : ""; onTextChanged: root.shortcutCaptureError = ""; onTextEdited: controller.markRunSettingsPending() }
                                KButton {
                                    objectName: "shortcutRecord_capture"
                                    implicitWidth: 106
                                    text: root.shortcutRecordingTarget === "capture" ? "Listening" : "Record"
                                    leading: root.shortcutRecordingTarget === "capture" ? "●" : "○"
                                    activeNeutral: root.shortcutRecordingTarget === "capture"
                                    onClicked: if (controller.recordGlobalShortcut("capture")) root.shortcutRecordingTarget = "capture"
                                }
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                Text { text: "Emergency stop"; color: Theme.ink2; font.pixelSize: 11; font.family: Theme.medium; Layout.preferredWidth: 88 }
                                KField { id: stopHotkey; objectName: "stopHotkeyField"; Layout.fillWidth: true; text: controller.runSettings.stopHotkey; invalid: runForm.shortcutValidation.stopConflict; validationMessage: invalid ? runForm.shortcutValidation.message : ""; onTextChanged: root.shortcutCaptureError = ""; onTextEdited: controller.markRunSettingsPending() }
                                KButton {
                                    objectName: "shortcutRecord_stop"
                                    implicitWidth: 106
                                    text: root.shortcutRecordingTarget === "stop" ? "Listening" : "Record"
                                    leading: root.shortcutRecordingTarget === "stop" ? "●" : "○"
                                    activeNeutral: root.shortcutRecordingTarget === "stop"
                                    onClicked: if (controller.recordGlobalShortcut("stop")) root.shortcutRecordingTarget = "stop"
                                }
                            }
                            Text {
                                objectName: "shortcutConflictMessage"
                                Layout.fillWidth: true
                                visible: runForm.shortcutMessage.length > 0
                                text: runForm.shortcutMessage
                                color: Theme.red
                                font.family: Theme.semiBold
                                font.pixelSize: 11
                                wrapMode: Text.WordWrap
                                Accessible.name: text
                            }
                            KButton { objectName: "runSettingsApplyButton"; Layout.fillWidth: true; Layout.topMargin: 8; primary: true; enabled: !runForm.shortcutValidation.hasConflict; text: runForm.shortcutValidation.hasConflict ? "Choose different shortcuts" : controller.runSettingsPending ? "Apply run settings" : "Run settings applied"; leading: controller.runSettingsPending ? "✓" : "●"; onClicked: runForm.apply() }
                            Item { Layout.preferredHeight: 12 }
                        }
                    }
                }
            }
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
        function onSelectedIndexChanged() {
            if (controller.actionCaptureMode !== "")
                controller.cancelActionCapture()
            if (controller.selectedIndex >= 0) {
                root.editorIndex = controller.selectedIndex
                editor.loadAction(controller.selectedIndex)
            } else if (root.editorIndex >= 0) {
                editor.reset()
            }
        }
        function onPositionCaptured(target, x, y, coordinateSpace, referenceWidth, referenceHeight) {
            if (target === 0) {
                xField.text = x; yField.text = y
                editor.referenceWidth = referenceWidth
                editor.referenceHeight = referenceHeight
            } else {
                x2Field.text = x; y2Field.text = y
                editor.referenceWidth2 = referenceWidth
                editor.referenceHeight2 = referenceHeight
            }
            editor.coordinateSpace = coordinateSpace
            editor.pointerProvided = true
        }
        function onActionKeyCaptured(value) {
            if (editor.kindValue() === "key")
                valueField.text = value
        }
        function onActionHotkeyCaptured(value) {
            if (editor.kindValue() === "hotkey")
                valueField.text = value
        }
        function onShortcutCaptured(target, value) {
            var proposed = controller.globalShortcutConflicts(
                target === "start" ? value : startHotkey.text,
                target === "capture" ? value : captureHotkey.text,
                target === "stop" ? value : stopHotkey.text
            )
            root.shortcutRecordingTarget = ""
            if (proposed.hasConflict) {
                root.shortcutCaptureError = proposed.message
                controller.notifyShortcutCaptureResult(value, proposed.message)
                return
            }
            root.shortcutCaptureError = ""
            if (target === "start") startHotkey.text = value
            else if (target === "capture") captureHotkey.text = value
            else if (target === "stop") stopHotkey.text = value
            controller.markRunSettingsPending()
            controller.notifyShortcutCaptureResult(value, "")
        }
        function onRunSettingsChanged() {
            foreverSwitch.checked = controller.runSettings.repeatForever
            repeatCount.text = controller.runSettings.repeatCount
            startDelay.text = controller.runSettings.startDelay
            cycleInterval.text = controller.runSettings.cycleInterval
            textInterval.text = controller.runSettings.textInterval
            jitter.text = controller.runSettings.jitter
            startHotkey.text = controller.runSettings.startHotkey
            captureHotkey.text = controller.runSettings.captureHotkey
            stopHotkey.text = controller.runSettings.stopHotkey
        }
        function onTargetSettingsChanged() {
            if (root.editorIndex < 0) {
                editor.coordinateSpace = editor.expectedSpace
                editor.referenceWidth = 0
                editor.referenceHeight = 0
                editor.referenceWidth2 = 0
                editor.referenceHeight2 = 0
                if (controller.targetSettings.mode === "window")
                    followPointerSwitch.checked = false
            }
        }
    }
}

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Effects
import "components" as Components

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

    function openWindowPicker() {
        if (controller.running)
            return
        if (controller.startWindowPick())
            windowPickerDialog.open()
    }

    function closeWindowPicker() {
        windowPickerDialog.close()
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
        onActivated: controller.undoDelete()
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

    component SoftShadow: MultiEffect {
        shadowEnabled: true
        shadowColor: "#240B1730"
        shadowBlur: 0.75
        shadowVerticalOffset: 8
        shadowHorizontalOffset: 0
    }

    component KButton: Components.AppButton {
        buttonFontFamily: interSemiBold.name || root.font.family
        inkColor: root.ink
        secondaryInkColor: root.ink2
        mutedInkColor: root.ink3
        dangerColor: root.red
        surfaceColor: root.surface
        surface2Color: root.surface2
        surface3Color: root.surface3
        lineColor: root.line
        primaryColor: root.primary
        primaryHoverColor: root.primaryHover
    }

    component KScrollBar: Components.AppScrollBar {
        pressedThumbColor: root.ink3
    }

    component KField: Components.AppField {
        fieldFontFamily: interMedium.name || root.font.family
        inkColor: root.ink
        mutedInkColor: root.ink3
        primaryColor: root.primary
        dangerColor: root.red
        lineColor: root.line
    }

    component FormLabel: Text {
        font.family: interSemiBold.name || root.font.family
        font.pixelSize: 10
        font.weight: Font.DemiBold
        font.letterSpacing: 0.8
        color: root.ink3
    }

    component WorkspaceTab: Rectangle {
        id: workspaceTab
        property string label: ""
        property string badge: ""
        property int tabIndex: 0
        property bool pointerHover: false
        readonly property bool selected: root.activeTab === tabIndex
        implicitWidth: workspaceTabContent.implicitWidth + (root.layoutMode === "compact" ? 20 : 28)
        implicitHeight: 38
        radius: 11
        color: selected ? root.surface : (pointerHover ? "#E3E8F1" : "transparent")
        border.width: selected ? 1 : 0
        border.color: root.line
        Behavior on color { ColorAnimation { duration: 140 } }
        Accessible.role: Accessible.PageTab
        Accessible.name: workspaceTab.label
        Accessible.onPressAction: root.selectTab(workspaceTab.tabIndex)
        HoverHandler { cursorShape: Qt.PointingHandCursor; onHoveredChanged: workspaceTab.pointerHover = hovered }
        TapHandler { onTapped: root.selectTab(workspaceTab.tabIndex) }
        ToolTip.visible: pointerHover && root.layoutMode === "compact"
        ToolTip.text: workspaceTab.label

        Row {
            id: workspaceTabContent
            anchors.centerIn: parent
            spacing: 7
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: workspaceTab.label
                color: workspaceTab.selected ? root.ink : root.ink2
                font.family: interSemiBold.name || root.font.family
                font.pixelSize: 13
            }
            Rectangle {
                visible: workspaceTab.badge !== ""
                anchors.verticalCenter: parent.verticalCenter
                width: Math.max(20, workspaceTabBadge.implicitWidth + 12)
                height: 19
                radius: 9
                color: workspaceTab.selected ? root.primarySoft : root.surface3
                Text {
                    id: workspaceTabBadge
                    anchors.centerIn: parent
                    text: workspaceTab.badge
                    color: workspaceTab.selected ? root.primary : root.ink2
                    font.family: interSemiBold.name || root.font.family
                    font.pixelSize: 10
                }
            }
        }
    }

    component KeyCap: Rectangle {
        property string keyText: "F6"
        implicitWidth: Math.max(42, keyLabel.implicitWidth + 18)
        implicitHeight: 25
        radius: 7
        color: root.surface3
        border.width: 1
        border.color: root.line
        Text {
            id: keyLabel
            anchors.centerIn: parent
            text: parent.keyText.toUpperCase()
            color: root.ink
            font.family: interSemiBold.name || root.font.family
            font.pixelSize: 10
        }
    }

    component ShortcutHint: Rectangle {
        id: shortcutHint
        property string keyText: "F6"
        property string labelText: "Start"
        property bool compact: false
        property bool pointerHover: false
        implicitHeight: compact ? 40 : 25
        radius: compact ? 10 : 0
        color: compact ? (pointerHover ? root.primarySoft : "#F3F6FC") : "#00F3F6FC"
        border.width: compact ? 1 : 0
        border.color: compact ? (pointerHover ? "#B8CDF7" : root.line) : "transparent"
        HoverHandler { onHoveredChanged: shortcutHint.pointerHover = hovered }
        ToolTip.visible: compact && pointerHover
        ToolTip.text: keyText.toUpperCase() + "  ·  " + labelText

        RowLayout {
            visible: !shortcutHint.compact
            anchors.fill: parent
            spacing: 7
            KeyCap { keyText: shortcutHint.keyText }
            Text {
                Layout.fillWidth: true
                text: shortcutHint.labelText
                color: root.ink2
                font.family: interMedium.name || root.font.family
                font.pixelSize: 11
            }
        }

        Column {
            visible: shortcutHint.compact
            width: parent.width - 6
            anchors.centerIn: parent
            spacing: 1
            Text {
                width: parent.width
                text: shortcutHint.keyText.toUpperCase()
                elide: Text.ElideRight
                horizontalAlignment: Text.AlignHCenter
                color: root.ink
                font.family: interSemiBold.name || root.font.family
                font.pixelSize: 11
            }
            Text {
                width: parent.width
                text: shortcutHint.labelText.toUpperCase()
                elide: Text.ElideRight
                horizontalAlignment: Text.AlignHCenter
                color: root.ink3
                font.family: interSemiBold.name || root.font.family
                font.pixelSize: 8
                font.letterSpacing: 0.45
            }
        }

        Behavior on color { ColorAnimation { duration: 120 } }
        Behavior on border.color { ColorAnimation { duration: 120 } }
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
            color: root.surface

            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                height: 1
                color: root.line
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
                        color: root.ink
                        font.family: interBold.name || root.font.family
                        font.pixelSize: 16
                        font.weight: Font.Bold
                    }
                    Text {
                        text: "AUTOMATOR  ·  " + Qt.application.version
                        color: root.ink3
                        font.family: interSemiBold.name || root.font.family
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
                    color: root.surface2

                    Row {
                        id: workspaceTabRow
                        anchors.centerIn: parent
                        spacing: 4
                        WorkspaceTab {
                            objectName: "workspaceTab_sequence"
                            tabIndex: 0
                            label: "Sequence"
                        }
                        WorkspaceTab {
                            objectName: "workspaceTab_profiles"
                            tabIndex: 1
                            label: "Profiles"
                            badge: controller.profileEntries.length > 0
                                   ? String(controller.profileEntries.length)
                                   : ""
                        }
                        WorkspaceTab {
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
                    ToolTip.visible: pointerHover
                    ToolTip.text: "Save profile (Ctrl+S)"
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
                    ToolTip.visible: pointerHover
                    ToolTip.text: "New sequence"
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
                                    color: root.ink
                                    font.family: interBold.name || root.font.family
                                    // Kept at 28 so the cap height still lines up with the
                                    // status badge on the right of this row.
                                    font.pixelSize: root.layoutMode === "compact" ? 24 : 28
                                    font.weight: Font.Bold
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: (controller.dirty ? "Unsaved  ·  " : "") + controller.summary
                                    elide: Text.ElideRight
                                    color: controller.dirty ? root.red : root.ink2
                                    font.family: interRegular.name || root.font.family
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
                                color: controller.statusTone === "success" ? "#E8F7F0" : controller.statusTone === "danger" ? "#FFF0F2" : controller.statusTone === "accent" ? root.primarySoft : root.surface2
                                Behavior on color { ColorAnimation { duration: 180 } }
                                Row {
                                    id: statusRow
                                    anchors.centerIn: parent
                                    spacing: 7
                                    Rectangle {
                                        width: 7; height: 7; radius: 4
                                        anchors.verticalCenter: parent.verticalCenter
                                        color: root.toneColor(controller.statusTone)
                                        SequentialAnimation on opacity {
                                            running: controller.running
                                            loops: Animation.Infinite
                                            NumberAnimation { to: 0.35; duration: 650 }
                                            NumberAnimation { to: 1; duration: 650 }
                                        }
                                    }
                                    Text { text: controller.status; color: root.toneColor(controller.statusTone); font.family: interSemiBold.name || root.font.family; font.pixelSize: 11 }
                                }
                            }
                        }

                        Rectangle {
                            id: sequenceToolbar
                            objectName: "sequenceToolbar"
                            Layout.fillWidth: true
                            Layout.preferredHeight: 48
                            radius: 13
                            color: root.surface
                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 14
                                anchors.rightMargin: 8
                                spacing: 4
                                Text {
                                    Layout.fillWidth: true
                                    text: controller.summary
                                    elide: Text.ElideRight
                                    color: root.ink2
                                    font.family: interSemiBold.name || root.font.family
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
                                    ToolTip.visible: pointerHover
                                    ToolTip.text: "Restore deleted action (Ctrl+Z)"
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
                                    ToolTip.visible: pointerHover
                                    ToolTip.text: "Test this action once after a safety countdown"
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
                                    ToolTip.visible: pointerHover
                                    ToolTip.text: "Run from the selected action"
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
                            color: root.surface
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
                                    Text { anchors.centerIn: parent; text: "+"; color: root.primary; font.family: interSemiBold.name || root.font.family; font.pixelSize: 28 }
                                    SequentialAnimation on scale {
                                        loops: Animation.Infinite
                                        NumberAnimation { to: 1.045; duration: 1600; easing.type: Easing.InOutSine }
                                        NumberAnimation { to: 1; duration: 1600; easing.type: Easing.InOutSine }
                                    }
                                }
                                Text { anchors.horizontalCenter: parent.horizontalCenter; text: "Build a sequence that feels effortless"; color: root.ink; font.family: interBold.name || root.font.family; font.pixelSize: 19; font.weight: Font.Bold }
                                Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap; text: "Add keys, clicks, scrolling, text, or drag actions. Then tune timing in the inspector."; color: root.ink2; font.family: interRegular.name || root.font.family; font.pixelSize: 12; lineHeight: 1.25 }
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
                                        color: root.primary
                                        Rectangle {
                                            width: 9
                                            height: 9
                                            radius: 5
                                            anchors.left: parent.left
                                            anchors.verticalCenter: parent.verticalCenter
                                            color: root.primary
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
                                        color: root.line
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
                                        color: controller.runningActionIndex === actionCard.actionIndex ? root.green : controller.selectedIndex === actionCard.actionIndex ? root.primary : hover.hovered ? root.primarySoft : root.surface2
                                        border.width: controller.runningActionIndex === actionCard.actionIndex || controller.selectedIndex === actionCard.actionIndex ? 0 : 1
                                        border.color: hover.hovered ? "#B8CCF5" : root.line
                                        Behavior on opacity { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
                                        Behavior on color { ColorAnimation { duration: 120 } }
                                        Behavior on border.color { ColorAnimation { duration: 120 } }
                                        Text {
                                            anchors.centerIn: parent
                                            text: String(actionCard.actionIndex + 1).padStart(2, "0")
                                            color: controller.runningActionIndex === actionCard.actionIndex || controller.selectedIndex === actionCard.actionIndex ? "white" : root.primary
                                            font.family: interSemiBold.name || root.font.family
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
                                        color: tap.pressed ? "#DEE9FF" : controller.runningActionIndex === actionCard.actionIndex ? root.successSoft : controller.selectedIndex === actionCard.actionIndex ? "#EDF3FF" : hover.hovered ? "#F4F7FF" : root.surface
                                        border.width: controller.selectedIndex === actionCard.actionIndex ? 2 : 1
                                        border.color: reorderDrag.active ? root.primary : controller.runningActionIndex === actionCard.actionIndex ? root.green : controller.selectedIndex === actionCard.actionIndex ? root.primary : hover.hovered ? "#B8CCF5" : root.line
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
                                                    color: controller.selectedIndex === actionCard.actionIndex ? root.surface : root.primarySoft
                                                    border.width: controller.selectedIndex === actionCard.actionIndex ? 1 : 0
                                                    border.color: "#C6D8FC"
                                                    Text {
                                                        anchors.centerIn: parent
                                                        text: actionCard.actionIcon
                                                        color: root.primary
                                                        font.family: interBold.name || root.font.family
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
                                                            color: root.ink
                                                            font.family: interSemiBold.name || root.font.family
                                                            font.pixelSize: 13
                                                        }
                                                        Rectangle {
                                                            objectName: "editingBadge"
                                                            visible: controller.runningActionIndex === actionCard.actionIndex || controller.selectedIndex === actionCard.actionIndex
                                                            implicitWidth: editingLabel.implicitWidth + 14
                                                            implicitHeight: 20
                                                            radius: 7
                                                            color: controller.runningActionIndex === actionCard.actionIndex ? root.green : root.primary
                                                            Text {
                                                                id: editingLabel
                                                                anchors.centerIn: parent
                                                                text: controller.runningActionIndex === actionCard.actionIndex ? "RUNNING" : "EDITING"
                                                                color: "white"
                                                                font.family: interSemiBold.name || root.font.family
                                                                font.pixelSize: 8
                                                                font.letterSpacing: 0.5
                                                            }
                                                        }
                                                    }
                                                    Text {
                                                        Layout.fillWidth: true
                                                        text: actionCard.subtitle
                                                        elide: Text.ElideRight
                                                        color: root.ink3
                                                        font.family: interRegular.name || root.font.family
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
                                                color: reorderDrag.active ? root.primarySoft : dragHover.hovered ? root.surface3 : "transparent"
                                                border.width: reorderDrag.active ? 1 : 0
                                                border.color: "#B8CCF5"
                                                HoverHandler {
                                                    id: dragHover
                                                    cursorShape: reorderDrag.active ? Qt.ClosedHandCursor : Qt.OpenHandCursor
                                                }
                                                ToolTip.visible: dragHover.hovered && !reorderDrag.active
                                                ToolTip.text: actionList.count > 1 ? "Drag to reorder" : "Add another action to reorder"

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
                                                            color: reorderDrag.active ? root.primary : root.ink3
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
                                                    color: enabledSwitch.checked ? root.primary : "#CAD1DC"
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

                Item {
                    objectName: "profileLibraryPage"

                    ColumnLayout {
                        // This content was laid out for a narrow drawer; cap it so rows
                        // stay readable and their trailing buttons stay on screen.
                        anchors.top: parent.top
                        anchors.bottom: parent.bottom
                        anchors.horizontalCenter: parent.horizontalCenter
                        width: Math.min(parent.width, 940)
                        spacing: 0
                        clip: true

                        Item {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 92
                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 20
                                anchors.rightMargin: 14
                                spacing: 8
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 3
                                    Text {
                                        text: "Profiles"
                                        color: root.ink
                                        font.family: interBold.name || root.font.family
                                        font.pixelSize: 23
                                        font.weight: Font.Bold
                                    }
                                    Text {
                                        text: controller.profileEntries.length === 1
                                              ? "1 saved sequence"
                                              : controller.profileEntries.length + " saved sequences"
                                        color: root.ink2
                                        font.family: interRegular.name || root.font.family
                                        font.pixelSize: 12
                                    }
                                }
                                KButton {
                                    objectName: "refreshProfileLibraryButton"
                                    leading: "↻"
                                    text: "Refresh"
                                    implicitWidth: 92
                                    Accessible.name: "Refresh profiles"
                                    ToolTip.visible: pointerHover
                                    ToolTip.text: "Refresh profiles"
                                    onClicked: controller.refreshProfiles()
                                }
                            }
                        }

                        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: root.line }

                        Item {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 88
                            ColumnLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 20
                                anchors.rightMargin: 14
                                anchors.topMargin: 12
                                anchors.bottomMargin: 12
                                spacing: 5
                                FormLabel { text: "PROFILE FOLDER" }
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 8
                                    Text {
                                        objectName: "profileDirectoryLabel"
                                        Layout.fillWidth: true
                                        text: controller.profileDirectory
                                        elide: Text.ElideMiddle
                                        color: root.ink2
                                        font.family: interMedium.name || root.font.family
                                        font.pixelSize: 11
                                        ToolTip.visible: directoryHover.hovered
                                        ToolTip.text: controller.profileDirectory
                                        HoverHandler { id: directoryHover }
                                    }
                                    KButton {
                                        objectName: "chooseProfileFolderButton"
                                        text: "Browse"
                                        implicitWidth: 84
                                        implicitHeight: 38
                                        onClicked: controller.chooseProfileFolder()
                                    }
                                }
                            }
                        }

                        Item {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            Layout.minimumHeight: 180

                            ListView {
                                id: profileList
                                objectName: "profileLibraryList"
                                anchors.fill: parent
                                anchors.leftMargin: 14
                                anchors.rightMargin: 14
                                anchors.topMargin: 4
                                anchors.bottomMargin: 8
                                spacing: 8
                                clip: true
                                boundsBehavior: Flickable.StopAtBounds
                                model: controller.profileEntries
                                ScrollBar.vertical: KScrollBar {
                                    id: profileScrollBar
                                    objectName: "profileLibraryScrollBar"
                                }
                                delegate: Item {
                                    id: profileDelegate
                                    required property var modelData
                                    required property int index
                                    readonly property string profilePath: modelData.path
                                    readonly property bool currentProfile: modelData.path === controller.currentProfilePath
                                    readonly property bool queued: controller.runQueuePaths.indexOf(profilePath) >= 0
                                    width: ListView.view.width
                                           - (profileScrollBar.visible ? profileScrollBar.width + 8 : 0)
                                    height: 80

                                    AbstractButton {
                                        id: profileRow
                                        readonly property var modelData: profileDelegate.modelData
                                        readonly property int index: profileDelegate.index
                                        readonly property string profilePath: profileDelegate.profilePath
                                        readonly property bool currentProfile: profileDelegate.currentProfile
                                        readonly property bool queued: profileDelegate.queued
                                        property bool pointerHover: false
                                        objectName: "profileLibraryRow_" + index
                                        anchors.left: parent.left
                                        anchors.right: queueProfileButton.left
                                        anchors.rightMargin: 8
                                        anchors.top: parent.top
                                        anchors.bottom: parent.bottom
                                        enabled: modelData.valid && !controller.running
                                        hoverEnabled: true
                                        Accessible.name: (currentProfile ? "Current profile, " : "Open profile, ") + modelData.name
                                        Accessible.description: modelData.valid
                                              ? modelData.actionCount + " actions. Modified " + modelData.modified
                                              : "Unavailable profile"
                                        HoverHandler { onHoveredChanged: profileRow.pointerHover = hovered }
                                        ToolTip.visible: profileRow.pointerHover
                                        ToolTip.text: modelData.valid ? modelData.path : modelData.error
                                        onClicked: {
                                            if (profileRow.currentProfile)
                                                root.selectTab(0)
                                            else
                                                root.requestProfileOpen(modelData.path)
                                        }
                                        background: Rectangle {
                                        radius: 14
                                        color: profileRow.currentProfile ? root.primarySoft
                                             : profileRow.down ? "#E8EEF8"
                                             : profileRow.pointerHover ? "#F4F7FF"
                                             : root.surface
                                        border.width: profileRow.currentProfile ? 2 : 1
                                        border.color: profileRow.currentProfile ? root.primary
                                                    : profileRow.pointerHover ? "#B8CCF5"
                                                    : root.line
                                        scale: profileRow.down ? 0.992 : 1
                                        Behavior on color { ColorAnimation { duration: 120 } }
                                        Behavior on border.color { ColorAnimation { duration: 120 } }
                                        Behavior on scale { NumberAnimation { duration: 90 } }
                                    }
                                        // Padding belongs to the control: anchoring the
                                        // contentItem fights the Control's own sizing and
                                        // let the trailing chevron escape the card.
                                        leftPadding: 12
                                        rightPadding: 12
                                        contentItem: RowLayout {
                                        spacing: 11
                                        Rectangle {
                                            Layout.preferredWidth: 38
                                            Layout.preferredHeight: 38
                                            radius: 11
                                            color: profileRow.currentProfile ? root.primary : root.surface2
                                            border.width: profileRow.currentProfile ? 0 : 1
                                            border.color: root.line
                                            Image {
                                                anchors.centerIn: parent
                                                width: 24
                                                height: 24
                                                source: "../assets/app-logo-transparent.png"
                                                fillMode: Image.PreserveAspectFit
                                                smooth: true
                                                mipmap: true
                                            }
                                        }
                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: 4
                                            RowLayout {
                                                Layout.fillWidth: true
                                                spacing: 6
                                                Text {
                                                    Layout.fillWidth: true
                                                    text: profileRow.modelData.name
                                                    elide: Text.ElideRight
                                                    color: profileRow.modelData.valid ? root.ink : root.red
                                                    font.family: interSemiBold.name || root.font.family
                                                    font.pixelSize: 13
                                                }
                                                Rectangle {
                                                    visible: profileRow.currentProfile
                                                    implicitWidth: currentProfileLabel.implicitWidth + 14
                                                    implicitHeight: 20
                                                    radius: 7
                                                    color: root.primary
                                                    Text {
                                                        id: currentProfileLabel
                                                        anchors.centerIn: parent
                                                        text: "CURRENT"
                                                        color: "white"
                                                        font.family: interSemiBold.name || root.font.family
                                                        font.pixelSize: 8
                                                        font.letterSpacing: 0.45
                                                    }
                                                }
                                            }
                                            Text {
                                                Layout.fillWidth: true
                                                text: profileRow.modelData.valid
                                                      ? (profileRow.modelData.actionCount === 1
                                                         ? "1 action"
                                                         : profileRow.modelData.actionCount + " actions")
                                                        + "  ·  " + profileRow.modelData.modified
                                                      : "Could not read this profile"
                                                elide: Text.ElideRight
                                                color: profileRow.modelData.valid ? root.ink3 : root.red
                                                font.family: interRegular.name || root.font.family
                                                font.pixelSize: 11
                                            }
                                        }
                                        Text {
                                            visible: profileRow.modelData.valid && !profileRow.currentProfile
                                            text: "›"
                                            color: root.ink3
                                            font.family: interSemiBold.name || root.font.family
                                            font.pixelSize: 20
                                        }
                                    }
                                }
                                    KButton {
                                        id: queueProfileButton
                                        objectName: "queueProfileButton_" + profileDelegate.index
                                        anchors.right: parent.right
                                        anchors.verticalCenter: parent.verticalCenter
                                        implicitWidth: 76
                                        implicitHeight: 38
                                        text: profileDelegate.queued ? "Queued" : "Queue"
                                        leading: profileDelegate.queued ? "✓" : "+"
                                        activeNeutral: profileDelegate.queued
                                        enabled: profileDelegate.modelData.valid
                                              && !controller.running
                                              && !profileDelegate.queued
                                              && !(profileDelegate.currentProfile && (controller.dirty || controller.runSettingsPending))
                                        Accessible.name: (profileDelegate.queued ? "Already queued " : "Queue ") + profileDelegate.modelData.name
                                        ToolTip.visible: pointerHover
                                        ToolTip.text: profileDelegate.currentProfile && (controller.dirty || controller.runSettingsPending)
                                                      ? "Save this profile before queuing it"
                                                      : profileDelegate.queued
                                                        ? "This profile is already in the run queue"
                                                        : "Add this saved profile to the sequential queue"
                                        onClicked: controller.enqueueProfile(profileDelegate.profilePath)
                                    }
                                }
                            }

                            Column {
                                objectName: "profileLibraryEmptyState"
                                visible: profileList.count === 0
                                anchors.centerIn: parent
                                width: Math.min(300, parent.width - 40)
                                spacing: 10
                                Rectangle {
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    width: 54
                                    height: 54
                                    radius: 17
                                    color: root.primarySoft
                                    Image {
                                        anchors.centerIn: parent
                                        width: 32
                                        height: 32
                                        source: "../assets/app-logo-transparent.png"
                                        fillMode: Image.PreserveAspectFit
                                        smooth: true
                                        mipmap: true
                                    }
                                }
                                Text {
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    text: "No saved profiles here"
                                    color: root.ink
                                    font.family: interBold.name || root.font.family
                                    font.pixelSize: 17
                                    font.weight: Font.Bold
                                }
                                Text {
                                    width: parent.width
                                    horizontalAlignment: Text.AlignHCenter
                                    wrapMode: Text.WordWrap
                                    text: "Save this sequence or choose the folder that already contains your KeyClick profiles."
                                    color: root.ink2
                                    font.family: interRegular.name || root.font.family
                                    font.pixelSize: 12
                                    lineHeight: 1.3
                                }
                                KButton {
                                    objectName: "profileLibraryEmptySaveButton"
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    text: "Save this profile"
                                    primary: true
                                    implicitWidth: 156
                                    onClicked: root.saveProfileAsWithVisibleSettings()
                                }
                            }
                        }

                        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: root.line }

                        Item {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 76
                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 14
                                anchors.rightMargin: 14
                                spacing: 8
                                Item { Layout.fillWidth: true }
                                KButton {
                                    objectName: "profileLibraryRunnerButton"
                                    Layout.preferredWidth: 112
                                    text: controller.runQueueCount > 0
                                          ? "Runner · " + controller.runQueueCount
                                          : "Runner"
                                    activeNeutral: controller.runQueueCount > 0
                                    onClicked: root.selectTab(2)
                                }
                                KButton {
                                    objectName: "profileLibrarySaveAsButton"
                                    Layout.preferredWidth: 112
                                    text: "Save as…"
                                    primary: true
                                    enabled: !controller.running
                                    onClicked: root.saveProfileAsWithVisibleSettings()
                                }
                                KButton {
                                    objectName: "profileLibraryOpenFileButton"
                                    Layout.preferredWidth: 112
                                    text: "Open file…"
                                    enabled: !controller.running
                                    onClicked: root.requestDestructiveAction("open")
                                }
                            }
                        }
                    }
                }

                Item {
                    objectName: "runQueuePage"

                    ColumnLayout {
                        // Laid out for a narrow drawer originally; cap the width so the
                        // mode toggle and footer actions stay inside the page.
                        anchors.top: parent.top
                        anchors.bottom: parent.bottom
                        anchors.horizontalCenter: parent.horizontalCenter
                        width: Math.min(parent.width, 940)
                        spacing: 0
                        clip: true

                        Item {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 92
                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 20
                                anchors.rightMargin: 14
                                spacing: 8
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 3
                                    Text {
                                        text: "Multi-Profile Runner"
                                        color: root.ink
                                        font.family: interBold.name || root.font.family
                                        font.pixelSize: 23
                                        font.weight: Font.Bold
                                    }
                                    Text {
                                        text: controller.runQueueCount === 0
                                              ? "No profiles queued"
                                              : controller.runQueueCount === 1
                                                ? "1 profile · " + (controller.runQueueMode === "parallel" ? "Parallel" : "Sequential")
                                                : controller.runQueueCount + " profiles · " + (controller.runQueueMode === "parallel" ? "Parallel" : "Sequential")
                                        color: root.ink2
                                        font.family: interRegular.name || root.font.family
                                        font.pixelSize: 12
                                    }
                                }
                                KButton {
                                    objectName: "runQueueAddProfilesButton"
                                    text: "Profiles"
                                    leading: "+"
                                    implicitWidth: 96
                                    enabled: !controller.running
                                    onClicked: root.selectTab(1)
                                }
                            }
                        }

                        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: root.line }

                        Rectangle {
                            objectName: "runQueueModeNotice"
                            Layout.fillWidth: true
                            Layout.preferredHeight: 106
                            Layout.leftMargin: 14
                            Layout.rightMargin: 14
                            Layout.topMargin: 12
                            Layout.bottomMargin: 8
                            radius: 13
                            color: root.primarySoft
                            border.width: 1
                            border.color: "#C6D8FC"
                            ColumnLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 13
                                anchors.rightMargin: 13
                                anchors.topMargin: 10
                                anchors.bottomMargin: 10
                                spacing: 6
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 6
                                    FormLabel { text: "RUN MODE"; color: root.primary }
                                    Item { Layout.fillWidth: true }
                                    KButton {
                                        objectName: "runQueueSequentialModeButton"
                                        implicitWidth: 116
                                        implicitHeight: 32
                                        text: "Sequential"
                                        leading: controller.runQueueMode === "sequential" ? "✓" : ""
                                        activeNeutral: controller.runQueueMode === "sequential"
                                        enabled: !controller.running
                                        Accessible.name: "Run profiles sequentially"
                                        Accessible.description: "Run one saved profile after another"
                                        onClicked: controller.setRunQueueMode("sequential")
                                    }
                                    KButton {
                                        objectName: "runQueueParallelModeButton"
                                        implicitWidth: 100
                                        implicitHeight: 32
                                        text: "Parallel"
                                        leading: controller.runQueueMode === "parallel" ? "✓" : ""
                                        activeNeutral: controller.runQueueMode === "parallel"
                                        enabled: !controller.running
                                        Accessible.name: "Run profiles in parallel"
                                        Accessible.description: "Run two to eight different background windows together"
                                        onClicked: controller.setRunQueueMode("parallel")
                                    }
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: controller.runQueueMode === "parallel"
                                          ? "Run 2–8 different background windows together. Desktop and duplicate targets are blocked; F9 stops all."
                                          : "Run one profile at a time. Stop can skip the active profile; F9 stops it and cancels everything waiting."
                                    color: root.ink2
                                    font.family: interRegular.name || root.font.family
                                    font.pixelSize: 11
                                    lineHeight: 1.25
                                    wrapMode: Text.WordWrap
                                }
                            }
                        }

                        Item {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            Layout.minimumHeight: 180

                            ListView {
                                id: runQueueList
                                objectName: "runQueueList"
                                anchors.fill: parent
                                anchors.leftMargin: 14
                                anchors.rightMargin: 14
                                anchors.topMargin: 6
                                anchors.bottomMargin: 8
                                spacing: 8
                                clip: true
                                boundsBehavior: Flickable.StopAtBounds
                                model: controller.runQueueEntries
                                ScrollBar.vertical: KScrollBar {
                                    id: runQueueScrollBar
                                    objectName: "runQueueScrollBar"
                                }
                                delegate: Rectangle {
                                    id: queueCard
                                    required property var modelData
                                    required property int index
                                    objectName: "runQueueCard_" + index
                                    width: ListView.view.width
                                           - (runQueueScrollBar.visible ? runQueueScrollBar.width + 8 : 0)
                                    height: modelData.error.length > 0 ? 124 : 100
                                    radius: 14
                                    color: modelData.state === "running" || modelData.state === "armed" || modelData.state === "paused"
                                           ? root.primarySoft
                                           : modelData.state === "error"
                                             ? root.redSoft
                                             : modelData.state === "complete"
                                               ? root.successSoft
                                               : root.surface
                                    border.width: modelData.state === "running" || modelData.state === "armed" || modelData.state === "paused" ? 2 : 1
                                    border.color: modelData.state === "error"
                                                  ? "#EDB8C2"
                                                  : modelData.state === "complete"
                                                    ? "#B8DECF"
                                                    : modelData.state === "running" || modelData.state === "armed" || modelData.state === "paused"
                                                      ? root.primary
                                                      : root.line

                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.margins: 12
                                        spacing: 10

                                        Rectangle {
                                            Layout.preferredWidth: 36
                                            Layout.preferredHeight: 36
                                            radius: 11
                                            color: queueCard.modelData.state === "complete"
                                                   ? root.green
                                                   : queueCard.modelData.state === "error"
                                                     ? root.red
                                                     : root.surface2
                                            border.width: queueCard.modelData.state === "queued" || queueCard.modelData.state === "cancelled" ? 1 : 0
                                            border.color: root.line
                                            Text {
                                                anchors.centerIn: parent
                                                text: String(queueCard.modelData.position).padStart(2, "0")
                                                color: queueCard.modelData.state === "complete" || queueCard.modelData.state === "error"
                                                       ? "white"
                                                       : root.primary
                                                font.family: interSemiBold.name || root.font.family
                                                font.pixelSize: 10
                                                font.letterSpacing: 0.35
                                            }
                                        }

                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: 4
                                            RowLayout {
                                                Layout.fillWidth: true
                                                spacing: 8
                                                Text {
                                                    Layout.fillWidth: true
                                                    text: queueCard.modelData.profileName
                                                    elide: Text.ElideRight
                                                    color: root.ink
                                                    font.family: interSemiBold.name || root.font.family
                                                    font.pixelSize: 13
                                                }
                                                Rectangle {
                                                    implicitWidth: queueStatusLabel.implicitWidth + 14
                                                    implicitHeight: 21
                                                    radius: 7
                                                    color: queueCard.modelData.tone === "danger"
                                                           ? root.redSoft
                                                           : queueCard.modelData.tone === "success"
                                                             ? root.successSoft
                                                             : queueCard.modelData.tone === "accent"
                                                               ? "#DCE8FF"
                                                               : root.surface2
                                                    Text {
                                                        id: queueStatusLabel
                                                        anchors.centerIn: parent
                                                        text: queueCard.modelData.status.toUpperCase()
                                                        color: root.toneColor(queueCard.modelData.tone)
                                                        font.family: interSemiBold.name || root.font.family
                                                        font.pixelSize: 8
                                                        font.letterSpacing: 0.4
                                                    }
                                                }
                                            }
                                            Text {
                                                Layout.fillWidth: true
                                                text: queueCard.modelData.target + "  ·  "
                                                      + queueCard.modelData.actionCount
                                                      + (queueCard.modelData.actionCount === 1 ? " active action" : " active actions")
                                                elide: Text.ElideRight
                                                color: root.ink3
                                                font.family: interRegular.name || root.font.family
                                                font.pixelSize: 11
                                            }
                                            Text {
                                                visible: queueCard.modelData.error.length > 0
                                                Layout.fillWidth: true
                                                text: queueCard.modelData.error
                                                wrapMode: Text.WordWrap
                                                maximumLineCount: 2
                                                elide: Text.ElideRight
                                                color: root.red
                                                font.family: interMedium.name || root.font.family
                                                font.pixelSize: 10
                                                ToolTip.visible: queueErrorHover.hovered
                                                ToolTip.text: text
                                                HoverHandler { id: queueErrorHover }
                                            }
                                            Rectangle {
                                                visible: queueCard.modelData.state === "running"
                                                      || queueCard.modelData.state === "armed"
                                                      || queueCard.modelData.state === "paused"
                                                Layout.fillWidth: true
                                                Layout.maximumWidth: 210
                                                Layout.preferredHeight: 5
                                                radius: 3
                                                color: root.surface3
                                                Rectangle {
                                                    height: parent.height
                                                    radius: 3
                                                    color: root.primary
                                                    width: queueCard.modelData.progress < 0
                                                           ? Math.max(28, parent.width * 0.3)
                                                           : parent.width * Math.max(0, Math.min(1, queueCard.modelData.progress))
                                                    SequentialAnimation on opacity {
                                                        running: queueCard.modelData.progress < 0
                                                              && queueCard.modelData.state !== "paused"
                                                        loops: Animation.Infinite
                                                        NumberAnimation { to: 0.4; duration: 520 }
                                                        NumberAnimation { to: 1; duration: 520 }
                                                    }
                                                    Behavior on width { NumberAnimation { duration: 180 } }
                                                }
                                            }
                                        }

                                        RowLayout {
                                            visible: !controller.runQueueRunning
                                            Layout.preferredWidth: 152
                                            spacing: 4
                                            KButton {
                                                objectName: "runQueueMoveUp_" + queueCard.index
                                                Layout.preferredWidth: 34
                                                Layout.minimumWidth: 34
                                                implicitWidth: 34
                                                implicitHeight: 34
                                                padding: 0
                                                leading: "↑"
                                                quiet: true
                                                enabled: queueCard.index > 0 && !controller.running
                                                Accessible.name: "Move " + queueCard.modelData.profileName + " up"
                                                onClicked: controller.moveQueuedProfile(queueCard.index, -1)
                                            }
                                            KButton {
                                                objectName: "runQueueMoveDown_" + queueCard.index
                                                Layout.preferredWidth: 34
                                                Layout.minimumWidth: 34
                                                implicitWidth: 34
                                                implicitHeight: 34
                                                padding: 0
                                                leading: "↓"
                                                quiet: true
                                                enabled: queueCard.index < controller.runQueueCount - 1 && !controller.running
                                                Accessible.name: "Move " + queueCard.modelData.profileName + " down"
                                                onClicked: controller.moveQueuedProfile(queueCard.index, 1)
                                            }
                                            KButton {
                                                objectName: "runQueueRemove_" + queueCard.index
                                                Layout.preferredWidth: 76
                                                Layout.minimumWidth: 76
                                                implicitWidth: 76
                                                implicitHeight: 34
                                                text: "Remove"
                                                danger: true
                                                quiet: true
                                                enabled: !controller.running
                                                Accessible.name: "Remove " + queueCard.modelData.profileName + " from queue"
                                                onClicked: controller.removeQueuedProfile(queueCard.index)
                                            }
                                        }

                                        RowLayout {
                                            visible: controller.runQueueRunning
                                                  && (queueCard.modelData.state === "armed"
                                                      || queueCard.modelData.state === "running"
                                                      || queueCard.modelData.state === "paused"
                                                      || queueCard.modelData.state === "stopping")
                                            Layout.preferredWidth: 152
                                            spacing: 4
                                            KButton {
                                                objectName: "runQueuePause_" + queueCard.index
                                                Layout.preferredWidth: 84
                                                Layout.minimumWidth: 84
                                                implicitWidth: 84
                                                implicitHeight: 34
                                                text: queueCard.modelData.paused ? "Resume" : "Pause"
                                                enabled: queueCard.modelData.state !== "stopping"
                                                activeNeutral: queueCard.modelData.paused
                                                Accessible.name: (queueCard.modelData.paused ? "Resume " : "Pause ") + queueCard.modelData.profileName
                                                onClicked: controller.toggleRunSessionPaused(queueCard.modelData.id)
                                            }
                                            KButton {
                                                objectName: "runQueueStop_" + queueCard.index
                                                Layout.preferredWidth: 64
                                                Layout.minimumWidth: 64
                                                implicitWidth: 64
                                                implicitHeight: 34
                                                text: "Stop"
                                                danger: true
                                                enabled: queueCard.modelData.state !== "stopping"
                                                Accessible.name: "Stop " + queueCard.modelData.profileName
                                                Accessible.description: controller.runQueueMode === "parallel"
                                                      ? "Stop only this profile"
                                                      : "Stop this profile and continue with the next queued profile"
                                                onClicked: controller.stopRunSession(queueCard.modelData.id)
                                            }
                                        }
                                    }
                                }
                            }

                            Column {
                                objectName: "runQueueEmptyState"
                                visible: runQueueList.count === 0
                                anchors.centerIn: parent
                                width: Math.min(330, parent.width - 48)
                                spacing: 10
                                Text {
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    text: "Build your first run queue"
                                    color: root.ink
                                    font.family: interBold.name || root.font.family
                                    font.pixelSize: 18
                                    font.weight: Font.Bold
                                }
                                Text {
                                    width: parent.width
                                    horizontalAlignment: Text.AlignHCenter
                                    wrapMode: Text.WordWrap
                                    text: "Open Profiles and add saved sequences in the order you want KeyClick to run them."
                                    color: root.ink2
                                    font.family: interRegular.name || root.font.family
                                    font.pixelSize: 12
                                    lineHeight: 1.3
                                }
                                KButton {
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    text: "Choose profiles"
                                    primary: true
                                    implicitWidth: 150
                                    onClicked: root.selectTab(1)
                                }
                            }
                        }

                        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: root.line }

                        Item {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 84
                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 14
                                anchors.rightMargin: 14
                                spacing: 8
                                KButton {
                                    objectName: "runQueueClearButton"
                                    Layout.preferredWidth: 88
                                    text: "Clear"
                                    enabled: controller.runQueueCount > 0 && !controller.running
                                    onClicked: controller.clearRunQueue()
                                }
                                Item { Layout.fillWidth: true }
                                KButton {
                                    objectName: "runQueueStopAllButton"
                                    visible: controller.runQueueRunning
                                    Layout.preferredWidth: 112
                                    text: "Stop all"
                                    leading: "■"
                                    keyHint: "F9"
                                    danger: true
                                    Accessible.description: "Stop every active and waiting profile"
                                    onClicked: controller.stopAllRuns()
                                }
                                KButton {
                                    objectName: "runQueueStartButton"
                                    Layout.preferredWidth: controller.runQueueMode === "parallel" ? 142 : 132
                                    text: controller.runQueueRunning
                                          ? "Running queue"
                                          : controller.runQueueMode === "parallel"
                                            ? "Run together"
                                            : "Run queue"
                                    leading: controller.runQueueRunning ? "●" : "▶"
                                    primary: true
                                    enabled: controller.runQueueCount > 0 && !controller.running
                                    onClicked: controller.startRunQueue()
                                }
                            }
                        }
                    }
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
            color: root.surface
            border.width: 1
            border.color: root.line
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
                        text: controller.capturePending ? "Pick a point on the frozen screen · Esc cancels" : controller.running ? controller.status : controller.targetSettings.mode === "window" && !controller.targetSettings.windowSelected ? "Choose a background target window" : controller.canRun ? "Ready when you are" : (actionList.count > 0 ? "Enable an action to begin" : "Add an action to begin")
                        elide: Text.ElideRight
                        color: root.ink2
                        font.family: interMedium.name || root.font.family
                        font.pixelSize: 12
                    }
                    Item {
                        id: runProgressTrack
                        objectName: "runProgressTrack"
                        visible: controller.running
                        Layout.fillWidth: true
                        Layout.maximumWidth: 220
                        Layout.preferredHeight: 6
                        Rectangle { anchors.fill: parent; radius: 3; color: root.surface3 }
                        Rectangle {
                            height: parent.height; radius: 3; color: root.primary
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
                    ToolTip.visible: shortcutDockHover.hovered
                    ToolTip.text: controller.targetSettings.mode === "window"
                                  ? "Background mode: " + controller.runSettings.stopHotkey.toUpperCase() + " stops the run."
                                  : "Desktop corner fail-safe is active."
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
                                    color: root.ink2
                                    font.family: interMedium.name || root.font.family
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
                            text: controller.running ? "Running" : runForm.shortcutValidation.hasConflict ? "Fix shortcuts" : controller.runSettingsPending ? "Apply & start" : "Start"
                            leading: controller.running ? "●" : "▶"
                            keyHint: controller.runSettings.startHotkey
                            primary: true
                            enabled: !controller.running && controller.canRun && !runForm.shortcutValidation.hasConflict && (controller.targetSettings.mode === "desktop" || controller.targetSettings.windowSelected)
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
            border.color: root.line
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
                    Text { Layout.fillWidth: true; text: "Inspector"; color: root.ink; font.family: interBold.name || root.font.family; font.pixelSize: 20; font.weight: Font.Bold }
                    KButton { visible: root.overlayInspector; text: ""; leading: "×"; quiet: true; implicitWidth: 38; onClicked: root.inspectorOpen = false }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 40
                    radius: 12
                    color: root.surface2
                    Rectangle {
                        id: tabSelectionPill
                        objectName: "tabSelectionPill"
                        x: 3 + root.activeInspectorTab * width
                        y: 3
                        width: (parent.width - 6) / 2
                        height: parent.height - 6
                        radius: 9
                        color: root.surface
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
                                Text { anchors.centerIn: parent; text: modelData; color: root.activeInspectorTab === index ? root.ink : root.ink3; font.family: interSemiBold.name || root.font.family; font.pixelSize: 12 }
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
                            // A follow-pointer click has no recorded position, so it can never
                            // belong to the wrong target and never needs recording again.
                            property bool followingPointer: clickAction && followPointerSwitch.checked && desktopTarget
                            property bool needsPointerPosition: mouseAction && !followingPointer
                            property bool targetMismatch: mouseAction && !followingPointer && coordinateSpace !== (desktopTarget ? "screen" : "window")

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
                                coordinateSpace = controller.targetSettings.mode === "window" ? "window" : "screen"
                                referenceWidth = 0
                                referenceHeight = 0
                                referenceWidth2 = 0
                                referenceHeight2 = 0
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
                                font.family: interMedium.name || root.font.family
                                font.pixelSize: 13
                                leftPadding: 13
                                rightPadding: 42
                                onCurrentIndexChanged: {
                                    if (controller.actionCaptureMode !== "")
                                        controller.cancelActionCapture()
                                }
                                contentItem: Text {
                                    text: actionType.displayText
                                    color: root.ink
                                    font: actionType.font
                                    verticalAlignment: Text.AlignVCenter
                                    elide: Text.ElideRight
                                }
                                indicator: Text {
                                    x: actionType.width - width - 14
                                    y: (actionType.height - height) / 2
                                    text: "⌄"
                                    color: root.ink2
                                    font.family: interSemiBold.name || root.font.family
                                    font.pixelSize: 20
                                    rotation: actionType.popup.visible ? 180 : 0
                                    Behavior on rotation { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
                                }
                                background: Rectangle {
                                    radius: 11
                                    color: actionType.hovered || actionType.activeFocus ? "#FFFFFF" : "#F8F9FC"
                                    border.width: actionType.activeFocus || actionType.popup.visible ? 2 : 1
                                    border.color: actionType.activeFocus || actionType.popup.visible ? root.primary : actionType.hovered ? "#BFC9D8" : root.line
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
                                        color: option.highlighted ? root.primary : root.ink
                                        font.family: option.highlighted ? interSemiBold.name : interMedium.name
                                        font.pixelSize: 13
                                        verticalAlignment: Text.AlignVCenter
                                    }
                                    background: Rectangle {
                                        radius: 9
                                        color: option.highlighted ? root.primarySoft : option.hovered ? "#F1F4F9" : "#00F1F4F9"
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
                                        color: root.surface
                                        border.width: 1
                                        border.color: root.line
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
                                color: root.surface2
                                RowLayout {
                                    anchors.fill: parent
                                    anchors.leftMargin: 13
                                    anchors.rightMargin: 10
                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: 2
                                        Text { text: "Follow current pointer"; color: root.ink; font.family: interSemiBold.name || root.font.family; font.pixelSize: 12 }
                                        Text { text: "Click wherever the pointer is during the run"; color: root.ink3; font.family: interRegular.name || root.font.family; font.pixelSize: 9 }
                                    }
                                    Switch { id: followPointerSwitch; objectName: "followPointerSwitch" }
                                }
                            }

                            Rectangle {
                                visible: editor.targetMismatch
                                Layout.fillWidth: true
                                Layout.preferredHeight: visible ? 62 : 0
                                radius: 12
                                color: root.redSoft
                                border.width: 1
                                border.color: "#F2C8D0"
                                Text {
                                    anchors.fill: parent
                                    anchors.margins: 11
                                    wrapMode: Text.WordWrap
                                    text: editor.desktopTarget ? "This position belongs to a background window. Record it again for Desktop mode before saving or running." : "This position belongs to the desktop. Record it again for the selected window before saving or running."
                                    color: root.red
                                    font.family: interMedium.name || root.font.family
                                    font.pixelSize: 10
                                    lineHeight: 1.2
                                }
                            }

                            FormLabel { visible: editor.needsPointerPosition; text: editor.kindValue() === "drag" ? "DRAG START POSITION" : editor.desktopTarget ? "SCREEN POSITION" : "WINDOW POSITION"; Layout.topMargin: 7 }
                            RowLayout {
                                visible: editor.needsPointerPosition
                                Layout.fillWidth: true
                                KField { id: xField; Layout.fillWidth: true; placeholderText: "X"; inputMethodHints: Qt.ImhDigitsOnly }
                                KField { id: yField; Layout.fillWidth: true; placeholderText: "Y"; inputMethodHints: Qt.ImhDigitsOnly }
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
                                color: controller.capturePending ? root.primary : root.ink3
                                font.family: interRegular.name || root.font.family
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
                                    Text { text: "Repeats"; color: root.ink2; font.pixelSize: 11; font.family: interMedium.name || root.font.family }
                                    KField { id: repeatsField; Layout.fillWidth: true; text: "1" }
                                }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 4
                                    Text { text: "Wait after"; color: root.ink2; font.pixelSize: 11; font.family: interMedium.name || root.font.family }
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
                            KButton {
                                objectName: "actionCommitButton"
                                Layout.fillWidth: true
                                Layout.topMargin: 10
                                implicitHeight: 48
                                primary: true
                                enabled: !editor.targetMismatch
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
                            FormLabel { text: "TARGET" }
                            Text { text: "Where should actions run?"; color: root.ink; font.family: interBold.name || root.font.family; font.pixelSize: 17 }
                            Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; text: "Desktop uses your real keyboard and pointer. Background window sends actions only to one selected app."; color: root.ink2; font.family: interRegular.name || root.font.family; font.pixelSize: 11; lineHeight: 1.25 }
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 7
                                KButton {
                                    id: desktopTargetModeButton
                                    objectName: "desktopTargetModeButton"
                                    Layout.fillWidth: true
                                    text: "Desktop"
                                    leading: "▣"
                                    activeNeutral: controller.targetSettings.mode === "desktop"
                                    onClicked: controller.setTargetMode("desktop")
                                }
                                KButton {
                                    id: windowTargetModeButton
                                    objectName: "windowTargetModeButton"
                                    Layout.fillWidth: true
                                    text: "Background"
                                    leading: "▤"
                                    activeNeutral: controller.targetSettings.mode === "window"
                                    onClicked: {
                                        if (controller.setTargetMode("window"))
                                            root.openWindowPicker()
                                    }
                                }
                            }
                            Text {
                                visible: controller.targetSettings.mode === "desktop"
                                Layout.fillWidth: true
                                wrapMode: Text.WordWrap
                                text: "Best for universal compatibility. Pointer actions control the physical mouse."
                                color: root.ink3
                                font.family: interRegular.name || root.font.family
                                font.pixelSize: 10
                            }
                            Rectangle {
                                visible: controller.targetSettings.mode === "window"
                                Layout.fillWidth: true
                                Layout.preferredHeight: visible ? 116 : 0
                                radius: 13
                                color: root.surface2
                                border.width: 1
                                border.color: controller.targetSettings.windowSelected ? "#C9D8F5" : root.line
                                ColumnLayout {
                                    anchors.fill: parent
                                    anchors.margins: 12
                                    spacing: 7
                                    FormLabel { text: controller.targetSettings.windowSelected ? "SELECTED WINDOW" : "NO WINDOW SELECTED" }
                                    Text {
                                        Layout.fillWidth: true
                                        text: controller.targetSettings.displayName
                                        elide: Text.ElideMiddle
                                        color: controller.targetSettings.windowSelected ? root.ink : root.ink3
                                        font.family: interSemiBold.name || root.font.family
                                        font.pixelSize: 12
                                    }
                                    KButton {
                                        objectName: "pickWindowButton"
                                        Layout.fillWidth: true
                                        text: controller.targetSettings.windowSelected ? "Browse open windows" : "Choose a window"
                                        leading: "▦"
                                        onClicked: root.openWindowPicker()
                                    }
                                }
                            }
                            Rectangle {
                                visible: controller.targetSettings.mode === "window"
                                Layout.fillWidth: true
                                Layout.preferredHeight: visible ? 82 : 0
                                radius: 12
                                color: "#FFF8E8"
                                border.width: 1
                                border.color: "#F0D99B"
                                Text {
                                    anchors.fill: parent
                                    anchors.margins: 11
                                    wrapMode: Text.WordWrap
                                    text: "Your pointer remains free and the target may stay behind other windows. Use Test once first. If the target becomes unstable or closes, switch to Desktop mode instead of retrying."
                                    color: "#785A12"
                                    font.family: interMedium.name || root.font.family
                                    font.pixelSize: 10
                                    lineHeight: 1.2
                                }
                            }
                            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: root.line; Layout.topMargin: 9; Layout.bottomMargin: 5 }
                            FormLabel { text: "RUN PLAN" }
                            Text { text: "Choose when it stops"; color: root.ink; font.family: interBold.name || root.font.family; font.pixelSize: 17 }
                            Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; text: "Run a fixed number of cycles or continue until you press Stop."; color: root.ink2; font.family: interRegular.name || root.font.family; font.pixelSize: 11; lineHeight: 1.25 }
                            Rectangle {
                                Layout.fillWidth: true; Layout.preferredHeight: 52; radius: 13; color: root.surface2
                                RowLayout {
                                    anchors.fill: parent
                                    anchors.leftMargin: 13
                                    anchors.rightMargin: 10
                                    Text { Layout.fillWidth: true; text: "Loop indefinitely"; color: root.ink; font.family: interSemiBold.name || root.font.family; font.pixelSize: 12 }
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
                            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: root.line; Layout.topMargin: 10; Layout.bottomMargin: 5 }
                            FormLabel { text: "GLOBAL SHORTCUTS" }
                            Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; text: "Use one key or a combination like ctrl+shift+s."; color: root.ink2; font.family: interRegular.name || root.font.family; font.pixelSize: 11 }
                            RowLayout {
                                Layout.fillWidth: true
                                Text { text: "Start / toggle"; color: root.ink2; font.pixelSize: 11; font.family: interMedium.name || root.font.family; Layout.preferredWidth: 88 }
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
                                Text { text: "Record pointer"; color: root.ink2; font.pixelSize: 11; font.family: interMedium.name || root.font.family; Layout.preferredWidth: 88 }
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
                                Text { text: "Emergency stop"; color: root.ink2; font.pixelSize: 11; font.family: interMedium.name || root.font.family; Layout.preferredWidth: 88 }
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
                                color: root.red
                                font.family: interSemiBold.name || root.font.family
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

    Dialog {
        id: windowPickerDialog
        objectName: "windowPickerDialog"
        parent: Overlay.overlay
        modal: true
        closePolicy: Popup.CloseOnEscape
        width: Math.min(780, root.width - 48)
        height: Math.min(610, root.height - 48)
        x: Math.round((root.width - width) / 2)
        y: Math.round((root.height - height) / 2)
        padding: 0
        onOpened: {
            windowPickerScroll.contentY = 0
            windowPickerScroll.forceActiveFocus()
        }
        background: Rectangle {
            radius: 20
            color: root.surface
            border.width: 1
            border.color: root.line
        }
        contentItem: ColumnLayout {
            spacing: 0

            Item {
                Layout.fillWidth: true
                Layout.preferredHeight: 96
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 22
                    anchors.rightMargin: 16
                    spacing: 12
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 5
                        Text {
                            text: "Choose where KeyClick runs"
                            color: root.ink
                            font.family: interBold.name || root.font.family
                            font.pixelSize: 20
                            font.weight: Font.Bold
                        }
                        Text {
                            Layout.fillWidth: true
                            text: "Use the desktop, or send actions to one open window while your pointer stays free."
                            color: root.ink2
                            elide: Text.ElideRight
                            font.family: interRegular.name || root.font.family
                            font.pixelSize: 11
                        }
                    }
                    KButton {
                        objectName: "windowPickerRefreshButton"
                        Layout.preferredWidth: 94
                        text: "Refresh"
                        leading: "↻"
                        onClicked: controller.refreshWindowEntries()
                    }
                    KButton {
                        objectName: "windowPickerCloseButton"
                        Layout.preferredWidth: 76
                        text: "Close"
                        activeNeutral: true
                        Accessible.name: "Close window picker"
                        onClicked: windowPickerDialog.close()
                    }
                }
            }

            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: root.line }

            Flickable {
                id: windowPickerScroll
                objectName: "windowPickerScroll"
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.rightMargin: 6
                Layout.bottomMargin: 10
                clip: true
                contentWidth: width
                contentHeight: windowPickerContent.implicitHeight
                boundsBehavior: Flickable.StopAtBounds
                maximumFlickVelocity: 3200
                flickDeceleration: 2600
                onContentHeightChanged: Qt.callLater(function() {
                    windowPickerScroll.returnToBounds()
                })
                ScrollBar.vertical: KScrollBar {
                    id: windowPickerScrollBar
                    objectName: "windowPickerScrollBar"
                    topPadding: 8
                    bottomPadding: 14
                }

                ColumnLayout {
                    id: windowPickerContent
                    width: windowPickerScroll.width
                           - (windowPickerScrollBar.visible ? windowPickerScrollBar.width + 8 : 0)
                    spacing: 10

                    FormLabel {
                        text: "ENTIRE SCREEN"
                        Layout.leftMargin: 22
                        Layout.topMargin: 18
                    }

                    AbstractButton {
                        id: desktopWindowChoice
                        objectName: "desktopWindowChoice"
                        Layout.fillWidth: true
                        Layout.preferredHeight: 112
                        Layout.leftMargin: 20
                        Layout.rightMargin: 20
                        hoverEnabled: true
                        Accessible.name: "Use the entire desktop"
                        onClicked: {
                            controller.setTargetMode("desktop")
                            root.closeWindowPicker()
                        }
                        background: Rectangle {
                            radius: 15
                            color: desktopWindowChoice.down ? "#E2ECFF"
                                 : desktopWindowChoice.hovered ? "#F3F7FF" : root.surface
                            border.width: controller.targetSettings.mode === "desktop" ? 2 : 1
                            border.color: controller.targetSettings.mode === "desktop" ? root.primary
                                        : desktopWindowChoice.hovered ? "#B8CCF5" : root.line
                            Behavior on color { ColorAnimation { duration: 120 } }
                            Behavior on border.color { ColorAnimation { duration: 120 } }
                        }
                        contentItem: RowLayout {
                            spacing: 14
                            Rectangle {
                                Layout.preferredWidth: 142
                                Layout.fillHeight: true
                                Layout.margins: 8
                                radius: 11
                                clip: true
                                color: root.surface2
                                Image {
                                    id: desktopPreviewImage
                                    anchors.fill: parent
                                    source: controller.desktopPreviewUrl
                                    visible: status === Image.Ready
                                    fillMode: Image.PreserveAspectCrop
                                    asynchronous: true
                                    cache: false
                                }
                                Item {
                                    anchors.centerIn: parent
                                    visible: desktopPreviewImage.status !== Image.Ready
                                    width: 46
                                    height: 38
                                    Rectangle {
                                        anchors.top: parent.top
                                        anchors.horizontalCenter: parent.horizontalCenter
                                        width: 42
                                        height: 27
                                        radius: 4
                                        color: "transparent"
                                        border.width: 2
                                        border.color: root.primary
                                    }
                                    Rectangle { anchors.horizontalCenter: parent.horizontalCenter; y: 28; width: 3; height: 5; radius: 1; color: root.primary }
                                    Rectangle { anchors.horizontalCenter: parent.horizontalCenter; anchors.bottom: parent.bottom; width: 24; height: 3; radius: 2; color: root.primary }
                                }
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 5
                                Text { text: "Desktop"; color: root.ink; font.family: interBold.name || root.font.family; font.pixelSize: 15 }
                                Text { Layout.fillWidth: true; text: "Controls the real keyboard and pointer across your screens"; color: root.ink2; wrapMode: Text.WordWrap; font.family: interRegular.name || root.font.family; font.pixelSize: 11 }
                            }
                            Rectangle {
                                visible: controller.targetSettings.mode === "desktop"
                                Layout.preferredWidth: 76
                                Layout.preferredHeight: 26
                                Layout.rightMargin: 12
                                radius: 9
                                color: root.primarySoft
                                Text { anchors.centerIn: parent; text: "SELECTED"; color: root.primary; font.family: interSemiBold.name || root.font.family; font.pixelSize: 8; font.letterSpacing: 0.4 }
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.leftMargin: 22
                        Layout.rightMargin: 20
                        Layout.topMargin: 7
                        FormLabel { Layout.fillWidth: true; text: "OPEN WINDOWS" }
                        Text {
                            text: controller.windowEntries.length === 1 ? "1 window" : controller.windowEntries.length + " windows"
                            color: root.ink3
                            font.family: interRegular.name || root.font.family
                            font.pixelSize: 10
                        }
                    }

                    GridLayout {
                        id: windowChoiceGrid
                        Layout.fillWidth: true
                        Layout.leftMargin: 20
                        Layout.rightMargin: 20
                        columns: windowPickerDialog.width >= 700 ? 3 : 2
                        columnSpacing: 10
                        rowSpacing: 10

                        Repeater {
                            model: controller.windowEntries
                            delegate: AbstractButton {
                                id: windowChoice
                                required property var modelData
                                required property int index
                                objectName: "windowChoice_" + index
                                Layout.fillWidth: true
                                Layout.preferredHeight: 176
                                enabled: !modelData.minimized
                                hoverEnabled: true
                                Accessible.name: "Use " + modelData.appName + ", " + modelData.title
                                ToolTip.visible: hovered
                                ToolTip.text: modelData.title
                                onClicked: controller.selectWindowTarget(modelData.handle)
                                background: Rectangle {
                                    radius: 15
                                    color: windowChoice.down ? "#E2ECFF"
                                         : windowChoice.hovered ? "#F3F7FF" : root.surface
                                    border.width: windowChoice.modelData.selected ? 2 : 1
                                    border.color: windowChoice.modelData.selected ? root.primary
                                                : windowChoice.hovered ? "#B8CCF5" : root.line
                                    opacity: windowChoice.enabled ? 1 : 0.58
                                    Behavior on color { ColorAnimation { duration: 120 } }
                                    Behavior on border.color { ColorAnimation { duration: 120 } }
                                }
                                contentItem: ColumnLayout {
                                    spacing: 7
                                    Rectangle {
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: 104
                                        Layout.margins: 7
                                        Layout.bottomMargin: 0
                                        radius: 10
                                        clip: true
                                        color: root.surface2
                                        Image {
                                            id: windowPreviewImage
                                            anchors.fill: parent
                                            source: windowChoice.modelData.previewUrl
                                            visible: status === Image.Ready
                                            fillMode: Image.PreserveAspectCrop
                                            asynchronous: true
                                            cache: false
                                        }
                                        Rectangle {
                                            anchors.fill: parent
                                            visible: windowPreviewImage.status !== Image.Ready
                                            color: root.primarySoft
                                            Text {
                                                anchors.centerIn: parent
                                                text: windowChoice.modelData.appName.length > 0 ? windowChoice.modelData.appName.charAt(0) : "W"
                                                color: root.primary
                                                font.family: interBold.name || root.font.family
                                                font.pixelSize: 28
                                            }
                                        }
                                        Rectangle {
                                            visible: windowChoice.modelData.selected || windowChoice.modelData.minimized
                                            anchors.top: parent.top
                                            anchors.right: parent.right
                                            anchors.margins: 7
                                            implicitWidth: windowStateLabel.implicitWidth + 14
                                            implicitHeight: 22
                                            radius: 8
                                            color: windowChoice.modelData.selected ? root.primary : "#DDE3EC"
                                            Text {
                                                id: windowStateLabel
                                                anchors.centerIn: parent
                                                text: windowChoice.modelData.selected ? "SELECTED" : "RESTORE TO USE"
                                                color: windowChoice.modelData.selected ? "white" : root.ink2
                                                font.family: interSemiBold.name || root.font.family
                                                font.pixelSize: 7
                                                font.letterSpacing: 0.35
                                            }
                                        }
                                    }
                                    Text {
                                        Layout.fillWidth: true
                                        Layout.leftMargin: 10
                                        Layout.rightMargin: 10
                                        text: windowChoice.modelData.appName
                                        elide: Text.ElideRight
                                        color: root.ink
                                        font.family: interSemiBold.name || root.font.family
                                        font.pixelSize: 12
                                    }
                                    Text {
                                        Layout.fillWidth: true
                                        Layout.leftMargin: 10
                                        Layout.rightMargin: 10
                                        Layout.bottomMargin: 8
                                        text: windowChoice.modelData.title
                                        elide: Text.ElideRight
                                        color: root.ink3
                                        font.family: interRegular.name || root.font.family
                                        font.pixelSize: 9
                                    }
                                }
                            }
                        }
                    }

                    Text {
                        visible: controller.windowEntries.length === 0
                        Layout.fillWidth: true
                        Layout.leftMargin: 28
                        Layout.rightMargin: 28
                        Layout.topMargin: 8
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.WordWrap
                        text: "No usable app windows are visible. Open or restore the app, then choose Refresh."
                        color: root.ink3
                        font.family: interRegular.name || root.font.family
                        font.pixelSize: 11
                    }
                    Item { Layout.fillWidth: true; Layout.preferredHeight: 18 }
                }
            }
        }
    }

    Dialog {
        id: recoveryDialog
        objectName: "recoveryDialog"
        modal: true
        closePolicy: Popup.NoAutoClose
        width: 440
        height: 258
        x: Math.round((root.width - width) / 2)
        y: Math.round((root.height - height) / 2)
        padding: 22
        background: Rectangle {
            radius: 18
            color: root.surface
            border.width: 1
            border.color: root.line
        }
        contentItem: ColumnLayout {
            spacing: 10
            Text { text: "Recover your sequence?"; color: root.ink; font.family: interBold.name || root.font.family; font.pixelSize: 20; font.weight: Font.Bold }
            Text {
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                text: "KeyClick found an autosaved recovery copy from the previous session.\n" + controller.draftSummary
                color: root.ink2
                font.family: interRegular.name || root.font.family
                font.pixelSize: 12
                lineHeight: 1.3
            }
            Item { Layout.fillHeight: true; Layout.minimumHeight: 8 }
            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                Item { Layout.fillWidth: true }
                KButton {
                    objectName: "recoveryDiscardButton"
                    Layout.preferredWidth: 88
                    text: "Discard"
                    danger: true
                    onClicked: {
                        controller.discardDraft()
                        recoveryDialog.close()
                    }
                }
                KButton {
                    objectName: "recoveryAcceptButton"
                    Layout.preferredWidth: 148
                    text: "Recover sequence"
                    primary: true
                    onClicked: {
                        if (controller.recoverDraft()) {
                            recoveryDialog.close()
                            if (controller.selectedIndex >= 0) {
                                root.editorIndex = controller.selectedIndex
                                editor.loadAction(controller.selectedIndex)
                            }
                        }
                    }
                }
            }
        }
    }

    Dialog {
        id: unsavedDialog
        objectName: "unsavedChangesDialog"
        modal: true
        closePolicy: Popup.NoAutoClose
        width: 460
        height: 258
        x: Math.round((root.width - width) / 2)
        y: Math.round((root.height - height) / 2)
        padding: 22
        background: Rectangle {
            radius: 18
            color: root.surface
            border.width: 1
            border.color: root.line
        }
        contentItem: ColumnLayout {
            spacing: 10
            Text { text: "Save your changes?"; color: root.ink; font.family: interBold.name || root.font.family; font.pixelSize: 20; font.weight: Font.Bold }
            Text {
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                text: root.pendingDestructiveAction === "close" ? "This sequence has unsaved changes. Save it before closing KeyClick, discard the changes, or return to the editor." : "This sequence has unsaved changes. Save it before continuing, discard the changes, or cancel."
                color: root.ink2
                font.family: interRegular.name || root.font.family
                font.pixelSize: 12
                lineHeight: 1.3
            }
            Item { Layout.fillHeight: true; Layout.minimumHeight: 8 }
            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                KButton {
                    objectName: "unsavedCancelButton"
                    text: "Cancel"
                    Layout.fillWidth: true
                    implicitHeight: 44
                    onClicked: {
                        root.pendingDestructiveAction = ""
                        root.pendingProfilePath = ""
                        unsavedDialog.close()
                    }
                }
                KButton {
                    objectName: "unsavedDiscardButton"
                    text: "Discard"
                    danger: true
                    Layout.fillWidth: true
                    implicitHeight: 44
                    onClicked: {
                        var action = root.pendingDestructiveAction
                        root.pendingDestructiveAction = ""
                        unsavedDialog.close()
                        root.performDestructiveAction(action)
                    }
                }
                KButton {
                    objectName: "unsavedSaveButton"
                    Layout.fillWidth: true
                    implicitHeight: 44
                    text: "Save & continue"
                    primary: true
                    onClicked: {
                        var action = root.pendingDestructiveAction
                        if (root.saveProfileWithVisibleSettings()) {
                            root.pendingDestructiveAction = ""
                            unsavedDialog.close()
                            root.performDestructiveAction(action)
                        }
                    }
                }
            }
        }
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
        color: toast.tone === "error" ? root.redSoft : toast.tone === "success" ? root.successSoft : root.primarySoft
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
            Rectangle { width: 8; height: 8; radius: 4; color: toast.tone === "error" ? root.red : toast.tone === "success" ? root.green : root.primary; anchors.verticalCenter: parent.verticalCenter }
            Text {
                id: toastText
                objectName: "toastText"
                width: Math.min(toast.toastTextLimit, implicitWidth)
                text: toast.message
                wrapMode: Text.WordWrap
                maximumLineCount: 3
                elide: Text.ElideRight
                color: toast.tone === "error" ? root.red : toast.tone === "success" ? root.green : root.ink
                font.family: interSemiBold.name || root.font.family
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
            if (windowPickerDialog.opened && controller.targetSettings.windowSelected)
                root.closeWindowPicker()
            if (root.editorIndex < 0) {
                editor.coordinateSpace = controller.targetSettings.mode === "window" ? "window" : "screen"
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

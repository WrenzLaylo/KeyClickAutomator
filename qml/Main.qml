import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Effects

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
    readonly property bool compactNav: layoutMode !== "wide"
    readonly property bool overlayInspector: layoutMode === "compact"
    property bool inspectorOpen: !overlayInspector
    property int activeInspectorTab: 0
    property int editorIndex: -1
    property string shortcutRecordingTarget: ""

    readonly property color ink: "#171A21"
    readonly property color ink2: "#4B5363"
    readonly property color ink3: "#7B8494"
    readonly property color canvas: "#F3F5F9"
    readonly property color surface: "#FFFFFF"
    readonly property color surface2: "#EEF1F6"
    readonly property color surface3: "#E5EAF2"
    readonly property color line: "#D9DFE8"
    readonly property color blue: "#1565FF"
    readonly property color blueHover: "#0759EB"
    readonly property color blueSoft: "#E8F0FF"
    readonly property color violet: "#7454F6"
    readonly property color green: "#148A5B"
    readonly property color red: "#D33C54"
    readonly property color redSoft: "#FFF0F3"
    readonly property color amber: "#B76812"
    readonly property color successSoft: "#E9F7F1"

    FontLoader { id: interRegular; source: "../assets/fonts/Inter-Regular.ttf" }
    FontLoader { id: interMedium; source: "../assets/fonts/Inter-Medium.ttf" }
    FontLoader { id: interSemiBold; source: "../assets/fonts/Inter-SemiBold.ttf" }
    FontLoader { id: interBold; source: "../assets/fonts/Inter-Bold.ttf" }

    font.family: interRegular.name || "Segoe UI"

    Behavior on opacity { NumberAnimation { duration: 260; easing.type: Easing.OutCubic } }
    Component.onCompleted: opacity = 1
    onOverlayInspectorChanged: inspectorOpen = !overlayInspector
    onClosing: controller.shutdown()

    function toneColor(tone) {
        if (tone === "accent") return blue
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

    component KButton: Button {
        id: control
        property bool primary: false
        property bool danger: false
        property bool quiet: false
        property bool navStyle: false
        property string leading: ""
        property bool pointerHover: false
        implicitHeight: 42
        implicitWidth: 112
        padding: 12
        hoverEnabled: true
        HoverHandler {
            onHoveredChanged: control.pointerHover = hovered
        }
        font.family: interSemiBold.name || root.font.family
        font.pixelSize: 13
        font.weight: Font.DemiBold
        contentItem: Row {
            spacing: control.leading ? 8 : 0
            anchors.centerIn: parent
            Text {
                visible: control.leading !== ""
                text: control.leading
                color: control.enabled ? (control.primary ? "white" : control.danger ? root.red : control.navStyle && control.pointerHover ? root.blue : root.ink) : root.ink3
                font.family: interSemiBold.name || root.font.family
                font.pixelSize: 15
                anchors.verticalCenter: parent.verticalCenter
            }
            Text {
                text: control.text
                color: control.enabled ? (control.primary ? "white" : control.danger ? root.red : control.navStyle && control.pointerHover ? root.blue : root.ink) : root.ink3
                font: control.font
                anchors.verticalCenter: parent.verticalCenter
            }
        }
        background: Rectangle {
            radius: 12
            color: !control.enabled ? root.surface2
                 : control.down ? (control.primary ? "#0049C9" : root.surface3)
                 : control.pointerHover ? (control.primary ? root.blueHover : control.danger ? "#FDECEF" : control.navStyle ? root.blueSoft : root.surface3)
                 : control.primary ? root.blue : control.quiet ? "transparent" : control.danger ? "#FFF2F4" : root.surface2
            border.width: control.visualFocus ? 2 : 0
            border.color: root.blue
            scale: control.down ? 0.975 : 1
            Behavior on color { ColorAnimation { duration: 130 } }
            Behavior on scale { NumberAnimation { duration: 100; easing.type: Easing.OutQuad } }
        }
    }

    component KField: TextField {
        id: field
        implicitHeight: 44
        leftPadding: 13
        rightPadding: 13
        selectByMouse: true
        font.family: interMedium.name || root.font.family
        font.pixelSize: 13
        color: root.ink
        placeholderTextColor: root.ink3
        selectionColor: root.blue
        background: Rectangle {
            radius: 11
            color: field.activeFocus ? "#FFFFFF" : "#F8F9FC"
            border.width: field.activeFocus ? 2 : 1
            border.color: field.activeFocus ? root.blue : root.line
            Behavior on border.color { ColorAnimation { duration: 120 } }
            Behavior on color { ColorAnimation { duration: 120 } }
        }
    }

    component FormLabel: Text {
        font.family: interSemiBold.name || root.font.family
        font.pixelSize: 10
        font.weight: Font.DemiBold
        font.letterSpacing: 0.8
        color: root.ink3
    }

    component KeyCap: Rectangle {
        property string keyText: "F6"
        implicitWidth: Math.max(42, keyLabel.implicitWidth + 18)
        implicitHeight: 25
        radius: 7
        color: root.surface3
        border.width: 1
        border.color: "#D5DBE5"
        Text {
            id: keyLabel
            anchors.centerIn: parent
            text: parent.keyText.toUpperCase()
            color: root.ink
            font.family: interSemiBold.name || root.font.family
            font.pixelSize: 10
        }
    }

    // A restrained ambient wash gives depth without fake glass or gradients on controls.
    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0; color: "#F3F6FB" }
            GradientStop { position: 0.58; color: "#F4F5F9" }
            GradientStop { position: 1; color: "#F7F7FA" }
        }
    }
    Rectangle {
        width: 420; height: 420; radius: 210
        x: root.width * 0.42; y: -290
        color: "#0F6B8FFF"
        SequentialAnimation on opacity {
            loops: Animation.Infinite
            NumberAnimation { from: 0.06; to: 0.035; duration: 2600; easing.type: Easing.InOutSine }
            NumberAnimation { to: 0.07; duration: 2600; easing.type: Easing.InOutSine }
        }
    }

    Item {
        id: appShell
        anchors.fill: parent

        Rectangle {
            id: navigation
            width: root.compactNav ? 76 : 216
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            color: "#EBEEF4"
            Behavior on width { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: root.compactNav ? 12 : 16
                spacing: 6

                Item {
                    Layout.fillWidth: true
                    Layout.preferredHeight: root.compactNav ? 72 : 104
                    Rectangle {
                        width: 44; height: 44; radius: 14
                        anchors.left: parent.left
                        anchors.top: parent.top
                        anchors.topMargin: 8
                        color: root.blue
                        layer.enabled: true
                        layer.effect: SoftShadow {}
                        Image {
                            anchors.fill: parent
                            anchors.margins: 5
                            source: "../assets/app-logo.png"
                            fillMode: Image.PreserveAspectFit
                            smooth: true
                            mipmap: true
                        }
                    }
                    Column {
                        visible: !root.compactNav
                        anchors.left: parent.left
                        anchors.top: parent.top
                        anchors.topMargin: 60
                        spacing: 2
                        Text { text: "KeyClick"; color: root.ink; font.family: interBold.name || root.font.family; font.pixelSize: 18; font.weight: Font.Bold }
                        Text { text: "AUTOMATOR  ·  " + Qt.application.version; color: root.ink3; font.family: interSemiBold.name || root.font.family; font.pixelSize: 10; font.letterSpacing: 0.6 }
                    }
                }

                FormLabel { visible: !root.compactNav; text: "WORKSPACE"; Layout.leftMargin: 4; Layout.topMargin: 8 }

                KButton {
                    objectName: "workspaceNav_open"
                    Layout.fillWidth: true
                    implicitHeight: 42
                    text: root.compactNav ? "" : "Open profile"
                    leading: "↗"
                    quiet: true
                    navStyle: true
                    ToolTip.visible: pointerHover && root.compactNav
                    ToolTip.text: "Open profile"
                    onClicked: controller.openProfile()
                }
                KButton {
                    objectName: "workspaceNav_save"
                    Layout.fillWidth: true
                    implicitHeight: 42
                    text: root.compactNav ? "" : "Save profile"
                    leading: "↓"
                    quiet: true
                    navStyle: true
                    ToolTip.visible: pointerHover && root.compactNav
                    ToolTip.text: "Save profile"
                    onClicked: controller.saveProfile()
                }
                KButton {
                    objectName: "workspaceNav_new"
                    Layout.fillWidth: true
                    implicitHeight: 42
                    text: root.compactNav ? "" : "New sequence"
                    leading: "+"
                    quiet: true
                    navStyle: true
                    ToolTip.visible: pointerHover && root.compactNav
                    ToolTip.text: "New sequence"
                    onClicked: controller.clearActions()
                }

                Item { Layout.fillHeight: true }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: root.compactNav ? 178 : 164
                    radius: 16
                    color: "#F7F8FB"
                    border.width: 1
                    border.color: "#E2E6ED"
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: root.compactNav ? 9 : 12
                        spacing: 7
                        FormLabel { visible: !root.compactNav; text: "GLOBAL CONTROL" }
                        Repeater {
                            model: [
                                {key: controller.runSettings.startHotkey, label: "Start"},
                                {key: controller.runSettings.captureHotkey, label: "Capture"},
                                {key: controller.runSettings.stopHotkey, label: "Stop"}
                            ]
                            delegate: RowLayout {
                                required property var modelData
                                Layout.fillWidth: true
                                KeyCap { keyText: modelData.key; Layout.alignment: Qt.AlignHCenter }
                                Text {
                                    visible: !root.compactNav
                                    text: modelData.label
                                    color: root.ink2
                                    font.family: interMedium.name || root.font.family
                                    font.pixelSize: 11
                                }
                            }
                        }
                        Text {
                            visible: !root.compactNav
                            Layout.fillWidth: true
                            text: "Corner fail-safe is always active."
                            wrapMode: Text.WordWrap
                            color: root.ink3
                            font.family: interRegular.name || root.font.family
                            font.pixelSize: 10
                        }
                    }
                }
            }
        }

        Item {
            id: workspace
            anchors.left: navigation.right
            anchors.right: (!root.overlayInspector || root.inspectorOpen) ? inspector.left : parent.right
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            clip: true
            Behavior on anchors.rightMargin { NumberAnimation { duration: 180 } }

            ColumnLayout {
                anchors.fill: parent
                anchors.leftMargin: root.layoutMode === "wide" ? 28 : 22
                anchors.rightMargin: root.layoutMode === "wide" ? 28 : 22
                anchors.topMargin: 22
                anchors.bottomMargin: 18
                spacing: 12

                RowLayout {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 68
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 3
                        Text {
                            text: "Sequence builder"
                            color: root.ink
                            font.family: interBold.name || root.font.family
                            font.pixelSize: root.layoutMode === "compact" ? 24 : 28
                            font.weight: Font.Bold
                        }
                        Text {
                            text: controller.currentProfileName + "  ·  " + controller.summary
                            color: root.ink2
                            font.family: interRegular.name || root.font.family
                            font.pixelSize: 12
                        }
                    }
                    Rectangle {
                        implicitWidth: statusRow.implicitWidth + 22
                        implicitHeight: 34
                        radius: 11
                        color: controller.statusTone === "success" ? "#E8F7F0" : controller.statusTone === "danger" ? "#FFF0F2" : controller.statusTone === "accent" ? root.blueSoft : root.surface2
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
                    KButton {
                        visible: root.overlayInspector
                        text: "Inspector"
                        leading: "⚙"
                        onClicked: root.inspectorOpen = !root.inspectorOpen
                    }
                }

                Rectangle {
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
                        KButton { visible: controller.selectedIndex >= 0 && workspace.width > 540; quiet: true; text: "Up"; leading: "↑"; implicitWidth: 66; onClicked: controller.moveAction(controller.selectedIndex, -1) }
                        KButton { visible: controller.selectedIndex >= 0 && workspace.width > 610; quiet: true; text: "Down"; leading: "↓"; implicitWidth: 76; onClicked: controller.moveAction(controller.selectedIndex, 1) }
                        KButton { visible: controller.selectedIndex >= 0; quiet: true; text: workspace.width > 680 ? "Duplicate" : ""; leading: "⧉"; implicitWidth: workspace.width > 680 ? 98 : 42; onClicked: controller.duplicateAction(controller.selectedIndex) }
                        KButton { visible: controller.selectedIndex >= 0; danger: true; quiet: true; text: workspace.width > 680 ? "Delete" : ""; leading: "×"; implicitWidth: workspace.width > 680 ? 78 : 42; onClicked: controller.deleteAction(controller.selectedIndex) }
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
                    layer.enabled: true
                    layer.effect: MultiEffect { shadowEnabled: true; shadowColor: "#120B1730"; shadowBlur: 0.45; shadowVerticalOffset: 4 }

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
                            Text { anchors.centerIn: parent; text: "+"; color: root.blue; font.family: interSemiBold.name || root.font.family; font.pixelSize: 28 }
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
                            onClicked: {
                                root.activeInspectorTab = 0
                                root.inspectorOpen = true
                                controller.addAction(editor.payload())
                                editor.reset()
                            }
                        }
                    }

                    ListView {
                        id: actionList
                        objectName: "actionList"
                        visible: count > 0
                        anchors.fill: parent
                        anchors.margins: 12
                        spacing: 8
                        clip: true
                        model: controller.actionModel
                        boundsBehavior: Flickable.StopAtBounds
                        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                        delegate: Rectangle {
                            id: actionCard
                            required property string title
                            required property string subtitle
                            required property bool enabled
                            required property int actionIndex
                            required property string actionIcon
                            width: ListView.view.width
                            height: 74
                            radius: 15
                            color: controller.selectedIndex === actionIndex ? "#E4EDFF" : hover.hovered ? "#F2F5FA" : "#FAFBFD"
                            border.width: 1
                            border.color: controller.selectedIndex === actionIndex ? "#8CB1FF" : hover.hovered ? "#DDE4EE" : "#EEF1F5"
                            opacity: enabled ? 1 : 0.48
                            scale: tap.pressed ? 0.992 : 1
                            Behavior on color { ColorAnimation { duration: 130 } }
                            Behavior on scale { NumberAnimation { duration: 90 } }
                            HoverHandler { id: hover }
                            Rectangle {
                                id: selectedStripe
                                visible: controller.selectedIndex === actionCard.actionIndex
                                width: 4
                                radius: 2
                                color: root.blue
                                anchors.left: parent.left
                                anchors.leftMargin: 4
                                anchors.top: parent.top
                                anchors.topMargin: 10
                                anchors.bottom: parent.bottom
                                anchors.bottomMargin: 10
                            }
                            TapHandler {
                                id: tap
                                onTapped: {
                                    controller.selectedIndex = actionCard.actionIndex
                                    root.editorIndex = actionCard.actionIndex
                                    editor.loadAction(actionCard.actionIndex)
                                    root.activeInspectorTab = 0
                                    root.inspectorOpen = true
                                }
                            }
                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 13
                                anchors.rightMargin: 13
                                spacing: 12
                                Rectangle {
                                    Layout.preferredWidth: 42
                                    Layout.preferredHeight: 42
                                    radius: 13
                                    color: controller.selectedIndex === actionCard.actionIndex ? "#D8E6FF" : root.surface3
                                    Text { anchors.centerIn: parent; text: actionCard.actionIcon; color: root.blue; font.family: interBold.name || root.font.family; font.pixelSize: actionCard.actionIcon.length > 1 ? 11 : 15 }
                                }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 3
                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 8
                                        Text { text: "Sequence " + (actionCard.actionIndex + 1); color: controller.selectedIndex === actionCard.actionIndex ? root.blue : root.ink3; font.family: interSemiBold.name || root.font.family; font.pixelSize: 10; font.letterSpacing: 0.4 }
                                        Text { Layout.fillWidth: true; text: actionCard.title; elide: Text.ElideRight; color: root.ink; font.family: interSemiBold.name || root.font.family; font.pixelSize: 13 }
                                    }
                                    Text { Layout.fillWidth: true; text: actionCard.subtitle; elide: Text.ElideRight; color: root.ink3; font.family: interRegular.name || root.font.family; font.pixelSize: 11 }
                                }
                                Switch {
                                    id: enabledSwitch
                                    checked: actionCard.enabled
                                    onToggled: controller.setActionEnabled(actionCard.actionIndex, checked)
                                    indicator: Rectangle {
                                        implicitWidth: 38; implicitHeight: 22; radius: 11
                                        color: enabledSwitch.checked ? root.blue : "#CAD0DA"
                                        Behavior on color { ColorAnimation { duration: 140 } }
                                        Rectangle {
                                            width: 18; height: 18; radius: 9; y: 2
                                            x: enabledSwitch.checked ? 18 : 2
                                            color: "white"
                                            Behavior on x { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 78
                    radius: 18
                    color: root.surface
                    layer.enabled: true
                    layer.effect: SoftShadow {}
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
                                text: controller.running ? (controller.progress < 0 ? "Looping until you stop it" : "Automation is active") : (actionList.count > 0 ? "Ready when you are" : "Add an action to begin")
                                elide: Text.ElideRight
                                color: root.ink2
                                font.family: interMedium.name || root.font.family
                                font.pixelSize: 12
                            }
                        }
                        Item {
                            visible: workspace.width > 520
                            Layout.preferredWidth: 120
                            Layout.preferredHeight: 6
                            Rectangle { anchors.fill: parent; radius: 3; color: root.surface3 }
                            Rectangle {
                                height: parent.height; radius: 3; color: root.blue
                                width: controller.progress < 0 ? 34 : parent.width * Math.max(0, Math.min(1, controller.progress))
                                x: controller.progress < 0 ? 0 : 0
                                SequentialAnimation on x {
                                    running: controller.progress < 0
                                    loops: Animation.Infinite
                                    NumberAnimation { from: 0; to: 86; duration: 760; easing.type: Easing.InOutCubic }
                                    NumberAnimation { from: 86; to: 0; duration: 760; easing.type: Easing.InOutCubic }
                                }
                                Behavior on width { NumberAnimation { duration: 180 } }
                            }
                        }
                        KButton { text: "Stop"; leading: "■"; danger: true; enabled: controller.running; implicitWidth: 94; onClicked: controller.stopRun() }
                        KButton { text: controller.running ? "Running" : "Start"; leading: controller.running ? "●" : "▶"; primary: true; enabled: !controller.running; implicitWidth: root.layoutMode === "compact" ? 96 : 116; onClicked: controller.startRun() }
                    }
                }
            }
        }

        Rectangle {
            visible: root.overlayInspector && root.inspectorOpen
            anchors.fill: parent
            color: "#42111A2D"
            opacity: root.inspectorOpen ? 1 : 0
            z: 9
            Behavior on opacity { NumberAnimation { duration: 160 } }
            TapHandler { onTapped: root.inspectorOpen = false }
        }

        Rectangle {
            id: inspector
            width: root.layoutMode === "wide" ? 368 : root.layoutMode === "medium" ? 340 : Math.min(380, root.width - 84)
            x: root.overlayInspector ? (root.inspectorOpen ? root.width - width : root.width + 8) : root.width - width
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            color: "#FCFCFE"
            z: 10
            clip: true
            layer.enabled: root.overlayInspector
            layer.effect: SoftShadow {}
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
                        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                        ColumnLayout {
                            id: editor
                            width: editorFlick.width - 8
                            spacing: 7
                            property bool mouseAction: ["left_click", "right_click", "double_click", "middle_click", "scroll", "drag"].indexOf(kindValue()) >= 0

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
                                durationField.text = a.duration || 0.4
                                repeatsField.text = a.repeats || 1
                                delayField.text = a.delay === undefined ? 0.1 : a.delay
                            }
                            function payload() {
                                return {kind: kindValue(), value: valueField.text, x: xField.text, y: yField.text, x2: x2Field.text, y2: y2Field.text, amount: amountField.text, duration: durationField.text, repeats: repeatsField.text, delay: delayField.text, enabled: true}
                            }
                            Component.onCompleted: reset()

                            KButton { Layout.fillWidth: true; text: root.editorIndex >= 0 ? "Editing action " + (root.editorIndex + 1) : "New action"; leading: root.editorIndex >= 0 ? "✦" : "+"; onClicked: editor.reset() }
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
                                    border.color: actionType.activeFocus || actionType.popup.visible ? root.blue : actionType.hovered ? "#BFC9D8" : root.line
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
                                        color: option.highlighted ? root.blue : root.ink
                                        font.family: option.highlighted ? interSemiBold.name : interMedium.name
                                        font.pixelSize: 13
                                        verticalAlignment: Text.AlignVCenter
                                    }
                                    background: Rectangle {
                                        radius: 9
                                        color: option.highlighted ? root.blueSoft : option.hovered ? "#F1F4F9" : "transparent"
                                        Behavior on color { ColorAnimation { duration: 100 } }
                                    }
                                    onClicked: {
                                        actionType.currentIndex = index
                                        actionType.popup.close()
                                    }
                                }
                                popup: Popup {
                                    objectName: "actionTypePopup"
                                    parent: Overlay.overlay
                                    x: actionType.mapToItem(Overlay.overlay, 0, 0).x
                                    y: actionType.mapToItem(Overlay.overlay, 0, actionType.height + 6).y
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
                                        layer.enabled: true
                                        layer.effect: SoftShadow {}
                                    }
                                }
                            }

                            FormLabel { visible: !editor.mouseAction; text: editor.kindValue() === "text" ? "TEXT TO TYPE" : "KEY OR SHORTCUT"; Layout.topMargin: 7 }
                            KField { id: valueField; visible: !editor.mouseAction; Layout.fillWidth: true; placeholderText: editor.kindValue() === "hotkey" ? "ctrl+shift+s" : editor.kindValue() === "text" ? "Type something…" : "space" }
                            KButton {
                                visible: editor.kindValue() === "key"
                                Layout.fillWidth: true
                                text: "Listen for a key"
                                leading: "⌨"
                                onClicked: controller.recordActionKey()
                            }

                            FormLabel { visible: editor.mouseAction; text: "SCREEN POSITION"; Layout.topMargin: 7 }
                            RowLayout {
                                visible: editor.mouseAction
                                Layout.fillWidth: true
                                KField { id: xField; Layout.fillWidth: true; placeholderText: "X"; inputMethodHints: Qt.ImhDigitsOnly }
                                KField { id: yField; Layout.fillWidth: true; placeholderText: "Y"; inputMethodHints: Qt.ImhDigitsOnly }
                            }
                            KButton { visible: editor.mouseAction; Layout.fillWidth: true; text: "Capture current pointer"; leading: "⌖"; onClicked: controller.capturePosition(0) }

                            FormLabel { visible: editor.kindValue() === "drag"; text: "DRAG DESTINATION"; Layout.topMargin: 7 }
                            RowLayout {
                                visible: editor.kindValue() === "drag"
                                Layout.fillWidth: true
                                KField { id: x2Field; Layout.fillWidth: true; placeholderText: "X"; inputMethodHints: Qt.ImhDigitsOnly }
                                KField { id: y2Field; Layout.fillWidth: true; placeholderText: "Y"; inputMethodHints: Qt.ImhDigitsOnly }
                            }
                            KButton { visible: editor.kindValue() === "drag"; Layout.fillWidth: true; text: "Capture destination"; leading: "⌖"; onClicked: controller.capturePosition(1) }

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
                            KButton {
                                Layout.fillWidth: true
                                Layout.topMargin: 10
                                implicitHeight: 48
                                primary: true
                                text: root.editorIndex >= 0 ? "Update action" : "Add to sequence"
                                leading: root.editorIndex >= 0 ? "✓" : "+"
                                onClicked: {
                                    if (root.editorIndex >= 0) controller.updateAction(root.editorIndex, editor.payload())
                                    else controller.addAction(editor.payload())
                                    if (root.editorIndex < 0) editor.reset()
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
                        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                        ColumnLayout {
                            id: runForm
                            width: runFlick.width - 8
                            spacing: 7
                            function apply() {
                                controller.applyRunSettings({repeatForever: foreverSwitch.checked, repeatCount: repeatCount.text, startDelay: startDelay.text, cycleInterval: cycleInterval.text, textInterval: textInterval.text, jitter: jitter.text, startHotkey: startHotkey.text, captureHotkey: captureHotkey.text, stopHotkey: stopHotkey.text})
                            }
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
                                    Switch { id: foreverSwitch; checked: controller.runSettings.repeatForever }
                                }
                            }
                            FormLabel { text: "REPEAT CYCLES"; Layout.topMargin: 7 }
                            KField { id: repeatCount; Layout.fillWidth: true; text: controller.runSettings.repeatCount; enabled: !foreverSwitch.checked }
                            FormLabel { text: "START COUNTDOWN"; Layout.topMargin: 7 }
                            KField { id: startDelay; Layout.fillWidth: true; text: controller.runSettings.startDelay }
                            FormLabel { text: "BETWEEN CYCLES"; Layout.topMargin: 7 }
                            KField { id: cycleInterval; Layout.fillWidth: true; text: controller.runSettings.cycleInterval }
                            RowLayout {
                                Layout.fillWidth: true
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 4
                                    FormLabel { text: "TYPING INTERVAL" }
                                    KField { id: textInterval; Layout.fillWidth: true; text: controller.runSettings.textInterval }
                                }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 4
                                    FormLabel { text: "VARIATION ±" }
                                    KField { id: jitter; Layout.fillWidth: true; text: controller.runSettings.jitter }
                                }
                            }
                            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: root.line; Layout.topMargin: 10; Layout.bottomMargin: 5 }
                            FormLabel { text: "GLOBAL SHORTCUTS" }
                            Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; text: "Use one key or a combination like ctrl+shift+s."; color: root.ink2; font.family: interRegular.name || root.font.family; font.pixelSize: 11 }
                            RowLayout {
                                Layout.fillWidth: true
                                Text { text: "Start / toggle"; color: root.ink2; font.pixelSize: 11; font.family: interMedium.name || root.font.family; Layout.preferredWidth: 88 }
                                KField { id: startHotkey; objectName: "startHotkeyField"; Layout.fillWidth: true; text: controller.runSettings.startHotkey }
                                KButton {
                                    objectName: "shortcutRecord_start"
                                    implicitWidth: 78
                                    text: root.shortcutRecordingTarget === "start" ? "Press…" : "Record"
                                    leading: root.shortcutRecordingTarget === "start" ? "●" : "⌨"
                                    primary: root.shortcutRecordingTarget === "start"
                                    onClicked: if (controller.recordGlobalShortcut("start")) root.shortcutRecordingTarget = "start"
                                }
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                Text { text: "Capture"; color: root.ink2; font.pixelSize: 11; font.family: interMedium.name || root.font.family; Layout.preferredWidth: 88 }
                                KField { id: captureHotkey; objectName: "captureHotkeyField"; Layout.fillWidth: true; text: controller.runSettings.captureHotkey }
                                KButton {
                                    objectName: "shortcutRecord_capture"
                                    implicitWidth: 78
                                    text: root.shortcutRecordingTarget === "capture" ? "Press…" : "Record"
                                    leading: root.shortcutRecordingTarget === "capture" ? "●" : "⌨"
                                    primary: root.shortcutRecordingTarget === "capture"
                                    onClicked: if (controller.recordGlobalShortcut("capture")) root.shortcutRecordingTarget = "capture"
                                }
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                Text { text: "Emergency stop"; color: root.ink2; font.pixelSize: 11; font.family: interMedium.name || root.font.family; Layout.preferredWidth: 88 }
                                KField { id: stopHotkey; objectName: "stopHotkeyField"; Layout.fillWidth: true; text: controller.runSettings.stopHotkey }
                                KButton {
                                    objectName: "shortcutRecord_stop"
                                    implicitWidth: 78
                                    text: root.shortcutRecordingTarget === "stop" ? "Press…" : "Record"
                                    leading: root.shortcutRecordingTarget === "stop" ? "●" : "⌨"
                                    primary: root.shortcutRecordingTarget === "stop"
                                    onClicked: if (controller.recordGlobalShortcut("stop")) root.shortcutRecordingTarget = "stop"
                                }
                            }
                            KButton { Layout.fillWidth: true; Layout.topMargin: 8; primary: true; text: "Apply run settings"; leading: "✓"; onClicked: runForm.apply() }
                            Item { Layout.preferredHeight: 12 }
                        }
                    }
                }
            }
        }
    }

    Rectangle {
        id: toast
        width: Math.min(380, toastText.implicitWidth + 54)
        height: 48
        radius: 14
        color: toast.tone === "error" ? root.redSoft : toast.tone === "success" ? root.successSoft : root.blueSoft
        border.width: 1
        border.color: toast.tone === "error" ? "#F3B8C2" : toast.tone === "success" ? "#A9DFC9" : "#B9CEFA"
        anchors.horizontalCenter: parent.horizontalCenter
        y: visible ? parent.height - 76 : parent.height + 16
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
            Rectangle { width: 8; height: 8; radius: 4; color: toast.tone === "error" ? root.red : toast.tone === "success" ? root.green : root.blue; anchors.verticalCenter: parent.verticalCenter }
            Text { id: toastText; text: toast.message; color: toast.tone === "error" ? root.red : toast.tone === "success" ? root.green : root.ink; font.family: interSemiBold.name || root.font.family; font.pixelSize: 12; anchors.verticalCenter: parent.verticalCenter }
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
        function onPositionCaptured(target, x, y) {
            if (target === 0) { xField.text = x; yField.text = y }
            else { x2Field.text = x; y2Field.text = y }
        }
        function onActionKeyCaptured(value) {
            valueField.text = value
        }
        function onShortcutCaptured(target, value) {
            if (target === "start") startHotkey.text = value
            else if (target === "capture") captureHotkey.text = value
            else if (target === "stop") stopHotkey.text = value
            root.shortcutRecordingTarget = ""
        }
        function onRunSettingsChanged() {
            startHotkey.text = controller.runSettings.startHotkey
            captureHotkey.text = controller.runSettings.captureHotkey
            stopHotkey.text = controller.runSettings.stopHotkey
        }
    }
}

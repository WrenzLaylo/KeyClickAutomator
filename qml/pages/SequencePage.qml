import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import qml
import "../components"

/*
  The sequence editor: what the profile is called, what it will do, and the
  cards you reorder to change that.

  `app` is the application root. `runForm` is the inspector's run-settings form,
  passed in because Test and From-here run with what is currently typed there.
  `actionCount` and `listSpacing` are published back out because the run bar and
  the drag maths both need to know about a list this page owns.
*/
Item {
    property var app
    property var runForm

    id: page
    objectName: "sequencePage"
    readonly property alias actionCount: actionList.count
    readonly property alias listSpacing: actionList.spacing

    ColumnLayout {
        anchors.fill: parent
        anchors.leftMargin: app.layoutMode === "wide" ? 28 : 22
        anchors.rightMargin: app.layoutMode === "wide" ? 28 : 22
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
                    font.pixelSize: app.layoutMode === "compact" ? 24 : 28
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
                visible: app.overlayInspector
                anchors.right: statusBadge.left
                anchors.rightMargin: 12
                anchors.verticalCenter: statusBadge.verticalCenter
                text: "Inspector"
                leading: "⚙"
                onClicked: app.inspectorOpen = !app.inspectorOpen
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
                    text: page.width > 760 ? "Undo" : ""
                    leading: "↶"
                    implicitWidth: page.width > 760 ? 72 : 42
                    onClicked: controller.undoDelete()
                }
                KButton {
                    objectName: "testActionButton"
                    visible: controller.selectedIndex >= 0 && page.width > 500
                    enabled: !controller.running
                    quiet: true
                    text: page.width > 800 ? "Test" : ""
                    leading: "1×"
                    implicitWidth: page.width > 800 ? 68 : 42
                    onClicked: controller.testActionWithSettings(controller.selectedIndex, runForm.payload())
                }
                KButton {
                    objectName: "runFromHereButton"
                    visible: controller.selectedIndex >= 0 && page.width > 540
                    enabled: !controller.running
                    quiet: true
                    text: page.width > 860 ? "From here" : ""
                    leading: "▶"
                    implicitWidth: page.width > 860 ? 104 : 42
                    onClicked: controller.startRunFromWithSettings(controller.selectedIndex, runForm.payload())
                }
                KButton { visible: controller.selectedIndex >= 0 && page.width > 610; enabled: !controller.running; quiet: true; text: "Up"; leading: "↑"; implicitWidth: 66; onClicked: controller.moveAction(controller.selectedIndex, -1) }
                KButton { visible: controller.selectedIndex >= 0 && page.width > 680; enabled: !controller.running; quiet: true; text: "Down"; leading: "↓"; implicitWidth: 76; onClicked: controller.moveAction(controller.selectedIndex, 1) }
                KButton { visible: controller.selectedIndex >= 0; enabled: !controller.running; quiet: true; text: page.width > 760 ? "Duplicate" : ""; leading: "⧉"; implicitWidth: page.width > 760 ? 98 : 42; onClicked: controller.duplicateAction(controller.selectedIndex) }
                KButton { visible: controller.selectedIndex >= 0; enabled: !controller.running; danger: true; quiet: true; text: page.width > 760 ? "Delete" : ""; leading: "×"; implicitWidth: page.width > 760 ? 78 : 42; onClicked: controller.deleteAction(controller.selectedIndex) }
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
                     onClicked: app.beginNewAction()
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
                        visible: app.draggedActionIndex >= 0
                              && app.draggedActionIndex !== actionCard.actionIndex
                              && app.dragTargetIndex === actionCard.actionIndex
                        z: 30
                        x: 46
                        y: app.draggedActionIndex < actionCard.actionIndex ? actionCard.height - height : 0
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
                            app.activeInspectorTab = 0
                            app.inspectorOpen = true
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
                                            app.beginSequenceDrag(actionCard.actionIndex)
                                            app.updateSequenceDrag(actionCard.actionIndex, translation.y)
                                        } else {
                                            app.finishSequenceDrag(actionCard.actionIndex)
                                        }
                                    }
                                    onTranslationChanged: {
                                        if (active)
                                            app.updateSequenceDrag(actionCard.actionIndex, translation.y)
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

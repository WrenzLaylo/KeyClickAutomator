import QtQuick
import QtQuick.Layouts
import qml

/*
  The bar pinned to the bottom of every tab: what the run is doing, the global
  shortcuts, and Start/Stop.

  `app` is the application root. `runForm` is the inspector's run-settings form,
  passed in because the bar starts a run with whatever is currently typed there
  rather than with what was last applied. `actionCount` comes from the sequence
  page for the same reason -- the bar reports on a list it does not own.
*/
Rectangle {
    property var app
    property var runForm
    property int actionCount: 0

    id: bar
    objectName: "runBar"
    // The form is assigned by the caller, so treat "not wired up yet" as clean
    // instead of letting the binding throw on the way up.
    readonly property bool shortcutConflict: runForm ? runForm.shortcutValidation.hasConflict : false
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
                text: controller.capturePending ? "Pick a point on the frozen screen · Esc cancels" : controller.running ? controller.status : controller.preflightBlocked ? controller.preflightSummary : controller.canRun ? "Ready when you are" : (bar.actionCount > 0 ? "Enable an action to begin" : "Add an action to begin")
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
            visible: bar.app.width >= 1000
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
                            visible: bar.app.layoutMode === "wide"
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
            Layout.preferredWidth: bar.app.layoutMode === "compact" ? 280 : 288
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
                    text: controller.running ? "Running" : bar.shortcutConflict ? "Fix shortcuts" : controller.preflightBlocked ? "Not ready" : controller.runSettingsPending ? "Apply & start" : "Start"
                    leading: controller.running ? "●" : "▶"
                    keyHint: controller.runSettings.startHotkey
                    primary: true
                    enabled: !controller.running && controller.canRun && !controller.preflightBlocked && !bar.shortcutConflict
                    onClicked: controller.startRunWithSettings(runForm.payload())
                }
            }
        }
    }
}

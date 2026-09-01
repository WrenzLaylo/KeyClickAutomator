import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import qml
import "../components"
import "../components" as Components

/*
  The multi-profile runner: queue order, run mode, and live run cards.

  `app` is the application root. The page reaches back through it for shared
  navigation and layout state rather than owning a copy of either.
*/
Item {
    id: page
    property var app

    objectName: "runQueuePage"

    ColumnLayout {
        // Same gutters as the Sequence page so the three tabs
        // share one left edge.
        anchors.fill: parent
        anchors.leftMargin: app.layoutMode === "wide" ? 28 : 22
        anchors.rightMargin: app.layoutMode === "wide" ? 28 : 22
        spacing: 0
        clip: true

        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 92
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 0
                anchors.rightMargin: 0
                spacing: 8
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 3
                    Text {
                        text: "Multi-Profile Runner"
                        color: Theme.ink
                        font.family: Theme.bold
                        font.pixelSize: 23
                        font.weight: Font.Bold
                    }
                    Text {
                        text: controller.runQueueCount === 0
                              ? "No profiles queued"
                              : controller.runQueueCount === 1
                                ? "1 profile · " + (controller.runQueueMode === "parallel" ? "Parallel" : "Sequential")
                                : controller.runQueueCount + " profiles · " + (controller.runQueueMode === "parallel" ? "Parallel" : "Sequential")
                        color: Theme.ink2
                        font.family: Theme.regular
                        font.pixelSize: 12
                    }
                }
                Item { Layout.fillWidth: true }
                KButton {
                    objectName: "runQueueAddProfilesButton"
                    text: "Profiles"
                    leading: "+"
                    implicitWidth: 96
                    enabled: !controller.running
                    onClicked: app.selectTab(1)
                }
            }
        }

        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.line }

        Rectangle {
            objectName: "runQueueModeNotice"
            Layout.fillWidth: true
            Layout.preferredHeight: 106
            Layout.leftMargin: 0
            Layout.rightMargin: 0
            Layout.topMargin: 12
            Layout.bottomMargin: 8
            radius: 13
            color: Theme.primarySoft
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
                    FormLabel { text: "RUN MODE"; color: Theme.primary }
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
                    color: Theme.ink2
                    font.family: Theme.regular
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
                anchors.leftMargin: 0
                anchors.rightMargin: 0
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
                           ? Theme.primarySoft
                           : modelData.state === "error"
                             ? Theme.redSoft
                             : modelData.state === "complete"
                               ? Theme.successSoft
                               : Theme.surface
                    border.width: modelData.state === "running" || modelData.state === "armed" || modelData.state === "paused" ? 2 : 1
                    border.color: modelData.state === "error"
                                  ? "#EDB8C2"
                                  : modelData.state === "complete"
                                    ? "#B8DECF"
                                    : modelData.state === "running" || modelData.state === "armed" || modelData.state === "paused"
                                      ? Theme.primary
                                      : Theme.line

                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 12
                        spacing: 10

                        Rectangle {
                            Layout.preferredWidth: 36
                            Layout.preferredHeight: 36
                            radius: 11
                            color: queueCard.modelData.state === "complete"
                                   ? Theme.green
                                   : queueCard.modelData.state === "error"
                                     ? Theme.red
                                     : Theme.surface2
                            border.width: queueCard.modelData.state === "queued" || queueCard.modelData.state === "cancelled" ? 1 : 0
                            border.color: Theme.line
                            Text {
                                anchors.centerIn: parent
                                text: String(queueCard.modelData.position).padStart(2, "0")
                                color: queueCard.modelData.state === "complete" || queueCard.modelData.state === "error"
                                       ? "white"
                                       : Theme.primary
                                font.family: Theme.semiBold
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
                                    color: Theme.ink
                                    font.family: Theme.semiBold
                                    font.pixelSize: 13
                                }
                                Rectangle {
                                    implicitWidth: queueStatusLabel.implicitWidth + 14
                                    implicitHeight: 21
                                    radius: 7
                                    color: queueCard.modelData.tone === "danger"
                                           ? Theme.redSoft
                                           : queueCard.modelData.tone === "success"
                                             ? Theme.successSoft
                                             : queueCard.modelData.tone === "accent"
                                               ? "#DCE8FF"
                                               : Theme.surface2
                                    Text {
                                        id: queueStatusLabel
                                        anchors.centerIn: parent
                                        text: queueCard.modelData.status.toUpperCase()
                                        color: Theme.toneColor(queueCard.modelData.tone)
                                        font.family: Theme.semiBold
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
                                color: Theme.ink3
                                font.family: Theme.regular
                                font.pixelSize: 11
                            }
                            Text {
                                visible: queueCard.modelData.error.length > 0
                                Layout.fillWidth: true
                                text: queueCard.modelData.error
                                wrapMode: Text.WordWrap
                                maximumLineCount: 2
                                elide: Text.ElideRight
                                color: Theme.red
                                font.family: Theme.medium
                                font.pixelSize: 10
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
                                color: Theme.surface3
                                Rectangle {
                                    height: parent.height
                                    radius: 3
                                    color: Theme.primary
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
                    color: Theme.ink
                    font.family: Theme.bold
                    font.pixelSize: 18
                    font.weight: Font.Bold
                }
                Text {
                    width: parent.width
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.WordWrap
                    text: "Open Profiles and add saved sequences in the order you want KeyClick to run them."
                    color: Theme.ink2
                    font.family: Theme.regular
                    font.pixelSize: 12
                    lineHeight: 1.3
                }
                KButton {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: "Choose profiles"
                    primary: true
                    implicitWidth: 150
                    onClicked: app.selectTab(1)
                }
            }
        }

        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.line }

        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 84
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 0
                anchors.rightMargin: 0
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

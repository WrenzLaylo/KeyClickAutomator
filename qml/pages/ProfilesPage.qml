import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import qml
import "../components"
import "../components" as Components

/*
  The saved profile library: open, queue, delete, and restore.

  `app` is the application root. The page reaches back through it for shared
  navigation and layout state rather than owning a copy of either.
*/
Item {
    id: page
    property var app

    objectName: "profileLibraryPage"

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
                        text: "Profiles"
                        color: Theme.ink
                        font.family: Theme.bold
                        font.pixelSize: 23
                        font.weight: Font.Bold
                    }
                    Text {
                        text: controller.profileEntries.length === 1
                              ? "1 saved sequence"
                              : controller.profileEntries.length + " saved sequences"
                        color: Theme.ink2
                        font.family: Theme.regular
                        font.pixelSize: 12
                    }
                }
                Item { Layout.fillWidth: true }
                KButton {
                    objectName: "refreshProfileLibraryButton"
                    leading: "↻"
                    text: "Refresh"
                    implicitWidth: 92
                    Accessible.name: "Refresh profiles"
                    onClicked: controller.refreshProfiles()
                }
            }
        }

        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.line }

        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 88
            ColumnLayout {
                anchors.fill: parent
                anchors.leftMargin: 0
                anchors.rightMargin: 0
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
                        color: Theme.ink2
                        font.family: Theme.medium
                        font.pixelSize: 11
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
                anchors.leftMargin: 0
                anchors.rightMargin: 0
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
                        onClicked: {
                            if (profileRow.currentProfile)
                                app.selectTab(0)
                            else
                                app.requestProfileOpen(modelData.path)
                        }
                        background: Rectangle {
                        radius: 14
                        color: profileRow.currentProfile ? Theme.primarySoft
                             : profileRow.down ? "#E8EEF8"
                             : profileRow.pointerHover ? "#F4F7FF"
                             : Theme.surface
                        border.width: profileRow.currentProfile ? 2 : 1
                        border.color: profileRow.currentProfile ? Theme.primary
                                    : profileRow.pointerHover ? "#B8CCF5"
                                    : Theme.line
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
                            color: profileRow.currentProfile ? Theme.primary : Theme.surface2
                            border.width: profileRow.currentProfile ? 0 : 1
                            border.color: Theme.line
                            Image {
                                anchors.centerIn: parent
                                width: 24
                                height: 24
                                source: "../../assets/app-logo-transparent.png"
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
                                    color: profileRow.modelData.valid ? Theme.ink : Theme.red
                                    font.family: Theme.semiBold
                                    font.pixelSize: 13
                                }
                                Rectangle {
                                    visible: profileRow.currentProfile
                                    implicitWidth: currentProfileLabel.implicitWidth + 14
                                    implicitHeight: 20
                                    radius: 7
                                    color: Theme.primary
                                    Text {
                                        id: currentProfileLabel
                                        anchors.centerIn: parent
                                        text: "CURRENT"
                                        color: "white"
                                        font.family: Theme.semiBold
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
                                color: profileRow.modelData.valid ? Theme.ink3 : Theme.red
                                font.family: Theme.regular
                                font.pixelSize: 11
                            }
                        }
                        Text {
                            visible: profileRow.modelData.valid && !profileRow.currentProfile
                            text: "›"
                            color: Theme.ink3
                            font.family: Theme.semiBold
                            font.pixelSize: 20
                        }
                    }
                }
                    KButton {
                        id: profileHistoryButton
                        objectName: "profileHistoryButton_" + profileDelegate.index
                        anchors.right: deleteProfileButton.left
                        anchors.rightMargin: 6
                        anchors.verticalCenter: parent.verticalCenter
                        implicitWidth: 42
                        implicitHeight: 38
                        leading: "↺"
                        quiet: true
                        enabled: !controller.running && !controller.runQueueRunning
                        Accessible.name: "Earlier versions of " + profileDelegate.modelData.name
                        onClicked: app.openProfileHistory(
                            profileDelegate.profilePath,
                            profileDelegate.modelData.name
                        )
                    }
                    KButton {
                        id: deleteProfileButton
                        objectName: "deleteProfileButton_" + profileDelegate.index
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        implicitWidth: 42
                        implicitHeight: 38
                        leading: "×"
                        danger: true
                        quiet: true
                        enabled: !controller.running && !controller.runQueueRunning
                        Accessible.name: "Delete " + profileDelegate.modelData.name
                        onClicked: app.requestProfileDelete(
                            profileDelegate.profilePath,
                            profileDelegate.modelData.name
                        )
                    }
                    KButton {
                        id: queueProfileButton
                        objectName: "queueProfileButton_" + profileDelegate.index
                        anchors.right: profileHistoryButton.left
                        anchors.rightMargin: 6
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
                    color: Theme.primarySoft
                    Image {
                        anchors.centerIn: parent
                        width: 32
                        height: 32
                        source: "../../assets/app-logo-transparent.png"
                        fillMode: Image.PreserveAspectFit
                        smooth: true
                        mipmap: true
                    }
                }
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: "No saved profiles here"
                    color: Theme.ink
                    font.family: Theme.bold
                    font.pixelSize: 17
                    font.weight: Font.Bold
                }
                Text {
                    width: parent.width
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.WordWrap
                    text: "Save this sequence or choose the folder that already contains your KeyClick profiles."
                    color: Theme.ink2
                    font.family: Theme.regular
                    font.pixelSize: 12
                    lineHeight: 1.3
                }
                KButton {
                    objectName: "profileLibraryEmptySaveButton"
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: "Save this profile"
                    primary: true
                    implicitWidth: 156
                    onClicked: app.saveProfileAsWithVisibleSettings()
                }
            }
        }

        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.line }

        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 76
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 0
                anchors.rightMargin: 0
                spacing: 8
                Item { Layout.fillWidth: true }
                KButton {
                    objectName: "profileLibraryRunnerButton"
                    Layout.preferredWidth: 112
                    text: controller.runQueueCount > 0
                          ? "Runner · " + controller.runQueueCount
                          : "Runner"
                    activeNeutral: controller.runQueueCount > 0
                    onClicked: app.selectTab(2)
                }
                KButton {
                    objectName: "profileLibrarySaveAsButton"
                    Layout.preferredWidth: 112
                    text: "Save as…"
                    primary: true
                    enabled: !controller.running
                    onClicked: app.saveProfileAsWithVisibleSettings()
                }
                KButton {
                    objectName: "profileLibraryOpenFileButton"
                    Layout.preferredWidth: 112
                    text: "Open file…"
                    enabled: !controller.running
                    onClicked: app.requestDestructiveAction("open")
                }
            }
        }
    }
}

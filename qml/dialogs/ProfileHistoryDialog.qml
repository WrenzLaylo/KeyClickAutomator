import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import qml
import "../components"

/*
  Earlier saved versions of one profile, with restore.

  `app` is the application root, used for sizing against the window and for the
  navigation helpers this dialog triggers.
*/
Dialog {
    property var app

    id: dialog
    objectName: "profileHistoryDialog"
    parent: Overlay.overlay
    modal: true
    closePolicy: Popup.CloseOnEscape
    width: Math.min(620, app.width - 48)
    height: Math.min(520, app.height - 64)
    x: Math.round((app.width - width) / 2)
    y: Math.round((app.height - height) / 2)
    padding: 0
    property string profilePath: ""
    property string profileLabel: ""
    property var entries: []
    background: Rectangle {
        radius: 18
        color: Theme.surface
        border.width: 1
        border.color: Theme.line
    }
    contentItem: ColumnLayout {
        spacing: 0
        clip: true

        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 82
            ColumnLayout {
                anchors.fill: parent
                anchors.leftMargin: 20
                anchors.rightMargin: 20
                spacing: 3
                Item { Layout.fillHeight: true }
                Text {
                    text: "Earlier versions"
                    color: Theme.ink
                    font.family: Theme.bold
                    font.pixelSize: 20
                    font.weight: Font.Bold
                }
                Text {
                    Layout.fillWidth: true
                    text: dialog.profileLabel
                    elide: Text.ElideMiddle
                    color: Theme.ink2
                    font.family: Theme.regular
                    font.pixelSize: 12
                }
                Item { Layout.fillHeight: true }
            }
        }

        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.line }

        Item {
            objectName: "profileHistoryEmptyState"
            visible: dialog.entries.length === 0
            Layout.fillWidth: true
            Layout.preferredHeight: visible ? 120 : 0
            Text {
                anchors.centerIn: parent
                width: parent.width - 60
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                text: "No earlier versions yet. KeyClick keeps a copy each time you save over this profile."
                color: Theme.ink3
                font.family: Theme.regular
                font.pixelSize: 12
            }
        }

        ListView {
            objectName: "profileHistoryList"
            visible: dialog.entries.length > 0
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.leftMargin: 14
            Layout.rightMargin: 14
            Layout.topMargin: 10
            spacing: 8
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            model: dialog.entries
            ScrollBar.vertical: KScrollBar { id: historyScrollBar }

            delegate: Rectangle {
                required property var modelData
                required property int index
                objectName: "profileHistoryRow_" + index
                width: ListView.view.width
                       - (historyScrollBar.visible ? historyScrollBar.width + 8 : 0)
                height: 60
                radius: 13
                color: Theme.surface
                border.width: 1
                border.color: Theme.line

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 14
                    anchors.rightMargin: 10
                    spacing: 10
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2
                        Text {
                            text: modelData.label
                            color: Theme.ink
                            font.family: Theme.semiBold
                            font.pixelSize: 12
                        }
                        Text {
                            text: modelData.actionCount < 0
                                  ? "Unreadable copy"
                                  : modelData.actionCount === 1
                                    ? "1 action"
                                    : modelData.actionCount + " actions"
                            color: modelData.actionCount < 0 ? Theme.red : Theme.ink3
                            font.family: Theme.regular
                            font.pixelSize: 11
                        }
                    }
                    KButton {
                        objectName: "restoreProfileVersion_" + index
                        implicitWidth: 96
                        text: "Restore"
                        leading: "↺"
                        enabled: modelData.actionCount >= 0
                        onClicked: {
                            if (controller.restoreProfileVersion(
                                    dialog.profilePath, modelData.path))
                                dialog.close()
                        }
                    }
                }
            }
        }

        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.line }

        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 66
            KButton {
                objectName: "closeProfileHistoryButton"
                anchors.right: parent.right
                anchors.rightMargin: 16
                anchors.verticalCenter: parent.verticalCenter
                implicitWidth: 110
                text: "Close"
                onClicked: dialog.close()
            }
        }
    }
}

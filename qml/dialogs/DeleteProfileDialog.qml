import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import qml
import "../components"

/*
  Confirms deleting a profile file from disk.

  `app` is the application root, used for sizing against the window and for the
  navigation helpers this dialog triggers.
*/
Dialog {
    property var app

    id: dialog
    objectName: "deleteProfileDialog"
    modal: true
    closePolicy: Popup.NoAutoClose
    width: 460
    height: 246
    x: Math.round((app.width - width) / 2)
    y: Math.round((app.height - height) / 2)
    padding: 22
    property string profilePath: ""
    property string profileLabel: ""
    background: Rectangle {
        radius: 18
        color: Theme.surface
        border.width: 1
        border.color: Theme.line
    }
    contentItem: ColumnLayout {
        spacing: 10
        Text {
            text: "Delete this profile?"
            color: Theme.ink
            font.family: Theme.bold
            font.pixelSize: 20
            font.weight: Font.Bold
        }
        Text {
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            text: "“" + dialog.profileLabel + "” will be deleted from disk. "
                + "This cannot be undone. The sequence open in the editor is kept."
            color: Theme.ink2
            font.family: Theme.regular
            font.pixelSize: 12
            lineHeight: 1.3
        }
        Item { Layout.fillHeight: true; Layout.minimumHeight: 8 }
        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            KButton {
                objectName: "cancelDeleteProfileButton"
                text: "Cancel"
                Layout.fillWidth: true
                implicitHeight: 44
                onClicked: {
                    dialog.profilePath = ""
                    dialog.close()
                }
            }
            KButton {
                objectName: "confirmDeleteProfileButton"
                text: "Delete"
                leading: "×"
                danger: true
                Layout.fillWidth: true
                implicitHeight: 44
                onClicked: {
                    var target = dialog.profilePath
                    dialog.profilePath = ""
                    dialog.close()
                    controller.deleteProfilePath(target)
                }
            }
        }
    }
}

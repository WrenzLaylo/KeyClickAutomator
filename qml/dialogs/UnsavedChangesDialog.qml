import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import qml
import "../components"

/*
  Save, discard, or cancel before abandoning unsaved sequence edits.

  `app` is the application root, used for sizing against the window and for the
  navigation helpers this dialog triggers.
*/
Dialog {
    property var app

    id: dialog
    objectName: "unsavedChangesDialog"
    modal: true
    closePolicy: Popup.NoAutoClose
    width: 460
    height: 258
    x: Math.round((app.width - width) / 2)
    y: Math.round((app.height - height) / 2)
    padding: 22
    background: Rectangle {
        radius: 18
        color: Theme.surface
        border.width: 1
        border.color: Theme.line
    }
    contentItem: ColumnLayout {
        spacing: 10
        Text { text: "Save your changes?"; color: Theme.ink; font.family: Theme.bold; font.pixelSize: 20; font.weight: Font.Bold }
        Text {
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            text: app.pendingDestructiveAction === "close" ? "This sequence has unsaved changes. Save it before closing KeyClick, discard the changes, or return to the editor." : "This sequence has unsaved changes. Save it before continuing, discard the changes, or cancel."
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
                objectName: "unsavedCancelButton"
                text: "Cancel"
                Layout.fillWidth: true
                implicitHeight: 44
                onClicked: {
                    app.pendingDestructiveAction = ""
                    app.pendingProfilePath = ""
                    dialog.close()
                }
            }
            KButton {
                objectName: "unsavedDiscardButton"
                text: "Discard"
                danger: true
                Layout.fillWidth: true
                implicitHeight: 44
                onClicked: {
                    var action = app.pendingDestructiveAction
                    app.pendingDestructiveAction = ""
                    dialog.close()
                    app.performDestructiveAction(action)
                }
            }
            KButton {
                objectName: "unsavedSaveButton"
                Layout.fillWidth: true
                implicitHeight: 44
                text: "Save & continue"
                primary: true
                onClicked: {
                    var action = app.pendingDestructiveAction
                    if (app.saveProfileWithVisibleSettings()) {
                        app.pendingDestructiveAction = ""
                        dialog.close()
                        app.performDestructiveAction(action)
                    }
                }
            }
        }
    }
}

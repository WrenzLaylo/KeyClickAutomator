import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import qml
import "../components"

/*
  Offers the autosaved draft left behind by an unexpected exit.

  `app` is the application root, used for sizing against the window and for the
  navigation helpers this dialog triggers.
*/
Dialog {
    property var app

    id: dialog
    objectName: "recoveryDialog"
    modal: true
    closePolicy: Popup.NoAutoClose
    width: 440
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
        Text { text: "Recover your sequence?"; color: Theme.ink; font.family: Theme.bold; font.pixelSize: 20; font.weight: Font.Bold }
        Text {
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            text: "KeyClick found an autosaved recovery copy from the previous session.\n" + controller.draftSummary
            color: Theme.ink2
            font.family: Theme.regular
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
                    dialog.close()
                }
            }
            KButton {
                objectName: "recoveryAcceptButton"
                Layout.preferredWidth: 148
                text: "Recover sequence"
                primary: true
                onClicked: {
                    if (controller.recoverDraft()) {
                        dialog.close()
                        if (controller.selectedIndex >= 0) {
                            app.editorIndex = controller.selectedIndex
                            editor.loadAction(controller.selectedIndex)
                        }
                    }
                }
            }
        }
    }
}

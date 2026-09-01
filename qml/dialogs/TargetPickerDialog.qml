import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import qml
import "../components"

/*
  Choose what to automate: this computer, an open window, or a browser tab.

  `app` is the application root, used for sizing against the window and for the
  navigation helpers this dialog triggers.
*/
Dialog {
    property var app

    id: dialog
    objectName: "targetPickerDialog"
    parent: Overlay.overlay
    modal: true
    closePolicy: Popup.CloseOnEscape
    width: Math.min(720, app.width - 48)
    height: Math.min(600, app.height - 64)
    x: Math.round((app.width - width) / 2)
    y: Math.round((app.height - height) / 2)
    padding: 0
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
            Layout.preferredHeight: 88
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 20
                anchors.rightMargin: 14
                spacing: 8
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 3
                    Text {
                        text: "What should it automate?"
                        color: Theme.ink
                        font.family: Theme.bold
                        font.pixelSize: 20
                        font.weight: Font.Bold
                    }
                    Text {
                        text: "Your computer, an open window, or a browser tab"
                        color: Theme.ink2
                        font.family: Theme.regular
                        font.pixelSize: 12
                    }
                }
                KButton {
                    objectName: "refreshTargetsButton"
                    text: "Refresh"
                    leading: "↻"
                    implicitWidth: 96
                    onClicked: controller.refreshAutomationTargets()
                }
            }
        }

        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.line }

        Item {
            objectName: "startBrowserPrompt"
            visible: !controller.browserReady
            Layout.fillWidth: true
            Layout.preferredHeight: visible ? 60 : 0
            Layout.leftMargin: 14
            Layout.rightMargin: 14
            Layout.topMargin: visible ? 10 : 0
            Rectangle {
                anchors.fill: parent
                radius: 13
                color: Theme.primarySoft
                border.width: 1
                border.color: "#B9CEFA"
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 14
                    anchors.rightMargin: 10
                    spacing: 10
                    Text {
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                        text: "Browser tabs appear once KeyClick's automation browser is running."
                        color: Theme.primary
                        font.family: Theme.medium
                        font.pixelSize: 11
                    }
                    KButton {
                        objectName: "startBrowserFromPickerButton"
                        implicitWidth: 150
                        primary: true
                        text: "Start browser"
                        onClicked: {
                            controller.startBrowser()
                            controller.refreshAutomationTargets()
                        }
                    }
                }
            }
        }

        ListView {
            objectName: "automationTargetList"
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.leftMargin: 14
            Layout.rightMargin: 14
            Layout.topMargin: 10
            spacing: 8
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            model: controller.automationTargets
            ScrollBar.vertical: KScrollBar { id: targetScrollBar; objectName: "targetPickerScrollBar" }

            delegate: AbstractButton {
                id: targetRow
                required property var modelData
                required property int index
                property bool pointerHover: false
                objectName: "automationTarget_" + index
                width: ListView.view.width
                       - (targetScrollBar.visible ? targetScrollBar.width + 8 : 0)
                height: modelData.advice === "" ? 66 : 84
                leftPadding: 14
                rightPadding: 14
                hoverEnabled: true
                Accessible.name: "Automate " + targetRow.modelData.title
                HoverHandler { onHoveredChanged: targetRow.pointerHover = hovered }
                onClicked: {
                    if (controller.selectAutomationTarget(
                            targetRow.modelData.kind, targetRow.modelData.id))
                        dialog.close()
                }
                background: Rectangle {
                    radius: 13
                    color: targetRow.modelData.current ? Theme.primarySoft
                         : targetRow.down ? "#E8EEF8"
                         : targetRow.pointerHover ? "#F4F7FF"
                         : Theme.surface
                    border.width: 1
                    border.color: targetRow.modelData.current ? "#B9CEFA" : Theme.line
                    Behavior on color { ColorAnimation { duration: 120 } }
                }
                contentItem: RowLayout {
                    spacing: 11
                    Rectangle {
                        visible: targetRow.modelData.previewUrl !== ""
                        Layout.preferredWidth: visible ? 68 : 0
                        Layout.preferredHeight: 42
                        radius: 8
                        color: Theme.surface3
                        border.width: 1
                        border.color: Theme.line
                        clip: true
                        Image {
                            anchors.fill: parent
                            anchors.margins: 1
                            source: targetRow.modelData.previewUrl
                            fillMode: Image.PreserveAspectCrop
                            asynchronous: true
                            smooth: true
                        }
                    }
                    Rectangle {
                        Layout.preferredWidth: 54
                        Layout.preferredHeight: 22
                        radius: 7
                        color: targetRow.modelData.kind === "browser" ? "#E4F1FF"
                             : targetRow.modelData.kind === "window" ? Theme.surface3
                             : Theme.successSoft
                        Text {
                            anchors.centerIn: parent
                            text: targetRow.modelData.kind === "browser" ? "TAB"
                                : targetRow.modelData.kind === "window" ? "WINDOW" : "PC"
                            color: targetRow.modelData.kind === "browser" ? Theme.primary
                                 : targetRow.modelData.kind === "window" ? Theme.ink2
                                 : Theme.green
                            font.family: Theme.semiBold
                            font.pixelSize: 8
                            font.letterSpacing: 0.4
                        }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 1
                        Text {
                            Layout.fillWidth: true
                            text: targetRow.modelData.title
                            elide: Text.ElideRight
                            color: Theme.ink
                            font.family: Theme.semiBold
                            font.pixelSize: 13
                        }
                        Text {
                            Layout.fillWidth: true
                            text: targetRow.modelData.subtitle
                            elide: Text.ElideMiddle
                            color: Theme.ink3
                            font.family: Theme.regular
                            font.pixelSize: 10
                        }
                        Text {
                            visible: targetRow.modelData.minimized === true
                            Layout.fillWidth: true
                            text: "Minimised \u00b7 restore it before running"
                            color: Theme.ink3
                            font.family: Theme.regular
                            font.pixelSize: 10
                        }
                        Text {
                            visible: targetRow.modelData.advice !== ""
                            Layout.fillWidth: true
                            text: targetRow.modelData.advice
                            wrapMode: Text.WordWrap
                            color: "#B26A00"
                            font.family: Theme.medium
                            font.pixelSize: 10
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
                objectName: "closeTargetPickerButton"
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

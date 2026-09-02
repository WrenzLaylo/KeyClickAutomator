import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Effects
import qml

/*
  The side panel that edits one action and the settings a run uses.

  `app` is the application root. The two forms are published as aliases because
  the run bar and the sequence page start runs from what is currently typed in
  them, and because the root needs to reset the editor without owning it.
*/
Rectangle {
    property var app

    id: inspectorPanel
    objectName: "runInspector"
    readonly property alias runSettingsForm: runSettingsPane
    readonly property alias actionEditor: editorForm

    function focusActionType() {
        editorForm.focusActionType()
    }

    visible: app.inspectorVisible
    width: app.layoutMode === "wide" ? 368 : app.layoutMode === "medium" ? 340 : Math.min(380, app.width - 84)
    x: app.overlayInspector ? (app.inspectorOpen ? app.width - width : app.width + 8) : app.width - width
    color: "#FCFCFE"
    z: 10
    clip: true
    border.width: app.overlayInspector ? 1 : 0
    border.color: Theme.line
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
            Text { Layout.fillWidth: true; text: "Inspector"; color: Theme.ink; font.family: Theme.bold; font.pixelSize: 20; font.weight: Font.Bold }
            KButton { visible: app.overlayInspector; text: ""; leading: "×"; quiet: true; implicitWidth: 38; onClicked: app.inspectorOpen = false }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 40
            radius: 12
            color: Theme.surface2
            Rectangle {
                id: tabSelectionPill
                objectName: "tabSelectionPill"
                x: 3 + app.activeInspectorTab * width
                y: 3
                width: (parent.width - 6) / 2
                height: parent.height - 6
                radius: 9
                color: Theme.surface
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
                        Text { anchors.centerIn: parent; text: modelData; color: app.activeInspectorTab === index ? Theme.ink : Theme.ink3; font.family: Theme.semiBold; font.pixelSize: 12 }
                        TapHandler { onTapped: app.activeInspectorTab = index }
                    }
                }
            }
        }

        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: app.activeInspectorTab

            Flickable {
                id: editorFlick
                contentHeight: editorForm.implicitHeight
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: KScrollBar { objectName: "editorScrollBar" }

                ActionEditorForm {
                    id: editorForm
                    app: inspectorPanel.app
                    runForm: runSettingsPane
                    width: editorFlick.width - 18
                }
            }

            Flickable {
                id: runFlick
                objectName: "runSettingsFlick"
                contentHeight: runSettingsPane.implicitHeight
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: KScrollBar { objectName: "runSettingsScrollBar" }
                RunSettingsForm {
                    id: runSettingsPane
                    app: inspectorPanel.app
                    width: runFlick.width - 18
                }
            }
        }
    }
}

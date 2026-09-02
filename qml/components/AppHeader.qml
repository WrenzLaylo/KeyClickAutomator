import QtQuick
import QtQuick.Layouts
import qml

/*
  The fixed top chrome: brand, workspace tabs, and the two actions that stay
  reachable from every tab.

  `app` is the application root. The header only reaches outward through it, so
  the caller keeps ownership of where this sits on screen.
*/
Rectangle {
    property var app

    id: header
    objectName: "appHeader"
    height: 72
    color: Theme.surface

    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 1
        color: Theme.line
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 20
        anchors.rightMargin: 14
        spacing: 12

        Image {
            id: brandLogo
            objectName: "brandLogo"
            Layout.preferredWidth: 34
            Layout.preferredHeight: 34
            source: "../../assets/app-logo-transparent.png"
            fillMode: Image.PreserveAspectFit
            smooth: true
            mipmap: true
        }

        ColumnLayout {
            visible: header.app.layoutMode !== "compact"
            spacing: 1
            Text {
                text: "KeyClick"
                color: Theme.ink
                font.family: Theme.bold
                font.pixelSize: 16
                font.weight: Font.Bold
            }
            Text {
                text: "AUTOMATOR  ·  " + Qt.application.version
                color: Theme.ink3
                font.family: Theme.semiBold
                font.pixelSize: 9
                font.letterSpacing: 0.6
            }
        }

        Rectangle {
            objectName: "workspaceTabs"
            Layout.leftMargin: header.app.layoutMode === "compact" ? 2 : 14
            Layout.preferredWidth: workspaceTabRow.implicitWidth + 8
            Layout.preferredHeight: 46
            radius: 14
            color: Theme.surface2

            Row {
                id: workspaceTabRow
                anchors.centerIn: parent
                spacing: 4
                WorkspaceTab {
                    app: header.app
                    objectName: "workspaceTab_sequence"
                    tabIndex: 0
                    label: "Sequence"
                }
                WorkspaceTab {
                    app: header.app
                    objectName: "workspaceTab_profiles"
                    tabIndex: 1
                    label: "Profiles"
                    badge: controller.profileEntries.length > 0
                           ? String(controller.profileEntries.length)
                           : ""
                }
                WorkspaceTab {
                    app: header.app
                    objectName: "workspaceTab_runner"
                    tabIndex: 2
                    label: "Runner"
                    badge: controller.runQueueCount > 0 ? String(controller.runQueueCount) : ""
                }
            }
        }

        Item { Layout.fillWidth: true }

        KButton {
            objectName: "workspaceNav_save"
            implicitWidth: header.app.layoutMode === "compact" ? 42 : 112
            implicitHeight: 40
            text: header.app.layoutMode === "compact" ? "" : "Save profile"
            leading: "↓"
            quiet: true
            enabled: !controller.running
            // Only worth a tooltip when the label itself is collapsed away.
            Accessible.name: "Save profile"
            onClicked: header.app.saveProfileWithVisibleSettings()
        }
        KButton {
            objectName: "workspaceNav_new"
            implicitWidth: header.app.layoutMode === "compact" ? 42 : 122
            implicitHeight: 40
            text: header.app.layoutMode === "compact" ? "" : "New sequence"
            leading: "+"
            quiet: true
            enabled: !controller.running
            Accessible.name: "New sequence"
            onClicked: header.app.requestDestructiveAction("new")
        }
    }
}

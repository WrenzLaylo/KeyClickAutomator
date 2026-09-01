import QtQuick
import QtQuick.Controls
import qml

Rectangle {
    property var app

    id: workspaceTab
    property string label: ""
    property string badge: ""
    property int tabIndex: 0
    property bool pointerHover: false
    readonly property bool selected: app.activeTab === tabIndex
    implicitWidth: workspaceTabContent.implicitWidth + (app.layoutMode === "compact" ? 20 : 28)
    implicitHeight: 38
    radius: 11
    // Fade from a zero-alpha copy of the hover colour, never from "transparent".
    // "transparent" is zero-alpha BLACK, so animating out of it drags the tab
    // through a dark smear -- the flash e5481d5 removed from the old nav.
    color: selected ? Theme.surface : (pointerHover ? "#E3E8F1" : "#00E3E8F1")
    border.width: selected ? 1 : 0
    border.color: Theme.line
    Behavior on color { ColorAnimation { duration: 140 } }
    Accessible.role: Accessible.PageTab
    Accessible.name: workspaceTab.label
    Accessible.onPressAction: app.selectTab(workspaceTab.tabIndex)
    HoverHandler { cursorShape: Qt.PointingHandCursor; onHoveredChanged: workspaceTab.pointerHover = hovered }
    TapHandler { onTapped: app.selectTab(workspaceTab.tabIndex) }

    Row {
        id: workspaceTabContent
        anchors.centerIn: parent
        spacing: 7
        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: workspaceTab.label
            color: workspaceTab.selected ? Theme.ink : Theme.ink2
            font.family: Theme.semiBold
            font.pixelSize: 13
        }
        Rectangle {
            visible: workspaceTab.badge !== ""
            anchors.verticalCenter: parent.verticalCenter
            width: Math.max(20, workspaceTabBadge.implicitWidth + 12)
            height: 19
            radius: 9
            color: workspaceTab.selected ? Theme.primarySoft : Theme.surface3
            Text {
                id: workspaceTabBadge
                anchors.centerIn: parent
                text: workspaceTab.badge
                color: workspaceTab.selected ? Theme.primary : Theme.ink2
                font.family: Theme.semiBold
                font.pixelSize: 10
            }
        }
    }
}

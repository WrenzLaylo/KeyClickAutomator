import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import qml

Rectangle {
    id: shortcutHint
    property string keyText: "F6"
    property string labelText: "Start"
    property bool compact: false
    property bool pointerHover: false
    implicitHeight: compact ? 40 : 25
    radius: compact ? 10 : 0
    color: compact ? (pointerHover ? Theme.primarySoft : "#F3F6FC") : "#00F3F6FC"
    border.width: compact ? 1 : 0
    border.color: compact ? (pointerHover ? "#B8CDF7" : Theme.line) : "transparent"
    HoverHandler { onHoveredChanged: shortcutHint.pointerHover = hovered }

    RowLayout {
        visible: !shortcutHint.compact
        anchors.fill: parent
        spacing: 7
        KeyCap { keyText: shortcutHint.keyText }
        Text {
            Layout.fillWidth: true
            text: shortcutHint.labelText
            color: Theme.ink2
            font.family: Theme.medium
            font.pixelSize: 11
        }
    }

    Column {
        visible: shortcutHint.compact
        width: parent.width - 6
        anchors.centerIn: parent
        spacing: 1
        Text {
            width: parent.width
            text: shortcutHint.keyText.toUpperCase()
            elide: Text.ElideRight
            horizontalAlignment: Text.AlignHCenter
            color: Theme.ink
            font.family: Theme.semiBold
            font.pixelSize: 11
        }
        Text {
            width: parent.width
            text: shortcutHint.labelText.toUpperCase()
            elide: Text.ElideRight
            horizontalAlignment: Text.AlignHCenter
            color: Theme.ink3
            font.family: Theme.semiBold
            font.pixelSize: 8
            font.letterSpacing: 0.45
        }
    }

    Behavior on color { ColorAnimation { duration: 120 } }
    Behavior on border.color { ColorAnimation { duration: 120 } }
}

import QtQuick
import qml

Rectangle {
    property string keyText: "F6"
    implicitWidth: Math.max(42, keyLabel.implicitWidth + 18)
    implicitHeight: 25
    radius: 7
    color: Theme.surface3
    border.width: 1
    border.color: Theme.line
    Text {
        id: keyLabel
        anchors.centerIn: parent
        text: parent.keyText.toUpperCase()
        color: Theme.ink
        font.family: Theme.semiBold
        font.pixelSize: 10
    }
}

import QtQuick
import QtQuick.Controls

ScrollBar {
    id: control

    property color thumbColor: "#B8C1CF"
    property color pressedThumbColor: "#7B8494"

    policy: ScrollBar.AsNeeded
    visible: policy === ScrollBar.AlwaysOn
             || (policy === ScrollBar.AsNeeded && size < 0.999)
    interactive: visible
    implicitWidth: 10
    padding: 2
    background: Item {}
    contentItem: Rectangle {
        implicitWidth: 6
        radius: 3
        color: control.pressed ? control.pressedThumbColor : control.thumbColor
        opacity: control.active ? 0.9 : 0.55
        Behavior on opacity { NumberAnimation { duration: 120 } }
    }
}

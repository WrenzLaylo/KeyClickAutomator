import QtQuick
import QtQuick.Controls

AbstractButton {
    id: control

    property bool primary: false
    property bool danger: false
    property bool quiet: false
    property bool activeNeutral: false
    property bool hamburgerIcon: false
    property string leading: ""
    property string keyHint: ""
    property bool pointerHover: false

    property string buttonFontFamily: "Segoe UI"
    property color inkColor: "#171A21"
    property color mutedInkColor: "#7B8494"
    property color secondaryInkColor: "#4B5363"
    property color dangerColor: "#D33C54"
    property color surfaceColor: "#FFFFFF"
    property color surface2Color: "#EEF1F6"
    property color surface3Color: "#E5EAF2"
    property color lineColor: "#D9DFE8"
    property color primaryColor: "#1565FF"
    property color primaryHoverColor: "#0759EB"

    implicitHeight: 42
    implicitWidth: 112
    padding: 12
    hoverEnabled: true
    clip: true
    font.family: buttonFontFamily
    font.pixelSize: 13
    font.weight: Font.DemiBold

    HoverHandler {
        onHoveredChanged: control.pointerHover = hovered
    }

    contentItem: Row {
        spacing: 7
        anchors.centerIn: parent

        Item {
            visible: control.hamburgerIcon
            width: visible ? 16 : 0
            height: 14
            anchors.verticalCenter: parent.verticalCenter

            Repeater {
                model: 3
                Rectangle {
                    required property int index
                    x: 0
                    y: 1 + index * 5
                    width: 16
                    height: 2
                    radius: 1
                    color: control.enabled
                        ? (control.primary ? "white" : control.danger ? control.dangerColor : control.inkColor)
                        : control.mutedInkColor
                }
            }
        }

        Text {
            visible: control.leading !== ""
            text: control.leading
            color: control.enabled
                ? (control.primary ? "white" : control.danger ? control.dangerColor : control.inkColor)
                : control.mutedInkColor
            font.family: control.buttonFontFamily
            font.pixelSize: 15
            anchors.verticalCenter: parent.verticalCenter
        }

        Text {
            visible: control.text !== ""
            text: control.text
            color: control.enabled
                ? (control.primary ? "white" : control.danger ? control.dangerColor : control.inkColor)
                : control.mutedInkColor
            font: control.font
            anchors.verticalCenter: parent.verticalCenter
        }

        Rectangle {
            objectName: control.objectName + "_keyHint"
            visible: control.keyHint !== ""
            width: visible ? Math.max(28, Math.min(42, keyHintLabel.implicitWidth + 12)) : 0
            height: 22
            radius: 7
            color: !control.enabled
                ? "#DCE2EB"
                : control.primary
                    ? "#30FFFFFF"
                    : control.danger
                        ? "#FFE5EA"
                        : control.surfaceColor
            border.width: 1
            border.color: !control.enabled
                ? "#CDD4DF"
                : control.primary
                    ? "#52FFFFFF"
                    : control.danger
                        ? "#F1BEC8"
                        : control.lineColor
            anchors.verticalCenter: parent.verticalCenter

            Text {
                id: keyHintLabel
                width: parent.width - 8
                anchors.centerIn: parent
                text: control.keyHint.toUpperCase()
                elide: Text.ElideRight
                horizontalAlignment: Text.AlignHCenter
                color: !control.enabled
                    ? control.mutedInkColor
                    : control.primary
                        ? "white"
                        : control.danger
                            ? control.dangerColor
                            : control.secondaryInkColor
                font.family: control.buttonFontFamily
                font.pixelSize: 9
                font.letterSpacing: 0.3
            }
        }
    }

    background: Rectangle {
        radius: 12
        color: !control.enabled
            ? control.surface2Color
            : control.down
                ? (control.primary ? "#0049C9" : control.activeNeutral ? "#D5DBE5" : control.surface3Color)
                : control.pointerHover
                    ? (control.primary ? control.primaryHoverColor : control.danger ? "#FDECEF" : control.activeNeutral ? "#DCE1E9" : control.surface3Color)
                    : control.primary
                        ? control.primaryColor
                        : control.quiet
                            ? "#00E5EAF2"
                            : control.danger
                                ? "#FFF2F4"
                                : control.activeNeutral
                                    ? "#E1E6EE"
                                    : control.surface2Color
        border.width: control.visualFocus ? 2 : control.activeNeutral ? 1 : 0
        border.color: control.visualFocus ? control.primaryColor : "#C7CED9"
        scale: control.down ? 0.975 : 1
        Behavior on color { ColorAnimation { duration: 130 } }
        Behavior on scale { NumberAnimation { duration: 100; easing.type: Easing.OutQuad } }
    }
}

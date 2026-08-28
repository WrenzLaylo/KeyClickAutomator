import QtQuick
import QtQuick.Controls

TextField {
    id: field

    property bool invalid: false
    property string validationMessage: ""
    property string fieldFontFamily: "Segoe UI"
    property color inkColor: "#171A21"
    property color mutedInkColor: "#7B8494"
    property color primaryColor: "#1565FF"
    property color dangerColor: "#D33C54"
    property color lineColor: "#D9DFE8"

    implicitHeight: 44
    leftPadding: 13
    rightPadding: 13
    selectByMouse: true
    font.family: fieldFontFamily
    font.pixelSize: 13
    color: inkColor
    placeholderTextColor: mutedInkColor
    selectionColor: primaryColor
    Accessible.description: field.validationMessage

    background: Rectangle {
        radius: 11
        color: field.activeFocus ? "#FFFFFF" : "#F8F9FC"
        border.width: field.activeFocus || field.invalid ? 2 : 1
        border.color: field.invalid
            ? field.dangerColor
            : field.activeFocus
                ? field.primaryColor
                : field.lineColor
        Behavior on border.color { ColorAnimation { duration: 120 } }
        Behavior on color { ColorAnimation { duration: 120 } }
    }
}

pragma Singleton

import QtQuick

/*
  Colours and fonts, reachable from any QML file.

  These used to be properties on Main.qml's root, which meant every screen and
  dialog had to live in that one file to see them. A singleton is what lets the
  interface be split up without passing a palette through each component.
*/
QtObject {
    readonly property color ink: "#171A21"
    readonly property color ink2: "#4B5363"
    readonly property color ink3: "#7B8494"
    readonly property color canvas: "#F3F5F9"
    readonly property color surface: "#FFFFFF"
    readonly property color surface2: "#EEF1F6"
    readonly property color surface3: "#E5EAF2"
    readonly property color line: "#D9DFE8"
    readonly property color primary: "#1565FF"
    readonly property color primaryHover: "#0759EB"
    readonly property color primarySoft: "#E8F0FF"
    readonly property color green: "#148A5B"
    readonly property color red: "#D33C54"
    readonly property color redSoft: "#FFF0F3"
    readonly property color successSoft: "#E9F7F1"

    readonly property FontLoader regularFont: FontLoader { source: "../assets/fonts/Inter-Regular.ttf" }
    readonly property FontLoader mediumFont: FontLoader { source: "../assets/fonts/Inter-Medium.ttf" }
    readonly property FontLoader semiBoldFont: FontLoader { source: "../assets/fonts/Inter-SemiBold.ttf" }
    readonly property FontLoader boldFont: FontLoader { source: "../assets/fonts/Inter-Bold.ttf" }

    readonly property string regular: regularFont.name || "Segoe UI"
    readonly property string medium: mediumFont.name || "Segoe UI"
    readonly property string semiBold: semiBoldFont.name || "Segoe UI"
    readonly property string bold: boldFont.name || "Segoe UI"

    function toneColor(tone) {
        if (tone === "accent") return primary
        if (tone === "success") return green
        if (tone === "danger") return red
        return ink2
    }
}

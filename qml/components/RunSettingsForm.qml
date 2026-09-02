import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import qml

/*
  What a run does before and between cycles, what it targets, and the global
  shortcuts that start and stop it.

  `app` is the application root; the shortcut recorder's in-progress state lives
  there because the capture is a global listener, not a field on this form.
*/
ColumnLayout {
    property var app

    id: runForm
    objectName: "runSettingsForm"
    spacing: 7
    enabled: !controller.running
    readonly property var shortcutValidation: controller.globalShortcutConflicts(startHotkey.text, captureHotkey.text, stopHotkey.text)
    readonly property string shortcutMessage: shortcutValidation.hasConflict ? shortcutValidation.message : app.shortcutCaptureError
    function payload() {
        return {repeatForever: foreverSwitch.checked, repeatCount: repeatCount.text, startDelay: startDelay.text, cycleInterval: cycleInterval.text, textInterval: textInterval.text, jitter: jitter.text, startHotkey: startHotkey.text, captureHotkey: captureHotkey.text, stopHotkey: stopHotkey.text}
    }
    function apply() {
        return controller.applyRunSettings(payload())
    }
    FormLabel { text: "BEFORE YOU RUN" }
    Rectangle {
        objectName: "preflightPanel"
        Layout.fillWidth: true
        Layout.preferredHeight: preflightColumn.implicitHeight + 20
        radius: 13
        color: Theme.surface2
        border.width: 1
        border.color: Theme.line

        ColumnLayout {
            id: preflightColumn
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: 10
            spacing: 6

            Repeater {
                model: controller.preflightChecks
                delegate: RowLayout {
                    required property var modelData
                    required property int index
                    objectName: "preflightCheck_" + index
                    Layout.fillWidth: true
                    spacing: 8

                    Rectangle {
                        Layout.alignment: Qt.AlignTop
                        Layout.topMargin: 2
                        width: 14; height: 14; radius: 7
                        color: modelData.status === "fail" ? Theme.redSoft
                             : modelData.status === "warn" ? "#FFF3E0"
                             : Theme.successSoft
                        Text {
                            anchors.centerIn: parent
                            text: modelData.status === "fail" ? "×"
                                : modelData.status === "warn" ? "!" : "✓"
                            color: modelData.status === "fail" ? Theme.red
                                 : modelData.status === "warn" ? "#B26A00" : Theme.green
                            font.family: Theme.semiBold
                            font.pixelSize: 9
                        }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 1
                        Text {
                            Layout.fillWidth: true
                            text: modelData.name + "  ·  " + modelData.detail
                            wrapMode: Text.WordWrap
                            color: modelData.status === "fail" ? Theme.red : Theme.ink2
                            font.family: Theme.medium
                            font.pixelSize: 10
                            lineHeight: 1.2
                        }
                        Text {
                            visible: modelData.remedy !== "" && modelData.status !== "pass"
                            Layout.fillWidth: true
                            text: modelData.remedy
                            wrapMode: Text.WordWrap
                            color: Theme.ink3
                            font.family: Theme.regular
                            font.pixelSize: 10
                            lineHeight: 1.2
                        }
                    }
                }
            }
        }
    }

    FormLabel { text: "TARGET"; Layout.topMargin: 6 }
    Text { text: "What should it automate?"; color: Theme.ink; font.family: Theme.bold; font.pixelSize: 17 }
    Text {
        Layout.fillWidth: true
        wrapMode: Text.WordWrap
        text: "Pick the thing you want automated. KeyClick works out how to reach it."
        color: Theme.ink2
        font.family: Theme.regular
        font.pixelSize: 11
        lineHeight: 1.25
    }

    Rectangle {
        objectName: "chosenTargetPanel"
        Layout.fillWidth: true
        Layout.preferredHeight: 108
        radius: 13
        color: Theme.surface2
        border.width: 1
        border.color: Theme.line
        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 12
            spacing: 7
            FormLabel { text: "AUTOMATING" }
            Text {
                Layout.fillWidth: true
                objectName: "chosenTargetLabel"
                text: controller.targetSummary
                elide: Text.ElideMiddle
                color: Theme.ink
                font.family: Theme.semiBold
                font.pixelSize: 13
            }
            KButton {
                objectName: "chooseTargetButton"
                Layout.fillWidth: true
                text: "Change what it automates"
                leading: "◈"
                onClicked: app.openTargetPicker()
            }
        }
    }

    FormLabel { text: "RUN PLAN" }
    Text { text: "Choose when it stops"; color: Theme.ink; font.family: Theme.bold; font.pixelSize: 17 }
    Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; text: "Run a fixed number of cycles or continue until you press Stop."; color: Theme.ink2; font.family: Theme.regular; font.pixelSize: 11; lineHeight: 1.25 }
    Rectangle {
        Layout.fillWidth: true; Layout.preferredHeight: 52; radius: 13; color: Theme.surface2
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 13
            anchors.rightMargin: 10
            Text { Layout.fillWidth: true; text: "Loop indefinitely"; color: Theme.ink; font.family: Theme.semiBold; font.pixelSize: 12 }
            Switch { id: foreverSwitch; checked: controller.runSettings.repeatForever; onToggled: controller.markRunSettingsPending() }
        }
    }
    FormLabel { text: "REPEAT CYCLES"; Layout.topMargin: 7 }
    KField { id: repeatCount; Layout.fillWidth: true; text: controller.runSettings.repeatCount; enabled: !foreverSwitch.checked; onTextEdited: controller.markRunSettingsPending() }
    FormLabel { text: "START COUNTDOWN"; Layout.topMargin: 7 }
    KField { id: startDelay; Layout.fillWidth: true; text: controller.runSettings.startDelay; onTextEdited: controller.markRunSettingsPending() }
    FormLabel { text: "BETWEEN CYCLES"; Layout.topMargin: 7 }
    KField { id: cycleInterval; Layout.fillWidth: true; text: controller.runSettings.cycleInterval; onTextEdited: controller.markRunSettingsPending() }
    RowLayout {
        Layout.fillWidth: true
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 4
            FormLabel { text: "TYPING INTERVAL" }
            KField { id: textInterval; Layout.fillWidth: true; text: controller.runSettings.textInterval; onTextEdited: controller.markRunSettingsPending() }
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 4
            FormLabel { text: "VARIATION ±" }
            KField { id: jitter; Layout.fillWidth: true; text: controller.runSettings.jitter; onTextEdited: controller.markRunSettingsPending() }
        }
    }
    Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.line; Layout.topMargin: 10; Layout.bottomMargin: 5 }
    FormLabel { text: "GLOBAL SHORTCUTS" }
    Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; text: "Use one key or a combination like ctrl+shift+s."; color: Theme.ink2; font.family: Theme.regular; font.pixelSize: 11 }
    RowLayout {
        Layout.fillWidth: true
        Text { text: "Start / toggle"; color: Theme.ink2; font.pixelSize: 11; font.family: Theme.medium; Layout.preferredWidth: 88 }
        KField { id: startHotkey; objectName: "startHotkeyField"; Layout.fillWidth: true; text: controller.runSettings.startHotkey; invalid: runForm.shortcutValidation.startConflict; validationMessage: invalid ? runForm.shortcutValidation.message : ""; onTextChanged: app.shortcutCaptureError = ""; onTextEdited: controller.markRunSettingsPending() }
        KButton {
            objectName: "shortcutRecord_start"
            implicitWidth: 106
            text: app.shortcutRecordingTarget === "start" ? "Listening" : "Record"
            leading: app.shortcutRecordingTarget === "start" ? "●" : "○"
            activeNeutral: app.shortcutRecordingTarget === "start"
            onClicked: if (controller.recordGlobalShortcut("start")) app.shortcutRecordingTarget = "start"
        }
    }
    RowLayout {
        Layout.fillWidth: true
        Text { text: "Record pointer"; color: Theme.ink2; font.pixelSize: 11; font.family: Theme.medium; Layout.preferredWidth: 88 }
        KField { id: captureHotkey; objectName: "captureHotkeyField"; Layout.fillWidth: true; text: controller.runSettings.captureHotkey; invalid: runForm.shortcutValidation.captureConflict; validationMessage: invalid ? runForm.shortcutValidation.message : ""; onTextChanged: app.shortcutCaptureError = ""; onTextEdited: controller.markRunSettingsPending() }
        KButton {
            objectName: "shortcutRecord_capture"
            implicitWidth: 106
            text: app.shortcutRecordingTarget === "capture" ? "Listening" : "Record"
            leading: app.shortcutRecordingTarget === "capture" ? "●" : "○"
            activeNeutral: app.shortcutRecordingTarget === "capture"
            onClicked: if (controller.recordGlobalShortcut("capture")) app.shortcutRecordingTarget = "capture"
        }
    }
    RowLayout {
        Layout.fillWidth: true
        Text { text: "Emergency stop"; color: Theme.ink2; font.pixelSize: 11; font.family: Theme.medium; Layout.preferredWidth: 88 }
        KField { id: stopHotkey; objectName: "stopHotkeyField"; Layout.fillWidth: true; text: controller.runSettings.stopHotkey; invalid: runForm.shortcutValidation.stopConflict; validationMessage: invalid ? runForm.shortcutValidation.message : ""; onTextChanged: app.shortcutCaptureError = ""; onTextEdited: controller.markRunSettingsPending() }
        KButton {
            objectName: "shortcutRecord_stop"
            implicitWidth: 106
            text: app.shortcutRecordingTarget === "stop" ? "Listening" : "Record"
            leading: app.shortcutRecordingTarget === "stop" ? "●" : "○"
            activeNeutral: app.shortcutRecordingTarget === "stop"
            onClicked: if (controller.recordGlobalShortcut("stop")) app.shortcutRecordingTarget = "stop"
        }
    }
    Text {
        objectName: "shortcutConflictMessage"
        Layout.fillWidth: true
        visible: runForm.shortcutMessage.length > 0
        text: runForm.shortcutMessage
        color: Theme.red
        font.family: Theme.semiBold
        font.pixelSize: 11
        wrapMode: Text.WordWrap
        Accessible.name: text
    }
    KButton { objectName: "runSettingsApplyButton"; Layout.fillWidth: true; Layout.topMargin: 8; primary: true; enabled: !runForm.shortcutValidation.hasConflict; text: runForm.shortcutValidation.hasConflict ? "Choose different shortcuts" : controller.runSettingsPending ? "Apply run settings" : "Run settings applied"; leading: controller.runSettingsPending ? "✓" : "●"; onClicked: runForm.apply() }
    Item { Layout.preferredHeight: 12 }
    // These all write into the fields above, so they live beside
    // them rather than on a root that cannot see them.
    Connections {
        target: controller
        function onShortcutCaptured(target, value) {
            var proposed = controller.globalShortcutConflicts(
                target === "start" ? value : startHotkey.text,
                target === "capture" ? value : captureHotkey.text,
                target === "stop" ? value : stopHotkey.text
            )
            app.shortcutRecordingTarget = ""
            if (proposed.hasConflict) {
                app.shortcutCaptureError = proposed.message
                controller.notifyShortcutCaptureResult(value, proposed.message)
                return
            }
            app.shortcutCaptureError = ""
            if (target === "start") startHotkey.text = value
            else if (target === "capture") captureHotkey.text = value
            else if (target === "stop") stopHotkey.text = value
            controller.markRunSettingsPending()
            controller.notifyShortcutCaptureResult(value, "")
        }
        function onRunSettingsChanged() {
            foreverSwitch.checked = controller.runSettings.repeatForever
            repeatCount.text = controller.runSettings.repeatCount
            startDelay.text = controller.runSettings.startDelay
            cycleInterval.text = controller.runSettings.cycleInterval
            textInterval.text = controller.runSettings.textInterval
            jitter.text = controller.runSettings.jitter
            startHotkey.text = controller.runSettings.startHotkey
            captureHotkey.text = controller.runSettings.captureHotkey
            stopHotkey.text = controller.runSettings.stopHotkey
        }
    }
}

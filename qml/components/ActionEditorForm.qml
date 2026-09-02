import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import qml

/*
  Everything that describes one action: what it does, where it does it, and how
  often it repeats.

  `app` is the application root. `runForm` is the sibling run-settings form,
  needed because Test and Run-from-here send whatever is currently typed there
  alongside this action.
*/
ColumnLayout {
    property var app
    property var runForm

    id: editor

    function focusActionType() {
        actionType.forceActiveFocus()
    }
    spacing: 7
    enabled: !controller.running
    property bool mouseAction: ["left_click", "right_click", "double_click", "middle_click", "scroll", "drag"].indexOf(kindValue()) >= 0
    property bool clickAction: ["left_click", "right_click", "double_click", "middle_click"].indexOf(kindValue()) >= 0
    property string coordinateSpace: "screen"
    property int referenceWidth: 0
    property int referenceHeight: 0
    property int referenceWidth2: 0
    property int referenceHeight2: 0
    property bool desktopTarget: controller.targetSettings.mode === "desktop"
    // Each target mode records positions in its own space.
    readonly property string expectedSpace: controller.targetSettings.mode === "desktop"
                                            ? "screen"
                                            : controller.targetSettings.mode === "browser"
                                              ? "viewport"
                                              : "window"
    // A follow-pointer click has no recorded position, so it can never
    // belong to the wrong target and never needs recording again.
    property bool followingPointer: clickAction && followPointerSwitch.checked && desktopTarget
    property bool needsPointerPosition: mouseAction && !followingPointer
    // A mouse action whose position was never recorded or typed
    // silently ends up at (0, 0) -- the corner of the target,
    // which looks like "the automation does nothing".
    property bool pointerProvided: false
    readonly property bool pointerMissing: needsPointerPosition && !pointerProvided
    property bool targetMismatch: mouseAction && !followingPointer && coordinateSpace !== expectedSpace

    function kindValue() {
        var values = ["key", "hotkey", "text", "left_click", "right_click", "double_click", "middle_click", "scroll", "drag"]
        return values[actionType.currentIndex]
    }
    function reset() {
        app.editorIndex = -1
        actionType.currentIndex = 0
        valueField.text = "space"
        xField.text = "0"; yField.text = "0"; x2Field.text = "0"; y2Field.text = "0"
        amountField.text = "-3"; durationField.text = "0.4"; repeatsField.text = "1"; delayField.text = "0.10"
        followPointerSwitch.checked = false
        coordinateSpace = expectedSpace
        referenceWidth = 0
        referenceHeight = 0
        referenceWidth2 = 0
        referenceHeight2 = 0
        pointerProvided = false
    }
    function loadAction(index) {
        var a = controller.actionAt(index)
        var kinds = ["key", "hotkey", "text", "left_click", "right_click", "double_click", "middle_click", "scroll", "drag"]
        actionType.currentIndex = Math.max(0, kinds.indexOf(a.kind))
        valueField.text = a.value || ""
        xField.text = a.x === undefined || a.x === null ? "0" : a.x
        yField.text = a.y === undefined || a.y === null ? "0" : a.y
        x2Field.text = a.x2 === undefined || a.x2 === null ? "0" : a.x2
        y2Field.text = a.y2 === undefined || a.y2 === null ? "0" : a.y2
        amountField.text = a.amount || -3
        durationField.text = a.duration === undefined || a.duration === null ? 0.4 : a.duration
        repeatsField.text = a.repeats || 1
        delayField.text = a.delay === undefined ? 0.1 : a.delay
        followPointerSwitch.checked = a.use_current_pointer || false
        coordinateSpace = a.coordinate_space || "screen"
        referenceWidth = a.reference_width || 0
        referenceHeight = a.reference_height || 0
        referenceWidth2 = a.reference_width2 || 0
        referenceHeight2 = a.reference_height2 || 0
        pointerProvided = true
    }
    function payload() {
        // Following the pointer drops the recorded position entirely, so the
        // action becomes a plain Desktop action no matter where it was recorded.
        return {kind: kindValue(), value: valueField.text, x: xField.text, y: yField.text, x2: x2Field.text, y2: y2Field.text, amount: amountField.text, duration: durationField.text, repeats: repeatsField.text, delay: delayField.text, enabled: true, useCurrentPointer: followingPointer, coordinateSpace: followingPointer ? "screen" : coordinateSpace, referenceWidth: followingPointer ? 0 : referenceWidth, referenceHeight: followingPointer ? 0 : referenceHeight, referenceWidth2: followingPointer ? 0 : referenceWidth2, referenceHeight2: followingPointer ? 0 : referenceHeight2}
    }
    Component.onCompleted: reset()

    KButton { Layout.fillWidth: true; text: app.editorIndex >= 0 ? "Editing action " + (app.editorIndex + 1) : "New action"; leading: app.editorIndex >= 0 ? "✦" : "+"; onClicked: app.beginNewAction() }
    FormLabel { text: "ACTION TYPE"; Layout.topMargin: 6 }
    ComboBox {
        id: actionType
        objectName: "actionTypePicker"
        Layout.fillWidth: true
        implicitHeight: 44
        model: ["Key press", "Hotkey", "Type text", "Left click", "Right click", "Double click", "Middle click", "Scroll", "Drag"]
        font.family: Theme.medium
        font.pixelSize: 13
        leftPadding: 13
        rightPadding: 42
        onCurrentIndexChanged: {
            if (controller.actionCaptureMode !== "")
                controller.cancelActionCapture()
        }
        contentItem: Text {
            text: actionType.displayText
            color: Theme.ink
            font: actionType.font
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
        indicator: Text {
            x: actionType.width - width - 14
            y: (actionType.height - height) / 2
            text: "⌄"
            color: Theme.ink2
            font.family: Theme.semiBold
            font.pixelSize: 20
            rotation: actionType.popup.visible ? 180 : 0
            Behavior on rotation { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
        }
        background: Rectangle {
            radius: 11
            color: actionType.hovered || actionType.activeFocus ? "#FFFFFF" : "#F8F9FC"
            border.width: actionType.activeFocus || actionType.popup.visible ? 2 : 1
            border.color: actionType.activeFocus || actionType.popup.visible ? Theme.primary : actionType.hovered ? "#BFC9D8" : Theme.line
            Behavior on color { ColorAnimation { duration: 120 } }
            Behavior on border.color { ColorAnimation { duration: 120 } }
        }
        delegate: ItemDelegate {
            id: option
            required property var modelData
            required property int index
            width: actionType.width - 12
            height: 40
            leftPadding: 12
            highlighted: actionType.highlightedIndex === index
            contentItem: Text {
                text: option.modelData
                color: option.highlighted ? Theme.primary : Theme.ink
                font.family: option.highlighted ? Theme.semiBold : Theme.medium
                font.pixelSize: 13
                verticalAlignment: Text.AlignVCenter
            }
            background: Rectangle {
                radius: 9
                color: option.highlighted ? Theme.primarySoft : option.hovered ? "#F1F4F9" : "#00F1F4F9"
                Behavior on color { ColorAnimation { duration: 100 } }
            }
            onClicked: {
                actionType.currentIndex = index
                actionType.popup.close()
            }
        }
        popup: Popup {
            objectName: "actionTypePopup"
            x: 0
            y: actionType.height + 6
            z: 100
            width: actionType.width
            implicitHeight: Math.min(contentItem.implicitHeight + 12, 380)
            padding: 6
            clip: true
            contentItem: ListView {
                clip: true
                implicitHeight: contentHeight
                model: actionType.popup.visible ? actionType.delegateModel : null
                currentIndex: actionType.highlightedIndex
                boundsBehavior: Flickable.StopAtBounds
                ScrollIndicator.vertical: ScrollIndicator {}
            }
            background: Rectangle {
                radius: 14
                color: Theme.surface
                border.width: 1
                border.color: Theme.line
            }
        }
    }

    FormLabel { visible: !editor.mouseAction; text: editor.kindValue() === "text" ? "TEXT TO TYPE" : "KEY OR SHORTCUT"; Layout.topMargin: 7 }
    KField { id: valueField; objectName: "actionValueField"; visible: !editor.mouseAction; Layout.fillWidth: true; placeholderText: editor.kindValue() === "hotkey" ? "ctrl+shift+s" : editor.kindValue() === "text" ? "Type something…" : "space" }
    KButton {
        objectName: "recordActionKey"
        visible: editor.kindValue() === "key"
        Layout.fillWidth: true
        text: controller.actionCaptureMode === "key"
              ? "Cancel key recording"
              : "Listen for a key"
        leading: controller.actionCaptureMode === "key" ? "×" : "⌨"
        activeNeutral: controller.actionCaptureMode === "key"
        onClicked: {
            if (controller.actionCaptureMode === "key")
                controller.cancelActionCapture()
            else
                controller.recordActionKey()
        }
    }
    KButton {
        objectName: "recordActionHotkey"
        visible: editor.kindValue() === "hotkey"
        Layout.fillWidth: true
        text: controller.actionCaptureMode === "hotkey"
              ? "Cancel hotkey recording"
              : "Record hotkey"
        leading: controller.actionCaptureMode === "hotkey" ? "×" : "⌘"
        activeNeutral: controller.actionCaptureMode === "hotkey"
        onClicked: {
            if (controller.actionCaptureMode === "hotkey")
                controller.cancelActionCapture()
            else
                controller.recordActionHotkey()
        }
    }

    Rectangle {
        visible: editor.clickAction && editor.desktopTarget
        Layout.fillWidth: true
        Layout.preferredHeight: visible ? 58 : 0
        radius: 13
        color: Theme.surface2
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 13
            anchors.rightMargin: 10
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2
                Text { text: "Follow current pointer"; color: Theme.ink; font.family: Theme.semiBold; font.pixelSize: 12 }
                Text { text: "Click wherever the pointer is during the run"; color: Theme.ink3; font.family: Theme.regular; font.pixelSize: 9 }
            }
            Switch { id: followPointerSwitch; objectName: "followPointerSwitch" }
        }
    }

    Rectangle {
        visible: editor.targetMismatch
        Layout.fillWidth: true
        Layout.preferredHeight: visible ? 62 : 0
        radius: 12
        color: Theme.redSoft
        border.width: 1
        border.color: "#F2C8D0"
        Text {
            anchors.fill: parent
            anchors.margins: 11
            wrapMode: Text.WordWrap
            text: "This position was recorded for a different target. Record it again for "
                + (editor.expectedSpace === "screen"
                   ? "Desktop mode"
                   : editor.expectedSpace === "viewport"
                     ? "the selected browser tab"
                     : "the selected window")
                + " before saving or running."
            color: Theme.red
            font.family: Theme.medium
            font.pixelSize: 10
            lineHeight: 1.2
        }
    }

    FormLabel { visible: editor.needsPointerPosition; text: editor.kindValue() === "drag" ? "DRAG START POSITION" : editor.desktopTarget ? "SCREEN POSITION" : "WINDOW POSITION"; Layout.topMargin: 7 }
    RowLayout {
        visible: editor.needsPointerPosition
        Layout.fillWidth: true
        KField {
            id: xField
            Layout.fillWidth: true
            placeholderText: "X"
            inputMethodHints: Qt.ImhDigitsOnly
            onTextEdited: editor.pointerProvided = true
        }
        KField {
            id: yField
            Layout.fillWidth: true
            placeholderText: "Y"
            inputMethodHints: Qt.ImhDigitsOnly
            onTextEdited: editor.pointerProvided = true
        }
    }
    KButton {
        objectName: "recordPointerPosition"
        visible: editor.needsPointerPosition
        Layout.fillWidth: true
        text: controller.capturePending && controller.captureTarget === 0 ? "Cancel point picker" : editor.kindValue() === "drag" ? "Pick start position" : "Pick pointer position"
        leading: controller.capturePending && controller.captureTarget === 0 ? "×" : "⌖"
        activeNeutral: controller.capturePending && controller.captureTarget === 0
        enabled: !controller.capturePending || controller.captureTarget === 0
        onClicked: {
            if (controller.capturePending) controller.cancelPositionCapture()
            else controller.startPositionCapture(0)
        }
    }
    Text {
        visible: editor.needsPointerPosition
        Layout.fillWidth: true
        wrapMode: Text.WordWrap
        text: controller.capturePending ? "Choose a point on the frozen screen, or press Esc to cancel." : editor.desktopTarget ? "KeyClick hides, freezes and dims the screen so you can choose the exact point without rushing." : "Choose the point on a frozen screen. It will scale with the selected window when that window is resized."
        color: controller.capturePending ? Theme.primary : Theme.ink3
        font.family: Theme.regular
        font.pixelSize: 10
        lineHeight: 1.2
    }

    FormLabel { visible: editor.kindValue() === "drag"; text: "DRAG DESTINATION"; Layout.topMargin: 7 }
    RowLayout {
        visible: editor.kindValue() === "drag"
        Layout.fillWidth: true
        KField { id: x2Field; Layout.fillWidth: true; placeholderText: "X"; inputMethodHints: Qt.ImhDigitsOnly }
        KField { id: y2Field; Layout.fillWidth: true; placeholderText: "Y"; inputMethodHints: Qt.ImhDigitsOnly }
    }
    KButton {
        objectName: "recordDragDestination"
        visible: editor.kindValue() === "drag"
        Layout.fillWidth: true
        text: controller.capturePending && controller.captureTarget === 1 ? "Cancel point picker" : "Pick destination"
        leading: controller.capturePending && controller.captureTarget === 1 ? "×" : "⌖"
        activeNeutral: controller.capturePending && controller.captureTarget === 1
        enabled: !controller.capturePending || controller.captureTarget === 1
        onClicked: {
            if (controller.capturePending) controller.cancelPositionCapture()
            else controller.startPositionCapture(1)
        }
    }

    FormLabel { visible: editor.kindValue() === "scroll"; text: "SCROLL STEPS"; Layout.topMargin: 7 }
    KField { id: amountField; visible: editor.kindValue() === "scroll"; Layout.fillWidth: true; placeholderText: "-3" }
    FormLabel { visible: editor.kindValue() === "drag"; text: "DRAG DURATION"; Layout.topMargin: 7 }
    KField { id: durationField; visible: editor.kindValue() === "drag"; Layout.fillWidth: true; placeholderText: "0.4" }

    FormLabel { text: "ACTION BEHAVIOR"; Layout.topMargin: 9 }
    RowLayout {
        Layout.fillWidth: true
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 4
            Text { text: "Repeats"; color: Theme.ink2; font.pixelSize: 11; font.family: Theme.medium }
            KField { id: repeatsField; Layout.fillWidth: true; text: "1" }
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 4
            Text { text: "Wait after"; color: Theme.ink2; font.pixelSize: 11; font.family: Theme.medium }
            KField { id: delayField; Layout.fillWidth: true; text: "0.10" }
        }
    }
    RowLayout {
        visible: app.editorIndex >= 0
        Layout.fillWidth: true
        Layout.topMargin: visible ? 7 : 0
        KButton {
            objectName: "inspectorTestActionButton"
            Layout.fillWidth: true
            text: "Test once"
            leading: "1×"
            enabled: !editor.targetMismatch
            onClicked: controller.testActionWithSettings(app.editorIndex, runForm.payload())
        }
        KButton {
            objectName: "inspectorRunFromButton"
            Layout.fillWidth: true
            text: "Run from here"
            leading: "▶"
            enabled: !editor.targetMismatch
            onClicked: controller.startRunFromWithSettings(app.editorIndex, runForm.payload())
        }
    }
    Rectangle {
        objectName: "pointerMissingNotice"
        visible: editor.pointerMissing
        Layout.fillWidth: true
        Layout.topMargin: visible ? 8 : 0
        Layout.preferredHeight: visible ? 54 : 0
        radius: 12
        color: Theme.primarySoft
        border.width: 1
        border.color: "#B9CEFA"
        Text {
            anchors.fill: parent
            anchors.margins: 11
            wrapMode: Text.WordWrap
            text: "Record where this should happen first. Without a position "
                + "the action lands at the target's top-left corner."
            color: Theme.primary
            font.family: Theme.medium
            font.pixelSize: 11
        }
    }
    KButton {
        objectName: "actionCommitButton"
        Layout.fillWidth: true
        Layout.topMargin: 10
        implicitHeight: 48
        primary: true
        enabled: !editor.targetMismatch && !editor.pointerMissing
        text: app.editorIndex >= 0 ? "Update action" : "Add to sequence"
        leading: app.editorIndex >= 0 ? "✓" : "+"
        onClicked: {
            if (app.editorIndex >= 0) {
                controller.updateAction(app.editorIndex, editor.payload())
            } else {
                if (controller.addAction(editor.payload())) {
                    controller.selectedIndex = -1
                    editor.reset()
                }
            }
        }
    }
    Item { Layout.preferredHeight: 12 }
    // These all write into the fields above, so they live beside
    // them rather than on a root that cannot see them.
    Connections {
        target: controller
        function onSelectedIndexChanged() {
            if (controller.actionCaptureMode !== "")
                controller.cancelActionCapture()
            if (controller.selectedIndex >= 0) {
                app.editorIndex = controller.selectedIndex
                editor.loadAction(controller.selectedIndex)
            } else if (app.editorIndex >= 0) {
                editor.reset()
            }
        }
        function onPositionCaptured(target, x, y, coordinateSpace, referenceWidth, referenceHeight) {
            if (target === 0) {
                xField.text = x; yField.text = y
                editor.referenceWidth = referenceWidth
                editor.referenceHeight = referenceHeight
            } else {
                x2Field.text = x; y2Field.text = y
                editor.referenceWidth2 = referenceWidth
                editor.referenceHeight2 = referenceHeight
            }
            editor.coordinateSpace = coordinateSpace
            editor.pointerProvided = true
        }
        function onActionKeyCaptured(value) {
            if (editor.kindValue() === "key")
                valueField.text = value
        }
        function onActionHotkeyCaptured(value) {
            if (editor.kindValue() === "hotkey")
                valueField.text = value
        }
        function onTargetSettingsChanged() {
            if (app.editorIndex < 0) {
                editor.coordinateSpace = editor.expectedSpace
                editor.referenceWidth = 0
                editor.referenceHeight = 0
                editor.referenceWidth2 = 0
                editor.referenceHeight2 = 0
                if (controller.targetSettings.mode === "window")
                    followPointerSwitch.checked = false
            }
        }
    }
}

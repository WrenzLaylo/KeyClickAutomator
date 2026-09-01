"""Every signal the controller exposes, in one place.

A Qt property's ``notify=`` argument needs the Signal object in scope where the
property is declared, so the concern mixins all inherit these rather than each
owning a private few.
"""
from __future__ import annotations

from PySide6.QtCore import Signal


class ControllerSignals:
    actionsChanged = Signal()
    summaryChanged = Signal()
    selectedIndexChanged = Signal()
    runningChanged = Signal()
    statusChanged = Signal()
    progressChanged = Signal()
    runSettingsChanged = Signal()
    runSettingsPendingChanged = Signal()
    currentProfileNameChanged = Signal()
    currentProfilePathChanged = Signal()
    profileDirectoryChanged = Signal()
    profileEntriesChanged = Signal()
    dirtyChanged = Signal()
    draftAvailableChanged = Signal()
    undoChanged = Signal()
    captureStateChanged = Signal()
    actionCaptureStateChanged = Signal()
    targetSettingsChanged = Signal()
    windowPickStateChanged = Signal()
    windowEntriesChanged = Signal()
    browserTabsChanged = Signal()
    preflightChanged = Signal()
    targetsChanged = Signal()
    browserPointCaptured = Signal(int, int, int, int, int)
    runningActionIndexChanged = Signal()
    runQueueChanged = Signal()
    runQueueRunningChanged = Signal()
    runQueueModeChanged = Signal()
    toast = Signal(str, str)
    positionCaptured = Signal(int, int, int, str, int, int)
    actionKeyCaptured = Signal(str)
    actionHotkeyCaptured = Signal(str)
    shortcutCaptured = Signal(str, str)
    progressFromWorker = Signal(str, str, int, int)
    finishedFromWorker = Signal(str, bool, str)
    hotkeyToggleRequested = Signal()
    hotkeyCaptureRequested = Signal()
    hotkeyStopRequested = Signal()

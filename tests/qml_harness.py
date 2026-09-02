"""Driving the real QML application from a test.

The application object lives here so that switching tabs the way the tab bar
does, and finding an item by objectName, mean the same thing in every module."""

from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from PySide6.QtCore import QMetaObject
from PySide6.QtCore import Q_ARG
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from window_backend import WindowInfo


class PickerWindowService:
    def __init__(self):
        self.windows = [
            WindowInfo(1001, "Team chat", "Chrome_WidgetWin_1", r"C:\\Apps\\Discord.exe", 51),
            WindowInfo(1002, "Daily meeting - Google Meet", "Chrome_WidgetWin_1", r"C:\\Apps\\chrome.exe", 52),
        ]

    def list_windows(self, excluded_process_id=0):
        return self.windows

    def ensure_usable(self, hwnd):
        return None

    def ensure_responsive(self, hwnd):
        return None

def show_tab(window, index, settle=200):
    """Switch workspace tabs exactly the way the tab bar does."""
    assert QMetaObject.invokeMethod(
        window, "selectTab", Qt.DirectConnection, Q_ARG("QVariant", index)
    )
    app.processEvents()
    QTest.qWait(settle)
    assert window.property("activeTab") == index

def visual_children_named(item, prefix):
    matches = []
    for child in item.childItems():
        if child.objectName().startswith(prefix):
            matches.append(child)
        matches.extend(visual_children_named(child, prefix))
    return matches

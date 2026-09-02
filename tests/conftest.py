"""One Qt application for the whole suite.

Which module created it used to depend on alphabetical collection order: the
controller tests ask for a QCoreApplication and the QML tests for a
QApplication, and whichever imported first won. A QCoreApplication arriving
first leaves the QML tests with no widget support at all, so adding a test file
whose name sorts early could break tests that never changed. Creating it here,
once and always as a QApplication, removes the ordering entirely.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

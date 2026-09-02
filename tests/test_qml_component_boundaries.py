"""Guards for the seams between the split QML files.

A green suite does not mean the interface is intact: a QML id that no longer
resolves, or a property bound to itself, fails silently at runtime and leaves
the rest of the tests passing. These tests read the warning stream and the
scope of an extracted file directly, which is where that damage shows up.
"""

import os
import re
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_QML_ROOT = Path(__file__).parents[1] / "qml"

from PySide6.QtCore import (
    QObject,
    Qt,
    QMetaObject,
    Q_ARG,
    qInstallMessageHandler,
    QtMsgType,
)
from PySide6.QtQml import QQmlExpression, qmlContext
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from qt_app import build_engine


_app = QApplication.instance() or QApplication([])

# Qt's native Windows style logs a "does not support customization" warning for
# every styled control, so match on the failures that mean something instead.
_BROKEN = (
    "ReferenceError",
    "is not defined",
    "TypeError",
    "Unable to assign",
    "Cannot assign",
    "Binding loop",
    "binding loop",
    "is not a function",
)


def evaluate_in(scope, source):
    """Evaluate a QML expression as if it were written inside `scope`'s file."""
    expression = QQmlExpression(qmlContext(scope), scope, source)
    value = expression.evaluate()
    assert not expression.hasError(), expression.error().toString()
    # PySide6 returns (value, wasUndefined).
    return value[0] if isinstance(value, tuple) else value


class _Warnings:
    """Collect QML warnings for the duration of a block."""

    def __enter__(self):
        self.messages = []

        def handler(mode, context, message):
            if mode in (QtMsgType.QtWarningMsg, QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
                self.messages.append(message)

        self._previous = qInstallMessageHandler(handler)
        return self

    def __exit__(self, *exc):
        qInstallMessageHandler(self._previous)
        return False

    @property
    def broken(self):
        return [m for m in self.messages if any(b in m for b in _BROKEN)]


def test_walking_the_whole_app_logs_no_unresolved_qml_references():
    with _Warnings() as log:
        engine, controller = build_engine(start_hotkeys=False)
        window = engine.rootObjects()[0]
        _app.processEvents()
        QTest.qWait(200)

        # Every tab, both inspector tabs, and every layout breakpoint, because an
        # extracted file can be wrong only in the state that first shows it.
        for tab in (1, 2, 0):
            QMetaObject.invokeMethod(
                window, "selectTab", Qt.DirectConnection, Q_ARG("QVariant", tab)
            )
            _app.processEvents()
            QTest.qWait(100)
        for inspector_tab in (1, 0):
            window.setProperty("activeInspectorTab", inspector_tab)
            _app.processEvents()
            QTest.qWait(100)
        for width, height in [(900, 640), (1024, 720), (1240, 760), (1600, 900)]:
            window.resize(width, height)
            _app.processEvents()
            QTest.qWait(100)

        QMetaObject.invokeMethod(window, "beginNewAction", Qt.DirectConnection)
        _app.processEvents()
        QTest.qWait(150)
        controller.shutdown()

    assert log.broken == []


def test_the_recovery_dialog_reaches_the_editor_through_the_app_root():
    """Ids do not cross files, so the dialog has to go through `app`.

    Calling a bare `editor.loadAction(...)` from this dialog resolved to
    undefined and threw the moment a recovered draft had a selected action.
    """
    engine, controller = build_engine(start_hotkeys=False)
    window = engine.rootObjects()[0]
    dialog = window.findChild(QObject, "recoveryDialog")
    assert dialog is not None

    assert evaluate_in(dialog, "typeof editor") == "undefined"
    assert evaluate_in(dialog, "typeof app.loadActionIntoEditor") == "function"
    controller.shutdown()


def test_no_qml_file_calls_through_an_id_that_lives_in_another_file():
    """Ids are scoped to their own file and resolve to undefined outside it.

    Nothing warns at load time -- the call throws the first time a user reaches
    the line, which is how `editor.loadAction(...)` survived in the recovery
    dialog. A reference is only flagged when the name is a declared id
    *somewhere else* and is neither an id nor a property here.
    """
    def code_only(text):
        """Prose and UI strings are full of `the inspector.` and `the editor.`."""
        text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
        text = re.sub(r"//[^\n]*", " ", text)
        return re.sub(r'"(?:[^"\\]|\\.)*"', '""', text)

    ids, declared, code = {}, {}, {}
    for path in sorted(_QML_ROOT.rglob("*.qml")):
        code[path] = code_only(path.read_text(encoding="utf-8"))
        own_ids = set(re.findall(r"^\s*id:\s*(\w+)", code[path], re.M))
        properties = {name for _, name in re.findall(r"property\s+(\w+)\s+(\w+)", code[path])}
        ids[path] = own_ids
        declared[path] = own_ids | properties

    foreign = {name: path for path, names in ids.items() for name in names}
    offences = []
    for path in sorted(_QML_ROOT.rglob("*.qml")):
        # A leading dot means it is somebody's sub-property, not a bare id.
        for name in sorted(set(re.findall(r"(?<![.\w])([a-z]\w*)\s*\.", code[path]))):
            if name in declared[path] or name not in foreign:
                continue
            if foreign[name] == path:
                continue
            offences.append(f"{path.name} reaches `{name}.`, an id in {foreign[name].name}")
    assert offences == []


def test_loading_an_action_into_the_editor_fills_the_visible_fields():
    with _Warnings() as log:
        engine, controller = build_engine(start_hotkeys=False)
        window = engine.rootObjects()[0]
        controller.addAction({"kind": "text", "value": "Hello"})
        _app.processEvents()
        QTest.qWait(100)

        QMetaObject.invokeMethod(
            window, "loadActionIntoEditor", Qt.DirectConnection, Q_ARG("QVariant", 0)
        )
        _app.processEvents()
        QTest.qWait(100)

        value_field = window.findChild(QQuickItem, "actionValueField")
        assert value_field is not None
        assert value_field.property("text") == "Hello"
        controller.shutdown()

    assert log.broken == []


def test_the_run_bar_and_sequence_page_share_the_inspector_s_live_run_form():
    """Both start runs from what is typed now, not from what was last applied."""
    engine, controller = build_engine(start_hotkeys=False)
    window = engine.rootObjects()[0]
    # Compared inside QML, because a custom QML type has no Python converter.
    assert evaluate_in(window, "inspector.runSettingsForm !== null") is True
    assert evaluate_in(window, "typeof inspector.runSettingsForm.payload") == "function"
    # A property bound to an id of the same name silently resolves to itself,
    # which reads as a live form right up until you call anything on it.
    assert evaluate_in(window, "runBar.runForm === inspector.runSettingsForm") is True
    assert (
        evaluate_in(window, "sequencePage.runForm === inspector.runSettingsForm") is True
    )
    controller.shutdown()

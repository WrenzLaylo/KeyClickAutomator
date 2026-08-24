from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QFont, QFontDatabase, QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWidgets import QApplication

from qt_controller import APP_VERSION, AutomatorController


def resource_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def install_fonts() -> None:
    root = resource_root() / "assets" / "fonts"
    for name in ("Inter-Regular.ttf", "Inter-Medium.ttf", "Inter-SemiBold.ttf", "Inter-Bold.ttf"):
        QFontDatabase.addApplicationFont(str(root / name))


def build_engine(start_hotkeys: bool = True) -> tuple[QQmlApplicationEngine, AutomatorController]:
    install_fonts()
    controller = AutomatorController(start_hotkeys=start_hotkeys)
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("controller", controller)
    qml_path = resource_root() / "qml" / "Main.qml"
    engine.load(QUrl.fromLocalFile(str(qml_path)))
    return engine, controller


def create_application(arguments: list[str] | None = None) -> QApplication:
    """Use QApplication because profile open/save dialogs are QWidget based."""
    existing = QApplication.instance()
    return existing if existing is not None else QApplication(arguments or [])


def main() -> int:
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    app = create_application(sys.argv)
    app.setApplicationName("KeyClick Automator")
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("KeyClick Automator")
    app.setWindowIcon(QIcon(str(resource_root() / "assets" / "app.ico")))
    app.setFont(QFont("Inter", 10))
    engine, controller = build_engine(start_hotkeys=True)
    if not engine.rootObjects():
        controller.shutdown()
        return 1
    code = app.exec()
    controller.shutdown()
    return code


if __name__ == "__main__":
    raise SystemExit(main())

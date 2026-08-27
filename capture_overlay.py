"""Frozen, dimmed desktop overlay used to record pointer positions safely."""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QKeyEvent, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget


class _CaptureScreenOverlay(QWidget):
    """One frozen screenshot surface for one monitor."""

    def __init__(
        self,
        screen,
        snapshot: QPixmap,
        title: str,
        on_selected: Callable[[], None],
        on_cancelled: Callable[[], None],
    ) -> None:
        super().__init__(None)
        self._screen = screen
        self._snapshot = snapshot
        self._title = title
        self._on_selected = on_selected
        self._on_cancelled = on_cancelled
        self._pointer = QPoint(-1, -1)
        self._selection_sent = False

        self.setObjectName("positionCaptureOverlay")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setGeometry(screen.geometry())

    def show_overlay(self) -> None:
        self.show()
        if self.windowHandle() is not None:
            self.windowHandle().setScreen(self._screen)
        self.setGeometry(self._screen.geometry())
        self.raise_()
        self.activateWindow()
        self.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt virtual method
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.drawPixmap(self.rect(), self._snapshot)
        painter.fillRect(self.rect(), QColor(8, 15, 28, 112))

        panel_width = min(520, max(300, self.width() - 48))
        panel = QRect((self.width() - panel_width) // 2, 28, panel_width, 76)
        painter.setPen(QPen(QColor(255, 255, 255, 42), 1))
        painter.setBrush(QColor(18, 25, 40, 232))
        painter.drawRoundedRect(panel, 16, 16)

        painter.setPen(QColor("#FFFFFF"))
        painter.setFont(QFont("Inter", 12, QFont.Weight.DemiBold))
        painter.drawText(
            panel.adjusted(18, 10, -18, -34),
            Qt.AlignmentFlag.AlignCenter,
            self._title,
        )
        painter.setPen(QColor("#C7D3E8"))
        painter.setFont(QFont("Inter", 9, QFont.Weight.Normal))
        painter.drawText(
            panel.adjusted(18, 38, -18, -8),
            Qt.AlignmentFlag.AlignCenter,
            "The screen is frozen  •  Click to record  •  Esc to cancel",
        )

        if self._pointer.x() >= 0:
            painter.setPen(QPen(QColor("#FFFFFF"), 2))
            painter.setBrush(QColor(21, 101, 255, 70))
            painter.drawEllipse(self._pointer, 14, 14)
            painter.drawLine(self._pointer.x() - 24, self._pointer.y(), self._pointer.x() + 24, self._pointer.y())
            painter.drawLine(self._pointer.x(), self._pointer.y() - 24, self._pointer.x(), self._pointer.y() + 24)
            painter.setPen(QPen(QColor("#1565FF"), 2))
            painter.drawEllipse(self._pointer, 8, 8)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt virtual method
        self._pointer = event.position().toPoint()
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt virtual method
        if event.button() != Qt.MouseButton.LeftButton or self._selection_sent:
            return
        self._selection_sent = True
        event.accept()
        self._on_selected()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt virtual method
        if event.key() == Qt.Key.Key_Escape:
            event.accept()
            self._on_cancelled()
            return
        super().keyPressEvent(event)


class PositionCaptureOverlay(QObject):
    """Hide KeyClick, freeze every monitor, and intercept one pointer click."""

    selected = Signal()
    cancelled = Signal()
    failed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._active = False
        self._title = "Pick a pointer position"
        self._overlays: list[_CaptureScreenOverlay] = []
        self._hidden_windows: list[object] = []

    @property
    def active(self) -> bool:
        return self._active

    def begin(self, title: str) -> bool:
        if self._active:
            return False
        app = QGuiApplication.instance()
        if app is None:
            self.failed.emit("The screen capture overlay is unavailable.")
            return False

        self._active = True
        self._title = title

        # Offscreen is used by the automated QML tests. Keep the state armed so
        # tests can commit a point explicitly without creating fake monitors.
        if not isinstance(app, QGuiApplication) or QGuiApplication.platformName().casefold() == "offscreen":
            return True

        for window in QGuiApplication.topLevelWindows():
            if window.isVisible():
                self._hidden_windows.append(window)
                window.hide()

        # Let the compositor redraw the desktop after KeyClick disappears.
        QTimer.singleShot(180, self._show_frozen_screens)
        return True

    def _show_frozen_screens(self) -> None:
        if not self._active:
            return
        screens = QGuiApplication.screens()
        snapshots = [(screen, screen.grabWindow(0)) for screen in screens]
        if not snapshots or any(pixmap.isNull() for _screen, pixmap in snapshots):
            self.finish()
            self.failed.emit("KeyClick could not freeze every monitor. Try recording the position again.")
            return

        for screen, snapshot in snapshots:
            overlay = _CaptureScreenOverlay(
                screen,
                snapshot,
                self._title,
                self.selected.emit,
                self.cancelled.emit,
            )
            self._overlays.append(overlay)
        for overlay in self._overlays:
            overlay.show_overlay()

    def finish(self) -> None:
        if not self._active and not self._overlays and not self._hidden_windows:
            return
        self._active = False
        for overlay in self._overlays:
            overlay.hide()
            overlay.deleteLater()
        self._overlays.clear()

        windows = list(self._hidden_windows)
        self._hidden_windows.clear()
        for window in windows:
            window.show()
        if windows:
            windows[0].requestActivate()

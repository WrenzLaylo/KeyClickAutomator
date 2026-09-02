"""Choosing what to automate: a window, a browser tab, or the desktop."""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

import pyautogui
from PySide6.QtCore import Property, QStandardPaths, Qt, QUrl, Slot
from PySide6.QtGui import QGuiApplication

from chrome_backend import (
    ChromeTabBackend,
    ChromeTargetError,
    browser_available,
    find_tab,
    launch_chrome,
    list_tabs,
    wait_for_browser,
)
from controller_signals import ControllerSignals
from engine import RunSettings
from preflight import looks_like_a_browser
from window_backend import (
    Win32WindowService,
    WindowInfo,
    WindowSelector,
    WindowTargetError,
)


class TargetingMixin(ControllerSignals):
    """Everything behind the one picker: windows, browser tabs, the desktop."""

    @Property(bool, notify=ControllerSignals.windowPickStateChanged)
    def windowPickPending(self) -> bool:
        return self._window_pick_countdown > 0

    @Property(int, notify=ControllerSignals.windowPickStateChanged)
    def windowPickCountdown(self) -> int:
        return self._window_pick_countdown

    @Property("QVariantList", notify=ControllerSignals.windowEntriesChanged)
    def windowEntries(self) -> list[dict[str, Any]]:
        return self._window_entries

    @Property(str, notify=ControllerSignals.windowEntriesChanged)
    def desktopPreviewUrl(self) -> str:
        return self._desktop_preview_url

    @Property("QVariantMap", notify=ControllerSignals.targetSettingsChanged)
    def targetSettings(self) -> dict[str, Any]:
        settings = self._run_settings
        selector = WindowSelector(
            settings.target_window_title,
            settings.target_window_class,
            settings.target_executable,
        )
        return {
            "mode": settings.target_mode,
            "windowSelected": selector.selected,
            "windowTitle": settings.target_window_title,
            "windowClass": settings.target_window_class,
            "executable": settings.target_executable,
            "displayName": settings.target_window_title
            or (Path(settings.target_executable).stem if settings.target_executable else settings.target_window_class)
            or "No window selected",
            "tabSelected": bool(settings.target_tab_url.strip()),
            "tabUrl": settings.target_tab_url,
            "tabTitle": settings.target_tab_title,
            "tabName": settings.target_tab_title or settings.target_tab_url or "No tab selected",
            "browserPort": settings.browser_port,
        }

    # -- browser tab targeting -------------------------------------------------

    @Property("QVariantList", notify=ControllerSignals.browserTabsChanged)
    def browserTabs(self) -> list[dict[str, Any]]:
        return self._browser_tabs

    @Property(bool, notify=ControllerSignals.browserTabsChanged)
    def browserReady(self) -> bool:
        return self._browser_ready

    @Slot(result=bool)
    def refreshBrowserTabs(self) -> bool:
        """List the tabs the debuggable browser is exposing right now."""
        port = self._run_settings.browser_port
        self._browser_ready = browser_available(port)
        if not self._browser_ready:
            self._browser_tabs = []
            self.browserTabsChanged.emit()
            return False
        try:
            tabs = list_tabs(port)
        except ChromeTargetError as exc:
            self._browser_tabs = []
            self.browserTabsChanged.emit()
            self.toast.emit(str(exc), "error")
            return False
        current = self._run_settings.target_tab_url
        self._browser_tabs = [
            {
                "id": tab.target_id,
                "title": tab.title or tab.url,
                "url": tab.url,
                "current": bool(current) and tab.url == current,
            }
            for tab in tabs
        ]
        self.browserTabsChanged.emit()
        return True

    @Slot(result=bool)
    def startBrowser(self) -> bool:
        """Launch a debuggable browser in KeyClick's own persistent profile."""
        port = self._run_settings.browser_port
        if browser_available(port):
            self.refreshBrowserTabs()
            return True
        chrome = self._chrome_executable()
        if not chrome:
            self.toast.emit(
                "Could not find Google Chrome. Install it, or open a browser with "
                f"--remote-debugging-port={port} yourself.",
                "error",
            )
            return False
        try:
            launch_chrome(chrome, self._browser_profile_root(), port=port)
        except OSError as exc:
            self.toast.emit(f"Could not start the browser: {exc}", "error")
            return False
        if not wait_for_browser(port, timeout=30.0):
            self.toast.emit("The browser did not open its debug port in time.", "error")
            return False
        self.refreshBrowserTabs()
        self.toast.emit("Browser ready for automation", "success")
        return True

    @Slot(str, result=bool)
    def selectBrowserTab(self, target_id: str) -> bool:
        if self._running:
            self.toast.emit("Stop the current run before changing its target.", "error")
            return False
        if not self._browser_tabs:
            # Selecting without having listed first is legitimate: refresh once
            # rather than failing on an empty cache.
            self.refreshBrowserTabs()
        chosen = next(
            (tab for tab in self._browser_tabs if tab["id"] == str(target_id)), None
        )
        if chosen is None:
            self.toast.emit("That tab is no longer open. Refresh the list.", "error")
            self.refreshBrowserTabs()
            return False
        self._run_settings.target_tab_url = chosen["url"]
        self._run_settings.target_tab_title = chosen["title"]
        self._set_dirty(True)
        self.targetSettingsChanged.emit()
        self.refreshBrowserTabs()
        self.toast.emit(f"Targeting {chosen['title'][:48]}", "success")
        return True

    def _start_browser_point_capture(self, target: int) -> bool:
        """Record a viewport point by asking the page which pixel was clicked."""
        try:
            tab = self._resolve_browser_tab(self._run_settings)
        except WindowTargetError as exc:
            self.toast.emit(str(exc), "error")
            return False
        try:
            backend = ChromeTabBackend(tab)
        except ChromeTargetError as exc:
            self.toast.emit(str(exc), "error")
            return False

        self._set_status("Pick a point", "accent")
        self.toast.emit("Click the spot in the browser tab", "neutral")

        def worker() -> None:
            picked = None
            try:
                picked = backend.capture_click_point(timeout=45.0)
            except ChromeTargetError:
                picked = None
            finally:
                backend.close()
            self.browserPointCaptured.emit(target, *(picked or (-1, -1, 0, 0)))

        self._browser_capture_thread = threading.Thread(target=worker, daemon=True)
        self._browser_capture_thread.start()
        return True

    @Slot(int, int, int, int, int)
    def _finish_browser_point_capture(
        self, target: int, x: int, y: int, width: int, height: int
    ) -> None:
        if x < 0 or y < 0:
            self._set_status("Ready", "neutral")
            self.toast.emit("Nothing was picked in the browser tab.", "neutral")
            return
        self._set_status("Ready", "neutral")
        self.positionCaptured.emit(target, x, y, "viewport", width, height)
        self.toast.emit(f"Recorded {x}, {y} in the tab", "success")

    # -- one list of everything you could automate ------------------------------

    @Property("QVariantList", notify=ControllerSignals.targetsChanged)
    def automationTargets(self) -> list[dict[str, Any]]:
        """Windows and browser tabs together, so the user picks a thing, not a mechanism.

        Pairing a target with the wrong delivery mechanism was the failure that
        cost a whole session: a browser window chosen in background-window mode
        runs perfectly and delivers nothing. Choosing the mechanism here makes
        that combination unreachable rather than merely detected.
        """
        settings = self._run_settings
        entries: list[dict[str, Any]] = [
            {
                "kind": "desktop",
                "id": "desktop",
                "previewUrl": self._desktop_preview_url,
                "minimized": False,
                "title": "This computer",
                "subtitle": "Uses your real mouse and keyboard",
                "current": settings.target_mode == "desktop",
                "advice": "",
            }
        ]

        for tab in self._browser_tabs:
            entries.append(
                {
                    "kind": "browser",
                    "id": tab["id"],
                    "previewUrl": "",
                    "minimized": False,
                    "title": tab["title"] or tab["url"],
                    "subtitle": tab["url"],
                    "current": settings.target_mode == "browser"
                    and tab["url"] == settings.target_tab_url,
                    "advice": "",
                }
            )

        for entry in self._window_entries:
            info = self._window_candidates.get(int(entry.get("handle", 0) or 0))
            executable = getattr(info, "executable", "")
            is_browser = looks_like_a_browser(
                entry.get("title", ""), getattr(info, "class_name", ""), executable
            )
            entries.append(
                {
                    "kind": "window",
                    "id": str(entry.get("handle", "")),
                    "title": entry.get("title", "") or entry.get("appName", ""),
                    "subtitle": entry.get("appName", "") or "Open window",
                    # Carried through so the picker can still show you the window
                    # rather than only naming it.
                    "previewUrl": entry.get("previewUrl", ""),
                    "minimized": entry.get("minimized", False),
                    "current": settings.target_mode == "window"
                    and entry.get("selected", False),
                    # Offered, but never silently: a browser window cannot receive
                    # background messages at all.
                    "advice": "Pick this app's tab instead — page clicks never reach a browser window"
                    if is_browser
                    else "",
                }
            )
        return entries

    @Slot(result=bool)
    def refreshAutomationTargets(self) -> bool:
        self.refreshWindowEntries()
        self.refreshBrowserTabs()
        self.targetsChanged.emit()
        return True

    @Slot(str, str, result=bool)
    def selectAutomationTarget(self, kind: str, identifier: str) -> bool:
        """Choose what to automate; KeyClick decides how to reach it."""
        if self._running or self._queue_active:
            self.toast.emit("Stop the current run before changing its target.", "error")
            return False
        kind = str(kind).strip().lower()
        if kind == "desktop":
            self.setTargetMode("desktop")
            self.targetsChanged.emit()
            return True
        if kind == "browser":
            if not self.setTargetMode("browser"):
                return False
            chosen = self.selectBrowserTab(identifier)
            self.targetsChanged.emit()
            return chosen
        if kind == "window":
            if not self.setTargetMode("window"):
                return False
            chosen = self.selectWindowTarget(identifier)
            self.targetsChanged.emit()
            return chosen
        return False

    @Property(str, notify=ControllerSignals.targetsChanged)
    def targetSummary(self) -> str:
        settings = self._run_settings
        if settings.target_mode == "desktop":
            return "This computer"
        if settings.target_mode == "browser":
            return settings.target_tab_title or settings.target_tab_url or "No tab chosen"
        return self.targetSettings["displayName"]

    def _browser_profile_root(self) -> Path:
        return Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))

    @staticmethod
    def _chrome_executable() -> str:
        for candidate in (
            os.environ.get("KEYCLICK_CHROME", ""),
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ):
            if candidate and Path(candidate).is_file():
                return candidate
        return ""

    def _resolve_browser_tab(self, settings: RunSettings):
        try:
            return find_tab(
                port=settings.browser_port,
                url=settings.target_tab_url,
                title=settings.target_tab_title,
            )
        except ChromeTargetError as exc:
            raise WindowTargetError(str(exc)) from exc

    def _get_window_service(self):
        if self._window_service is None:
            self._window_service = Win32WindowService()
        return self._window_service

    @staticmethod
    def _window_selector(settings: RunSettings) -> WindowSelector:
        return WindowSelector(
            settings.target_window_title,
            settings.target_window_class,
            settings.target_executable,
        )

    def _resolve_target_info(
        self,
        settings: RunSettings | None = None,
        preferred_hwnd: int | None = None,
        remember: bool | None = None,
    ) -> WindowInfo:
        selected_settings = settings or self._run_settings
        selected_preference = self._target_hwnd if preferred_hwnd is None else int(preferred_hwnd)
        info = self._get_window_service().resolve_window(
            self._window_selector(selected_settings),
            selected_preference,
        )
        self._get_window_service().ensure_usable(info.hwnd)
        should_remember = settings is None if remember is None else bool(remember)
        if should_remember:
            self._target_hwnd = info.hwnd
        return info

    @staticmethod
    def _window_app_name(info: WindowInfo) -> str:
        stem = Path(info.executable).stem if info.executable else info.class_name
        aliases = {
            "chrome": "Google Chrome",
            "msedge": "Microsoft Edge",
            "firefox": "Mozilla Firefox",
            "discord": "Discord",
            "zoom": "Zoom",
            "slack": "Slack",
            "teams": "Microsoft Teams",
            "ms-teams": "Microsoft Teams",
            "applicationframehost": "Windows app",
        }
        return aliases.get(stem.casefold(), stem.replace("_", " ").strip().title() or "Application")

    def _window_preview(self, hwnd: int, name: str) -> str:
        app = QGuiApplication.instance()
        if not isinstance(app, QGuiApplication) or QGuiApplication.platformName().casefold() == "offscreen":
            return ""
        screen = app.primaryScreen()
        if screen is None:
            return ""
        try:
            pixmap = screen.grabWindow(int(hwnd))
            if pixmap.isNull():
                return ""
            cache_dir = Path(QStandardPaths.writableLocation(QStandardPaths.CacheLocation)) / "window-previews"
            cache_dir.mkdir(parents=True, exist_ok=True)
            path = cache_dir / f"{name}-{int(hwnd)}.png"
            preview = pixmap.scaled(
                420,
                236,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            if not preview.save(str(path), "PNG"):
                return ""
            return QUrl.fromLocalFile(str(path)).toString() + f"?v={path.stat().st_mtime_ns}"
        except Exception:
            return ""

    def _refresh_window_selection(self) -> None:
        selected = self._target_hwnd if self._run_settings.target_mode == "window" else 0
        self._window_entries = [
            {**entry, "selected": int(entry["handle"]) == selected}
            for entry in self._window_entries
        ]
        self.windowEntriesChanged.emit()

    @Slot(result=bool)
    def refreshWindowEntries(self) -> bool:
        if self._running:
            self.toast.emit("Stop the automation before changing its target.", "error")
            return False
        try:
            service = self._get_window_service()
            candidates = service.list_windows(excluded_process_id=os.getpid())[:18]
        except Exception as exc:
            self._window_candidates = {}
            self._window_entries = []
            self._desktop_preview_url = ""
            self.windowEntriesChanged.emit()
            self.toast.emit(f"Open windows could not be listed: {exc}", "error")
            return False

        if self._run_settings.target_mode == "window" and self._window_selector(self._run_settings).selected:
            try:
                resolved = service.resolve_window(self._window_selector(self._run_settings), self._target_hwnd)
                self._target_hwnd = resolved.hwnd
            except Exception:
                # The list is still useful when a saved target is closed or
                # ambiguous; the user can choose a replacement visually.
                pass

        self._window_candidates = {info.hwnd: info for info in candidates}
        self._desktop_preview_url = self._window_preview(0, "desktop")
        self._window_entries = [
            {
                "handle": str(info.hwnd),
                "title": info.title,
                "appName": self._window_app_name(info),
                "previewUrl": "" if info.is_minimized else self._window_preview(info.hwnd, "window"),
                "minimized": info.is_minimized,
                "selected": self._run_settings.target_mode == "window" and info.hwnd == self._target_hwnd,
            }
            for info in candidates
        ]
        self.windowEntriesChanged.emit()
        return True

    def _set_window_target(self, info: WindowInfo) -> None:
        self._target_hwnd = info.hwnd
        self._run_settings.target_mode = "window"
        self._run_settings.target_window_title = info.title
        self._run_settings.target_window_class = info.class_name
        self._run_settings.target_executable = info.executable
        self.targetSettingsChanged.emit()
        self._refresh_window_selection()
        self._clear_undo()
        self._set_dirty(True)
        self.toast.emit(f"Target set to {info.display_name}", "success")

    @Slot(str, result=bool)
    def selectWindowTarget(self, handle: str) -> bool:
        if self._running:
            self.toast.emit("Stop the automation before choosing a target window.", "error")
            return False
        try:
            hwnd = int(str(handle))
            info = self._window_candidates.get(hwnd)
            if info is None:
                raise WindowTargetError("That window is no longer available. Refresh the list and try again.")
            self._get_window_service().ensure_usable(info.hwnd)
        except (TypeError, ValueError, WindowTargetError) as exc:
            self.toast.emit(f"Target window could not be selected: {exc}", "error")
            return False
        self.cancelPositionCapture(announce=False)
        self._set_window_target(info)
        return True

    @Slot(str, result=bool)
    def setTargetMode(self, mode: str) -> bool:
        normalized = str(mode).strip().lower()
        if normalized not in {"desktop", "window", "browser"}:
            return False
        if self._running:
            self.toast.emit("Stop the current run before changing its target.", "error")
            return False
        if normalized == self._run_settings.target_mode:
            return True
        self._cancel_action_capture(announce=False)
        self.cancelPositionCapture(announce=False)
        self.cancelWindowPick(announce=False)
        self._run_settings.target_mode = normalized
        self.targetSettingsChanged.emit()
        self._refresh_window_selection()
        self._clear_undo()
        self._set_dirty(True)
        if normalized == "window":
            self.toast.emit("Background window mode selected · choose a target window", "neutral")
        else:
            self.toast.emit("Desktop mode selected", "success")
        return True

    @Slot(result=bool)
    def startWindowPick(self) -> bool:
        if self._running:
            self.toast.emit("Stop the automation before choosing a target window.", "error")
            return False
        self._cancel_action_capture(announce=False)
        if self._capture_listener is not None:
            self.toast.emit("Finish recording the current key or shortcut first.", "error")
            return False
        self.cancelPositionCapture(announce=False)
        self.cancelWindowPick(announce=False)
        return self.refreshWindowEntries()

    @Slot()
    def cancelWindowPick(self, announce: bool = True) -> None:
        self._window_pick_countdown = 0
        self.windowPickStateChanged.emit()

    @Slot()
    def captureWindowTarget(self) -> None:
        self.cancelWindowPick(announce=False)
        try:
            point = pyautogui.position()
            info = self._get_window_service().window_at_point(int(point.x), int(point.y))
            if info.process_id == os.getpid():
                raise WindowTargetError("Move the pointer over the app you want to automate, not KeyClick itself.")
        except Exception as exc:
            self.toast.emit(f"Target window could not be selected: {exc}", "error")
            return
        self._set_window_target(info)

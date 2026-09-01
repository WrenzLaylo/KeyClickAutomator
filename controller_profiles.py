"""Saving, opening, deleting, and restoring profiles and recovery drafts."""
from __future__ import annotations

import copy
import os
import threading
from pathlib import Path
from typing import Any

import pyautogui
from PySide6.QtCore import Property, QStandardPaths, QTimer, Slot
from PySide6.QtWidgets import QFileDialog
from pynput import keyboard

from capture_overlay import PositionCaptureOverlay
from chrome_backend import (
    ChromeTabBackend,
    ChromeTargetError,
    browser_available,
    find_tab,
    launch_chrome,
    list_tabs,
    wait_for_browser,
)
from engine import (
    Action,
    AutomationRunner,
    RunSettings,
    canonical_global_shortcuts,
    load_profile,
    save_profile,
)
from preflight import Check, blocking_failures, looks_like_a_browser, preflight
from profile_catalog import default_profile_directory, normalize_path, profile_name
from profile_history import restore as restore_version, snapshot, versions
from recovery_store import (
    describe_recovery_draft,
    read_recovery_payload,
    remove_recovery_draft,
    write_recovery_draft,
)
from run_session import RunSession
from shortcut_service import global_shortcut_conflicts, pynput_hotkey
from window_backend import (
    WindowInfo,
    WindowMessageBackend,
    WindowSelector,
    WindowTargetError,
    Win32WindowService,
)

from controller_signals import ControllerSignals


class ProfilesMixin(ControllerSignals):
    """Profile files on disk and the drafts that protect them."""

    @Slot(result=bool)
    def recoverDraft(self) -> bool:
        if not self._draft_available:
            return False
        try:
            payload = read_recovery_payload(self._recovery_path)
            actions, settings = load_profile(self._recovery_path)
            if self._hotkeys_enabled and not self._install_hotkeys(settings):
                return False
        except (OSError, ValueError, TypeError) as exc:
            self.toast.emit(f"Recovery copy could not be opened: {exc}", "error")
            return False
        self._model.mutate(lambda: setattr(self, "actions", actions))
        self._run_settings = settings
        self._target_hwnd = 0
        recovered_name = str(payload.get("profile_name") or "Untitled sequence")
        if self._current_profile_path is not None:
            self._current_profile_path = None
            self.currentProfilePathChanged.emit()
        self._current_profile_name = f"Recovered — {recovered_name}"
        self.currentProfileNameChanged.emit()
        self._selected_index = 0 if actions else -1
        self._clear_undo()
        self._set_run_settings_pending(False)
        self._notify_actions()
        self.selectedIndexChanged.emit()
        self.runSettingsChanged.emit()
        self.targetSettingsChanged.emit()
        self._set_dirty(True)
        self.toast.emit("Recovery copy restored", "success")
        return True

    @Slot()
    def discardDraft(self) -> None:
        self._remove_recovery_draft()

    @Slot(result=bool)
    def saveProfile(self) -> bool:
        if self._current_profile_path:
            return self._save_profile_path(self._current_profile_path)
        return self.saveProfileAs()

    @Slot(result=bool)
    def saveProfileAs(self) -> bool:
        suggested_name = self._current_profile_name.strip() or "Untitled sequence"
        for character in '<>:"/\\|?*':
            suggested_name = suggested_name.replace(character, "_")
        suggested_path = self._current_profile_path or str(
            Path(self._profile_directory) / f"{suggested_name}.kca.json"
        )
        path, _ = QFileDialog.getSaveFileName(
            None,
            "Save automation profile",
            suggested_path,
            "KeyClick profiles (*.kca.json);;JSON (*.json)",
        )
        if not path:
            return False
        if not path.lower().endswith((".json", ".kca.json")):
            path += ".kca.json"
        return self._save_profile_path(path)

    def _save_profile_path(self, path: str | Path) -> bool:
        normalized = normalize_path(path)
        try:
            # Keep what is on disk before overwriting it. Saving is the most
            # destructive action in the app and used to be the least reversible.
            try:
                snapshot(normalized)
            except OSError:
                pass  # history is a safety net, never a reason to block a save
            save_profile(normalized, self.actions, self._run_settings)
            self._set_profile_directory(Path(normalized).parent)
            self._set_current_profile(normalized)
            self._set_dirty(False)
            self.refreshProfiles()
            self.toast.emit(f"Saved {Path(normalized).name}", "success")
            return True
        except OSError as exc:
            self.toast.emit(str(exc), "error")
            return False

    @Slot(result=bool)
    def openProfile(self) -> bool:
        path, _ = QFileDialog.getOpenFileName(
            None,
            "Open automation profile",
            self._profile_directory,
            "KeyClick profiles (*.kca.json *.json)",
        )
        if not path:
            return False
        return self.openProfilePath(path)

    @Slot(str, result=bool)
    def openProfilePath(self, path: str) -> bool:
        if self._running:
            self.toast.emit("Stop the current run before switching profiles.", "error")
            return False
        normalized = normalize_path(path)
        if not Path(normalized).is_file():
            self.toast.emit("That profile file is no longer available. Refresh the list.", "error")
            self.refreshProfiles()
            return False
        try:
            actions, settings = load_profile(normalized)
            if self._hotkeys_enabled and not self._install_hotkeys(settings):
                return False
            self._model.mutate(lambda: setattr(self, "actions", actions))
            self._run_settings = settings
            self._target_hwnd = 0
            self._set_profile_directory(Path(normalized).parent)
            self._set_current_profile(normalized)
            self._selected_index = 0 if actions else -1
            self._clear_undo()
            self._set_run_settings_pending(False)
            self._notify_actions()
            self.selectedIndexChanged.emit()
            self.runSettingsChanged.emit()
            self.targetSettingsChanged.emit()
            self._set_dirty(False)
            self.toast.emit(f"Opened {Path(normalized).name}", "success")
            return True
        except (OSError, ValueError, TypeError) as exc:
            self.toast.emit(str(exc), "error")
            return False

    @Slot(str, result="QVariantList")
    def profileVersions(self, path: str) -> list[dict[str, object]]:
        if not path:
            return []
        return [version.as_entry() for version in versions(normalize_path(path))]

    @Slot(str, str, result=bool)
    def restoreProfileVersion(self, path: str, version_path: str) -> bool:
        if self._running or self._queue_active:
            self.toast.emit("Stop the current run before restoring a version.", "error")
            return False
        normalized = normalize_path(path)
        try:
            restore_version(normalized, version_path)
        except OSError as exc:
            self.toast.emit(str(exc), "error")
            return False
        self.refreshProfiles()
        if (
            self._current_profile_path
            and self._path_key(self._current_profile_path) == self._path_key(normalized)
        ):
            self.openProfilePath(normalized)
        self.toast.emit(f"Restored {profile_name(normalized)}", "success")
        return True

    @Slot(str, result=bool)
    def deleteProfilePath(self, path: str) -> bool:
        """Delete a saved profile file. The open sequence is never discarded."""
        if self._running or self._queue_active:
            self.toast.emit("Stop the current run before deleting a profile.", "error")
            return False
        normalized = normalize_path(path)
        name = profile_name(normalized)
        try:
            try:
                snapshot(normalized)
            except OSError:
                pass
            Path(normalized).unlink()
        except FileNotFoundError:
            self.toast.emit(f"{name} was already gone.", "neutral")
            self.refreshProfiles()
            return False
        except OSError as exc:
            self.toast.emit(f"Could not delete {name}: {exc}", "error")
            return False

        # Drop it from the run queue so the runner cannot point at a dead file.
        removed_from_queue = [
            session
            for session in self._run_queue
            if self._path_key(session.profile_path) == self._path_key(normalized)
        ]
        for session in removed_from_queue:
            self._run_queue.remove(session)
        if removed_from_queue:
            self.runQueueChanged.emit()

        # Keep the user's work on screen; it simply becomes unsaved again.
        if (
            self._current_profile_path
            and self._path_key(self._current_profile_path) == self._path_key(normalized)
        ):
            self._set_current_profile(None)
            self._set_dirty(bool(self.actions))

        self.refreshProfiles()
        self.toast.emit(f"Deleted {name}", "neutral")
        return True


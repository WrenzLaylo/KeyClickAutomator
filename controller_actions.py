"""The sequence itself: the list model QML renders, and editing the actions in it."""
from __future__ import annotations

import copy
from dataclasses import asdict
from typing import Any

from PySide6.QtCore import (
    Property,
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    QObject,
    Qt,
    Slot,
)

from controller_signals import ControllerSignals
from engine import Action


class ActionListModel(QAbstractListModel):
    TitleRole = Qt.UserRole + 1
    SubtitleRole = Qt.UserRole + 2
    KindRole = Qt.UserRole + 3
    EnabledRole = Qt.UserRole + 4
    IndexRole = Qt.UserRole + 5
    IconRole = Qt.UserRole + 6

    def __init__(self, controller: "AutomatorController") -> None:
        super().__init__()
        self.controller = controller

    def roleNames(self) -> dict[int, QByteArray]:
        return {
            self.TitleRole: QByteArray(b"title"),
            self.SubtitleRole: QByteArray(b"subtitle"),
            self.KindRole: QByteArray(b"kind"),
            self.EnabledRole: QByteArray(b"actionEnabled"),
            self.IndexRole: QByteArray(b"actionIndex"),
            self.IconRole: QByteArray(b"actionIcon"),
        }

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.controller.actions)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid() or not 0 <= index.row() < len(self.controller.actions):
            return None
        action = self.controller.actions[index.row()]
        if role == self.TitleRole:
            return self._title(action)
        if role == self.SubtitleRole:
            return self._subtitle(action)
        if role == self.KindRole:
            return action.kind
        if role == self.EnabledRole:
            return action.enabled
        if role == self.IndexRole:
            return index.row()
        if role == self.IconRole:
            return self._icon(action.kind)
        return None

    @staticmethod
    def _title(action: Action) -> str:
        if action.kind == "key":
            return f"Press {action.value.upper()}"
        if action.kind == "hotkey":
            return f"Shortcut {action.value.upper()}"
        if action.kind == "text":
            preview = action.value.replace("\n", " ↵ ")
            return f"Type “{preview[:28]}{'…' if len(preview) > 28 else ''}”"
        names = {
            "left_click": "Left click",
            "right_click": "Right click",
            "double_click": "Double click",
            "middle_click": "Middle click",
            "scroll": "Scroll",
            "drag": "Drag pointer",
        }
        return names.get(action.kind, action.kind.replace("_", " ").title())

    @staticmethod
    def _subtitle(action: Action) -> str:
        parts: list[str] = []
        click_actions = {"left_click", "right_click", "double_click", "middle_click"}
        if action.kind in click_actions and action.use_current_pointer:
            parts.append("current pointer")
        elif action.kind in {*click_actions, "scroll", "drag"}:
            prefix = "window " if action.coordinate_space == "window" else ""
            parts.append(f"{prefix}{action.x}, {action.y}")
            if action.coordinate_space == "window" and action.reference_width and action.reference_height:
                parts.append("scales with window")
        if action.kind == "drag":
            parts[-1] += f" → {action.x2}, {action.y2}"
        if action.kind == "scroll":
            parts.append(f"{action.amount:+d} steps")
        if action.repeats > 1:
            parts.append(f"repeat {action.repeats}×")
        parts.append(f"wait {action.delay_after:g}s")
        return "  ·  ".join(parts)

    @staticmethod
    def _icon(kind: str) -> str:
        return {
            "key": "K",
            "hotkey": "⌘",
            "text": "T",
            "left_click": "↖",
            "right_click": "↗",
            "double_click": "×2",
            "middle_click": "●",
            "scroll": "↕",
            "drag": "↗",
        }.get(kind, "•")

    def mutate(self, callback) -> None:
        self.beginResetModel()
        callback()
        self.endResetModel()

    def move_row(self, source: int, target: int) -> bool:
        count = self.rowCount()
        if not (0 <= source < count and 0 <= target < count) or source == target:
            return False

        # Qt expects destination_child in the model's pre-move coordinates.
        destination_child = target + 1 if target > source else target
        if not self.beginMoveRows(
            QModelIndex(), source, source, QModelIndex(), destination_child
        ):
            return False
        action = self.controller.actions.pop(source)
        self.controller.actions.insert(target, action)
        self.endMoveRows()

        first = min(source, target)
        last = max(source, target)
        self.dataChanged.emit(
            self.index(first, 0), self.index(last, 0), [self.IndexRole]
        )
        return True

    def notify_row(self, row: int, roles: list[int]) -> None:
        if not 0 <= row < self.rowCount():
            return
        model_index = self.index(row, 0)
        self.dataChanged.emit(model_index, model_index, roles)


class ActionsMixin(ControllerSignals):
    """Reading and editing the action list.

    Not a QObject: PySide6 still registers these Property and Slot objects as
    long as the class they are mixed into is one.
    """

    @Property(QObject, constant=True)
    def actionModel(self):
        return self._model
    @Property(str, notify=ControllerSignals.summaryChanged)
    def summary(self) -> str:
        active = [a for a in self.actions if a.enabled]
        operations = sum(a.repeats for a in active)
        if not self.actions:
            return "No actions yet"
        return f"{len(active)} active  ·  {operations} operations / cycle"

    @Property(int, notify=ControllerSignals.selectedIndexChanged)
    def selectedIndex(self) -> int:
        return self._selected_index

    @selectedIndex.setter
    def selectedIndex(self, value: int) -> None:
        value = int(value)
        if value != self._selected_index:
            self._selected_index = value
            self.selectedIndexChanged.emit()
    @Property(bool, notify=ControllerSignals.actionsChanged)
    def canRun(self) -> bool:
        return any(action.enabled for action in self.actions)
    @Slot(int, result="QVariantMap")
    def actionAt(self, index: int) -> dict[str, Any]:
        if not 0 <= index < len(self.actions):
            return {}
        data = asdict(self.actions[index])
        data["delay"] = data.pop("delay_after")
        return data

    @staticmethod
    def _to_action(data: dict[str, Any]) -> Action:
        def integer(name: str, default: int = 0) -> int:
            value = data.get(name, default)
            return int(value if value not in (None, "") else default)

        def floating(name: str, default: float = 0.0) -> float:
            value = data.get(name, default)
            return float(value if value not in (None, "") else default)

        kind = str(data.get("kind", "key"))
        mouse = kind in {"left_click", "right_click", "double_click", "middle_click", "scroll", "drag"}
        click = kind in {"left_click", "right_click", "double_click", "middle_click"}
        use_current_pointer = bool(data.get("useCurrentPointer", data.get("use_current_pointer", False)))
        return Action(
            kind=kind,
            value=str(data.get("value", "")),
            x=integer("x") if mouse and not (click and use_current_pointer) else None,
            y=integer("y") if mouse and not (click and use_current_pointer) else None,
            x2=integer("x2") if kind == "drag" else None,
            y2=integer("y2") if kind == "drag" else None,
            amount=integer("amount", -3),
            duration=floating("duration", 0.4),
            repeats=integer("repeats", 1),
            delay_after=floating("delay", 0.1),
            enabled=bool(data.get("enabled", True)),
            use_current_pointer=use_current_pointer,
            coordinate_space=str(data.get("coordinateSpace", data.get("coordinate_space", "screen"))).lower(),
            reference_width=integer("referenceWidth", integer("reference_width")),
            reference_height=integer("referenceHeight", integer("reference_height")),
            reference_width2=integer("referenceWidth2", integer("reference_width2")),
            reference_height2=integer("referenceHeight2", integer("reference_height2")),
        )

    def _notify_actions(self) -> None:
        self.actionsChanged.emit()
        self.summaryChanged.emit()

    @Slot("QVariantMap", result=bool)
    def addAction(self, data: dict[str, Any]) -> bool:
        try:
            action = self._to_action(data)
            action.validate(self._reserved_shortcuts())
        except (ValueError, TypeError) as exc:
            self.toast.emit(str(exc), "error")
            return False
        self._model.mutate(lambda: self.actions.append(action))
        self._selected_index = len(self.actions) - 1
        self._clear_undo()
        self._notify_actions()
        self.selectedIndexChanged.emit()
        self._set_dirty(True)
        self.toast.emit("Action added", "success")
        return True

    @Slot(int, "QVariantMap", result=bool)
    def updateAction(self, index: int, data: dict[str, Any]) -> bool:
        if not 0 <= index < len(self.actions):
            return False
        try:
            action = self._to_action(data)
            action.enabled = self.actions[index].enabled
            action.validate(self._reserved_shortcuts())
        except (ValueError, TypeError) as exc:
            self.toast.emit(str(exc), "error")
            return False
        self._model.mutate(lambda: self.actions.__setitem__(index, action))
        self._clear_undo()
        self._notify_actions()
        self._set_dirty(True)
        self.toast.emit("Action updated", "success")
        return True

    @Slot(int)
    def deleteAction(self, index: int) -> None:
        if 0 <= index < len(self.actions):
            self._undo_deleted = (index, copy.deepcopy(self.actions[index]))
            self.undoChanged.emit()
            self._model.mutate(lambda: self.actions.pop(index))
            self._selected_index = min(index, len(self.actions) - 1)
            self._notify_actions()
            self.selectedIndexChanged.emit()
            self._set_dirty(True)
            self.toast.emit("Action deleted · Undo is available", "neutral")

    @Slot()
    def undoDelete(self) -> None:
        if self._undo_deleted is None or self._running:
            return
        index, action = self._undo_deleted
        index = min(max(0, index), len(self.actions))
        self._model.mutate(lambda: self.actions.insert(index, action))
        self._selected_index = index
        self._undo_deleted = None
        self.undoChanged.emit()
        self._notify_actions()
        self.selectedIndexChanged.emit()
        self._set_dirty(True)
        self.toast.emit("Deleted action restored", "success")

    @Slot(int)
    def duplicateAction(self, index: int) -> None:
        if 0 <= index < len(self.actions):
            duplicate = copy.deepcopy(self.actions[index])
            self._model.mutate(lambda: self.actions.insert(index + 1, duplicate))
            self._selected_index = index + 1
            self._clear_undo()
            self._notify_actions()
            self.selectedIndexChanged.emit()
            self._set_dirty(True)

    @Slot(int, int)
    def moveAction(self, index: int, delta: int) -> None:
        self.moveActionTo(index, index + delta)

    @Slot(int, int)
    def moveActionTo(self, source: int, target: int) -> None:
        if self._running or not self._model.move_row(source, target):
            return

        previous_selection = self._selected_index
        if previous_selection == source:
            self._selected_index = target
        elif source < previous_selection <= target:
            self._selected_index -= 1
        elif target <= previous_selection < source:
            self._selected_index += 1

        self._clear_undo()
        self._notify_actions()
        if self._selected_index != previous_selection:
            self.selectedIndexChanged.emit()
        self._set_dirty(True)
        self.toast.emit(f"Action moved to step {target + 1}", "success")

    @Slot(int, bool)
    def setActionEnabled(self, index: int, enabled: bool) -> None:
        if 0 <= index < len(self.actions):
            enabled = bool(enabled)
            if self.actions[index].enabled == enabled:
                return
            self.actions[index].enabled = enabled
            self._clear_undo()
            self._model.notify_row(index, [ActionListModel.EnabledRole])
            self._notify_actions()
            self._set_dirty(True)

    @Slot()
    def clearActions(self) -> None:
        if self._running:
            return
        self._model.mutate(self.actions.clear)
        self._set_current_profile(None)
        self._selected_index = -1
        self._clear_undo()
        self._set_run_settings_pending(False)
        self._notify_actions()
        self.selectedIndexChanged.emit()
        self._set_dirty(False)

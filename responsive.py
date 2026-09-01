from __future__ import annotations

from dataclasses import dataclass


HEADER_HEIGHT = 72
RUN_BAR_HEIGHT = 82


@dataclass(frozen=True)
class LayoutMode:
    name: str
    inspector_width: int
    inspector_overlay: bool
    shortcut_hints_visible: bool


def layout_for_width(width: int) -> LayoutMode:
    """Return deterministic responsive geometry for the Qt interface.

    Navigation is a full-width tab header rather than a side rail, so only the
    inspector and the run bar's shortcut hints vary with the window width.
    """
    if width >= 1240:
        return LayoutMode("wide", 368, False, True)
    if width >= 1024:
        return LayoutMode("medium", 340, False, True)
    return LayoutMode("compact", 360, True, width >= 1000)

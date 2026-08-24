from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LayoutMode:
    name: str
    navigation_width: int
    inspector_width: int
    inspector_overlay: bool


def layout_for_width(width: int) -> LayoutMode:
    """Return deterministic responsive geometry for the Qt interface."""
    if width >= 1240:
        return LayoutMode("wide", 216, 368, False)
    if width >= 1024:
        return LayoutMode("medium", 76, 340, False)
    return LayoutMode("compact", 76, 360, True)

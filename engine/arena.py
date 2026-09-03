"""Logical canvas and arena geometry.

All simulation coordinates are expressed in logical canvas pixels (9:16),
with the origin in the top-left corner and y growing downwards.
"""

from __future__ import annotations

from dataclasses import dataclass

# Logical YouTube Shorts canvas.
CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 1920

# Margins reserved around the playable area for future Shorts overlays.
SIDE_MARGIN = 60
TOP_MARGIN = 380
BOTTOM_MARGIN = 380

# Static wall thickness; walls are placed so their inner surface is exactly
# on the arena bounds.
WALL_THICKNESS = 8.0


@dataclass(frozen=True)
class Arena:
    """Axis-aligned rectangular playable area inside the logical canvas."""

    left: float
    top: float
    right: float
    bottom: float

    @classmethod
    def default(cls) -> "Arena":
        return cls(
            left=SIDE_MARGIN,
            top=TOP_MARGIN,
            right=CANVAS_WIDTH - SIDE_MARGIN,
            bottom=CANVAS_HEIGHT - BOTTOM_MARGIN,
        )

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.bottom - self.top

    def contains_circle(self, x: float, y: float, radius: float) -> bool:
        return (
            self.left + radius <= x <= self.right - radius
            and self.top + radius <= y <= self.bottom - radius
        )

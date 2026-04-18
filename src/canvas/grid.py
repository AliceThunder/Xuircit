"""Grid rendering and snap-to-grid helpers."""
from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen

GRID_SIZE = 20  # pixels (must be an integer multiple used for snapping)
MAJOR_FACTOR = 5  # every 5th line is a major (darker) grid line


def snap_to_grid(x: float, y: float) -> tuple[float, float]:
    """Snap coordinates to the nearest grid point."""
    return (
        round(x / GRID_SIZE) * GRID_SIZE,
        round(y / GRID_SIZE) * GRID_SIZE,
    )


def draw_grid(painter: QPainter, rect: QRectF) -> None:
    """Draw a minor/major line grid on the scene background."""
    major_size = GRID_SIZE * MAJOR_FACTOR

    # Compute grid extent with one cell of padding on each side
    left = math.floor(rect.left() / GRID_SIZE) * GRID_SIZE - GRID_SIZE
    top = math.floor(rect.top() / GRID_SIZE) * GRID_SIZE - GRID_SIZE
    right = math.ceil(rect.right() / GRID_SIZE) * GRID_SIZE + GRID_SIZE
    bottom = math.ceil(rect.bottom() / GRID_SIZE) * GRID_SIZE + GRID_SIZE

    # ── minor lines ───────────────────────────────────────────────────
    minor_pen = QPen(QColor("#e4e4e4"), 0)
    minor_pen.setCosmetic(True)
    painter.setPen(minor_pen)

    x = left
    while x <= right:
        if x % major_size != 0:
            painter.drawLine(QPointF(x, top), QPointF(x, bottom))
        x += GRID_SIZE

    y = top
    while y <= bottom:
        if y % major_size != 0:
            painter.drawLine(QPointF(left, y), QPointF(right, y))
        y += GRID_SIZE

    # ── major lines ───────────────────────────────────────────────────
    major_pen = QPen(QColor("#c8c8c8"), 0)
    major_pen.setCosmetic(True)
    painter.setPen(major_pen)

    x = math.floor(rect.left() / major_size) * major_size
    while x <= right:
        painter.drawLine(QPointF(x, top), QPointF(x, bottom))
        x += major_size

    y = math.floor(rect.top() / major_size) * major_size
    while y <= bottom:
        painter.drawLine(QPointF(left, y), QPointF(right, y))
        y += major_size

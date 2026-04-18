"""Grid rendering and snap-to-grid helpers."""
from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen

GRID_SIZE = 20  # pixels


def snap_to_grid(x: float, y: float) -> tuple[float, float]:
    """Snap coordinates to the nearest grid point."""
    return (
        round(x / GRID_SIZE) * GRID_SIZE,
        round(y / GRID_SIZE) * GRID_SIZE,
    )


def draw_grid(painter: QPainter, rect: QRectF) -> None:
    """Draw a dot-grid on the scene background."""
    pen = QPen(QColor("#cccccc"), 1)
    pen.setCosmetic(True)
    painter.setPen(pen)

    left = int(rect.left()) - (int(rect.left()) % GRID_SIZE)
    top = int(rect.top()) - (int(rect.top()) % GRID_SIZE)

    x = left
    while x < rect.right():
        y = top
        while y < rect.bottom():
            painter.drawPoint(x, y)
            y += GRID_SIZE
        x += GRID_SIZE

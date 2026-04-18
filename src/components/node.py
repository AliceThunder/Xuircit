"""Node items: Junction, Ground, NetLabel."""
from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsTextItem,
    QStyleOptionGraphicsItem,
    QWidget,
)

from .base import ComponentItem, _std_pen


class JunctionItem(QGraphicsEllipseItem):
    """Filled junction dot for T/cross wire connections."""

    RADIUS = 4.0

    def __init__(self, pos: QPointF) -> None:
        r = self.RADIUS
        super().__init__(-r, -r, 2 * r, 2 * r)
        self.setPos(pos)
        self.setPen(QPen(QColor("#1a1a8c"), 1))
        self.setBrush(QBrush(QColor("#1a1a8c")))
        self.setZValue(3)
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable)


class GroundItem(ComponentItem):
    """Ground symbol — horizontal lines of decreasing width.
    Pin at (0, -20) (on 20 px grid)."""

    _WIDTH = 40.0
    _HEIGHT = 40.0
    _ref_label_offset = (28.0, -10.0)
    _val_label_offset = (28.0, 6.0)

    def __init__(self, ref: str = "GND1", value: str = "",
                 params: dict[str, Any] | None = None,
                 comp_id: str | None = None) -> None:
        super().__init__("GND", ref, value, params, comp_id)

    def _pin_definitions(self) -> dict[str, QPointF]:
        return {"p": QPointF(0, -20)}

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(_std_pen())
        painter.setBrush(Qt.BrushStyle.NoBrush)
        # Lead down (extended to -20)
        painter.drawLine(QPointF(0, -20), QPointF(0, 0))
        # Three horizontal bars, decreasing width
        painter.drawLine(QPointF(-16, 0), QPointF(16, 0))
        painter.drawLine(QPointF(-10, 6), QPointF(10, 6))
        painter.drawLine(QPointF(-4, 12), QPointF(4, 12))


class NetLabelItem(QGraphicsTextItem):
    """Net name label that attaches to a wire or pin."""

    def __init__(self, text: str = "NET", pos: QPointF | None = None) -> None:
        super().__init__(text)
        self.setFont(QFont("monospace", 9))
        self.setDefaultTextColor(QColor("#006600"))
        self.setFlag(self.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable)
        if pos is not None:
            self.setPos(pos)

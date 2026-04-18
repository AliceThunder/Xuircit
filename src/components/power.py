"""Power electronics component symbols: Switch, SCR, TRIAC."""
from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QStyleOptionGraphicsItem, QWidget

from .base import ComponentItem, _std_pen


class IdealSwitchItem(ComponentItem):
    """Ideal switch symbol."""

    _WIDTH = 50.0
    _HEIGHT = 30.0

    def __init__(self, ref: str = "SW1", value: str = "",
                 params: dict[str, Any] | None = None,
                 comp_id: str | None = None) -> None:
        super().__init__("SW", ref, value, params, comp_id)

    def _pin_definitions(self) -> dict[str, QPointF]:
        return {"p": QPointF(-25, 0), "n": QPointF(25, 0)}

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(_std_pen())
        painter.setBrush(Qt.BrushStyle.NoBrush)
        # Left lead + contact dot
        painter.drawLine(QPointF(-25, 0), QPointF(-12, 0))
        painter.drawEllipse(QPointF(-12, 0), 2, 2)
        # Moving arm (open)
        painter.drawLine(QPointF(-12, 0), QPointF(10, -10))
        # Right contact dot + lead
        painter.drawEllipse(QPointF(12, 0), 2, 2)
        painter.drawLine(QPointF(12, 0), QPointF(25, 0))


class SCRItem(ComponentItem):
    """SCR / Thyristor symbol."""

    _WIDTH = 60.0
    _HEIGHT = 50.0

    def __init__(self, ref: str = "SCR1", value: str = "TYN612",
                 params: dict[str, Any] | None = None,
                 comp_id: str | None = None) -> None:
        super().__init__("SCR", ref, value, params, comp_id)

    def _pin_definitions(self) -> dict[str, QPointF]:
        return {
            "anode": QPointF(-30, 0),
            "cathode": QPointF(30, 0),
            "gate": QPointF(15, 20),
        }

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(_std_pen())
        painter.setBrush(QBrush(QColor("#333")))
        # Diode triangle
        painter.drawLine(QPointF(-30, 0), QPointF(-10, 0))
        painter.drawLine(QPointF(10, 0), QPointF(30, 0))
        tri = QPainterPath()
        tri.moveTo(-10, -10)
        tri.lineTo(-10, 10)
        tri.lineTo(10, 0)
        tri.closeSubpath()
        painter.drawPath(tri)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(QPointF(10, -10), QPointF(10, 10))
        # Gate
        painter.drawLine(QPointF(10, 10), QPointF(15, 20))


class TRIACItem(ComponentItem):
    """TRIAC symbol — two back-to-back thyristors."""

    _WIDTH = 60.0
    _HEIGHT = 60.0

    def __init__(self, ref: str = "TRIAC1", value: str = "BTA12",
                 params: dict[str, Any] | None = None,
                 comp_id: str | None = None) -> None:
        super().__init__("TRIAC", ref, value, params, comp_id)

    def _pin_definitions(self) -> dict[str, QPointF]:
        return {
            "MT1": QPointF(-30, 0),
            "MT2": QPointF(30, 0),
            "gate": QPointF(0, 22),
        }

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(_std_pen())
        painter.setBrush(QBrush(QColor("#333")))
        painter.drawLine(QPointF(-30, 0), QPointF(-12, 0))
        painter.drawLine(QPointF(12, 0), QPointF(30, 0))
        # Upper triangle
        t1 = QPainterPath()
        t1.moveTo(-12, -12)
        t1.lineTo(-12, 12)
        t1.lineTo(12, 0)
        t1.closeSubpath()
        painter.drawPath(t1)
        # Lower triangle (reversed)
        t2 = QPainterPath()
        t2.moveTo(12, -12)
        t2.lineTo(12, 12)
        t2.lineTo(-12, 0)
        t2.closeSubpath()
        painter.drawPath(t2)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(QPointF(-12, -12), QPointF(12, -12))
        painter.drawLine(QPointF(-12, 12), QPointF(12, 12))
        # Gate
        painter.drawLine(QPointF(0, 12), QPointF(0, 22))

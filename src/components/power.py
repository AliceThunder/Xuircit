"""Power electronics component symbols: Switch, SCR, TRIAC."""
from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QStyleOptionGraphicsItem, QWidget

from .base import ComponentItem, _std_pen


class IdealSwitchItem(ComponentItem):
    """Ideal switch symbol.  Pins at ±40 (on 20 px grid)."""

    _WIDTH = 80.0
    _HEIGHT = 30.0
    _ref_label_offset = (0.0, -24.0)
    _val_label_offset = (0.0, 20.0)

    def __init__(self, ref: str = "SW1", value: str = "",
                 params: dict[str, Any] | None = None,
                 comp_id: str | None = None) -> None:
        super().__init__("SW", ref, value, params, comp_id)

    def _pin_definitions(self) -> dict[str, QPointF]:
        return {"p": QPointF(-40, 0), "n": QPointF(40, 0)}

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(_std_pen(self._color))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        # Left lead + contact dot
        painter.drawLine(QPointF(-40, 0), QPointF(-12, 0))
        painter.drawEllipse(QPointF(-12, 0), 2, 2)
        # Moving arm (open)
        painter.drawLine(QPointF(-12, 0), QPointF(10, -10))
        # Right contact dot + lead
        painter.drawEllipse(QPointF(12, 0), 2, 2)
        painter.drawLine(QPointF(12, 0), QPointF(40, 0))


class SCRItem(ComponentItem):
    """SCR / Thyristor symbol.
    Pins: anode at (-40, 0), cathode at (40, 0), gate at (20, 20)."""

    _WIDTH = 80.0
    _HEIGHT = 50.0
    _ref_label_offset = (0.0, -34.0)
    _val_label_offset = (0.0, 34.0)

    def __init__(self, ref: str = "SCR1", value: str = "TYN612",
                 params: dict[str, Any] | None = None,
                 comp_id: str | None = None) -> None:
        super().__init__("SCR", ref, value, params, comp_id)

    def _pin_definitions(self) -> dict[str, QPointF]:
        return {
            "anode": QPointF(-40, 0),
            "cathode": QPointF(40, 0),
            "gate": QPointF(20, 20),
        }

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(_std_pen(self._color))
        painter.setBrush(QBrush(QColor("#333")))
        # Diode triangle
        painter.drawLine(QPointF(-40, 0), QPointF(-10, 0))
        painter.drawLine(QPointF(10, 0), QPointF(40, 0))
        tri = QPainterPath()
        tri.moveTo(-10, -10)
        tri.lineTo(-10, 10)
        tri.lineTo(10, 0)
        tri.closeSubpath()
        painter.drawPath(tri)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(QPointF(10, -10), QPointF(10, 10))
        # Gate (connect to pin at (20, 20))
        painter.drawLine(QPointF(10, 10), QPointF(20, 20))


class TRIACItem(ComponentItem):
    """TRIAC symbol — two back-to-back thyristors.
    Pins: MT1 at (-40, 0), MT2 at (40, 0), gate at (0, 20)."""

    _WIDTH = 80.0
    _HEIGHT = 60.0
    _ref_label_offset = (0.0, -40.0)
    _val_label_offset = (0.0, 40.0)

    def __init__(self, ref: str = "TRIAC1", value: str = "BTA12",
                 params: dict[str, Any] | None = None,
                 comp_id: str | None = None) -> None:
        super().__init__("TRIAC", ref, value, params, comp_id)

    def _pin_definitions(self) -> dict[str, QPointF]:
        return {
            "MT1": QPointF(-40, 0),
            "MT2": QPointF(40, 0),
            "gate": QPointF(0, 20),
        }

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(_std_pen(self._color))
        painter.setBrush(QBrush(QColor("#333")))
        painter.drawLine(QPointF(-40, 0), QPointF(-12, 0))
        painter.drawLine(QPointF(12, 0), QPointF(40, 0))
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
        # Gate (connect to pin at (0, 20))
        painter.drawLine(QPointF(0, 12), QPointF(0, 20))

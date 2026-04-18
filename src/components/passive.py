"""Passive component symbols: Resistor, Capacitor, Inductor, Transformer."""
from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QStyleOptionGraphicsItem, QWidget

from .base import ComponentItem, _std_pen


class ResistorItem(ComponentItem):
    """US-style zigzag resistor symbol.  Pins at ±40 (on 20 px grid)."""

    _WIDTH = 80.0
    _HEIGHT = 20.0
    _ref_label_offset = (0.0, -18.0)
    _val_label_offset = (0.0, 14.0)

    def __init__(self, ref: str = "R1", value: str = "1k",
                 params: dict[str, Any] | None = None,
                 comp_id: str | None = None) -> None:
        super().__init__("R", ref, value, params, comp_id)

    def _pin_definitions(self) -> dict[str, QPointF]:
        return {"p": QPointF(-40, 0), "n": QPointF(40, 0)}

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(_std_pen(self._color))
        painter.setBrush(QBrush(QColor("white")))
        path = QPainterPath()
        path.moveTo(-40, 0)
        path.lineTo(-12, 0)
        zx = [-12, -9, -6, -3, 0, 3, 6, 9, 12]
        zy = [0, -8, 8, -8, 8, -8, 8, -8, 0]
        for x, y in zip(zx, zy):
            path.lineTo(x, y)
        path.lineTo(40, 0)
        painter.drawPath(path)


class CapacitorItem(ComponentItem):
    """Capacitor symbol — two parallel plates."""

    _WIDTH = 30.0
    _HEIGHT = 40.0
    _ref_label_offset = (-28.0, -8.0)
    _val_label_offset = (24.0, -8.0)

    def __init__(self, ref: str = "C1", value: str = "100n",
                 params: dict[str, Any] | None = None,
                 comp_id: str | None = None) -> None:
        super().__init__("C", ref, value, params, comp_id)

    def _pin_definitions(self) -> dict[str, QPointF]:
        return {"+": QPointF(0, -20), "-": QPointF(0, 20)}

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(_std_pen(self._color))
        painter.setBrush(QBrush(QColor("white")))
        painter.drawLine(QPointF(0, -20), QPointF(0, -5))
        painter.drawLine(QPointF(-13, -5), QPointF(13, -5))
        painter.drawLine(QPointF(-13, 5), QPointF(13, 5))
        painter.drawLine(QPointF(0, 5), QPointF(0, 20))
        from PyQt6.QtGui import QFont
        painter.setFont(QFont("sans", 7))
        painter.setPen(QPen(QColor("#555")))
        painter.drawText(-20, -2, "+")


class InductorItem(ComponentItem):
    """Inductor — series of arcs.  Pins at ±40 (on 20 px grid)."""

    _WIDTH = 80.0
    _HEIGHT = 24.0
    _ref_label_offset = (0.0, -18.0)
    _val_label_offset = (0.0, 16.0)

    def __init__(self, ref: str = "L1", value: str = "10u",
                 params: dict[str, Any] | None = None,
                 comp_id: str | None = None) -> None:
        super().__init__("L", ref, value, params, comp_id)

    def _pin_definitions(self) -> dict[str, QPointF]:
        return {"p": QPointF(-40, 0), "n": QPointF(40, 0)}

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(_std_pen(self._color))
        painter.setBrush(QBrush(QColor("white")))
        painter.drawLine(QPointF(-40, 0), QPointF(-18, 0))
        painter.drawLine(QPointF(18, 0), QPointF(40, 0))
        path = QPainterPath()
        path.moveTo(-18, 0)
        for cx in [-12.0, -4.0, 4.0, 12.0]:
            path.arcTo(QRectF(cx - 6, -8, 12, 12), 180, -180)
        painter.drawPath(path)


class TransformerItem(ComponentItem):
    """Transformer — two facing inductor coils with coupling lines."""

    _WIDTH = 80.0
    _HEIGHT = 80.0
    _ref_label_offset = (0.0, -50.0)
    _val_label_offset = (0.0, 50.0)

    def __init__(self, ref: str = "T1", value: str = "",
                 params: dict[str, Any] | None = None,
                 comp_id: str | None = None) -> None:
        super().__init__("T", ref, value, params, comp_id)

    def _pin_definitions(self) -> dict[str, QPointF]:
        return {
            "p1": QPointF(-40, -20),
            "p2": QPointF(-40, 20),
            "s1": QPointF(40, -20),
            "s2": QPointF(40, 20),
        }

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(_std_pen(self._color))

        def _coil(cx: float, direction: int) -> QPainterPath:
            path = QPainterPath()
            path.moveTo(cx, -30)
            ys = [-30.0, -20.0, -10.0, 0.0, 10.0]
            for i in range(len(ys) - 1):
                my = (ys[i] + ys[i + 1]) / 2
                path.arcTo(QRectF(cx - 6, my - 6, 12, 12),
                           90, -180 * direction)
            path.lineTo(cx, 30)
            return path

        painter.setBrush(QBrush(QColor("white")))
        painter.drawPath(_coil(-15, 1))
        painter.drawPath(_coil(15, -1))

        painter.setPen(QPen(QColor("#111"), 1.5))
        painter.drawLine(QPointF(-40, -20), QPointF(-15, -20))
        painter.drawLine(QPointF(-40, 20), QPointF(-15, 20))
        painter.drawLine(QPointF(15, -20), QPointF(40, -20))
        painter.drawLine(QPointF(15, 20), QPointF(40, 20))
        painter.drawLine(QPointF(-4, -28), QPointF(-4, 28))
        painter.drawLine(QPointF(4, -28), QPointF(4, 28))

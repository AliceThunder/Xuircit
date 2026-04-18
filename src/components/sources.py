"""Source component symbols: Voltage, Current, and dependent sources."""
from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QFont
from PyQt6.QtWidgets import QStyleOptionGraphicsItem, QWidget

from .base import ComponentItem, _std_pen


class VoltageSourceItem(ComponentItem):
    """Independent voltage source — circle with + / - labels."""

    _WIDTH = 40.0
    _HEIGHT = 40.0

    def __init__(self, ref: str = "V1", value: str = "5",
                 params: dict[str, Any] | None = None,
                 comp_id: str | None = None) -> None:
        super().__init__("V", ref, value, params, comp_id)

    def _pin_definitions(self) -> dict[str, QPointF]:
        return {"+": QPointF(0, -20), "-": QPointF(0, 20)}

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(_std_pen())
        painter.setBrush(QBrush(QColor("white")))
        painter.drawEllipse(QPointF(0, 0), 16, 16)
        painter.drawLine(QPointF(0, -20), QPointF(0, -16))
        painter.drawLine(QPointF(0, 16), QPointF(0, 20))
        painter.setFont(QFont("sans", 8, QFont.Weight.Bold))
        painter.setPen(QPen(QColor("#111")))
        painter.drawText(-4, -4, "+")
        painter.drawText(-4, 10, "−")


class CurrentSourceItem(ComponentItem):
    """Independent current source — circle with arrow."""

    _WIDTH = 40.0
    _HEIGHT = 40.0

    def __init__(self, ref: str = "I1", value: str = "1m",
                 params: dict[str, Any] | None = None,
                 comp_id: str | None = None) -> None:
        super().__init__("I", ref, value, params, comp_id)

    def _pin_definitions(self) -> dict[str, QPointF]:
        return {"+": QPointF(0, -20), "-": QPointF(0, 20)}

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(_std_pen())
        painter.setBrush(QBrush(QColor("white")))
        painter.drawEllipse(QPointF(0, 0), 16, 16)
        painter.drawLine(QPointF(0, -20), QPointF(0, -16))
        painter.drawLine(QPointF(0, 16), QPointF(0, 20))
        # Arrow pointing up inside circle
        arrow = QPainterPath()
        arrow.moveTo(0, 10)
        arrow.lineTo(0, -8)
        arrow.moveTo(-4, -4)
        arrow.lineTo(0, -10)
        arrow.lineTo(4, -4)
        painter.setPen(_std_pen())
        painter.drawPath(arrow)


def _diamond_source(painter: QPainter, w: float = 28, h: float = 20) -> None:
    """Draw a diamond (rhombus) shape for dependent sources."""
    path = QPainterPath()
    path.moveTo(0, -h)
    path.lineTo(w, 0)
    path.lineTo(0, h)
    path.lineTo(-w, 0)
    path.closeSubpath()
    painter.setPen(_std_pen())
    painter.setBrush(QBrush(QColor("white")))
    painter.drawPath(path)


class VCVSItem(ComponentItem):
    """Voltage-controlled voltage source (E element)."""

    _WIDTH = 60.0
    _HEIGHT = 60.0

    def __init__(self, ref: str = "E1", value: str = "1",
                 params: dict[str, Any] | None = None,
                 comp_id: str | None = None) -> None:
        super().__init__("E", ref, value, params, comp_id)

    def _pin_definitions(self) -> dict[str, QPointF]:
        return {
            "+": QPointF(0, -30), "-": QPointF(0, 30),
            "nc+": QPointF(-30, 0), "nc-": QPointF(30, 0),
        }

    def _draw_symbol(self, painter: QPainter) -> None:
        _diamond_source(painter, 26, 26)
        painter.drawLine(QPointF(0, -30), QPointF(0, -26))
        painter.drawLine(QPointF(0, 26), QPointF(0, 30))
        painter.drawLine(QPointF(-30, 0), QPointF(-26, 0))
        painter.drawLine(QPointF(26, 0), QPointF(30, 0))
        painter.setFont(QFont("sans", 7))
        painter.setPen(QPen(QColor("#333")))
        painter.drawText(-5, -8, "+")
        painter.drawText(-5, 14, "−")
        painter.drawText(-22, 4, "V")


class CCCSItem(ComponentItem):
    """Current-controlled current source (F element)."""

    _WIDTH = 60.0
    _HEIGHT = 60.0

    def __init__(self, ref: str = "F1", value: str = "1",
                 params: dict[str, Any] | None = None,
                 comp_id: str | None = None) -> None:
        super().__init__("F", ref, value, params, comp_id)

    def _pin_definitions(self) -> dict[str, QPointF]:
        return {
            "+": QPointF(0, -30), "-": QPointF(0, 30),
            "nc+": QPointF(-30, 0), "nc-": QPointF(30, 0),
        }

    def _draw_symbol(self, painter: QPainter) -> None:
        _diamond_source(painter, 26, 26)
        painter.drawLine(QPointF(0, -30), QPointF(0, -26))
        painter.drawLine(QPointF(0, 26), QPointF(0, 30))
        painter.drawLine(QPointF(-30, 0), QPointF(-26, 0))
        painter.drawLine(QPointF(26, 0), QPointF(30, 0))
        painter.setFont(QFont("sans", 7))
        painter.setPen(QPen(QColor("#333")))
        painter.drawText(-5, -8, "↑")
        painter.drawText(-22, 4, "I")


class VCCSItem(ComponentItem):
    """Voltage-controlled current source (G element)."""

    _WIDTH = 60.0
    _HEIGHT = 60.0

    def __init__(self, ref: str = "G1", value: str = "1",
                 params: dict[str, Any] | None = None,
                 comp_id: str | None = None) -> None:
        super().__init__("G", ref, value, params, comp_id)

    def _pin_definitions(self) -> dict[str, QPointF]:
        return {
            "+": QPointF(0, -30), "-": QPointF(0, 30),
            "nc+": QPointF(-30, 0), "nc-": QPointF(30, 0),
        }

    def _draw_symbol(self, painter: QPainter) -> None:
        _diamond_source(painter, 26, 26)
        painter.drawLine(QPointF(0, -30), QPointF(0, -26))
        painter.drawLine(QPointF(0, 26), QPointF(0, 30))
        painter.drawLine(QPointF(-30, 0), QPointF(-26, 0))
        painter.drawLine(QPointF(26, 0), QPointF(30, 0))
        painter.setFont(QFont("sans", 7))
        painter.setPen(QPen(QColor("#333")))
        painter.drawText(-5, -8, "↑")
        painter.drawText(-22, 4, "G")


class CCVSItem(ComponentItem):
    """Current-controlled voltage source (H element)."""

    _WIDTH = 60.0
    _HEIGHT = 60.0

    def __init__(self, ref: str = "H1", value: str = "1",
                 params: dict[str, Any] | None = None,
                 comp_id: str | None = None) -> None:
        super().__init__("H", ref, value, params, comp_id)

    def _pin_definitions(self) -> dict[str, QPointF]:
        return {
            "+": QPointF(0, -30), "-": QPointF(0, 30),
            "nc+": QPointF(-30, 0), "nc-": QPointF(30, 0),
        }

    def _draw_symbol(self, painter: QPainter) -> None:
        _diamond_source(painter, 26, 26)
        painter.drawLine(QPointF(0, -30), QPointF(0, -26))
        painter.drawLine(QPointF(0, 26), QPointF(0, 30))
        painter.drawLine(QPointF(-30, 0), QPointF(-26, 0))
        painter.drawLine(QPointF(26, 0), QPointF(30, 0))
        painter.setFont(QFont("sans", 7))
        painter.setPen(QPen(QColor("#333")))
        painter.drawText(-5, -8, "+")
        painter.drawText(-5, 14, "−")
        painter.drawText(-22, 4, "H")

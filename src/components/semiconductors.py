"""Semiconductor component symbols: Diode, BJT, MOSFET, IGBT."""
from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QStyleOptionGraphicsItem, QWidget

from .base import ComponentItem, _std_pen


class DiodeItem(ComponentItem):
    """PN diode — triangle + bar."""

    _WIDTH = 50.0
    _HEIGHT = 30.0

    def __init__(self, ref: str = "D1", value: str = "1N4148",
                 params: dict[str, Any] | None = None,
                 comp_id: str | None = None) -> None:
        super().__init__("D", ref, value, params, comp_id)

    def _pin_definitions(self) -> dict[str, QPointF]:
        return {"anode": QPointF(-25, 0), "cathode": QPointF(25, 0)}

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(_std_pen())
        painter.setBrush(QBrush(QColor("#333333")))
        # Lead lines
        painter.drawLine(QPointF(-25, 0), QPointF(-10, 0))
        painter.drawLine(QPointF(10, 0), QPointF(25, 0))
        # Triangle (anode → cathode direction)
        tri = QPainterPath()
        tri.moveTo(-10, -10)
        tri.lineTo(-10, 10)
        tri.lineTo(10, 0)
        tri.closeSubpath()
        painter.drawPath(tri)
        # Cathode bar
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(QPointF(10, -10), QPointF(10, 10))


class ZenerDiodeItem(ComponentItem):
    """Zener diode — triangle + bent bar."""

    _WIDTH = 50.0
    _HEIGHT = 30.0

    def __init__(self, ref: str = "D1", value: str = "BZX55C5V1",
                 params: dict[str, Any] | None = None,
                 comp_id: str | None = None) -> None:
        super().__init__("Z", ref, value, params, comp_id)

    def _pin_definitions(self) -> dict[str, QPointF]:
        return {"anode": QPointF(-25, 0), "cathode": QPointF(25, 0)}

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(_std_pen())
        painter.setBrush(QBrush(QColor("#333333")))
        painter.drawLine(QPointF(-25, 0), QPointF(-10, 0))
        painter.drawLine(QPointF(10, 0), QPointF(25, 0))
        tri = QPainterPath()
        tri.moveTo(-10, -10)
        tri.lineTo(-10, 10)
        tri.lineTo(10, 0)
        tri.closeSubpath()
        painter.drawPath(tri)
        # Zener bent bar
        painter.setBrush(Qt.BrushStyle.NoBrush)
        zbar = QPainterPath()
        zbar.moveTo(10, -10)
        zbar.lineTo(10, 10)
        zbar.moveTo(10, -10)
        zbar.lineTo(14, -14)
        zbar.moveTo(10, 10)
        zbar.lineTo(6, 14)
        painter.drawPath(zbar)


class _BJTItem(ComponentItem):
    """Base class for NPN and PNP BJT."""

    _WIDTH = 50.0
    _HEIGHT = 60.0
    _IS_NPN: bool = True

    def _pin_definitions(self) -> dict[str, QPointF]:
        return {
            "base": QPointF(-25, 0),
            "collector": QPointF(25, -20),
            "emitter": QPointF(25, 20),
        }

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(_std_pen())
        painter.setBrush(Qt.BrushStyle.NoBrush)
        # Vertical base line
        painter.drawLine(QPointF(-10, -20), QPointF(-10, 20))
        # Base lead
        painter.drawLine(QPointF(-25, 0), QPointF(-10, 0))
        if self._IS_NPN:
            # Collector line
            painter.drawLine(QPointF(-10, -12), QPointF(25, -20))
            # Emitter with arrow (pointing out)
            painter.drawLine(QPointF(-10, 12), QPointF(25, 20))
            # Arrow on emitter
            arr = QPainterPath()
            arr.moveTo(25, 20)
            arr.lineTo(18, 16)
            arr.lineTo(20, 23)
            arr.closeSubpath()
            painter.setBrush(QBrush(QColor("#111")))
            painter.drawPath(arr)
        else:
            # PNP
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawLine(QPointF(-10, -12), QPointF(25, -20))
            painter.drawLine(QPointF(-10, 12), QPointF(25, 20))
            # Arrow on emitter pointing in
            arr = QPainterPath()
            arr.moveTo(-10, 12)
            arr.lineTo(-4, 8)
            arr.lineTo(-3, 16)
            arr.closeSubpath()
            painter.setBrush(QBrush(QColor("#111")))
            painter.drawPath(arr)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(_std_pen())
        painter.drawLine(QPointF(25, -20), QPointF(25, -25))
        painter.drawLine(QPointF(25, 20), QPointF(25, 25))


class NPNItem(_BJTItem):
    _IS_NPN = True

    def __init__(self, ref: str = "Q1", value: str = "2N2222",
                 params: dict[str, Any] | None = None,
                 comp_id: str | None = None) -> None:
        super().__init__("Q_NPN", ref, value, params, comp_id)


class PNPItem(_BJTItem):
    _IS_NPN = False

    def __init__(self, ref: str = "Q1", value: str = "2N2907",
                 params: dict[str, Any] | None = None,
                 comp_id: str | None = None) -> None:
        super().__init__("Q_PNP", ref, value, params, comp_id)


class _MOSFETItem(ComponentItem):
    """Base class for NMOS and PMOS."""

    _WIDTH = 60.0
    _HEIGHT = 70.0
    _IS_N: bool = True

    def _pin_definitions(self) -> dict[str, QPointF]:
        return {
            "gate": QPointF(-30, 0),
            "drain": QPointF(30, -25),
            "source": QPointF(30, 25),
            "body": QPointF(0, 0),
        }

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(_std_pen())
        painter.setBrush(Qt.BrushStyle.NoBrush)
        # Gate lead
        painter.drawLine(QPointF(-30, 0), QPointF(-12, 0))
        # Gate plate
        painter.drawLine(QPointF(-12, -18), QPointF(-12, 18))
        # Channel plate (with gap)
        painter.drawLine(QPointF(-8, -18), QPointF(-8, -6))
        painter.drawLine(QPointF(-8, -6), QPointF(-8, 6))
        painter.drawLine(QPointF(-8, 6), QPointF(-8, 18))
        # Source / drain connections
        painter.drawLine(QPointF(-8, -18), QPointF(8, -18))
        painter.drawLine(QPointF(-8, 18), QPointF(8, 18))
        painter.drawLine(QPointF(8, -18), QPointF(30, -25))
        painter.drawLine(QPointF(8, 18), QPointF(30, 25))
        painter.drawLine(QPointF(8, -18), QPointF(8, 18))
        # Arrow on body (N: pointing in; P: pointing out)
        arr = QPainterPath()
        if self._IS_N:
            arr.moveTo(-8, 0)
            arr.lineTo(-2, -4)
            arr.lineTo(-2, 4)
        else:
            arr.moveTo(-2, 0)
            arr.lineTo(-8, -4)
            arr.lineTo(-8, 4)
        arr.closeSubpath()
        painter.setBrush(QBrush(QColor("#111")))
        painter.drawPath(arr)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(_std_pen())
        painter.drawLine(QPointF(30, -25), QPointF(30, -30))
        painter.drawLine(QPointF(30, 25), QPointF(30, 30))


class NMOSItem(_MOSFETItem):
    _IS_N = True

    def __init__(self, ref: str = "M1", value: str = "IRF540",
                 params: dict[str, Any] | None = None,
                 comp_id: str | None = None) -> None:
        super().__init__("M_NMOS", ref, value, params, comp_id)


class PMOSItem(_MOSFETItem):
    _IS_N = False

    def __init__(self, ref: str = "M1", value: str = "IRF9540",
                 params: dict[str, Any] | None = None,
                 comp_id: str | None = None) -> None:
        super().__init__("M_PMOS", ref, value, params, comp_id)


class IGBTItem(ComponentItem):
    """IGBT symbol."""

    _WIDTH = 60.0
    _HEIGHT = 70.0

    def __init__(self, ref: str = "Q1", value: str = "IRGB4062",
                 params: dict[str, Any] | None = None,
                 comp_id: str | None = None) -> None:
        super().__init__("IGBT", ref, value, params, comp_id)

    def _pin_definitions(self) -> dict[str, QPointF]:
        return {
            "gate": QPointF(-30, 0),
            "collector": QPointF(30, -25),
            "emitter": QPointF(30, 25),
        }

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(_std_pen())
        painter.setBrush(Qt.BrushStyle.NoBrush)
        # Reuse MOSFET-like body
        painter.drawLine(QPointF(-30, 0), QPointF(-12, 0))
        painter.drawLine(QPointF(-12, -18), QPointF(-12, 18))
        painter.drawLine(QPointF(-8, -18), QPointF(-8, -6))
        painter.drawLine(QPointF(-8, -6), QPointF(-8, 6))
        painter.drawLine(QPointF(-8, 6), QPointF(-8, 18))
        painter.drawLine(QPointF(-8, -18), QPointF(8, -18))
        painter.drawLine(QPointF(-8, 18), QPointF(8, 18))
        painter.drawLine(QPointF(8, -18), QPointF(30, -25))
        painter.drawLine(QPointF(8, 18), QPointF(30, 25))
        painter.drawLine(QPointF(8, -18), QPointF(8, 18))
        # Arrow (NPN-like) on emitter
        arr = QPainterPath()
        arr.moveTo(30, 25)
        arr.lineTo(23, 21)
        arr.lineTo(25, 28)
        arr.closeSubpath()
        painter.setBrush(QBrush(QColor("#111")))
        painter.drawPath(arr)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(_std_pen())
        painter.drawLine(QPointF(30, -25), QPointF(30, -30))
        painter.drawLine(QPointF(30, 25), QPointF(30, 30))

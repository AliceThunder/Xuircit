"""Wire and junction wiring items."""
from __future__ import annotations

import uuid
from typing import Any

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QGraphicsPathItem,
    QGraphicsSceneContextMenuEvent,
    QMenu,
    QStyleOptionGraphicsItem,
    QWidget,
)


class WireItem(QGraphicsPathItem):
    """A wire between two points, auto-routed at 90° angles."""

    def __init__(self, start: QPointF, end: QPointF,
                 wire_id: str | None = None) -> None:
        super().__init__()
        self.wire_id: str = wire_id or str(uuid.uuid4())
        self.start_pos = start
        self.end_pos = end
        self.start_pin: tuple[str, str] | None = None
        self.end_pin: tuple[str, str] | None = None
        self.net_name: str = ""

        pen = QPen(QColor("#1a1a8c"), 2.0)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        self.setPen(pen)
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable)
        self.setZValue(1)
        self._rebuild_path()

    def _rebuild_path(self) -> None:
        """L-shaped 90° routing: go horizontal first, then vertical."""
        s, e = self.start_pos, self.end_pos
        path = QPainterPath(s)
        mid = QPointF(e.x(), s.y())
        path.lineTo(mid)
        path.lineTo(e)
        self.setPath(path)

    def update_endpoints(self, start: QPointF, end: QPointF) -> None:
        self.start_pos = start
        self.end_pos = end
        self._rebuild_path()

    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent) -> None:
        menu = QMenu()
        menu.addAction("Delete Wire").triggered.connect(self._delete_self)
        menu.exec(event.screenPos())

    def _delete_self(self) -> None:
        scene = self.scene()
        if scene:
            scene.removeItem(self)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.wire_id,
            "start": [self.start_pos.x(), self.start_pos.y()],
            "end": [self.end_pos.x(), self.end_pos.y()],
            "start_pin": list(self.start_pin) if self.start_pin else None,
            "end_pin": list(self.end_pin) if self.end_pin else None,
            "net_name": self.net_name,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WireItem":
        s = data.get("start", [0, 0])
        e = data.get("end", [0, 0])
        item = cls(QPointF(s[0], s[1]), QPointF(e[0], e[1]),
                   wire_id=data.get("id"))
        sp = data.get("start_pin")
        ep = data.get("end_pin")
        item.start_pin = tuple(sp) if sp else None  # type: ignore[assignment]
        item.end_pin = tuple(ep) if ep else None  # type: ignore[assignment]
        item.net_name = data.get("net_name", "")
        return item


# ---------------------------------------------------------------------------
# Wiring connector components (Elbow and Tee)
# ---------------------------------------------------------------------------

from .base import ComponentItem, _std_pen


class WireElbowItem(ComponentItem):
    """90° elbow wire connector.

    Pins: 'a' at (0, -20) and 'b' at (20, 0) — an L-shaped corner.
    """

    _WIDTH = 40.0
    _HEIGHT = 40.0

    def __init__(self, ref: str = "J1", value: str = "",
                 params: dict[str, Any] | None = None,
                 comp_id: str | None = None) -> None:
        super().__init__("ELBOW", ref, value, params, comp_id)

    def _pin_definitions(self) -> dict[str, QPointF]:
        return {"a": QPointF(0, -20), "b": QPointF(20, 0)}

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(_std_pen())
        painter.setBrush(QBrush(QColor("#e0f0ff")))
        # L-shaped corner mark
        painter.drawLine(QPointF(0, -20), QPointF(0, 0))
        painter.drawLine(QPointF(0, 0), QPointF(20, 0))
        # Corner dot
        painter.setBrush(QBrush(QColor("#1a1a8c")))
        painter.drawEllipse(QPointF(0, 0), 4, 4)


class WireTeeItem(ComponentItem):
    """T-junction wire connector.

    Pins: 'left' at (-20, 0), 'right' at (20, 0), 'down' at (0, 20).
    """

    _WIDTH = 40.0
    _HEIGHT = 40.0

    def __init__(self, ref: str = "J1", value: str = "",
                 params: dict[str, Any] | None = None,
                 comp_id: str | None = None) -> None:
        super().__init__("TEE", ref, value, params, comp_id)

    def _pin_definitions(self) -> dict[str, QPointF]:
        return {
            "left": QPointF(-20, 0),
            "right": QPointF(20, 0),
            "down": QPointF(0, 20),
        }

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(_std_pen())
        # T-shaped lines
        painter.drawLine(QPointF(-20, 0), QPointF(20, 0))
        painter.drawLine(QPointF(0, 0), QPointF(0, 20))
        # Junction dot
        painter.setBrush(QBrush(QColor("#1a1a8c")))
        painter.drawEllipse(QPointF(0, 0), 4, 4)

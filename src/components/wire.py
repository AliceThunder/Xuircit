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

_LINE_STYLE_MAP = {
    "solid": Qt.PenStyle.SolidLine,
    "dash": Qt.PenStyle.DashLine,
    "dot": Qt.PenStyle.DotLine,
    "dash_dot": Qt.PenStyle.DashDotLine,
    "dash_dot_dot": Qt.PenStyle.DashDotDotLine,
}


def _qt_style(name: str) -> Qt.PenStyle:
    return _LINE_STYLE_MAP.get(name, Qt.PenStyle.SolidLine)


class WireItem(QGraphicsPathItem):
    """A wire between two points, auto-routed at 90° angles."""

    _DEFAULT_COLOR = "#000000"  # Task 7: default wire color is black

    def __init__(self, start: QPointF, end: QPointF,
                 wire_id: str | None = None,
                 is_auto: bool = False) -> None:
        super().__init__()
        self.wire_id: str = wire_id or str(uuid.uuid4())
        self.start_pos = start
        self.end_pos = end
        self.start_pin: tuple[str, str] | None = None
        self.end_pin: tuple[str, str] | None = None
        self.net_name: str = ""
        # Bug 1 fix: auto-generated wires are non-interactive
        self.is_auto: bool = is_auto
        # Task 7: read default wire color from settings
        try:
            from ..app.settings import AppSettings
            s = AppSettings()
            self._color: str = s.wire_color()
            self._line_style_name: str = s.wire_line_style()
            self._line_width: float = s.wire_line_width()
        except Exception:
            self._color = self._DEFAULT_COLOR
            self._line_style_name = "solid"
            self._line_width = 2.0

        self._apply_pen()
        if not is_auto:
            self.setFlag(self.GraphicsItemFlag.ItemIsSelectable)
        else:
            # Auto-wires: not selectable, not focusable, don't accept mouse events
            self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, False)
            self.setFlag(self.GraphicsItemFlag.ItemIsFocusable, False)
            self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
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

    def _apply_pen(self) -> None:
        pen = QPen(QColor(self._color), self._line_width)
        pen.setStyle(_qt_style(self._line_style_name))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        self.setPen(pen)

    def set_color(self, color: str) -> None:
        self._color = color
        self._apply_pen()
        self.update()

    def set_line_style(self, style_name: str, width: float | None = None) -> None:
        self._line_style_name = style_name
        if width is not None:
            self._line_width = max(0.5, float(width))
        self._apply_pen()
        self.update()

    def update_endpoints(self, start: QPointF, end: QPointF) -> None:
        self.start_pos = start
        self.end_pos = end
        self._rebuild_path()

    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent) -> None:
        menu = QMenu()
        menu.addAction("Set Wire Color…").triggered.connect(self._set_color)
        menu.addSeparator()
        menu.addAction("Delete Wire").triggered.connect(self._delete_self)
        menu.exec(event.screenPos())

    def _set_color(self) -> None:
        """Feature #8: open color dialog for wire color."""
        from PyQt6.QtWidgets import QColorDialog
        color = QColorDialog.getColor(
            QColor(self._color), None, "Set Wire Color"
        )
        if color.isValid():
            self.set_color(color.name())

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
            "color": self._color,
            "line_style": self._line_style_name,
            "line_width": self._line_width,
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
        # Feature #8: restore wire color
        if "color" in data:
            item.set_color(data["color"])
        item.set_line_style(
            str(data.get("line_style", "solid")),
            float(data.get("line_width", 2.0)),
        )
        return item




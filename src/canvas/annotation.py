"""Annotation items for the annotation drawing layer (Feature #6)."""
from __future__ import annotations

import uuid
from typing import Any

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsSceneContextMenuEvent,
    QMenu,
    QStyleOptionGraphicsItem,
    QWidget,
)

# Z-value for annotation items (above components)
ANNOTATION_Z = 20

# Default annotation color
_DEFAULT_ANNO_COLOR = "#cc2222"


class AnnotationItem(QGraphicsPathItem):
    """A user-drawn annotation shape on the annotation layer.

    Supports:
    - "line":     a straight line from p1 to p2
    - "arrow":    a line with an arrowhead at p2
    - "circle":   a circle centred at p1 with radius = dist(p1, p2)
    - "ellipse":  an ellipse inscribed in the bounding box of p1–p2
    - "rect":     a rectangle from p1 to p2
    - "polyline": an open/closed polyline of multiple points
    """

    def __init__(
        self,
        kind: str,
        points: list[list[float]],
        closed: bool = False,
        color: str = _DEFAULT_ANNO_COLOR,
        line_width: float = 2.0,
        fill: bool = False,
        anno_id: str | None = None,
    ) -> None:
        super().__init__()
        self.anno_id = anno_id or str(uuid.uuid4())
        self.kind = kind
        self.points = points  # list of [x, y]
        self.closed = closed
        self.anno_color = color
        self.line_width = line_width
        self.fill = fill
        self.setZValue(ANNOTATION_Z)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self._rebuild_path()

    # ------------------------------------------------------------------
    # Path construction
    # ------------------------------------------------------------------

    def _rebuild_path(self) -> None:
        pen = QPen(QColor(self.anno_color), self.line_width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        self.setPen(pen)
        if self.fill:
            self.setBrush(QBrush(QColor(self.anno_color)))
        else:
            self.setBrush(QBrush(Qt.BrushStyle.NoBrush))

        path = QPainterPath()
        pts = self.points

        if not pts:
            self.setPath(path)
            return

        if self.kind == "arrow":
            self._build_arrow_path(path)
        elif self.kind in ("line", "polyline"):
            path.moveTo(pts[0][0], pts[0][1])
            for pt in pts[1:]:
                path.lineTo(pt[0], pt[1])
            if self.closed and len(pts) >= 3:
                path.closeSubpath()
        elif self.kind == "circle":
            if len(pts) >= 2:
                import math
                cx, cy = pts[0]
                dx = pts[1][0] - cx
                dy = pts[1][1] - cy
                r = math.hypot(dx, dy)
                path.addEllipse(QPointF(cx, cy), r, r)
        elif self.kind in ("ellipse", "rect"):
            if len(pts) >= 2:
                x1, y1 = pts[0]
                x2, y2 = pts[1]
                rx, ry = min(x1, x2), min(y1, y2)
                w, h = abs(x2 - x1), abs(y2 - y1)
                if self.kind == "ellipse":
                    path.addEllipse(QRectF(rx, ry, w, h))
                else:
                    path.addRect(QRectF(rx, ry, w, h))
        else:
            # Fallback: treat as polyline
            path.moveTo(pts[0][0], pts[0][1])
            for pt in pts[1:]:
                path.lineTo(pt[0], pt[1])

        self.setPath(path)

    def _build_arrow_path(self, path: QPainterPath) -> None:
        """Build an arrow from first to last point with arrowhead at last."""
        import math
        pts = self.points
        if len(pts) < 2:
            return
        x1, y1 = pts[0]
        x2, y2 = pts[-1]
        path.moveTo(x1, y1)
        path.lineTo(x2, y2)

        # Arrowhead
        angle = math.atan2(y2 - y1, x2 - x1)
        arrow_size = 12.0
        a1 = angle + math.pi * 0.8
        a2 = angle - math.pi * 0.8
        path.moveTo(x2, y2)
        path.lineTo(x2 + arrow_size * math.cos(a1),
                    y2 + arrow_size * math.sin(a1))
        path.moveTo(x2, y2)
        path.lineTo(x2 + arrow_size * math.cos(a2),
                    y2 + arrow_size * math.sin(a2))

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent) -> None:
        menu = QMenu()
        menu.addAction("Set Color…").triggered.connect(self._set_color)
        menu.addSeparator()
        menu.addAction("Delete").triggered.connect(self._delete_self)
        menu.exec(event.screenPos())

    def _set_color(self) -> None:
        from PyQt6.QtWidgets import QColorDialog
        color = QColorDialog.getColor(
            QColor(self.anno_color), None, "Set Annotation Color"
        )
        if color.isValid():
            self.anno_color = color.name()
            self._rebuild_path()

    def _delete_self(self) -> None:
        scene = self.scene()
        if scene is not None:
            scene.removeItem(self)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.anno_id,
            "kind": self.kind,
            "points": self.points,
            "closed": self.closed,
            "color": self.anno_color,
            "line_width": self.line_width,
            "fill": self.fill,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AnnotationItem":
        return cls(
            kind=data.get("kind", "line"),
            points=data.get("points", []),
            closed=data.get("closed", False),
            color=data.get("color", _DEFAULT_ANNO_COLOR),
            line_width=data.get("line_width", 2.0),
            fill=data.get("fill", False),
            anno_id=data.get("id"),
        )

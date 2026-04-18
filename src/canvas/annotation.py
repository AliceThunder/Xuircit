"""Annotation items for the annotation drawing layer (Feature #6)."""
from __future__ import annotations

import uuid
from typing import Any

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QFontComboBox,
    QFormLayout,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsSceneContextMenuEvent,
    QGraphicsSimpleTextItem,
    QMenu,
    QSpinBox,
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
        color = QColorDialog.getColor(
            QColor(self.anno_color), None, "Set Annotation Color"
        )
        if color.isValid():
            scene = self.scene()
            before = None
            if scene is not None and hasattr(scene, "_take_snapshot") and \
                    hasattr(scene, "undo_stack") and scene.undo_stack is not None:
                before = scene._take_snapshot()
            self.anno_color = color.name()
            self._rebuild_path()
            if before is not None and hasattr(scene, "_push_undo") and \
                    hasattr(scene, "_take_snapshot"):
                after = scene._take_snapshot()
                scene._push_undo("Set Annotation Color", before, after)

    def _delete_self(self) -> None:
        scene = self.scene()
        if scene is not None:
            # Fix 6: push undo before deleting
            before = None
            if hasattr(scene, "_take_snapshot") and \
                    hasattr(scene, "undo_stack") and scene.undo_stack is not None:
                before = scene._take_snapshot()
            if hasattr(scene, "circuit"):
                scene.circuit.remove_annotation(self.anno_id)
            scene.removeItem(self)
            if before is not None and hasattr(scene, "_push_undo") and \
                    hasattr(scene, "_take_snapshot"):
                after = scene._take_snapshot()
                scene._push_undo("Delete Annotation", before, after)

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
        # Dispatch to TextAnnotationItem for "text" kind
        if data.get("kind") == "text":
            return TextAnnotationItem.from_dict(data)  # type: ignore[return-value]
        return cls(
            kind=data.get("kind", "line"),
            points=data.get("points", []),
            closed=data.get("closed", False),
            color=data.get("color", _DEFAULT_ANNO_COLOR),
            line_width=data.get("line_width", 2.0),
            fill=data.get("fill", False),
            anno_id=data.get("id"),
        )


# ---------------------------------------------------------------------------
# Fix 10: Text annotation item
# ---------------------------------------------------------------------------

class TextAnnotationItem(QGraphicsSimpleTextItem):
    """A text annotation placed on the annotation layer.

    Supports full text styling: font family, size, bold, italic, color.
    """

    def __init__(
        self,
        text: str,
        x: float,
        y: float,
        color: str = _DEFAULT_ANNO_COLOR,
        font_family: str = "Sans Serif",
        font_size: int = 12,
        bold: bool = False,
        italic: bool = False,
        anno_id: str | None = None,
    ) -> None:
        super().__init__(text)
        self.anno_id = anno_id or str(uuid.uuid4())
        self.kind = "text"
        self.anno_color = color
        self.font_family = font_family
        self.font_size = font_size
        self.bold = bold
        self.italic = italic

        self.setBrush(QBrush(QColor(color)))
        font = QFont(font_family, font_size)
        font.setBold(bold)
        font.setItalic(italic)
        self.setFont(font)

        self.setPos(x, y)
        self.setZValue(ANNOTATION_Z)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)

    # Expose points as a convenience (x, y of origin) for sync_to_circuit
    @property
    def points(self) -> list[list[float]]:
        return [[self.pos().x(), self.pos().y()]]

    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent) -> None:
        menu = QMenu()
        menu.addAction("Edit…").triggered.connect(self._edit_text)
        menu.addAction("Set Color…").triggered.connect(self._set_color)
        menu.addSeparator()
        menu.addAction("Delete").triggered.connect(self._delete_self)
        menu.exec(event.screenPos())

    def _edit_text(self) -> None:
        scene = self.scene()
        before = None
        if scene is not None and hasattr(scene, "_take_snapshot") and \
                hasattr(scene, "undo_stack") and scene.undo_stack is not None:
            before = scene._take_snapshot()
        dlg = _TextAnnotationDialog(
            text=self.text(),
            color=self.anno_color,
            font_family=self.font_family,
            font_size=self.font_size,
            bold=self.bold,
            italic=self.italic,
        )
        if dlg.exec():
            self.anno_color = dlg.color()
            self.font_family = dlg.font_family()
            self.font_size = dlg.font_size()
            self.bold = dlg.bold()
            self.italic = dlg.italic()
            self.setText(dlg.text())
            self.setBrush(QBrush(QColor(self.anno_color)))
            font = QFont(self.font_family, self.font_size)
            font.setBold(self.bold)
            font.setItalic(self.italic)
            self.setFont(font)
            # Update in circuit annotations
            if scene is not None and hasattr(scene, "circuit"):
                scene.circuit.remove_annotation(self.anno_id)
                scene.circuit.add_annotation(self.to_dict())
            if before is not None and scene is not None and \
                    hasattr(scene, "_push_undo") and hasattr(scene, "_take_snapshot"):
                after = scene._take_snapshot()
                scene._push_undo("Edit Text Annotation", before, after)

    def _set_color(self) -> None:
        color = QColorDialog.getColor(
            QColor(self.anno_color), None, "Set Text Color"
        )
        if color.isValid():
            scene = self.scene()
            before = None
            if scene is not None and hasattr(scene, "_take_snapshot") and \
                    hasattr(scene, "undo_stack") and scene.undo_stack is not None:
                before = scene._take_snapshot()
            self.anno_color = color.name()
            self.setBrush(QBrush(QColor(self.anno_color)))
            if scene is not None and hasattr(scene, "circuit"):
                scene.circuit.remove_annotation(self.anno_id)
                scene.circuit.add_annotation(self.to_dict())
            if before is not None and scene is not None and \
                    hasattr(scene, "_push_undo") and hasattr(scene, "_take_snapshot"):
                after = scene._take_snapshot()
                scene._push_undo("Set Text Color", before, after)

    def _delete_self(self) -> None:
        scene = self.scene()
        if scene is not None:
            before = None
            if hasattr(scene, "_take_snapshot") and \
                    hasattr(scene, "undo_stack") and scene.undo_stack is not None:
                before = scene._take_snapshot()
            if hasattr(scene, "circuit"):
                scene.circuit.remove_annotation(self.anno_id)
            scene.removeItem(self)
            if before is not None and hasattr(scene, "_push_undo") and \
                    hasattr(scene, "_take_snapshot"):
                after = scene._take_snapshot()
                scene._push_undo("Delete Text Annotation", before, after)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.anno_id,
            "kind": "text",
            "text": self.text(),
            "x": self.pos().x(),
            "y": self.pos().y(),
            "color": self.anno_color,
            "font_family": self.font_family,
            "font_size": self.font_size,
            "bold": self.bold,
            "italic": self.italic,
            # For compatibility with AnnotationItem.from_dict dispatcher
            "points": [[self.pos().x(), self.pos().y()]],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TextAnnotationItem":
        x, y = data.get("x", 0.0), data.get("y", 0.0)
        # Fallback: read from points list if x/y not present
        pts = data.get("points", [])
        if pts:
            x, y = pts[0][0], pts[0][1]
        return cls(
            text=data.get("text", ""),
            x=x, y=y,
            color=data.get("color", _DEFAULT_ANNO_COLOR),
            font_family=data.get("font_family", "Sans Serif"),
            font_size=data.get("font_size", 12),
            bold=data.get("bold", False),
            italic=data.get("italic", False),
            anno_id=data.get("id"),
        )


# ---------------------------------------------------------------------------
# Fix 10: Text annotation placement dialog
# ---------------------------------------------------------------------------

class _TextAnnotationDialog(QDialog):
    """Dialog for entering text annotation content and style."""

    def __init__(
        self,
        text: str = "",
        color: str = _DEFAULT_ANNO_COLOR,
        font_family: str = "Sans Serif",
        font_size: int = 12,
        bold: bool = False,
        italic: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Text Annotation")
        self._color = color

        layout = QFormLayout(self)

        from PyQt6.QtWidgets import QLineEdit
        self._text_edit = QLineEdit(text)
        self._text_edit.setPlaceholderText("Enter annotation text…")
        layout.addRow("Text:", self._text_edit)

        self._font_combo = QFontComboBox()
        self._font_combo.setCurrentFont(QFont(font_family))
        layout.addRow("Font:", self._font_combo)

        self._size_spin = QSpinBox()
        self._size_spin.setRange(4, 200)
        self._size_spin.setValue(font_size)
        layout.addRow("Size:", self._size_spin)

        self._bold_cb = QCheckBox()
        self._bold_cb.setChecked(bold)
        layout.addRow("Bold:", self._bold_cb)

        self._italic_cb = QCheckBox()
        self._italic_cb.setChecked(italic)
        layout.addRow("Italic:", self._italic_cb)

        self._color_btn = _ColorButton(color)
        layout.addRow("Color:", self._color_btn)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

    def text(self) -> str:
        from PyQt6.QtWidgets import QLineEdit
        return self._text_edit.text()

    def font_family(self) -> str:
        return self._font_combo.currentFont().family()

    def font_size(self) -> int:
        return self._size_spin.value()

    def bold(self) -> bool:
        return self._bold_cb.isChecked()

    def italic(self) -> bool:
        return self._italic_cb.isChecked()

    def color(self) -> str:
        return self._color_btn.color()


class _ColorButton(QWidget):
    """Simple color-picker button used in dialogs."""

    def __init__(self, color: str = "#cc2222", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        from PyQt6.QtWidgets import QHBoxLayout, QPushButton
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._color = color
        self._btn = QPushButton("  ")
        self._btn.setFixedWidth(60)
        self._btn.setStyleSheet(f"background-color: {color}; border: 1px solid #888;")
        self._btn.clicked.connect(self._pick)
        layout.addWidget(self._btn)

    def _pick(self) -> None:
        c = QColorDialog.getColor(QColor(self._color), self, "Pick Color")
        if c.isValid():
            self._color = c.name()
            self._btn.setStyleSheet(
                f"background-color: {self._color}; border: 1px solid #888;"
            )

    def color(self) -> str:
        return self._color


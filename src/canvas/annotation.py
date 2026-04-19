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
    QGraphicsSceneMouseEvent,
    QGraphicsSceneContextMenuEvent,
    QGraphicsTextItem,
    QMenu,
    QSpinBox,
    QStyleOptionGraphicsItem,
    QWidget,
)

from ..components.wire import _qt_style as _line_style_qt
from ..canvas.grid import GRID_SIZE

# Z-value for annotation items (above components)
ANNOTATION_Z = 20

# Default annotation color
_DEFAULT_ANNO_COLOR = "#cc2222"
_ANNO_GRID_SIZE = GRID_SIZE // 4


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
        line_style: str = "solid",
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
        self.line_style = line_style
        self.fill = fill
        self.setZValue(ANNOTATION_Z)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self._rebuild_path()

    # ------------------------------------------------------------------
    # Path construction
    # ------------------------------------------------------------------

    def _rebuild_path(self) -> None:
        pen = QPen(QColor(self.anno_color), self.line_width)
        pen.setStyle(_line_style_qt(self.line_style))
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
        if not self.isSelected():
            scene = self.scene()
            if scene is not None:
                scene.clearSelection()
            self.setSelected(True)
        menu = QMenu()
        menu.addAction("Set Color…").triggered.connect(self._set_color)
        menu.addAction("Properties…").triggered.connect(self._open_properties_panel)
        menu.addSeparator()
        menu.addAction("Delete").triggered.connect(self._delete_self)
        menu.exec(event.screenPos())

    def _open_properties_panel(self) -> None:
        scene = self.scene()
        if scene is not None and hasattr(scene, "focus_properties_for_item"):
            scene.focus_properties_for_item(self)

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        self.setSelected(True)
        self._open_properties_panel()
        super().mouseDoubleClickEvent(event)

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

    def set_line_style(self, style_name: str, width: float | None = None) -> None:
        self.line_style = style_name
        if width is not None:
            self.line_width = max(0.5, float(width))
        self._rebuild_path()

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any) -> Any:
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            return QPointF(
                round(value.x() / _ANNO_GRID_SIZE) * _ANNO_GRID_SIZE,
                round(value.y() / _ANNO_GRID_SIZE) * _ANNO_GRID_SIZE,
            )
        return super().itemChange(change, value)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        super().paint(painter, option, widget)
        if self.isSelected():
            sel_pen = QPen(QColor("#ff8800"), 1.5, Qt.PenStyle.DashLine)
            painter.setPen(sel_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.boundingRect())

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
            "line_style": self.line_style,
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
            line_style=data.get("line_style", "solid"),
            fill=data.get("fill", False),
            anno_id=data.get("id"),
        )


# ---------------------------------------------------------------------------
# Bug 6: Text annotation item with rich text (HTML) support
# ---------------------------------------------------------------------------

class TextAnnotationItem(QGraphicsTextItem):
    """A text annotation placed on the annotation layer.

    Bug 6: Supports HTML rich text (bold, italic, font size, inline color,
    etc.) via QGraphicsTextItem.  Plain-text annotations from earlier project
    files are loaded transparently and converted to plain HTML.
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
        # Bug 6: is_html=True → text is stored/loaded as HTML; False → plain
        is_html: bool = False,
    ) -> None:
        super().__init__()
        self.anno_id = anno_id or str(uuid.uuid4())
        self.kind = "text"
        self.anno_color = color
        self.font_family = font_family
        self.font_size = font_size
        self.bold = bold
        self.italic = italic

        font = QFont(font_family, font_size)
        font.setBold(bold)
        font.setItalic(italic)
        self.setFont(font)
        self.setDefaultTextColor(QColor(color))

        # Store and display content
        if is_html:
            self.setHtml(text)
        else:
            # Wrap plain text in a span so the color is applied uniformly
            self.setPlainText(text)

        self.setPos(x, y)
        self.setZValue(ANNOTATION_Z)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)

    # Expose points as a convenience (x, y of origin) for sync_to_circuit
    @property
    def points(self) -> list[list[float]]:
        return [[self.pos().x(), self.pos().y()]]

    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent) -> None:
        if not self.isSelected():
            scene = self.scene()
            if scene is not None:
                scene.clearSelection()
            self.setSelected(True)
        menu = QMenu()
        menu.addAction("Edit…").triggered.connect(self._edit_text)
        menu.addAction("Set Default Color…").triggered.connect(self._set_color)
        menu.addAction("Properties…").triggered.connect(self._open_properties_panel)
        menu.addSeparator()
        menu.addAction("Delete").triggered.connect(self._delete_self)
        menu.exec(event.screenPos())

    def _open_properties_panel(self) -> None:
        scene = self.scene()
        if scene is not None and hasattr(scene, "focus_properties_for_item"):
            scene.focus_properties_for_item(self)

    def _edit_text(self) -> None:
        scene = self.scene()
        before = None
        if scene is not None and hasattr(scene, "_take_snapshot") and \
                hasattr(scene, "undo_stack") and scene.undo_stack is not None:
            before = scene._take_snapshot()
        dlg = _RichTextAnnotationDialog(
            html=self.toHtml(),
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
            self.setHtml(dlg.html())
            self.setDefaultTextColor(QColor(self.anno_color))
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
            QColor(self.anno_color), None, "Set Default Text Color"
        )
        if color.isValid():
            scene = self.scene()
            before = None
            if scene is not None and hasattr(scene, "_take_snapshot") and \
                    hasattr(scene, "undo_stack") and scene.undo_stack is not None:
                before = scene._take_snapshot()
            self.anno_color = color.name()
            self.setDefaultTextColor(QColor(self.anno_color))
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
            # Bug 6: store as HTML so rich text is preserved across save/load
            "text": self.toHtml(),
            "is_html": True,
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

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any) -> Any:
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            return QPointF(
                round(value.x() / _ANNO_GRID_SIZE) * _ANNO_GRID_SIZE,
                round(value.y() / _ANNO_GRID_SIZE) * _ANNO_GRID_SIZE,
            )
        return super().itemChange(change, value)

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        self.setSelected(True)
        self._open_properties_panel()
        super().mouseDoubleClickEvent(event)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        super().paint(painter, option, widget)
        if self.isSelected():
            sel_pen = QPen(QColor("#ff8800"), 1.5, Qt.PenStyle.DashLine)
            painter.setPen(sel_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.boundingRect())

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
            is_html=data.get("is_html", False),
        )


# ---------------------------------------------------------------------------
# Bug 6: Rich text annotation dialog
# ---------------------------------------------------------------------------

class _RichTextAnnotationDialog(QDialog):
    """Dialog for entering/editing a rich-text annotation.

    Features a QTextEdit with a formatting toolbar (bold, italic, color, font
    size) so the user can apply inline formatting to individual words.
    """

    def __init__(
        self,
        html: str = "",
        color: str = _DEFAULT_ANNO_COLOR,
        font_family: str = "Sans Serif",
        font_size: int = 12,
        bold: bool = False,
        italic: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Text Annotation (Rich Text)")
        self.resize(520, 380)
        self._color = color

        from PyQt6.QtWidgets import QTextEdit, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSizePolicy
        from PyQt6.QtGui import QTextCharFormat, QFont as QF

        outer = QVBoxLayout(self)

        # ── Formatting toolbar ────────────────────────────────────────
        fmt_row = QHBoxLayout()

        self._font_combo = QFontComboBox()
        self._font_combo.setCurrentFont(QF(font_family))
        self._font_combo.setMaximumWidth(160)
        fmt_row.addWidget(self._font_combo)

        self._size_spin = QSpinBox()
        self._size_spin.setRange(4, 200)
        self._size_spin.setValue(font_size)
        self._size_spin.setMaximumWidth(55)
        fmt_row.addWidget(self._size_spin)

        self._bold_btn = QPushButton("B")
        self._bold_btn.setCheckable(True)
        self._bold_btn.setChecked(bold)
        self._bold_btn.setMaximumWidth(28)
        self._bold_btn.setStyleSheet("font-weight: bold;")
        fmt_row.addWidget(self._bold_btn)

        self._italic_btn = QPushButton("I")
        self._italic_btn.setCheckable(True)
        self._italic_btn.setChecked(italic)
        self._italic_btn.setMaximumWidth(28)
        self._italic_btn.setStyleSheet("font-style: italic;")
        fmt_row.addWidget(self._italic_btn)

        self._color_btn = QPushButton("Color…")
        self._color_btn.setMaximumWidth(60)
        self._color_btn.setStyleSheet(
            f"background-color: {color}; border: 1px solid #888;"
        )
        self._color_btn.clicked.connect(self._pick_color)
        fmt_row.addWidget(self._color_btn)

        apply_fmt_btn = QPushButton("Apply to Selection")
        apply_fmt_btn.clicked.connect(self._apply_format)
        fmt_row.addWidget(apply_fmt_btn)

        fmt_row.addStretch()
        outer.addLayout(fmt_row)

        # ── Text editor ───────────────────────────────────────────────
        self._editor = QTextEdit()
        self._editor.setAcceptRichText(True)
        if html and html.strip().startswith("<"):
            self._editor.setHtml(html)
        else:
            self._editor.setPlainText(html)
        outer.addWidget(self._editor, 1)

        # ── Default font/color note ───────────────────────────────────
        note = QLabel(
            "Tip: Select text and click 'Apply to Selection' to apply "
            "bold/italic/color/size to individual words."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #666; font-size: 10px;")
        outer.addWidget(note)

        # ── Buttons ───────────────────────────────────────────────────
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        outer.addWidget(btns)

    def _pick_color(self) -> None:
        c = QColorDialog.getColor(QColor(self._color), self, "Pick Default Color")
        if c.isValid():
            self._color = c.name()
            self._color_btn.setStyleSheet(
                f"background-color: {self._color}; border: 1px solid #888;"
            )

    def _apply_format(self) -> None:
        """Apply the chosen font/size/bold/italic/color to the selected text."""
        from PyQt6.QtGui import QTextCharFormat, QFont as QF, QColor as QC
        fmt = QTextCharFormat()
        font = QF(self._font_combo.currentFont().family(), self._size_spin.value())
        font.setBold(self._bold_btn.isChecked())
        font.setItalic(self._italic_btn.isChecked())
        fmt.setFont(font)
        fmt.setForeground(QC(self._color))
        cursor = self._editor.textCursor()
        if cursor.hasSelection():
            cursor.mergeCharFormat(fmt)
        else:
            # No selection – apply to whole document
            self._editor.selectAll()
            self._editor.textCursor().mergeCharFormat(fmt)
            cursor = self._editor.textCursor()
            cursor.clearSelection()
            self._editor.setTextCursor(cursor)

    def html(self) -> str:
        return self._editor.toHtml()

    def font_family(self) -> str:
        return self._font_combo.currentFont().family()

    def font_size(self) -> int:
        return self._size_spin.value()

    def bold(self) -> bool:
        return self._bold_btn.isChecked()

    def italic(self) -> bool:
        return self._italic_btn.isChecked()

    def color(self) -> str:
        return self._color


# Keep the old name as an alias for backward compatibility (used by tests).
_TextAnnotationDialog = _RichTextAnnotationDialog

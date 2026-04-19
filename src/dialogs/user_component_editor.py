"""User Component Editor — create and edit schematic components across libraries."""
from __future__ import annotations

import copy
from typing import Any

from PyQt6.QtCore import QPointF, QRectF, Qt, QObject, QEvent, pyqtSignal
from PyQt6.QtGui import (
    QBrush, QColor, QFont, QPainter, QPen, QKeySequence, QUndoCommand,
    QUndoStack, QPolygonF,
)
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..models.user_library import LabelDef, PinDef, SymbolCmd, UserCompDef
from ..models.library_system import LibEntry, LibraryManager, PRESET_LIBRARY_ID
from ..canvas.grid import GRID_SIZE, draw_grid, snap_to_grid

# Issue 7: sub-grid (denser than existing GRID_SIZE=20).
# Pins still snap to GRID_SIZE; drawing-tool endpoints snap to SUB_GRID.
# Issue 7: 4 sub-divisions per main grid (was 2 → SUB_GRID = GRID_SIZE // 4 = 5 px)
SUB_GRID = GRID_SIZE // 4  # 5 px


def _snap_sub(x: float, y: float) -> tuple[float, float]:
    """Snap to the denser sub-grid."""
    return round(x / SUB_GRID) * SUB_GRID, round(y / SUB_GRID) * SUB_GRID


# ---------------------------------------------------------------------------
# Undo command for symbol scene (Issue 6)
# ---------------------------------------------------------------------------

class _SymSceneSnapshot(QUndoCommand):
    """Undo/redo a complete symbol-state change."""

    def __init__(self, scene: "_SymbolScene", before: dict, after: dict,
                 text: str) -> None:
        super().__init__(text)
        self._scene = scene
        self._before = before
        self._after = after
        self._first_redo = True

    def undo(self) -> None:
        self._scene._restore_snapshot(self._before)

    def redo(self) -> None:
        if self._first_redo:
            self._first_redo = False
            return
        self._scene._restore_snapshot(self._after)


# ---------------------------------------------------------------------------
# Mini scene / view for drawing the symbol
# ---------------------------------------------------------------------------

class _SymbolScene(QGraphicsScene):
    """Small scene for placing symbol elements interactively."""

    # Issue 4: emitted when the active tool changes so the toolbar can highlight
    tool_changed = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setSceneRect(QRectF(-200, -200, 400, 400))
        self.setBackgroundBrush(QColor("#f8f8f8"))
        # tools: "select" | "line" | "rect" | "ellipse" | "pin" | "polyline"
        self._tool: str = "select"
        self._fill_mode: bool = False  # Issue 6: solid fill toggle
        self._line_start: QPointF | None = None
        self._temp_item: QGraphicsItem | None = None
        self.pins: list["_PinMarker"] = []
        self.sym_cmds: list[SymbolCmd] = []
        # Issue 5/6: parallel list of QGraphicsItems for sym_cmds (1-to-1 mapping)
        self._sym_items: list[QGraphicsItem] = []
        # Issue 5: clipboard for copy/paste within the editor
        self._sym_clipboard: list[SymbolCmd] = []
        # Issue 6: undo stack
        self._undo_stack = QUndoStack(self)
        # Feature #3: polyline drawing state
        self._poly_points: list[QPointF] = []
        self._poly_segs: list[QGraphicsItem] = []  # temporary segment items
        # Task 2: property position markers (Ref = Basic Property, Val = Extra Property)
        self._ref_marker: "_PropertyMarkerItem | None" = None
        self._val_marker: "_PropertyMarkerItem | None" = None
        # Feature 6: markers for extra properties (one per LabelDef, by index)
        self._extra_markers: list["_PropertyMarkerItem | None"] = []
        try:
            from ..app.settings import AppSettings
            s = AppSettings()
            self._line_style_name = s.editor_line_style()
            self._line_width = s.editor_line_width()
        except Exception:
            self._line_style_name = "solid"
            self._line_width = 2.0
        self._draw_origin()

    def _draw_pen(self) -> QPen:
        pen = QPen(QColor("#111111"), self._line_width)
        style_map = {
            "solid": Qt.PenStyle.SolidLine,
            "dash": Qt.PenStyle.DashLine,
            "dot": Qt.PenStyle.DotLine,
            "dash_dot": Qt.PenStyle.DashDotLine,
            "dash_dot_dot": Qt.PenStyle.DashDotDotLine,
        }
        pen.setStyle(style_map.get(self._line_style_name, Qt.PenStyle.SolidLine))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return pen

    @staticmethod
    def _pen_for_cmd(cmd: SymbolCmd) -> QPen:
        pen = QPen(QColor("#111111"), float(getattr(cmd, "line_width", 2.0)))
        style_map = {
            "solid": Qt.PenStyle.SolidLine,
            "dash": Qt.PenStyle.DashLine,
            "dot": Qt.PenStyle.DotLine,
            "dash_dot": Qt.PenStyle.DashDotLine,
            "dash_dot_dot": Qt.PenStyle.DashDotDotLine,
        }
        pen.setStyle(style_map.get(
            str(getattr(cmd, "line_style", "solid")), Qt.PenStyle.SolidLine
        ))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return pen

    def set_line_style(self, style_name: str, width: float) -> None:
        self._line_style_name = style_name
        self._line_width = max(0.5, float(width))

    def apply_line_style_to_selected(self, style_name: str, width: float) -> None:
        selected = [it for it in self.selectedItems() if it in self._sym_items]
        if not selected:
            return
        before = self._snapshot()
        self.set_line_style(style_name, width)
        selected_set = set(selected)
        for idx, it in enumerate(self._sym_items):
            if it not in selected_set:
                continue
            cmd = self.sym_cmds[idx]
            cmd.line_style = style_name
            cmd.line_width = self._line_width
            it.setPen(self._draw_pen())
        self._push_undo("Set Line Style", before, self._snapshot())

    def _draw_origin(self) -> None:
        """Draw the origin crosshair."""
        pen = QPen(QColor("#aaaaff"), 0.5)
        pen.setCosmetic(True)
        self.addLine(-200, 0, 200, 0, pen)
        self.addLine(0, -200, 0, 200, pen)

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        super().drawBackground(painter, rect)
        # Issue 7: draw the denser sub-grid first (lighter), then the normal grid on top
        self._draw_sub_grid(painter, rect)
        draw_grid(painter, rect)

    def _draw_sub_grid(self, painter: QPainter, rect: QRectF) -> None:
        """Draw the additional denser sub-grid (SUB_GRID spacing)."""
        import math
        left = math.floor(rect.left() / SUB_GRID) * SUB_GRID - SUB_GRID
        top = math.floor(rect.top() / SUB_GRID) * SUB_GRID - SUB_GRID
        right = math.ceil(rect.right() / SUB_GRID) * SUB_GRID + SUB_GRID
        bottom = math.ceil(rect.bottom() / SUB_GRID) * SUB_GRID + SUB_GRID

        pen = QPen(QColor("#efefef"), 0)
        pen.setCosmetic(True)
        painter.setPen(pen)
        x = left
        while x <= right:
            if x % GRID_SIZE != 0:  # skip lines that belong to the major grid
                painter.drawLine(QPointF(x, top), QPointF(x, bottom))
            x += SUB_GRID
        y = top
        while y <= bottom:
            if y % GRID_SIZE != 0:
                painter.drawLine(QPointF(left, y), QPointF(right, y))
            y += SUB_GRID

    def set_tool(self, tool: str) -> None:
        self._cancel_draw()  # Cancel any in-progress draw when switching tools
        self._tool = tool
        self.tool_changed.emit(tool)  # Issue 4: notify toolbar of tool change

    def _cancel_draw(self) -> None:
        """Cancel any in-progress drawing operation."""
        self._line_start = None
        if self._temp_item:
            self.removeItem(self._temp_item)
            self._temp_item = None
        # Feature #3: cancel polyline drawing
        for seg in self._poly_segs:
            self.removeItem(seg)
        self._poly_segs.clear()
        self._poly_points.clear()

    # ------------------------------------------------------------------
    # Undo/redo helpers (Issue 6)
    # ------------------------------------------------------------------

    def _snapshot(self) -> dict:
        return {
            "cmds": copy.deepcopy(self.sym_cmds),
            "pins": [(p.pos().x(), p.pos().y(), p.pin_name) for p in self.pins],
        }

    def _restore_snapshot(self, snap: dict) -> None:
        """Restore scene from a snapshot dict."""
        # Rebuild sym items
        for it in list(self._sym_items):
            self.removeItem(it)
        self._sym_items.clear()
        self.sym_cmds.clear()
        # Remove pins
        for p in list(self.pins):
            self.removeItem(p)
        self.pins.clear()

        for cmd in snap.get("cmds", []):
            self.sym_cmds.append(cmd)
            pen = self._pen_for_cmd(cmd)
            if cmd.kind == "line":
                it = self.addLine(cmd.x1, cmd.y1, cmd.x2, cmd.y2, pen)
            elif cmd.kind == "rect":
                brush = (QBrush(QColor("#333333")) if cmd.filled
                         else QBrush(Qt.BrushStyle.NoBrush))
                it = self.addRect(QRectF(cmd.x1, cmd.y1, cmd.w, cmd.h), pen, brush)
            elif cmd.kind == "ellipse":
                rx, ry = cmd.w / 2, cmd.h / 2
                brush = (QBrush(QColor("#333333")) if cmd.filled
                         else QBrush(Qt.BrushStyle.NoBrush))
                it = self.addEllipse(
                    QRectF(cmd.x1 - rx, cmd.y1 - ry, cmd.w, cmd.h), pen, brush)
            elif cmd.kind == "polyline":
                # Feature #3: render polyline in the symbol editor
                from PyQt6.QtGui import QPainterPath
                pts = cmd.points
                if len(pts) >= 2:
                    path = QPainterPath()
                    path.moveTo(pts[0][0], pts[0][1])
                    for px, py in pts[1:]:
                        path.lineTo(px, py)
                    if cmd.filled and len(pts) >= 3:
                        path.closeSubpath()
                    it = QGraphicsPathItem(path)
                    it.setPen(pen)
                    if cmd.filled and len(pts) >= 3:
                        it.setBrush(QBrush(QColor("#333333")))
                    self.addItem(it)
                else:
                    it = self.addLine(0, 0, 0, 0, pen)
            else:
                it = self.addLine(0, 0, 0, 0, pen)
            it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
            it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
            self._sym_items.append(it)

        for px, py, pname in snap.get("pins", []):
            marker = _PinMarker(QPointF(px, py), pname)
            self.addItem(marker)
            self.pins.append(marker)

    def _push_undo(self, text: str, before: dict, after: dict) -> None:
        cmd = _SymSceneSnapshot(self, before, after, text)
        self._undo_stack.push(cmd)

    # ------------------------------------------------------------------
    # Mouse events
    # ------------------------------------------------------------------

    def mousePressEvent(self, event: Any) -> None:
        pos = event.scenePos()
        # Issue 6: right-click finishes polyline (if active) or cancels drawing
        if event.button() == Qt.MouseButton.RightButton:
            if self._tool == "polyline" and len(self._poly_points) >= 2:
                self._finish_polyline()
            else:
                self._cancel_draw()
            return

        sx, sy = snap_to_grid(pos.x(), pos.y())
        snapped = QPointF(sx, sy)
        # Issue 7: non-pin tools snap to sub-grid; pins snap to main grid
        if self._tool == "pin":
            draw_pos = snapped
        else:
            dsx, dsy = _snap_sub(pos.x(), pos.y())
            draw_pos = QPointF(dsx, dsy)

        if self._tool == "pin":
            before = self._snapshot()
            self._place_pin(snapped)
            self._push_undo("Add Pin", before, self._snapshot())
        elif self._tool == "polyline":
            # Feature #3: multi-segment polyline
            self._poly_points.append(draw_pos)
            if len(self._poly_points) >= 2:
                # Draw the confirmed segment
                pen = self._draw_pen()
                p1, p2 = self._poly_points[-2], self._poly_points[-1]
                seg = self.addLine(p1.x(), p1.y(), p2.x(), p2.y(), pen)
                self._poly_segs.append(seg)
            # Remove old preview
            if self._temp_item:
                self.removeItem(self._temp_item)
                self._temp_item = None
        elif self._tool == "line":
            if self._line_start is None:
                self._line_start = draw_pos
            else:
                before = self._snapshot()
                cmd = SymbolCmd("line",
                                x1=self._line_start.x(), y1=self._line_start.y(),
                                x2=draw_pos.x(), y2=draw_pos.y(),
                                line_style=self._line_style_name,
                                line_width=self._line_width)
                self.sym_cmds.append(cmd)
                pen = self._draw_pen()
                it = self.addLine(self._line_start.x(), self._line_start.y(),
                                  draw_pos.x(), draw_pos.y(), pen)
                it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
                it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
                self._sym_items.append(it)
                if self._temp_item:
                    self.removeItem(self._temp_item)
                    self._temp_item = None
                self._line_start = None
                self._push_undo("Draw Line", before, self._snapshot())
        elif self._tool == "rect":
            if self._line_start is None:
                self._line_start = draw_pos
            else:
                before = self._snapshot()
                x1, y1 = self._line_start.x(), self._line_start.y()
                x2, y2 = draw_pos.x(), draw_pos.y()
                w, h = abs(x2 - x1), abs(y2 - y1)
                rx, ry = min(x1, x2), min(y1, y2)
                cmd = SymbolCmd("rect", x1=rx, y1=ry, w=w, h=h,
                                line_style=self._line_style_name,
                                line_width=self._line_width,
                                filled=self._fill_mode)
                self.sym_cmds.append(cmd)
                pen = self._draw_pen()
                brush = (QBrush(QColor("#333333")) if self._fill_mode
                         else QBrush(Qt.BrushStyle.NoBrush))
                it = self.addRect(QRectF(rx, ry, w, h), pen, brush)
                it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
                it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
                self._sym_items.append(it)
                if self._temp_item:
                    self.removeItem(self._temp_item)
                    self._temp_item = None
                self._line_start = None
                self._push_undo("Draw Rect", before, self._snapshot())
        elif self._tool == "ellipse":
            if self._line_start is None:
                self._line_start = draw_pos
            else:
                before = self._snapshot()
                x1, y1 = self._line_start.x(), self._line_start.y()
                x2, y2 = draw_pos.x(), draw_pos.y()
                w, h = abs(x2 - x1), abs(y2 - y1)
                rx, ry = min(x1, x2), min(y1, y2)
                cmd = SymbolCmd("ellipse", x1=rx + w / 2, y1=ry + h / 2,
                                w=w, h=h, filled=self._fill_mode,
                                line_style=self._line_style_name,
                                line_width=self._line_width)
                self.sym_cmds.append(cmd)
                pen = self._draw_pen()
                brush = (QBrush(QColor("#333333")) if self._fill_mode
                         else QBrush(Qt.BrushStyle.NoBrush))
                it = self.addEllipse(QRectF(rx, ry, w, h), pen, brush)
                it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
                it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
                self._sym_items.append(it)
                if self._temp_item:
                    self.removeItem(self._temp_item)
                    self._temp_item = None
                self._line_start = None
                self._push_undo("Draw Ellipse", before, self._snapshot())
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: Any) -> None:
        pos = event.scenePos()
        # Preview for line/rect/ellipse
        if self._line_start is not None and self._tool in ("line", "rect", "ellipse"):
            # Issue 7: preview end-point also snaps to sub-grid
            dsx, dsy = _snap_sub(pos.x(), pos.y())
            draw_pos = QPointF(dsx, dsy)
            if self._temp_item:
                self.removeItem(self._temp_item)
            pen = QPen(QColor("#2277ee"), 1, Qt.PenStyle.DashLine)
            if self._tool == "line":
                self._temp_item = self.addLine(
                    self._line_start.x(), self._line_start.y(),
                    draw_pos.x(), draw_pos.y(), pen)
            elif self._tool == "rect":
                x1, y1 = self._line_start.x(), self._line_start.y()
                x2, y2 = draw_pos.x(), draw_pos.y()
                w, h = abs(x2 - x1), abs(y2 - y1)
                rx, ry = min(x1, x2), min(y1, y2)
                self._temp_item = self.addRect(
                    QRectF(rx, ry, w, h), pen, QBrush(Qt.BrushStyle.NoBrush))
            else:  # ellipse
                x1, y1 = self._line_start.x(), self._line_start.y()
                x2, y2 = draw_pos.x(), draw_pos.y()
                w, h = abs(x2 - x1), abs(y2 - y1)
                rx, ry = min(x1, x2), min(y1, y2)
                self._temp_item = self.addEllipse(
                    QRectF(rx, ry, w, h), pen, QBrush(Qt.BrushStyle.NoBrush))
        # Feature #3: preview for polyline
        elif self._tool == "polyline" and self._poly_points:
            dsx, dsy = _snap_sub(pos.x(), pos.y())
            draw_pos = QPointF(dsx, dsy)
            if self._temp_item:
                self.removeItem(self._temp_item)
            pen = QPen(QColor("#2277ee"), 1, Qt.PenStyle.DashLine)
            last = self._poly_points[-1]
            self._temp_item = self.addLine(
                last.x(), last.y(), draw_pos.x(), draw_pos.y(), pen)
        super().mouseMoveEvent(event)

    def mouseDoubleClickEvent(self, event: Any) -> None:
        """Feature #3: double-click finishes the polyline."""
        if self._tool == "polyline" and len(self._poly_points) >= 2:
            self._finish_polyline()
            return
        super().mouseDoubleClickEvent(event)

    def _finish_polyline(self) -> None:
        """Feature #3: commit the current polyline as a SymbolCmd."""
        if len(self._poly_points) < 2:
            self._cancel_draw()
            return
        before = self._snapshot()
        pts = [[p.x(), p.y()] for p in self._poly_points]
        cmd = SymbolCmd(
            "polyline",
            filled=self._fill_mode,
            points=pts,
            line_style=self._line_style_name,
            line_width=self._line_width,
        )
        self.sym_cmds.append(cmd)

        # Build a QGraphicsPathItem for the symbol editor display
        from PyQt6.QtGui import QPainterPath
        path = QPainterPath()
        path.moveTo(pts[0][0], pts[0][1])
        for px, py in pts[1:]:
            path.lineTo(px, py)
        if self._fill_mode and len(pts) >= 3:
            path.closeSubpath()
        pen = self._draw_pen()
        it = QGraphicsPathItem(path)
        it.setPen(pen)
        if self._fill_mode and len(pts) >= 3:
            it.setBrush(QBrush(QColor("#333333")))
        it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.addItem(it)
        self._sym_items.append(it)

        # Clean up temporary preview segments
        for seg in self._poly_segs:
            self.removeItem(seg)
        self._poly_segs.clear()
        self._poly_points.clear()
        if self._temp_item:
            self.removeItem(self._temp_item)
            self._temp_item = None
        self._push_undo("Draw Polyline", before, self._snapshot())

    # ------------------------------------------------------------------
    # Keyboard handling (Issues 5 & 6)
    # ------------------------------------------------------------------

    def keyPressEvent(self, event: Any) -> None:
        key = event.key()
        ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)

        # Issue 6: undo (Ctrl+Z) / redo (Ctrl+Y or Ctrl+Shift+Z)
        if ctrl and key == Qt.Key.Key_Z and not shift:
            self._undo_stack.undo()
            return
        if ctrl and (key == Qt.Key.Key_Y or (key == Qt.Key.Key_Z and shift)):
            self._undo_stack.redo()
            return

        # Feature #3: Escape cancels in-progress polyline or resets to select
        if key == Qt.Key.Key_Escape:
            self._cancel_draw()
            self.set_tool("select")  # Issue 4: reset to select and notify toolbar
            return

        # Issue 5: delete selected graphics
        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            selected_items = [it for it in self.selectedItems()
                              if it in self._sym_items]
            selected_pins = [it for it in self.selectedItems()
                             if isinstance(it, _PinMarker)]
            if selected_items or selected_pins:
                before = self._snapshot()
                for it in selected_items:
                    idx = self._sym_items.index(it)
                    self._sym_items.pop(idx)
                    self.sym_cmds.pop(idx)
                    self.removeItem(it)
                for p in selected_pins:
                    self.pins.remove(p)
                    self.removeItem(p)
                self._push_undo("Delete", before, self._snapshot())
            return

        # Issue 5: copy selected graphics
        if key == Qt.Key.Key_C and ctrl:
            self._sym_clipboard = []
            for it in self.selectedItems():
                if it in self._sym_items:
                    idx = self._sym_items.index(it)
                    self._sym_clipboard.append(copy.deepcopy(self.sym_cmds[idx]))
            return

        # Issue 5: paste graphics
        if key == Qt.Key.Key_V and ctrl:
            if self._sym_clipboard:
                before = self._snapshot()
                for cmd in self._sym_clipboard:
                    # Offset the pasted shape by sub-grid amount
                    c = copy.deepcopy(cmd)
                    c.x1 += SUB_GRID
                    c.y1 += SUB_GRID
                    if c.kind == "line":
                        c.x2 += SUB_GRID
                        c.y2 += SUB_GRID
                    self.sym_cmds.append(c)
                    if c.kind == "line":
                        pen = self._pen_for_cmd(c)
                        it = self.addLine(c.x1, c.y1, c.x2, c.y2, pen)
                    elif c.kind == "rect":
                        pen = self._pen_for_cmd(c)
                        it = self.addRect(QRectF(c.x1, c.y1, c.w, c.h), pen,
                                          QBrush(Qt.BrushStyle.NoBrush))
                    elif c.kind == "ellipse":
                        pen = self._pen_for_cmd(c)
                        rx2, ry2 = c.w / 2, c.h / 2
                        it = self.addEllipse(
                            QRectF(c.x1 - rx2, c.y1 - ry2, c.w, c.h), pen,
                            QBrush(Qt.BrushStyle.NoBrush))
                    else:
                        it = self.addLine(0, 0, 0, 0, pen)
                    it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
                    it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
                    self._sym_items.append(it)
                self._push_undo("Paste", before, self._snapshot())
            return

        # Issue 5: mirror (flip horizontally about y-axis) selected graphics
        if key == Qt.Key.Key_M and not ctrl:
            selected = [it for it in self.selectedItems() if it in self._sym_items]
            if selected:
                before = self._snapshot()
                for it in selected:
                    idx = self._sym_items.index(it)
                    cmd = self.sym_cmds[idx]
                    if cmd.kind == "line":
                        cmd.x1, cmd.x2 = -cmd.x1, -cmd.x2
                    elif cmd.kind == "rect":
                        # rect stored as top-left (x1,y1) + size (w,h)
                        cmd.x1 = -(cmd.x1 + cmd.w)
                    elif cmd.kind == "ellipse":
                        # ellipse stored as centre (x1,y1) + size (w,h)
                        cmd.x1 = -cmd.x1
                # Rebuild items from updated cmds
                self._restore_snapshot(self._snapshot())
                self._push_undo("Mirror", before, self._snapshot())
            return

        # Issue 5: arrow-key movement of selected items
        arrow_keys = {
            Qt.Key.Key_Left: (-SUB_GRID, 0),
            Qt.Key.Key_Right: (SUB_GRID, 0),
            Qt.Key.Key_Up: (0, -SUB_GRID),
            Qt.Key.Key_Down: (0, SUB_GRID),
        }
        if key in arrow_keys:
            dx, dy = arrow_keys[key]
            sel_sym = [it for it in self.selectedItems() if it in self._sym_items]
            sel_pins = [it for it in self.selectedItems() if isinstance(it, _PinMarker)]
            if sel_sym or sel_pins:
                before = self._snapshot()
                for it in sel_sym:
                    idx = self._sym_items.index(it)
                    cmd = self.sym_cmds[idx]
                    cmd.x1 += dx
                    cmd.y1 += dy
                    if cmd.kind == "line":
                        cmd.x2 += dx
                        cmd.y2 += dy
                for p in sel_pins:
                    p.setPos(p.pos() + QPointF(dx, dy))
                self._restore_snapshot(self._snapshot())
                self._push_undo("Move", before, self._snapshot())
            return

        super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # Pin placement
    # ------------------------------------------------------------------

    def _place_pin(self, pos: QPointF) -> None:
        # Bug 5: use max(existing_P{n}) + 1 to avoid duplicate pin names
        max_n = 0
        for p in self.pins:
            name = p.pin_name
            if name.startswith("P") and name[1:].isdigit():
                max_n = max(max_n, int(name[1:]))
        marker = _PinMarker(pos, f"P{max_n + 1}")
        self.addItem(marker)
        self.pins.append(marker)

    # ------------------------------------------------------------------
    # Task 2: property label position markers
    # ------------------------------------------------------------------

    def set_ref_marker(self, dx: float, dy: float,
                       on_moved: "object | None" = None) -> None:
        """Place or move the Ref (Basic Property) position marker."""
        if self._ref_marker is None:
            self._ref_marker = _PropertyMarkerItem(
                "⊕ Ref (Basic)", QColor("#c05000"), on_moved
            )
            self.addItem(self._ref_marker)
        self._ref_marker.setPos(dx, dy)

    def set_val_marker(self, dx: float, dy: float,
                       on_moved: "object | None" = None) -> None:
        """Place or move the Val (Extra Property) position marker."""
        if self._val_marker is None:
            self._val_marker = _PropertyMarkerItem(
                "⊕ Val (Extra)", QColor("#007700"), on_moved
            )
            self.addItem(self._val_marker)
        self._val_marker.setPos(dx, dy)

    def set_extra_marker(self, idx: int, label: str, dx: float, dy: float,
                         on_moved: "object | None" = None) -> None:
        """Feature 6: place or move the position marker for an extra property."""
        while len(self._extra_markers) <= idx:
            self._extra_markers.append(None)
        if self._extra_markers[idx] is None:
            m = _PropertyMarkerItem(f"⊕ {label}", QColor("#005588"), on_moved)
            self.addItem(m)
            self._extra_markers[idx] = m
        else:
            self._extra_markers[idx]._on_moved = on_moved
        self._extra_markers[idx].setPos(dx, dy)

    def remove_extra_marker(self, idx: int) -> None:
        """Feature 6: remove the extra property marker at *idx*."""
        if 0 <= idx < len(self._extra_markers):
            m = self._extra_markers[idx]
            if m is not None:
                self.removeItem(m)
            self._extra_markers[idx] = None

    def clear_extra_markers(self) -> None:
        """Feature 6: remove all extra property position markers."""
        for m in self._extra_markers:
            if m is not None:
                self.removeItem(m)
        self._extra_markers.clear()

    def clear_symbol(self) -> None:
        for item in list(self.items()):
            self.removeItem(item)
        self.pins.clear()
        self.sym_cmds.clear()
        self._sym_items.clear()
        self._line_start = None
        self._temp_item = None
        self._poly_points.clear()
        self._poly_segs.clear()
        # Property markers are removed by the clear above; reset references
        self._ref_marker = None
        self._val_marker = None
        self._extra_markers.clear()
        self._draw_origin()

    def load_def(self, udef: UserCompDef) -> None:
        self.clear_symbol()
        for cmd in udef.symbol:
            pen = self._pen_for_cmd(cmd)
            if cmd.kind == "line":
                it = self.addLine(cmd.x1, cmd.y1, cmd.x2, cmd.y2, pen)
            elif cmd.kind == "rect":
                brush = (QBrush(QColor("#333333")) if cmd.filled
                         else QBrush(Qt.BrushStyle.NoBrush))
                it = self.addRect(QRectF(cmd.x1, cmd.y1, cmd.w, cmd.h),
                                  pen, brush)
            elif cmd.kind == "ellipse":
                rx, ry = cmd.w / 2, cmd.h / 2
                brush = (QBrush(QColor("#333333")) if cmd.filled
                         else QBrush(Qt.BrushStyle.NoBrush))
                it = self.addEllipse(
                    QRectF(cmd.x1 - rx, cmd.y1 - ry, cmd.w, cmd.h),
                    pen, brush)
            elif cmd.kind == "polyline":
                # Feature #3: render polyline
                from PyQt6.QtGui import QPainterPath
                pts = cmd.points
                if len(pts) >= 2:
                    path = QPainterPath()
                    path.moveTo(pts[0][0], pts[0][1])
                    for px, py in pts[1:]:
                        path.lineTo(px, py)
                    if cmd.filled and len(pts) >= 3:
                        path.closeSubpath()
                    it = QGraphicsPathItem(path)
                    it.setPen(pen)
                    if cmd.filled and len(pts) >= 3:
                        it.setBrush(QBrush(QColor("#333333")))
                    self.addItem(it)
                else:
                    it = self.addLine(0, 0, 0, 0, pen)
            else:
                it = self.addLine(0, 0, 0, 0, pen)
            it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
            it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
            self._sym_items.append(it)
        self.sym_cmds = list(udef.symbol)
        for p in udef.pins:
            marker = _PinMarker(QPointF(p.x, p.y), p.name)
            self.addItem(marker)
            self.pins.append(marker)


class _PinMarker(QGraphicsEllipseItem):
    """Visible pin marker on the symbol editor canvas.

    Bug 1 fix: the pin-name label is drawn in paint() with a counter-rotation
    so it always appears upright regardless of the canvas view rotation
    (e.g. when V-perspective is active and the view is rotated 90°).

    Bug 4 fix: pin dragging snaps to the main grid (GRID_SIZE) via itemChange.
    """
    def __init__(self, pos: QPointF, name: str) -> None:
        r = 5
        super().__init__(-r, -r, 2 * r, 2 * r)
        self.setPos(pos)
        self.pin_name = name
        self.setPen(QPen(QColor("#2277ee"), 1.5))
        self.setBrush(QBrush(QColor("#aaccff")))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        # Bug 4: enable geometry-change notifications for snapping
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)

    def boundingRect(self) -> QRectF:
        # Extend bounding rect to cover the label text at (r+1, -r).
        r = 5
        return QRectF(-r - 2, -r - 2, 80, r * 2 + 16)

    def paint(self, painter: QPainter, option: object, widget: object = None) -> None:
        import math
        # Draw the ellipse via the parent class
        super().paint(painter, option, widget)
        # Bug 1: counter-rotate the pin-name text so it stays upright
        wt = painter.worldTransform()
        det = wt.m11() * wt.m22() - wt.m12() * wt.m21()
        if det < 0:
            angle_deg = math.degrees(math.atan2(-wt.m12(), -wt.m11()))
        else:
            angle_deg = math.degrees(math.atan2(wt.m12(), wt.m11()))
        r = 5
        painter.save()
        painter.rotate(-angle_deg)
        painter.setPen(QPen(QColor("#0044aa"), 1))
        painter.setFont(QFont("monospace", 6))
        painter.drawText(QPointF(r + 2, 4), self.pin_name)
        painter.restore()

    def itemChange(
        self, change: QGraphicsItem.GraphicsItemChange, value: object
    ) -> object:
        # Bug 4: snap dragged pin positions to the main grid
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            from ..canvas.grid import GRID_SIZE as _GS
            p = value  # type: ignore[assignment]
            sx = round(p.x() / _GS) * _GS  # type: ignore[union-attr]
            sy = round(p.y() / _GS) * _GS  # type: ignore[union-attr]
            return QPointF(sx, sy)
        return super().itemChange(change, value)


class _PropertyMarkerItem(QGraphicsItem):
    """Draggable marker that shows the default position of a label (Ref or Val).

    Task 2: marks Basic Property (ref) and Extra Property (val) positions
    in the component editor drawing area with a special symbol so users can
    see where their labels will appear and drag them to adjust the offset.
    """

    def __init__(
        self,
        label: str,
        color: "QColor",
        on_moved: "object | None" = None,
    ) -> None:
        super().__init__()
        self._label = label
        self._color = color
        self._on_moved = on_moved
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setZValue(50)

    def boundingRect(self) -> "QRectF":
        return QRectF(-10, -10, 70, 22)

    def paint(
        self,
        painter: "QPainter",
        option: "object",
        widget: "object" = None,
    ) -> None:
        import math
        # Draw a distinctive diamond marker + label text
        pen = QPen(self._color, 1.5)
        painter.setPen(pen)
        s = 6
        # Diamond shape
        diamond = QPolygonF([
            QPointF(0, -s), QPointF(s, 0),
            QPointF(0, s), QPointF(-s, 0),
        ])
        painter.setBrush(QBrush(self._color))
        painter.drawPolygon(diamond)
        # Bug 1: counter-rotate the label text so it stays upright
        wt = painter.worldTransform()
        det = wt.m11() * wt.m22() - wt.m12() * wt.m21()
        if det < 0:
            angle_deg = math.degrees(math.atan2(-wt.m12(), -wt.m11()))
        else:
            angle_deg = math.degrees(math.atan2(wt.m12(), wt.m11()))
        painter.save()
        painter.rotate(-angle_deg)
        painter.setPen(QPen(self._color, 1))
        painter.setFont(QFont("monospace", 7))
        painter.drawText(QPointF(s + 3, 4), self._label)
        painter.restore()

    def itemChange(
        self, change: "QGraphicsItem.GraphicsItemChange", value: "object"
    ) -> "object":
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            if self._on_moved is not None:
                p = value  # type: ignore[assignment]
                self._on_moved(p.x(), p.y())  # type: ignore[union-attr]
            # Bug 5 fix: invalidate the whole scene so the old marker position
            # is repainted and the residual shadow is erased immediately.
            scene = self.scene()
            if scene is not None:
                scene.update(scene.sceneRect())
        return super().itemChange(change, value)


# ---------------------------------------------------------------------------
# Issue 7: Zoomable view for the symbol editor canvas
# ---------------------------------------------------------------------------

class _SymView(QGraphicsView):
    """QGraphicsView with Ctrl+wheel zoom for the symbol editor (Issue 7)."""

    _ZOOM_FACTOR = 1.15
    _ZOOM_MIN = 0.1
    _ZOOM_MAX = 10.0

    def __init__(self, scene: QGraphicsScene) -> None:
        super().__init__(scene)
        self._zoom_level: float = 1.0
        self.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )

    def wheelEvent(self, event: Any) -> None:
        mods = event.modifiers()
        if mods & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            factor = self._ZOOM_FACTOR if delta > 0 else 1.0 / self._ZOOM_FACTOR
            new_zoom = self._zoom_level * factor
            if self._ZOOM_MIN <= new_zoom <= self._ZOOM_MAX:
                self.scale(factor, factor)
                self._zoom_level = new_zoom
            event.accept()
        elif mods & Qt.KeyboardModifier.ShiftModifier:
            delta = event.angleDelta().y()
            sb = self.horizontalScrollBar()
            sb.setValue(sb.value() - delta // 2)
            event.accept()
        else:
            super().wheelEvent(event)

    def zoom_level(self) -> float:
        """Return the current zoom level (used by the floating toolbar for canvas rotation)."""
        return self._zoom_level




class _FloatingToolbar(QWidget):
    """Toolbar that floats above the drawing view, visible on hover.

    Each button is labelled with a unicode icon character and a short text.
    The toolbar is positioned in the top-left of the view and is hidden by
    default; it appears when the mouse enters the view and disappears when
    the mouse leaves both the toolbar and the view.
    """

    # (icon char, tooltip, tool-name or action, is_action)
    _BUTTONS: list[tuple[str, str, str, bool]] = [
        ("⬚", "Select (Esc)", "select", False),
        ("╱", "Draw Line", "line", False),
        ("⌇", "Draw Polyline (click=add vertex, right-click or dbl-click=finish)", "polyline", False),
        ("▭", "Draw Rect", "rect", False),
        ("◯", "Draw Ellipse", "ellipse", False),
        ("⊙", "Add Pin", "pin", False),
        ("■", "Toggle Fill (solid shapes)", "fill", True),  # Issue 6
        ("✕", "Clear Canvas", "clear", True),
        ("↩", "Undo (Ctrl+Z)", "undo", True),
        ("↪", "Redo (Ctrl+Y)", "redo", True),
    ]
    # Keys that correspond to actions rather than selectable tools
    _ACTION_KEYS: frozenset[str] = frozenset({"fill", "clear", "undo", "redo"})

    def __init__(self, view: QGraphicsView, scene: "_SymbolScene") -> None:
        super().__init__(view)
        self._scene = scene

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        self._btn_map: dict[str, QPushButton] = {}
        for icon, tip, key, is_action in self._BUTTONS:
            btn = QPushButton(icon)
            btn.setFixedSize(32, 32)
            btn.setToolTip(tip)
            if is_action:
                btn.setStyleSheet(self._inactive_style())
                btn.clicked.connect(
                    lambda _checked, k=key: self._do_action(k)
                )
            else:
                btn.setStyleSheet(self._inactive_style())
                btn.clicked.connect(
                    lambda _checked, k=key: self._select_tool(k)
                )
            layout.addWidget(btn)
            self._btn_map[key] = btn

        self.adjustSize()
        self.hide()

        # Issue 4: connect to scene's tool_changed signal to keep buttons in sync
        scene.tool_changed.connect(self._update_active_tool)
        # Highlight the default "select" tool on startup
        self._update_active_tool("select")

        # Install event filters to track enter/leave on view and its viewport
        view.installEventFilter(self)
        view.viewport().installEventFilter(self)

    @staticmethod
    def _inactive_style() -> str:
        return (
            "QPushButton {"
            "  background: rgba(255,255,255,200);"
            "  border: 1px solid #aaa;"
            "  border-radius: 4px;"
            "  font-size: 14px;"
            "}"
            "QPushButton:hover { background: rgba(200,220,255,220); }"
            "QPushButton:pressed { background: rgba(160,200,255,255); }"
        )

    @staticmethod
    def _active_style() -> str:
        return (
            "QPushButton {"
            "  background: rgba(50,100,220,200);"
            "  border: 2px solid #3355cc;"
            "  border-radius: 4px;"
            "  font-size: 14px;"
            "  color: white;"
            "}"
        )

    def _select_tool(self, tool: str) -> None:
        """Select a tool and update button highlighting."""
        self._scene.set_tool(tool)  # This emits tool_changed → _update_active_tool

    def _update_active_tool(self, tool: str) -> None:
        """Issue 4: highlight the button for the currently active tool."""
        for key, btn in self._btn_map.items():
            if key in self._ACTION_KEYS:
                continue
            btn.setStyleSheet(
                self._active_style() if key == tool else self._inactive_style()
            )

    def _do_action(self, action: str) -> None:
        if action == "clear":
            self._scene.clear_symbol()
        elif action == "undo":
            self._scene._undo_stack.undo()
        elif action == "redo":
            self._scene._undo_stack.redo()
        elif action == "fill":
            # Issue 6: toggle fill mode; update button appearance
            self._scene._fill_mode = not self._scene._fill_mode
            btn = self._btn_map.get("fill")
            if btn:
                if self._scene._fill_mode:
                    btn.setStyleSheet(self._active_style())
                else:
                    btn.setStyleSheet(self._inactive_style())

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Enter:
            self._reposition()
            self.show()
            self.raise_()
        elif event.type() == QEvent.Type.Leave:
            # Only hide if the cursor is not over the toolbar itself
            from PyQt6.QtGui import QCursor
            if not self.geometry().contains(self.parent().mapFromGlobal(QCursor.pos())):  # type: ignore[arg-type]
                self.hide()
        elif event.type() == QEvent.Type.Resize:
            self._reposition()
        return False

    def leaveEvent(self, event: Any) -> None:
        self.hide()
        super().leaveEvent(event)

    def _reposition(self) -> None:
        """Place the toolbar in the top-left corner of the parent view."""
        self.move(8, 8)


# ---------------------------------------------------------------------------
# Main editor dialog
# ---------------------------------------------------------------------------

class UserComponentEditorDialog(QDialog):
    """Dialog to create or edit a user-defined schematic component."""

    def __init__(self, parent: QWidget | None = None,
                 existing: LibEntry | None = None,
                 library_id: str | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(
            "Edit Component" if existing else "Create Component"
        )
        self.resize(1000, 700)
        self._existing = existing
        self._library_id = library_id or PRESET_LIBRARY_ID

        # ── root layout ──────────────────────────────────────────────
        root = QHBoxLayout(self)

        # ── left: canvas ─────────────────────────────────────────────
        left = QVBoxLayout()
        root.addLayout(left, 2)

        lbl = QLabel(
            "Draw symbol (hover the canvas to reveal tool icons).\n"
            "Pins snap to grid. Other shapes snap to sub-grid.\n"
            "⊕ Orange=Ref (Basic), ⊕ Green=Val (Value), ⊕ Blue=Extra Property positions.\n"
            "H/V toggle (right panel) switches between horizontal/vertical perspective markers.\n"
            "Keys: Del=delete  Ctrl+C/V=copy/paste  M=mirror  Arrows=move  "
            "Ctrl+Z/Y=undo/redo  Right-click=cancel drawing."
        )
        lbl.setWordWrap(True)
        left.addWidget(lbl)

        # Canvas wrapped in a container so the floating toolbar can overlay it
        self._canvas_container = QWidget()
        self._canvas_container.setMinimumSize(400, 400)
        canvas_layout = QVBoxLayout(self._canvas_container)
        canvas_layout.setContentsMargins(0, 0, 0, 0)

        self._sym_scene = _SymbolScene()
        self._sym_view = _SymView(self._sym_scene)
        self._sym_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._sym_view.setMouseTracking(True)
        self._sym_view.viewport().setMouseTracking(True)
        # Ensure the view can receive keyboard focus for shortcuts (Issues 5/6)
        self._sym_view.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        canvas_layout.addWidget(self._sym_view)
        left.addWidget(self._canvas_container, 1)

        # Issue 8: Floating icon toolbar (shows on hover)
        self._float_toolbar = _FloatingToolbar(
            self._sym_view, self._sym_scene
        )
        line_row = QHBoxLayout()
        line_row.addWidget(QLabel("Line style:"))
        self._line_style_combo = QComboBox()
        self._line_style_combo.addItems(
            ["solid", "dash", "dot", "dash_dot", "dash_dot_dot"]
        )
        line_row.addWidget(self._line_style_combo)
        line_row.addWidget(QLabel("Width:"))
        self._line_width_spin = QDoubleSpinBox()
        self._line_width_spin.setRange(0.5, 12.0)
        self._line_width_spin.setSingleStep(0.5)
        line_row.addWidget(self._line_width_spin)
        self._line_apply_btn = QPushButton("Apply to Selection")
        self._line_apply_btn.clicked.connect(self._apply_symbol_line_style)
        line_row.addWidget(self._line_apply_btn)
        line_row.addStretch()
        left.addLayout(line_row)
        self._line_style_combo.setCurrentText(self._sym_scene._line_style_name)
        self._line_width_spin.setValue(self._sym_scene._line_width)

        # ── right: properties panel ───────────────────────────────────
        right = QVBoxLayout()
        root.addLayout(right, 1)

        form_box = QGroupBox("Component Properties")
        form = QFormLayout(form_box)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g. MY_COMP")
        form.addRow("Type name:", self._name_edit)

        self._display_edit = QLineEdit()
        self._display_edit.setPlaceholderText("e.g. My Component")
        form.addRow("Display name:", self._display_edit)

        self._cat_edit = QLineEdit("User")
        form.addRow("Category:", self._cat_edit)

        self._desc_edit = QLineEdit()
        form.addRow("Description:", self._desc_edit)

        self._prefix_edit = QLineEdit("U")
        form.addRow("Ref prefix:", self._prefix_edit)

        self._value_edit = QLineEdit()
        form.addRow("Default value:", self._value_edit)

        # Bug 2: virtual component type
        self._virtual_cb = QCheckBox(
            "Virtual component (wiring helper, no SPICE element)")
        self._virtual_cb.setToolTip(
            "Check to make this a virtual (non-SPICE) component,\n"
            "e.g. wire bends, T-junctions you draw yourself."
        )
        form.addRow("", self._virtual_cb)

        right.addWidget(form_box)

        # Fix 8: Label position defaults with perspective support (Feature 8)
        self._label_pos_box = QGroupBox("Default Label Positions & Styles")
        label_pos_box = self._label_pos_box
        label_pos_form = QFormLayout(label_pos_box)

        # Feature 8: perspective toggle (H = normal, V = rotated 90°)
        from PyQt6.QtWidgets import QRadioButton, QButtonGroup, QSpinBox
        persp_row = QHBoxLayout()
        persp_row.addWidget(QLabel("Canvas markers perspective:"))
        self._persp_h_rb = QRadioButton("Horizontal (H)")
        self._persp_v_rb = QRadioButton("Vertical / Rotated (V)")
        self._persp_h_rb.setChecked(True)
        self._persp_h_rb.setToolTip("Show position markers for the normal (unrotated) view")
        self._persp_v_rb.setToolTip("Show position markers for the vertical (rotated 90°) view")
        self._persp_group = QButtonGroup(self)
        self._persp_group.addButton(self._persp_h_rb)
        self._persp_group.addButton(self._persp_v_rb)
        persp_row.addWidget(self._persp_h_rb)
        persp_row.addWidget(self._persp_v_rb)
        label_pos_form.addRow(persp_row)

        def _make_dspin(val: float) -> QDoubleSpinBox:
            s = QDoubleSpinBox()
            s.setRange(-500.0, 500.0)
            s.setSingleStep(1.0)
            s.setDecimals(1)
            s.setValue(val)
            return s

        def _make_ispin(val: int) -> QSpinBox:
            s = QSpinBox()
            s.setRange(0, 72)
            s.setValue(val)
            return s

        # ── Ref label ──
        ref_h_row = QHBoxLayout()
        self._ref_dx_spin = _make_dspin(0.0)
        self._ref_dy_spin = _make_dspin(-22.0)
        ref_h_row.addWidget(QLabel("H  dx:")); ref_h_row.addWidget(self._ref_dx_spin)
        ref_h_row.addWidget(QLabel("dy:")); ref_h_row.addWidget(self._ref_dy_spin)
        label_pos_form.addRow("Ref label pos:", ref_h_row)

        ref_v_row = QHBoxLayout()
        self._ref_dx_v_spin = _make_dspin(0.0)
        self._ref_dy_v_spin = _make_dspin(-22.0)
        ref_v_row.addWidget(QLabel("V  dx:")); ref_v_row.addWidget(self._ref_dx_v_spin)
        ref_v_row.addWidget(QLabel("dy:")); ref_v_row.addWidget(self._ref_dy_v_spin)
        label_pos_form.addRow("", ref_v_row)

        # Feature 7: Ref label style
        ref_style_row = QHBoxLayout()
        self._ref_font_family_edit = QLineEdit("")
        self._ref_font_family_edit.setPlaceholderText("font (blank=default)")
        self._ref_font_family_edit.setMaximumWidth(110)
        self._ref_font_size_spin = _make_ispin(0)
        self._ref_font_size_spin.setToolTip("0=default size")
        self._ref_font_size_spin.setMaximumWidth(50)
        self._ref_bold_cb = QCheckBox("B")
        self._ref_bold_cb.setToolTip("Bold")
        self._ref_italic_cb = QCheckBox("I")
        self._ref_italic_cb.setToolTip("Italic")
        self._ref_color_edit = QLineEdit("")
        self._ref_color_edit.setPlaceholderText("#rrggbb")
        self._ref_color_edit.setMaximumWidth(75)
        self._ref_align_combo = QComboBox()
        for _a in ("left", "center", "right"):
            self._ref_align_combo.addItem(_a)
        ref_style_row.addWidget(QLabel("Style:"))
        ref_style_row.addWidget(self._ref_font_family_edit)
        ref_style_row.addWidget(self._ref_font_size_spin)
        ref_style_row.addWidget(self._ref_bold_cb)
        ref_style_row.addWidget(self._ref_italic_cb)
        ref_style_row.addWidget(self._ref_color_edit)
        ref_style_row.addWidget(self._ref_align_combo)
        label_pos_form.addRow("Ref style:", ref_style_row)

        # ── Val label ──
        val_h_row = QHBoxLayout()
        self._val_dx_spin = _make_dspin(0.0)
        self._val_dy_spin = _make_dspin(14.0)
        val_h_row.addWidget(QLabel("H  dx:")); val_h_row.addWidget(self._val_dx_spin)
        val_h_row.addWidget(QLabel("dy:")); val_h_row.addWidget(self._val_dy_spin)
        label_pos_form.addRow("Val label pos:", val_h_row)

        val_v_row = QHBoxLayout()
        self._val_dx_v_spin = _make_dspin(0.0)
        self._val_dy_v_spin = _make_dspin(14.0)
        val_v_row.addWidget(QLabel("V  dx:")); val_v_row.addWidget(self._val_dx_v_spin)
        val_v_row.addWidget(QLabel("dy:")); val_v_row.addWidget(self._val_dy_v_spin)
        label_pos_form.addRow("", val_v_row)

        # Feature 7: Val label style
        val_style_row = QHBoxLayout()
        self._val_font_family_edit = QLineEdit("")
        self._val_font_family_edit.setPlaceholderText("font (blank=default)")
        self._val_font_family_edit.setMaximumWidth(110)
        self._val_font_size_spin = _make_ispin(0)
        self._val_font_size_spin.setToolTip("0=default size")
        self._val_font_size_spin.setMaximumWidth(50)
        self._val_bold_cb = QCheckBox("B")
        self._val_bold_cb.setToolTip("Bold")
        self._val_italic_cb = QCheckBox("I")
        self._val_italic_cb.setToolTip("Italic")
        self._val_color_edit = QLineEdit("")
        self._val_color_edit.setPlaceholderText("#rrggbb")
        self._val_color_edit.setMaximumWidth(75)
        self._val_align_combo = QComboBox()
        for _a in ("left", "center", "right"):
            self._val_align_combo.addItem(_a)
        val_style_row.addWidget(QLabel("Style:"))
        val_style_row.addWidget(self._val_font_family_edit)
        val_style_row.addWidget(self._val_font_size_spin)
        val_style_row.addWidget(self._val_bold_cb)
        val_style_row.addWidget(self._val_italic_cb)
        val_style_row.addWidget(self._val_color_edit)
        val_style_row.addWidget(self._val_align_combo)

        label_pos_form.addRow("Val style:", val_style_row)

        right.addWidget(label_pos_box)

        # Pin list (from scene)
        pin_box = QGroupBox("Pin names (edit name in list, position on canvas)")
        pin_layout = QVBoxLayout(pin_box)
        self._pin_list = QListWidget()
        self._pin_list.setToolTip("Double-click to rename a pin")
        self._pin_list.itemDoubleClicked.connect(self._rename_pin)
        pin_layout.addWidget(self._pin_list)

        refresh_btn = QPushButton("Refresh pin list from canvas")
        refresh_btn.clicked.connect(self._refresh_pin_list)
        pin_layout.addWidget(refresh_btn)

        right.addWidget(pin_box)

        # ── Issue 12: Extra Properties section (renamed from Extra Labels) ──
        self._label_box = QGroupBox("Extra Properties (beyond Ref/Value)")
        label_box = self._label_box
        label_layout = QVBoxLayout(label_box)
        self._label_list = QListWidget()
        self._label_list.setToolTip(
            "Extra properties attached to this component.\n"
            "Each entry: <name>  [<side>  order=<n>  default=<value>]\n"
            "The property VALUE (not name) is displayed next to the component."
        )
        label_layout.addWidget(self._label_list)

        label_btn_row = QHBoxLayout()
        add_lbl_btn = QPushButton("Add Property…")
        add_lbl_btn.clicked.connect(self._add_label)
        edit_lbl_btn = QPushButton("Edit…")
        edit_lbl_btn.clicked.connect(self._edit_label)
        del_lbl_btn = QPushButton("Remove")
        del_lbl_btn.clicked.connect(self._remove_label)
        for b in (add_lbl_btn, edit_lbl_btn, del_lbl_btn):
            label_btn_row.addWidget(b)
        label_layout.addLayout(label_btn_row)

        right.addWidget(label_box)
        right.addStretch()

        # OK / Cancel
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        right.addWidget(buttons)

        # ── internal label data model ─────────────────────────────────
        self._label_defs: list[LabelDef] = []

        # ── pre-fill if editing ───────────────────────────────────────
        if existing:
            self._name_edit.setText(existing.type_name)
            self._display_edit.setText(existing.display_name)
            self._cat_edit.setText(existing.category)
            self._desc_edit.setText(existing.description)
            self._prefix_edit.setText(existing.ref_prefix)
            self._value_edit.setText(existing.default_value)
            # Fix 3: virtual flag
            self._virtual_cb.setChecked(getattr(existing, "is_virtual", False))
            # Fix 8: label position defaults (H perspective)
            ref_off = getattr(existing, "ref_label_offset", [0.0, -22.0])
            val_off = getattr(existing, "val_label_offset", [0.0, 14.0])
            self._ref_dx_spin.setValue(ref_off[0] if ref_off else 0.0)
            self._ref_dy_spin.setValue(ref_off[1] if len(ref_off) > 1 else -22.0)
            self._val_dx_spin.setValue(val_off[0] if val_off else 0.0)
            self._val_dy_spin.setValue(val_off[1] if len(val_off) > 1 else 14.0)
            # Feature 8: V-perspective offsets (fall back to H if not set)
            ref_off_v = getattr(existing, "ref_label_offset_v", []) or ref_off
            val_off_v = getattr(existing, "val_label_offset_v", []) or val_off
            self._ref_dx_v_spin.setValue(ref_off_v[0] if ref_off_v else 0.0)
            self._ref_dy_v_spin.setValue(ref_off_v[1] if len(ref_off_v) > 1 else -22.0)
            self._val_dx_v_spin.setValue(val_off_v[0] if val_off_v else 0.0)
            self._val_dy_v_spin.setValue(val_off_v[1] if len(val_off_v) > 1 else 14.0)
            # Feature 7: pre-fill ref style
            ref_style = getattr(existing, "ref_label_style", {}) or {}
            self._ref_font_family_edit.setText(ref_style.get("font_family", ""))
            self._ref_font_size_spin.setValue(int(ref_style.get("font_size", 0)))
            self._ref_bold_cb.setChecked(bool(ref_style.get("bold", False)))
            self._ref_italic_cb.setChecked(bool(ref_style.get("italic", False)))
            self._ref_color_edit.setText(ref_style.get("color", ""))
            ref_align = ref_style.get("alignment", "left")
            self._ref_align_combo.setCurrentIndex(
                max(0, self._ref_align_combo.findText(ref_align)))
            # Feature 7: pre-fill val style
            val_style = getattr(existing, "val_label_style", {}) or {}
            self._val_font_family_edit.setText(val_style.get("font_family", ""))
            self._val_font_size_spin.setValue(int(val_style.get("font_size", 0)))
            self._val_bold_cb.setChecked(bool(val_style.get("bold", False)))
            self._val_italic_cb.setChecked(bool(val_style.get("italic", False)))
            self._val_color_edit.setText(val_style.get("color", ""))
            val_align = val_style.get("alignment", "left")
            self._val_align_combo.setCurrentIndex(
                max(0, self._val_align_combo.findText(val_align)))
            if not existing.is_builtin:
                # Load custom symbol only for user-defined entries
                _sym_udef = UserCompDef(
                    type_name=existing.type_name,
                    display_name=existing.display_name,
                    category=existing.category,
                    description=existing.description,
                    ref_prefix=existing.ref_prefix,
                    default_value=existing.default_value,
                    pins=[PinDef(**p) for p in existing.pins],
                    symbol=[
                        SymbolCmd(
                            kind=s.get("kind", "line") if isinstance(s, dict) else s.kind,
                            x1=s.get("x1", 0.0) if isinstance(s, dict) else s.x1,
                            y1=s.get("y1", 0.0) if isinstance(s, dict) else s.y1,
                            x2=s.get("x2", 0.0) if isinstance(s, dict) else s.x2,
                            y2=s.get("y2", 0.0) if isinstance(s, dict) else s.y2,
                            w=s.get("w", 0.0) if isinstance(s, dict) else s.w,
                            h=s.get("h", 0.0) if isinstance(s, dict) else s.h,
                            text=s.get("text", "") if isinstance(s, dict) else s.text,
                            filled=s.get("filled", False) if isinstance(s, dict) else s.filled,
                            # Bug 2 fix: include points so polylines are preserved on re-edit
                            points=s.get("points", []) if isinstance(s, dict) else s.points,
                        )
                        for s in existing.symbol
                    ],
                )
                self._sym_scene.load_def(_sym_udef)
            else:
                # Issue 1: For built-in components, show actual rendered preview
                self._load_builtin_preview(existing)
            # Populate existing extra properties
            for lbl_dict in existing.labels:
                if isinstance(lbl_dict, dict):
                    ldef = LabelDef(
                        text=lbl_dict.get("text", ""),
                        side=lbl_dict.get("side", "top"),
                        order=lbl_dict.get("order", 0),
                        default_value=lbl_dict.get("default_value", ""),
                        dx=lbl_dict.get("dx", 0.0),
                        dy=lbl_dict.get("dy", 0.0),
                        dx_v=lbl_dict.get("dx_v", 0.0),
                        dy_v=lbl_dict.get("dy_v", 0.0),
                        font_family=lbl_dict.get("font_family", ""),
                        font_size=lbl_dict.get("font_size", 0),
                        bold=lbl_dict.get("bold", False),
                        italic=lbl_dict.get("italic", False),
                        color=lbl_dict.get("color", ""),
                        alignment=lbl_dict.get("alignment", "left"),
                        use_offset=lbl_dict.get("use_offset", False),
                    )
                else:
                    ldef = lbl_dict
                self._label_defs.append(ldef)
            self._refresh_label_list()
            self._refresh_pin_list()

        # Task 2: initialize property markers in the drawing area
        # These markers show where Ref (Basic Property) and Val (Extra Property)
        # labels will appear relative to the component origin.
        self._init_property_markers()

        # Connect spin boxes to update markers when values change
        self._ref_dx_spin.valueChanged.connect(self._sync_ref_marker_from_spins)
        self._ref_dy_spin.valueChanged.connect(self._sync_ref_marker_from_spins)
        self._val_dx_spin.valueChanged.connect(self._sync_val_marker_from_spins)
        self._val_dy_spin.valueChanged.connect(self._sync_val_marker_from_spins)
        self._ref_dx_v_spin.valueChanged.connect(self._sync_ref_marker_from_spins)
        self._ref_dy_v_spin.valueChanged.connect(self._sync_ref_marker_from_spins)
        self._val_dx_v_spin.valueChanged.connect(self._sync_val_marker_from_spins)
        self._val_dy_v_spin.valueChanged.connect(self._sync_val_marker_from_spins)
        # Feature 8: perspective toggle
        self._persp_h_rb.toggled.connect(self._on_perspective_changed)
        self._persp_v_rb.toggled.connect(self._on_perspective_changed)
        # Bug 2: disable label settings when virtual component is checked
        self._virtual_cb.stateChanged.connect(self._on_virtual_changed)
        # Apply initial state in case existing component is virtual
        if existing and getattr(existing, "is_virtual", False):
            self._on_virtual_changed(True)

    def _on_virtual_changed(self, state: object) -> None:
        """Bug 2: disable label settings when 'Virtual Component' is checked."""
        is_virtual = bool(self._virtual_cb.isChecked())
        self._label_pos_box.setEnabled(not is_virtual)
        self._label_box.setEnabled(not is_virtual)

    def _is_v_perspective(self) -> bool:
        """Feature 8: return True if the vertical (rotated) perspective is active."""
        return self._persp_v_rb.isChecked()

    def _init_property_markers(self) -> None:
        """Task 2 / Feature 6/8: place property-position markers on the symbol canvas."""
        if self._is_v_perspective():
            rdx, rdy = self._ref_dx_v_spin.value(), self._ref_dy_v_spin.value()
            vdx, vdy = self._val_dx_v_spin.value(), self._val_dy_v_spin.value()
        else:
            rdx, rdy = self._ref_dx_spin.value(), self._ref_dy_spin.value()
            vdx, vdy = self._val_dx_spin.value(), self._val_dy_spin.value()
        self._sym_scene.set_ref_marker(rdx, rdy, self._on_ref_marker_moved)
        self._sym_scene.set_val_marker(vdx, vdy, self._on_val_marker_moved)
        # Feature 6: extra property markers
        self._sync_extra_markers()

    def _on_perspective_changed(self, checked: bool) -> None:
        """Feature 8: switch the canvas markers to show H or V perspective.
        Bug 1 fix: also rotate the canvas view 90° when V perspective is active."""
        if not checked:
            return
        # Move markers to the position for the newly selected perspective
        self._sync_ref_marker_from_spins()
        self._sync_val_marker_from_spins()
        self._sync_extra_markers()
        # Bug 1: rotate the canvas to show what the component looks like in this orientation
        self._update_canvas_rotation()

    def _update_canvas_rotation(self) -> None:
        """Bug 1 fix: rotate the symbol editor view 90° for V perspective, 0° for H.

        The current zoom level is preserved across the perspective switch by
        re-applying ``zoom_level()`` after resetting the transform.
        """
        view = self._sym_view
        zoom = view.zoom_level()
        view.resetTransform()
        view.scale(zoom, zoom)
        if self._is_v_perspective():
            view.rotate(90.0)

    def _sync_ref_marker_from_spins(self) -> None:
        """Move the Ref marker when the spin boxes change."""
        if self._is_v_perspective():
            dx, dy = self._ref_dx_v_spin.value(), self._ref_dy_v_spin.value()
        else:
            dx, dy = self._ref_dx_spin.value(), self._ref_dy_spin.value()
        if self._sym_scene._ref_marker is not None:
            self._sym_scene._ref_marker.setPos(dx, dy)

    def _sync_val_marker_from_spins(self) -> None:
        """Move the Val marker when the spin boxes change."""
        if self._is_v_perspective():
            dx, dy = self._val_dx_v_spin.value(), self._val_dy_v_spin.value()
        else:
            dx, dy = self._val_dx_spin.value(), self._val_dy_spin.value()
        if self._sym_scene._val_marker is not None:
            self._sym_scene._val_marker.setPos(dx, dy)

    def _sync_extra_markers(self) -> None:
        """Feature 6/8: create/update extra property markers for all label_defs."""
        is_v = self._is_v_perspective()
        # Remove markers that are no longer needed
        for idx in range(len(self._label_defs), len(self._sym_scene._extra_markers)):
            self._sym_scene.remove_extra_marker(idx)
        # Create/update markers for each label_def
        for idx, ldef in enumerate(self._label_defs):
            dx = ldef.dx_v if is_v else ldef.dx
            dy = ldef.dy_v if is_v else ldef.dy
            self._sym_scene.set_extra_marker(
                idx, ldef.text, dx, dy,
                lambda x, y, i=idx: self._on_extra_marker_moved(i, x, y)
            )

    def _on_extra_marker_moved(self, idx: int, x: float, y: float) -> None:
        """Feature 6/8: update LabelDef when an extra property marker is dragged."""
        if 0 <= idx < len(self._label_defs):
            ld = self._label_defs[idx]
            if self._is_v_perspective():
                ld.dx_v = x
                ld.dy_v = y
            else:
                ld.dx = x
                ld.dy = y
            ld.use_offset = True

    def _on_ref_marker_moved(self, x: float, y: float) -> None:
        """Update spin boxes when the Ref marker is dragged."""
        if self._is_v_perspective():
            self._ref_dx_v_spin.blockSignals(True)
            self._ref_dy_v_spin.blockSignals(True)
            self._ref_dx_v_spin.setValue(x)
            self._ref_dy_v_spin.setValue(y)
            self._ref_dx_v_spin.blockSignals(False)
            self._ref_dy_v_spin.blockSignals(False)
        else:
            self._ref_dx_spin.blockSignals(True)
            self._ref_dy_spin.blockSignals(True)
            self._ref_dx_spin.setValue(x)
            self._ref_dy_spin.setValue(y)
            self._ref_dx_spin.blockSignals(False)
            self._ref_dy_spin.blockSignals(False)

    def _on_val_marker_moved(self, x: float, y: float) -> None:
        """Update spin boxes when the Val marker is dragged."""
        if self._is_v_perspective():
            self._val_dx_v_spin.blockSignals(True)
            self._val_dy_v_spin.blockSignals(True)
            self._val_dx_v_spin.setValue(x)
            self._val_dy_v_spin.setValue(y)
            self._val_dx_v_spin.blockSignals(False)
            self._val_dy_v_spin.blockSignals(False)
        else:
            self._val_dx_spin.blockSignals(True)
            self._val_dy_spin.blockSignals(True)
            self._val_dx_spin.setValue(x)
            self._val_dy_spin.setValue(y)
            self._val_dx_spin.blockSignals(False)
            self._val_dy_spin.blockSignals(False)

    # ------------------------------------------------------------------
    # Issue 1: built-in component preview
    # ------------------------------------------------------------------
        """Show the actual rendered component in the symbol scene (read-only)."""
        try:
            from ..canvas.scene import create_component_item
            item = create_component_item(
                entry.type_name,
                ref=entry.ref_prefix + "?",
                value=entry.default_value,
                library_id=PRESET_LIBRARY_ID,
            )
            if item is None:
                return
            # Make the preview non-interactive
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, False)
            item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            item.setOpacity(0.85)
            self._sym_scene.addItem(item)
            # Bug #9: show connection points (pins) in the preview
            item.show_pins(True)
            # Centre the view on the item
            self._sym_view.centerOn(item)
        except Exception:
            pass  # preview is best-effort

    # ------------------------------------------------------------------

    def _refresh_pin_list(self) -> None:
        self._pin_list.clear()
        for marker in self._sym_scene.pins:
            self._pin_list.addItem(marker.pin_name)

    def _rename_pin(self, item: Any) -> None:
        row = self._pin_list.row(item)
        if 0 <= row < len(self._sym_scene.pins):
            marker = self._sym_scene.pins[row]
            new_name, ok = QInputDialog.getText(
                self, "Rename Pin", "Pin name:", text=marker.pin_name)
            if ok and new_name.strip():
                marker.pin_name = new_name.strip()
                item.setText(new_name.strip())
                for child in marker.childItems():
                    if isinstance(child, QGraphicsTextItem):
                        child.setPlainText(new_name.strip())

    # ------------------------------------------------------------------
    # Issue 6: Extra label management
    # ------------------------------------------------------------------

    def _refresh_label_list(self) -> None:
        self._label_list.clear()
        for ld in self._label_defs:
            style_parts = []
            if ld.font_family:
                style_parts.append(ld.font_family)
            if ld.font_size:
                style_parts.append(f"{ld.font_size}pt")
            if ld.bold:
                style_parts.append("B")
            if ld.italic:
                style_parts.append("I")
            if ld.color:
                style_parts.append(ld.color)
            style_str = f"  style={','.join(style_parts)}" if style_parts else ""
            offset_str = (f"  pos=({ld.dx:.0f},{ld.dy:.0f})"
                          if ld.use_offset else "")
            self._label_list.addItem(
                f"{ld.text!r}  [{ld.side}  order={ld.order}"
                + (f"  default={ld.default_value!r}" if ld.default_value else "")
                + style_str + offset_str + "]"
            )

    def _add_label(self) -> None:
        dlg = _LabelEditDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._label_defs.append(dlg.label_def())
            self._refresh_label_list()
            self._sync_extra_markers()

    def _edit_label(self) -> None:
        row = self._label_list.currentRow()
        if 0 <= row < len(self._label_defs):
            dlg = _LabelEditDialog(self, self._label_defs[row])
            if dlg.exec() == QDialog.DialogCode.Accepted:
                updated = dlg.label_def()
                # Preserve the position data (dx/dy) set via canvas markers
                old = self._label_defs[row]
                updated.dx = old.dx
                updated.dy = old.dy
                updated.dx_v = old.dx_v
                updated.dy_v = old.dy_v
                updated.use_offset = old.use_offset
                self._label_defs[row] = updated
                self._refresh_label_list()
                self._sync_extra_markers()

    def _remove_label(self) -> None:
        row = self._label_list.currentRow()
        if 0 <= row < len(self._label_defs):
            self._sym_scene.remove_extra_marker(row)
            self._sym_scene._extra_markers.pop(row)
            self._label_defs.pop(row)
            self._refresh_label_list()
            self._sync_extra_markers()

    # ------------------------------------------------------------------

    def _apply_symbol_line_style(self) -> None:
        style = self._line_style_combo.currentText()
        width = float(self._line_width_spin.value())
        self._sym_scene.set_line_style(style, width)
        self._sym_scene.apply_line_style_to_selected(style, width)

    def _on_accept(self) -> None:
        type_name = self._name_edit.text().strip()
        display = self._display_edit.text().strip() or type_name
        if not type_name:
            QMessageBox.warning(self, "Validation", "Type name is required.")
            return

        pins_pos = []
        for marker in self._sym_scene.pins:
            pins_pos.append({
                "name": marker.pin_name,
                "x": marker.pos().x(),
                "y": marker.pos().y(),
            })

        # Preserve is_builtin if editing a built-in component (only meta changes)
        is_builtin = False
        if self._existing is not None:
            is_builtin = self._existing.is_builtin

        # Issue 12: include all LabelDef fields in label serialisation
        # Feature 6: include dx/dy offsets and use_offset
        # Feature 7: include style fields
        # Feature 8: include V-perspective offsets
        labels_data = [
            {
                "text": ld.text,
                "side": ld.side,
                "order": ld.order,
                "default_value": ld.default_value,
                "dx": ld.dx,
                "dy": ld.dy,
                "dx_v": ld.dx_v,
                "dy_v": ld.dy_v,
                "font_family": ld.font_family,
                "font_size": ld.font_size,
                "bold": ld.bold,
                "italic": ld.italic,
                "color": ld.color,
                "alignment": ld.alignment,
                "use_offset": ld.use_offset,
            }
            for ld in self._label_defs
        ]

        entry = LibEntry(
            type_name=type_name,
            display_name=display,
            category=self._cat_edit.text().strip() or "User",
            description=self._desc_edit.text().strip(),
            ref_prefix=self._prefix_edit.text().strip() or "U",
            default_value=self._value_edit.text().strip(),
            pin_names=[p["name"] for p in pins_pos] if is_builtin else [],
            pins=pins_pos if not is_builtin else [],
            symbol=[s.__dict__ for s in self._sym_scene.sym_cmds] if not is_builtin else [],
            is_builtin=is_builtin,
            labels=labels_data,
            # Fix 3: virtual flag
            is_virtual=self._virtual_cb.isChecked(),
            # Fix 8: label position defaults (H perspective)
            ref_label_offset=[
                self._ref_dx_spin.value(), self._ref_dy_spin.value()
            ],
            val_label_offset=[
                self._val_dx_spin.value(), self._val_dy_spin.value()
            ],
            # Feature 8: V-perspective offsets
            ref_label_offset_v=[
                self._ref_dx_v_spin.value(), self._ref_dy_v_spin.value()
            ],
            val_label_offset_v=[
                self._val_dx_v_spin.value(), self._val_dy_v_spin.value()
            ],
            # Feature 7: ref/val label styles
            ref_label_style={
                "font_family": self._ref_font_family_edit.text().strip(),
                "font_size": self._ref_font_size_spin.value(),
                "bold": self._ref_bold_cb.isChecked(),
                "italic": self._ref_italic_cb.isChecked(),
                "color": self._ref_color_edit.text().strip(),
                "alignment": self._ref_align_combo.currentText(),
            },
            val_label_style={
                "font_family": self._val_font_family_edit.text().strip(),
                "font_size": self._val_font_size_spin.value(),
                "bold": self._val_bold_cb.isChecked(),
                "italic": self._val_italic_cb.isChecked(),
                "color": self._val_color_edit.text().strip(),
                "alignment": self._val_align_combo.currentText(),
            },
        )

        lm = LibraryManager()
        # Issue 5: if the type_name was changed during edit, delete the old entry
        # first so we don't leave a stale entry in the library.
        if (self._existing is not None
                and self._existing.type_name != type_name):
            lm.delete_entry(self._library_id, self._existing.type_name)

        lm.save_entry(self._library_id, entry)

        self.accept()


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Extra-property definition editor dialog (Issue 12: renamed from LabelEditDialog)
# ---------------------------------------------------------------------------

class _LabelEditDialog(QDialog):
    """Small dialog for adding or editing an extra-property definition.

    Issue 12: renamed to 'Extra Property'.  Each property has:
    - Property name: the key stored in the component's params dict.
    - Default value: displayed next to the component when no instance
      value has been set.
    - Side and order: layout position.
    Feature 7: per-label font, size, bold, italic, color, alignment.
    Feature 6: use_offset flag enables explicit dx/dy positioning.
    """

    def __init__(self, parent: QWidget | None = None,
                 ldef: LabelDef | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Extra Property Definition")
        layout = QFormLayout(self)

        self._text_edit = QLineEdit(ldef.text if ldef else "")
        layout.addRow("Property name:", self._text_edit)

        # Issue 12: default value field
        self._default_edit = QLineEdit(
            ldef.default_value if (ldef and ldef.default_value) else "")
        layout.addRow("Default value:", self._default_edit)

        self._side_combo = QComboBox()
        for s in ("top", "bottom", "left", "right"):
            self._side_combo.addItem(s)
        if ldef:
            idx = self._side_combo.findText(ldef.side)
            if idx >= 0:
                self._side_combo.setCurrentIndex(idx)
        layout.addRow("Side (auto layout):", self._side_combo)

        self._order_edit = QLineEdit(str(ldef.order) if ldef else "0")
        layout.addRow("Order (0 = first):", self._order_edit)

        # Feature 7: per-label style
        from PyQt6.QtWidgets import QSpinBox
        self._font_family_edit = QLineEdit(
            ldef.font_family if (ldef and ldef.font_family) else "")
        self._font_family_edit.setPlaceholderText("blank = app default")
        layout.addRow("Font family:", self._font_family_edit)

        self._font_size_spin = QSpinBox()
        self._font_size_spin.setRange(0, 72)
        self._font_size_spin.setValue(ldef.font_size if ldef else 0)
        self._font_size_spin.setToolTip("0 = application default font size")
        layout.addRow("Font size (0=default):", self._font_size_spin)

        self._bold_cb = QCheckBox()
        self._bold_cb.setChecked(ldef.bold if ldef else False)
        layout.addRow("Bold:", self._bold_cb)

        self._italic_cb = QCheckBox()
        self._italic_cb.setChecked(ldef.italic if ldef else False)
        layout.addRow("Italic:", self._italic_cb)

        self._color_edit = QLineEdit(
            ldef.color if (ldef and ldef.color) else "")
        self._color_edit.setPlaceholderText("#rrggbb or blank = component color")
        layout.addRow("Color:", self._color_edit)

        self._align_combo = QComboBox()
        for a in ("left", "center", "right"):
            self._align_combo.addItem(a)
        if ldef:
            idx = self._align_combo.findText(ldef.alignment)
            if idx >= 0:
                self._align_combo.setCurrentIndex(idx)
        layout.addRow("Alignment:", self._align_combo)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

    def label_def(self) -> LabelDef:
        try:
            order = int(self._order_edit.text().strip())
        except ValueError:
            order = 0
        return LabelDef(
            text=self._text_edit.text().strip(),
            side=self._side_combo.currentText(),
            order=order,
            default_value=self._default_edit.text().strip(),
            font_family=self._font_family_edit.text().strip(),
            font_size=self._font_size_spin.value(),
            bold=self._bold_cb.isChecked(),
            italic=self._italic_cb.isChecked(),
            color=self._color_edit.text().strip(),
            alignment=self._align_combo.currentText(),
        )


# ---------------------------------------------------------------------------
# Multi-library manager dialog
# ---------------------------------------------------------------------------

class LibraryManagerDialog(QDialog):
    """Manage all component libraries: add/remove libraries, add/edit/delete
    components within any library (including the preset library).
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Component Library Manager")
        self.resize(800, 500)

        root = QHBoxLayout(self)

        # ── Left: library list ────────────────────────────────────────
        left = QVBoxLayout()
        root.addLayout(left, 1)

        left.addWidget(QLabel("Libraries:"))
        self._lib_list = QListWidget()
        self._lib_list.currentRowChanged.connect(self._on_lib_selected)
        left.addWidget(self._lib_list)

        lib_btns = QHBoxLayout()
        self._add_lib_btn = QPushButton("Add Library")
        self._add_lib_btn.clicked.connect(self._add_library)
        self._del_lib_btn = QPushButton("Delete Library")
        self._del_lib_btn.clicked.connect(self._delete_library)
        self._ren_lib_btn = QPushButton("Rename…")
        self._ren_lib_btn.clicked.connect(self._rename_library)
        for b in (self._add_lib_btn, self._del_lib_btn, self._ren_lib_btn):
            lib_btns.addWidget(b)
        left.addLayout(lib_btns)

        # Feature #5: Export / Import library buttons
        io_btns = QHBoxLayout()
        self._export_btn = QPushButton("Export…")
        self._export_btn.setToolTip("Export the selected library to a JSON file")
        self._export_btn.clicked.connect(self._export_library)
        self._import_btn = QPushButton("Import…")
        self._import_btn.setToolTip("Import a library from a JSON file")
        self._import_btn.clicked.connect(self._import_library)
        for b in (self._export_btn, self._import_btn):
            io_btns.addWidget(b)
        left.addLayout(io_btns)

        # ── Right: component list ─────────────────────────────────────
        right = QVBoxLayout()
        root.addLayout(right, 2)

        right.addWidget(QLabel("Components in selected library:"))
        self._comp_list = QListWidget()
        right.addWidget(self._comp_list)

        comp_btns = QHBoxLayout()
        self._new_comp_btn = QPushButton("New Component…")
        self._new_comp_btn.clicked.connect(self._new_component)
        self._edit_comp_btn = QPushButton("Edit…")
        self._edit_comp_btn.clicked.connect(self._edit_component)
        self._del_comp_btn = QPushButton("Delete")
        self._del_comp_btn.clicked.connect(self._delete_component)
        for b in (self._new_comp_btn, self._edit_comp_btn, self._del_comp_btn):
            comp_btns.addWidget(b)
        right.addLayout(comp_btns)

        close_btn = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_btn.rejected.connect(self.accept)
        right.addWidget(close_btn)

        self._refresh_libs()

    # ── Library helpers ────────────────────────────────────────────────

    def _refresh_libs(self) -> None:
        self._lib_list.clear()
        lm = LibraryManager()
        # Fix 2: Only show user libraries (not the preset library which is read-only)
        self._libs = [lib for lib in lm.all_libraries() if not lib.is_preset]
        for lib in self._libs:
            self._lib_list.addItem(lib.name)
        if self._libs:
            self._lib_list.setCurrentRow(0)
            self._refresh_comps(0)

    def _current_lib(self):
        row = self._lib_list.currentRow()
        if 0 <= row < len(self._libs):
            return self._libs[row]
        return None

    def _on_lib_selected(self, row: int) -> None:
        self._refresh_comps(row)

    def _add_library(self) -> None:
        name, ok = QInputDialog.getText(self, "New Library", "Library name:")
        if ok and name.strip():
            lm = LibraryManager()
            lm.add_library(name.strip())
            self._refresh_libs()

    def _delete_library(self) -> None:
        lib = self._current_lib()
        if lib is None:
            return
        reply = QMessageBox.question(
            self, "Delete Library",
            f"Delete library '{lib.name}' and all its components?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            lm = LibraryManager()
            lm.remove_library(lib.library_id)
            self._refresh_libs()

    def _rename_library(self) -> None:
        lib = self._current_lib()
        if lib is None:
            return
        name, ok = QInputDialog.getText(
            self, "Rename Library", "New name:", text=lib.name)
        if ok and name.strip():
            lm = LibraryManager()
            lm.rename_library(lib.library_id, name.strip())
            self._refresh_libs()

    def _export_library(self) -> None:
        """Feature #5: Export the current library to a JSON file."""
        import json as _json
        from PyQt6.QtWidgets import QFileDialog
        lib = self._current_lib()
        if lib is None:
            QMessageBox.warning(self, "Export Library", "Please select a library first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Library",
            f"{lib.name}.json",
            "JSON files (*.json);;All files (*)",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                _json.dump(lib.to_dict(), fh, indent=2)
            QMessageBox.information(
                self, "Export Library",
                f"Library '{lib.name}' exported to:\n{path}",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Export Error", str(exc))

    def _import_library(self) -> None:
        """Feature #5: Import a library from a JSON file."""
        import json as _json
        import uuid as _uuid
        from PyQt6.QtWidgets import QFileDialog
        from ..models.library_system import CompLibrary
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Library", "",
            "JSON files (*.json);;All files (*)",
        )
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as fh:
                data = _json.load(fh)
            lib = CompLibrary.from_dict(data)
            lm = LibraryManager()
            # Assign a new ID if one already exists to avoid collision
            if lm.get_library(lib.library_id) is not None:
                lib.library_id = str(_uuid.uuid4())
            lm._libraries.append(lib)
            lm._save_library(lib)
            self._refresh_libs()
            QMessageBox.information(
                self, "Import Library",
                f"Library '{lib.name}' imported successfully.",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Import Error", str(exc))

    # ── Component helpers ──────────────────────────────────────────────

    def _refresh_comps(self, lib_row: int | None = None) -> None:
        self._comp_list.clear()
        lib = self._current_lib()
        if lib is None:
            self._entries: list[LibEntry] = []
            return
        self._entries = lib.all()
        for e in self._entries:
            tag = " [built-in]" if e.is_builtin else ""
            self._comp_list.addItem(f"{e.display_name}  [{e.type_name}]{tag}")

    def _new_component(self) -> None:
        lib = self._current_lib()
        if lib is None:
            QMessageBox.warning(self, "New Component",
                                "Please select a library first.")
            return
        dlg = UserComponentEditorDialog(self, library_id=lib.library_id)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._refresh_comps()

    def _edit_component(self) -> None:
        lib = self._current_lib()
        row = self._comp_list.currentRow()
        if lib is None or row < 0 or row >= len(self._entries):
            return
        entry = self._entries[row]
        dlg = UserComponentEditorDialog(
            self, existing=entry, library_id=lib.library_id)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._refresh_comps()

    def _delete_component(self) -> None:
        lib = self._current_lib()
        row = self._comp_list.currentRow()
        if lib is None or row < 0 or row >= len(self._entries):
            return
        entry = self._entries[row]
        reply = QMessageBox.question(
            self, "Delete Component",
            f"Delete component '{entry.display_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            lm = LibraryManager()
            lm.delete_entry(lib.library_id, entry.type_name)
            self._refresh_comps()


# ---------------------------------------------------------------------------
# Backward-compat alias
# ---------------------------------------------------------------------------

UserLibraryManagerDialog = LibraryManagerDialog

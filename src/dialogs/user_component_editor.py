"""User Component Editor — create and edit schematic components across libraries."""
from __future__ import annotations

import copy
from typing import Any

from PyQt6.QtCore import QPointF, QRectF, Qt, QObject, QEvent
from PyQt6.QtGui import (
    QBrush, QColor, QFont, QPainter, QPen, QKeySequence, QUndoCommand,
    QUndoStack,
)
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
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
SUB_GRID = GRID_SIZE // 2  # 10 px


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

    def __init__(self) -> None:
        super().__init__()
        self.setSceneRect(QRectF(-200, -200, 400, 400))
        self.setBackgroundBrush(QColor("#f8f8f8"))
        # tools: "select" | "line" | "rect" | "ellipse" | "pin"
        self._tool: str = "select"
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
        self._draw_origin()

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
        self._tool = tool
        if tool == "select":
            self._cancel_draw()

    def _cancel_draw(self) -> None:
        """Cancel any in-progress drawing operation."""
        self._line_start = None
        if self._temp_item:
            self.removeItem(self._temp_item)
            self._temp_item = None

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

        pen = QPen(QColor("#111111"), 2)
        for cmd in snap.get("cmds", []):
            self.sym_cmds.append(cmd)
            if cmd.kind == "line":
                it = self.addLine(cmd.x1, cmd.y1, cmd.x2, cmd.y2, pen)
            elif cmd.kind == "rect":
                it = self.addRect(QRectF(cmd.x1, cmd.y1, cmd.w, cmd.h), pen,
                                  QBrush(Qt.BrushStyle.NoBrush))
            elif cmd.kind == "ellipse":
                rx, ry = cmd.w / 2, cmd.h / 2
                it = self.addEllipse(
                    QRectF(cmd.x1 - rx, cmd.y1 - ry, cmd.w, cmd.h), pen,
                    QBrush(Qt.BrushStyle.NoBrush))
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
        # Issue 6: right-click cancels any ongoing drawing
        if event.button() == Qt.MouseButton.RightButton:
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
        elif self._tool == "line":
            if self._line_start is None:
                self._line_start = draw_pos
            else:
                before = self._snapshot()
                cmd = SymbolCmd("line",
                                x1=self._line_start.x(), y1=self._line_start.y(),
                                x2=draw_pos.x(), y2=draw_pos.y())
                self.sym_cmds.append(cmd)
                pen = QPen(QColor("#111111"), 2)
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
                cmd = SymbolCmd("rect", x1=rx, y1=ry, w=w, h=h)
                self.sym_cmds.append(cmd)
                pen = QPen(QColor("#111111"), 2)
                it = self.addRect(QRectF(rx, ry, w, h), pen,
                                  QBrush(Qt.BrushStyle.NoBrush))
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
                cmd = SymbolCmd("ellipse", x1=rx + w / 2, y1=ry + h / 2, w=w, h=h)
                self.sym_cmds.append(cmd)
                pen = QPen(QColor("#111111"), 2)
                it = self.addEllipse(QRectF(rx, ry, w, h), pen,
                                     QBrush(Qt.BrushStyle.NoBrush))
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
        super().mouseMoveEvent(event)

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
                pen = QPen(QColor("#111111"), 2)
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
                        it = self.addLine(c.x1, c.y1, c.x2, c.y2, pen)
                    elif c.kind == "rect":
                        it = self.addRect(QRectF(c.x1, c.y1, c.w, c.h), pen,
                                          QBrush(Qt.BrushStyle.NoBrush))
                    elif c.kind == "ellipse":
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
        marker = _PinMarker(pos, f"P{len(self.pins) + 1}")
        self.addItem(marker)
        self.pins.append(marker)

    def clear_symbol(self) -> None:
        for item in list(self.items()):
            self.removeItem(item)
        self.pins.clear()
        self.sym_cmds.clear()
        self._sym_items.clear()
        self._line_start = None
        self._temp_item = None
        self._draw_origin()

    def load_def(self, udef: UserCompDef) -> None:
        self.clear_symbol()
        pen = QPen(QColor("#111111"), 2)
        for cmd in udef.symbol:
            if cmd.kind == "line":
                it = self.addLine(cmd.x1, cmd.y1, cmd.x2, cmd.y2, pen)
            elif cmd.kind == "rect":
                it = self.addRect(QRectF(cmd.x1, cmd.y1, cmd.w, cmd.h),
                                  pen, QBrush(Qt.BrushStyle.NoBrush))
            elif cmd.kind == "ellipse":
                # cmd.x1/y1 is the centre; cmd.w/h is the bounding rect size
                rx, ry = cmd.w / 2, cmd.h / 2
                it = self.addEllipse(
                    QRectF(cmd.x1 - rx, cmd.y1 - ry, cmd.w, cmd.h),
                    pen, QBrush(Qt.BrushStyle.NoBrush))
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
    """Visible pin marker on the symbol editor canvas."""
    def __init__(self, pos: QPointF, name: str) -> None:
        r = 5
        super().__init__(-r, -r, 2 * r, 2 * r)
        self.setPos(pos)
        self.pin_name = name
        self.setPen(QPen(QColor("#2277ee"), 1.5))
        self.setBrush(QBrush(QColor("#aaccff")))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        lbl = QGraphicsTextItem(name, self)
        lbl.setDefaultTextColor(QColor("#0044aa"))
        lbl.setFont(QFont("monospace", 6))
        lbl.setPos(r + 1, -r)


# ---------------------------------------------------------------------------
# Issue 8: Floating icon toolbar that appears when hovering over the canvas
# ---------------------------------------------------------------------------

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
        ("▭", "Draw Rect", "rect", False),
        ("◯", "Draw Ellipse", "ellipse", False),
        ("⊙", "Add Pin", "pin", False),
        ("✕", "Clear Canvas", "clear", True),
        ("↩", "Undo (Ctrl+Z)", "undo", True),
        ("↪", "Redo (Ctrl+Y)", "redo", True),
    ]

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
            btn.setStyleSheet(
                "QPushButton {"
                "  background: rgba(255,255,255,200);"
                "  border: 1px solid #aaa;"
                "  border-radius: 4px;"
                "  font-size: 14px;"
                "}"
                "QPushButton:hover { background: rgba(200,220,255,220); }"
                "QPushButton:pressed { background: rgba(160,200,255,255); }"
            )
            if is_action:
                btn.clicked.connect(
                    lambda _checked, k=key: self._do_action(k)
                )
            else:
                btn.clicked.connect(
                    lambda _checked, k=key: self._scene.set_tool(k)
                )
            layout.addWidget(btn)
            self._btn_map[key] = btn

        self.adjustSize()
        self.hide()

        # Install event filters to track enter/leave on view and its viewport
        view.installEventFilter(self)
        view.viewport().installEventFilter(self)

    def _do_action(self, action: str) -> None:
        if action == "clear":
            self._scene.clear_symbol()
        elif action == "undo":
            self._scene._undo_stack.undo()
        elif action == "redo":
            self._scene._undo_stack.redo()

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
        self._sym_view = QGraphicsView(self._sym_scene)
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

        right.addWidget(form_box)

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

        # ── Issue 6: Extra labels section ─────────────────────────────
        label_box = QGroupBox("Extra Labels (beyond Ref/Value)")
        label_layout = QVBoxLayout(label_box)
        self._label_list = QListWidget()
        self._label_list.setToolTip(
            "Extra labels attached to this component.\n"
            "Each entry: <text>  [<side>  order=<n>]"
        )
        label_layout.addWidget(self._label_list)

        label_btn_row = QHBoxLayout()
        add_lbl_btn = QPushButton("Add Label…")
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
                    symbol=[SymbolCmd(**s) for s in existing.symbol],
                )
                self._sym_scene.load_def(_sym_udef)
            else:
                # Issue 1: For built-in components, show actual rendered preview
                self._load_builtin_preview(existing)
            # Populate existing extra labels
            for lbl_dict in existing.labels:
                ldef = LabelDef(**lbl_dict) if isinstance(lbl_dict, dict) else lbl_dict
                self._label_defs.append(ldef)
            self._refresh_label_list()
            self._refresh_pin_list()

    # ------------------------------------------------------------------
    # Issue 1: built-in component preview
    # ------------------------------------------------------------------

    def _load_builtin_preview(self, entry: LibEntry) -> None:
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
            self._label_list.addItem(
                f"{ld.text!r}  [{ld.side}  order={ld.order}]"
            )

    def _add_label(self) -> None:
        dlg = _LabelEditDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._label_defs.append(dlg.label_def())
            self._refresh_label_list()

    def _edit_label(self) -> None:
        row = self._label_list.currentRow()
        if 0 <= row < len(self._label_defs):
            dlg = _LabelEditDialog(self, self._label_defs[row])
            if dlg.exec() == QDialog.DialogCode.Accepted:
                self._label_defs[row] = dlg.label_def()
                self._refresh_label_list()

    def _remove_label(self) -> None:
        row = self._label_list.currentRow()
        if 0 <= row < len(self._label_defs):
            self._label_defs.pop(row)
            self._refresh_label_list()

    # ------------------------------------------------------------------

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

        labels_data = [
            {"text": ld.text, "side": ld.side, "order": ld.order}
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
        )

        lm = LibraryManager()
        lm.save_entry(self._library_id, entry)

        self.accept()


# ---------------------------------------------------------------------------
# Simple label-definition editor dialog (Issue 6)
# ---------------------------------------------------------------------------

class _LabelEditDialog(QDialog):
    """Small dialog for adding or editing a LabelDef."""

    def __init__(self, parent: QWidget | None = None,
                 ldef: LabelDef | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Label Definition")
        layout = QFormLayout(self)

        self._text_edit = QLineEdit(ldef.text if ldef else "")
        layout.addRow("Label text:", self._text_edit)

        self._side_combo = QComboBox()
        for s in ("top", "bottom", "left", "right"):
            self._side_combo.addItem(s)
        if ldef:
            idx = self._side_combo.findText(ldef.side)
            if idx >= 0:
                self._side_combo.setCurrentIndex(idx)
        layout.addRow("Side:", self._side_combo)

        self._order_edit = QLineEdit(str(ldef.order) if ldef else "0")
        layout.addRow("Order (0 = first):", self._order_edit)

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
        self._libs = lm.all_libraries()
        for lib in self._libs:
            tag = " [Preset]" if lib.is_preset else ""
            self._lib_list.addItem(f"{lib.name}{tag}")
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
        if lib.is_preset:
            QMessageBox.warning(self, "Delete Library",
                                "The Preset Library cannot be deleted.")
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


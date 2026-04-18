"""User Component Editor — create and edit user-defined schematic components."""
from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
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
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..models.user_library import PinDef, SymbolCmd, UserCompDef, UserLibrary
from ..canvas.grid import GRID_SIZE, draw_grid, snap_to_grid


# ---------------------------------------------------------------------------
# Mini scene / view for drawing the symbol
# ---------------------------------------------------------------------------

class _SymbolScene(QGraphicsScene):
    """Small scene for placing symbol elements interactively."""

    def __init__(self) -> None:
        super().__init__()
        self.setSceneRect(QRectF(-200, -200, 400, 400))
        self.setBackgroundBrush(QColor("#f8f8f8"))
        self._tool: str = "select"   # "select" | "line" | "rect" | "pin"
        self._line_start: QPointF | None = None
        self._temp_item: QGraphicsItem | None = None
        self.pins: list["_PinMarker"] = []
        self.sym_cmds: list[SymbolCmd] = []
        self._draw_origin()

    def _draw_origin(self) -> None:
        """Draw the origin crosshair."""
        pen = QPen(QColor("#aaaaff"), 0.5)
        pen.setCosmetic(True)
        self.addLine(-200, 0, 200, 0, pen)
        self.addLine(0, -200, 0, 200, pen)

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        super().drawBackground(painter, rect)
        draw_grid(painter, rect)

    def set_tool(self, tool: str) -> None:
        self._tool = tool
        if tool == "select":
            self._line_start = None
            if self._temp_item:
                self.removeItem(self._temp_item)
                self._temp_item = None

    def mousePressEvent(self, event: Any) -> None:
        pos = event.scenePos()
        sx, sy = snap_to_grid(pos.x(), pos.y())
        snapped = QPointF(sx, sy)

        if self._tool == "pin":
            self._place_pin(snapped)
        elif self._tool == "line":
            if self._line_start is None:
                self._line_start = snapped
            else:
                cmd = SymbolCmd("line",
                                x1=self._line_start.x(), y1=self._line_start.y(),
                                x2=snapped.x(), y2=snapped.y())
                self.sym_cmds.append(cmd)
                pen = QPen(QColor("#111111"), 2)
                self.addLine(self._line_start.x(), self._line_start.y(),
                             snapped.x(), snapped.y(), pen)
                if self._temp_item:
                    self.removeItem(self._temp_item)
                    self._temp_item = None
                self._line_start = snapped  # chain lines
        elif self._tool == "rect":
            if self._line_start is None:
                self._line_start = snapped
            else:
                x1, y1 = self._line_start.x(), self._line_start.y()
                x2, y2 = snapped.x(), snapped.y()
                w, h = abs(x2 - x1), abs(y2 - y1)
                rx, ry = min(x1, x2), min(y1, y2)
                cmd = SymbolCmd("rect", x1=rx, y1=ry, w=w, h=h)
                self.sym_cmds.append(cmd)
                pen = QPen(QColor("#111111"), 2)
                self.addRect(QRectF(rx, ry, w, h), pen, QBrush(Qt.BrushStyle.NoBrush))
                if self._temp_item:
                    self.removeItem(self._temp_item)
                    self._temp_item = None
                self._line_start = None
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: Any) -> None:
        pos = event.scenePos()
        sx, sy = snap_to_grid(pos.x(), pos.y())
        snapped = QPointF(sx, sy)
        if self._line_start is not None and self._tool in ("line", "rect"):
            if self._temp_item:
                self.removeItem(self._temp_item)
            pen = QPen(QColor("#2277ee"), 1, Qt.PenStyle.DashLine)
            if self._tool == "line":
                self._temp_item = self.addLine(
                    self._line_start.x(), self._line_start.y(),
                    snapped.x(), snapped.y(), pen)
            else:
                x1, y1 = self._line_start.x(), self._line_start.y()
                x2, y2 = snapped.x(), snapped.y()
                w, h = abs(x2 - x1), abs(y2 - y1)
                rx, ry = min(x1, x2), min(y1, y2)
                self._temp_item = self.addRect(
                    QRectF(rx, ry, w, h), pen, QBrush(Qt.BrushStyle.NoBrush))
        super().mouseMoveEvent(event)

    def _place_pin(self, pos: QPointF) -> None:
        marker = _PinMarker(pos, f"P{len(self.pins) + 1}")
        self.addItem(marker)
        self.pins.append(marker)

    def clear_symbol(self) -> None:
        for item in list(self.items()):
            self.removeItem(item)
        self.pins.clear()
        self.sym_cmds.clear()
        self._line_start = None
        self._temp_item = None
        self._draw_origin()

    def load_def(self, udef: UserCompDef) -> None:
        self.clear_symbol()
        pen = QPen(QColor("#111111"), 2)
        for cmd in udef.symbol:
            if cmd.kind == "line":
                self.addLine(cmd.x1, cmd.y1, cmd.x2, cmd.y2, pen)
            elif cmd.kind == "rect":
                self.addRect(QRectF(cmd.x1, cmd.y1, cmd.w, cmd.h),
                             pen, QBrush(Qt.BrushStyle.NoBrush))
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
# Main editor dialog
# ---------------------------------------------------------------------------

class UserComponentEditorDialog(QDialog):
    """Dialog to create or edit a user-defined schematic component."""

    def __init__(self, parent: QWidget | None = None,
                 existing: UserCompDef | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(
            "Edit User Component" if existing else "Create User Component"
        )
        self.resize(900, 650)
        self._existing = existing

        # ── root layout ──────────────────────────────────────────────
        root = QHBoxLayout(self)

        # ── left: canvas ─────────────────────────────────────────────
        left = QVBoxLayout()
        root.addLayout(left, 2)

        lbl = QLabel(
            "Draw symbol (click tools below).\n"
            "Pins snap to grid and become connection points."
        )
        lbl.setWordWrap(True)
        left.addWidget(lbl)

        self._sym_scene = _SymbolScene()
        self._sym_view = QGraphicsView(self._sym_scene)
        self._sym_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._sym_view.setMinimumSize(400, 400)
        left.addWidget(self._sym_view)

        # Tool buttons
        tool_row = QHBoxLayout()
        for label, tool in [("Select", "select"), ("Line", "line"),
                             ("Rect", "rect"), ("Add Pin", "pin")]:
            btn = QPushButton(label)
            btn.clicked.connect(lambda checked, t=tool: self._sym_scene.set_tool(t))
            tool_row.addWidget(btn)
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._sym_scene.clear_symbol)
        tool_row.addWidget(clear_btn)
        left.addLayout(tool_row)

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
        right.addStretch()

        # OK / Cancel
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        right.addWidget(buttons)

        # ── pre-fill if editing ───────────────────────────────────────
        if existing:
            self._name_edit.setText(existing.type_name)
            self._display_edit.setText(existing.display_name)
            self._cat_edit.setText(existing.category)
            self._desc_edit.setText(existing.description)
            self._prefix_edit.setText(existing.ref_prefix)
            self._value_edit.setText(existing.default_value)
            self._sym_scene.load_def(existing)
            self._refresh_pin_list()

    # ------------------------------------------------------------------

    def _refresh_pin_list(self) -> None:
        self._pin_list.clear()
        for marker in self._sym_scene.pins:
            self._pin_list.addItem(marker.pin_name)

    def _rename_pin(self, item: Any) -> None:
        from PyQt6.QtWidgets import QInputDialog
        row = self._pin_list.row(item)
        if 0 <= row < len(self._sym_scene.pins):
            marker = self._sym_scene.pins[row]
            new_name, ok = QInputDialog.getText(
                self, "Rename Pin", "Pin name:", text=marker.pin_name)
            if ok and new_name.strip():
                marker.pin_name = new_name.strip()
                item.setText(new_name.strip())
                # Update label inside the marker
                for child in marker.childItems():
                    if isinstance(child, QGraphicsTextItem):
                        child.setPlainText(new_name.strip())

    def _on_accept(self) -> None:
        type_name = self._name_edit.text().strip()
        display = self._display_edit.text().strip() or type_name
        if not type_name:
            QMessageBox.warning(self, "Validation", "Type name is required.")
            return

        pins = []
        for marker in self._sym_scene.pins:
            pins.append(PinDef(
                name=marker.pin_name,
                x=marker.pos().x(),
                y=marker.pos().y(),
            ))

        udef = UserCompDef(
            type_name=type_name,
            display_name=display,
            category=self._cat_edit.text().strip() or "User",
            description=self._desc_edit.text().strip(),
            ref_prefix=self._prefix_edit.text().strip() or "U",
            default_value=self._value_edit.text().strip(),
            pins=pins,
            symbol=list(self._sym_scene.sym_cmds),
        )

        ulib = UserLibrary()
        ulib.save_def(udef)
        # Reset singleton so palette picks up the change
        UserLibrary.reset_instance()

        self.accept()


# ---------------------------------------------------------------------------
# Manager dialog (list existing + create/edit/delete)
# ---------------------------------------------------------------------------

class UserLibraryManagerDialog(QDialog):
    """Browse and manage user-defined components."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("User Component Library")
        self.resize(500, 350)

        layout = QVBoxLayout(self)

        self._list = QListWidget()
        layout.addWidget(self._list)

        btn_row = QHBoxLayout()
        new_btn = QPushButton("New Component…")
        edit_btn = QPushButton("Edit…")
        del_btn = QPushButton("Delete")
        new_btn.clicked.connect(self._new)
        edit_btn.clicked.connect(self._edit)
        del_btn.clicked.connect(self._delete)
        for b in (new_btn, edit_btn, del_btn):
            btn_row.addWidget(b)
        layout.addLayout(btn_row)

        close_btn = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_btn.rejected.connect(self.reject)
        layout.addWidget(close_btn)

        self._refresh()

    def _refresh(self) -> None:
        self._list.clear()
        ulib = UserLibrary()
        for udef in ulib.all():
            self._list.addItem(f"{udef.display_name}  [{udef.type_name}]")
        self._udefs = ulib.all()

    def _new(self) -> None:
        dlg = UserComponentEditorDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._refresh()

    def _edit(self) -> None:
        row = self._list.currentRow()
        if row < 0 or row >= len(self._udefs):
            return
        dlg = UserComponentEditorDialog(self, existing=self._udefs[row])
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._refresh()

    def _delete(self) -> None:
        row = self._list.currentRow()
        if row < 0 or row >= len(self._udefs):
            return
        udef = self._udefs[row]
        reply = QMessageBox.question(
            self, "Delete", f"Delete component '{udef.display_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            ulib = UserLibrary()
            ulib.delete_def(udef.type_name)
            UserLibrary.reset_instance()
            self._refresh()

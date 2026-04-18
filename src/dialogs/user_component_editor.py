"""User Component Editor — create and edit schematic components across libraries."""
from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPen
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
                # Issue 3 fix: reset start to None (independent lines, not chains)
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
                self._line_start = None  # end line; don't chain
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
        elif self._tool == "ellipse":
            if self._line_start is None:
                self._line_start = snapped
            else:
                x1, y1 = self._line_start.x(), self._line_start.y()
                x2, y2 = snapped.x(), snapped.y()
                w, h = abs(x2 - x1), abs(y2 - y1)
                rx, ry = min(x1, x2), min(y1, y2)
                # Store as ellipse cmd: x1/y1 = top-left, w/h = bounding rect dims
                cmd = SymbolCmd("ellipse", x1=rx + w / 2, y1=ry + h / 2, w=w, h=h)
                self.sym_cmds.append(cmd)
                pen = QPen(QColor("#111111"), 2)
                self.addEllipse(QRectF(rx, ry, w, h), pen,
                                QBrush(Qt.BrushStyle.NoBrush))
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
        if self._line_start is not None and self._tool in ("line", "rect",
                                                            "ellipse"):
            if self._temp_item:
                self.removeItem(self._temp_item)
            pen = QPen(QColor("#2277ee"), 1, Qt.PenStyle.DashLine)
            if self._tool == "line":
                self._temp_item = self.addLine(
                    self._line_start.x(), self._line_start.y(),
                    snapped.x(), snapped.y(), pen)
            elif self._tool == "rect":
                x1, y1 = self._line_start.x(), self._line_start.y()
                x2, y2 = snapped.x(), snapped.y()
                w, h = abs(x2 - x1), abs(y2 - y1)
                rx, ry = min(x1, x2), min(y1, y2)
                self._temp_item = self.addRect(
                    QRectF(rx, ry, w, h), pen, QBrush(Qt.BrushStyle.NoBrush))
            else:  # ellipse
                x1, y1 = self._line_start.x(), self._line_start.y()
                x2, y2 = snapped.x(), snapped.y()
                w, h = abs(x2 - x1), abs(y2 - y1)
                rx, ry = min(x1, x2), min(y1, y2)
                self._temp_item = self.addEllipse(
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
            elif cmd.kind == "ellipse":
                # cmd.x1/y1 is the centre; cmd.w/h is the bounding rect size
                rx, ry = cmd.w / 2, cmd.h / 2
                self.addEllipse(
                    QRectF(cmd.x1 - rx, cmd.y1 - ry, cmd.w, cmd.h),
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
            "Draw symbol (click tools below).\n"
            "Pins snap to grid and become connection points.\n"
            "Note: built-in preset components use hardcoded rendering; "
            "only metadata fields apply to them."
        )
        lbl.setWordWrap(True)
        left.addWidget(lbl)

        self._sym_scene = _SymbolScene()
        self._sym_view = QGraphicsView(self._sym_scene)
        self._sym_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._sym_view.setMinimumSize(400, 400)
        # Issue 2: enable mouse tracking so real-time shape preview works even
        # when no mouse button is held (i.e. after clicking the first point).
        self._sym_view.setMouseTracking(True)
        self._sym_view.viewport().setMouseTracking(True)
        left.addWidget(self._sym_view)

        # Tool buttons
        tool_row = QHBoxLayout()
        for label, tool in [("Select", "select"), ("Line", "line"),
                             ("Rect", "rect"), ("Ellipse", "ellipse"),
                             ("Add Pin", "pin")]:
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


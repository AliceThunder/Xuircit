"""CircuitScene — QGraphicsScene with schematic editing modes."""
from __future__ import annotations

import copy
import re
import uuid
from enum import Enum, auto
from typing import Any

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QPainter, QUndoCommand, QUndoStack
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsScene, QGraphicsSceneMouseEvent

from ..canvas.grid import draw_grid, snap_to_grid, GRID_SIZE
from ..components.base import ComponentItem, PinItem
from ..components.wire import WireItem, _qt_style as _wire_qt_style
from ..components.node import JunctionItem, GroundItem, NetLabelItem
from ..models.circuit import Circuit

# Bug 8: Annotation layer snaps to a grid twice as dense as the current 10 px,
# i.e. 5 px.  GRID_SIZE = 20 px → annotation grid = 5 px.
# No grid lines are drawn for the annotation layer; items just snap to this
# finer resolution.
_ANNO_GRID_SIZE = GRID_SIZE // 4  # 5 px


def _snap_anno(x: float, y: float) -> tuple[float, float]:
    """Snap a point to the annotation layer's finer grid."""
    g = _ANNO_GRID_SIZE
    return round(x / g) * g, round(y / g) * g

class SceneMode(Enum):
    """Operating modes for the circuit scene."""
    SELECT = auto()
    PLACE_COMPONENT = auto()
    DRAW_WIRE = auto()


# Snap radius: within this many pixels of a pin the wire snaps to it.
_PIN_SNAP_RADIUS = GRID_SIZE * 0.8
# Tolerance for treating two coordinates as equal (used for aligned-pin detection).
_COORD_EPSILON = 1.0


def _migrate_label_pos(pos: list[float], rotation: float) -> list[float]:
    """Convert a label position from old screen-space (pre-v2 format) to
    parent-local space by applying inverse rotation.

    In old project files the label offset was manually rotated every time the
    component was rotated via ``_rotate_label_offset``.  The new rendering
    approach stores the offset in parent-local space (it never changes when
    the component rotates).  To recover the parent-local offset from an old
    saved value, apply the inverse rotation (CCW) the same number of times.
    """
    x, y = pos[0], pos[1]
    n = int(round(rotation / 90)) % 4
    # Inverse of n CW rotations = n CCW rotations; CCW formula: (x,y)→(y,−x)
    for _ in range(n):
        x, y = y, -x
    return [x, y]


def _fix_node_value_split(
    comp: dict[str, Any],
    type_name: str,
    lib_id: str | None,
    lm: Any,
) -> dict[str, Any]:
    """Correct the node/value split in a parsed SPICE component dict.

    The SPICE parser heuristically treats the last non-parameter token as
    the component value.  For multi-pin components with an empty value this
    misidentifies the last node as the value.

    When the library entry is found, we compute the expected pin count and
    redistribute the tokens accordingly.
    """
    try:
        result = lm.find_entry(type_name, lib_id)
        if result is None:
            return comp
        entry, _ = result
        pin_count = len(entry.pin_names) if entry.is_builtin else len(entry.pins)
        if pin_count == 0:
            return comp
        nodes: list[str] = list(comp.get("nodes", []))
        value: str = comp.get("value", "")
        all_tokens = nodes + ([value] if value else [])
        if len(all_tokens) <= pin_count:
            comp = dict(comp)
            comp["nodes"] = all_tokens
            comp["value"] = ""
        elif len(all_tokens) > pin_count:
            comp = dict(comp)
            comp["nodes"] = all_tokens[:pin_count]
            comp["value"] = " ".join(str(t) for t in all_tokens[pin_count:])
    except Exception:
        pass
    return comp





# Populated lazily on first access
_COMP_REGISTRY: dict[str, type[ComponentItem]] = {}


def _registry() -> dict[str, type[ComponentItem]]:
    global _COMP_REGISTRY
    if not _COMP_REGISTRY:
        from ..components.passive import (
            ResistorItem, CapacitorItem, InductorItem, TransformerItem,
        )
        from ..components.sources import (
            VoltageSourceItem, CurrentSourceItem,
            VCVSItem, CCCSItem, VCCSItem, CCVSItem,
        )
        from ..components.semiconductors import (
            DiodeItem, ZenerDiodeItem, NPNItem, PNPItem,
            NMOSItem, PMOSItem, IGBTItem,
        )
        from ..components.power import IdealSwitchItem, SCRItem, TRIACItem
        from ..components.wire import WireElbowItem, WireTeeItem

        _COMP_REGISTRY = {
            "R": ResistorItem,
            "C": CapacitorItem,
            "L": InductorItem,
            "T": TransformerItem,
            "V": VoltageSourceItem,
            "I": CurrentSourceItem,
            "E": VCVSItem,
            "F": CCCSItem,
            "G": VCCSItem,
            "H": CCVSItem,
            "D": DiodeItem,
            "Z": ZenerDiodeItem,
            "Q_NPN": NPNItem,
            "Q_PNP": PNPItem,
            "M_NMOS": NMOSItem,
            "M_PMOS": PMOSItem,
            "IGBT": IGBTItem,
            "SW": IdealSwitchItem,
            "SCR": SCRItem,
            "TRIAC": TRIACItem,
            "GND": GroundItem,
            "ELBOW": WireElbowItem,
            "TEE": WireTeeItem,
        }
    return _COMP_REGISTRY


def create_component_item(
    comp_type: str,
    ref: str = "X1",
    value: str = "",
    params: dict[str, Any] | None = None,
    comp_id: str | None = None,
    library_id: str | None = None,
) -> ComponentItem | None:
    """Create a ComponentItem for *comp_type*.

    The unified LibraryManager is consulted first.  If the entry is a
    built-in type (``is_builtin=True``) and a renderer class is registered,
    that class is used.  Otherwise a UserComponentItem is created from the
    entry's ``pins`` / ``symbol`` data.
    """
    try:
        from ..models.library_system import LibraryManager
        lm = LibraryManager()
        result = lm.find_entry(comp_type, library_id)
        if result is not None:
            entry, found_lib_id = result
            if entry.is_builtin:
                cls = _registry().get(comp_type)
                if cls is not None:
                    item = cls(ref=ref, value=value,
                               params=params or {}, comp_id=comp_id)
                    item.library_id = found_lib_id
                    return item
            # User-defined rendering
            from ..models.user_library import UserCompDef, PinDef, SymbolCmd, LabelDef
            from ..components.user_component import UserComponentItem
            udef = UserCompDef(
                type_name=entry.type_name,
                display_name=entry.display_name,
                category=entry.category,
                description=entry.description,
                ref_prefix=entry.ref_prefix,
                default_value=entry.default_value,
                pins=[PinDef(**p) for p in entry.pins],
                symbol=[SymbolCmd(**s) for s in entry.symbol],
                ref_label_offset=entry.ref_label_offset,
                val_label_offset=entry.val_label_offset,
                # Bug 2 fix: pass V-perspective offsets so rotated components
                # use the correct label positions stored in the component editor.
                ref_label_offset_v=entry.ref_label_offset_v,
                val_label_offset_v=entry.val_label_offset_v,
                ref_label_style=entry.ref_label_style,
                val_label_style=entry.val_label_style,
                labels=[LabelDef(**lb) for lb in entry.labels],
                is_virtual=entry.is_virtual,
            )
            return UserComponentItem(udef, ref=ref, value=value,
                                     params=params or {}, comp_id=comp_id,
                                     library_id=found_lib_id)
    except Exception:
        pass

    # Fallback: legacy registry lookup
    cls = _registry().get(comp_type)
    if cls is None:
        return None
    return cls(ref=ref, value=value, params=params or {}, comp_id=comp_id)


class _SnapshotCommand(QUndoCommand):
    """Undo/redo command that restores the entire circuit from a snapshot."""

    def __init__(
        self,
        scene: "CircuitScene",
        before: dict[str, Any],
        after: dict[str, Any],
        text: str,
    ) -> None:
        super().__init__(text)
        self._scene = scene
        self._before = before
        self._after = after
        self._first_redo = True  # skip redo on initial push (already applied)

    def undo(self) -> None:
        self._scene._restore_snapshot(self._before)

    def redo(self) -> None:
        if self._first_redo:
            self._first_redo = False
            return
        self._scene._restore_snapshot(self._after)


class CircuitScene(QGraphicsScene):
    """Main schematic canvas scene."""

    component_placed = pyqtSignal(dict)
    wire_drawn = pyqtSignal(dict)
    selection_changed_signal = pyqtSignal(list)
    mode_changed = pyqtSignal(str)
    # Fix 9: emitted when ESC resets the annotation tool to "select"
    annotation_tool_reset = pyqtSignal()

    def __init__(self, circuit: Circuit, parent: Any = None) -> None:
        super().__init__(parent)
        self.circuit = circuit
        self._mode = SceneMode.SELECT
        self._pending_type: str = ""
        self._ghost: ComponentItem | None = None

        # Wire-drawing state
        self._wire_start: QPointF | None = None
        self._wire_start_pin: tuple[str, str] | None = None
        self._temp_wire: WireItem | None = None
        # Visual alignment indicator (dashed line shown in auto-connect mode)
        self._align_indicator: Any = None

        # Grid visibility flag (False during export)
        self._show_grid: bool = True

        # Undo/redo — set by main_window after construction
        self.undo_stack: QUndoStack | None = None

        # Clipboard for copy/paste (list of serialised component dicts)
        self._clipboard: list[dict[str, Any]] = []

        # Bug 4 fix: track last mouse scene position for paste
        self._last_mouse_scene_pos: QPointF = QPointF(0, 0)

        # Feature #6: Layer visibility flags
        self._component_layer_visible: bool = True
        self._annotation_layer_visible: bool = True

        # Feature #6: Annotation layer state
        self._annotation_tool: str = "select"   # "select", "line", "arrow", etc.
        self._anno_start: QPointF | None = None  # Drawing start point
        self._anno_poly_pts: list[QPointF] = []  # Polyline points
        self._anno_poly_segs: list[Any] = []     # Temp segments
        self._anno_temp: Any = None              # Preview item
        # Task 8: read annotation color and canvas background from settings
        try:
            from ..app.settings import AppSettings as _AS
            _s = _AS()
            self._anno_color: str = _s.annotation_color()
            self._anno_line_style: str = _s.annotation_line_style()
            self._anno_line_width: float = _s.annotation_line_width()
            _bg = _s.canvas_bg_color()
            self._show_grid = _s.show_grid()
        except Exception:
            self._anno_color = "#cc2222"
            self._anno_line_style = "solid"
            self._anno_line_width = 2.0
            _bg = "#f8f8f8"
        self._anno_fill: bool = False

        self.setBackgroundBrush(QColor(_bg))
        self.setSceneRect(QRectF(-2000, -2000, 4000, 4000))
        self.selectionChanged.connect(self._on_selection_changed)

    # ------------------------------------------------------------------
    # Mode control
    # ------------------------------------------------------------------

    def set_mode(self, mode: SceneMode) -> None:
        if self._mode == mode:
            return
        self._clear_ghost()
        self._cancel_wire()
        self._mode = mode
        self.mode_changed.emit(mode.name)

    def mode(self) -> SceneMode:
        return self._mode

    def set_pending_component(self, comp_type: str) -> None:
        self._pending_type = comp_type
        self._clear_ghost()
        item = create_component_item(comp_type, ref="?")
        if item:
            item.setOpacity(0.5)
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            self.addItem(item)
            self._ghost = item

    # ------------------------------------------------------------------
    # Feature #6: Layer controls
    # ------------------------------------------------------------------

    def set_component_layer_visible(self, visible: bool) -> None:
        """Feature #6: show/hide the component drawing layer."""
        self._component_layer_visible = visible
        for item in self.items():
            from ..canvas.annotation import AnnotationItem
            if not isinstance(item, AnnotationItem):
                item.setVisible(visible)

    def set_annotation_layer_visible(self, visible: bool) -> None:
        """Feature #6: show/hide the annotation layer."""
        from ..canvas.annotation import AnnotationItem
        self._annotation_layer_visible = visible
        for item in self.items():
            if isinstance(item, AnnotationItem):
                item.setVisible(visible)

    def set_annotation_tool(self, tool: str) -> None:
        """Feature #6: set the active annotation drawing tool."""
        self._annotation_tool = tool
        self._anno_cancel()

    def set_annotation_color(self, color: str) -> None:
        """Feature #6: set annotation drawing color."""
        self._anno_color = color

    def set_annotation_fill(self, fill: bool) -> None:
        """Feature #6: set annotation fill mode."""
        self._anno_fill = fill

    def set_annotation_pen(self, style_name: str, width: float) -> None:
        self._anno_line_style = style_name
        self._anno_line_width = max(0.5, float(width))

    def apply_line_style_to_selection(self, style_name: str, width: float) -> None:
        """Apply line style/width to selected wires and annotations."""
        from ..canvas.annotation import AnnotationItem
        selected_items = [
            item
            for item in self.selectedItems()
            if isinstance(item, (WireItem, AnnotationItem))
        ]
        if not selected_items:
            return
        before = self._take_snapshot()
        for item in selected_items:
            item.set_line_style(style_name, width)
        after = self._take_snapshot()
        self._push_undo("Set Line Style", before, after)

    def _anno_cancel(self) -> None:
        """Cancel any in-progress annotation drawing."""
        self._anno_start = None
        if self._anno_temp is not None:
            self.removeItem(self._anno_temp)
            self._anno_temp = None
        for seg in self._anno_poly_segs:
            self.removeItem(seg)
        self._anno_poly_segs.clear()
        self._anno_poly_pts.clear()

    def _is_annotation_mode(self) -> bool:
        """Return True if the annotation tool is active (not 'select')."""
        return (self._mode == SceneMode.SELECT
                and self._annotation_tool not in ("select", "")
                and self._annotation_layer_visible)

    # ------------------------------------------------------------------
    # Mouse events
    # ------------------------------------------------------------------

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        pos = event.scenePos()
        sx, sy = snap_to_grid(pos.x(), pos.y())
        snapped = QPointF(sx, sy)

        if self._mode == SceneMode.PLACE_COMPONENT:
            if event.button() == Qt.MouseButton.LeftButton:
                self._place_component(snapped)
            elif event.button() == Qt.MouseButton.RightButton:
                self.set_mode(SceneMode.SELECT)
                # Issue 5: reset annotation tool on right-click
                self.annotation_tool_reset.emit()
            return

        if self._mode == SceneMode.DRAW_WIRE:
            if event.button() == Qt.MouseButton.LeftButton:
                self._wire_click(snapped)
            elif event.button() == Qt.MouseButton.RightButton:
                self._cancel_wire()
                # Issue 5: reset annotation tool on right-click
                self.annotation_tool_reset.emit()
            return

        # Feature #6: annotation drawing
        if self._is_annotation_mode():
            if event.button() == Qt.MouseButton.RightButton:
                # Right-click: finish polyline or cancel
                if self._annotation_tool == "polyline" and len(self._anno_poly_pts) >= 2:
                    self._anno_finish_polyline()
                else:
                    self._anno_cancel()
                # Issue 5: right-click always resets annotation tool to "select"
                self.set_annotation_tool("select")
                self.annotation_tool_reset.emit()
                return
            if event.button() == Qt.MouseButton.LeftButton:
                # Task 6: snap to the denser annotation grid (half the component grid)
                ax, ay = _snap_anno(pos.x(), pos.y())
                self._anno_press(QPointF(ax, ay))
                return

        # Issue 5: right-click in SELECT mode resets annotation tool
        if event.button() == Qt.MouseButton.RightButton:
            self.annotation_tool_reset.emit()

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        pos = event.scenePos()
        sx, sy = snap_to_grid(pos.x(), pos.y())
        snapped = QPointF(sx, sy)

        # Bug 4 fix: always track the last mouse scene position
        self._last_mouse_scene_pos = pos

        if self._mode == SceneMode.PLACE_COMPONENT and self._ghost:
            self._ghost.setPos(snapped)
        elif self._mode == SceneMode.DRAW_WIRE and self._wire_start:
            # 1. Direct pin snap (nearest pin within snap radius)
            pin_pos, _ = self._nearest_pin(snapped)
            # 2. H/V alignment snap: look for an aligned pin further away
            aligned_pos, aligned_info = self._aligned_pin(snapped)

            # Prefer the direct snap if available, else aligned, else raw grid
            if pin_pos is not None:
                effective_end = pin_pos
                self._remove_align_indicator()
            elif aligned_pos is not None:
                effective_end = aligned_pos
                self._show_align_indicator(snapped, aligned_pos)
            else:
                effective_end = snapped
                self._remove_align_indicator()

            if self._temp_wire is None:
                wire = WireItem(self._wire_start, effective_end)
                self.addItem(wire)
                self._temp_wire = wire
            else:
                self._temp_wire.update_endpoints(self._wire_start, effective_end)
        elif self._is_annotation_mode():
            # Task 6: snap annotation preview to finer grid
            ax, ay = _snap_anno(pos.x(), pos.y())
            self._anno_move(QPointF(ax, ay))

        super().mouseMoveEvent(event)

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self._mode == SceneMode.DRAW_WIRE:
            pos = event.scenePos()
            sx, sy = snap_to_grid(pos.x(), pos.y())
            self._finish_wire(QPointF(sx, sy))
            return
        # Feature #6: double-click finishes polyline annotation
        if self._is_annotation_mode() and self._annotation_tool == "polyline":
            if len(self._anno_poly_pts) >= 2:
                self._anno_finish_polyline()
            return
        super().mouseDoubleClickEvent(event)

    # ------------------------------------------------------------------
    # Placement
    # ------------------------------------------------------------------

    def _place_component(self, pos: QPointF) -> None:
        from ..models.library_system import LibraryManager
        lm = LibraryManager()
        result = lm.find_entry(self._pending_type)
        if result is None:
            return
        entry, library_id = result

        # Capture before-state for undo
        before = self._take_snapshot()

        ref = self.circuit.next_ref(entry.ref_prefix)
        default_value = entry.default_value
        default_params = dict(entry.default_params)

        comp_id = str(uuid.uuid4())
        item = create_component_item(
            self._pending_type, ref=ref,
            value=default_value, params=default_params,
            comp_id=comp_id, library_id=library_id,
        )
        if item is None:
            return
        item.setPos(pos)

        # Apply ghost rotation and flip so the user's shortcut adjustments are
        # preserved on the placed component (Issue 3).
        if self._ghost is not None:
            ghost_rot = self._ghost.rotation()
            ghost_fh = self._ghost._flip_h_active
            ghost_fv = self._ghost._flip_v_active
            if ghost_rot:
                item.setRotation(ghost_rot)
            if ghost_fh or ghost_fv:
                from PyQt6.QtGui import QTransform
                item.setTransform(QTransform(
                    -1.0 if ghost_fh else 1.0, 0, 0,
                    0, -1.0 if ghost_fv else 1.0, 0,
                    0, 0, 1,
                ))
                item._flip_h_active = ghost_fh
                item._flip_v_active = ghost_fv

        self.addItem(item)

        comp_dict: dict[str, Any] = {
            "id": comp_id,
            "type": self._pending_type,
            "library_id": library_id,
            "ref": ref,
            "value": default_value,
            "params": default_params,
            "x": pos.x(),
            "y": pos.y(),
            "rotation": item.rotation(),
            "flip_h": item._flip_h_active,
            "flip_v": item._flip_v_active,
        }
        self.circuit.add_component(comp_dict)
        self.component_placed.emit(comp_dict)

        # Rebuild all auto-wires after placement
        self._rebuild_auto_wires()

        # Push undo command
        after = self._take_snapshot()
        self._push_undo("Place Component", before, after)

    # ------------------------------------------------------------------
    # Wire drawing
    # ------------------------------------------------------------------

    def _wire_click(self, pos: QPointF) -> None:
        # 1. Direct pin snap
        pin_pos, pin_info = self._nearest_pin(pos)
        # 2. H/V alignment snap as fallback
        if pin_pos is None:
            pin_pos, pin_info = self._aligned_pin(pos)
        actual = pin_pos if pin_pos is not None else pos

        if self._wire_start is None:
            self._wire_start = actual
            self._wire_start_pin = pin_info
        else:
            self._finish_wire(actual, pin_info)

    def _finish_wire(self, end: QPointF,
                     end_pin: tuple[str, str] | None = None) -> None:
        if self._wire_start is None:
            return
        if end_pin is None:
            end_pin = self._pin_at(end)

        if self._temp_wire:
            self._temp_wire.update_endpoints(self._wire_start, end)
            self._temp_wire.start_pin = self._wire_start_pin
            self._temp_wire.end_pin = end_pin
            wire_dict = self._temp_wire.to_dict()
            self.circuit.add_wire(wire_dict)
            self.wire_drawn.emit(wire_dict)
            self._temp_wire = None

        self._wire_start = None
        self._wire_start_pin = None

    def _cancel_wire(self) -> None:
        if self._temp_wire:
            self.removeItem(self._temp_wire)
            self._temp_wire = None
        self._remove_align_indicator()
        self._wire_start = None
        self._wire_start_pin = None

    # ------------------------------------------------------------------
    # Feature #6: Annotation drawing helpers
    # ------------------------------------------------------------------

    def _anno_press(self, pos: QPointF) -> None:
        """Handle left-click for annotation drawing."""
        from PyQt6.QtGui import QPen, QColor as QC
        tool = self._annotation_tool

        if tool == "text":
            # Fix 10: Open text-input dialog and place a text annotation
            self._anno_place_text(pos)
            return

        if tool == "polyline":
            self._anno_poly_pts.append(pos)
            if len(self._anno_poly_pts) >= 2:
                pen = QPen(QC(self._anno_color), self._anno_line_width)
                pen.setStyle(_wire_qt_style(self._anno_line_style))
                p1, p2 = self._anno_poly_pts[-2], self._anno_poly_pts[-1]
                seg = self.addLine(p1.x(), p1.y(), p2.x(), p2.y(), pen)
                self._anno_poly_segs.append(seg)
            if self._anno_temp is not None:
                self.removeItem(self._anno_temp)
                self._anno_temp = None
        elif tool in ("line", "arrow", "circle", "ellipse", "rect"):
            if self._anno_start is None:
                self._anno_start = pos
            else:
                # Commit the annotation
                self._anno_commit(self._anno_start, pos)
                self._anno_start = None
                if self._anno_temp is not None:
                    self.removeItem(self._anno_temp)
                    self._anno_temp = None

    def _anno_place_text(self, pos: QPointF) -> None:
        """Fix 10: Open text annotation dialog and place result at pos."""
        from ..canvas.annotation import TextAnnotationItem, _TextAnnotationDialog
        dlg = _TextAnnotationDialog(color=self._anno_color)
        if dlg.exec():
            text = dlg.html()
            if text:
                before = self._take_snapshot()
                item = TextAnnotationItem(
                    text=text,
                    x=pos.x(), y=pos.y(),
                    color=self._anno_color,
                    font_family=dlg.font_family(),
                    font_size=dlg.font_size(),
                    bold=dlg.bold(),
                    italic=dlg.italic(),
                )
                if not self._annotation_layer_visible:
                    item.setVisible(False)
                self.addItem(item)
                self.circuit.add_annotation(item.to_dict())
                after = self._take_snapshot()
                self._push_undo("Add Text Annotation", before, after)

    def _anno_move(self, pos: QPointF) -> None:
        """Update annotation preview during mouse move."""
        from PyQt6.QtGui import QPen, QColor as QC
        from PyQt6.QtCore import Qt as Qt_
        tool = self._annotation_tool
        pen = QPen(QC(self._anno_color), max(1.0, self._anno_line_width * 0.75), Qt_.PenStyle.DashLine)

        if self._anno_temp is not None:
            self.removeItem(self._anno_temp)
            self._anno_temp = None

        if tool == "polyline" and self._anno_poly_pts:
            last = self._anno_poly_pts[-1]
            self._anno_temp = self.addLine(
                last.x(), last.y(), pos.x(), pos.y(), pen)
        elif self._anno_start is not None and tool in ("line", "arrow"):
            s = self._anno_start
            self._anno_temp = self.addLine(s.x(), s.y(), pos.x(), pos.y(), pen)
        elif self._anno_start is not None and tool in ("circle", "ellipse", "rect"):
            import math
            s = self._anno_start
            x1, y1 = s.x(), s.y()
            x2, y2 = pos.x(), pos.y()
            if tool == "circle":
                r = math.hypot(x2 - x1, y2 - y1)
                from PyQt6.QtCore import QRectF as QRF_
                self._anno_temp = self.addEllipse(
                    QRF_(x1 - r, y1 - r, 2 * r, 2 * r), pen)
            else:
                from PyQt6.QtCore import QRectF as QRF_
                rx, ry = min(x1, x2), min(y1, y2)
                w, h = abs(x2 - x1), abs(y2 - y1)
                if tool == "ellipse":
                    self._anno_temp = self.addEllipse(
                        QRF_(rx, ry, w, h), pen)
                else:
                    self._anno_temp = self.addRect(
                        QRF_(rx, ry, w, h), pen)

    def _anno_commit(self, start: QPointF, end: QPointF) -> None:
        """Commit a two-point annotation (not polyline)."""
        from ..canvas.annotation import AnnotationItem
        tool = self._annotation_tool
        pts = [[start.x(), start.y()], [end.x(), end.y()]]
        # Fix 6: capture before-state for undo
        before = self._take_snapshot()
        item = AnnotationItem(
            kind=tool,
            points=pts,
            closed=False,
            color=self._anno_color,
            line_width=self._anno_line_width,
            line_style=self._anno_line_style,
            fill=self._anno_fill,
        )
        if not self._annotation_layer_visible:
            item.setVisible(False)
        self.addItem(item)
        # Persist in circuit
        self.circuit.add_annotation(item.to_dict())
        # Fix 6: push undo
        after = self._take_snapshot()
        self._push_undo("Add Annotation", before, after)

    def _anno_finish_polyline(self) -> None:
        """Commit the current annotation polyline."""
        from ..canvas.annotation import AnnotationItem
        if len(self._anno_poly_pts) < 2:
            self._anno_cancel()
            return
        # Fix 6: capture before-state for undo
        before = self._take_snapshot()
        pts = [[p.x(), p.y()] for p in self._anno_poly_pts]
        item = AnnotationItem(
            kind="polyline",
            points=pts,
            closed=self._anno_fill,
            color=self._anno_color,
            line_width=self._anno_line_width,
            line_style=self._anno_line_style,
            fill=self._anno_fill,
        )
        if not self._annotation_layer_visible:
            item.setVisible(False)
        self.addItem(item)
        self.circuit.add_annotation(item.to_dict())
        self._anno_cancel()
        # Fix 6: push undo
        after = self._take_snapshot()
        self._push_undo("Add Annotation", before, after)

    def _pin_at(self, pos: QPointF) -> tuple[str, str] | None:
        """Return (comp_id, pin_name) if a pin is near pos."""
        for item in self.items(pos):
            if isinstance(item, PinItem):
                parent = item.parentItem()
                if isinstance(parent, ComponentItem):
                    return (parent.component_id, item.pin_name)
        return None

    def _aligned_pin(
        self, pos: QPointF, max_dist: float = 400.0, tol: float = 4.0
    ) -> tuple[QPointF | None, tuple[str, str] | None]:
        """Find the nearest pin that is horizontally OR vertically aligned
        with *pos* within *tol* pixels of the axis.

        Returns the closest such pin (scene pos, info) within *max_dist*.
        Excludes pins already at the wire start (to avoid zero-length wires).
        """
        best_d = max_dist
        best_pos: QPointF | None = None
        best_info: tuple[str, str] | None = None

        search = QRectF(
            pos.x() - max_dist, pos.y() - max_dist,
            2 * max_dist, 2 * max_dist,
        )
        for item in self.items(search):
            if not isinstance(item, ComponentItem):
                continue
            for pin_name, pin in item._pins.items():
                sp = item.mapToScene(pin.pos())
                # Skip if same point as wire start (no zero-length wire)
                if self._wire_start is not None:
                    if abs(sp.x() - self._wire_start.x()) < _COORD_EPSILON and \
                       abs(sp.y() - self._wire_start.y()) < _COORD_EPSILON:
                        continue
                dx = abs(sp.x() - pos.x())
                dy = abs(sp.y() - pos.y())
                # Horizontally aligned: same Y within tolerance
                if dy < tol:
                    d = dx
                    if d < best_d:
                        best_d = d
                        best_pos = sp
                        best_info = (item.component_id, pin_name)
                # Vertically aligned: same X within tolerance
                elif dx < tol:
                    d = dy
                    if d < best_d:
                        best_d = d
                        best_pos = sp
                        best_info = (item.component_id, pin_name)

        return best_pos, best_info

    def _show_align_indicator(self, from_pos: QPointF,
                              to_pos: QPointF) -> None:
        """Draw a dashed guide line to the aligned pin."""
        from PyQt6.QtGui import QPen, QColor
        self._remove_align_indicator()
        pen = QPen(QColor("#22cc44"), 1, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        self._align_indicator = self.addLine(
            from_pos.x(), from_pos.y(),
            to_pos.x(), to_pos.y(),
            pen,
        )
        if self._align_indicator:
            self._align_indicator.setZValue(10)

    def _remove_align_indicator(self) -> None:
        if self._align_indicator is not None:
            self.removeItem(self._align_indicator)
            self._align_indicator = None

    # ------------------------------------------------------------------
    # Auto-wire rebuild (Problem 1 + 2)
    # ------------------------------------------------------------------

    def _rebuild_auto_wires(self) -> None:
        """Remove all existing auto-wires and regenerate from scratch.

        Called after any component add / delete / move / rotate / flip so
        wires always reflect the current layout.
        """
        # Remove all WireItems from scene and circuit
        for item in list(self.items()):
            if isinstance(item, WireItem):
                self.removeItem(item)
        self.circuit.wires.clear()
        self.circuit._wire_index.clear()

        # Gather all component items currently in the scene
        comp_items: list[ComponentItem] = [
            it for it in self.items()
            if isinstance(it, ComponentItem)
        ]

        # Check every ordered pair (avoid double-drawing)
        seen: set[tuple[str, str, str, str]] = set()
        for i, item_a in enumerate(comp_items):
            for item_b in comp_items[i + 1:]:
                for pin_a, pin in item_a._pins.items():
                    sp_a = item_a.mapToScene(pin.pos())
                    for pin_b, pin2 in item_b._pins.items():
                        sp_b = item_b.mapToScene(pin2.pos())
                        self._try_auto_wire_pair(
                            item_a, pin_a, sp_a,
                            item_b, pin_b, sp_b,
                            seen,
                        )

    def _try_auto_wire_pair(
        self,
        item_a: ComponentItem,
        pin_a: str,
        sp_a: QPointF,
        item_b: ComponentItem,
        pin_b: str,
        sp_b: QPointF,
        seen: set[tuple[str, str, str, str]],
    ) -> None:
        """Attempt to draw a wire between two specific pins on two components."""
        dx = abs(sp_b.x() - sp_a.x())
        dy = abs(sp_b.y() - sp_a.y())

        is_h_aligned = dy < _COORD_EPSILON and dx > _COORD_EPSILON
        is_v_aligned = dx < _COORD_EPSILON and dy > _COORD_EPSILON
        if not is_h_aligned and not is_v_aligned:
            return

        # Enforce direction compatibility:
        # horizontal alignment → both pins must face horizontally
        # vertical alignment   → both pins must face vertically
        h_a = self._pin_is_horizontal(item_a, sp_a)
        h_b = self._pin_is_horizontal(item_b, sp_b)
        if is_h_aligned and (not h_a or not h_b):
            return
        if is_v_aligned and (h_a or h_b):
            return

        # Avoid duplicate wires
        key = tuple(sorted([(item_a.component_id, pin_a),
                             (item_b.component_id, pin_b)]))
        flat = (key[0][0], key[0][1], key[1][0], key[1][1])
        if flat in seen:
            return
        seen.add(flat)

        # Bug 3: exclude the two endpoint components themselves from path check
        if not self._is_path_clear(sp_a, sp_b, exclude={item_a, item_b}):
            return

        self._add_auto_wire(
            sp_a, sp_b,
            (item_a.component_id, pin_a),
            (item_b.component_id, pin_b),
        )

    def _pin_is_horizontal(self, item: ComponentItem,
                           pin_sp: QPointF) -> bool:
        """Return True if this pin faces horizontally (|dx| >= |dy| from item centre)."""
        comp_sp = item.scenePos()
        dx = abs(pin_sp.x() - comp_sp.x())
        dy = abs(pin_sp.y() - comp_sp.y())
        return dx >= dy

    def _is_path_clear(self, p1: QPointF, p2: QPointF,
                       exclude: "set[ComponentItem] | None" = None) -> bool:
        """Return True if the straight line from p1 to p2 is unobstructed.

        Components in *exclude* (typically the two endpoint components) are
        never counted as obstacles so that direct pin-to-pin connections work
        even when the component body slightly overlaps the wire path.
        The endpoints are shrunk inward so that the endpoint component bodies
        do not false-trigger (the shrink margin exceeds the bounding-rect
        padding used by all built-in symbols).
        """
        shrink = 8.0
        tol = 4.0
        if abs(p1.y() - p2.y()) < _COORD_EPSILON:
            # Horizontal wire
            x1 = min(p1.x(), p2.x()) + shrink
            x2 = max(p1.x(), p2.x()) - shrink
            if x2 <= x1:
                return True
            check_rect = QRectF(x1, p1.y() - tol, x2 - x1, 2 * tol)
        else:
            # Vertical wire
            y1 = min(p1.y(), p2.y()) + shrink
            y2 = max(p1.y(), p2.y()) - shrink
            if y2 <= y1:
                return True
            check_rect = QRectF(p1.x() - tol, y1, 2 * tol, y2 - y1)

        for item in self.items(check_rect):
            if isinstance(item, ComponentItem):
                if exclude and item in exclude:
                    continue
                return False
        return True

    def _add_auto_wire(
        self,
        start: QPointF,
        end: QPointF,
        start_pin: tuple[str, str],
        end_pin: tuple[str, str],
    ) -> None:
        """Create and register a wire between two pins."""
        wire = WireItem(start, end, wire_id=str(uuid.uuid4()), is_auto=True)
        wire.start_pin = start_pin
        wire.end_pin = end_pin
        self.addItem(wire)
        wire_dict = wire.to_dict()
        self.circuit.add_wire(wire_dict)
        self.wire_drawn.emit(wire_dict)

    def _nearest_pin(
        self, pos: QPointF, radius: float = _PIN_SNAP_RADIUS
    ) -> tuple[QPointF | None, tuple[str, str] | None]:
        """Find the nearest pin within *radius* scene pixels.

        Returns (scene_pos, (comp_id, pin_name)) or (None, None).
        """
        best_d2 = radius * radius
        best_pos: QPointF | None = None
        best_info: tuple[str, str] | None = None

        search = QRectF(
            pos.x() - radius, pos.y() - radius,
            2 * radius, 2 * radius,
        )
        for item in self.items(search):
            if not isinstance(item, ComponentItem):
                continue
            for pin_name, pin in item._pins.items():
                sp = item.mapToScene(pin.pos())
                dx = sp.x() - pos.x()
                dy = sp.y() - pos.y()
                d2 = dx * dx + dy * dy
                if d2 < best_d2:
                    best_d2 = d2
                    best_pos = sp
                    best_info = (item.component_id, pin_name)

        return best_pos, best_info

    # ------------------------------------------------------------------
    # Ghost
    # ------------------------------------------------------------------

    def _clear_ghost(self) -> None:
        if self._ghost:
            self.removeItem(self._ghost)
            self._ghost = None

    # ------------------------------------------------------------------
    # Undo / redo helpers
    # ------------------------------------------------------------------

    def _take_snapshot(self) -> dict[str, Any]:
        """Return a deep copy of the current circuit state."""
        self.sync_to_circuit()
        return copy.deepcopy(self.circuit.to_dict())

    def _push_undo(
        self, text: str, before: dict[str, Any], after: dict[str, Any]
    ) -> None:
        """Push a snapshot command onto the undo stack (if connected)."""
        if self.undo_stack is not None:
            cmd = _SnapshotCommand(self, before, after, text)
            self.undo_stack.push(cmd)

    def _restore_snapshot(self, snapshot: dict[str, Any]) -> None:
        """Restore circuit state from a snapshot and rebuild the scene."""
        self.circuit.from_dict(snapshot)
        self.rebuild_from_circuit()

    # ------------------------------------------------------------------
    # Background grid
    # ------------------------------------------------------------------

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        super().drawBackground(painter, rect)
        if self._show_grid:
            draw_grid(painter, rect)

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    def _on_selection_changed(self) -> None:
        self.selection_changed_signal.emit(self.selectedItems())

    # ------------------------------------------------------------------
    # Rebuild / apply
    # ------------------------------------------------------------------

    def sync_to_circuit(self) -> None:
        """Sync scene item positions/transforms back to the circuit model.

        Call this before generating any netlist or XCIT output to capture
        the current on-screen position of every component — including any
        drag, rotate, or flip operations that happened since the component
        was first placed (Issue 4).
        """
        idx: dict[str, dict] = {
            c["id"]: c for c in self.circuit.components if "id" in c
        }
        from ..canvas.annotation import AnnotationItem, TextAnnotationItem
        anno_idx: dict[str, dict] = {
            a["id"]: a for a in self.circuit.annotations if "id" in a
        }
        for item in self.items():
            # Fix 10: sync TextAnnotationItem positions
            if isinstance(item, TextAnnotationItem):
                aid = item.anno_id
                if aid in anno_idx:
                    dp = item.pos()
                    # TextAnnotationItem position is in scene coords via setPos
                    anno_idx[aid]["x"] = dp.x()
                    anno_idx[aid]["y"] = dp.y()
                    anno_idx[aid]["points"] = [[dp.x(), dp.y()]]
                    # Sync style fields so saves capture context-menu changes
                    anno_idx[aid]["text"] = item.toHtml()
                    anno_idx[aid]["is_html"] = True
                    anno_idx[aid]["color"] = item.anno_color
                    anno_idx[aid]["font_family"] = item.font_family
                    anno_idx[aid]["font_size"] = item.font_size
                    anno_idx[aid]["bold"] = item.bold
                    anno_idx[aid]["italic"] = item.italic
                continue
            # Feature #6: sync moved annotation positions
            if isinstance(item, AnnotationItem):
                aid = item.anno_id
                if aid in anno_idx:
                    # Update position if item was moved
                    dp = item.pos()
                    if dp.x() != 0 or dp.y() != 0:
                        pts = [[p[0] + dp.x(), p[1] + dp.y()]
                               for p in item.points]
                        anno_idx[aid]["points"] = pts
                        item.points = pts
                        item.setPos(0, 0)
                        item._rebuild_path()
                    # Sync style fields so saves capture context-menu changes
                    anno_idx[aid]["color"] = item.anno_color
                    anno_idx[aid]["line_width"] = item.line_width
                    anno_idx[aid]["line_style"] = item.line_style
                    anno_idx[aid]["fill"] = item.fill
                continue
            if not isinstance(item, ComponentItem):
                continue
            cid = item.component_id
            if cid not in idx:
                continue
            comp = idx[cid]
            pos = item.pos()
            comp["x"] = pos.x()
            comp["y"] = pos.y()
            comp["rotation"] = item.rotation()
            comp["flip_h"] = item._flip_h_active
            comp["flip_v"] = item._flip_v_active
            comp["label_ref_pos"] = [
                item._ref_label.pos().x(),
                item._ref_label.pos().y(),
            ]
            comp["label_val_pos"] = [
                item._val_label.pos().x(),
                item._val_label.pos().y(),
            ]
            # Issue 9: persist per-instance label colors so they survive save/load
            comp["label_ref_color"] = item._ref_label.brush().color().name()
            comp["label_val_color"] = item._val_label.brush().color().name()
            # Issue 14: persist per-label visibility flags
            comp["ref_visible"] = item._ref_visible
            comp["val_visible"] = item._val_visible
            # Feature #7: persist component color
            comp["color"] = item._color
            from ..components.user_component import UserComponentItem
            if isinstance(item, UserComponentItem):
                comp["extra_visible"] = list(item._extra_visible)
                # Issue 12: persist extra property values from params
                comp["params"] = dict(item.params)

    def rebuild_from_circuit(self) -> None:
        """Clear and repopulate the scene from self.circuit."""
        for item in list(self.items()):
            self.removeItem(item)

        # Detect old label-position format (pre-v2.0 project files wrote
        # label positions in manually-rotated screen space rather than
        # parent-local space).  Apply the inverse rotation so positions are
        # correct with the new rendering approach.
        label_format = getattr(self.circuit, "label_format", 2)

        for comp in self.circuit.components:
            item = create_component_item(
                comp["type"],
                ref=comp.get("ref", "X"),
                value=comp.get("value", ""),
                params=comp.get("params", {}),
                comp_id=comp.get("id"),
                library_id=comp.get("library_id"),
            )
            if item:
                item.setPos(comp.get("x", 0), comp.get("y", 0))
                rot = comp.get("rotation", 0)
                item.setRotation(rot)
                # Restore flip state
                from PyQt6.QtGui import QTransform
                fh = comp.get("flip_h", False)
                fv = comp.get("flip_v", False)
                if fh or fv:
                    t = QTransform(
                        -1.0 if fh else 1.0, 0, 0,
                        0, -1.0 if fv else 1.0, 0,
                        0, 0, 1,
                    )
                    item.setTransform(t)
                item._flip_h_active = fh
                item._flip_v_active = fv
                # Issue 14: restore per-label visibility flags
                item._ref_visible = comp.get("ref_visible", True)
                item._val_visible = comp.get("val_visible", True)
                item._refresh_labels()
                # Feature #7: restore component color
                if "color" in comp:
                    item._color = comp["color"]
                # Issue 14: restore extra-property visibility for UserComponentItem
                from ..components.user_component import UserComponentItem
                if isinstance(item, UserComponentItem):
                    ev = comp.get("extra_visible")
                    if ev and isinstance(ev, list):
                        for i, v in enumerate(ev):
                            if i < len(item._extra_visible):
                                item._extra_visible[i] = bool(v)
                    item._refresh_extra_labels()
                    # Bug 4 fix: run extra-label layout BEFORE restoring explicit
                    # label positions so the restore wins over auto-layout.
                    item._layout_extra_labels()
                    # Feature 8: apply perspective offsets based on saved rotation
                    item._apply_perspective_label_offsets()
                # Restore label positions, migrating from old format if needed
                lrp = comp.get("label_ref_pos")
                if lrp:
                    if label_format < 2:
                        lrp = _migrate_label_pos(lrp, rot)
                    item._ref_label.setPos(QPointF(lrp[0], lrp[1]))
                lvp = comp.get("label_val_pos")
                if lvp:
                    if label_format < 2:
                        lvp = _migrate_label_pos(lvp, rot)
                    item._val_label.setPos(QPointF(lvp[0], lvp[1]))
                # Issue 9: restore per-instance label colors
                lrc = comp.get("label_ref_color")
                if lrc:
                    try:
                        item._ref_label.setBrush(QBrush(QColor(lrc)))
                    except (ValueError, RuntimeError):
                        pass
                lvc = comp.get("label_val_color")
                if lvc:
                    try:
                        item._val_label.setBrush(QBrush(QColor(lvc)))
                    except (ValueError, RuntimeError):
                        pass
                self.addItem(item)

        # Wires are auto-generated — no need to restore from file
        self._rebuild_auto_wires()

        # Feature #6: restore annotation items
        from ..canvas.annotation import AnnotationItem
        for anno in self.circuit.annotations:
            try:
                anno_item = AnnotationItem.from_dict(anno)
                if not self._annotation_layer_visible:
                    anno_item.setVisible(False)
                self.addItem(anno_item)
            except Exception:
                pass

    def apply_netlist(self, netlist_text: str) -> None:
        """Parse netlist and reconstruct scene.

        Automatically detects XCIT format (contains ``.xcit_layout``) and
        uses position data from the file when present.
        """
        if ".xcit_layout" in netlist_text:
            self._apply_xcit_netlist(netlist_text)
            return

        from ..io.netlist_parser import parse_netlist, layout_components

        components = parse_netlist(netlist_text)
        self.circuit.clear()
        positions = layout_components(components)

        for i, comp in enumerate(components):
            pos = positions[i]
            comp_id = str(uuid.uuid4())
            comp_dict: dict[str, Any] = {
                "id": comp_id,
                "type": comp.get("type", "R"),
                "ref": comp.get("ref", "X1"),
                "value": comp.get("value", ""),
                "params": comp.get("params", {}),
                "x": pos[0],
                "y": pos[1],
                "rotation": 0,
            }
            self.circuit.add_component(comp_dict)

        self.rebuild_from_circuit()

    def _apply_xcit_netlist(self, xcit_text: str) -> None:
        """Parse an XCIT extended netlist and reconstruct scene with stored positions."""
        from ..io.xcit_netlist import parse_xcit_netlist
        from ..io.netlist_parser import layout_components
        from ..models.library_system import LibraryManager

        components, positions, virtual_comps, label_format, annotations = \
            parse_xcit_netlist(xcit_text)
        self.circuit.clear()
        # Store format so rebuild_from_circuit uses the right label migration
        self.circuit.label_format = label_format

        lm = LibraryManager()

        # Assign positions from layout section; fall back to auto-layout
        auto_positions = layout_components(components)
        for i, comp in enumerate(components):
            ref = comp.get("ref", "X1")
            pos_data = positions.get(ref)
            if pos_data:
                x, y = pos_data["x"], pos_data["y"]
                rot = pos_data.get("rotation", 0)
                fh = pos_data.get("flip_h", False)
                fv = pos_data.get("flip_v", False)
                lrp = pos_data.get("label_ref_pos", None)
                lvp = pos_data.get("label_val_pos", None)
                # Issue 9: restore color metadata from XCIT JSON field
                comp_color = pos_data.get("color")
                lrc = pos_data.get("label_ref_color")
                lvc = pos_data.get("label_val_color")
                ref_vis = pos_data.get("ref_visible", True)
                val_vis = pos_data.get("val_visible", True)
            else:
                x, y = auto_positions[i]
                rot, fh, fv = 0, False, False
                lrp, lvp = None, None
                comp_color = lrc = lvc = None
                ref_vis = val_vis = True

            comp_id = str(uuid.uuid4())
            # Use type_name from the layout section when available so that
            # user-defined components are not misidentified by the SPICE parser
            # (which can only guess type from the reference prefix letter).
            resolved_type = (pos_data.get("type_name") if pos_data else None) \
                or comp.get("type", "R")
            lib_id = pos_data.get("library_id") if pos_data else None

            # Fix 1: Correct node/value split using known pin count from library.
            # The SPICE parser always takes the last token as the value, but for
            # multi-pin components with no value this misidentifies the last node.
            comp = _fix_node_value_split(comp, resolved_type, lib_id, lm)

            comp_dict: dict[str, Any] = {
                "id": comp_id,
                "type": resolved_type,
                "library_id": lib_id,
                "ref": ref,
                "value": comp.get("value", ""),
                "params": comp.get("params", {}),
                "x": x,
                "y": y,
                "rotation": rot,
                "flip_h": fh,
                "flip_v": fv,
            }
            if lrp:
                comp_dict["label_ref_pos"] = lrp
            if lvp:
                comp_dict["label_val_pos"] = lvp
            # Issue 9: persist color info from XCIT metadata
            if comp_color:
                comp_dict["color"] = comp_color
            if lrc:
                comp_dict["label_ref_color"] = lrc
            if lvc:
                comp_dict["label_val_color"] = lvc
            comp_dict["ref_visible"] = ref_vis
            comp_dict["val_visible"] = val_vis
            self.circuit.add_component(comp_dict)

        # Issue 5: Restore virtual (non-SPICE) components from .xcit_virtual section
        for vcomp in virtual_comps:
            comp_id = str(uuid.uuid4())
            comp_dict = {
                "id": comp_id,
                "type": vcomp["type"],
                "library_id": vcomp.get("library_id"),
                "ref": vcomp.get("ref", "V?"),
                "value": "",
                "params": {},
                "x": vcomp.get("x", 0.0),
                "y": vcomp.get("y", 0.0),
                "rotation": vcomp.get("rotation", 0),
                "flip_h": vcomp.get("flip_h", False),
                "flip_v": vcomp.get("flip_v", False),
            }
            if vcomp.get("color"):
                comp_dict["color"] = vcomp["color"]
            self.circuit.add_component(comp_dict)

        # Fix 11: Restore annotations from XCIT annotation section
        for anno in annotations:
            self.circuit.add_annotation(anno)

        # Wires are auto-generated on rebuild
        self.rebuild_from_circuit()

    # ------------------------------------------------------------------
    # Keyboard
    # ------------------------------------------------------------------

    def keyPressEvent(self, event: Any) -> None:
        key = event.key()
        modifiers = event.modifiers()
        ctrl = modifiers & Qt.KeyboardModifier.ControlModifier

        # ── Shortcuts that work during component placement (ghost present) ──
        # Bug 1 fix: work whenever a ghost is shown (incl. during palette drag)
        if self._ghost is not None:
            if key == Qt.Key.Key_R and not ctrl:
                self._ghost._rotate_cw()
                return
            elif key == Qt.Key.Key_F and not ctrl:
                self._ghost._flip_h()
                return
            elif key == Qt.Key.Key_V and not ctrl:
                self._ghost._flip_v()
                return

        changed = False
        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            from ..canvas.annotation import AnnotationItem, TextAnnotationItem
            selected_comps = [
                it for it in self.selectedItems()
                if isinstance(it, ComponentItem)
            ]
            selected_wires = [
                it for it in self.selectedItems()
                if isinstance(it, WireItem)
            ]
            selected_annos = [
                it for it in self.selectedItems()
                if isinstance(it, (AnnotationItem, TextAnnotationItem))
            ]
            if selected_comps or selected_wires or selected_annos:
                before = self._take_snapshot()
                for item in selected_comps:
                    self.circuit.remove_component(item.component_id)
                    self.removeItem(item)
                    changed = True
                for item in selected_wires:
                    self.circuit.remove_wire(item.wire_id)
                    self.removeItem(item)
                for item in selected_annos:
                    self.circuit.remove_annotation(item.anno_id)
                    self.removeItem(item)
                if changed:
                    self._rebuild_auto_wires()
                after = self._take_snapshot()
                self._push_undo("Delete", before, after)
            return
        elif key == Qt.Key.Key_C and ctrl:
            # Copy selected components to clipboard
            self.sync_to_circuit()
            self._clipboard = []
            for item in self.selectedItems():
                if isinstance(item, ComponentItem):
                    comp = self.circuit.get_component(item.component_id)
                    if comp:
                        self._clipboard.append(copy.deepcopy(comp))
        elif key == Qt.Key.Key_V and ctrl:
            # Bug 4 fix: Paste at the current mouse cursor position.
            # The pasted items are kept selected so they can be immediately dragged.
            if self._clipboard:
                before = self._take_snapshot()
                # Centre the pasted group at the snapped mouse position
                paste_cx, paste_cy = snap_to_grid(
                    self._last_mouse_scene_pos.x(),
                    self._last_mouse_scene_pos.y(),
                )
                # Find the bounding centre of the clipboard items
                xs = [c.get("x", 0.0) for c in self._clipboard]
                ys = [c.get("y", 0.0) for c in self._clipboard]
                orig_cx = (min(xs) + max(xs)) / 2 if xs else 0.0
                orig_cy = (min(ys) + max(ys)) / 2 if ys else 0.0
                dx = paste_cx - orig_cx
                dy = paste_cy - orig_cy
                new_ids: list[str] = []
                for comp_data in self._clipboard:
                    new_comp = copy.deepcopy(comp_data)
                    new_id = str(uuid.uuid4())
                    new_comp["id"] = new_id
                    new_comp["x"] = comp_data.get("x", 0.0) + dx
                    new_comp["y"] = comp_data.get("y", 0.0) + dy
                    m = re.match(r'^([A-Za-z_]+)', comp_data.get("ref", "X"))
                    prefix = m.group(1) if m else "X"
                    new_comp["ref"] = self.circuit.next_ref(prefix)
                    self.circuit.add_component(new_comp)
                    new_ids.append(new_id)
                self.rebuild_from_circuit()
                # Select only the newly pasted items
                self.clearSelection()
                for it in self.items():
                    if isinstance(it, ComponentItem) and it.component_id in new_ids:
                        it.setSelected(True)
                after = self._take_snapshot()
                self._push_undo("Paste", before, after)
            return
        elif key == Qt.Key.Key_R and not ctrl:
            targets = [
                it for it in self.selectedItems()
                if isinstance(it, ComponentItem)
            ]
            if targets:
                before = self._take_snapshot()
                for item in targets:
                    item._rotate_cw()
                    changed = True
                after = self._take_snapshot()
                self._push_undo("Rotate", before, after)
        elif key == Qt.Key.Key_F and not ctrl:
            targets = [
                it for it in self.selectedItems()
                if isinstance(it, ComponentItem)
            ]
            if targets:
                before = self._take_snapshot()
                for item in targets:
                    item._flip_h()
                    changed = True
                after = self._take_snapshot()
                self._push_undo("Flip Horizontal", before, after)
        elif key == Qt.Key.Key_V and not ctrl:
            targets = [
                it for it in self.selectedItems()
                if isinstance(it, ComponentItem)
            ]
            if targets:
                before = self._take_snapshot()
                for item in targets:
                    item._flip_v()
                    changed = True
                after = self._take_snapshot()
                self._push_undo("Flip Vertical", before, after)
        elif key == Qt.Key.Key_Escape:
            self._cancel_wire()
            self._anno_cancel()
            # Fix 9: also reset annotation tool to "select" and notify UI
            if self._annotation_tool != "select":
                self._annotation_tool = "select"
                self.annotation_tool_reset.emit()
            self.set_mode(SceneMode.SELECT)
        else:
            super().keyPressEvent(event)
            return

        if changed:
            self._rebuild_auto_wires()

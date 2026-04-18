"""CircuitScene — QGraphicsScene with schematic editing modes."""
from __future__ import annotations

import uuid
from enum import Enum, auto
from typing import Any

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsScene, QGraphicsSceneMouseEvent

from ..canvas.grid import draw_grid, snap_to_grid, GRID_SIZE
from ..components.base import ComponentItem, PinItem
from ..components.wire import WireItem
from ..components.node import JunctionItem, GroundItem, NetLabelItem
from ..models.circuit import Circuit

# Snap radius: within this many pixels of a pin the wire snaps to it.
_PIN_SNAP_RADIUS = GRID_SIZE * 0.8
# Tolerance for treating two coordinates as equal (used for aligned-pin detection).
_COORD_EPSILON = 1.0


class SceneMode(Enum):
    SELECT = auto()
    PLACE_COMPONENT = auto()
    DRAW_WIRE = auto()


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
) -> ComponentItem | None:
    # Check user-defined components first
    try:
        from ..models.user_library import UserLibrary
        ulib = UserLibrary()
        udef = ulib.get(comp_type)
        if udef is not None:
            from ..components.user_component import UserComponentItem
            return UserComponentItem(udef, ref=ref, value=value,
                                     params=params or {}, comp_id=comp_id)
    except Exception:
        pass

    cls = _registry().get(comp_type)
    if cls is None:
        return None
    return cls(ref=ref, value=value, params=params or {}, comp_id=comp_id)


class CircuitScene(QGraphicsScene):
    """Main schematic canvas scene."""

    component_placed = pyqtSignal(dict)
    wire_drawn = pyqtSignal(dict)
    selection_changed_signal = pyqtSignal(list)
    mode_changed = pyqtSignal(str)

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

        self.setBackgroundBrush(QColor("#f8f8f8"))
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
            return

        if self._mode == SceneMode.DRAW_WIRE:
            if event.button() == Qt.MouseButton.LeftButton:
                self._wire_click(snapped)
            elif event.button() == Qt.MouseButton.RightButton:
                self._cancel_wire()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        pos = event.scenePos()
        sx, sy = snap_to_grid(pos.x(), pos.y())
        snapped = QPointF(sx, sy)

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

        super().mouseMoveEvent(event)

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self._mode == SceneMode.DRAW_WIRE:
            pos = event.scenePos()
            sx, sy = snap_to_grid(pos.x(), pos.y())
            self._finish_wire(QPointF(sx, sy))
            return
        super().mouseDoubleClickEvent(event)

    # ------------------------------------------------------------------
    # Placement
    # ------------------------------------------------------------------

    def _place_component(self, pos: QPointF) -> None:
        from ..models.component_library import ComponentLibrary
        from ..models.user_library import UserLibrary
        lib = ComponentLibrary()
        cdef = lib.get(self._pending_type)
        ulib = UserLibrary()
        udef = ulib.get(self._pending_type)

        if cdef is None and udef is None:
            return

        if cdef is not None:
            ref = self.circuit.next_ref(cdef.ref_prefix)
            default_value = cdef.default_value
            default_params = dict(cdef.default_params)
        else:
            assert udef is not None
            ref = self.circuit.next_ref(udef.ref_prefix)
            default_value = udef.default_value
            default_params = {}

        comp_id = str(uuid.uuid4())
        item = create_component_item(
            self._pending_type, ref=ref,
            value=default_value, params=default_params,
            comp_id=comp_id,
        )
        if item is None:
            return
        item.setPos(pos)
        self.addItem(item)

        comp_dict: dict[str, Any] = {
            "id": comp_id,
            "type": self._pending_type,
            "ref": ref,
            "value": default_value,
            "params": default_params,
            "x": pos.x(),
            "y": pos.y(),
            "rotation": 0,
        }
        self.circuit.add_component(comp_dict)
        self.component_placed.emit(comp_dict)

        # Auto-connect aligned pins after placement
        self._auto_connect_component(item)

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
    # Auto-connect (called after component placement)
    # ------------------------------------------------------------------

    def _auto_connect_component(self, new_item: ComponentItem) -> None:
        """After placing *new_item*, auto-draw wires to any H/V aligned pins.

        Checks every pin of *new_item* against every pin of every other
        component.  When two pins share an X (vertical) or Y (horizontal)
        coordinate — with no intervening component blocking the straight line
        — a wire is drawn automatically.
        """
        for pin_name, pin in new_item._pins.items():
            pin_sp = new_item.mapToScene(pin.pos())
            self._try_auto_wire(new_item, pin_name, pin_sp)

    def _try_auto_wire(
        self,
        new_item: ComponentItem,
        new_pin: str,
        pin_sp: QPointF,
    ) -> None:
        """Try to auto-connect pin_sp to any aligned, unobstructed existing pin."""
        search = QRectF(
            pin_sp.x() - 2000, pin_sp.y() - 2000, 4000, 4000
        )
        for item in self.items(search):
            if not isinstance(item, ComponentItem):
                continue
            if item is new_item:
                continue
            for other_pin_name, other_pin in item._pins.items():
                other_sp = item.mapToScene(other_pin.pos())
                dx = abs(other_sp.x() - pin_sp.x())
                dy = abs(other_sp.y() - pin_sp.y())
                is_h_aligned = dy < _COORD_EPSILON and dx > _COORD_EPSILON
                is_v_aligned = dx < _COORD_EPSILON and dy > _COORD_EPSILON
                if not is_h_aligned and not is_v_aligned:
                    continue
                # Avoid duplicate wires
                if self._wire_exists(new_item.component_id, new_pin,
                                     item.component_id, other_pin_name):
                    continue
                # Only draw if path is unobstructed
                if self._is_path_clear(pin_sp, other_sp, {new_item, item}):
                    self._add_auto_wire(
                        pin_sp, other_sp,
                        (new_item.component_id, new_pin),
                        (item.component_id, other_pin_name),
                    )

    def _is_path_clear(
        self,
        p1: QPointF,
        p2: QPointF,
        exclude: set[ComponentItem],
    ) -> bool:
        """Return True if the straight line from p1 to p2 is unobstructed.

        Builds a thin check rectangle along the path (shrinking endpoints by
        a small margin so the endpoint components themselves are not flagged).
        """
        shrink = 6.0
        tol = 4.0
        if abs(p1.y() - p2.y()) < _COORD_EPSILON:
            # Horizontal wire
            x1, x2 = min(p1.x(), p2.x()) + shrink, max(p1.x(), p2.x()) - shrink
            if x2 <= x1:
                return True
            check_rect = QRectF(x1, p1.y() - tol, x2 - x1, 2 * tol)
        else:
            # Vertical wire
            y1, y2 = min(p1.y(), p2.y()) + shrink, max(p1.y(), p2.y()) - shrink
            if y2 <= y1:
                return True
            check_rect = QRectF(p1.x() - tol, y1, 2 * tol, y2 - y1)

        for item in self.items(check_rect):
            if isinstance(item, ComponentItem) and item not in exclude:
                return False
        return True

    def _wire_exists(
        self, c1: str, p1: str, c2: str, p2: str
    ) -> bool:
        """Return True if a wire already connects these two pins."""
        for wire in self.circuit.wires:
            sp = wire.get("start_pin")
            ep = wire.get("end_pin")
            if sp and ep:
                if (sp[0] == c1 and sp[1] == p1 and
                        ep[0] == c2 and ep[1] == p2):
                    return True
                if (sp[0] == c2 and sp[1] == p2 and
                        ep[0] == c1 and ep[1] == p1):
                    return True
        return False

    def _add_auto_wire(
        self,
        start: QPointF,
        end: QPointF,
        start_pin: tuple[str, str],
        end_pin: tuple[str, str],
    ) -> None:
        """Create and register a wire between two pins."""
        wire = WireItem(start, end, wire_id=str(uuid.uuid4()))
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

    def rebuild_from_circuit(self) -> None:
        """Clear and repopulate the scene from self.circuit."""
        for item in list(self.items()):
            self.removeItem(item)

        for comp in self.circuit.components:
            item = create_component_item(
                comp["type"],
                ref=comp.get("ref", "X"),
                value=comp.get("value", ""),
                params=comp.get("params", {}),
                comp_id=comp.get("id"),
            )
            if item:
                item.setPos(comp.get("x", 0), comp.get("y", 0))
                item.setRotation(comp.get("rotation", 0))
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
                # Restore dragged label positions (if previously saved)
                lrp = comp.get("label_ref_pos")
                if lrp:
                    item._ref_label.setPos(QPointF(lrp[0], lrp[1]))
                lvp = comp.get("label_val_pos")
                if lvp:
                    item._val_label.setPos(QPointF(lvp[0], lvp[1]))
                self.addItem(item)

        for wire_data in self.circuit.wires:
            wire = WireItem.from_dict(wire_data)
            self.addItem(wire)

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

        components, positions, wires = parse_xcit_netlist(xcit_text)
        self.circuit.clear()

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
            else:
                x, y = auto_positions[i]
                rot, fh, fv = 0, False, False
                lrp, lvp = None, None

            comp_id = str(uuid.uuid4())
            comp_dict: dict[str, Any] = {
                "id": comp_id,
                "type": comp.get("type", "R"),
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
            self.circuit.add_component(comp_dict)

        # Restore wires
        for wire_data in wires:
            self.circuit.add_wire(wire_data)

        self.rebuild_from_circuit()

    # ------------------------------------------------------------------
    # Keyboard
    # ------------------------------------------------------------------

    def keyPressEvent(self, event: Any) -> None:
        key = event.key()
        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            for item in list(self.selectedItems()):
                if isinstance(item, ComponentItem):
                    self.circuit.remove_component(item.component_id)
                elif isinstance(item, WireItem):
                    self.circuit.remove_wire(item.wire_id)
                self.removeItem(item)
        elif key == Qt.Key.Key_R:
            for item in self.selectedItems():
                if isinstance(item, ComponentItem):
                    item._rotate_cw()
        elif key == Qt.Key.Key_F:
            for item in self.selectedItems():
                if isinstance(item, ComponentItem):
                    item._flip_h()
        elif key == Qt.Key.Key_V:
            for item in self.selectedItems():
                if isinstance(item, ComponentItem):
                    item._flip_v()
        elif key == Qt.Key.Key_Escape:
            self._cancel_wire()
            self.set_mode(SceneMode.SELECT)
        else:
            super().keyPressEvent(event)

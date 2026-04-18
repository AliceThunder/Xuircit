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
            # Snap endpoint to nearby pin if available
            effective_end, _ = self._nearest_pin(snapped)
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

    # ------------------------------------------------------------------
    # Wire drawing
    # ------------------------------------------------------------------

    def _wire_click(self, pos: QPointF) -> None:
        # Prefer snapping to a nearby pin over raw grid position
        pin_pos, pin_info = self._nearest_pin(pos)
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
                self.addItem(item)

        for wire_data in self.circuit.wires:
            wire = WireItem.from_dict(wire_data)
            self.addItem(wire)

    def apply_netlist(self, netlist_text: str) -> None:
        """Parse netlist and reconstruct scene."""
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
            self.set_mode(SceneMode.SELECT)
        else:
            super().keyPressEvent(event)

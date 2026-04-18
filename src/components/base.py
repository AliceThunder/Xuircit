"""Base class for all schematic component graphics items."""
from __future__ import annotations

import uuid
from typing import Any

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPen,
    QTransform,
)
from PyQt6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsSceneContextMenuEvent,
    QGraphicsSceneMouseEvent,
    QGraphicsSimpleTextItem,
    QMenu,
    QStyleOptionGraphicsItem,
    QWidget,
)

GRID = 20  # px
# Minimum Manhattan-length (in scene coords) before a click becomes a drag.
_DRAG_THRESHOLD = 4


def snap(v: float) -> float:
    return round(v / GRID) * GRID


class PinItem(QGraphicsEllipseItem):
    """Small circle marking a pin connection point."""

    RADIUS = 3.5

    def __init__(self, pin_name: str, local_pos: QPointF,
                 parent: "ComponentItem") -> None:
        r = self.RADIUS
        super().__init__(-r, -r, 2 * r, 2 * r, parent)
        self.pin_name = pin_name
        self.setPos(local_pos)
        self.setPen(QPen(QColor("#2277ee"), 1.5))
        self.setBrush(QBrush(QColor("#2277ee")))
        self.setZValue(2)
        self.setVisible(False)
        # Pins must NOT be independently selectable or movable
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)


class LabelItem(QGraphicsSimpleTextItem):
    """A draggable text label attached to a component.

    Without ``ItemIgnoresTransformations`` the label scales with the canvas
    zoom just like the component body.  The label's ``pos()`` is in
    the parent component's *local* coordinate space, so it naturally moves to
    the correct side when the parent is rotated or flipped.

    The ``paint()`` override counter-rotates and counter-flips the text so it
    always appears upright regardless of the parent's orientation.  Text
    alignment (left / right / centre) is inferred automatically from the
    label's scene position relative to the parent component.

    Issue 8: Class-level flag ``_dragging_enabled`` controls whether labels
    can be dragged independently.  Use ``LabelItem.set_dragging_enabled()``
    to toggle from the main window.
    """

    # Issue 8: globally enable/disable label dragging
    _dragging_enabled: bool = True

    @classmethod
    def set_dragging_enabled(cls, enabled: bool) -> None:
        cls._dragging_enabled = enabled

    def __init__(self, text: str, parent: "ComponentItem") -> None:
        super().__init__(text, parent)
        font = QFont("monospace", 8)
        self.setFont(font)
        self.setBrush(QBrush(QColor("#333333")))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        # NOTE: ItemIgnoresTransformations is intentionally NOT set so the
        # label scales with the view zoom like the component body.
        self.setZValue(5)

    def boundingRect(self) -> QRectF:
        """Return a conservative bounding rect centred on the item's origin.

        Issue 3 & 4: The rect must cover the text in ALL orientations
        (any parent rotation + reflection) so that:
          * the hit-test area always overlaps the visible text, and
          * the repaint region always clears the old text position.

        The text is painted after a counter-rotation whose magnitude can be
        up to 360 degrees.  In the worst case a label of size (w x h) can
        appear up to sqrt(w^2+h^2) pixels from the item origin.
        """
        import math
        br = super().boundingRect()
        w, h = br.width(), br.height()
        r = math.sqrt(w * w + h * h) + 6.0
        return QRectF(-r, -r, 2 * r, 2 * r)

    def shape(self):
        """Issue 3: return a shape covering the full boundingRect so the
        entire text area is hittable regardless of the parent's orientation."""
        from PyQt6.QtGui import QPainterPath
        path = QPainterPath()
        path.addRect(self.boundingRect())
        return path

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        import math

        wt = painter.worldTransform()
        # Determinant < 0 means an odd number of reflections are applied.
        det = wt.m11() * wt.m22() - wt.m12() * wt.m21()
        has_reflection = det < 0
        # Rotation angle of the item in device space (degrees, CW positive).
        # When a reflection is present, atan2(m12, m11) returns theta + 180 instead
        # of the true visual rotation theta.  Negate both arguments to recover theta.
        if has_reflection:
            angle_deg = math.degrees(math.atan2(-wt.m12(), -wt.m11()))
        else:
            angle_deg = math.degrees(math.atan2(wt.m12(), wt.m11()))

        br_text = QGraphicsSimpleTextItem.boundingRect(self)
        w, h = br_text.width(), br_text.height()

        # Determine text alignment from scene position.
        # Left side  -> right-align (text ends at anchor)  ax = -w
        # Right side -> left-align  (text starts at anchor) ax = 0
        # Top/Bottom -> left-align per spec                  ax = 0
        ax: float = 0.0  # default: left-align
        parent = self.parentItem()
        if parent is not None:
            lsp = self.mapToScene(QPointF(0.0, 0.0))
            psp = parent.scenePos()
            dx = lsp.x() - psp.x()
            dy = lsp.y() - psp.y()
            if abs(dx) >= abs(dy):
                ax = -w if dx < 0 else 0.0
            # else: top/bottom -> ax stays 0 (left-align)

        painter.save()
        # Counter-rotate so the text is always upright.
        painter.rotate(-angle_deg)
        if has_reflection:
            # Counter the reflection; also swap the horizontal alignment
            # because the x-axis direction is now reversed.
            painter.scale(-1.0, 1.0)
            ax = -ax - w
        # Vertically centre the text around the item's origin.
        painter.translate(ax, -h / 2)
        QGraphicsSimpleTextItem.paint(self, painter, option, widget)
        painter.restore()

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any) -> Any:
        """Issue 4: force scene repaint when position changes to avoid trail."""
        if change in (
            QGraphicsItem.GraphicsItemChange.ItemPositionChange,
            QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged,
        ):
            scene = self.scene()
            if scene is not None:
                # Invalidate a generous area so old selection borders are erased.
                scene.update(scene.sceneRect())
        return super().itemChange(change, value)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Issue 2: prevent independent label drag during batch selection.
        Issue 8: respect the global label-dragging switch."""
        if not LabelItem._dragging_enabled:
            event.ignore()
            return
        # If multiple components are selected, let the parent component
        # handle the drag so the whole group moves together.
        scene = self.scene()
        if scene is not None:
            multi = sum(
                1 for it in scene.selectedItems()
                if isinstance(it, ComponentItem)
            )
            if multi > 1:
                event.ignore()
                return
        super().mousePressEvent(event)


class ComponentItem(QGraphicsItem):
    """Abstract base for all schematic component graphics items."""

    _WIDTH: float = 60.0
    _HEIGHT: float = 40.0

    # Default label offsets (in screen-space relative to parent scene pos).
    # Subclasses override these as (dx, dy) tuples.
    _ref_label_offset: tuple[float, float] = (0.0, -22.0)
    _val_label_offset: tuple[float, float] = (0.0, 14.0)

    # Set to False in subclasses that should not display ref/value labels.
    _show_ref_label: bool = True
    _show_val_label: bool = True

    def __init__(
        self,
        comp_type: str,
        ref: str,
        value: str = "",
        params: dict[str, Any] | None = None,
        comp_id: str | None = None,
        library_id: str | None = None,
    ) -> None:
        super().__init__()
        self.comp_type = comp_type
        self.ref = ref
        self.value = value
        self.params: dict[str, Any] = params or {}
        self.component_id: str = comp_id or str(uuid.uuid4())
        self.library_id: str | None = library_id

        # Issue 14: per-instance label visibility flags
        self._ref_visible: bool = True
        self._val_visible: bool = True

        # We implement dragging manually so we can enforce a drag threshold.
        # ItemIsMovable is intentionally NOT set.
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)

        # Internal drag state
        self._drag_start: QPointF | None = None
        self._drag_orig_pos: QPointF | None = None
        self._dragging: bool = False

        # Flip state tracked explicitly so serialisation is unambiguous
        self._flip_h_active: bool = False
        self._flip_v_active: bool = False

        self._pins: dict[str, PinItem] = {}
        self._build_pins()

        # Draggable, always-upright labels
        self._ref_label = LabelItem(self.ref, self)
        self._ref_label.setPos(QPointF(*self._ref_label_offset))
        self._ref_label.setVisible(self._show_ref_label and self._ref_visible)

        self._val_label = LabelItem(self.value, self)
        self._val_label.setPos(QPointF(*self._val_label_offset))
        self._val_label.setVisible(
            bool(self.value) and self._show_val_label and self._val_visible
        )

    # ------------------------------------------------------------------
    # Override in subclasses
    # ------------------------------------------------------------------

    def _pin_definitions(self) -> dict[str, QPointF]:
        """Return mapping pin_name -> local QPointF. Override in subclass."""
        return {}

    def _draw_symbol(self, painter: QPainter) -> None:
        """Draw the schematic symbol. Override in subclass."""
        painter.drawRect(self.boundingRect())

    # ------------------------------------------------------------------
    # Pin management
    # ------------------------------------------------------------------

    def _build_pins(self) -> None:
        for name, pos in self._pin_definitions().items():
            pin = PinItem(name, pos, self)
            self._pins[name] = pin

    def get_pin_scene_pos(self, pin_name: str) -> QPointF | None:
        pin = self._pins.get(pin_name)
        if pin is None:
            return None
        return self.mapToScene(pin.pos())

    def show_pins(self, visible: bool) -> None:
        for p in self._pins.values():
            p.setVisible(visible)

    # ------------------------------------------------------------------
    # Label helpers
    # ------------------------------------------------------------------

    def _refresh_labels(self) -> None:
        """Sync label text and visibility with current ref/value/flags."""
        self._ref_label.setText(self.ref)
        self._ref_label.setVisible(self._show_ref_label and self._ref_visible)
        self._val_label.setText(self.value)
        self._val_label.setVisible(
            bool(self.value) and self._show_val_label and self._val_visible
        )

    # ------------------------------------------------------------------
    # QGraphicsItem interface
    # ------------------------------------------------------------------

    def boundingRect(self) -> QRectF:
        hw = self._WIDTH / 2
        hh = self._HEIGHT / 2
        return QRectF(-hw - 4, -hh - 4, self._WIDTH + 8, self._HEIGHT + 8)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self.isSelected():
            sel_pen = QPen(QColor("#ff8800"), 1.5, Qt.PenStyle.DashLine)
            painter.setPen(sel_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(
                QRectF(-self._WIDTH / 2 - 3, -self._HEIGHT / 2 - 3,
                       self._WIDTH + 6, self._HEIGHT + 6)
            )

        self._draw_symbol(painter)

    # ------------------------------------------------------------------
    # Hover: show/hide pins
    # ------------------------------------------------------------------

    def hoverEnterEvent(self, event: Any) -> None:
        self.show_pins(True)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event: Any) -> None:
        self.show_pins(False)
        super().hoverLeaveEvent(event)

    # ------------------------------------------------------------------
    # Manual drag implementation (with threshold to prevent jump-on-click)
    # ------------------------------------------------------------------

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.scenePos()
            self._drag_orig_pos = self.pos()
            self._dragging = False
            # Capture before-state for undo (used in mouseReleaseEvent)
            scene = self.scene()
            if (
                scene is not None
                and hasattr(scene, '_take_snapshot')
                and hasattr(scene, 'undo_stack')
                and scene.undo_stack is not None  # type: ignore[union-attr]
            ):
                self._undo_before_snap: Any = scene._take_snapshot()  # type: ignore[union-attr]
            else:
                self._undo_before_snap = None
            # Bug 3 fix: record the original positions of ALL currently-selected
            # ComponentItems so we can move the whole group as one.
            self._drag_group_origins: dict["ComponentItem", QPointF] = {}
            if scene is not None and self.isSelected():
                for it in scene.selectedItems():
                    if isinstance(it, ComponentItem):
                        self._drag_group_origins[it] = it.pos()
            event.accept()
        # Allow the default handler to manage selection
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if (
            self._drag_start is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            delta = event.scenePos() - self._drag_start
            if not self._dragging:
                if (abs(delta.x()) + abs(delta.y())) < _DRAG_THRESHOLD:
                    return  # below threshold – don't start drag yet
                self._dragging = True
            # Bug 3 fix: if we are dragging a group of selected items, move them all.
            group = getattr(self, '_drag_group_origins', {})
            if len(group) > 1:
                for it, orig in group.items():
                    it.setPos(QPointF(snap(orig.x() + delta.x()),
                                     snap(orig.y() + delta.y())))
            else:
                assert self._drag_orig_pos is not None
                new_x = snap(self._drag_orig_pos.x() + delta.x())
                new_y = snap(self._drag_orig_pos.y() + delta.y())
                self.setPos(QPointF(new_x, new_y))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        was_dragging = self._dragging
        undo_before = getattr(self, '_undo_before_snap', None)
        self._drag_start = None
        self._drag_orig_pos = None
        self._dragging = False
        self._undo_before_snap = None
        self._drag_group_origins = {}
        super().mouseReleaseEvent(event)
        if was_dragging:
            scene = self.scene()
            if hasattr(scene, "_rebuild_auto_wires"):
                scene._rebuild_auto_wires()  # type: ignore[union-attr]
            # Push undo for the drag move
            if (
                undo_before is not None
                and hasattr(scene, '_take_snapshot')
                and hasattr(scene, '_push_undo')
            ):
                after = scene._take_snapshot()  # type: ignore[union-attr]
                scene._push_undo("Move Component", undo_before, after)  # type: ignore[union-attr]

    # ------------------------------------------------------------------
    # itemChange – snap externally-set positions (e.g. rebuild_from_circuit)
    # ------------------------------------------------------------------

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any) -> Any:
        if (
            change == QGraphicsItem.GraphicsItemChange.ItemPositionChange
            and not self._dragging
        ):
            return QPointF(snap(value.x()), snap(value.y()))
        return super().itemChange(change, value)

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent) -> None:
        menu = QMenu()
        menu.addAction("Rotate CW  (R)").triggered.connect(
            lambda: self._context_action(self._rotate_cw, "Rotate"))
        menu.addAction("Rotate CCW").triggered.connect(
            lambda: self._context_action(self._rotate_ccw, "Rotate CCW"))
        menu.addAction("Flip Horizontal  (F)").triggered.connect(
            lambda: self._context_action(self._flip_h, "Flip Horizontal"))
        menu.addAction("Flip Vertical  (V)").triggered.connect(
            lambda: self._context_action(self._flip_v, "Flip Vertical"))
        menu.addSeparator()
        menu.addAction("Properties…").triggered.connect(self._open_props)
        menu.addSeparator()
        menu.addAction("Delete").triggered.connect(self._delete_self)
        menu.exec(event.screenPos())

    def _context_action(self, fn: Any, text: str) -> None:
        """Wrap a context-menu action with undo capture."""
        scene = self.scene()
        before = None
        if (
            scene is not None
            and hasattr(scene, '_take_snapshot')
            and hasattr(scene, 'undo_stack')
            and scene.undo_stack is not None  # type: ignore[union-attr]
        ):
            before = scene._take_snapshot()  # type: ignore[union-attr]
        fn()
        if before is not None and hasattr(scene, '_push_undo') and hasattr(scene, '_take_snapshot'):
            after = scene._take_snapshot()  # type: ignore[union-attr]
            scene._push_undo(text, before, after)  # type: ignore[union-attr]

    def _rotate_cw(self) -> None:
        self.setRotation(self.rotation() + 90)
        self._notify_scene_changed()

    def _rotate_ccw(self) -> None:
        self.setRotation(self.rotation() - 90)
        self._notify_scene_changed()

    def _flip_h(self) -> None:
        """Flip horizontally (mirror about vertical axis)."""
        self._flip_h_active = not self._flip_h_active
        t = QTransform(-1, 0, 0, 0, 1, 0, 0, 0, 1) * self.transform()
        self.setTransform(t)
        self._notify_scene_changed()

    def _flip_v(self) -> None:
        """Flip vertically (mirror about horizontal axis)."""
        self._flip_v_active = not self._flip_v_active
        t = QTransform(1, 0, 0, 0, -1, 0, 0, 0, 1) * self.transform()
        self.setTransform(t)
        self._notify_scene_changed()

    def _notify_scene_changed(self) -> None:
        """Notify the scene that this component changed so auto-wires rebuild."""
        scene = self.scene()
        if scene is not None and hasattr(scene, "_rebuild_auto_wires"):
            scene._rebuild_auto_wires()  # type: ignore[union-attr]

    def _delete_self(self) -> None:
        scene = self.scene()
        if scene:
            before = None
            if (
                hasattr(scene, '_take_snapshot')
                and hasattr(scene, 'undo_stack')
                and scene.undo_stack is not None  # type: ignore[union-attr]
            ):
                before = scene._take_snapshot()  # type: ignore[union-attr]
            if hasattr(scene, "circuit") and hasattr(scene.circuit, "remove_component"):
                scene.circuit.remove_component(  # type: ignore[union-attr]
                    self.component_id)
            scene.removeItem(self)
            if hasattr(scene, "_rebuild_auto_wires"):
                scene._rebuild_auto_wires()  # type: ignore[union-attr]
            if before is not None and hasattr(scene, '_push_undo') and hasattr(scene, '_take_snapshot'):
                after = scene._take_snapshot()  # type: ignore[union-attr]
                scene._push_undo("Delete Component", before, after)  # type: ignore[union-attr]

    def _open_props(self) -> None:
        _open_properties(self)

    # ------------------------------------------------------------------
    # Double-click → properties
    # ------------------------------------------------------------------

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        _open_properties(self)
        super().mouseDoubleClickEvent(event)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.component_id,
            "type": self.comp_type,
            "ref": self.ref,
            "value": self.value,
            "params": self.params,
            "x": self.pos().x(),
            "y": self.pos().y(),
            "rotation": self.rotation(),
            "flip_h": self._flip_h_active,
            "flip_v": self._flip_v_active,
            "label_ref_pos": [self._ref_label.pos().x(),
                               self._ref_label.pos().y()],
            "label_val_pos": [self._val_label.pos().x(),
                               self._val_label.pos().y()],
            "ref_visible": self._ref_visible,
            "val_visible": self._val_visible,
        }
        if self.library_id is not None:
            d["library_id"] = self.library_id
        return d


# ------------------------------------------------------------------
# Properties dialog helper
# ------------------------------------------------------------------

def _open_properties(item: "ComponentItem") -> None:
    from PyQt6.QtWidgets import (
        QDialog, QDialogButtonBox, QFormLayout, QLineEdit
    )
    dlg = QDialog()
    dlg.setWindowTitle(f"Properties — {item.ref}")
    layout = QFormLayout(dlg)
    ref_edit = QLineEdit(item.ref)
    val_edit = QLineEdit(item.value)
    layout.addRow("Reference:", ref_edit)
    layout.addRow("Value:", val_edit)
    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok |
        QDialogButtonBox.StandardButton.Cancel
    )
    layout.addRow(buttons)
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    if dlg.exec() == QDialog.DialogCode.Accepted:
        item.ref = ref_edit.text().strip()
        item.value = val_edit.text().strip()
        item._refresh_labels()
        item.update()


# ------------------------------------------------------------------
# Shared pen helper
# ------------------------------------------------------------------

def _std_pen() -> QPen:
    pen = QPen(QColor("#111111"), 2.0)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen

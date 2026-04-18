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
    """A draggable, always-upright text label attached to a component.

    Uses ItemIgnoresTransformations so the text is never rotated/flipped
    regardless of the parent component's transform.  The position (pos())
    is in parent-local coordinates and acts as a direct screen-space offset
    from the parent's scene position.
    """

    def __init__(self, text: str, parent: "ComponentItem") -> None:
        super().__init__(text, parent)
        font = QFont("monospace", 8)
        self.setFont(font)
        self.setBrush(QBrush(QColor("#333333")))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        self.setZValue(5)

    def boundingRect(self) -> QRectF:
        """Return a bounding rect centred on the item's origin."""
        br = super().boundingRect()
        return QRectF(-br.width() / 2, -br.height() / 2,
                      br.width(), br.height())

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        # Shift painter so that the text is drawn centred around the origin.
        br = QGraphicsSimpleTextItem.boundingRect(self)
        painter.translate(-br.width() / 2, -br.height() / 2)
        super().paint(painter, option, widget)


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
    ) -> None:
        super().__init__()
        self.comp_type = comp_type
        self.ref = ref
        self.value = value
        self.params: dict[str, Any] = params or {}
        self.component_id: str = comp_id or str(uuid.uuid4())

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
        self._ref_label.setVisible(self._show_ref_label)

        self._val_label = LabelItem(self.value, self)
        self._val_label.setPos(QPointF(*self._val_label_offset))
        self._val_label.setVisible(bool(self.value) and self._show_val_label)

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
        """Sync label text with current ref/value fields."""
        self._ref_label.setText(self.ref)
        self._ref_label.setVisible(self._show_ref_label)
        self._val_label.setText(self.value)
        self._val_label.setVisible(bool(self.value) and self._show_val_label)

    def _rotate_label_offset(self, label: LabelItem) -> None:
        """Rotate the label offset 90° CW in screen-space (y-down)."""
        p = label.pos()
        # CW 90° in screen (y-down): (x, y) → (-y, x)
        label.setPos(QPointF(-p.y(), p.x()))

    def _rotate_label_offset_ccw(self, label: LabelItem) -> None:
        """Rotate the label offset 90° CCW in screen-space (y-down)."""
        p = label.pos()
        # CCW 90° in screen (y-down): (x, y) → (y, -x)
        label.setPos(QPointF(p.y(), -p.x()))

    def _flip_label_h(self, label: LabelItem) -> None:
        """Mirror label offset about the vertical axis: (x, y) → (-x, y)."""
        p = label.pos()
        label.setPos(QPointF(-p.x(), p.y()))

    def _flip_label_v(self, label: LabelItem) -> None:
        """Mirror label offset about the horizontal axis: (x, y) → (x, -y)."""
        p = label.pos()
        label.setPos(QPointF(p.x(), -p.y()))

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
            assert self._drag_orig_pos is not None
            new_x = snap(self._drag_orig_pos.x() + delta.x())
            new_y = snap(self._drag_orig_pos.y() + delta.y())
            self.setPos(QPointF(new_x, new_y))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        self._drag_start = None
        self._drag_orig_pos = None
        self._dragging = False
        super().mouseReleaseEvent(event)

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
        menu.addAction("Rotate CW  (R)").triggered.connect(self._rotate_cw)
        menu.addAction("Rotate CCW").triggered.connect(self._rotate_ccw)
        menu.addAction("Flip Horizontal  (F)").triggered.connect(self._flip_h)
        menu.addAction("Flip Vertical  (V)").triggered.connect(self._flip_v)
        menu.addSeparator()
        menu.addAction("Properties…").triggered.connect(self._open_props)
        menu.addSeparator()
        menu.addAction("Delete").triggered.connect(self._delete_self)
        menu.exec(event.screenPos())

    def _rotate_cw(self) -> None:
        self.setRotation(self.rotation() + 90)
        self._rotate_label_offset(self._ref_label)
        self._rotate_label_offset(self._val_label)

    def _rotate_ccw(self) -> None:
        self.setRotation(self.rotation() - 90)
        self._rotate_label_offset_ccw(self._ref_label)
        self._rotate_label_offset_ccw(self._val_label)

    def _flip_h(self) -> None:
        """Flip horizontally (mirror about vertical axis)."""
        self._flip_h_active = not self._flip_h_active
        t = QTransform(-1, 0, 0, 0, 1, 0, 0, 0, 1) * self.transform()
        self.setTransform(t)
        self._flip_label_h(self._ref_label)
        self._flip_label_h(self._val_label)

    def _flip_v(self) -> None:
        """Flip vertically (mirror about horizontal axis)."""
        self._flip_v_active = not self._flip_v_active
        t = QTransform(1, 0, 0, 0, -1, 0, 0, 0, 1) * self.transform()
        self.setTransform(t)
        self._flip_label_v(self._ref_label)
        self._flip_label_v(self._val_label)

    def _delete_self(self) -> None:
        scene = self.scene()
        if scene:
            scene.removeItem(self)

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
        return {
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
        }


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

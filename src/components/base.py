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
)
from PyQt6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsSceneContextMenuEvent,
    QGraphicsSceneMouseEvent,
    QMenu,
    QStyleOptionGraphicsItem,
    QWidget,
)

GRID = 20  # px


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


class ComponentItem(QGraphicsItem):
    """Abstract base for all schematic component graphics items."""

    _WIDTH: float = 60.0
    _HEIGHT: float = 40.0

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

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)

        self._pins: dict[str, PinItem] = {}
        self._build_pins()

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
    # QGraphicsItem interface
    # ------------------------------------------------------------------

    def boundingRect(self) -> QRectF:
        hw = self._WIDTH / 2
        hh = self._HEIGHT / 2
        return QRectF(-hw - 4, -hh - 16, self._WIDTH + 8, self._HEIGHT + 28)

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

        font = QFont("monospace", 8)
        painter.setFont(font)
        painter.setPen(QPen(QColor("#333333")))
        painter.drawText(
            QRectF(-self._WIDTH / 2, -self._HEIGHT / 2 - 14,
                   self._WIDTH, 12),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
            self.ref,
        )
        if self.value:
            painter.drawText(
                QRectF(-self._WIDTH / 2, self._HEIGHT / 2 + 2,
                       self._WIDTH, 12),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                self.value,
            )

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
    # Snap on move
    # ------------------------------------------------------------------

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any) -> Any:
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            return QPointF(snap(value.x()), snap(value.y()))
        return super().itemChange(change, value)

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent) -> None:
        menu = QMenu()
        menu.addAction("Rotate CW").triggered.connect(self._rotate_cw)
        menu.addAction("Rotate CCW").triggered.connect(self._rotate_ccw)
        menu.addSeparator()
        menu.addAction("Properties…").triggered.connect(self._open_props)
        menu.addSeparator()
        menu.addAction("Delete").triggered.connect(self._delete_self)
        menu.exec(event.screenPos())

    def _rotate_cw(self) -> None:
        self.setRotation(self.rotation() + 90)

    def _rotate_ccw(self) -> None:
        self.setRotation(self.rotation() - 90)

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
        item.update()


# ------------------------------------------------------------------
# Shared pen helper
# ------------------------------------------------------------------

def _std_pen() -> QPen:
    pen = QPen(QColor("#111111"), 2.0)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen

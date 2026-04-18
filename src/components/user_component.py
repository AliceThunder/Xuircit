"""UserComponentItem — renders a user-defined schematic component."""
from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPen

from .base import ComponentItem, LabelItem, _std_pen
from ..models.user_library import UserCompDef


class UserComponentItem(ComponentItem):
    """A component whose appearance is described by a UserCompDef."""

    def __init__(
        self,
        udef: UserCompDef,
        ref: str = "U1",
        value: str = "",
        params: dict[str, Any] | None = None,
        comp_id: str | None = None,
        library_id: str | None = None,
    ) -> None:
        self._udef = udef
        # Compute bounding box from pin and symbol extents
        all_x: list[float] = []
        all_y: list[float] = []
        for p in udef.pins:
            all_x.append(p.x)
            all_y.append(p.y)
        for s in udef.symbol:
            all_x += [s.x1, s.x2, s.x1 + s.w]
            all_y += [s.y1, s.y2, s.y1 + s.h]
        if all_x and all_y:
            w = max(60.0, abs(max(all_x)) * 2, abs(min(all_x)) * 2)
            h = max(40.0, abs(max(all_y)) * 2, abs(min(all_y)) * 2)
        else:
            w, h = 60.0, 40.0
        self._WIDTH = w
        self._HEIGHT = h
        # Apply label offsets from the user component definition
        self._ref_label_offset = tuple(udef.ref_label_offset)  # type: ignore[assignment]
        self._val_label_offset = tuple(udef.val_label_offset)  # type: ignore[assignment]
        super().__init__(udef.type_name, ref, value, params, comp_id,
                         library_id=library_id)
        # ── Extra labels from udef.labels (beyond ref and value) ─────
        self._extra_labels: list[LabelItem] = []
        for ldef in udef.labels:
            offset = self._label_offset_for(ldef.side, ldef.order)
            item = LabelItem(ldef.text, self)
            item.setPos(offset)
            self._extra_labels.append(item)

    # ------------------------------------------------------------------

    def _label_offset_for(self, side: str, order: int) -> QPointF:
        """Return the parent-local offset for a label given its side and order."""
        hw = self._WIDTH / 2
        hh = self._HEIGHT / 2
        spacing = 14.0  # pixels between labels on the same side
        if side == "left":
            return QPointF(-hw - 14.0, order * spacing)
        if side == "right":
            return QPointF(hw + 14.0, order * spacing)
        if side == "bottom":
            return QPointF(order * 50.0, hh + 12.0)
        # default: "top"
        return QPointF(order * 50.0, -hh - 16.0)

    # ------------------------------------------------------------------
    # Pin definitions from user data
    # ------------------------------------------------------------------

    def _pin_definitions(self) -> dict[str, QPointF]:
        return {p.name: QPointF(p.x, p.y) for p in self._udef.pins}

    # ------------------------------------------------------------------
    # Symbol drawing from stored commands
    # ------------------------------------------------------------------

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(_std_pen())
        painter.setBrush(Qt.BrushStyle.NoBrush)

        if not self._udef.symbol:
            # Default: draw a rectangle with the component name
            painter.setBrush(QBrush(QColor("#fffde7")))
            hw = self._WIDTH / 2
            hh = self._HEIGHT / 2
            painter.drawRect(QRectF(-hw, -hh, self._WIDTH, self._HEIGHT))
            painter.setFont(QFont("monospace", 7))
            painter.setPen(QPen(QColor("#333")))
            painter.drawText(
                QRectF(-hw, -hh, self._WIDTH, self._HEIGHT),
                Qt.AlignmentFlag.AlignCenter,
                self._udef.display_name,
            )
            # Draw pin stubs
            for p in self._udef.pins:
                painter.setPen(QPen(QColor("#2277ee"), 1.5))
                # Stub line from rectangle edge to pin location
                px, py = p.x, p.y
                painter.drawLine(QPointF(px * 0.6, py * 0.6), QPointF(px, py))
                # Pin label
                painter.setFont(QFont("monospace", 6))
                painter.setPen(QPen(QColor("#555")))
                painter.drawText(QPointF(px * 0.62, py * 0.62 + 4), p.name)
            return

        # Render from stored commands
        for cmd in self._udef.symbol:
            painter.setPen(_std_pen())
            painter.setBrush(Qt.BrushStyle.NoBrush)
            if cmd.kind == "line":
                painter.drawLine(QPointF(cmd.x1, cmd.y1), QPointF(cmd.x2, cmd.y2))
            elif cmd.kind == "rect":
                painter.drawRect(QRectF(cmd.x1, cmd.y1, cmd.w, cmd.h))
            elif cmd.kind == "ellipse":
                cx, cy = cmd.x1, cmd.y1
                rx, ry = cmd.w / 2, cmd.h / 2
                painter.drawEllipse(QPointF(cx, cy), rx, ry)
            elif cmd.kind == "text":
                painter.setFont(QFont("monospace", 8))
                painter.setPen(QPen(QColor("#333")))
                painter.drawText(QPointF(cmd.x1, cmd.y1), cmd.text)

    # ------------------------------------------------------------------
    # Pin definitions from user data
    # ------------------------------------------------------------------

    def _pin_definitions(self) -> dict[str, QPointF]:
        return {p.name: QPointF(p.x, p.y) for p in self._udef.pins}

    # ------------------------------------------------------------------
    # Symbol drawing from stored commands
    # ------------------------------------------------------------------

    def _draw_symbol(self, painter: QPainter) -> None:
        painter.setPen(_std_pen())
        painter.setBrush(Qt.BrushStyle.NoBrush)

        if not self._udef.symbol:
            # Default: draw a rectangle with the component name
            painter.setBrush(QBrush(QColor("#fffde7")))
            hw = self._WIDTH / 2
            hh = self._HEIGHT / 2
            painter.drawRect(QRectF(-hw, -hh, self._WIDTH, self._HEIGHT))
            painter.setFont(QFont("monospace", 7))
            painter.setPen(QPen(QColor("#333")))
            painter.drawText(
                QRectF(-hw, -hh, self._WIDTH, self._HEIGHT),
                Qt.AlignmentFlag.AlignCenter,
                self._udef.display_name,
            )
            # Draw pin stubs
            for p in self._udef.pins:
                painter.setPen(QPen(QColor("#2277ee"), 1.5))
                # Stub line from rectangle edge to pin location
                px, py = p.x, p.y
                painter.drawLine(QPointF(px * 0.6, py * 0.6), QPointF(px, py))
                # Pin label
                painter.setFont(QFont("monospace", 6))
                painter.setPen(QPen(QColor("#555")))
                painter.drawText(QPointF(px * 0.62, py * 0.62 + 4), p.name)
            return

        # Render from stored commands
        for cmd in self._udef.symbol:
            painter.setPen(_std_pen())
            painter.setBrush(Qt.BrushStyle.NoBrush)
            if cmd.kind == "line":
                painter.drawLine(QPointF(cmd.x1, cmd.y1), QPointF(cmd.x2, cmd.y2))
            elif cmd.kind == "rect":
                painter.drawRect(QRectF(cmd.x1, cmd.y1, cmd.w, cmd.h))
            elif cmd.kind == "ellipse":
                cx, cy = cmd.x1, cmd.y1
                rx, ry = cmd.w / 2, cmd.h / 2
                painter.drawEllipse(QPointF(cx, cy), rx, ry)
            elif cmd.kind == "text":
                painter.setFont(QFont("monospace", 8))
                painter.setPen(QPen(QColor("#333")))
                painter.drawText(QPointF(cmd.x1, cmd.y1), cmd.text)

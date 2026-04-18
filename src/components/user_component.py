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
        # Keep label offsets outside the body; they will be overridden by
        # the auto-layout below but need sensible defaults for super().__init__.
        hh = h / 2
        self._ref_label_offset = (0.0, -(hh + 16.0))  # type: ignore[assignment]
        self._val_label_offset = (0.0, hh + 16.0)  # type: ignore[assignment]
        super().__init__(udef.type_name, ref, value, params, comp_id,
                         library_id=library_id)

        # Issue 14: extra-property visibility list (one entry per extra prop)
        self._extra_visible: list[bool] = [True] * len(udef.labels)

        # Issue 12: Extra properties (value displayed, not name)
        # Issue 13: Positions computed by auto-layout below.
        self._extra_labels: list[LabelItem] = []
        for ldef in udef.labels:
            # Display the instance value from params; fall back to default_value
            display_text = self.params.get(ldef.text, ldef.default_value)
            item = LabelItem(display_text, self)
            self._extra_labels.append(item)

        # Issue 13: compute non-overlapping layout for all labels
        self._auto_layout_all_labels()

    # ------------------------------------------------------------------
    # Issue 13: non-overlapping label layout
    # ------------------------------------------------------------------

    def _auto_layout_all_labels(self) -> None:
        """Compute and apply non-overlapping positions for all labels.

        Rules (Issue 13):
        - Right, top, bottom sides: left-aligned.
        - Left side: right-aligned.
        - Top: labels arranged bottom-to-top (closest to body = lowest y).
        - Bottom: labels arranged top-to-bottom (closest to body = highest y).
        - Left/Right: symmetric around the component centre; spread up and
          down from centre.
        - Hidden labels do not occupy a position slot.
        """
        hw = self._WIDTH / 2
        hh = self._HEIGHT / 2
        margin = 16.0    # gap from body edge to first label
        spacing = 16.0   # gap between consecutive labels on the same side

        # Collect (label_item, side, order) for labels that will be shown.
        # ref → "top", val → "bottom".
        by_side: dict[str, list[tuple[LabelItem, int]]] = {
            "top": [], "bottom": [], "left": [], "right": []
        }

        if self._show_ref_label and self._ref_visible:
            by_side["top"].append((self._ref_label, -1000))
        if self._show_val_label and self._val_visible and self.value:
            by_side["bottom"].append((self._val_label, -1000))
        for i, (ldef, litem) in enumerate(zip(self._udef.labels,
                                               self._extra_labels)):
            if i < len(self._extra_visible) and not self._extra_visible[i]:
                continue
            side = ldef.side if ldef.side in by_side else "right"
            by_side[side].append((litem, ldef.order))

        # Sort each side by order value
        for side in by_side:
            by_side[side].sort(key=lambda x: x[1])

        # Apply positions
        # Top: bottom-to-top (i=0 at y = -(hh+margin), decreasing y further up)
        for i, (label, _) in enumerate(by_side["top"]):
            label.setPos(QPointF(0.0, -(hh + margin + i * spacing)))

        # Bottom: top-to-bottom (i=0 at y = hh+margin, increasing y further down)
        for i, (label, _) in enumerate(by_side["bottom"]):
            label.setPos(QPointF(0.0, hh + margin + i * spacing))

        # Right: left-aligned, symmetric around centre
        right = [l for l, _ in by_side["right"]]
        n = len(right)
        for i, label in enumerate(right):
            y = (i - (n - 1) / 2.0) * spacing
            label.setPos(QPointF(hw + margin, y))

        # Left: right-aligned, symmetric around centre
        left = [l for l, _ in by_side["left"]]
        n = len(left)
        for i, label in enumerate(left):
            y = (i - (n - 1) / 2.0) * spacing
            label.setPos(QPointF(-(hw + margin), y))

    # ------------------------------------------------------------------
    # Issue 12: refresh extra labels after params change
    # ------------------------------------------------------------------

    def _refresh_extra_labels(self) -> None:
        """Update extra label texts from current params."""
        for i, (ldef, litem) in enumerate(zip(self._udef.labels,
                                               self._extra_labels)):
            display_text = self.params.get(ldef.text, ldef.default_value)
            litem.setText(display_text)
            visible = i < len(self._extra_visible) and self._extra_visible[i]
            litem.setVisible(visible)

    def _refresh_labels(self) -> None:
        """Override to also refresh extra property labels."""
        super()._refresh_labels()
        self._refresh_extra_labels()
        # Re-run layout so hidden labels don't leave gaps
        self._auto_layout_all_labels()

    # ------------------------------------------------------------------
    # Issue 14: serialise extra visibility
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d["extra_visible"] = list(self._extra_visible)
        return d

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
                px, py = p.x, p.y
                painter.drawLine(QPointF(px * 0.6, py * 0.6), QPointF(px, py))
                painter.setFont(QFont("monospace", 6))
                painter.setPen(QPen(QColor("#555")))
                painter.drawText(QPointF(px * 0.62, py * 0.62 + 4), p.name)
            return

        # Render from stored commands
        for cmd in self._udef.symbol:
            painter.setPen(_std_pen())
            # Issue 6: support solid (filled) shapes
            if cmd.filled:
                painter.setBrush(QBrush(QColor("#333333")))
            else:
                painter.setBrush(Qt.BrushStyle.NoBrush)
            if cmd.kind == "line":
                painter.drawLine(QPointF(cmd.x1, cmd.y1),
                                  QPointF(cmd.x2, cmd.y2))
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


"""UserComponentItem — renders a user-defined schematic component."""
from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPen

from .base import ComponentItem, LabelItem, _std_pen
from ..models.user_library import UserCompDef
from .wire import _qt_style as _wire_qt_style


def _apply_label_style(label: LabelItem, style: dict) -> None:
    """Feature 7: apply a style dict to a LabelItem.

    Keys recognised: font_family, font_size, bold, italic, color, alignment.
    Missing keys leave the existing setting unchanged.
    """
    if not style:
        return
    from PyQt6.QtGui import QFont as QF_, QBrush as QB_, QColor as QC_
    fam = style.get("font_family", "")
    sz = int(style.get("font_size", 0))
    bold = bool(style.get("bold", False))
    italic = bool(style.get("italic", False))
    color = str(style.get("color", ""))
    alignment = str(style.get("alignment", ""))

    if fam or sz or bold or italic:
        base = label.font()
        f = QF_(fam if fam else base.family(),
                sz if sz else base.pointSize())
        f.setBold(bold)
        f.setItalic(italic)
        label.setFont(f)
    if color:
        try:
            label.setBrush(QB_(QC_(color)))
        except Exception:
            pass
    # Bug 3 fix: apply explicit alignment override when set
    if alignment in ("left", "center", "right"):
        label._alignment_override = alignment
    elif alignment == "auto" or not alignment:
        # "auto" or empty string means reset to position-based auto-compute
        label._alignment_override = None


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
        # Compute bounding box from pin and symbol extents (used for label placement)
        all_x: list[float] = []
        all_y: list[float] = []
        for p in udef.pins:
            all_x.append(p.x)
            all_y.append(p.y)
        for s in udef.symbol:
            if s.kind == "arc":
                # Arc is center-based (x1=cx, y1=cy); use its actual extents
                all_x += [s.x1 - s.w / 2, s.x1 + s.w / 2]
                all_y += [s.y1 - s.h / 2, s.y1 + s.h / 2]
            else:
                all_x += [s.x1, s.x2, s.x1 + s.w]
                all_y += [s.y1, s.y2, s.y1 + s.h]
            # Feature #3: include polyline points in bounding box
            for pt in s.points:
                if len(pt) >= 2:
                    all_x.append(pt[0])
                    all_y.append(pt[1])
        if all_x and all_y:
            w = max(60.0, abs(max(all_x)) * 2, abs(min(all_x)) * 2)
            h = max(40.0, abs(max(all_y)) * 2, abs(min(all_y)) * 2)
        else:
            w, h = 60.0, 40.0
        self._WIDTH = w
        self._HEIGHT = h

        # Compute body rect from symbol lines only (not pins), using actual
        # min/max bounds.  This is the tight enclosing rect of the drawn symbol
        # and is used for hit-testing, wire-path clearance, and overlap detection.
        # Labels (child items) are intentionally not considered.
        body_x: list[float] = []
        body_y: list[float] = []
        for s in udef.symbol:
            if s.kind == "line":
                body_x += [s.x1, s.x2]
                body_y += [s.y1, s.y2]
            elif s.kind == "rect":
                body_x += [s.x1, s.x1 + s.w]
                body_y += [s.y1, s.y1 + s.h]
            elif s.kind == "ellipse":
                body_x += [s.x1 - s.w / 2, s.x1 + s.w / 2]
                body_y += [s.y1 - s.h / 2, s.y1 + s.h / 2]
            elif s.kind == "arc":
                # Arc is center-based (x1=cx, y1=cy); include full bounding box
                body_x += [s.x1 - s.w / 2, s.x1 + s.w / 2]
                body_y += [s.y1 - s.h / 2, s.y1 + s.h / 2]
            elif s.kind == "polyline":
                for pt in s.points:
                    if len(pt) >= 2:
                        body_x.append(pt[0])
                        body_y.append(pt[1])
        if body_x and body_y:
            _bx1, _bx2 = min(body_x), max(body_x)
            _by1, _by2 = min(body_y), max(body_y)
        else:
            # Fallback: use pin extents or the label-placement dimensions
            _pin_x = [p.x for p in udef.pins]
            _pin_y = [p.y for p in udef.pins]
            if _pin_x and _pin_y:
                _bx1, _bx2 = min(_pin_x), max(_pin_x)
                _by1, _by2 = min(_pin_y), max(_pin_y)
            else:
                _bx1, _by1, _bx2, _by2 = -w / 2, -h / 2, w / 2, h / 2
        self._body_rect = QRectF(_bx1, _by1, _bx2 - _bx1, _by2 - _by1)

        # Bug 4 fix: use the stored label offsets from the component definition
        # instead of computed defaults. The auto-layout will NOT override these.
        ref_off = udef.ref_label_offset if udef.ref_label_offset else [0.0, -(h / 2 + 16.0)]
        val_off = udef.val_label_offset if udef.val_label_offset else [0.0, h / 2 + 16.0]
        self._ref_label_offset = (ref_off[0], ref_off[1])  # type: ignore[assignment]
        self._val_label_offset = (val_off[0], val_off[1])  # type: ignore[assignment]
        # Feature 8: V-perspective offsets (fallback to H if not set)
        self._ref_offset_v: tuple[float, float] = (
            udef.ref_label_offset_v[0], udef.ref_label_offset_v[1]
        ) if udef.ref_label_offset_v else self._ref_label_offset
        self._val_offset_v: tuple[float, float] = (
            udef.val_label_offset_v[0], udef.val_label_offset_v[1]
        ) if udef.val_label_offset_v else self._val_label_offset
        # Bug 3 fix: V-perspective label styles (fallback to H style if not set)
        self._ref_style_v: dict = getattr(udef, "ref_label_style_v", {}) or {}
        self._val_style_v: dict = getattr(udef, "val_label_style_v", {}) or {}

        super().__init__(udef.type_name, ref, value, params, comp_id,
                         library_id=library_id)

        # Issue 14: extra-property visibility list (one entry per extra prop)
        # Initialised here — before the is_virtual check — so that
        # _refresh_labels() (called immediately below for virtual components)
        # can safely call _refresh_extra_labels() without AttributeError.
        self._extra_visible: list[bool] = [True] * len(udef.labels)

        # Issue 12: Extra properties — initialised empty here for the same
        # reason; populated in the loop below after the virtual-component check.
        self._extra_labels: list[LabelItem] = []

        # Bug 2: hide ref/val labels for virtual (wire-connector) components
        if udef.is_virtual:
            self._show_ref_label = False
            self._show_val_label = False
            self._refresh_labels()

        # Feature 7: apply per-label styles to ref and val labels (H perspective)
        _apply_label_style(self._ref_label, udef.ref_label_style)
        _apply_label_style(self._val_label, udef.val_label_style)

        # Issue 12: Extra properties (value displayed, not name)
        # Feature 6: positions come from LabelDef.dx/dy if use_offset=True,
        #             otherwise side-based auto-layout is used.
        for ldef in udef.labels:
            # Display the instance value from params; fall back to default_value
            display_text = self.params.get(ldef.text, ldef.default_value)
            item = LabelItem(display_text, self, edit_info=("extra", ldef.text))
            # Feature 7: apply per-label style
            style = {
                "font_family": ldef.font_family,
                "font_size": ldef.font_size,
                "bold": ldef.bold,
                "italic": ldef.italic,
                "color": ldef.color,
            }
            _apply_label_style(item, style)
            self._extra_labels.append(item)

        # Position extra labels (side-based for those without explicit offsets,
        # explicit offsets for those with use_offset=True)
        self._layout_extra_labels()

    # ------------------------------------------------------------------
    # Bug 4 / Feature 6: extra label layout
    # ------------------------------------------------------------------

    def _layout_extra_labels(self) -> None:
        """Compute and apply positions for extra property labels.

        Labels with ``use_offset=True`` are placed at their stored dx/dy.
        All other labels are arranged using the side-based auto-layout.
        """
        hw = self._WIDTH / 2
        hh = self._HEIGHT / 2
        margin = 16.0    # gap from body edge to first label
        spacing = 16.0   # gap between consecutive labels on the same side

        by_side: dict[str, list[tuple[LabelItem, int]]] = {
            "top": [], "bottom": [], "left": [], "right": []
        }

        for i, (ldef, litem) in enumerate(zip(self._udef.labels,
                                               self._extra_labels)):
            if i < len(self._extra_visible) and not self._extra_visible[i]:
                continue
            if ldef.use_offset:
                # Feature 6: use explicit offset directly
                litem.setPos(QPointF(ldef.dx, ldef.dy))
            else:
                side = ldef.side if ldef.side in by_side else "right"
                by_side[side].append((litem, ldef.order))

        for side in by_side:
            by_side[side].sort(key=lambda x: x[1])

        for i, (label, _) in enumerate(by_side["top"]):
            label.setPos(QPointF(0.0, -(hh + margin + i * spacing)))
        for i, (label, _) in enumerate(by_side["bottom"]):
            label.setPos(QPointF(0.0, hh + margin + i * spacing))
        right = [l for l, _ in by_side["right"]]
        n = len(right)
        for i, label in enumerate(right):
            label.setPos(QPointF(hw + margin, (i - (n - 1) / 2.0) * spacing))
        left = [l for l, _ in by_side["left"]]
        n = len(left)
        for i, label in enumerate(left):
            label.setPos(QPointF(-(hw + margin), (i - (n - 1) / 2.0) * spacing))

    # Keep the old name as an alias so that callers in scene.py still work
    def _auto_layout_all_labels(self) -> None:
        """Alias kept for backward compatibility. Only lays out extra labels now."""
        self._layout_extra_labels()

    # ------------------------------------------------------------------
    # Issue 2: tight bounding rect based on symbol lines only
    # ------------------------------------------------------------------

    def boundingRect(self) -> QRectF:
        """Return the minimum enclosing rect of the drawn symbol lines.

        Only symbol drawing commands contribute (not pin positions or labels).
        A 4 px padding is added on all sides to accommodate pen widths and
        anti-aliasing without clipping any drawn pixels.
        """
        return self._body_rect.adjusted(-4.0, -4.0, 4.0, 4.0)

    def _on_rotation_changed(self) -> None:
        """Feature 8: update label positions when the component is rotated."""
        self._apply_perspective_label_offsets()

    def _apply_perspective_label_offsets(self) -> None:
        """Feature 8 / Bug 3 fix: apply H or V label offsets and alignment based on rotation.

        Horizontal (0° / 180°): use H offsets + H alignment.
        Vertical (90° / 270°): use V offsets + V alignment.
        """
        import math
        angle = self.rotation() % 360.0
        # Consider 90° and 270° as "vertical" perspective
        is_vertical = 80.0 < angle < 100.0 or 260.0 < angle < 280.0
        if is_vertical and hasattr(self, "_ref_offset_v"):
            self._ref_label.setPos(QPointF(*self._ref_offset_v))
            self._val_label.setPos(QPointF(*self._val_offset_v))
            # Bug 3 fix: apply V-perspective alignment (fall back to H style if not set)
            _apply_label_style(self._ref_label,
                               self._ref_style_v if self._ref_style_v
                               else self._udef.ref_label_style)
            _apply_label_style(self._val_label,
                               self._val_style_v if self._val_style_v
                               else self._udef.val_label_style)
        else:
            self._ref_label.setPos(QPointF(*self._ref_label_offset))
            self._val_label.setPos(QPointF(*self._val_label_offset))
            # Bug 3 fix: apply H-perspective alignment
            _apply_label_style(self._ref_label, self._udef.ref_label_style)
            _apply_label_style(self._val_label, self._udef.val_label_style)
        # Also apply explicit offsets to extra labels
        is_v_flag = is_vertical
        for i, (ldef, litem) in enumerate(zip(self._udef.labels,
                                               self._extra_labels)):
            if ldef.use_offset:
                dx = ldef.dx_v if (is_v_flag and (ldef.dx_v or ldef.dy_v)) else ldef.dx
                dy = ldef.dy_v if (is_v_flag and (ldef.dx_v or ldef.dy_v)) else ldef.dy
                litem.setPos(QPointF(dx, dy))

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
        self._layout_extra_labels()

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
        painter.setPen(_std_pen(self._color))
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
            painter.setPen(_cmd_pen(
                self._color,
                getattr(cmd, "line_style", "solid"),
                float(getattr(cmd, "line_width", 2.0)),
            ))
            # Issue 6: support solid (filled) shapes
            if cmd.filled:
                painter.setBrush(QBrush(QColor(self._color)))
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
            elif cmd.kind == "polyline":
                # Feature #3: multi-segment polyline
                pts = cmd.points
                if len(pts) >= 2:
                    from PyQt6.QtGui import QPainterPath
                    path = QPainterPath()
                    path.moveTo(QPointF(pts[0][0], pts[0][1]))
                    for px, py in pts[1:]:
                        path.lineTo(QPointF(px, py))
                    if cmd.filled and len(pts) >= 3:
                        path.closeSubpath()
                        painter.fillPath(path, QBrush(QColor(self._color)))
                    painter.drawPath(path)
            elif cmd.kind == "arc":
                from PyQt6.QtGui import QPainterPath
                cx, cy = cmd.x1, cmd.y1
                rx, ry = cmd.w / 2, cmd.h / 2
                arc_rect = QRectF(cx - rx, cy - ry, cmd.w, cmd.h)
                path = QPainterPath()
                path.arcMoveTo(arc_rect, cmd.start_angle)
                path.arcTo(arc_rect, cmd.start_angle, cmd.span_angle)
                painter.drawPath(path)
def _cmd_pen(color: str, style_name: str, width: float) -> QPen:
    pen = QPen(QColor(color), width)
    pen.setStyle(_wire_qt_style(style_name))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


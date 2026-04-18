"""CircuitView — QGraphicsView with zoom and pan."""
from __future__ import annotations

from PyQt6.QtCore import QPointF, Qt, pyqtSignal
from PyQt6.QtGui import QPainter, QWheelEvent
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsView


class CircuitView(QGraphicsView):
    """Zoomable, pannable view of the circuit canvas."""

    zoom_changed = pyqtSignal(float)

    _ZOOM_FACTOR = 1.15
    _ZOOM_MIN = 0.05
    _ZOOM_MAX = 12.0

    def __init__(self, scene: QGraphicsScene, parent: object = None) -> None:
        super().__init__(scene, parent)  # type: ignore[arg-type]
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing |
            QPainter.RenderHint.TextAntialiasing
        )
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )
        self.setResizeAnchor(
            QGraphicsView.ViewportAnchor.AnchorViewCenter
        )
        self._zoom_level: float = 1.0
        self._panning = False
        self._pan_start_x = 0
        self._pan_start_y = 0
        # Accept external drag-and-drop from the component palette (Issue 2)
        self.setAcceptDrops(True)

    # ------------------------------------------------------------------
    # Zoom
    # ------------------------------------------------------------------

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self._apply_zoom(self._ZOOM_FACTOR)
            else:
                self._apply_zoom(1.0 / self._ZOOM_FACTOR)
            event.accept()
        else:
            super().wheelEvent(event)

    def _apply_zoom(self, factor: float) -> None:
        new_zoom = self._zoom_level * factor
        if new_zoom < self._ZOOM_MIN or new_zoom > self._ZOOM_MAX:
            return
        self.scale(factor, factor)
        self._zoom_level = new_zoom
        self.zoom_changed.emit(self._zoom_level)

    def zoom_in(self) -> None:
        self._apply_zoom(self._ZOOM_FACTOR)

    def zoom_out(self) -> None:
        self._apply_zoom(1.0 / self._ZOOM_FACTOR)

    def fit_all(self) -> None:
        items = self.scene().items()
        if not items:
            return
        rect = self.scene().itemsBoundingRect()
        rect = rect.adjusted(-40, -40, 40, 40)
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        self._zoom_level = self.transform().m11()
        self.zoom_changed.emit(self._zoom_level)

    # ------------------------------------------------------------------
    # Middle-mouse pan
    # ------------------------------------------------------------------

    def mousePressEvent(self, event: object) -> None:
        from PyQt6.QtGui import QMouseEvent
        if isinstance(event, QMouseEvent) and event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_start_x = event.position().x()
            self._pan_start_y = event.position().y()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)  # type: ignore[arg-type]

    def mouseMoveEvent(self, event: object) -> None:
        from PyQt6.QtGui import QMouseEvent
        if isinstance(event, QMouseEvent) and self._panning:
            dx = event.position().x() - self._pan_start_x
            dy = event.position().y() - self._pan_start_y
            self._pan_start_x = event.position().x()
            self._pan_start_y = event.position().y()
            self.horizontalScrollBar().setValue(
                int(self.horizontalScrollBar().value() - dx)
            )
            self.verticalScrollBar().setValue(
                int(self.verticalScrollBar().value() - dy)
            )
            event.accept()
            return
        super().mouseMoveEvent(event)  # type: ignore[arg-type]

    def mouseReleaseEvent(self, event: object) -> None:
        from PyQt6.QtGui import QMouseEvent
        if isinstance(event, QMouseEvent) and event.button() == Qt.MouseButton.MiddleButton:
            self._panning = False
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Drag-and-drop from component palette (Issue 2)
    # ------------------------------------------------------------------

    _PALETTE_MIME = "application/x-xuircit-component"

    def dragEnterEvent(self, event: object) -> None:
        from PyQt6.QtGui import QDragEnterEvent
        if isinstance(event, QDragEnterEvent) and event.mimeData().hasFormat(
            self._PALETTE_MIME
        ):
            comp_type = (
                event.mimeData().data(self._PALETTE_MIME).data().decode("utf-8")
            )
            scene = self.scene()
            # Bug 1 fix: switch to PLACE_COMPONENT mode so R/F/V shortcuts work
            if hasattr(scene, "set_mode") and hasattr(scene, "SceneMode"):
                pass  # SceneMode is module-level; import directly
            if hasattr(scene, "set_pending_component"):
                from ..canvas.scene import SceneMode
                if hasattr(scene, "set_mode"):
                    scene.set_mode(SceneMode.PLACE_COMPONENT)  # type: ignore[union-attr]
            # Create a ghost preview if one is not already showing
            if (
                hasattr(scene, "set_pending_component")
                and hasattr(scene, "_ghost")
                and scene._ghost is None  # type: ignore[union-attr]
            ):
                scene.set_pending_component(comp_type)  # type: ignore[union-attr]
            # Bug 1 / Bug 2 fix: take keyboard focus so R/F/V reach the scene
            self.setFocus(Qt.FocusReason.OtherFocusReason)
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)  # type: ignore[arg-type]

    def dragMoveEvent(self, event: object) -> None:
        from PyQt6.QtGui import QDragMoveEvent
        if isinstance(event, QDragMoveEvent) and event.mimeData().hasFormat(
            self._PALETTE_MIME
        ):
            scene = self.scene()
            if hasattr(scene, "_ghost") and scene._ghost is not None:  # type: ignore[union-attr]
                from ..canvas.grid import snap_to_grid
                view_pos = event.position().toPoint()
                sp = self.mapToScene(view_pos)
                sx, sy = snap_to_grid(sp.x(), sp.y())
                scene._ghost.setPos(QPointF(sx, sy))  # type: ignore[union-attr]
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)  # type: ignore[arg-type]

    def dragLeaveEvent(self, event: object) -> None:
        scene = self.scene()
        if hasattr(scene, "_clear_ghost"):
            scene._clear_ghost()  # type: ignore[union-attr]
        super().dragLeaveEvent(event)  # type: ignore[arg-type]

    def dropEvent(self, event: object) -> None:
        from PyQt6.QtGui import QDropEvent
        if isinstance(event, QDropEvent) and event.mimeData().hasFormat(
            self._PALETTE_MIME
        ):
            scene = self.scene()
            from ..canvas.grid import snap_to_grid
            view_pos = event.position().toPoint()
            sp = self.mapToScene(view_pos)
            sx, sy = snap_to_grid(sp.x(), sp.y())
            if hasattr(scene, "_place_component") and hasattr(scene, "_pending_type"):
                if scene._pending_type:  # type: ignore[union-attr]
                    scene._place_component(QPointF(sx, sy))  # type: ignore[union-attr]
            if hasattr(scene, "_clear_ghost"):
                scene._clear_ghost()  # type: ignore[union-attr]
            event.acceptProposedAction()
        else:
            super().dropEvent(event)  # type: ignore[arg-type]

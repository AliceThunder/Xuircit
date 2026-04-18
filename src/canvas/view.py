"""CircuitView — QGraphicsView with zoom and pan."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
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

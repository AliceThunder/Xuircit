"""Layers panel — controls for component layer and annotation layer."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QDockWidget,
    QGroupBox,
    QVBoxLayout,
    QWidget,
)


class LayersPanel(QDockWidget):
    """Layer visibility controls.

    Emits:
    - component_layer_toggled(bool): component layer visibility changed
    - annotation_layer_toggled(bool): annotation layer visibility changed
    """

    component_layer_toggled = pyqtSignal(bool)
    annotation_layer_toggled = pyqtSignal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__("Layers", parent)
        self.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea |
            Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.setMinimumWidth(180)

        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(6, 6, 6, 6)

        # ── Layer visibility ──────────────────────────────────────────
        vis_box = QGroupBox("Layer Visibility")
        vis_layout = QVBoxLayout(vis_box)

        self._comp_layer_cb = QCheckBox("Component Layer")
        self._comp_layer_cb.setChecked(True)
        self._comp_layer_cb.setToolTip(
            "Show / hide the component drawing layer.\n"
            "Components and wires are placed on this layer."
        )
        self._comp_layer_cb.toggled.connect(self.component_layer_toggled.emit)

        self._anno_layer_cb = QCheckBox("Annotation Layer")
        self._anno_layer_cb.setChecked(True)
        self._anno_layer_cb.setToolTip(
            "Show / hide the annotation drawing layer.\n"
            "Use this layer for arrows, circles, and other annotations."
        )
        self._anno_layer_cb.toggled.connect(self.annotation_layer_toggled.emit)

        vis_layout.addWidget(self._comp_layer_cb)
        vis_layout.addWidget(self._anno_layer_cb)
        layout.addWidget(vis_box)

        layout.addStretch()

        self.setWidget(w)

    def set_component_layer_visible(self, visible: bool) -> None:
        self._comp_layer_cb.setChecked(visible)

    def set_annotation_layer_visible(self, visible: bool) -> None:
        self._anno_layer_cb.setChecked(visible)

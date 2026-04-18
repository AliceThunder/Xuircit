"""Layers panel — controls for component layer and annotation layer (Feature #6)."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDockWidget,
    QGroupBox,
    QHBoxLayout,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)


class LayersPanel(QDockWidget):
    """Feature #6: Layer visibility controls and annotation drawing tools.

    Emits:
    - component_layer_toggled(bool): component layer visibility changed
    - annotation_layer_toggled(bool): annotation layer visibility changed
    - annotation_tool_selected(str): one of "select", "line", "arrow",
      "circle", "ellipse", "rect", "polyline" selected for drawing
    """

    component_layer_toggled = pyqtSignal(bool)
    annotation_layer_toggled = pyqtSignal(bool)
    annotation_tool_selected = pyqtSignal(str)

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

        # ── Annotation tools ──────────────────────────────────────────
        anno_box = QGroupBox("Annotation Tools")
        anno_layout = QVBoxLayout(anno_box)

        self._tool_group = QButtonGroup(self)
        tools = [
            ("⬚ Select",   "select",   "Select / move annotations"),
            ("╱ Line",     "line",     "Draw a straight line annotation"),
            ("→ Arrow",    "arrow",    "Draw an arrow annotation"),
            ("◯ Circle",   "circle",   "Draw a circle (click centre, drag radius)"),
            ("⬭ Ellipse",  "ellipse",  "Draw an ellipse (drag bounding box)"),
            ("▭ Rect",     "rect",     "Draw a rectangle annotation"),
            ("⌇ Polyline", "polyline", "Draw a polyline (right-click to finish)"),
        ]
        for label, tool_name, tooltip in tools:
            rb = QRadioButton(label)
            rb.setToolTip(tooltip)
            rb.setProperty("tool", tool_name)
            rb.toggled.connect(
                lambda checked, t=tool_name: self._on_tool(checked, t)
            )
            self._tool_group.addButton(rb)
            anno_layout.addWidget(rb)

        # Select is checked by default
        self._tool_group.buttons()[0].setChecked(True)

        layout.addWidget(anno_box)
        layout.addStretch()

        self.setWidget(w)

    def _on_tool(self, checked: bool, tool: str) -> None:
        if checked:
            self.annotation_tool_selected.emit(tool)

    def set_component_layer_visible(self, visible: bool) -> None:
        self._comp_layer_cb.setChecked(visible)

    def set_annotation_layer_visible(self, visible: bool) -> None:
        self._anno_layer_cb.setChecked(visible)

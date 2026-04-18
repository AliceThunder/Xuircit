"""Properties panel dock widget."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDockWidget,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class PropertiesPanel(QDockWidget):
    """Right dock: shows and edits properties of the selected component."""

    def __init__(self, parent: object = None) -> None:
        super().__init__("Properties", parent)  # type: ignore[arg-type]
        self.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea |
            Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.setMinimumWidth(200)

        self._current_item: object = None

        outer = QWidget()
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(4, 4, 4, 4)

        self._placeholder = QLabel("Select a component to\nview its properties.")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer_layout.addWidget(self._placeholder)

        # Form area (hidden when nothing selected)
        self._form_widget = QWidget()
        self._form = QFormLayout(self._form_widget)
        self._ref_edit = QLineEdit()
        self._val_edit = QLineEdit()
        self._form.addRow("Reference:", self._ref_edit)
        self._form.addRow("Value:", self._val_edit)

        self._apply_btn = QPushButton("Apply")
        self._apply_btn.clicked.connect(self._apply)
        self._form.addRow(self._apply_btn)

        outer_layout.addWidget(self._form_widget)
        self._form_widget.setVisible(False)

        outer_layout.addStretch()
        self.setWidget(outer)

    def show_component(self, item: object) -> None:
        from ..components.base import ComponentItem
        if not isinstance(item, ComponentItem):
            self.clear()
            return
        self._current_item = item
        self._ref_edit.setText(item.ref)
        self._val_edit.setText(item.value)
        self._placeholder.setVisible(False)
        self._form_widget.setVisible(True)

    def clear(self) -> None:
        self._current_item = None
        self._placeholder.setVisible(True)
        self._form_widget.setVisible(False)

    def _apply(self) -> None:
        from ..components.base import ComponentItem
        if not isinstance(self._current_item, ComponentItem):
            return
        self._current_item.ref = self._ref_edit.text().strip()
        self._current_item.value = self._val_edit.text().strip()
        self._current_item.update()

"""Properties panel dock widget."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDockWidget,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class PropertiesPanel(QDockWidget):
    """Right dock: shows and edits properties of the selected component.

    Issue 11: _apply() now calls _refresh_labels() so label text
              updates immediately after applying changes.
    Issue 12: Extra properties for UserComponentItem are shown with
              their names as row labels and their values as edit fields.
    Issue 14: Visibility checkboxes for ref, value, and extra properties.
    """

    def __init__(self, parent: object = None) -> None:
        super().__init__("Properties", parent)  # type: ignore[arg-type]
        self.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea |
            Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.setMinimumWidth(220)

        self._current_item: object = None
        # Extra-property edit boxes: list of (property_name, QLineEdit)
        self._extra_edits: list[tuple[str, QLineEdit]] = []
        # Visibility checkboxes: {key: QCheckBox}  key = "ref" | "val" | "extra_N"
        self._vis_checks: dict[str, QCheckBox] = {}

        outer = QWidget()
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(4, 4, 4, 4)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer_layout.addWidget(scroll)

        self._scroll_content = QWidget()
        self._scroll_layout = QVBoxLayout(self._scroll_content)
        self._scroll_layout.setContentsMargins(2, 2, 2, 2)
        scroll.setWidget(self._scroll_content)

        self._placeholder = QLabel("Select a component to\nview its properties.")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._scroll_layout.addWidget(self._placeholder)

        self._form_widget = QWidget()
        self._build_form_widget()
        self._scroll_layout.addWidget(self._form_widget)
        self._form_widget.setVisible(False)
        self._scroll_layout.addStretch()

        self.setWidget(outer)

    def _build_form_widget(self) -> None:
        """Build the base form (ref, value, apply button).  Extra-property rows
        are added dynamically in show_component()."""
        layout = QVBoxLayout(self._form_widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # ── Basic properties ─────────────────────────────────────────
        basic_box = QGroupBox("Basic")
        basic_form = QFormLayout(basic_box)
        self._ref_edit = QLineEdit()
        self._val_edit = QLineEdit()
        basic_form.addRow("Reference:", self._ref_edit)
        basic_form.addRow("Value:", self._val_edit)
        layout.addWidget(basic_box)

        # ── Label visibility (Issue 14) ────────────────────────────
        self._vis_group = QGroupBox("Label Visibility")
        self._vis_layout = QFormLayout(self._vis_group)
        self._ref_vis_cb = QCheckBox()
        self._ref_vis_cb.setChecked(True)
        self._val_vis_cb = QCheckBox()
        self._val_vis_cb.setChecked(True)
        self._vis_layout.addRow("Show Ref:", self._ref_vis_cb)
        self._vis_layout.addRow("Show Value:", self._val_vis_cb)
        layout.addWidget(self._vis_group)

        # ── Extra properties container (Issue 12) ─────────────────
        self._extra_group = QGroupBox("Extra Properties")
        self._extra_layout = QFormLayout(self._extra_group)
        layout.addWidget(self._extra_group)

        # ── Apply button ──────────────────────────────────────────
        self._apply_btn = QPushButton("Apply")
        self._apply_btn.clicked.connect(self._apply)
        layout.addWidget(self._apply_btn)

    def show_component(self, item: object) -> None:
        from ..components.base import ComponentItem
        if not isinstance(item, ComponentItem):
            self.clear()
            return
        self._current_item = item
        self._ref_edit.setText(item.ref)
        self._val_edit.setText(item.value)

        # Issue 14: visibility checkboxes for ref/val
        self._ref_vis_cb.setChecked(getattr(item, "_ref_visible", True))
        self._val_vis_cb.setChecked(getattr(item, "_val_visible", True))

        # Clear old extra rows
        while self._extra_layout.count():
            child = self._extra_layout.takeAt(0)
            if child and child.widget():
                child.widget().deleteLater()
        self._extra_edits.clear()

        # Issue 12: add extra-property rows for UserComponentItem
        from ..components.user_component import UserComponentItem
        self._extra_group.setVisible(isinstance(item, UserComponentItem))
        if isinstance(item, UserComponentItem):
            for i, ldef in enumerate(item._udef.labels):
                prop_name = ldef.text
                current_val = item.params.get(prop_name, ldef.default_value)
                edit = QLineEdit(current_val)
                self._extra_edits.append((prop_name, edit))

                row_widget = QWidget()
                row_layout = self._extra_layout.addRow(
                    f"{prop_name}:", edit)  # type: ignore[assignment]
                # Issue 14: visibility checkbox for extra prop
                vis_cb = QCheckBox("Show")
                vis_val = (
                    item._extra_visible[i]
                    if i < len(item._extra_visible) else True
                )
                vis_cb.setChecked(vis_val)
                self._extra_layout.addRow("", vis_cb)
                self._vis_checks[f"extra_{i}"] = vis_cb

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
        item = self._current_item

        item.ref = self._ref_edit.text().strip()
        item.value = self._val_edit.text().strip()

        # Issue 14: apply visibility flags
        item._ref_visible = self._ref_vis_cb.isChecked()
        item._val_visible = self._val_vis_cb.isChecked()

        # Issue 12: update extra property values in params
        from ..components.user_component import UserComponentItem
        if isinstance(item, UserComponentItem):
            for prop_name, edit in self._extra_edits:
                item.params[prop_name] = edit.text().strip()
            for key, cb in self._vis_checks.items():
                if key.startswith("extra_"):
                    try:
                        idx = int(key[len("extra_"):])
                        if idx < len(item._extra_visible):
                            item._extra_visible[idx] = cb.isChecked()
                    except ValueError:
                        pass

        # Issue 11: refresh label display immediately
        item._refresh_labels()
        item.update()


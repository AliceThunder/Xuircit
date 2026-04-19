"""Properties panel dock widget."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QColorDialog,
    QDockWidget,
    QDoubleSpinBox,
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
        self._build_annotation_form_widget()
        self._scroll_layout.addWidget(self._form_widget)
        self._scroll_layout.addWidget(self._anno_form_widget)
        self._form_widget.setVisible(False)
        self._anno_form_widget.setVisible(False)
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

        # ── Appearance (Feature #7: component color) ──────────────────
        self._appearance_box = QGroupBox("Appearance")
        appearance_form = QFormLayout(self._appearance_box)
        self._color_btn = QPushButton()
        self._color_btn.setFixedWidth(60)
        self._color_btn.setToolTip("Click to change component color")
        self._color_btn.clicked.connect(self._pick_color)
        appearance_form.addRow("Color:", self._color_btn)
        layout.addWidget(self._appearance_box)

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

    def _build_annotation_form_widget(self) -> None:
        layout = QVBoxLayout()
        self._anno_form_widget = QWidget()
        self._anno_form_widget.setLayout(layout)
        layout.setContentsMargins(0, 0, 0, 0)

        basic_box = QGroupBox("Annotation")
        basic_form = QFormLayout(basic_box)
        self._anno_kind = QLabel("-")
        basic_form.addRow("Kind:", self._anno_kind)
        layout.addWidget(basic_box)

        appearance_box = QGroupBox("Appearance")
        ap_form = QFormLayout(appearance_box)
        self._anno_color_btn = QPushButton()
        self._anno_color_btn.setFixedWidth(60)
        self._anno_color_btn.clicked.connect(self._pick_anno_color)
        ap_form.addRow("Color:", self._anno_color_btn)
        self._anno_line_style = QComboBox()
        self._anno_line_style.addItems(
            ["solid", "dash", "dot", "dash_dot", "dash_dot_dot"]
        )
        ap_form.addRow("Line Style:", self._anno_line_style)
        self._anno_line_width = QDoubleSpinBox()
        self._anno_line_width.setRange(0.5, 12.0)
        self._anno_line_width.setSingleStep(0.5)
        ap_form.addRow("Line Width:", self._anno_line_width)
        self._anno_fill_cb = QCheckBox("Fill")
        ap_form.addRow("", self._anno_fill_cb)
        layout.addWidget(appearance_box)

        self._anno_apply_btn = QPushButton("Apply")
        self._anno_apply_btn.clicked.connect(self._apply_annotation)
        layout.addWidget(self._anno_apply_btn)

    def show_component(self, item: object) -> None:
        from ..components.base import ComponentItem
        if not isinstance(item, ComponentItem):
            self.clear()
            return
        self._current_item = item
        self._anno_form_widget.setVisible(False)
        self._ref_edit.setText(item.ref)
        self._val_edit.setText(item.value)

        # Feature #7: update color button
        comp_color = getattr(item, "_color", "#111111")
        self._color_btn.setStyleSheet(
            f"background-color: {comp_color}; border: 1px solid #888;"
        )

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

        # Bug 2: disable property editing for virtual components
        from ..components.user_component import UserComponentItem
        is_virtual = isinstance(item, UserComponentItem) and item._udef.is_virtual
        self._ref_edit.setEnabled(not is_virtual)
        self._val_edit.setEnabled(not is_virtual)
        self._apply_btn.setEnabled(not is_virtual)
        if is_virtual:
            self._ref_edit.setToolTip("Virtual components do not have editable properties.")
            self._val_edit.setToolTip("Virtual components do not have editable properties.")
        else:
            self._ref_edit.setToolTip("")
            self._val_edit.setToolTip("")

    def show_annotation(self, item: object) -> None:
        from ..canvas.annotation import AnnotationItem, TextAnnotationItem
        if not isinstance(item, (AnnotationItem, TextAnnotationItem)):
            self.clear()
            return
        self._current_item = item
        self._placeholder.setVisible(False)
        self._form_widget.setVisible(False)
        self._anno_form_widget.setVisible(True)
        self._anno_kind.setText(getattr(item, "kind", "unknown"))

        color = getattr(item, "anno_color", "#cc2222")
        self._anno_color_btn.setStyleSheet(
            f"background-color: {color}; border: 1px solid #888;"
        )
        is_shape = isinstance(item, AnnotationItem)
        self._anno_line_style.setEnabled(is_shape)
        self._anno_line_width.setEnabled(is_shape)
        self._anno_fill_cb.setEnabled(is_shape)
        if is_shape:
            self._anno_line_style.setCurrentText(item.line_style)
            self._anno_line_width.setValue(float(item.line_width))
            self._anno_fill_cb.setChecked(bool(item.fill))

    def _pick_color(self) -> None:
        """Feature #7: open color dialog and apply to component."""
        from ..components.base import ComponentItem
        if not isinstance(self._current_item, ComponentItem):
            return
        item = self._current_item
        current = QColor(getattr(item, "_color", "#111111"))
        color = QColorDialog.getColor(current, self, "Set Component Color")
        if color.isValid():
            item._color = color.name()
            item.update()
            self._color_btn.setStyleSheet(
                f"background-color: {color.name()}; border: 1px solid #888;"
            )

    def clear(self) -> None:
        self._current_item = None
        self._placeholder.setVisible(True)
        self._form_widget.setVisible(False)
        self._anno_form_widget.setVisible(False)

    def _apply(self) -> None:
        from ..components.base import ComponentItem
        if not isinstance(self._current_item, ComponentItem):
            return
        item = self._current_item

        # Fix 6: capture before-state for undo
        scene = item.scene() if callable(getattr(item, "scene", None)) else None
        before = None
        if scene is not None and hasattr(scene, "_take_snapshot") and \
                hasattr(scene, "undo_stack") and scene.undo_stack is not None:
            before = scene._take_snapshot()

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

        # Fix 6: push undo after applying
        if before is not None and scene is not None and \
                hasattr(scene, "_push_undo") and hasattr(scene, "_take_snapshot"):
            after = scene._take_snapshot()
            scene._push_undo("Edit Properties", before, after)

    def _pick_anno_color(self) -> None:
        from ..canvas.annotation import AnnotationItem, TextAnnotationItem
        if not isinstance(self._current_item, (AnnotationItem, TextAnnotationItem)):
            return
        item = self._current_item
        scene = item.scene() if callable(getattr(item, "scene", None)) else None
        before = None
        if scene is not None and hasattr(scene, "_take_snapshot") and \
                hasattr(scene, "undo_stack") and scene.undo_stack is not None:
            before = scene._take_snapshot()

        color = QColorDialog.getColor(QColor(item.anno_color), self, "Set Color")
        if not color.isValid():
            return

        new_color = color.name()
        if new_color == item.anno_color:
            return

        item.anno_color = new_color
        if isinstance(item, AnnotationItem):
            item._rebuild_path()
        else:
            item.setDefaultTextColor(color)
        self._anno_color_btn.setStyleSheet(
            f"background-color: {new_color}; border: 1px solid #888;"
        )

        if before is not None and scene is not None and \
                hasattr(scene, "_push_undo") and hasattr(scene, "_take_snapshot"):
            after = scene._take_snapshot()
            scene._push_undo("Edit Annotation Properties", before, after)

    def _apply_annotation(self) -> None:
        from ..canvas.annotation import AnnotationItem, TextAnnotationItem
        if not isinstance(self._current_item, (AnnotationItem, TextAnnotationItem)):
            return
        item = self._current_item
        # TextAnnotationItem has no editable line/fill properties — nothing to apply.
        if not isinstance(item, AnnotationItem):
            return
        scene = item.scene() if callable(getattr(item, "scene", None)) else None
        before = None
        if scene is not None and hasattr(scene, "_take_snapshot") and \
                hasattr(scene, "undo_stack") and scene.undo_stack is not None:
            before = scene._take_snapshot()
        item.line_style = self._anno_line_style.currentText()
        item.line_width = float(self._anno_line_width.value())
        item.fill = self._anno_fill_cb.isChecked()
        item._rebuild_path()
        if before is not None and scene is not None and \
                hasattr(scene, "_push_undo") and hasattr(scene, "_take_snapshot"):
            after = scene._take_snapshot()
            scene._push_undo("Edit Annotation Properties", before, after)

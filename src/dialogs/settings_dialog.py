"""Settings dialog — font, shortcuts, and other application preferences."""
from __future__ import annotations

from PyQt6.QtGui import QColor, QFont, QFontDatabase, QKeySequence
from PyQt6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QPushButton,
    QScrollArea,
    QDoubleSpinBox,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..app.settings import AppSettings, _DEFAULT_SHORTCUTS


# Human-readable labels for action IDs
_ACTION_LABELS: dict[str, str] = {
    "file.new":        "File → New",
    "file.open":       "File → Open",
    "file.save":       "File → Save",
    "file.save_as":    "File → Save As",
    "file.exit":       "File → Exit",
    "edit.undo":       "Edit → Undo",
    "edit.redo":       "Edit → Redo",
    "edit.select_all": "Edit → Select All",
    "edit.delete":     "Edit → Delete Selected",
    "view.zoom_in":    "View → Zoom In",
    "view.zoom_out":   "View → Zoom Out",
    "view.fit_all":    "View → Fit All",
    "tools.select":    "Tools → Select Mode",
    "tools.rotate_cw": "Tools → Rotate CW",
    "tools.flip_h":    "Tools → Flip Horizontal",
    "tools.flip_v":    "Tools → Flip Vertical",
}


class _ColorButton(QWidget):
    """Simple inline color-picker button."""

    def __init__(self, color: str = "#000000",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._color = color
        self._btn = QPushButton()
        self._btn.setFixedWidth(80)
        self._update_style()
        self._btn.clicked.connect(self._pick)
        layout.addWidget(self._btn)
        layout.addStretch()

    def _update_style(self) -> None:
        self._btn.setStyleSheet(
            f"background-color: {self._color}; border: 1px solid #888;"
        )
        self._btn.setText(self._color)

    def _pick(self) -> None:
        c = QColorDialog.getColor(QColor(self._color), self, "Pick Color")
        if c.isValid():
            self._color = c.name()
            self._update_style()

    def color(self) -> str:
        return self._color


class SettingsDialog(QDialog):
    """Application settings editor."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings — Preferences")
        self.resize(520, 500)

        settings = AppSettings()
        layout = QVBoxLayout(self)

        tabs = QTabWidget()
        layout.addWidget(tabs)

        # ── Tab 1: Label Font ─────────────────────────────────────────
        font_tab = QWidget()
        font_layout = QVBoxLayout(font_tab)

        font_box = QGroupBox("Property Label Font")
        font_form = QFormLayout(font_box)

        self._family_combo = QComboBox()
        families = sorted(set(
            ["monospace", "Courier", "Courier New", "Consolas",
             "DejaVu Sans Mono", "Liberation Mono", "Arial", "Helvetica",
             "Sans Serif", "Times New Roman"]
            + list(QFontDatabase.families())
        ))
        for f in families:
            self._family_combo.addItem(f)
        current_family = settings.label_font_family()
        idx = self._family_combo.findText(current_family)
        if idx >= 0:
            self._family_combo.setCurrentIndex(idx)
        else:
            self._family_combo.insertItem(0, current_family)
            self._family_combo.setCurrentIndex(0)

        font_form.addRow("Font family:", self._family_combo)

        self._size_spin = QSpinBox()
        self._size_spin.setRange(4, 72)
        self._size_spin.setValue(settings.label_font_size())
        font_form.addRow("Font size (pt):", self._size_spin)

        font_layout.addWidget(font_box)
        font_layout.addStretch()
        tabs.addTab(font_tab, "Label Font")

        # ── Tab 2: Canvas ─────────────────────────────────────────────
        canvas_tab = QWidget()
        canvas_layout = QVBoxLayout(canvas_tab)

        wire_box = QGroupBox("Wire Settings")
        wire_form = QFormLayout(wire_box)
        # Task 7: wire color setting
        self._wire_color_btn = _ColorButton(settings.wire_color())
        wire_form.addRow("Default wire color:", self._wire_color_btn)
        self._wire_style_combo = QComboBox()
        self._wire_style_combo.addItems(
            ["solid", "dash", "dot", "dash_dot", "dash_dot_dot"]
        )
        self._wire_style_combo.setCurrentText(settings.wire_line_style())
        wire_form.addRow("Default wire line style:", self._wire_style_combo)
        self._wire_width_spin = QDoubleSpinBox()
        self._wire_width_spin.setRange(0.5, 12.0)
        self._wire_width_spin.setSingleStep(0.5)
        self._wire_width_spin.setValue(settings.wire_line_width())
        wire_form.addRow("Default wire line width:", self._wire_width_spin)
        canvas_layout.addWidget(wire_box)

        anno_box = QGroupBox("Annotation Settings")
        anno_form = QFormLayout(anno_box)
        # Task 8: default annotation color
        self._anno_color_btn = _ColorButton(settings.annotation_color())
        anno_form.addRow("Default annotation color:", self._anno_color_btn)
        self._anno_style_combo = QComboBox()
        self._anno_style_combo.addItems(
            ["solid", "dash", "dot", "dash_dot", "dash_dot_dot"]
        )
        self._anno_style_combo.setCurrentText(settings.annotation_line_style())
        anno_form.addRow("Default annotation line style:", self._anno_style_combo)
        self._anno_width_spin = QDoubleSpinBox()
        self._anno_width_spin.setRange(0.5, 12.0)
        self._anno_width_spin.setSingleStep(0.5)
        self._anno_width_spin.setValue(settings.annotation_line_width())
        anno_form.addRow("Default annotation line width:", self._anno_width_spin)
        canvas_layout.addWidget(anno_box)

        editor_box = QGroupBox("Component Editor Drawing")
        editor_form = QFormLayout(editor_box)
        self._editor_style_combo = QComboBox()
        self._editor_style_combo.addItems(
            ["solid", "dash", "dot", "dash_dot", "dash_dot_dot"]
        )
        self._editor_style_combo.setCurrentText(settings.editor_line_style())
        editor_form.addRow("Default editor line style:", self._editor_style_combo)
        self._editor_width_spin = QDoubleSpinBox()
        self._editor_width_spin.setRange(0.5, 12.0)
        self._editor_width_spin.setSingleStep(0.5)
        self._editor_width_spin.setValue(settings.editor_line_width())
        editor_form.addRow("Default editor line width:", self._editor_width_spin)
        canvas_layout.addWidget(editor_box)

        bg_box = QGroupBox("Canvas Appearance")
        bg_form = QFormLayout(bg_box)
        # Task 8: canvas background color
        self._bg_color_btn = _ColorButton(settings.canvas_bg_color())
        bg_form.addRow("Canvas background color:", self._bg_color_btn)
        # Task 8: grid visibility
        self._show_grid_cb = QCheckBox("Show grid lines")
        self._show_grid_cb.setChecked(settings.show_grid())
        bg_form.addRow("Grid:", self._show_grid_cb)
        canvas_layout.addWidget(bg_box)

        canvas_layout.addStretch()
        tabs.addTab(canvas_tab, "Canvas")

        # ── Tab 3: Keyboard Shortcuts ─────────────────────────────────
        shortcuts_tab = QWidget()
        shortcuts_layout = QVBoxLayout(shortcuts_tab)

        note = QLabel(
            "Click a shortcut field and press your desired key combination.\n"
            "Changes take effect after clicking OK and restarting the application."
        )
        note.setWordWrap(True)
        shortcuts_layout.addWidget(note)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        sc_widget = QWidget()
        sc_form = QFormLayout(sc_widget)

        self._shortcut_edits: dict[str, QKeySequenceEdit] = {}
        current_shortcuts = settings.all_shortcuts()
        for action_id in sorted(_DEFAULT_SHORTCUTS.keys()):
            label = _ACTION_LABELS.get(action_id, action_id)
            ks_str = current_shortcuts.get(action_id, "")
            edit = QKeySequenceEdit(QKeySequence(ks_str))
            self._shortcut_edits[action_id] = edit
            sc_form.addRow(f"{label}:", edit)

        scroll.setWidget(sc_widget)
        shortcuts_layout.addWidget(scroll)
        tabs.addTab(shortcuts_tab, "Keyboard Shortcuts")

        # ── Buttons ──────────────────────────────────────────────────
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self) -> None:
        settings = AppSettings()

        # Save font settings
        settings.set("label_font_family", self._family_combo.currentText())
        settings.set("label_font_size", self._size_spin.value())

        # Apply new font to LabelItem class-level default
        from ..components.base import LabelItem
        new_font = QFont(self._family_combo.currentText(),
                         self._size_spin.value())
        LabelItem.set_label_font(new_font)

        # Task 7: save wire color
        settings.set("wire_color", self._wire_color_btn.color())
        settings.set("wire_line_style", self._wire_style_combo.currentText())
        settings.set("wire_line_width", self._wire_width_spin.value())

        # Task 8: save canvas settings
        settings.set("annotation_color", self._anno_color_btn.color())
        settings.set("annotation_line_style", self._anno_style_combo.currentText())
        settings.set("annotation_line_width", self._anno_width_spin.value())
        settings.set("editor_line_style", self._editor_style_combo.currentText())
        settings.set("editor_line_width", self._editor_width_spin.value())
        settings.set("canvas_bg_color", self._bg_color_btn.color())
        settings.set("show_grid", self._show_grid_cb.isChecked())

        # Save shortcut settings
        for action_id, edit in self._shortcut_edits.items():
            ks = edit.keySequence()
            settings.set_shortcut(action_id, ks.toString())

        self.accept()

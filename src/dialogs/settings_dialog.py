"""Settings dialog — font, shortcuts, and other application preferences."""
from __future__ import annotations

from PyQt6.QtGui import QFont, QFontDatabase, QKeySequence
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QKeySequenceEdit,
    QLabel,
    QScrollArea,
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


class SettingsDialog(QDialog):
    """Application settings editor."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings — Preferences")
        self.resize(500, 450)

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

        # ── Tab 2: Keyboard Shortcuts ─────────────────────────────────
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

        # Save shortcut settings
        for action_id, edit in self._shortcut_edits.items():
            ks = edit.keySequence()
            settings.set_shortcut(action_id, ks.toString())

        self.accept()

"""Settings dialog — font, shortcuts, and other application preferences."""
from __future__ import annotations

from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QSpinBox,
    QVBoxLayout,
)

from ..app.settings import AppSettings


class SettingsDialog(QDialog):
    """Application settings editor."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(400, 250)

        settings = AppSettings()
        layout = QVBoxLayout(self)

        # ── Label font ───────────────────────────────────────────────
        font_box = QGroupBox("Property Label Font")
        font_form = QFormLayout(font_box)

        self._family_combo = QComboBox()
        # Populate with all available monospace families + common ones
        families = sorted(set(
            ["monospace", "Courier", "Courier New", "Consolas",
             "DejaVu Sans Mono", "Liberation Mono", "Arial", "Helvetica",
             "Sans Serif", "Times New Roman"]
            + list(QFontDatabase.families())
        ))
        for f in families:
            self._family_combo.addItem(f)
        # Select current
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

        layout.addWidget(font_box)

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
        settings.set("label_font_family", self._family_combo.currentText())
        settings.set("label_font_size", self._size_spin.value())

        # Apply new font to LabelItem class-level default
        from ..components.base import LabelItem
        new_font = QFont(self._family_combo.currentText(),
                         self._size_spin.value())
        LabelItem.set_label_font(new_font)

        self.accept()

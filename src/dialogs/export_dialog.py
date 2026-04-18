"""Export dialog: choose format (PNG, SVG, PDF) and export."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ExportDialog(QDialog):
    """Dialog for exporting the schematic."""

    def __init__(self, scene: object, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._scene = scene
        self.setWindowTitle("Export Schematic")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._fmt_combo = QComboBox()
        self._fmt_combo.addItems(["PNG", "SVG", "PDF", "Visio (SVG)"])
        self._fmt_combo.currentTextChanged.connect(self._on_format_changed)
        form.addRow("Format:", self._fmt_combo)

        self._dpi_combo = QComboBox()
        self._dpi_combo.addItems(["72", "150", "300"])
        self._dpi_combo.setCurrentText("150")
        self._dpi_label = QLabel("DPI:")
        form.addRow(self._dpi_label, self._dpi_combo)

        self._path_edit = QLineEdit()
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse)
        row = QHBoxLayout()
        row.addWidget(self._path_edit)
        row.addWidget(browse_btn)
        form.addRow("File:", row)  # type: ignore[arg-type]

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._export)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_format_changed(self, fmt: str) -> None:
        visible = fmt == "PNG"
        self._dpi_label.setVisible(visible)
        self._dpi_combo.setVisible(visible)
        if fmt == "Visio (SVG)":
            from PyQt6.QtWidgets import QMessageBox
            # Show a note only on first switch to this format
            pass  # tooltip is enough

    def _browse(self) -> None:
        fmt = self._fmt_combo.currentText()
        filters = {
            "PNG": "PNG images (*.png)",
            "SVG": "SVG files (*.svg)",
            "PDF": "PDF files (*.pdf)",
            "Visio (SVG)": "SVG files (*.svg)",
        }
        path, _ = QFileDialog.getSaveFileName(
            self, "Export As", "", filters.get(fmt, "All files (*)")
        )
        if path:
            self._path_edit.setText(path)

    def _export(self) -> None:
        path = self._path_edit.text().strip()
        if not path:
            QMessageBox.warning(self, "Export", "Please specify a filename.")
            return
        fmt = self._fmt_combo.currentText()
        try:
            if fmt == "PNG":
                from ..io.svg_exporter import export_png
                export_png(self._scene, path, int(self._dpi_combo.currentText()))  # type: ignore[arg-type]
            elif fmt == "SVG":
                from ..io.svg_exporter import export_svg
                export_svg(self._scene, path)  # type: ignore[arg-type]
            elif fmt == "PDF":
                from ..io.svg_exporter import export_pdf
                export_pdf(self._scene, path)  # type: ignore[arg-type]
            elif fmt == "Visio (SVG)":
                from ..io.svg_exporter import export_svg
                if not path.lower().endswith(".svg"):
                    path += ".svg"
                export_svg(self._scene, path)  # type: ignore[arg-type]
                QMessageBox.information(
                    self, "Visio Export",
                    f"Exported to:\n{path}\n\n"
                    "To edit in Visio: open Visio → File → Open, select the SVG file.\n"
                    "Visio can import SVG files for secondary vector editing."
                )
                self.accept()
                return
            QMessageBox.information(self, "Export", f"Exported to:\n{path}")
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, "Export Error", str(exc))

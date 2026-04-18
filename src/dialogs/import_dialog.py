"""Import netlist dialog."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ImportDialog(QDialog):
    """Dialog for importing a SPICE netlist file."""

    def __init__(self, scene: object, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._scene = scene
        self._text: str = ""
        self.setWindowTitle("Import Netlist")
        self.setMinimumSize(500, 340)

        layout = QVBoxLayout(self)

        browse_btn = QPushButton("Browse for Netlist File…")
        browse_btn.clicked.connect(self._browse)
        layout.addWidget(browse_btn)

        layout.addWidget(QLabel("Preview (first 30 lines):"))
        self._preview = QPlainTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setMaximumHeight(180)
        layout.addWidget(self._preview)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Import")
        buttons.accepted.connect(self._import)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Netlist", "",
            "SPICE files (*.sp *.net *.cir);;Text files (*.txt);;All files (*)"
        )
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as fh:
                self._text = fh.read()
            preview = "\n".join(self._text.splitlines()[:30])
            self._preview.setPlainText(preview)
        except OSError as exc:
            QMessageBox.critical(self, "Error", str(exc))

    def _import(self) -> None:
        if not self._text.strip():
            QMessageBox.warning(self, "Import", "No netlist loaded.")
            return
        from ..canvas.scene import CircuitScene
        if isinstance(self._scene, CircuitScene):
            self._scene.apply_netlist(self._text)
        self.accept()

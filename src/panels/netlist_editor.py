"""Netlist editor dock widget with SPICE syntax highlighting."""
from __future__ import annotations

from PyQt6.QtCore import Qt, QRegularExpression
from PyQt6.QtGui import (
    QColor,
    QFont,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextDocument,
)
from PyQt6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)


class SpiceHighlighter(QSyntaxHighlighter):
    """Basic SPICE netlist syntax highlighter."""

    def __init__(self, document: QTextDocument) -> None:
        super().__init__(document)
        self._rules: list[tuple[QRegularExpression, QTextCharFormat]] = []

        # Comment lines (* or ;)
        comment_fmt = QTextCharFormat()
        comment_fmt.setForeground(QColor("#888888"))
        comment_fmt.setFontItalic(True)
        self._rules.append((
            QRegularExpression(r"^[*;].*"),
            comment_fmt,
        ))

        # Directive lines (starting with .)
        directive_fmt = QTextCharFormat()
        directive_fmt.setForeground(QColor("#007700"))
        directive_fmt.setFontWeight(QFont.Weight.Bold.value)
        self._rules.append((
            QRegularExpression(r"^\.[A-Za-z]+\b.*"),
            directive_fmt,
        ))

        # XCIT section headers (.xcit_layout, .end_xcit_layout, etc.) —
        # must come after the directive rule so it takes precedence.
        xcit_fmt = QTextCharFormat()
        xcit_fmt.setForeground(QColor("#660066"))
        xcit_fmt.setFontWeight(QFont.Weight.Bold.value)
        self._rules.append((
            QRegularExpression(r"^\.(xcit_\w+|end_xcit_\w+)\b.*"),
            xcit_fmt,
        ))

        # Element lines (starting with R/C/L/V/I/D/Q/M/E/F/G/H/S/W/B/X)
        element_fmt = QTextCharFormat()
        element_fmt.setForeground(QColor("#00008b"))
        self._rules.append((
            QRegularExpression(r"^[RCLVIDQMEFGHSWBXTKrclvidqmefghswbxtk]\w*"),
            element_fmt,
        ))

        # Numeric values with SI suffixes
        value_fmt = QTextCharFormat()
        value_fmt.setForeground(QColor("#8b4513"))
        self._rules.append((
            QRegularExpression(
                r"\b\d+\.?\d*([eE][+-]?\d+)?[TGMkKmuUnpPf]?\b"
            ),
            value_fmt,
        ))

    def highlightBlock(self, text: str) -> None:
        for pattern, fmt in self._rules:
            it = pattern.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), fmt)


class NetlistEditor(QDockWidget):
    """Bottom dock: SPICE netlist text editor with highlighting."""

    def __init__(self, parent: object = None) -> None:
        super().__init__("Netlist Editor", parent)  # type: ignore[arg-type]
        self.setAllowedAreas(
            Qt.DockWidgetArea.BottomDockWidgetArea |
            Qt.DockWidgetArea.TopDockWidgetArea
        )
        self._scene: object = None

        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)

        # Toolbar
        tb = QHBoxLayout()
        self._btn_gen = QPushButton("Generate SPICE")
        self._btn_gen_xcit = QPushButton("Generate XCIT")
        self._btn_apply = QPushButton("Apply to Schematic")
        self._btn_load = QPushButton("Load File…")
        self._btn_save = QPushButton("Save File…")
        for btn in (self._btn_gen, self._btn_gen_xcit, self._btn_apply,
                    self._btn_load, self._btn_save):
            tb.addWidget(btn)
        tb.addStretch()
        layout.addLayout(tb)

        # Editor
        self._editor = QPlainTextEdit()
        self._editor.setFont(QFont("Courier", 10))
        self._editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._highlighter = SpiceHighlighter(self._editor.document())
        layout.addWidget(self._editor)

        self.setWidget(widget)

        self._btn_gen.clicked.connect(self._generate)
        self._btn_gen_xcit.clicked.connect(self._generate_xcit)
        self._btn_apply.clicked.connect(self._apply)
        self._btn_load.clicked.connect(self._load_file)
        self._btn_save.clicked.connect(self._save_file)

    def set_scene(self, scene: object) -> None:
        self._scene = scene

    def set_text(self, text: str) -> None:
        self._editor.setPlainText(text)

    def get_text(self) -> str:
        return self._editor.toPlainText()

    def _generate(self) -> None:
        from ..canvas.scene import CircuitScene
        from ..io.netlist_generator import generate_netlist
        if not isinstance(self._scene, CircuitScene):
            return
        text = generate_netlist(self._scene.circuit)
        self._editor.setPlainText(text)

    def _generate_xcit(self) -> None:
        from ..canvas.scene import CircuitScene
        from ..io.xcit_netlist import generate_xcit_netlist
        if not isinstance(self._scene, CircuitScene):
            return
        text = generate_xcit_netlist(self._scene.circuit)
        self._editor.setPlainText(text)

    def _apply(self) -> None:
        from ..canvas.scene import CircuitScene
        if not isinstance(self._scene, CircuitScene):
            return
        text = self._editor.toPlainText().strip()
        if not text:
            return
        self._scene.apply_netlist(text)

    def _load_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            None, "Open Netlist", "",
            "All netlist files (*.xcit_net *.sp *.net *.cir *.txt);;"
            "XCIT files (*.xcit_net);;SPICE files (*.sp *.net *.cir);;"
            "Text files (*.txt);;All files (*)"
        )
        if path:
            try:
                with open(path, encoding="utf-8") as fh:
                    self._editor.setPlainText(fh.read())
            except OSError as exc:
                QMessageBox.critical(None, "Load Error", str(exc))

    def _save_file(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            None, "Save Netlist", "",
            "XCIT files (*.xcit_net);;SPICE files (*.sp *.net *.cir);;Text files (*.txt)"
        )
        if path:
            try:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(self._editor.toPlainText())
            except OSError as exc:
                QMessageBox.critical(None, "Save Error", str(exc))

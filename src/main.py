"""Entry point for the Xuircit circuit drawing application."""
from __future__ import annotations

import os
import sys

# Ensure the repo root is on sys.path so `src` is importable as a package
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from PyQt6.QtWidgets import QApplication
from src.app.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Xuircit")
    app.setOrganizationName("Xuircit")
    app.setApplicationVersion("0.1.0")

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

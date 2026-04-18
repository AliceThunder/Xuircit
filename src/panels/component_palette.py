"""Component palette dock widget."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDockWidget,
    QLabel,
    QLineEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..models.component_library import ComponentLibrary


class ComponentPalette(QDockWidget):
    """Left dock: categorized list of components with search."""

    place_requested = pyqtSignal(str)  # emits comp_type

    def __init__(self, parent: object = None) -> None:
        super().__init__("Components", parent)  # type: ignore[arg-type]
        self.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea |
            Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.setMinimumWidth(180)

        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)

        # Search bar
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search components…")
        self._search.textChanged.connect(self._on_search)
        layout.addWidget(self._search)

        # Tree
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setRootIsDecorated(True)
        layout.addWidget(self._tree)

        # Place button
        btn = QPushButton("Place Selected")
        btn.clicked.connect(self._on_place_clicked)
        layout.addWidget(btn)

        self.setWidget(widget)
        self._populate()

    def _populate(self, filter_text: str = "") -> None:
        self._tree.clear()
        lib = ComponentLibrary()
        ft = filter_text.strip().lower()

        for cat in lib.categories():
            defs = lib.by_category(cat)
            if ft:
                defs = [d for d in defs
                        if ft in d.display_name.lower()
                        or ft in d.type_name.lower()]
            if not defs:
                continue
            cat_item = QTreeWidgetItem([cat])
            cat_item.setFlags(cat_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            font = cat_item.font(0)
            font.setBold(True)
            cat_item.setFont(0, font)
            self._tree.addTopLevelItem(cat_item)
            for cdef in defs:
                child = QTreeWidgetItem([cdef.display_name])
                child.setData(0, Qt.ItemDataRole.UserRole, cdef.type_name)
                child.setToolTip(0, cdef.description)
                cat_item.addChild(child)
            cat_item.setExpanded(True)

        self._tree.itemDoubleClicked.connect(self._on_double_click)

    def _on_search(self, text: str) -> None:
        self._populate(text)

    def _on_double_click(self, item: QTreeWidgetItem, col: int) -> None:
        comp_type = item.data(0, Qt.ItemDataRole.UserRole)
        if comp_type:
            self.place_requested.emit(comp_type)

    def _on_place_clicked(self) -> None:
        selected = self._tree.currentItem()
        if selected:
            comp_type = selected.data(0, Qt.ItemDataRole.UserRole)
            if comp_type:
                self.place_requested.emit(comp_type)

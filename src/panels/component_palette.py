"""Component palette dock widget."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDockWidget,
    QLineEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
)

from ..models.library_system import LibraryManager


class ComponentPalette(QDockWidget):
    """Left dock: categorized list of components with search.

    Issue 1: components are placed by single-clicking the item (no drag-and-drop).
    Components are grouped first by library, then by category within each library.
    """

    place_requested = pyqtSignal(str, str)  # emits (comp_type, library_id)
    library_changed = pyqtSignal()     # Task 5: emitted after library edits

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

        # Tree (Issue 1: single-click selects; no drag-and-drop)
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setRootIsDecorated(True)
        self._tree.setDragEnabled(False)  # Issue 1: disable drag
        layout.addWidget(self._tree)

        # Button row
        btn_row = QHBoxLayout()
        manage_btn = QPushButton("Manage Libraries…")
        manage_btn.setToolTip("Add / remove libraries and components")
        manage_btn.clicked.connect(self._on_manage)
        btn_row.addWidget(manage_btn)
        layout.addLayout(btn_row)

        self.setWidget(widget)
        # Issue 1: single-click places the component (was double-click)
        self._tree.itemClicked.connect(self._on_item_clicked)
        self._populate()

    def _populate(self, filter_text: str = "") -> None:
        self._tree.clear()
        ft = filter_text.strip().lower()

        lm = LibraryManager()
        for lib in lm.all_libraries():
            # Collect matching entries for this library
            matching = [
                e for e in lib.all()
                if not ft
                or ft in e.display_name.lower()
                or ft in e.type_name.lower()
            ]
            if not matching:
                continue

            # Library root node
            lib_item = QTreeWidgetItem([lib.name])
            lib_item.setFlags(lib_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            font = lib_item.font(0)
            font.setBold(True)
            font.setPointSize(font.pointSize() + 1)
            lib_item.setFont(0, font)
            self._tree.addTopLevelItem(lib_item)

            # Group by category
            cats: dict[str, list] = {}
            for e in matching:
                cats.setdefault(e.category, []).append(e)

            for cat_name, entries in cats.items():
                cat_item = self._make_category(cat_name, lib_item)
                for e in entries:
                    child = QTreeWidgetItem([e.display_name])
                    child.setData(0, Qt.ItemDataRole.UserRole, e.type_name)
                    child.setData(
                        0, Qt.ItemDataRole.UserRole + 1, lib.library_id
                    )
                    child.setToolTip(0, e.description)
                    cat_item.addChild(child)
                cat_item.setExpanded(True)

            lib_item.setExpanded(True)

    def _make_category(self, name: str,
                        parent: QTreeWidgetItem) -> QTreeWidgetItem:
        cat_item = QTreeWidgetItem([name])
        cat_item.setFlags(cat_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        font = cat_item.font(0)
        font.setBold(True)
        cat_item.setFont(0, font)
        parent.addChild(cat_item)
        return cat_item

    def _on_search(self, text: str) -> None:
        self._populate(text)

    def _on_item_clicked(self, item: QTreeWidgetItem, col: int) -> None:
        """Issue 1: single-click on a component emits place_requested."""
        comp_type = item.data(0, Qt.ItemDataRole.UserRole)
        library_id = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if comp_type and library_id:
            self.place_requested.emit(comp_type, library_id)

    def _on_manage(self) -> None:
        from ..dialogs.user_component_editor import LibraryManagerDialog
        dlg = LibraryManagerDialog(self.widget())
        dlg.exec()
        # Refresh palette in case user added/removed libraries or components
        LibraryManager.reset_instance()
        self._populate(self._search.text())
        # Task 5: notify main window to rebuild the canvas with updated definitions
        self.library_changed.emit()

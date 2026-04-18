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
    QHBoxLayout,
    QWidget,
)

from ..models.component_library import ComponentLibrary
from ..models.user_library import UserLibrary


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

        # Button row
        btn_row = QHBoxLayout()
        place_btn = QPushButton("Place Selected")
        place_btn.clicked.connect(self._on_place_clicked)
        btn_row.addWidget(place_btn)

        manage_btn = QPushButton("Manage Library…")
        manage_btn.setToolTip("Create / edit / delete user-defined components")
        manage_btn.clicked.connect(self._on_manage)
        btn_row.addWidget(manage_btn)
        layout.addLayout(btn_row)

        self.setWidget(widget)
        self._populate()

    def _populate(self, filter_text: str = "") -> None:
        self._tree.clear()
        ft = filter_text.strip().lower()

        # ── built-in library ──────────────────────────────────────────
        lib = ComponentLibrary()
        for cat in lib.categories():
            defs = lib.by_category(cat)
            if ft:
                defs = [d for d in defs
                        if ft in d.display_name.lower()
                        or ft in d.type_name.lower()]
            if not defs:
                continue
            cat_item = self._make_category(cat)
            for cdef in defs:
                child = QTreeWidgetItem([cdef.display_name])
                child.setData(0, Qt.ItemDataRole.UserRole, cdef.type_name)
                child.setToolTip(0, cdef.description)
                cat_item.addChild(child)
            cat_item.setExpanded(True)

        # ── user-defined components ───────────────────────────────────
        ulib = UserLibrary()
        udefs = ulib.all()
        if ft:
            udefs = [d for d in udefs
                     if ft in d.display_name.lower()
                     or ft in d.type_name.lower()]
        if udefs:
            # Group by user-defined category
            cats: dict[str, list] = {}
            for u in udefs:
                cats.setdefault(u.category, []).append(u)
            for cat_name, items in cats.items():
                cat_item = self._make_category(cat_name)
                for u in items:
                    child = QTreeWidgetItem([u.display_name])
                    child.setData(0, Qt.ItemDataRole.UserRole, u.type_name)
                    child.setToolTip(0, u.description)
                    cat_item.addChild(child)
                cat_item.setExpanded(True)

        self._tree.itemDoubleClicked.connect(self._on_double_click)

    def _make_category(self, name: str) -> QTreeWidgetItem:
        cat_item = QTreeWidgetItem([name])
        cat_item.setFlags(cat_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        font = cat_item.font(0)
        font.setBold(True)
        cat_item.setFont(0, font)
        self._tree.addTopLevelItem(cat_item)
        return cat_item

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

    def _on_manage(self) -> None:
        from ..dialogs.user_component_editor import UserLibraryManagerDialog
        dlg = UserLibraryManagerDialog(self.widget())
        dlg.exec()
        # Refresh palette in case user added/removed components
        self._populate(self._search.text())

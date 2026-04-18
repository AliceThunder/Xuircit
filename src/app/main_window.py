"""MainWindow — top-level application window."""
from __future__ import annotations

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QAction, QKeySequence, QUndoStack
from PyQt6.QtWidgets import (
    QCheckBox,
    QDockWidget,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStatusBar,
    QToolBar,
    QWidget,
)

from ..canvas.scene import CircuitScene, SceneMode
from ..canvas.view import CircuitView
from ..components.base import ComponentItem
from ..components.wire import WireItem
from ..models.circuit import Circuit
from ..panels.component_palette import ComponentPalette
from ..panels.properties_panel import PropertiesPanel
from ..panels.netlist_editor import NetlistEditor


class MainWindow(QMainWindow):
    """Main application window for Xuircit."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Xuircit — Circuit Drawing Tool")
        self.resize(1440, 900)

        # Data model
        self._circuit = Circuit()
        self._filepath: str = ""
        self._modified = False

        # Undo stack
        self._undo_stack = QUndoStack(self)

        # Scene and view
        self._scene = CircuitScene(self._circuit)
        self._scene.undo_stack = self._undo_stack  # wire undo/redo (Issue 6)
        self._view = CircuitView(self._scene)
        self.setCentralWidget(self._view)

        # Panels
        self._palette = ComponentPalette(self)
        self._properties = PropertiesPanel(self)
        self._netlist_editor = NetlistEditor(self)
        self._netlist_editor.set_scene(self._scene)

        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._palette)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._properties)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._netlist_editor)

        # Status bar
        self._status_mode = QLabel("Mode: SELECT")
        self._status_pos = QLabel("(0, 0)")
        self._status_zoom = QLabel("Zoom: 100%")
        sb = QStatusBar()
        sb.addWidget(self._status_mode)
        sb.addPermanentWidget(self._status_pos)
        sb.addPermanentWidget(self._status_zoom)
        self.setStatusBar(sb)

        self._build_menu()
        self._build_toolbar()
        self._connect_signals()

        # Feature #2: apply saved font settings to labels
        self._apply_font_settings()

    def _apply_font_settings(self) -> None:
        """Feature #2: apply saved font/size settings to LabelItem."""
        from ..app.settings import AppSettings
        from ..components.base import LabelItem
        from PyQt6.QtGui import QFont
        settings = AppSettings()
        font = QFont(settings.label_font_family(), settings.label_font_size())
        LabelItem.set_label_font(font)

    # ------------------------------------------------------------------
    # Menu bar
    # ------------------------------------------------------------------

    def _build_menu(self) -> None:
        mb = self.menuBar()

        # File
        file_menu = mb.addMenu("&File")
        self._act_new = self._action("&New", "Ctrl+N", self._new)
        self._act_open = self._action("&Open…", "Ctrl+O", self._open)
        self._act_save = self._action("&Save", "Ctrl+S", self._save)
        self._act_save_as = self._action("Save &As…", "Ctrl+Shift+S", self._save_as)
        self._act_import = self._action("Import &Netlist…", callback=self._import_netlist)
        self._act_exit = self._action("E&xit", "Alt+F4", self.close)

        export_menu = file_menu.addMenu("&Export")
        self._action("Export as &PNG…",
                     callback=lambda: self._export("PNG"),
                     parent_menu=export_menu)
        self._action("Export as &SVG…",
                     callback=lambda: self._export("SVG"),
                     parent_menu=export_menu)
        self._action("Export as P&DF…",
                     callback=lambda: self._export("PDF"),
                     parent_menu=export_menu)
        self._action("Export &Netlist (SPICE)…",
                     callback=self._export_netlist,
                     parent_menu=export_menu)
        self._action("Export &XCIT Netlist…",
                     callback=self._export_xcit_netlist,
                     parent_menu=export_menu)

        for act in (self._act_new, self._act_open, self._act_save,
                    self._act_save_as, None, export_menu.menuAction(),
                    self._act_import, None, self._act_exit):
            if act is None:
                file_menu.addSeparator()
            else:
                file_menu.addAction(act)

        # Edit
        edit_menu = mb.addMenu("&Edit")
        self._act_undo = self._undo_stack.createUndoAction(self, "&Undo")
        self._act_undo.setShortcut("Ctrl+Z")
        self._act_redo = self._undo_stack.createRedoAction(self, "&Redo")
        self._act_redo.setShortcut("Ctrl+Y")
        self._act_select_all = self._action("Select &All", "Ctrl+A", self._select_all)
        self._act_delete = self._action("&Delete Selected", "Del", self._delete_selected)
        for act in (self._act_undo, self._act_redo, None,
                    self._act_select_all, self._act_delete):
            if act is None:
                edit_menu.addSeparator()
            else:
                edit_menu.addAction(act)

        # View
        view_menu = mb.addMenu("&View")
        self._act_zoom_in = self._action("Zoom &In", "Ctrl++", self._view.zoom_in)
        self._act_zoom_out = self._action("Zoom &Out", "Ctrl+-", self._view.zoom_out)
        self._act_fit = self._action("&Fit All", "Ctrl+0", self._view.fit_all)
        for act in (self._act_zoom_in, self._act_zoom_out, self._act_fit):
            view_menu.addAction(act)
        view_menu.addSeparator()
        view_menu.addAction(self._palette.toggleViewAction())
        view_menu.addAction(self._properties.toggleViewAction())
        view_menu.addAction(self._netlist_editor.toggleViewAction())

        # Tools
        tools_menu = mb.addMenu("&Tools")
        self._act_select_mode = self._action(
            "&Select", "Escape",
            lambda: self._scene.set_mode(SceneMode.SELECT),
            checkable=True, checked=True,
        )
        # Bug 1 fix: manual wire drawing is removed from the UI.
        # DRAW_WIRE mode is kept internally for compatibility but not exposed.
        tools_menu.addAction(self._act_select_mode)
        tools_menu.addSeparator()
        tools_menu.addAction(self._action(
            "Rotate Selected CW  (R)", callback=self._rotate_selected_cw))
        tools_menu.addAction(self._action(
            "Flip Selected Horizontal  (F)", callback=self._flip_selected_h))
        tools_menu.addAction(self._action(
            "Flip Selected Vertical  (V)", callback=self._flip_selected_v))

        # Library
        lib_menu = mb.addMenu("&Library")
        lib_menu.addAction(self._action(
            "Manage User Components…",
            callback=self._manage_user_library,
        ))

        # Settings
        settings_menu = mb.addMenu("&Settings")
        settings_menu.addAction(self._action(
            "Preferences…",
            callback=self._open_settings,
        ))

        # Help
        help_menu = mb.addMenu("&Help")
        help_menu.addAction(self._action("&About", callback=self._about))

    def _action(
        self,
        text: str,
        shortcut: str = "",
        callback: object = None,
        checkable: bool = False,
        checked: bool = False,
        parent_menu: object = None,
    ) -> QAction:
        act = QAction(text, self)
        if shortcut:
            act.setShortcut(QKeySequence(shortcut))
        if checkable:
            act.setCheckable(True)
            act.setChecked(checked)
        if callback:
            act.triggered.connect(callback)
        if parent_menu is not None:
            from PyQt6.QtWidgets import QMenu
            if isinstance(parent_menu, QMenu):
                parent_menu.addAction(act)
        return act

    # ------------------------------------------------------------------
    # Toolbar
    # ------------------------------------------------------------------

    def _build_toolbar(self) -> None:
        tb = QToolBar("Main")
        tb.setMovable(False)
        tb.setIconSize(QSize(20, 20))
        self.addToolBar(tb)
        for act in (self._act_new, self._act_open, self._act_save):
            tb.addAction(act)
        tb.addSeparator()
        for act in (self._act_undo, self._act_redo):
            tb.addAction(act)
        tb.addSeparator()
        tb.addAction(self._act_select_mode)
        tb.addSeparator()
        for act in (self._act_zoom_in, self._act_zoom_out, self._act_fit):
            tb.addAction(act)
        tb.addSeparator()
        # Issue 8: label-dragging toggle switch
        self._lbl_drag_cb = QCheckBox("Label Drag")
        self._lbl_drag_cb.setChecked(True)
        self._lbl_drag_cb.setToolTip(
            "Enable / disable dragging of component labels.\n"
            "Uncheck to prevent accidental label moves."
        )
        self._lbl_drag_cb.toggled.connect(self._on_label_drag_toggled)
        tb.addWidget(self._lbl_drag_cb)

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        self._palette.place_requested.connect(self._on_place_requested)
        self._scene.component_placed.connect(self._on_component_placed)
        self._scene.wire_drawn.connect(self._on_wire_drawn)
        self._scene.selection_changed_signal.connect(self._on_selection_changed)
        self._scene.mode_changed.connect(self._on_mode_changed)
        self._view.zoom_changed.connect(self._on_zoom_changed)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_place_requested(self, comp_type: str) -> None:
        self._scene.set_mode(SceneMode.PLACE_COMPONENT)
        self._scene.set_pending_component(comp_type)
        self._status_mode.setText(f"Mode: PLACE {comp_type}")
        # Bug 2 fix: grab keyboard focus so R/F/V shortcuts reach the scene
        self._view.setFocus(Qt.FocusReason.OtherFocusReason)

    def _on_component_placed(self, comp: dict) -> None:
        self._modified = True
        self._update_title()

    def _on_wire_drawn(self, wire: dict) -> None:
        self._modified = True
        self._update_title()

    def _on_selection_changed(self, items: list) -> None:
        comp_items = [i for i in items if isinstance(i, ComponentItem)]
        if len(comp_items) == 1:
            self._properties.show_component(comp_items[0])
        else:
            self._properties.clear()

    def _on_mode_changed(self, mode_name: str) -> None:
        self._status_mode.setText(f"Mode: {mode_name}")
        self._act_select_mode.setChecked(mode_name == "SELECT")
        # Issue 9: only allow rubber-band selection in SELECT mode
        self._view.set_select_mode(mode_name == "SELECT")

    def _on_zoom_changed(self, zoom: float) -> None:
        self._status_zoom.setText(f"Zoom: {zoom * 100:.0f}%")

    def _on_label_drag_toggled(self, enabled: bool) -> None:
        """Issue 8: toggle label dragging globally."""
        from ..components.base import LabelItem
        LabelItem.set_dragging_enabled(enabled)

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------

    def _new(self) -> None:
        if self._modified:
            reply = QMessageBox.question(
                self, "New", "Discard unsaved changes?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self._circuit.clear()
        for item in list(self._scene.items()):
            self._scene.removeItem(item)
        self._filepath = ""
        self._modified = False
        self._update_title()

    def _open(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Project", "",
            "Xuircit files (*.xcit);;All files (*)"
        )
        if not path:
            return
        try:
            from ..io.project_file import load_project
            circuit = load_project(path)
            self._circuit = circuit
            self._scene.circuit = circuit
            self._scene.rebuild_from_circuit()
            self._filepath = path
            self._modified = False
            self._update_title()
        except Exception as exc:
            QMessageBox.critical(self, "Open Error", str(exc))

    def _save(self) -> None:
        if not self._filepath:
            self._save_as()
            return
        self._do_save(self._filepath)

    def _save_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Project As", "",
            "Xuircit files (*.xcit);;All files (*)"
        )
        if path:
            if not path.endswith(".xcit"):
                path += ".xcit"
            self._do_save(path)
            self._filepath = path

    def _do_save(self, path: str) -> None:
        try:
            self._sync_scene_to_circuit()
            from ..io.project_file import save_project
            save_project(self._circuit, path)
            self._modified = False
            self._update_title()
        except Exception as exc:
            QMessageBox.critical(self, "Save Error", str(exc))

    def _sync_scene_to_circuit(self) -> None:
        """Sync scene item state (rotation, flip, label positions) back to the
        circuit model so that saves and exports are always up to date."""
        from ..components.base import ComponentItem
        for item in self._scene.items():
            if isinstance(item, ComponentItem):
                comp = self._circuit.get_component(item.component_id)
                if comp is not None:
                    comp.update(item.to_dict())

    def _import_netlist(self) -> None:
        from ..dialogs.import_dialog import ImportDialog
        dlg = ImportDialog(self._scene, self)
        dlg.exec()

    def _export(self, fmt: str) -> None:
        from ..dialogs.export_dialog import ExportDialog
        dlg = ExportDialog(self._scene, self)
        dlg._fmt_combo.setCurrentText(fmt)
        dlg.exec()

    def _export_netlist(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Netlist", "",
            "SPICE files (*.sp *.net *.cir);;Text files (*.txt)"
        )
        if path:
            try:
                self._sync_scene_to_circuit()
                from ..io.netlist_generator import generate_netlist
                text = generate_netlist(self._circuit)
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(text)
            except Exception as exc:
                QMessageBox.critical(self, "Error", str(exc))

    def _export_xcit_netlist(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export XCIT Netlist", "",
            "XCIT files (*.xcit_net);;Text files (*.txt)"
        )
        if path:
            try:
                self._sync_scene_to_circuit()
                from ..io.xcit_netlist import generate_xcit_netlist
                text = generate_xcit_netlist(self._circuit)
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(text)
            except Exception as exc:
                QMessageBox.critical(self, "Error", str(exc))

    # ------------------------------------------------------------------
    # Edit helpers
    # ------------------------------------------------------------------

    def _select_all(self) -> None:
        for item in self._scene.items():
            item.setSelected(True)

    def _delete_selected(self) -> None:
        changed = False
        for item in list(self._scene.selectedItems()):
            if isinstance(item, ComponentItem):
                self._circuit.remove_component(item.component_id)
                changed = True
            elif isinstance(item, WireItem):
                self._circuit.remove_wire(item.wire_id)
            self._scene.removeItem(item)
        if changed:
            self._scene._rebuild_auto_wires()
        self._modified = True
        self._update_title()

    def _rotate_selected_cw(self) -> None:
        changed = False
        for item in self._scene.selectedItems():
            if isinstance(item, ComponentItem):
                item._rotate_cw()
                changed = True
        # Wire rebuild is triggered by ComponentItem._rotate_cw via _notify_scene_changed

    def _flip_selected_h(self) -> None:
        for item in self._scene.selectedItems():
            if isinstance(item, ComponentItem):
                item._flip_h()

    def _flip_selected_v(self) -> None:
        for item in self._scene.selectedItems():
            if isinstance(item, ComponentItem):
                item._flip_v()

    # ------------------------------------------------------------------
    # Library
    # ------------------------------------------------------------------

    def _manage_user_library(self) -> None:
        from ..dialogs.user_component_editor import LibraryManagerDialog
        from ..models.library_system import LibraryManager
        dlg = LibraryManagerDialog(self)
        dlg.exec()
        # Reset singleton and refresh palette after any changes
        LibraryManager.reset_instance()
        self._palette._populate(self._palette._search.text())

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def _open_settings(self) -> None:
        from ..dialogs.settings_dialog import SettingsDialog
        dlg = SettingsDialog(self)
        dlg.exec()

    # ------------------------------------------------------------------
    # About
    # ------------------------------------------------------------------

    def _about(self) -> None:
        QMessageBox.about(
            self, "About Xuircit",
            "<h2>Xuircit</h2>"
            "<p>A desktop GUI circuit drawing application.</p>"
            "<p>Built with Python + PyQt6.</p>",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _update_title(self) -> None:
        name = self._filepath or "Untitled"
        mod = " *" if self._modified else ""
        self.setWindowTitle(f"Xuircit — {name}{mod}")

    def closeEvent(self, event: object) -> None:
        if self._modified:
            reply = QMessageBox.question(
                self, "Quit", "Save changes before quitting?",
                QMessageBox.StandardButton.Save |
                QMessageBox.StandardButton.Discard |
                QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Save:
                self._save()
                event.accept()  # type: ignore[union-attr]
            elif reply == QMessageBox.StandardButton.Discard:
                event.accept()  # type: ignore[union-attr]
            else:
                event.ignore()  # type: ignore[union-attr]
        else:
            event.accept()  # type: ignore[union-attr]

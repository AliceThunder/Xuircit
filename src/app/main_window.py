"""MainWindow — top-level application window."""
from __future__ import annotations

from PyQt6.QtCore import Qt, QSize, QEvent, QObject
from PyQt6.QtGui import QAction, QKeySequence, QUndoStack
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ..canvas.scene import CircuitScene, SceneMode
from ..canvas.view import CircuitView
from ..components.base import ComponentItem
from ..components.wire import WireItem
from ..models.circuit import Circuit
from ..panels.component_palette import ComponentPalette
from ..panels.layers_panel import LayersPanel
from ..panels.properties_panel import PropertiesPanel
from ..panels.netlist_editor import NetlistEditor


# ---------------------------------------------------------------------------
# Bug 7: Floating annotation toolbar overlay for the main canvas
# ---------------------------------------------------------------------------

class _CanvasAnnotationToolbar(QWidget):
    """Semi-transparent floating toolbar that hovers over the circuit canvas.

    It provides icon buttons for annotation tools and the fill/layer toggles,
    so the user doesn't need to look at the Layers dock panel while drawing.
    The toolbar auto-hides when the cursor leaves the canvas area and
    reappears when it enters.
    """

    _TOOLS = [
        ("⬚", "select",   "Select / move annotations"),
        ("╱", "line",     "Draw a straight line"),
        ("→", "arrow",    "Draw an arrow"),
        ("◯", "circle",   "Draw a circle"),
        ("⬭", "ellipse",  "Draw an ellipse"),
        ("▭", "rect",     "Draw a rectangle"),
        ("⌇", "polyline", "Draw a polyline (right-click to finish)"),
        ("✎", "text",     "Place a text annotation"),
    ]
    _BTN_SIZE = 36

    def __init__(self, view: CircuitView, parent: QWidget) -> None:
        super().__init__(parent)
        self._view = view
        self._current_tool = "select"
        self._btns: dict[str, QPushButton] = {}

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowFlags(Qt.WindowType.SubWindow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        for icon, tool_id, tip in self._TOOLS:
            btn = QPushButton(icon)
            btn.setToolTip(tip)
            btn.setFixedSize(self._BTN_SIZE, self._BTN_SIZE)
            btn.setCheckable(True)
            btn.setChecked(tool_id == "select")
            btn.setStyleSheet(self._btn_style(tool_id == "select"))
            btn.clicked.connect(lambda checked=False, t=tool_id: self._on_tool(t))
            self._btns[tool_id] = btn
            layout.addWidget(btn)

        # Fill toggle
        self._fill_btn = QPushButton("■")
        self._fill_btn.setToolTip("Toggle solid fill for closed shapes")
        self._fill_btn.setFixedSize(self._BTN_SIZE, self._BTN_SIZE)
        self._fill_btn.setCheckable(True)
        self._fill_btn.setChecked(False)
        self._fill_btn.setStyleSheet(self._btn_style(False))
        self._fill_btn.clicked.connect(self._on_fill_toggled)
        layout.addWidget(self._fill_btn)

        self.adjustSize()
        self.move(8, 8)
        self.hide()

        # Install event filter on the view's viewport to track hover
        view.viewport().installEventFilter(self)

    # ------------------------------------------------------------------
    # Styling helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _btn_style(active: bool) -> str:
        if active:
            return (
                "QPushButton {"
                "  background: rgba(50,100,220,200);"
                "  border: 2px solid #3355cc;"
                "  border-radius: 5px;"
                "  font-size: 16px;"
                "  color: white;"
                "}"
            )
        return (
            "QPushButton {"
            "  background: rgba(60,60,60,160);"
            "  border: 1px solid #555;"
            "  border-radius: 5px;"
            "  font-size: 16px;"
            "  color: #ddd;"
            "}"
            "QPushButton:hover {"
            "  background: rgba(90,90,90,200);"
            "  border: 1px solid #888;"
            "}"
        )

    def _set_active(self, tool_id: str) -> None:
        self._current_tool = tool_id
        for t, btn in self._btns.items():
            btn.setStyleSheet(self._btn_style(t == tool_id))
            btn.setChecked(t == tool_id)

    # ------------------------------------------------------------------
    # Tool signals
    # ------------------------------------------------------------------

    def _on_tool(self, tool_id: str) -> None:
        self._set_active(tool_id)
        # Notify whoever connected the signal (main window → scene)
        if hasattr(self, "_tool_callback") and self._tool_callback is not None:
            self._tool_callback(tool_id)  # type: ignore[misc]

    def _on_fill_toggled(self) -> None:
        active = self._fill_btn.isChecked()
        self._fill_btn.setStyleSheet(self._btn_style(active))
        if hasattr(self, "_fill_callback") and self._fill_callback is not None:
            self._fill_callback(active)  # type: ignore[misc]

    def connect_tool_callback(self, cb: object) -> None:
        self._tool_callback = cb  # type: ignore[attr-defined]

    def connect_fill_callback(self, cb: object) -> None:
        self._fill_callback = cb  # type: ignore[attr-defined]

    def set_active_tool(self, tool_id: str) -> None:
        """Called externally when the tool changes (e.g. from Layers panel)."""
        self._set_active(tool_id)

    # ------------------------------------------------------------------
    # Hover show/hide
    # ------------------------------------------------------------------

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj is self._view.viewport():
            if event.type() == QEvent.Type.Enter:
                self._reposition()
                self.show()
                self.raise_()
            elif event.type() == QEvent.Type.Leave:
                from PyQt6.QtGui import QCursor
                gp = QCursor.pos()
                lp = self.mapFromGlobal(gp)
                if not self.rect().contains(lp):
                    self.hide()
            elif event.type() == QEvent.Type.Resize:
                self._reposition()
        return False

    def leaveEvent(self, event: object) -> None:
        self.hide()
        super().leaveEvent(event)  # type: ignore[arg-type]

    def _reposition(self) -> None:
        self.move(8, 8)
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
        self._layers_panel = LayersPanel(self)  # Feature #6

        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._palette)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._properties)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._layers_panel)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._netlist_editor)

        # Bug 7: floating annotation toolbar overlaid on the canvas view
        self._anno_toolbar = _CanvasAnnotationToolbar(self._view, self._view)
        self._anno_toolbar.connect_tool_callback(self._on_annotation_tool_selected)
        self._anno_toolbar.connect_fill_callback(self._scene.set_annotation_fill)

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
        try:
            from ..app.settings import AppSettings
            s = AppSettings()
            self._line_style_combo.setCurrentText(s.annotation_line_style())
            self._line_width_spin.setValue(s.annotation_line_width())
            self._scene.set_annotation_pen(
                s.annotation_line_style(), s.annotation_line_width()
            )
        except Exception:
            pass

        # Feature #2: apply saved font settings to labels
        self._apply_font_settings()

        # Fix 5: ensure Label Drag starts disabled (matching the checkbox default)
        from ..components.base import LabelItem
        LabelItem.set_dragging_enabled(False)

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

        # Feature #4: load user shortcuts from settings
        from ..app.settings import AppSettings
        _sc = AppSettings().shortcut  # shorthand

        # File
        file_menu = mb.addMenu("&File")
        self._act_new = self._action("&New", _sc("file.new"), self._new)
        self._act_open = self._action("&Open…", _sc("file.open"), self._open)
        self._act_save = self._action("&Save", _sc("file.save"), self._save)
        self._act_save_as = self._action("Save &As…", _sc("file.save_as"), self._save_as)
        self._act_import = self._action("Import &Netlist…", callback=self._import_netlist)
        self._act_exit = self._action("E&xit", _sc("file.exit"), self.close)

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
        self._action("Export for &Visio (SVG)…",
                     callback=lambda: self._export("Visio (SVG)"),
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
        self._act_undo.setShortcut(_sc("edit.undo"))
        self._act_redo = self._undo_stack.createRedoAction(self, "&Redo")
        self._act_redo.setShortcut(_sc("edit.redo"))
        self._act_select_all = self._action("Select &All", _sc("edit.select_all"), self._select_all)
        self._act_delete = self._action("&Delete Selected", _sc("edit.delete"), self._delete_selected)
        for act in (self._act_undo, self._act_redo, None,
                    self._act_select_all, self._act_delete):
            if act is None:
                edit_menu.addSeparator()
            else:
                edit_menu.addAction(act)

        # View
        view_menu = mb.addMenu("&View")
        self._act_zoom_in = self._action("Zoom &In", _sc("view.zoom_in"), self._view.zoom_in)
        self._act_zoom_out = self._action("Zoom &Out", _sc("view.zoom_out"), self._view.zoom_out)
        self._act_fit = self._action("&Fit All", _sc("view.fit_all"), self._view.fit_all)
        for act in (self._act_zoom_in, self._act_zoom_out, self._act_fit):
            view_menu.addAction(act)
        view_menu.addSeparator()
        view_menu.addAction(self._palette.toggleViewAction())
        view_menu.addAction(self._properties.toggleViewAction())
        view_menu.addAction(self._netlist_editor.toggleViewAction())
        view_menu.addAction(self._layers_panel.toggleViewAction())

        # Tools
        tools_menu = mb.addMenu("&Tools")
        self._act_select_mode = self._action(
            "&Select", _sc("tools.select"),
            self._on_select_mode,
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
        # Fix 5: label-dragging toggle switch — default is OFF
        self._lbl_drag_cb = QCheckBox("Label Drag")
        self._lbl_drag_cb.setChecked(False)
        self._lbl_drag_cb.setToolTip(
            "Enable / disable dragging of component labels.\n"
            "Uncheck to prevent accidental label moves."
        )
        self._lbl_drag_cb.toggled.connect(self._on_label_drag_toggled)
        tb.addWidget(self._lbl_drag_cb)
        tb.addSeparator()
        tb.addWidget(QLabel("Line"))
        self._line_style_combo = QComboBox()
        self._line_style_combo.addItems(
            ["solid", "dash", "dot", "dash_dot", "dash_dot_dot"]
        )
        tb.addWidget(self._line_style_combo)
        self._line_width_spin = QDoubleSpinBox()
        self._line_width_spin.setRange(0.5, 12.0)
        self._line_width_spin.setSingleStep(0.5)
        self._line_width_spin.setValue(2.0)
        tb.addWidget(self._line_width_spin)
        self._line_apply_btn = QPushButton("Apply")
        self._line_apply_btn.clicked.connect(self._apply_line_style_to_selection)
        tb.addWidget(self._line_apply_btn)

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        self._palette.place_requested.connect(self._on_place_requested)
        self._palette.library_changed.connect(self._on_library_changed)  # Task 5
        self._scene.component_placed.connect(self._on_component_placed)
        self._scene.wire_drawn.connect(self._on_wire_drawn)
        self._scene.selection_changed_signal.connect(self._on_selection_changed)
        self._scene.mode_changed.connect(self._on_mode_changed)
        self._view.zoom_changed.connect(self._on_zoom_changed)
        # Feature #6: layer panel
        self._layers_panel.component_layer_toggled.connect(
            self._scene.set_component_layer_visible)
        self._layers_panel.annotation_layer_toggled.connect(
            self._scene.set_annotation_layer_visible)
        self._scene.annotation_tool_reset.connect(
            lambda: self._on_annotation_tool_selected("select"))

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_select_mode(self) -> None:
        """Switch to select mode and reset annotation tool (Bug 3 fix)."""
        self._scene.set_mode(SceneMode.SELECT)
        self._on_annotation_tool_selected("select")

    def _on_place_requested(self, comp_type: str) -> None:
        self._scene.set_mode(SceneMode.PLACE_COMPONENT)
        self._scene.set_pending_component(comp_type)
        self._status_mode.setText(f"Mode: PLACE {comp_type}")
        # Bug 2 fix: grab keyboard focus so R/F/V shortcuts reach the scene
        self._view.setFocus(Qt.FocusReason.OtherFocusReason)

    def _on_component_placed(self, comp: dict) -> None:
        self._modified = True
        self._update_title()
        self._on_annotation_tool_selected("select")

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
        # Fix 7: update cursor based on mode
        from PyQt6.QtCore import Qt as Qt_
        if mode_name == "SELECT":
            self._view.viewport().setCursor(Qt_.CursorShape.ArrowCursor)
        else:
            self._view.viewport().setCursor(Qt_.CursorShape.CrossCursor)

    def _on_annotation_tool_selected(self, tool: str) -> None:
        """Feature #6: switch scene to the selected annotation drawing tool."""
        self._scene.set_annotation_tool(tool)
        # Bug 7: keep floating toolbar in sync
        self._anno_toolbar.set_active_tool(tool)
        # Fix 7: update cursor for annotation mode
        from PyQt6.QtCore import Qt as Qt_
        if tool == "select":
            self._status_mode.setText("Mode: SELECT")
            self._view.viewport().setCursor(Qt_.CursorShape.ArrowCursor)
        else:
            self._status_mode.setText(f"Mode: ANNOTATE ({tool})")
            self._view.viewport().setCursor(Qt_.CursorShape.CrossCursor)

    def _on_zoom_changed(self, zoom: float) -> None:
        self._status_zoom.setText(f"Zoom: {zoom * 100:.0f}%")

    def _on_label_drag_toggled(self, enabled: bool) -> None:
        """Issue 8: toggle label dragging globally."""
        from ..components.base import LabelItem
        LabelItem.set_dragging_enabled(enabled)

    def _apply_line_style_to_selection(self) -> None:
        style = self._line_style_combo.currentText()
        width = float(self._line_width_spin.value())
        self._scene.apply_line_style_to_selection(style, width)
        self._scene.set_annotation_pen(style, width)

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
        from ..canvas.annotation import AnnotationItem, TextAnnotationItem
        changed = False
        for item in list(self._scene.selectedItems()):
            if isinstance(item, ComponentItem):
                self._circuit.remove_component(item.component_id)
                changed = True
            elif isinstance(item, WireItem):
                self._circuit.remove_wire(item.wire_id)
            elif isinstance(item, (AnnotationItem, TextAnnotationItem)):
                # Bug 1 fix: also remove annotations from the circuit model so
                # they are not restored by rebuild_from_circuit on Ctrl+V paste.
                self._circuit.remove_annotation(item.anno_id)
            self._scene.removeItem(item)
        if changed:
            self._scene._rebuild_auto_wires()
        self._modified = True
        self._update_title()

    def _rotate_selected_cw(self) -> None:
        changed = False
        targets = [i for i in self._scene.selectedItems() if isinstance(i, ComponentItem)]
        if targets:
            before = self._scene._take_snapshot()
            for item in targets:
                item._rotate_cw()
                changed = True
            after = self._scene._take_snapshot()
            self._scene._push_undo("Rotate CW", before, after)

    def _flip_selected_h(self) -> None:
        targets = [i for i in self._scene.selectedItems() if isinstance(i, ComponentItem)]
        if targets:
            before = self._scene._take_snapshot()
            for item in targets:
                item._flip_h()
            after = self._scene._take_snapshot()
            self._scene._push_undo("Flip Horizontal", before, after)

    def _flip_selected_v(self) -> None:
        targets = [i for i in self._scene.selectedItems() if isinstance(i, ComponentItem)]
        if targets:
            before = self._scene._take_snapshot()
            for item in targets:
                item._flip_v()
            after = self._scene._take_snapshot()
            self._scene._push_undo("Flip Vertical", before, after)

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
        # Task 5: rebuild canvas so component graphics reflect the updated definitions
        self._scene.rebuild_from_circuit()

    def _on_library_changed(self) -> None:
        """Task 5: rebuild scene when component library definitions are updated."""
        self._scene.rebuild_from_circuit()

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

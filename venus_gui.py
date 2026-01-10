from __future__ import annotations

import sys
from pathlib import Path

from PyQt6 import QtCore, QtGui, QtWidgets

import venus_protocol as vp


KEY_USAGE = {chr(ord("A") + i): 0x04 + i for i in range(26)}

DEFAULT_MACRO_EVENTS_HEX = (
    "000e811700005d411700009d810800005d41080000bc811600006d411600009c811700005e41170000"
    "9c810c00005e410c0000bc811100004e41110000cb810a00005e410a00"
)
DEFAULT_MACRO_TAIL_HEX = "000369000000"


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Venus Pro Config (Reverse Engineering)")
        self.resize(1200, 780)

        self.device: vp.VenusDevice | None = None
        self.device_infos: list[vp.DeviceInfo] = []
        self.custom_profiles: dict[str, tuple[int, int, int]] = {}
        self.button_assignments: dict[str, dict] = {} # Stored button settings from device

        root = QtWidgets.QWidget()
        self.setCentralWidget(root)

        main_layout = QtWidgets.QHBoxLayout(root)

        left_panel = QtWidgets.QVBoxLayout()
        main_layout.addLayout(left_panel, stretch=3)

        right_panel = QtWidgets.QVBoxLayout()
        main_layout.addLayout(right_panel, stretch=2)

        left_panel.addWidget(self._build_connection_group())
        left_panel.addWidget(self._build_tabs(), stretch=1)
        left_panel.addWidget(self._build_log())

        right_panel.addWidget(self._build_mouse_image())
        right_panel.addStretch(1)
        right_panel.addStretch(1)
        
        self.custom_profiles = {}  # key -> (code_hi, code_lo, apply_offset)
        self.current_edit_key = None
        self.button_assignments = {}
        self._initialize_default_assignments()


        self._refresh_and_connect()


    def _build_connection_group(self) -> QtWidgets.QGroupBox:
        group = QtWidgets.QGroupBox("Device Status")
        layout = QtWidgets.QHBoxLayout(group)

        self.status_label = QtWidgets.QLabel("Searching...")
        layout.addWidget(self.status_label)
        
        self.refresh_button = QtWidgets.QPushButton("⟳ Reconnect/Refresh")
        layout.addWidget(self.refresh_button)
        
        self.read_button = QtWidgets.QPushButton("📥 Read Settings")
        layout.addWidget(self.read_button)
        
        self.export_button = QtWidgets.QPushButton("💾 Export Profile")
        layout.addWidget(self.export_button)
        
        self.import_button = QtWidgets.QPushButton("📂 Import Profile")
        layout.addWidget(self.import_button)
        
        # Hidden combo for logic, but not needed for user interaction mostly
        self.device_combo = QtWidgets.QComboBox()
        self.device_combo.setVisible(False)

        self.refresh_button.clicked.connect(self._refresh_and_connect)
        self.read_button.clicked.connect(self._read_settings)
        self.export_button.clicked.connect(self._export_profile)
        self.import_button.clicked.connect(self._import_profile)
        # Remove old connect/disconnect/reset buttons from here

        return group


    def _build_tabs(self) -> QtWidgets.QTabWidget:
        tabs = QtWidgets.QTabWidget()
        tabs.addTab(self._build_buttons_tab(), "Buttons")
        tabs.addTab(self._build_macros_tab(), "Macros")
        tabs.addTab(self._build_rgb_tab(), "RGB")
        tabs.addTab(self._build_polling_tab(), "Polling")
        tabs.addTab(self._build_dpi_tab(), "DPI")
        tabs.addTab(self._build_advanced_tab(), "Advanced")
        return tabs

    def _build_buttons_tab(self) -> QtWidgets.QWidget:
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        
        # --- Left: Button List ---
        left_widget = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        self.btn_table = QtWidgets.QTableWidget()
        self.btn_table.setColumnCount(2)
        self.btn_table.setHorizontalHeaderLabels(["Button", "Current Assignment"])
        self.btn_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.btn_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.btn_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.btn_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.btn_table.verticalHeader().setVisible(False)
        
        # Populate rows
        # Sort by button number (Side 1-12, then others)
        self.sorted_btn_keys = sorted(vp.BUTTON_PROFILES.keys(), key=lambda k: int(k.split()[1]))
        self.btn_table.setRowCount(len(self.sorted_btn_keys))
        
        for i, key in enumerate(self.sorted_btn_keys):
            profile = vp.BUTTON_PROFILES[key]
            item_name = QtWidgets.QTableWidgetItem(profile.label)
            item_name.setData(QtCore.Qt.ItemDataRole.UserRole, key)
            item_name.setFlags(item_name.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            self.btn_table.setItem(i, 0, item_name)
            
            item_assign = QtWidgets.QTableWidgetItem("Unknown (Read to update)")
            item_assign.setFlags(item_assign.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            self.btn_table.setItem(i, 1, item_assign)
            
        self.btn_table.itemSelectionChanged.connect(self._on_btn_table_select)
        left_layout.addWidget(self.btn_table)
        
        # --- Right: Editor ---
        right_widget = QtWidgets.QWidget()
        self.editor_layout = QtWidgets.QVBoxLayout(right_widget)
        self.editor_layout.setContentsMargins(10, 0, 0, 0)
        
        # Reverse map for key names
        self.HID_USAGE_TO_NAME = {v: k for k, v in vp.HID_KEY_USAGE.items()}
        
        self.editor_label = QtWidgets.QLabel("Select a button to edit")

        self.editor_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.editor_layout.addWidget(self.editor_label)
        
        self.action_select = QtWidgets.QComboBox()
        self.action_select.addItems([
            "Keyboard Key", "Left Click", "Right Click", "Middle Click", 
            "Forward", "Back", "Macro", "Reset Defaults",
            "Fire Key", "Triple Click", "Media Key", "RGB Toggle", 
            "Polling Rate Toggle", "DPI Control", "Disabled"
        ])
        self.editor_layout.addWidget(QtWidgets.QLabel("Action:"))
        self.editor_layout.addWidget(self.action_select)
        
        # -- Editor Groups (same as before) --
        # 1. Keyboard
        self.key_group = QtWidgets.QWidget()
        key_group_layout = QtWidgets.QVBoxLayout(self.key_group)
        key_group_layout.setContentsMargins(0, 0, 0, 0)
        self.key_select = QtWidgets.QKeySequenceEdit()
        # Initial empty sequence
        self.key_select.setKeySequence(QtGui.QKeySequence(""))
        self.mod_ctrl = QtWidgets.QCheckBox("Ctrl")
        self.mod_shift = QtWidgets.QCheckBox("Shift")
        self.mod_alt = QtWidgets.QCheckBox("Alt")
        self.mod_win = QtWidgets.QCheckBox("Win")
        mod_layout = QtWidgets.QHBoxLayout()
        mod_layout.addWidget(self.mod_ctrl); mod_layout.addWidget(self.mod_shift)
        mod_layout.addWidget(self.mod_alt); mod_layout.addWidget(self.mod_win)
        mod_layout.addStretch()
        key_group_layout.addWidget(QtWidgets.QLabel("Key:"))
        key_group_layout.addWidget(self.key_select)
        key_group_layout.addWidget(QtWidgets.QLabel("Modifiers:"))
        key_group_layout.addLayout(mod_layout)
        
        # 2. Macro
        self.macro_group = QtWidgets.QWidget()
        macro_layout = QtWidgets.QFormLayout(self.macro_group)
        self.macro_index_spin = QtWidgets.QSpinBox()
        self.macro_index_spin.setRange(1, 12)
        macro_layout.addRow("Macro Index:", self.macro_index_spin)
        
        # Macro Repeat Mode
        self.macro_repeat_combo = QtWidgets.QComboBox()
        self.macro_repeat_combo.addItem("Run Once", vp.MACRO_REPEAT_ONCE)
        self.macro_repeat_combo.addItem("Repeat While Held", vp.MACRO_REPEAT_HOLD)
        self.macro_repeat_combo.addItem("Loop Until Key", vp.MACRO_REPEAT_TOGGLE)
        macro_layout.addRow("Repeat:", self.macro_repeat_combo)
        
        # Macro Recall
        self.load_macro_btn = QtWidgets.QPushButton("Load from Slot")
        self.load_macro_btn.clicked.connect(self._load_macro_from_slot)
        macro_layout.addRow("Recall:", self.load_macro_btn)
        
        # Quick Text Group inside Macro layout
        quick_group = QtWidgets.QGroupBox("Quick Text Macro")
        quick_layout = QtWidgets.QVBoxLayout(quick_group)
        self.quick_text_edit = QtWidgets.QLineEdit()
        self.quick_text_edit.setPlaceholderText("Enter text here (max ~35 chars)")
        quick_hbox = QtWidgets.QHBoxLayout()
        quick_hbox.addWidget(QtWidgets.QLabel("Delay:"))
        self.quick_delay_spin = QtWidgets.QSpinBox()
        self.quick_delay_spin.setRange(1, 255); self.quick_delay_spin.setValue(10); self.quick_delay_spin.setSuffix(" ms")
        quick_hbox.addWidget(self.quick_delay_spin)
        self.gen_text_btn = QtWidgets.QPushButton("Generate Events")
        self.gen_text_btn.clicked.connect(self._generate_text_macro)
        quick_hbox.addWidget(self.gen_text_btn)
        
        quick_layout.addWidget(self.quick_text_edit)
        quick_layout.addLayout(quick_hbox)
        
        macro_layout.addRow(quick_group)

        
        # 3. Special
        self.special_group = QtWidgets.QWidget()
        special_layout = QtWidgets.QHBoxLayout(self.special_group)
        self.special_delay_spin = QtWidgets.QSpinBox()
        self.special_delay_spin.setRange(0, 255); self.special_delay_spin.setValue(40); self.special_delay_spin.setSuffix(" ms")
        self.special_repeat_spin = QtWidgets.QSpinBox()
        self.special_repeat_spin.setRange(0, 255); self.special_repeat_spin.setValue(3)
        special_layout.addWidget(QtWidgets.QLabel("Delay:")); special_layout.addWidget(self.special_delay_spin)
        special_layout.addWidget(QtWidgets.QLabel("Repeats:")); special_layout.addWidget(self.special_repeat_spin)

        # 4. Media
        self.media_group = QtWidgets.QWidget()
        media_layout = QtWidgets.QHBoxLayout(self.media_group)
        self.media_select = QtWidgets.QComboBox()
        for key in sorted(vp.MEDIA_KEY_CODES.keys()):
            self.media_select.addItem(key, vp.MEDIA_KEY_CODES[key])
        media_layout.addWidget(QtWidgets.QLabel("Media Function:")); media_layout.addWidget(self.media_select)

        # 5. DPI Control Group
        self.dpi_group = QtWidgets.QWidget()
        dpi_layout = QtWidgets.QHBoxLayout(self.dpi_group)
        self.dpi_action_select = QtWidgets.QComboBox()
        self.dpi_action_select.addItem("DPI Loop (Shift+6)", 0x02) # D1=02
        self.dpi_action_select.addItem("DPI + (Ctrl+Shift+7)", 0x03) # D1=03
        self.dpi_action_select.addItem("DPI - (Ctrl+8)", 0x01) # D1=01
        dpi_layout.addWidget(QtWidgets.QLabel("DPI Function:"))
        dpi_layout.addWidget(self.dpi_action_select)
        
        # Add groups
        self.editor_layout.addWidget(self.key_group)
        self.editor_layout.addWidget(self.macro_group)
        self.editor_layout.addWidget(self.special_group)
        self.editor_layout.addWidget(self.media_group)
        self.editor_layout.addWidget(self.dpi_group)
        
        self.apply_button = QtWidgets.QPushButton("Apply Binding")
        self.apply_button.setStyleSheet("font-weight: bold; padding: 5px;")
        self.apply_button.clicked.connect(self._apply_button_binding)
        self.apply_button.clicked.connect(self._apply_button_binding)
        self.editor_layout.addWidget(self.apply_button)

        # Advanced / Custom Offsets (Restored for logic compatibility)
        self.advanced_group = QtWidgets.QGroupBox("Advanced / Custom Offsets")
        self.advanced_group.setCheckable(True)
        self.advanced_group.setChecked(False)
        adv_layout = QtWidgets.QFormLayout(self.advanced_group)
        self.code_hi_spin = QtWidgets.QSpinBox(); self.code_hi_spin.setRange(0, 255); self.code_hi_spin.setDisplayIntegerBase(16); self.code_hi_spin.setPrefix("0x")
        self.code_lo_spin = QtWidgets.QSpinBox(); self.code_lo_spin.setRange(0, 255); self.code_lo_spin.setDisplayIntegerBase(16); self.code_lo_spin.setPrefix("0x")
        self.apply_offset_spin = QtWidgets.QSpinBox(); self.apply_offset_spin.setRange(0, 255); self.apply_offset_spin.setDisplayIntegerBase(16); self.apply_offset_spin.setPrefix("0x")
        adv_layout.addRow("Code Hi:", self.code_hi_spin)
        adv_layout.addRow("Code Lo:", self.code_lo_spin)
        adv_layout.addRow("Apply Offset:", self.apply_offset_spin)
        self.editor_layout.addWidget(self.advanced_group)
        
        self.editor_layout.addStretch()


        # Connects
        self.action_select.currentTextChanged.connect(self._update_bind_ui)
        
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        
        return splitter

    def _on_btn_table_select(self) -> None:
        """Handle button selection in the table."""
        rows = self.btn_table.selectionModel().selectedRows()
        if not rows:
            self.right_panel_enabled(False)
            self.current_edit_key = None
            return
            
        row = rows[0].row()
        key = self.btn_table.item(row, 0).data(QtCore.Qt.ItemDataRole.UserRole)
        label = self.btn_table.item(row, 0).text()
        
        self.editor_label.setText(f"Editing: {label}")
        self.current_edit_key = key # Store for apply
        self.right_panel_enabled(True)
        
        # Update Advanced / Custom Offsets UI
        if key in vp.BUTTON_PROFILES:
            p = vp.BUTTON_PROFILES[key]
            self.code_hi_spin.blockSignals(True)
            self.code_lo_spin.blockSignals(True)
            self.apply_offset_spin.blockSignals(True)
            
            self.code_hi_spin.setValue(p.code_hi or 0)
            self.code_lo_spin.setValue(p.code_lo or 0)
            self.apply_offset_spin.setValue(p.apply_offset or 0)
            
            self.code_hi_spin.blockSignals(False)
            self.code_lo_spin.blockSignals(False)
            self.apply_offset_spin.blockSignals(False)
            
            self.code_hi_spin.setEnabled(False)
            self.code_lo_spin.setEnabled(False)
            self.apply_offset_spin.setEnabled(False)
        else:
            custom = self.custom_profiles.get(key)
            if custom:
                self.code_hi_spin.setValue(custom[0])
                self.code_lo_spin.setValue(custom[1])
                self.apply_offset_spin.setValue(custom[2])
            else:
                self.code_hi_spin.setValue(0)
                self.code_lo_spin.setValue(0)
                self.apply_offset_spin.setValue(0)
            self.code_hi_spin.setEnabled(True)
            self.code_lo_spin.setEnabled(True)
            self.apply_offset_spin.setEnabled(True)
        
        # Populate editor from current assignment
        self._update_ui_from_assignment(key)


    def right_panel_enabled(self, enabled: bool) -> None:
        self.action_select.setEnabled(enabled)
        self.apply_button.setEnabled(enabled)
        # Also disable groups?
        
    def _update_ui_from_assignment(self, button_key: str) -> None:
        """Update editor UI from stored assignment."""
        if button_key not in self.button_assignments: return
        assign = self.button_assignments[button_key]
        action = assign["action"]
        params = assign["params"]
        
        self.action_select.blockSignals(True)
        # No mapping needed

        
        idx = self.action_select.findText(action)
        if idx >= 0: self.action_select.setCurrentIndex(idx)
        else: self.action_select.setCurrentIndex(self.action_select.findText("Disabled")) # Fallback
        
        self._update_bind_ui(self.action_select.currentText())
        self.action_select.blockSignals(False)
        
        if action == "Keyboard Key":
            hid_key = params.get("key", 0)
            mod = params.get("mod", 0)
            
            key_name = self.HID_USAGE_TO_NAME.get(hid_key, "")
            if key_name:
                # Map HID name back to Qt Key name for display
                qt_name_map = {
                    "Enter": "Return",
                    "Escape": "Esc",
                    "Delete": "Del",
                    "Insert": "Ins",
                    "PageUp": "PgUp",
                    "PageDown": "PgDown",
                }
                qt_name = qt_name_map.get(key_name, key_name)
                self.key_select.setKeySequence(QtGui.QKeySequence(qt_name))
            else:
                self.key_select.setKeySequence(QtGui.QKeySequence(""))
            
            self.mod_ctrl.setChecked(bool(mod & vp.MODIFIER_CTRL))
            self.mod_shift.setChecked(bool(mod & vp.MODIFIER_SHIFT))
            self.mod_alt.setChecked(bool(mod & vp.MODIFIER_ALT))
            self.mod_win.setChecked(bool(mod & vp.MODIFIER_WIN))
        elif action == "Macro":
            self.macro_index_spin.setValue(params.get("index", 1))
        elif action in ["Fire Key", "Triple Click"]:
            self.special_delay_spin.setValue(params.get("delay", 40))
            self.special_repeat_spin.setValue(params.get("repeat", 3))


    def _update_bind_ui(self, action: str) -> None:
        """Show/hide UI elements based on selected action."""
        self.key_group.setVisible(action == "Keyboard Key")
        self.macro_group.setVisible(action == "Macro")
        self.special_group.setVisible(action in ["Fire Key", "Triple Click"])
        self.media_group.setVisible(action == "Media Key")
        
        if action == "Fire Key":
            self.special_delay_spin.setValue(40)
            self.special_repeat_spin.setValue(3)
        elif action == "Triple Click":
            self.special_delay_spin.setValue(50)
            self.special_repeat_spin.setValue(3)

    def _build_macros_tab(self) -> QtWidgets.QWidget:
        """Build the visual macro editor tab with event list, recording, and preview."""
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)

        # --- Macro Name ---
        name_layout = QtWidgets.QHBoxLayout()
        name_layout.addWidget(QtWidgets.QLabel("Macro Name:"))
        self.macro_name_edit = QtWidgets.QLineEdit("my_macro")
        name_layout.addWidget(self.macro_name_edit, stretch=1)
        layout.addLayout(name_layout)

        # --- Recording Controls ---
        record_layout = QtWidgets.QHBoxLayout()
        self.record_button = QtWidgets.QPushButton("🔴 Record")
        self.record_button.setCheckable(True)
        self.record_button.setStyleSheet("QPushButton:checked { background-color: #ff4444; color: white; }")
        self.record_button.toggled.connect(self._toggle_recording)
        self.stop_record_button = QtWidgets.QPushButton("⏹ Stop")
        self.stop_record_button.setEnabled(False)
        self.stop_record_button.clicked.connect(self._stop_recording)
        self.clear_events_button = QtWidgets.QPushButton("Clear All")
        self.clear_events_button.clicked.connect(self._clear_macro_events)

        record_layout.addWidget(self.record_button)
        record_layout.addWidget(self.stop_record_button)
        record_layout.addWidget(self.clear_events_button)
        record_layout.addStretch()
        layout.addLayout(record_layout)

        # Recording state
        self._recording = False
        self._last_key_time: float = 0.0

        # --- Event Table ---
        layout.addWidget(QtWidgets.QLabel("Events:"))
        self.macro_event_table = QtWidgets.QTableWidget()
        self.macro_event_table.setColumnCount(5)
        self.macro_event_table.setHorizontalHeaderLabels(["#", "Key", "Action", "Delay (ms)", ""])
        self.macro_event_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Fixed)
        self.macro_event_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.macro_event_table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Fixed)
        self.macro_event_table.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.Fixed)
        self.macro_event_table.horizontalHeader().setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.Fixed)
        self.macro_event_table.setColumnWidth(0, 35)
        self.macro_event_table.setColumnWidth(2, 70)
        self.macro_event_table.setColumnWidth(3, 80)
        self.macro_event_table.setColumnWidth(4, 80)
        self.macro_event_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.macro_event_table.setMinimumHeight(200)
        layout.addWidget(self.macro_event_table)

        # Move Up/Down buttons
        move_layout = QtWidgets.QHBoxLayout()
        self.move_up_button = QtWidgets.QPushButton("▲ Move Up")
        self.move_up_button.clicked.connect(self._move_event_up)
        self.move_down_button = QtWidgets.QPushButton("▼ Move Down")
        self.move_down_button.clicked.connect(self._move_event_down)
        move_layout.addWidget(self.move_up_button)
        move_layout.addWidget(self.move_down_button)
        move_layout.addStretch()
        layout.addLayout(move_layout)

        # --- Manual Add Event ---
        add_group = QtWidgets.QGroupBox("Add Event Manually")
        add_layout = QtWidgets.QHBoxLayout(add_group)

        add_layout.addWidget(QtWidgets.QLabel("Key:"))
        self.add_key_combo = QtWidgets.QComboBox()
        for key_name in sorted(vp.HID_KEY_USAGE.keys(), key=lambda x: (len(x) > 1, x)):
            self.add_key_combo.addItem(key_name, vp.HID_KEY_USAGE[key_name])
        add_layout.addWidget(self.add_key_combo)

        add_layout.addWidget(QtWidgets.QLabel("Action:"))
        self.add_action_combo = QtWidgets.QComboBox()
        self.add_action_combo.addItem("Press", True)
        self.add_action_combo.addItem("Release", False)
        add_layout.addWidget(self.add_action_combo)

        add_layout.addWidget(QtWidgets.QLabel("Delay:"))
        self.add_delay_spin = QtWidgets.QSpinBox()
        self.add_delay_spin.setRange(0, 5000)
        self.add_delay_spin.setValue(50)
        self.add_delay_spin.setSuffix(" ms")
        add_layout.addWidget(self.add_delay_spin)

        self.add_event_button = QtWidgets.QPushButton("Add")
        self.add_event_button.clicked.connect(self._add_manual_event)
        add_layout.addWidget(self.add_event_button)

        layout.addWidget(add_group)

        # --- Preview ---
        preview_group = QtWidgets.QGroupBox("Preview")
        preview_layout = QtWidgets.QVBoxLayout(preview_group)
        self.macro_preview_label = QtWidgets.QLabel('Output: "" (0 ms)')
        self.macro_preview_label.setStyleSheet("font-family: monospace; padding: 4px;")
        preview_layout.addWidget(self.macro_preview_label)
        layout.addWidget(preview_group)

        # --- Bind & Upload ---
        bind_group = QtWidgets.QGroupBox("Upload && Bind")
        bind_layout = QtWidgets.QGridLayout(bind_group)

        bind_layout.addWidget(QtWidgets.QLabel("Bind to Button:"), 0, 0)
        self.macro_button_select = QtWidgets.QComboBox()
        for key, profile in vp.BUTTON_PROFILES.items():
            self.macro_button_select.addItem(profile.label, key)
        bind_layout.addWidget(self.macro_button_select, 0, 1)

        bind_layout.addWidget(QtWidgets.QLabel("Macro Index:"), 0, 2)
        self.macro_bind_index_spin = QtWidgets.QSpinBox()
        self.macro_bind_index_spin.setRange(1, 8)
        self.macro_bind_index_spin.setValue(1)
        bind_layout.addWidget(self.macro_bind_index_spin, 0, 3)

        bind_layout.addWidget(QtWidgets.QLabel("Repeat:"), 0, 4)
        self.macro_tab_repeat_combo = QtWidgets.QComboBox()
        self.macro_tab_repeat_combo.addItem("Run Once", vp.MACRO_REPEAT_ONCE)
        self.macro_tab_repeat_combo.addItem("Repeat While Held", vp.MACRO_REPEAT_HOLD)
        self.macro_tab_repeat_combo.addItem("Loop Until Key", vp.MACRO_REPEAT_TOGGLE)
        bind_layout.addWidget(self.macro_tab_repeat_combo, 0, 5)


        upload_button = QtWidgets.QPushButton("Upload Macro")
        upload_button.clicked.connect(self._upload_macro)
        bind_button = QtWidgets.QPushButton("Bind to Button")
        bind_button.clicked.connect(self._bind_macro_to_button)
        load_button = QtWidgets.QPushButton("Load from Device")
        load_button.clicked.connect(self._load_macro_from_slot_on_tab)

        bind_layout.addWidget(upload_button, 1, 0, 1, 2)
        bind_layout.addWidget(bind_button, 1, 2, 1, 2)
        bind_layout.addWidget(load_button, 1, 4, 1, 2)

        layout.addWidget(bind_group)
        layout.addStretch()

        return widget

    def _toggle_recording(self, checked: bool) -> None:
        """Start or stop macro recording."""
        if checked:
            self._recording = True
            self._last_key_time = 0.0
            self.record_button.setText("🔴 Recording...")
            self.stop_record_button.setEnabled(True)
            # Install event filter to capture key events
            QtWidgets.QApplication.instance().installEventFilter(self)
            self._log("Recording started - press keys to record macro events")
        else:
            self._stop_recording()

    def _stop_recording(self) -> None:
        """Stop macro recording."""
        self._recording = False
        self.record_button.setChecked(False)
        self.record_button.setText("🔴 Record")
        self.stop_record_button.setEnabled(False)
        QtWidgets.QApplication.instance().removeEventFilter(self)
        self._update_macro_preview()
        self._log("Recording stopped")

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        """Capture key events during recording."""
        if self._recording:
            if event.type() == QtCore.QEvent.Type.KeyPress or event.type() == QtCore.QEvent.Type.KeyRelease:
                key_event = event
                if key_event.isAutoRepeat():
                    return False  # Ignore auto-repeat

                key_text = key_event.text().upper()
                qt_key = key_event.key()

                # Map Qt key to HID key name
                key_name = self._qt_key_to_name(qt_key, key_text)
                if key_name and key_name in vp.HID_KEY_USAGE:
                    import time
                    current_time = time.time() * 1000  # ms
                    delay = int(current_time - self._last_key_time) if self._last_key_time > 0 else 0
                    delay = min(delay, 5000)  # Cap at 5 seconds
                    self._last_key_time = current_time

                    is_down = event.type() == QtCore.QEvent.Type.KeyPress
                    self._add_event_to_table(key_name, is_down, delay)
                    return True  # Consume the event

        return super().eventFilter(obj, event)

    def _qt_key_to_name(self, qt_key: int, key_text: str) -> str | None:
        """Convert Qt key code to HID key name."""
        # Handle letter keys
        if len(key_text) == 1 and key_text.isalpha():
            return key_text.upper()
        # Handle number keys
        if len(key_text) == 1 and key_text.isdigit():
            return key_text
        # Handle special keys
        key_map = {
            QtCore.Qt.Key.Key_Return: "Enter",
            QtCore.Qt.Key.Key_Enter: "Enter",
            QtCore.Qt.Key.Key_Escape: "Escape",
            QtCore.Qt.Key.Key_Backspace: "Backspace",
            QtCore.Qt.Key.Key_Tab: "Tab",
            QtCore.Qt.Key.Key_Space: "Space",
            QtCore.Qt.Key.Key_Insert: "Insert",
            QtCore.Qt.Key.Key_Home: "Home",
            QtCore.Qt.Key.Key_End: "End",
            QtCore.Qt.Key.Key_PageUp: "PageUp",
            QtCore.Qt.Key.Key_PageDown: "PageDown",
            QtCore.Qt.Key.Key_Delete: "Delete",
            QtCore.Qt.Key.Key_Left: "Left",
            QtCore.Qt.Key.Key_Right: "Right",
            QtCore.Qt.Key.Key_Up: "Up",
            QtCore.Qt.Key.Key_Down: "Down",
            QtCore.Qt.Key.Key_F1: "F1", QtCore.Qt.Key.Key_F2: "F2", QtCore.Qt.Key.Key_F3: "F3",
            QtCore.Qt.Key.Key_F4: "F4", QtCore.Qt.Key.Key_F5: "F5", QtCore.Qt.Key.Key_F6: "F6",
            QtCore.Qt.Key.Key_F7: "F7", QtCore.Qt.Key.Key_F8: "F8", QtCore.Qt.Key.Key_F9: "F9",
            QtCore.Qt.Key.Key_F10: "F10", QtCore.Qt.Key.Key_F11: "F11", QtCore.Qt.Key.Key_F12: "F12",
            QtCore.Qt.Key.Key_Comma: "Comma",
            QtCore.Qt.Key.Key_Period: "Period",
            QtCore.Qt.Key.Key_Slash: "Slash",
            QtCore.Qt.Key.Key_Semicolon: "Semicolon",
            QtCore.Qt.Key.Key_Minus: "Minus",
            QtCore.Qt.Key.Key_Equal: "Equal",
        }
        return key_map.get(qt_key)

    def _add_event_to_table(self, key_name: str, is_down: bool, delay: int) -> None:
        """Add an event row to the macro event table."""
        row = self.macro_event_table.rowCount()
        self.macro_event_table.insertRow(row)

        # Row number
        num_item = QtWidgets.QTableWidgetItem(str(row + 1))
        num_item.setFlags(num_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
        self.macro_event_table.setItem(row, 0, num_item)

        # Key name
        key_item = QtWidgets.QTableWidgetItem(key_name)
        key_item.setFlags(key_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
        self.macro_event_table.setItem(row, 1, key_item)

        # Action
        action_item = QtWidgets.QTableWidgetItem("Press" if is_down else "Release")
        action_item.setFlags(action_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
        action_item.setData(QtCore.Qt.ItemDataRole.UserRole, is_down)
        self.macro_event_table.setItem(row, 2, action_item)

        # Delay (editable)
        delay_spin = QtWidgets.QSpinBox()
        delay_spin.setRange(0, 5000)
        delay_spin.setValue(delay)
        delay_spin.setSuffix(" ms")
        delay_spin.valueChanged.connect(self._update_macro_preview)
        self.macro_event_table.setCellWidget(row, 3, delay_spin)

        # Delete button
        delete_btn = QtWidgets.QPushButton("✕")
        delete_btn.setMaximumWidth(30)
        delete_btn.clicked.connect(lambda: self._delete_event_row(row))
        self.macro_event_table.setCellWidget(row, 4, delete_btn)

        self._update_macro_preview()

    def _delete_event_row(self, row: int) -> None:
        """Delete a row from the event table."""
        # Find the current row of the delete button that was clicked
        sender = self.sender()
        for i in range(self.macro_event_table.rowCount()):
            if self.macro_event_table.cellWidget(i, 4) == sender:
                self.macro_event_table.removeRow(i)
                break
        self._renumber_rows()
        self._update_macro_preview()

    def _renumber_rows(self) -> None:
        """Renumber all rows in the event table."""
        for i in range(self.macro_event_table.rowCount()):
            item = self.macro_event_table.item(i, 0)
            if item:
                item.setText(str(i + 1))

    def _clear_macro_events(self) -> None:
        """Clear all events from the table."""
        self.macro_event_table.setRowCount(0)
        self._update_macro_preview()

    def _move_event_up(self) -> None:
        """Move the selected event up in the list."""
        row = self.macro_event_table.currentRow()
        if row > 0:
            self._swap_rows(row, row - 1)
            self.macro_event_table.selectRow(row - 1)

    def _move_event_down(self) -> None:
        """Move the selected event down in the list."""
        row = self.macro_event_table.currentRow()
        if row >= 0 and row < self.macro_event_table.rowCount() - 1:
            self._swap_rows(row, row + 1)
            self.macro_event_table.selectRow(row + 1)

    def _swap_rows(self, row1: int, row2: int) -> None:
        """Swap two rows in the event table."""
        # Get data from both rows
        data1 = self._get_row_data(row1)
        data2 = self._get_row_data(row2)

        # Set data in swapped positions
        self._set_row_data(row1, data2)
        self._set_row_data(row2, data1)
        self._renumber_rows()
        self._update_macro_preview()

    def _get_row_data(self, row: int) -> tuple:
        """Get data from a row."""
        key = self.macro_event_table.item(row, 1).text()
        action_item = self.macro_event_table.item(row, 2)
        is_down = action_item.data(QtCore.Qt.ItemDataRole.UserRole)
        delay_widget = self.macro_event_table.cellWidget(row, 3)
        delay = delay_widget.value() if delay_widget else 0
        return (key, is_down, delay)

    def _set_row_data(self, row: int, data: tuple) -> None:
        """Set data in a row."""
        key, is_down, delay = data
        self.macro_event_table.item(row, 1).setText(key)
        action_item = self.macro_event_table.item(row, 2)
        action_item.setText("Press" if is_down else "Release")
        action_item.setData(QtCore.Qt.ItemDataRole.UserRole, is_down)
        delay_widget = self.macro_event_table.cellWidget(row, 3)
        if delay_widget:
            delay_widget.setValue(delay)

    def _add_manual_event(self) -> None:
        """Add an event manually from the add controls."""
        key_name = self.add_key_combo.currentText()
        is_down = self.add_action_combo.currentData()
        delay = self.add_delay_spin.value()
        self._add_event_to_table(key_name, is_down, delay)

    def _update_macro_preview(self) -> None:
        """Update the preview label with the macro output."""
        # Build string from press events (assuming standard typing)
        result = []
        total_delay = 0
        pressed_keys = set()

        for row in range(self.macro_event_table.rowCount()):
            key = self.macro_event_table.item(row, 1).text() if self.macro_event_table.item(row, 1) else ""
            action_item = self.macro_event_table.item(row, 2)
            is_down = action_item.data(QtCore.Qt.ItemDataRole.UserRole) if action_item else True
            delay_widget = self.macro_event_table.cellWidget(row, 3)
            delay = delay_widget.value() if delay_widget else 0

            total_delay += delay

            if is_down:
                pressed_keys.add(key)
                # Only add to result for single-char keys to show "typed" output
                if len(key) == 1:
                    result.append(key.lower())
            else:
                pressed_keys.discard(key)

        output = "".join(result)
        self.macro_preview_label.setText(f'Output: "{output}" ({total_delay} ms total)')

    def _get_macro_events_from_table(self) -> list:
        """Extract macro events from the table."""
        events = []
        for row in range(self.macro_event_table.rowCount()):
            key_item = self.macro_event_table.item(row, 1)
            action_item = self.macro_event_table.item(row, 2)
            delay_widget = self.macro_event_table.cellWidget(row, 3)

            if not key_item or not action_item:
                continue

            key_name = key_item.text()
            is_down = action_item.data(QtCore.Qt.ItemDataRole.UserRole)
            delay = delay_widget.value() if delay_widget else 0

            if key_name in vp.HID_KEY_USAGE:
                events.append(vp.MacroEvent(
                    keycode=vp.HID_KEY_USAGE[key_name],
                    is_down=is_down,
                    delay_ms=delay
                ))
        return events

    def _build_rgb_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QFormLayout(widget)

        # Preset selector (quick options)
        self.rgb_select = QtWidgets.QComboBox()
        self.rgb_select.addItems(vp.RGB_PRESETS.keys())

        apply_preset_button = QtWidgets.QPushButton("Apply Preset")
        apply_preset_button.clicked.connect(self._apply_rgb_preset)

        layout.addRow("Presets:", self.rgb_select)
        layout.addRow("", apply_preset_button)

        # Separator
        layout.addRow(QtWidgets.QLabel(""))
        layout.addRow(QtWidgets.QLabel("Custom Color:"))

        # Color picker
        self.rgb_color_button = QtWidgets.QPushButton("Pick Color")
        self.rgb_color_button.setStyleSheet("background-color: #FF00FF; color: white; font-weight: bold;")
        self.rgb_color_button.clicked.connect(self._pick_rgb_color)
        self.rgb_current_color = QtGui.QColor(255, 0, 255)  # Default magenta
        
        # Mode selector
        self.rgb_mode = QtWidgets.QComboBox()
        self.rgb_mode.addItem("Off", vp.RGB_MODE_OFF)
        self.rgb_mode.addItem("Steady", vp.RGB_MODE_STEADY)
        self.rgb_mode.addItem("Breathing", vp.RGB_MODE_BREATHING)
        self.rgb_mode.setCurrentIndex(1)  # Default to Steady
        
        # Brightness slider
        self.rgb_brightness = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.rgb_brightness.setRange(0, 100)
        self.rgb_brightness.setValue(100)
        self.rgb_brightness_label = QtWidgets.QLabel("100%")
        self.rgb_brightness.valueChanged.connect(
            lambda v: self.rgb_brightness_label.setText(f"{v}%")
        )
        
        brightness_layout = QtWidgets.QHBoxLayout()
        brightness_layout.addWidget(self.rgb_brightness, stretch=1)
        brightness_layout.addWidget(self.rgb_brightness_label)

        apply_custom_button = QtWidgets.QPushButton("Apply Custom")
        apply_custom_button.clicked.connect(self._apply_rgb_custom)

        layout.addRow("Color:", self.rgb_color_button)
        layout.addRow("Mode:", self.rgb_mode)
        layout.addRow("Brightness:", brightness_layout)
        layout.addRow("", apply_custom_button)
        
        return widget

    def _pick_rgb_color(self) -> None:
        color = QtWidgets.QColorDialog.getColor(self.rgb_current_color, self, "Pick LED Color")
        if color.isValid():
            self.rgb_current_color = color
            self.rgb_color_button.setStyleSheet(
                f"background-color: {color.name()}; color: {'white' if color.lightness() < 128 else 'black'}; font-weight: bold;"
            )

    def _build_polling_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QFormLayout(widget)

        self.polling_select = QtWidgets.QComboBox()
        for rate in sorted(vp.POLLING_RATE_PAYLOADS.keys()):
            self.polling_select.addItem(f"{rate} Hz", rate)

        apply_button = QtWidgets.QPushButton("Apply Polling Rate")
        apply_button.clicked.connect(self._apply_polling_rate)

        layout.addRow("Polling rate:", self.polling_select)
        layout.addRow("", apply_button)
        return widget

    def _build_dpi_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)

        header = QtWidgets.QLabel("DPI slots (use presets or raw values from captures)")
        layout.addWidget(header)

        self.dpi_rows: list[tuple[QtWidgets.QComboBox, QtWidgets.QSpinBox, QtWidgets.QSpinBox]] = []
        for slot in range(5):
            row = QtWidgets.QHBoxLayout()
            label = QtWidgets.QLabel(f"Slot {slot + 1}")
            label.setMinimumWidth(60)

            combo = QtWidgets.QComboBox()
            combo.addItem("Custom", None)
            for dpi in sorted(vp.DPI_PRESETS.keys()):
                combo.addItem(f"{dpi} DPI", dpi)
            combo.currentIndexChanged.connect(self._sync_dpi_presets)

            value_spin = QtWidgets.QSpinBox()
            value_spin.setRange(0, 255)
            tweak_spin = QtWidgets.QSpinBox()
            tweak_spin.setRange(0, 255)

            row.addWidget(label)
            row.addWidget(combo)
            row.addWidget(QtWidgets.QLabel("Value"))
            row.addWidget(value_spin)
            row.addWidget(QtWidgets.QLabel("Tweak"))
            row.addWidget(tweak_spin)
            layout.addLayout(row)

            self.dpi_rows.append((combo, value_spin, tweak_spin))

        apply_button = QtWidgets.QPushButton("Apply DPI Slots")
        apply_button.clicked.connect(self._apply_dpi)
        layout.addWidget(apply_button)
        layout.addStretch(1)

        self._sync_dpi_presets()
        return widget

    def _build_advanced_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QFormLayout(widget)

        self.adv_command = QtWidgets.QLineEdit("07")
        self.adv_payload = QtWidgets.QLineEdit("")
        self.adv_raw = QtWidgets.QLineEdit("")

        send_built = QtWidgets.QPushButton("Send Built Report")
        send_raw = QtWidgets.QPushButton("Send Raw Report")

        send_built.clicked.connect(self._send_built_report)
        send_raw.clicked.connect(self._send_raw_report)

        layout.addRow("Command (hex):", self.adv_command)
        layout.addRow("Payload 14 bytes hex:", self.adv_payload)
        layout.addRow("", send_built)
        layout.addRow("Full report hex (17 bytes):", self.adv_raw)
        layout.addRow("", send_raw)
        
        # Factory Reset button
        layout.addRow("", QtWidgets.QLabel(""))  # Spacer
        reset_button = QtWidgets.QPushButton("⚠️ Factory Reset")
        reset_button.setStyleSheet("background-color: #cc4444; color: white; font-weight: bold; padding: 8px;")
        reset_button.clicked.connect(self._factory_reset)
        layout.addRow("", reset_button)
        
        return widget

    def _build_log(self) -> QtWidgets.QGroupBox:
        group = QtWidgets.QGroupBox("Log")
        layout = QtWidgets.QVBoxLayout(group)
        self.log_area = QtWidgets.QPlainTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMaximumBlockCount(2000)
        layout.addWidget(self.log_area)
        return group

    def _build_mouse_image(self) -> QtWidgets.QGroupBox:
        group = QtWidgets.QGroupBox("Mouse")
        layout = QtWidgets.QVBoxLayout(group)
        label = QtWidgets.QLabel()
        label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        img_path = Path(__file__).resolve().parent / "mouseimg.png"
        if img_path.exists():
            pixmap = QtGui.QPixmap(str(img_path))
            label.setPixmap(pixmap.scaledToWidth(420, QtCore.Qt.TransformationMode.SmoothTransformation))
        else:
            label.setText("mouseimg.png not found")
        layout.addWidget(label)
        return group


    def _store_custom_profile(self) -> None:
        button_key = self.current_edit_key
        if button_key is None:
            return
        # If it's a standard profile, we shouldn't be here (locked fields), but check anyway
        if button_key in vp.BUTTON_PROFILES:
            profile = vp.BUTTON_PROFILES[button_key]
            if profile.code_hi is not None:
                return

        self.custom_profiles[button_key] = (
            self.code_hi_spin.value(),
            self.code_lo_spin.value(),
            self.apply_offset_spin.value(),
        )

    def _resolve_profile(self, button_key: str, use_fallback: bool) -> tuple[int, int, int]:
        profile = vp.BUTTON_PROFILES[button_key]
        if profile.code_hi is not None and profile.code_lo is not None and profile.apply_offset is not None:
            return profile.code_hi, profile.code_lo, profile.apply_offset
        if button_key in self.custom_profiles:
            return self.custom_profiles[button_key]
        if use_fallback and button_key == self.current_edit_key:
            code_hi = self.code_hi_spin.value()
            code_lo = self.code_lo_spin.value()
            apply_offset = self.apply_offset_spin.value()
            self.custom_profiles[button_key] = (code_hi, code_lo, apply_offset)
            return code_hi, code_lo, apply_offset
        raise ValueError("Unknown button profile. Fill code/offset values in the Buttons tab first.")


    def _log(self, text: str) -> None:
        self.log_area.appendPlainText(text)

    def _refresh_devices(self) -> None:
        self.device_infos = vp.list_devices()
        self.device_combo.clear()
        if not self.device_infos:
            self.device_combo.addItem("No Venus Pro devices found")
            return
        for info in self.device_infos:
            label = f"{info.product} (0x{info.product_id:04x}) {info.serial}".strip()
            self.device_combo.addItem(label, info)

    def _connect_device(self) -> None:
        if not self.device_infos:
            QtWidgets.QMessageBox.warning(self, "No device", "No supported devices detected.")
            return
        info = self.device_combo.currentData()
        if info is None:
            QtWidgets.QMessageBox.warning(self, "No device", "Pick a device entry first.")
            return
        try:
            self.device = vp.VenusDevice(info.path)
            self.device.open()
            self.status_label.setText("Connected")
            self._log(f"Connected to {info.product} ({info.serial})")
        except Exception as exc:
            self.device = None
            QtWidgets.QMessageBox.critical(self, "Connect failed", str(exc))

    def _disconnect_device(self) -> None:
        if self.device is None:
            return
        self.device.close()
        self.device = None
        self.status_label.setText("Disconnected")
        self._log("Disconnected")

    def _refresh_and_connect(self) -> None:
        """Refresh devices and attempt to connect."""
        self._refresh_devices()
        self._auto_connect()

    def _auto_connect(self) -> None:
        """Automatically connect to the first available device and read settings."""
        if not self.device_infos:
            self.status_label.setText("No device found")
            return
        
        # Already connected?
        if self.device:
            return

        info = self.device_infos[0]
        try:
            self.device = vp.VenusDevice(info.path)
            self.device.open()
            self.status_label.setText(f"Connected: {info.product}")
            self._log(f"Auto-connected to {info.product}")
            self._read_settings() # Auto-read on connect
        except Exception as exc:
            self.device = None
            self.status_label.setText("Connection failed")
            self._log(f"Auto-connect failed: {exc}")

    def _require_device(self, auto_mode: bool = False) -> bool:
        if self.device is None:
            # Try to auto-connect first
            self._refresh_and_connect()
            
        if self.device is None:
            if not auto_mode: # Only show warnings for user-initiated actions, not lazy background checks
                QtWidgets.QMessageBox.warning(self, "No device", "Could not connect to device.")
            return False
        return True


    def _send_reports(self, reports: list[bytes], label: str) -> None:
        if not self._require_device():
            return
        try:
            import time
            for report in reports:
                self.device.send(report)
                self._log(f"{label}: {report.hex()}")
                # Protocol requires delay between commands to prevent drops
                # Wireless mode is slower/less reliable, increasing to 250ms
                time.sleep(0.25)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Send failed", str(exc))

    def _apply_button_binding(self) -> None:
        if not self._require_device():
            return
        
        button_key = self.current_edit_key
        if button_key is None:
            QtWidgets.QMessageBox.warning(self, "No Button", "Please select a button to edit first.")
            return

        action = self.action_select.currentText()

        reports = [vp.build_simple(0x04), vp.build_simple(0x03)]  # Windows sequence: 0x04 THEN 0x03

        if action == "Keyboard Key":
            # Get key from QKeySequenceEdit
            seq = self.key_select.keySequence()
            if seq.isEmpty():
                QtWidgets.QMessageBox.warning(self, "No Key", "Please type a key in the field.")
                return

            seq_str = seq.toString(QtGui.QKeySequence.SequenceFormat.PortableText)
            # seq_str might be "Ctrl+Shift+A" or "Return"
            parts = seq_str.split('+')
            base_key_name = parts[-1]
            
            # Map Qt names to HID names if needed
            name_map = {
                "Return": "Enter",
                "Esc": "Escape",
                "Del": "Delete",
                "Ins": "Insert",
                "PgUp": "PageUp",
                "PgDown": "PageDown",
                "Bksp": "Backspace",
                # Add more if found missing
            }
            hid_name = name_map.get(base_key_name, base_key_name)
            
            if hid_name not in vp.HID_KEY_USAGE:
                QtWidgets.QMessageBox.warning(self, "Unknown Key", f"Key '{base_key_name}' (mapped to '{hid_name}') not found in HID database.")
                return

            key_code = vp.HID_KEY_USAGE[hid_name]
            
            # Compute modifier byte from checkboxes (AND the typed sequence)
            # If user typed "Ctrl+A", we can infer Ctrl.
            # But user said "select modifier keys... with check boxes".
            # So we respect checkboxes primarily. 
            # Optionally we could auto-check them, but let's stick to reading them.
            
            modifier = 0
            if self.mod_ctrl.isChecked():
                modifier |= vp.MODIFIER_CTRL
            if self.mod_shift.isChecked():
                modifier |= vp.MODIFIER_SHIFT
            if self.mod_alt.isChecked():
                modifier |= vp.MODIFIER_ALT
            if self.mod_win.isChecked():
                modifier |= vp.MODIFIER_WIN
            
            # Resolve Base Profile (Profile 1) Addresses
            code_hi_base, code_lo, apply_offset_base = self._resolve_profile(button_key, use_fallback=True)
            
            # List of profile pages (Page 0x00, 0x40, 0x80, 0xC0)
            # We write to ALL of them to ensure consistency across Wired/Wireless modes
            profile_pages = [0x00, 0x40, 0x80, 0xC0]
            
            if action == "Reset Defaults":
                # Reset is global? Or per profile? 
                # Command 0x09 is simple. Assume global or irrelevant to page.
                self._send_reports([vp.build_simple(0x09)], "Reset defaults")
                return

            for page in profile_pages:
                # Adjust code_hi for the current page (Key Data page shifts with Profile page)
                # If Profile 1 keys are at Page 1, Profile 2 keys are at Page 0x41.
                current_code_hi = code_hi_base + page

                if action == "Keyboard Key":
                    reports.extend(vp.build_key_binding(current_code_hi, code_lo, key_code, modifier))
                    
                    # Application packet binding the slot to Keyboard function (Type 0x05)
                    reports.append(vp.build_apply_binding(apply_offset_base, action_type=vp.BUTTON_TYPE_KEYBOARD, action_code=0x50, modifier=modifier, page=page))

                elif action == "DPI Control":
                    # Map Function ID to (Key, Mod)
                    func_id = self.dpi_action_select.currentData()
                    
                    hid_key = 0x23  # Default 6
                    if func_id == 0x03: hid_key = 0x24 # 7
                    elif func_id == 0x01: hid_key = 0x25 # 8
                    
                    # Write Page 1 data: Simple Key Binding (No modifiers in stream)
                    reports.extend(vp.build_key_binding(current_code_hi, code_lo, hid_key, modifier=0))
                    
                    # Page 0 Binding: Type 0x02 (DPI Legacy), D1 = func_id
                    reports.append(vp.build_apply_binding(apply_offset_base, action_type=vp.BUTTON_TYPE_DPI_LEGACY, action_code=0x50, modifier=func_id, page=page))

                elif action in ["Left Click", "Right Click", "Middle Click", "Forward", "Back"]:
                    val_map = {
                        "Left Click": 0x01, "Right Click": 0x02, "Middle Click": 0x04,
                        "Back": 0x08, "Forward": 0x10
                    }
                    val = val_map[action]
                    reports.append(vp.build_mouse_param(apply_offset_base, val, page=page))

                elif action == "Macro":
                    macro_index = self.macro_index_spin.value()
                    repeat_mode = self.macro_repeat_combo.currentData()
                    reports.append(vp.build_macro_bind(apply_offset_base, macro_index, repeat_mode, page=page))

                elif action in ["Fire Key", "Triple Click"]:
                    delay_ms = self.special_delay_spin.value()
                    repeat_count = self.special_repeat_spin.value()
                    reports.append(vp.build_special_binding(apply_offset_base, delay_ms, repeat_count, page=page))

                elif action == "Media Key":
                    media_key_name = self.media_select.currentText()
                    media_code = self.media_select.currentData()
                    
                    # Media keys use a keyboard region packet structure (Type 0x05/0x02? Actually seen as Type 0x05)
                    # Payload construction:
                    payload = bytes([
                        0x00, current_code_hi, code_lo, 0x08, 0x02, 
                        0x82, media_code, 0x00, 
                        0x42, media_code, 0x00, 
                        0x00, 0x00, 0x00
                    ])
                    reports.append(vp.build_report(0x07, payload))
                    
                    # Apply packet (Type 0x05 Media)
                    reports.append(vp.build_apply_binding(apply_offset_base, action_type=vp.BUTTON_TYPE_MEDIA, action_code=0x51, page=page))

                elif action == "RGB Toggle":
                    reports.append(vp.build_rgb_toggle(apply_offset_base, page=page))

                elif action == "Polling Rate Toggle":
                    reports.append(vp.build_poll_rate_toggle(apply_offset_base, page=page))

                elif action == "Disabled":
                    reports.append(vp.build_disabled(apply_offset_base, page=page))

            # Add Commit and Wake Packets (Once at the end of the batch)
            reports.append(vp.build_simple(0x04))
            reports.append(vp.build_simple(0x03))
            
            desc_str = f"{action}"
            if action == "Keyboard Key" or action == "DPI Control":
                # Reconstruct mod string for logging
                if modifier:
                    parts = []
                    if modifier & vp.MODIFIER_CTRL: parts.append("Ctrl")
                    if modifier & vp.MODIFIER_SHIFT: parts.append("Shift")
                    if modifier & vp.MODIFIER_ALT: parts.append("Alt")
                    if modifier & vp.MODIFIER_WIN: parts.append("Win")
                    mod_str = "+".join(parts) + "+"
                    desc_str += f" ({mod_str}{hid_name})"
                else:
                    desc_str += f" ({hid_name})"
            elif action == "Macro":
                 desc_str += f" {self.macro_index_spin.value()}"

            self._send_reports(reports, f"Bind {button_key} -> {desc_str} (All 4 Profiles)")
            return



    def _upload_macro(self) -> None:
        if not self._require_device():
            return
        name = self.macro_name_edit.text().strip() or "macro"
        
        # Get events from the visual table
        macro_events = self._get_macro_events_from_table()
        
        if not macro_events:
            QtWidgets.QMessageBox.warning(self, "No Events", "Add some macro events before uploading.")
            return

        # Get the target button to check availability (not used for page calc anymore)
        button_key = self.macro_button_select.currentData()
        try:
            _, _, apply_offset = self._resolve_profile(button_key, use_fallback=False)
        except ValueError as exc:
            QtWidgets.QMessageBox.warning(self, "Missing profile", str(exc))
            return
        
        # Determine Macro Index and Repeat Mode
        macro_index = self.macro_bind_index_spin.value()
        repeat_mode = self.macro_tab_repeat_combo.currentData()

        # Calculate macro memory location using new slot logic
        start_page, start_offset = vp.get_macro_slot_info(macro_index)
        self._log(f"Using macro slot {macro_index}: Page 0x{start_page:02X}, Offset 0x{start_offset:02X}")

        # Prepare name (UTF-16LE)
        name_bytes = name.encode("utf-16le")
        # Name is stored at offset 0 (1 byte header + bytes). Max safe len ~20 bytes?
        # Protocol uses 1 byte for name length.
        
        # Build macro buffer
        try:
            # First, check total size
            # Name takes len(name_bytes) + 1
            # Events take 5 bytes * 2 * num_events (approx 10 bytes per key cycle)
            total_size = 1 + len(name_bytes) + (len(macro_events) * 10) + 6 # +6 for terminator
            
            if total_size > 384:
                msg = f"Macro is too large ({total_size} bytes). Max is 384 bytes.\nPlease reduce event count."
                QtWidgets.QMessageBox.warning(self, "Macro limitations", msg)
                return

            buf = bytearray(0x200) # Use reasonably large buffer, but we only send what's needed
            # Byte 0 = Slot Index (NOT name length! This was a bug causing all macros to show Slot=6)
            buf[0] = macro_index
            # Name is UTF-16LE starting at byte 1, padded with zeros to byte 0x1E (30 bytes max)
            name_bytes_capped = name_bytes[:28]  # Max 28 bytes = 14 chars
            buf[1 : 1 + len(name_bytes_capped)] = name_bytes_capped

            # Pack events into buffer starting at 0x1E
            event_offset = 0x20  # Events start after header (byte 0x1F is event count)
            for event in macro_events:
                event_data = event.to_bytes()
                buf[event_offset : event_offset + len(event_data)] = event_data
                event_offset += len(event_data)

            # Terminator goes after last event - align to 10-byte boundary
            terminator_offset = ((event_offset + 9) // 10) * 10  # Round up to next 10
            if terminator_offset < event_offset:
                terminator_offset = event_offset + 10 # Should have been covered by round up, but safety

            self._log(f"Events end at buffer 0x{event_offset:02X}, terminator at 0x{terminator_offset:02X}")
            
            # The terminator chunk itself is built by build_macro_terminator, which includes 
            # [00 03 OFFSET 00...]. The offset inside the terminator is the offset WITHIN the macro slot?
            # Or the absolute offset? Existing code passed 'terminator_offset' (buffer offset).
            # Let's trust it's relative to macro start. But we need to verify terminator logic later if it fails.
            
            # Terminator bytes for the buffer (we'll manually construct chunks rather than using helper for terminator)
            # Or just stop iterating at terminator_offset and send terminator separately?
            # Let's iterate up to terminator_offset.
            
        except Exception as e:
            self._log(f"Error building buffer: {e}")
            return

        # Upload sequence
        # Upload sequence
        reports = [
            # Windows sequence: 0x04 (Prepare) -> 0x03 (Handshake)
            vp.build_simple(0x04),
            vp.build_simple(0x03),
        ]
        
        # Upload chunks of 10 bytes up to terminator_offset
        # Map buffer offsets to absolute (Page, Offset)
        for buf_offset in range(0x00, terminator_offset, 0x0A):
            chunk = bytes(buf[buf_offset : buf_offset + 10])
            
            # Calculate absolute address
            abs_addr_int = (start_page << 8) | start_offset
            curr_addr_int = abs_addr_int + buf_offset
            
            curr_page = (curr_addr_int >> 8) & 0xFF
            curr_offset = curr_addr_int & 0xFF
            
            packet = vp.build_macro_chunk(curr_offset, chunk, curr_page)
            reports.append(packet)
            
        # Terminator
        # Calculate address for terminator
        abs_term_int = (start_page << 8) | start_offset + terminator_offset
        term_page = (abs_term_int >> 8) & 0xFF
        term_offset = abs_term_int & 0xFF
        
        # build_macro_terminator helper uses build_macro_chunk internally.
        # It puts [00 03 OFFSET 00...]. 
        # CAUTION: The 'OFFSET' in the terminator data payload might need to be specific.
        # Captures showed "00 03 64 00..." for terminator at offset 0x64.
        # So it likely wants the *buffer offset* (relative to macro start), not absolute 0x80+offset.
        # We'll pass terminator_offset as the 'offset' argument to the helper (for payload), 
        # but we need to ensure the helper uses term_page/term_offset for the REPORT structure.
        
        # Current vp.build_macro_terminator(offset, page) calls build_macro_chunk(offset, tail, page).
        # It uses 'offset' for both payload and chunk address. This is wrong if start_offset != 0.
        # We need to manually build the terminator chunk here to be precise.
        
        term_payload_inner = bytes([0x00, 0x03, terminator_offset & 0xFF, 0x00, 0x00, 0x00])
        reports.append(vp.build_macro_chunk(term_offset, term_payload_inner, term_page))
        
        # Bind macro to button
        reports.append(vp.build_macro_bind(apply_offset, macro_index, repeat_mode))
        
        # Commit changes - No trailing 0x04 found in captures
        # reports.append(vp.build_simple(0x04))
        
        self._send_reports(reports, f"Upload macro '{name}' (Slot {macro_index}) to {button_key}")
        self._log(f"Macro uploaded (Size: {total_size}B).")


    def _bind_macro_to_button(self) -> None:
        """Rebind an already-uploaded macro to a different button."""
        if not self._require_device():
            return
        button_key = self.macro_button_select.currentData()
        macro_index = self.macro_bind_index_spin.value()
        repeat_mode = self.macro_tab_repeat_combo.currentData()
        
        try:
            _, _, apply_offset = self._resolve_profile(button_key, use_fallback=False)
        except ValueError as exc:
            QtWidgets.QMessageBox.warning(self, "Missing profile", str(exc))
            return
        reports = [vp.build_simple(0x04), vp.build_simple(0x03), vp.build_macro_bind(apply_offset, macro_index, repeat_mode)]
        self._send_reports(reports, f"Bind macro {macro_index} -> {button_key}")


    def _apply_rgb_preset(self) -> None:
        preset_key = self.rgb_select.currentText()
        payload = vp.RGB_PRESETS[preset_key]
        reports = [vp.build_simple(0x04), vp.build_simple(0x03), vp.build_report(0x07, payload)]
        self._send_reports(reports, f"RGB Preset: {preset_key}")

    def _apply_rgb_custom(self) -> None:
        if not self._require_device():
            return
        r = self.rgb_current_color.red()
        g = self.rgb_current_color.green()
        b = self.rgb_current_color.blue()
        mode = self.rgb_mode.currentData()
        brightness = self.rgb_brightness.value()
        
        rgb_packet = vp.build_rgb(r, g, b, mode, brightness)
        # Sequence based on captures: 03, 03, [RGB], 04
        reports = [vp.build_simple(0x04), vp.build_simple(0x03), rgb_packet]
        
        mode_name = self.rgb_mode.currentText()
        self._send_reports(reports, f"RGB Custom: #{r:02x}{g:02x}{b:02x} {mode_name} {brightness}%")


    def _apply_polling_rate(self) -> None:
        rate = self.polling_select.currentData()
        payload = vp.POLLING_RATE_PAYLOADS[rate]
        reports = [vp.build_simple(0x04), vp.build_simple(0x03), vp.build_report(0x07, payload)]
        self._send_reports(reports, f"Polling {rate} Hz")

    def _sync_dpi_presets(self) -> None:
        for combo, value_spin, tweak_spin in self.dpi_rows:
            dpi_value = combo.currentData()
            if dpi_value is None:
                continue
            preset = vp.DPI_PRESETS[dpi_value]
            value_spin.blockSignals(True)
            tweak_spin.blockSignals(True)
            value_spin.setValue(preset["value"])
            tweak_spin.setValue(preset["tweak"])
            value_spin.blockSignals(False)
            tweak_spin.blockSignals(False)

    def _apply_dpi(self) -> None:
        reports = [vp.build_simple(0x03)]
        for slot, (_, value_spin, tweak_spin) in enumerate(self.dpi_rows):
            reports.append(vp.build_dpi(slot, value_spin.value(), tweak_spin.value()))
        # reports.append(vp.build_simple(0x04)) # No trailing 0x04
        self._send_reports(reports, "DPI slots")

    def _send_built_report(self) -> None:
        if not self._require_device():
            return
        try:
            command = int(self.adv_command.text().strip(), 16)
            payload_hex = self.adv_payload.text().strip().replace(" ", "")
            payload = bytes.fromhex(payload_hex)
            report = vp.build_report(command, payload)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "Invalid input", str(exc))
            return
        self._send_reports([report], "Advanced built")

    def _send_raw_report(self) -> None:
        if not self._require_device():
            return
        try:
            raw_hex = self.adv_raw.text().strip().replace(" ", "")
            report = bytes.fromhex(raw_hex)
        except ValueError as exc:
            QtWidgets.QMessageBox.warning(self, "Invalid hex", str(exc))
            return
        if len(report) != vp.REPORT_LEN:
            QtWidgets.QMessageBox.warning(self, "Invalid length", f"Report must be {vp.REPORT_LEN} bytes.")
            return
        self._send_reports([report], "Advanced raw")


    def _factory_reset(self) -> None:
        if not self._require_device():
            return
        
        reply = QtWidgets.QMessageBox.question(
            self, 
            "Confirm Reset", 
            "Are you sure you want to reset the device to factory defaults?\nThis will clear all custom button mappings, macros, and RGB settings.",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
        )
        
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            self._send_reports([vp.build_simple(0x09)], "Factory reset")
            QtWidgets.QMessageBox.information(self, "Reset Complete", "Factory reset command sent.")

    def _read_settings(self) -> None:
        if not self._require_device(auto_mode=True):
            return
        
        self._log("--- Reading from Device ---")
        try:
            # Ensure clean state and enter config mode
            self.device.send(vp.build_simple(0x04))
            self.device.send(vp.build_simple(0x03))
            
            # Page 0 contains most settings
            page0 = bytearray()
            # Read in larger chunks if reliable, but sticking to 8 bytes for now
            for offset in range(0, 256, 8):
                chunk = self.device.read_flash(0, offset, 8)
                page0.extend(chunk)
            
            # Page 1 contains keyboard mappings (Part 1)
            page1 = bytearray()
            for offset in range(0, 256, 8):
                chunk = self.device.read_flash(1, offset, 8)
                page1.extend(chunk)

            # Page 2 contains keyboard mappings (Part 2)
            page2 = bytearray()
            for offset in range(0, 256, 8):
                chunk = self.device.read_flash(2, offset, 8)
                page2.extend(chunk)


            self._log("Flash pages 0 and 1 read complete.")

            # 1. DPI Levels
            dpi_offsets = [0x0C, 0x10, 0x14, 0x18, 0x1C]
            for i, offset in enumerate(dpi_offsets):
                val = page0[offset]
                closest_dpi = 1000
                min_diff = 999
                for dpi, info in vp.DPI_PRESETS.items():
                    if abs(info["value"] - val) < min_diff:
                        min_diff = abs(info["value"] - val)
                        closest_dpi = dpi
                
                if i < len(self.dpi_rows):
                    combo, value_spin, tweak_spin = self.dpi_rows[i]
                    combo.blockSignals(True)
                    # Find DPI in combo
                    found = False
                    for idx in range(combo.count()):
                        if combo.itemData(idx) == closest_dpi:
                            combo.setCurrentIndex(idx)
                            found = True
                            break
                    if not found:
                        combo.setCurrentIndex(0) # Custom
                    
                    value_spin.setValue(val)
                    # Tweak is usually fixed for the preset, but let's try reading it too?
                    # Captures show tweak at offset+2? Let's check DPI_PRESETS again.
                    # Actually, let's just use our presets for now to be safe.
                    preset = vp.DPI_PRESETS.get(closest_dpi)
                    if preset:
                        tweak_spin.setValue(preset["tweak"])
                    
                    combo.blockSignals(False)

            # 2. Polling Rate
            poll_code = page0[0x04]
            rate = 1000
            if poll_code == 0x04: rate = 125
            elif poll_code == 0x02: rate = 250
            elif poll_code == 0x01: rate = 500
            elif poll_code == 0x00: rate = 1000
            
            # Find the rate in the combo box
            for i in range(self.polling_select.count()):
                if self.polling_select.itemData(i) == rate:
                    self.polling_select.setCurrentIndex(i)
                    self._log(f"  Polling Rate: {rate}Hz")
                    break

            # 3. RGB Settings
            rgb_r = page0[0x55]
            rgb_g = page0[0x56]
            rgb_b = page0[0x57]
            rgb_mode = page0[0x58]
            brightness_b1 = page0[0x5B]
            
            self.rgb_current_color = QtGui.QColor(rgb_r, rgb_g, rgb_b)
            self.rgb_color_button.setStyleSheet(
                f"background-color: {self.rgb_current_color.name()}; "
                f"color: {'white' if self.rgb_current_color.lightness() < 128 else 'black'}; "
                f"font-weight: bold;"
            )
            
            # Update mode combo
            # Map 0x56/0x57 back to our labels
            if rgb_mode == 0x56:
                idx = self.rgb_mode.findData(vp.RGB_MODE_STEADY)
                if idx >= 0: self.rgb_mode.setCurrentIndex(idx)
            elif rgb_mode == 0x57:
                idx = self.rgb_mode.findData(vp.RGB_MODE_BREATHING) # Or neon
                if idx >= 0: self.rgb_mode.setCurrentIndex(idx)
            elif rgb_mode == 0x00: # Off
                idx = self.rgb_mode.findData(vp.RGB_MODE_OFF)
                if idx >= 0: self.rgb_mode.setCurrentIndex(idx)
            
            # Brightness
            brightness = int(brightness_b1 / 3)
            self.rgb_brightness.setValue(brightness)
            self.rgb_brightness_label.setText(f"{brightness}%")
            self._log(f"  RGB: ({rgb_r},{rgb_g},{rgb_b}), Mode: 0x{rgb_mode:02X}, Brightness: {brightness}%")

            # 4. Button Bindings
            self._log("  Parsing Button bindings...")
            for button_key, profile in vp.BUTTON_PROFILES.items():
                offset = profile.apply_offset
                btype = page0[offset]
                d1 = page0[offset + 1]
                d2 = page0[offset + 2]
                
                action = "Disabled"
                params = {}
                
                self._log(f"DEBUG: Parsing {button_key} (Offset 0x{offset:02X}) -> Type 0x{btype:02X}, D1 0x{d1:02X}, D2 0x{d2:02X}")

                if btype == vp.BUTTON_TYPE_MOUSE:
                    if d1 == 0x01: action = "Left Click"
                    elif d1 == 0x02: action = "Right Click"
                    elif d1 == 0x04: action = "Middle Click"
                    elif d1 == 0x08: action = "Back"
                    elif d1 == 0x10: action = "Forward"
                    else: action = f"Mouse Button (0x{d1:02X})"
                
                # Correct parsing maps back to dict for consistent params
                params = {}
                if action in ["Left Click", "Right Click", "Middle Click", "Back", "Forward"]:
                    params["type"] = "mouse" # just context
                
                # Split logic: Type 0x05 is Standard Keyboard, Type 0x02 is DPI Legacy
                elif btype == vp.BUTTON_TYPE_KEYBOARD: # 0x05 (Standard/Complex)
                    p1_offset = profile.code_lo
                    # ... (rest of keyboard logic follows)
                    
                elif btype == vp.BUTTON_TYPE_DPI_LEGACY: # 0x02 (DPI Shortcuts)
                    action = "DPI Control"
                    # D1 determines function: 02=Loop, 03=+, 01=-
                    params["dpi_func"] = d1
                    
                # Continue with old logic for compat if needed, but the elif above handles 0x05
                if btype == vp.BUTTON_TYPE_KEYBOARD: # Re-enter block for keyboard processing
                    p1_offset = profile.code_lo
                    # Use code_hi to determine which page to read from
                    kbd_page_src = page1 if profile.code_hi == 0x01 else page2
                    page_name = "Page 1" if profile.code_hi == 0x01 else "Page 2"
                    
                    self._log(f"  DEBUG: Checking {page_name} offset 0x{p1_offset:02X}")
                    
                    kbd_page = kbd_page_src # Alias
                    
                    # Ensure offset is within bounds (256 bytes per page)
                    if p1_offset + 8 <= len(kbd_page):
                        # Dump raw bytes for debugging
                        raw_bytes = kbd_page[p1_offset : p1_offset + 8]
                        self._log(f"  DEBUG: Raw Kbd Data: {raw_bytes.hex()}")

                        # Flash format seems to be: [Type] [Header] [Key] [Mod] ... without the 0x08 length byte
                        p1_type = kbd_page[p1_offset + 0]
                        p1_header = kbd_page[p1_offset + 1]
                        
                     
                        if p1_type == 0x02:
                            # Standard Key or Media
                            if p1_header == 0x81: # Keyboard
                                action = "Keyboard Key"
                                params["key"] = kbd_page[p1_offset + 2]
                                # Modifier is in Page 0 D1 field, NOT Page 1/2 data
                                params["mod"] = d1
                            elif p1_header == 0x82: # Media
                                action = "Media Key"
                                params["key"] = kbd_page[p1_offset + 2]
                            else:
                                action = f"Unknown Kbd (02 {p1_header:02X})"
                        elif p1_type == 0x04:
                            # Complex binding (4-event stream with modifiers)
                            # Format: [04] [80 MM 00] [81 KK 00] [40 MM 00] [41 KK 00] [Guard]
                            # Byte offsets: 0=count, 1=80(ModDn), 2=Modifier, 3=pad, 4=81(KeyDn), 5=Key, 6=pad
                            action = "Keyboard Key"
                            params["key"] = kbd_page[p1_offset + 5]  # Key is at offset+5 (after 81)
                            # For 4-event stream, modifier is embedded in the ModDn event (byte 2)
                            params["mod"] = kbd_page[p1_offset + 2]  # Modifier from ModDn event
                        elif p1_type == 0x06:
                            # Multi-modifier binding (6-event stream: Ctrl+Shift+Key)
                            # Format: [06] [80 M1 00] [80 M2 00] [81 KK 00] [40 M1 00] [40 M2 00] [41 KK 00]
                            # Byte offsets: 0=count, 1-3=ModDn1, 4-6=ModDn2, 7=81(KeyDn), 8=Key
                            action = "Keyboard Key"
                            params["key"] = kbd_page[p1_offset + 8]  # Key is at offset+8 (after two ModDn + 81)
                            # Combine both modifiers (OR them together)
                            mod1 = kbd_page[p1_offset + 2]  # First modifier
                            mod2 = kbd_page[p1_offset + 5]  # Second modifier
                            params["mod"] = mod1 | mod2
                        else:
                            action = f"Unknown Type (0x{p1_type:02X})"
                    else:
                        action = "Disabled (OOB)"
                elif btype == vp.BUTTON_TYPE_MACRO:
                    action = "Macro"
                    macro_index = d1
                    params["index"] = macro_index + 1
                    self._log(f"  DEBUG: Macro Index {macro_index+1}")
                    
                    # Fetch macro name from its flash page
                    macro_page = vp.get_macro_page(profile.apply_offset)
                    try:
                        name_chunk = self.device.read_flash(macro_page, 0x00, 11)
                        if name_chunk and name_chunk[0] > 0 and name_chunk[0] <= 22:
                            nlen = name_chunk[0]
                            params["name"] = name_chunk[1:1+nlen].decode('utf-16le', errors='ignore')
                        else:
                            params["name"] = f"Macro {macro_index+1}"
                    except:
                        params["name"] = f"Macro {macro_index+1}"
                elif btype == vp.BUTTON_TYPE_SPECIAL:
                    action = "Triple Click" if d1 == 50 else "Fire Key"
                    params["delay"] = d1
                    params["repeat"] = d2
                elif btype == vp.BUTTON_TYPE_POLL_RATE:
                    action = "Polling Rate Toggle"
                elif btype == vp.BUTTON_TYPE_RGB_TOGGLE:
                    action = "RGB Toggle"

                self.button_assignments[button_key] = {"action": action, "params": params}
                self._log(f"  DEBUG: Resolved Action: {action} {params}")

            self._log("Button bindings parsed.")
            self._update_all_ui_from_assignments()
            
            # Close session to return mouse to normal input mode
            # Sending Commit (04) signals end of config. 
            self.device.send(vp.build_simple(0x04))
            
            self._log("--- Done Reading ---")
            QtWidgets.QMessageBox.information(self, "Read Success", "Configuration successfully read from device.")

        except Exception as e:
            self._log(f"Error reading configuration: {e}")
            QtWidgets.QMessageBox.critical(self, "Read Error", str(e))

    def _export_profile(self) -> None:
        """Dump device memory to a file."""
        if not self._require_device():
            return
            
        fname, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save Profile", "profile.bin", "Binary Files (*.bin)")
        if not fname:
            return
            
        progress = QtWidgets.QProgressDialog("Exporting profile...", "Cancel", 0, 256, self)
        progress.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        progress.show()
        
        try:
            with open(fname, "wb") as f:
                for page in range(256):
                    if progress.wasCanceled():
                        return
                    progress.setValue(page)
                    
                    # Read page (256 bytes)
                    page_data = bytearray()
                    for offset in range(0, 256, 8):
                        chunk = self.device.read_flash(page, offset, 8)
                        page_data.extend(chunk)
                    f.write(page_data)
            self._log(f"Profile exported to {fname}")
            QtWidgets.QMessageBox.information(self, "Export Successful", f"Profile saved to {fname}")
        except Exception as e:
            self._log(f"Export failed: {e}")
            QtWidgets.QMessageBox.critical(self, "Export Failed", str(e))
        finally:
            progress.close()

    def _import_profile(self) -> None:
        """Load profile from file and write to device."""
        if not self._require_device():
            return
            
        fname, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open Profile", "", "Binary Files (*.bin)")
        if not fname:
            return
            
        try:
            data = open(fname, "rb").read()
            if len(data) != 65536: # 256 * 256
                QtWidgets.QMessageBox.warning(self, "Invalid File", f"File size must be exactly 64KB (got {len(data)} bytes).")
                return
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Read Failed", str(e))
            return
            
        # Warning
        reply = QtWidgets.QMessageBox.question(
            self, "Confirm Import", 
            "This will overwrite ALL device settings (macros, bindings, etc) with the imported profile.\nContinue?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
        )
        if reply != QtWidgets.QMessageBox.StandardButton.Yes:
            return
            
        progress = QtWidgets.QProgressDialog("Importing profile (Writing Flash)...", "Cancel", 0, 256, self)
        progress.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        progress.show()
        
        try:
            # Prepare flash?
            # Upload macro sequence uses 0x03, 0x03...
            # We should probably send Prepare before each page or once at start?
            # Let's do it once globally, or per page if safer.
            # Captures for macros use it once per macro op.
            
            # Send initial prepare
            self.device.send(vp.build_simple(0x03))
            self.device.send(vp.build_simple(0x03))
            
            import time
            
            for page in range(256):
                if progress.wasCanceled():
                    break
                progress.setValue(page)
                
                # Extract page data
                page_start = page * 256
                page_data = data[page_start : page_start + 256]
                
                # Check if empty (FF) - optimization
                # If page is all 0xFF, we might skip if flash is pre-erased, but we don't know state.
                # Safer to write all, or check if different? READING is slow.
                # Writing 0xFF might be fast or slow.
                # Let's write everything for correctness.
                
                # Write in 10-byte chunks (protocol limit)
                for offset in range(0, 256, 10):
                    chunk = page_data[offset : offset + 10]
                    # build_flash_write(page, offset, chunk) -> build_macro_chunk -> returns packet
                    packet = vp.build_flash_write(page, offset, chunk)
                    self.device.send(packet)
                    time.sleep(0.002) # Small delay to prevent flooding
                    
            # Finalize
            self.device.send(vp.build_simple(0x04))
            self.device.send(vp.build_simple(0x04))
            
            self._log(f"Profile imported from {fname}")
            QtWidgets.QMessageBox.information(self, "Import Successful", "Profile successfully written to device.")
            
            # Reload settings
            self._read_settings()
            
        except Exception as e:
            self._log(f"Import failed: {e}")
            QtWidgets.QMessageBox.critical(self, "Import Failed", str(e))
        finally:
            progress.close()

    def _initialize_default_assignments(self) -> None:

        """Initialize assignments with Disabled for all known buttons."""
        for button_key in vp.BUTTON_PROFILES.keys():
            self.button_assignments[button_key] = {"action": "Disabled", "params": {}}
            
    def _update_all_ui_from_assignments(self) -> None:
        """Refresh the button table and other UI."""
        for row in range(self.btn_table.rowCount()):
            key = self.btn_table.item(row, 0).data(QtCore.Qt.ItemDataRole.UserRole)
            if key in self.button_assignments:
                assign = self.button_assignments[key]
                action = assign["action"]
                desc = action
                if action == "Keyboard Key":
                    k = assign["params"].get("key", 0)
                    k_name = self.HID_USAGE_TO_NAME.get(k, f"{k}")
                    
                    # Also show modifiers if present
                    mod = assign["params"].get("mod", 0)
                    mod_str = ""
                    if mod:
                        parts = []
                        if mod & vp.MODIFIER_CTRL: parts.append("Ctrl")
                        if mod & vp.MODIFIER_SHIFT: parts.append("Shift")
                        if mod & vp.MODIFIER_ALT: parts.append("Alt")
                        if mod & vp.MODIFIER_WIN: parts.append("Win")
                        mod_str = "+".join(parts) + "+"

                    desc = f"Key: {mod_str}{k_name}"
                    
                elif action == "DPI Control":
                    func = assign["params"].get("dpi_func", 0)
                    if func == 0x02: desc = "DPI Loop (Shift+6)"
                    elif func == 0x03: desc = "DPI + (Ctrl+Shift+7)"
                    elif func == 0x01: desc = "DPI - (Ctrl+8)"
                    else: desc = f"DPI Control (0x{func:02X})"
                elif action == "Media Key":
                    media_code = assign["params"].get("key", 0)
                    # Reverse lookup media code to name
                    media_name = None
                    for name, code in vp.MEDIA_KEY_CODES.items():
                        if code == media_code:
                            media_name = name
                            break
                    desc = f"Media: {media_name or f'0x{media_code:02X}'}"
                elif action == "Macro":
                    desc = f"Macro: {assign['params'].get('name', '')}"
                
                self.btn_table.item(row, 1).setText(desc)

    def _load_macro_from_slot_on_tab(self) -> None:
        """Load macro from slot using the Macros tab's slot index spinner."""
        if not self._require_device():
            return
        # The existing _load_macro_from_slot reads from macro_index_spin (Buttons tab)
        # Temporarily sync the value from macro_bind_index_spin (Macros tab)
        slot_index = self.macro_bind_index_spin.value()
        self.macro_index_spin.setValue(slot_index)
        self._load_macro_from_slot()

    def _load_macro_from_slot(self) -> None:
        """Read macro from selected slot and populate table."""
        if not self._require_device():
            return
            
        slot_index = self.macro_index_spin.value()
        start_page, start_offset = vp.get_macro_slot_info(slot_index)
        
        self._log(f"Reading macro slot {slot_index} (Page 0x{start_page:02X}, Offset 0x{start_offset:02X})")
        
        self._log(f"Reading macro slot {slot_index} (Page 0x{start_page:02X}, Offset 0x{start_offset:02X})")
        
        # Retry logic for read error (device might have reset or timed out)
        data = bytearray()
        try:
            # Check if we can read one byte first to verify connection?
            # Or just wrap the whole read loop
            
            def attempt_read():
                data.clear()
                # Page 1
                for off in range(0, 256, 8):
                    data.extend(self.device.read_flash(start_page, off, 8))
                # Page 2
                for off in range(0, 256, 8):
                    data.extend(self.device.read_flash(start_page + 1, off, 8))
            
            try:
                attempt_read()
            except (OSError, RuntimeError) as e:
                self._log(f"Read failed ({e}), attempting reconnect...")
                self._disconnect_device()
                import time
                time.sleep(0.5)
                self._refresh_and_connect()
                if self.device:
                     self._log("Reconnected. Retrying read...")
                     attempt_read()
                else:
                    raise e # Re-raise if reconnect failed

            # Slice relevant part
            if start_offset == 0:
                raw_macro = data[0:384]
            else:
                raw_macro = data[128 : 128 + 384] # Offset 0x80 = 128
                
            # Parse Name
            # Byte 0 is slot index (NOT name length - this was a bug!)
            # Name is at bytes 1-28 in UTF-16LE, null terminated
            slot_in_data = raw_macro[0]
            self._log(f"  Slot index in data: {slot_in_data}")
            
            # Find name by looking for null terminator in UTF-16LE (00 00)
            name_bytes = bytearray()
            for i in range(1, 29, 2):
                if i+1 < len(raw_macro):
                    lo = raw_macro[i]
                    hi = raw_macro[i+1]
                    if lo == 0 and hi == 0:
                        break
                    name_bytes.extend([lo, hi])
            
            if name_bytes:
                try:
                    name = name_bytes.decode('utf-16le')
                    self.macro_name_edit.setText(name)
                except:
                    self.macro_name_edit.setText(f"Macro {slot_index}")
            else:
                self.macro_name_edit.setText(f"Macro {slot_index}")
                
            # Parse Events
            self.macro_event_table.setRowCount(0)
            event_offset = 0x20  # Events start after header (byte 0x1F is event count)
            
            # Events are 5 bytes: [Status] [Key] 00 [DelayHi] [DelayLo]
            while event_offset < 380:
                # Check for terminator (might be in the stream)
                # If we encounter 0xFF 0xFF or something, or just name boundary?
                # The buffer is 384 bytes.
                # Terminator is implicitly where we stop?
                # Existing write logic writes a terminator chunk [00 03...].
                # But reading raw data, we look for something not event-like?
                
                # Check if enough bytes left for an event
                if event_offset + 5 > 384:
                    break
                    
                b0 = raw_macro[event_offset]
                b1 = raw_macro[event_offset+1]
                
                # Heuristic: Valid status is 0x81 (Down) or 0x41 (Up)
                if b0 not in (0x81, 0x41):
                    # Likely terminator or empty space (0xFF or 0x00)
                    break
                    
                keycode = b1
                delay = (raw_macro[event_offset+3] << 8) | raw_macro[event_offset+4]
                is_down = (b0 == 0x81)
                
                key_name = self.HID_USAGE_TO_NAME.get(keycode, f"Key 0x{keycode:02X}")
                
                self._add_event_to_table(key_name, is_down, delay)
                
                event_offset += 5
                
            self._log(f"Loaded macro slot {slot_index}")
            
        except Exception as e:
            self._log(f"Failed to load macro: {e}")
            QtWidgets.QMessageBox.critical(self, "Load Error", str(e))

    def _generate_text_macro(self) -> None:
        """Generate macro events from quick text."""
        text = self.quick_text_edit.text()
        if not text:
            return
            
        delay = self.quick_delay_spin.value()
        
        self.macro_event_table.setRowCount(0)
        
        estimated_bytes = 1 + len(text.encode('utf-16le')) + (len(text) * 10) + 6
        if estimated_bytes > 384:
             QtWidgets.QMessageBox.warning(self, "Too Long", f"Estimated size {estimated_bytes} > 384 bytes.")
             return
        
        for char in text:
            if char in vp.ASCII_TO_HID:
                code, mod = vp.ASCII_TO_HID[char]
                key_name = self.HID_USAGE_TO_NAME.get(code, f"Key 0x{code:02X}")
                
                # TODO: Handle modifiers if we want to be fancy.
                # For now, just press the key.
                
                # Press
                self._add_event_to_table(key_name, True, delay)
                # Release
                self._add_event_to_table(key_name, False, delay) # Optional small delay on release? Use same for now.
            else:
                self._log(f"Skipping unknown char: {char}")


def main() -> None:

    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

from __future__ import annotations

import json
import copy
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict, List, Optional, Set, Tuple

from .constants import BALL_COLORS, COLOR_HEX, DIRECTIONS, ENTITY_TYPES, LEVEL_DIFFICULTIES
from .gate_text import gates_to_text, parse_gate_text
from .level_data import (
    entity_bg,
    entity_label,
    find_cell,
    make_empty_level,
    make_shooter_entity,
    make_shooter_modifiers,
    make_tunnel_entity,
    make_wall_entity,
    normalize_runtime_level,
    set_grid_size,
)
from .utils import safe_int, short_id
from .validator import LevelValidator

DEFAULT_LEVEL_SAVE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Levels"))

class BallDropLevelEditor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("BallDropParty Level Editor - Python GUI")
        self.geometry("1600x920")
        self.minsize(1360, 780)
        try:
            self.state("zoomed")
        except tk.TclError:
            pass

        self.level = make_empty_level()
        self.current_file: Optional[str] = None
        self.saved_level_snapshot = copy.deepcopy(self.level)
        self.level_folder = DEFAULT_LEVEL_SAVE_DIR
        self.level_file_ids: List[int] = []
        self.selected_cell: Optional[Tuple[int, int]] = None
        self.selected_grid_cells: Set[Tuple[int, int]] = set()
        self.grid_buttons: Dict[Tuple[int, int], tk.Button] = {}
        self.grid_button_frames: Dict[Tuple[int, int], tk.Frame] = {}
        self.gate_hit_areas: List[Dict[str, Any]] = []
        self.selected_gate_index = 0
        self.selected_gate_indices: Set[int] = {0}
        self.selected_tray_index: Optional[int] = None
        self.selected_trays: Set[Tuple[int, int]] = set()
        self.selected_layer_index = 0
        self._validation_after_id: Optional[str] = None
        self.undo_stack: List[Dict[str, Any]] = []
        self.redo_stack: List[Dict[str, Any]] = []
        self.clipboard_entity: Optional[Dict[str, Any]] = None
        self.grid_drag_cell: Optional[Tuple[int, int]] = None
        self.gate_drag_source: Optional[Tuple[int, int]] = None

        self._init_level_meta_vars()
        self._build_ui()
        self._refresh_all()
        self._mark_current_level_saved()

    def _init_level_meta_vars(self):
        self.game_mode_var = tk.StringVar(value="Classic")
        self.difficulty_var = tk.StringVar(value="Normal")
        self.level_var = tk.StringVar(value="1")
        self.file_level_var = tk.StringVar(value="1")
        self.category_var = tk.IntVar(value=0)
        self.time_var = tk.IntVar(value=60)
        self.level_name_var = tk.StringVar(value="New Level")
        self.level_folder_var = tk.StringVar(value=f"Folder: {self.level_folder}")
        self.level_file_status_var = tk.StringVar(value="No file loaded")

    def _build_ui(self):
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)
        self.columnconfigure(2, weight=0)
        self.rowconfigure(0, weight=1)

        left = ttk.Frame(self, padding=8)
        left.grid(row=0, column=0, sticky="ns")
        right = ttk.Frame(self, padding=8)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)
        validation_side = ttk.Frame(self, padding=(0, 8, 8, 8), width=340)
        validation_side.grid(row=0, column=2, sticky="ns")
        validation_side.grid_propagate(False)
        validation_side.rowconfigure(0, weight=1)
        validation_side.columnconfigure(0, weight=1)

        self._build_toolbar(left)
        self._build_brush_panel(left)
        self._build_grid_panel(left)

        self.tabs = ttk.Notebook(right)
        self.tabs.grid(row=0, column=0, sticky="nsew")

        self.grid_tab = ttk.Frame(self.tabs, padding=8)
        self.gate_tab = ttk.Frame(self.tabs, padding=8)
        self.json_tab = ttk.Frame(self.tabs, padding=8)

        self.tabs.add(self.grid_tab, text="Grid")
        self.tabs.add(self.gate_tab, text="Gate / Tray")
        self.tabs.add(self.json_tab, text="JSON Preview")

        self._build_grid_editor(self.grid_tab)
        self._build_gate_editor(self.gate_tab)
        self._build_json_preview(self.json_tab)
        self._build_validation_panel(validation_side)

    def _build_toolbar(self, parent):
        frame = ttk.LabelFrame(parent, text="File / Level", padding=8)
        frame.pack(fill="x", pady=(0, 8))

        ttk.Button(frame, text="New", command=self.new_level).pack(fill="x", pady=2)
        ttk.Button(frame, text="Choose JSON Folder", command=self.choose_level_folder).pack(fill="x", pady=2)
        ttk.Label(frame, textvariable=self.level_folder_var, wraplength=220, justify="left").pack(fill="x", pady=(2, 6))

        level_row = ttk.Frame(frame)
        level_row.pack(fill="x", pady=2)
        ttk.Label(level_row, text="File #", width=8).pack(side="left")
        level_entry = ttk.Entry(level_row, textvariable=self.file_level_var, width=9)
        level_entry.pack(side="left", fill="x", expand=True)
        level_entry.bind("<Return>", lambda e: self.load_selected_level())

        load_row = ttk.Frame(frame)
        load_row.pack(fill="x", pady=2)
        ttk.Button(load_row, text="Previous", command=self.load_previous_level).pack(side="left", fill="x", expand=True)
        ttk.Button(load_row, text="Load", command=self.load_selected_level).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(load_row, text="Next", command=self.load_next_level).pack(side="left", fill="x", expand=True)

        meta_row = ttk.Frame(frame)
        meta_row.pack(fill="x", pady=(6, 2))
        ttk.Label(meta_row, text="Difficulty", width=8).pack(side="left")
        difficulty_combo = ttk.Combobox(meta_row, textvariable=self.difficulty_var, values=LEVEL_DIFFICULTIES, state="readonly", width=12)
        difficulty_combo.pack(side="left", fill="x", expand=True)
        difficulty_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh_json_preview())

        ttk.Button(frame, text="Save", command=self.save_json).pack(fill="x", pady=2)
        ttk.Button(frame, text="Save As", command=self.save_json_as).pack(fill="x", pady=2)
        ttk.Label(frame, textvariable=self.level_file_status_var, wraplength=220, justify="left").pack(fill="x", pady=(2, 6))
        ttk.Separator(frame).pack(fill="x", pady=6)
        ttk.Button(frame, text="Undo", command=self.undo).pack(fill="x", pady=2)
        ttk.Button(frame, text="Redo", command=self.redo).pack(fill="x", pady=2)
        ttk.Button(frame, text="Info", command=self.show_info).pack(fill="x", pady=2)

    def _build_brush_panel(self, parent):
        frame = ttk.LabelFrame(parent, text="Brush", padding=8)
        frame.pack(fill="x", pady=(0, 8))

        self.brush_type = tk.StringVar(value="Shooter")
        self.brush_color = tk.StringVar(value="Blue")
        self.brush_capacity = tk.IntVar(value=9)
        self.brush_hidden_modifier = tk.BooleanVar(value=False)
        self.brush_ice_modifier = tk.BooleanVar(value=False)
        self.brush_ice_hp = tk.IntVar(value=1)
        self.brush_ice_can_click = tk.BooleanVar(value=False)
        self.brush_ice_blocks_activation = tk.BooleanVar(value=True)
        self.tunnel_direction = tk.StringVar(value="Up")
        self.tunnel_queue = tk.StringVar(value="Blue:5, Red:5")

        ttk.Label(frame, text="Entity").pack(anchor="w")
        brush_type_combo = ttk.Combobox(frame, textvariable=self.brush_type, values=ENTITY_TYPES, state="readonly")
        brush_type_combo.pack(fill="x", pady=2)
        brush_type_combo.bind("<<ComboboxSelected>>", lambda e: self.update_brush_tunnel_state())

        ttk.Label(frame, text="Shooter color").pack(anchor="w")
        ttk.Combobox(frame, textvariable=self.brush_color, values=BALL_COLORS[1:], state="readonly").pack(fill="x", pady=2)

        ttk.Label(frame, text="Capacity").pack(anchor="w")
        ttk.Spinbox(frame, from_=1, to=999, textvariable=self.brush_capacity).pack(fill="x", pady=2)

        modifier_frame = ttk.LabelFrame(frame, text="Shooter modifiers", padding=6)
        modifier_frame.pack(fill="x", pady=(6, 2))
        ttk.Checkbutton(modifier_frame, text="Hidden", variable=self.brush_hidden_modifier).pack(anchor="w")
        ttk.Checkbutton(
            modifier_frame,
            text="Ice",
            variable=self.brush_ice_modifier,
            command=self.update_brush_modifier_state,
        ).pack(anchor="w")
        self.ice_hp_label = ttk.Label(modifier_frame, text="Ice HP")
        self.ice_hp_label.pack(anchor="w")
        self.ice_hp_spin = ttk.Spinbox(modifier_frame, from_=1, to=999, textvariable=self.brush_ice_hp)
        self.ice_hp_spin.pack(fill="x", pady=2)
        self.ice_can_click_check = ttk.Checkbutton(
            modifier_frame,
            text="Can click while frozen",
            variable=self.brush_ice_can_click,
        )
        self.ice_can_click_check.pack(anchor="w")
        self.ice_blocks_activation_check = ttk.Checkbutton(
            modifier_frame,
            text="Blocks activation",
            variable=self.brush_ice_blocks_activation,
        )
        self.ice_blocks_activation_check.pack(anchor="w")

        self.tunnel_direction_label = ttk.Label(frame, text="Tunnel direction")
        self.tunnel_direction_label.pack(anchor="w")
        self.tunnel_direction_combo = ttk.Combobox(frame, textvariable=self.tunnel_direction, values=DIRECTIONS, state="readonly")
        self.tunnel_direction_combo.pack(fill="x", pady=2)

        self.tunnel_queue_label = ttk.Label(frame, text="Tunnel queue")
        self.tunnel_queue_label.pack(anchor="w")
        self.tunnel_queue_entry = ttk.Entry(frame, textvariable=self.tunnel_queue)
        self.tunnel_queue_entry.pack(fill="x", pady=2)

        ttk.Button(frame, text="Apply to selected cell", command=self.apply_brush_to_selected).pack(fill="x", pady=(8, 2))
        ttk.Button(frame, text="Clear selected cell", command=self.clear_selected_cell).pack(fill="x", pady=2)
        ttk.Button(frame, text="Apply modifiers to selected", command=self.apply_modifiers_to_selected_shooters).pack(fill="x", pady=(8, 2))
        ttk.Button(frame, text="Remove modifiers from selected", command=self.remove_modifiers_from_selected_shooters).pack(fill="x", pady=2)
        ttk.Button(frame, text="Load selected modifiers", command=self.load_selected_shooter_modifiers).pack(fill="x", pady=2)
        self.update_brush_tunnel_state()
        self.update_brush_modifier_state()

    def update_brush_tunnel_state(self):
        if not hasattr(self, "tunnel_direction_combo"):
            return
        state = "readonly" if self.brush_type.get() == "Tunnel" else "disabled"
        entry_state = "normal" if self.brush_type.get() == "Tunnel" else "disabled"
        self.tunnel_direction_combo.configure(state=state)
        self.tunnel_queue_entry.configure(state=entry_state)

    def update_brush_modifier_state(self):
        if not hasattr(self, "ice_hp_spin"):
            return
        state = "normal" if self.brush_ice_modifier.get() else "disabled"
        self.ice_hp_spin.configure(state=state)
        self.ice_can_click_check.configure(state=state)
        self.ice_blocks_activation_check.configure(state=state)

    def _build_grid_panel(self, parent):
        frame = ttk.LabelFrame(parent, text="Grid Size", padding=8)
        frame.pack(fill="x", pady=(0, 8))

        self.rows_var = tk.IntVar(value=4)
        self.cols_var = tk.IntVar(value=4)

        row = ttk.Frame(frame)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Rows", width=8).pack(side="left")
        ttk.Spinbox(row, from_=1, to=20, textvariable=self.rows_var, width=7).pack(side="left")

        row = ttk.Frame(frame)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Columns", width=8).pack(side="left")
        ttk.Spinbox(row, from_=1, to=20, textvariable=self.cols_var, width=7).pack(side="left")

        ttk.Button(frame, text="Resize/Rebuild", command=self.resize_grid).pack(fill="x", pady=(8, 2))

    def _build_grid_editor(self, parent):
        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=1)

        tools = ttk.LabelFrame(parent, text="Grid Tools", padding=8)
        tools.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        tools.columnconfigure(8, weight=1)
        self.grid_paint_on_click_var = tk.BooleanVar(value=True)
        self.grid_right_clear_var = tk.BooleanVar(value=True)
        self.grid_multi_shooter_select_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(tools, text="Paint on click", variable=self.grid_paint_on_click_var).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(tools, text="Right click clears", variable=self.grid_right_clear_var).grid(row=0, column=1, sticky="w", padx=(12, 0))
        ttk.Checkbutton(tools, text="Multi shooter select", variable=self.grid_multi_shooter_select_var).grid(row=0, column=2, sticky="w", padx=(12, 0))
        ttk.Button(tools, text="Paint Selected", command=self.apply_brush_to_selected).grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Button(tools, text="Clear Selected", command=self.clear_selected_cell).grid(row=1, column=1, sticky="w", padx=(12, 0), pady=(8, 0))
        ttk.Button(tools, text="Copy", command=self.copy_selected_cell).grid(row=1, column=2, sticky="w", padx=(12, 0), pady=(8, 0))
        ttk.Button(tools, text="Paste", command=self.paste_selected_cell).grid(row=1, column=3, sticky="w", padx=(12, 0), pady=(8, 0))

        grid_holder = ttk.LabelFrame(parent, text="Grid Click/Paint", padding=8)
        grid_holder.grid(row=1, column=0, sticky="nsew")
        grid_holder.rowconfigure(0, weight=1)
        grid_holder.columnconfigure(0, weight=1)

        self.grid_canvas = tk.Canvas(grid_holder, highlightthickness=0)
        self.grid_scroll_y = ttk.Scrollbar(grid_holder, orient="vertical", command=self.grid_canvas.yview)
        self.grid_scroll_x = ttk.Scrollbar(grid_holder, orient="horizontal", command=self.grid_canvas.xview)
        self.grid_canvas.configure(yscrollcommand=self.grid_scroll_y.set, xscrollcommand=self.grid_scroll_x.set)

        self.grid_canvas.grid(row=0, column=0, sticky="nsew")
        self.grid_scroll_y.grid(row=0, column=1, sticky="ns")
        self.grid_scroll_x.grid(row=1, column=0, sticky="ew")

        self.grid_inner = ttk.Frame(self.grid_canvas)
        self.grid_canvas_window = self.grid_canvas.create_window((0, 0), window=self.grid_inner, anchor="nw")
        self.grid_inner.bind("<Configure>", lambda e: self.grid_canvas.configure(scrollregion=self.grid_canvas.bbox("all")))

        self.selected_label = ttk.Label(parent, text="Selected: none")
        self.selected_label.grid(row=2, column=0, sticky="w", pady=(8, 0))

    def _build_gate_editor(self, parent):
        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=1)

        top = ttk.LabelFrame(parent, text="Gate System", padding=8)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        top.columnconfigure(5, weight=1)

        self.gate_count_var = tk.IntVar(value=4)
        self.max_visible_var = tk.IntVar(value=4)

        ttk.Label(top, text="Gate Count").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(top, from_=1, to=12, textvariable=self.gate_count_var, width=8).grid(row=0, column=1, sticky="w", padx=6)
        ttk.Label(top, text="Max Visible Tray / Gate").grid(row=0, column=2, sticky="w", padx=(12, 0))
        ttk.Spinbox(top, from_=1, to=10, textvariable=self.max_visible_var, width=8).grid(row=0, column=3, sticky="w", padx=6)

        ttk.Button(top, text="Apply gate count", command=self.apply_gate_system).grid(row=0, column=4, padx=8)
        ttk.Button(top, text="Refresh Gate", command=self.apply_gate_ui).grid(row=0, column=5, sticky="e", padx=(8, 0))

        preview_holder = ttk.LabelFrame(parent, text="Gate Direct Edit", padding=8)
        preview_holder.grid(row=1, column=0, sticky="nsew")
        preview_holder.rowconfigure(0, weight=1)
        preview_holder.columnconfigure(0, weight=1)

        self.gate_preview_canvas = tk.Canvas(
            preview_holder,
            height=320,
            bg="#242941",
            highlightthickness=0,
            relief="flat",
        )
        self.gate_preview_scroll_y = ttk.Scrollbar(preview_holder, orient="vertical", command=self.gate_preview_canvas.yview)
        self.gate_preview_canvas.configure(yscrollcommand=self.gate_preview_scroll_y.set)
        self.gate_preview_canvas.grid(row=0, column=0, sticky="nsew")
        self.gate_preview_scroll_y.grid(row=0, column=1, sticky="ns")
        self.gate_preview_canvas.bind("<Configure>", lambda e: self.draw_gate_preview())
        self.gate_preview_canvas.bind("<Button-1>", self.on_gate_preview_click)
        self.gate_preview_canvas.bind("<ButtonRelease-1>", self.on_gate_preview_release)
        self.gate_preview_canvas.bind("<MouseWheel>", lambda e: self.gate_preview_canvas.yview_scroll(int(-e.delta / 120), "units"))

        self._build_gate_direct_controls(preview_holder)

        text_tools = ttk.LabelFrame(parent, text="Text Import / Export", padding=8)
        text_tools.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        text_tools.columnconfigure(0, weight=1)
        self.gate_text = tk.Text(text_tools, height=6, wrap="none", font=("Consolas", 10))
        self.gate_text.grid(row=0, column=0, sticky="ew")
        btns = ttk.Frame(text_tools)
        btns.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(btns, text="Parse Text", command=self.apply_gate_text).pack(side="left")
        ttk.Button(btns, text="Reload Text", command=self.refresh_gate_text).pack(side="left", padx=8)

    def _build_gate_direct_controls(self, parent):
        controls = ttk.Frame(parent, padding=(0, 8, 0, 0))
        controls.grid(row=1, column=0, sticky="ew")
        controls.columnconfigure(6, weight=1)

        self.gate_selection_label = ttk.Label(controls, text="Selected: Gate 0")
        self.gate_selection_label.grid(row=0, column=0, columnspan=10, sticky="w", pady=(0, 6))
        self.add_layer_enabled_var = tk.BooleanVar(value=False)

        ttk.Button(controls, text="+ Tray", command=self.add_tray_to_selected_gate).grid(row=1, column=0, padx=(0, 4), pady=2)
        ttk.Button(controls, text="Up", command=lambda: self.move_selected_tray(-1)).grid(row=1, column=1, padx=4, pady=2)
        ttk.Button(controls, text="Down", command=lambda: self.move_selected_tray(1)).grid(row=1, column=2, padx=4, pady=2)
        ttk.Button(controls, text="Delete Tray", command=self.remove_selected_tray).grid(row=1, column=3, padx=4, pady=2)
        ttk.Button(controls, text="Gate Left", command=lambda: self.move_selected_gate(-1)).grid(row=1, column=4, padx=(12, 4), pady=2)
        ttk.Button(controls, text="Gate Right", command=lambda: self.move_selected_gate(1)).grid(row=1, column=5, padx=4, pady=2)

        ttk.Label(controls, text="Tray ID").grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.selected_tray_id_var = tk.StringVar()
        tray_id_entry = ttk.Entry(controls, textvariable=self.selected_tray_id_var, width=18)
        tray_id_entry.grid(row=2, column=1, columnspan=2, sticky="w", padx=(4, 12), pady=(8, 0))
        tray_id_entry.bind("<Return>", lambda e: self.apply_selected_tray_fields())
        tray_id_entry.bind("<FocusOut>", lambda e: self.apply_selected_tray_fields())

        layer_controls = ttk.Frame(controls)
        layer_controls.grid(row=1, column=7, rowspan=2, sticky="e", padx=(18, 0))

        self.add_layer_button = ttk.Button(layer_controls, text="+ Layer", command=self.add_layer_to_selected_tray, state="disabled")
        self.add_layer_button.grid(row=0, column=0, padx=(0, 4), pady=2)
        ttk.Button(layer_controls, text="Delete Layer", command=self.remove_selected_layer).grid(row=0, column=1, padx=4, pady=2)
        ttk.Checkbutton(layer_controls, text="Enable +Layer", variable=self.add_layer_enabled_var, command=self.update_add_layer_button_state).grid(row=0, column=2, sticky="w", padx=(8, 0), pady=2)

        ttk.Label(layer_controls, text="Layer").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.selected_layer_var = tk.IntVar(value=0)
        layer_spin = ttk.Spinbox(layer_controls, from_=0, to=0, textvariable=self.selected_layer_var, width=5, command=self.select_layer_from_control)
        layer_spin.grid(row=1, column=1, sticky="w", padx=(4, 12), pady=(8, 0))
        layer_spin.bind("<Return>", lambda e: self.select_layer_from_control())
        layer_spin.bind("<FocusOut>", lambda e: self.select_layer_from_control())
        self.selected_layer_spin = layer_spin

        ttk.Label(layer_controls, text="Color").grid(row=1, column=2, sticky="w", pady=(8, 0))
        self.selected_layer_color_var = tk.StringVar(value="Blue")
        color_combo = ttk.Combobox(layer_controls, textvariable=self.selected_layer_color_var, values=BALL_COLORS[1:], state="readonly", width=12)
        color_combo.grid(row=1, column=3, sticky="w", padx=(4, 12), pady=(8, 0))
        color_combo.bind("<<ComboboxSelected>>", lambda e: self.apply_selected_layer_fields())

        ttk.Label(layer_controls, text="Count").grid(row=1, column=4, sticky="w", pady=(8, 0))
        self.selected_layer_count_var = tk.IntVar(value=3)
        count_spin = ttk.Spinbox(layer_controls, from_=1, to=999, textvariable=self.selected_layer_count_var, width=7, command=self.apply_selected_layer_fields)
        count_spin.grid(row=1, column=5, sticky="w", padx=(4, 0), pady=(8, 0))
        count_spin.bind("<Return>", lambda e: self.apply_selected_layer_fields())
        count_spin.bind("<FocusOut>", lambda e: self.apply_selected_layer_fields())

    def update_add_layer_button_state(self):
        if not hasattr(self, "add_layer_button"):
            return
        state = "normal" if self.add_layer_enabled_var.get() else "disabled"
        self.add_layer_button.configure(state=state)

    def _build_json_preview(self, parent):
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)
        self.json_text = tk.Text(parent, wrap="none", font=("Consolas", 10))
        self.json_text.grid(row=0, column=0, sticky="nsew")
        ttk.Button(parent, text="Refresh Preview", command=self.refresh_json_preview).grid(row=1, column=0, sticky="ew", pady=(8, 0))

    def _build_validation_panel(self, parent):
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)
        frame = ttk.LabelFrame(parent, text="Validate", padding=8)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.rowconfigure(3, weight=1)
        frame.columnconfigure(0, weight=1)

        self.validation_summary = tk.Label(
            frame,
            text="Not checked",
            bg="#4B5563",
            fg="#FFFFFF",
            padx=8,
            pady=6,
            anchor="w",
        )
        self.validation_summary.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        actions = ttk.Frame(frame)
        actions.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        actions.columnconfigure(1, weight=1)
        self.auto_validate_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(actions, text="Auto check", variable=self.auto_validate_var, command=self.mark_level_changed).grid(row=0, column=0, sticky="w")
        ttk.Button(actions, text="Check Now", command=self.validate_level).grid(row=0, column=1, sticky="e")

        balance_frame = ttk.LabelFrame(frame, text="Color Balance", padding=4)
        balance_frame.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        balance_frame.columnconfigure(0, weight=1)
        columns = ("color", "shooter", "tray", "delta")
        self.color_balance_tree = ttk.Treeview(balance_frame, columns=columns, show="headings", height=10)
        for key, title, width in [
            ("color", "Color", 78),
            ("shooter", "Shooter", 70),
            ("tray", "Tray", 70),
            ("delta", "Delta", 60),
        ]:
            self.color_balance_tree.heading(key, text=title)
            self.color_balance_tree.column(key, width=width, minwidth=48, anchor="center", stretch=(key == "color"))
        self.color_balance_tree.grid(row=0, column=0, sticky="ew")
        self.color_balance_tree.tag_configure("ok", background="#064E3B", foreground="#D1FAE5")
        self.color_balance_tree.tag_configure("bad", background="#7F1D1D", foreground="#FEE2E2")
        self.color_balance_tree.tag_configure("unused", background="#374151", foreground="#E5E7EB")

        self.validation_text = tk.Text(
            frame,
            wrap="word",
            font=("Consolas", 10),
            padx=8,
            pady=8,
            relief="flat",
            bg="#111827",
            fg="#E5E7EB",
            insertbackground="#E5E7EB",
            state="disabled",
        )
        self.validation_text.grid(row=3, column=0, sticky="nsew")
        self.validation_text.tag_configure("error_header", foreground="#FFFFFF", background="#B91C1C", spacing1=6, spacing3=4)
        self.validation_text.tag_configure("warning_header", foreground="#111827", background="#FBBF24", spacing1=6, spacing3=4)
        self.validation_text.tag_configure("ok_header", foreground="#FFFFFF", background="#047857", spacing1=6, spacing3=4)
        self.validation_text.tag_configure("error_item", foreground="#FCA5A5", lmargin1=8, lmargin2=20, spacing3=3)
        self.validation_text.tag_configure("warning_item", foreground="#FDE68A", lmargin1=8, lmargin2=20, spacing3=3)
        self.validation_text.tag_configure("info_item", foreground="#A7F3D0", lmargin1=8, lmargin2=20, spacing3=3)

    def new_level(self):
        if self.has_unsaved_changes():
            if not self._confirm_discard_unsaved_changes("creating a new level"):
                return
        elif not messagebox.askyesno("New Level", "Create a new level?"):
            return
        self.record_history()
        self.level = make_empty_level()
        self.current_file = None
        self._refresh_all()
        self._mark_current_level_saved()

    def current_level_id(self) -> int:
        return max(1, safe_int(str(self.level_var.get()), 1))

    def selected_file_level_id(self) -> int:
        return max(1, safe_int(str(self.file_level_var.get()), self.current_level_id()))

    def _mark_current_level_saved(self):
        self.sync_basic_fields()
        self.saved_level_snapshot = copy.deepcopy(self.level)

    def has_unsaved_changes(self) -> bool:
        self.sync_basic_fields()
        return self.level != self.saved_level_snapshot

    def _confirm_discard_unsaved_changes(self, action: str) -> bool:
        if not self.has_unsaved_changes():
            return True
        change_log = "\n".join(f"- {item}" for item in self.unsaved_change_log())
        return messagebox.askyesno(
            "Unsaved Changes",
            f"Current level has unsaved changes before {action}.\n\n"
            f"Unsaved changes:\n{change_log}\n\n"
            "Continue and discard these changes?",
        )

    def unsaved_change_log(self, max_items: int = 20) -> List[str]:
        changes: List[str] = []
        self._collect_changed_paths(self.saved_level_snapshot, self.level, "", changes, max_items + 1)
        if not changes:
            return ["No detailed changes found."]
        if len(changes) > max_items:
            return changes[:max_items] + ["... more changes not shown"]
        return changes

    def _collect_changed_paths(self, before: Any, after: Any, path: str, changes: List[str], limit: int):
        if len(changes) >= limit:
            return
        label = path or "level"
        if type(before) is not type(after):
            changes.append(f"{label}: {self._format_change_value(before)} -> {self._format_change_value(after)}")
            return
        if isinstance(before, dict):
            for key in sorted(set(before) | set(after), key=str):
                child_path = f"{label}.{key}" if path else str(key)
                if key not in before:
                    changes.append(f"{child_path}: added {self._format_change_value(after[key])}")
                elif key not in after:
                    changes.append(f"{child_path}: removed {self._format_change_value(before[key])}")
                else:
                    self._collect_changed_paths(before[key], after[key], child_path, changes, limit)
                if len(changes) >= limit:
                    return
            return
        if isinstance(before, list):
            if len(before) != len(after):
                changes.append(f"{label}: list length {len(before)} -> {len(after)}")
                if len(changes) >= limit:
                    return
            for idx, (before_item, after_item) in enumerate(zip(before, after)):
                self._collect_changed_paths(before_item, after_item, f"{label}[{idx}]", changes, limit)
                if len(changes) >= limit:
                    return
            return
        if before != after:
            changes.append(f"{label}: {self._format_change_value(before)} -> {self._format_change_value(after)}")

    def _format_change_value(self, value: Any) -> str:
        if isinstance(value, dict):
            entity_type = value.get("type")
            if entity_type:
                return f"{entity_type} object"
            return f"object({len(value)} keys)"
        if isinstance(value, list):
            return f"list({len(value)})"
        text = repr(value)
        return text if len(text) <= 80 else f"{text[:77]}..."

    def _level_id_from_path(self, path: str) -> Optional[int]:
        stem = os.path.splitext(os.path.basename(path))[0]
        if not stem.isdigit():
            return None
        level_id = int(stem)
        return level_id if level_id > 0 else None

    def _refresh_level_folder_files(self):
        ids: List[int] = []
        if os.path.isdir(self.level_folder):
            try:
                names = os.listdir(self.level_folder)
            except OSError:
                names = []
            for name in names:
                stem, ext = os.path.splitext(name)
                if ext.lower() == ".json" and stem.isdigit():
                    ids.append(int(stem))
        self.level_file_ids = sorted(set(ids))
        self._update_level_file_status()

    def _update_level_file_status(self):
        self.level_folder_var.set(f"Folder: {self.level_folder}")
        loaded = f"Loaded: {os.path.basename(self.current_file)}" if self.current_file else "No file loaded"
        if self.level_file_ids:
            count = len(self.level_file_ids)
            files = f"{count} numeric JSON file(s) in folder"
        else:
            files = "0 numeric JSON files in folder"
        self.level_file_status_var.set(f"{loaded}\n{files}")

    def choose_level_folder(self):
        initial_dir = self.level_folder if os.path.isdir(self.level_folder) else DEFAULT_LEVEL_SAVE_DIR
        path = filedialog.askdirectory(initialdir=initial_dir, title="Choose folder with level JSON files")
        if not path:
            return
        self.level_folder = path
        self.current_file = None
        self._refresh_level_folder_files()

    def load_selected_level(self):
        level_id = self.selected_file_level_id()
        self._load_level_by_id(level_id)

    def _load_level_by_id(self, level_id: int):
        self._refresh_level_folder_files()
        path = os.path.join(self.level_folder, f"{level_id}.json")
        if not os.path.isfile(path):
            messagebox.showerror("Load Error", f"Cannot find {level_id}.json in:\n{self.level_folder}")
            return False
        return self._load_level_file(path, level_id=level_id)

    def _neighbor_level_id(self, direction: int) -> Optional[int]:
        self._refresh_level_folder_files()
        if not self.level_file_ids:
            return None
        current = self.selected_file_level_id()
        if current in self.level_file_ids:
            next_index = self.level_file_ids.index(current) + direction
            if 0 <= next_index < len(self.level_file_ids):
                return self.level_file_ids[next_index]
            return None
        if direction < 0:
            before = [level_id for level_id in self.level_file_ids if level_id < current]
            return before[-1] if before else None
        after = [level_id for level_id in self.level_file_ids if level_id > current]
        return after[0] if after else None

    def load_previous_level(self):
        level_id = self._neighbor_level_id(-1)
        if level_id is None:
            if not self.level_file_ids:
                messagebox.showwarning("Load", "Choose a folder with numeric JSON files first.")
                return
            messagebox.showinfo("Load", "Already at the first level in this folder.")
            return
        self._load_level_by_id(level_id)

    def load_next_level(self):
        level_id = self._neighbor_level_id(1)
        if level_id is None:
            if not self.level_file_ids:
                messagebox.showwarning("Load", "Choose a folder with numeric JSON files first.")
                return
            messagebox.showinfo("Load", "Already at the last level in this folder.")
            return
        self._load_level_by_id(level_id)

    def _load_level_file(self, path: str, level_id: Optional[int] = None) -> bool:
        if not self._confirm_discard_unsaved_changes("loading another level"):
            return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                loaded_level = json.load(f)
            normalize_runtime_level(loaded_level)
            file_level_id = level_id if level_id is not None else self._level_id_from_path(path)
            if file_level_id is not None:
                loaded_level["level"] = file_level_id
            self.level = loaded_level
            self.current_file = path
            self.level_folder = os.path.dirname(path)
            self.undo_stack.clear()
            self.redo_stack.clear()
            self._refresh_all()
            self._mark_current_level_saved()
            return True
        except Exception as exc:
            messagebox.showerror("Load Error", str(exc))
            return False

    def open_json(self):
        initial_dir = self.level_folder if os.path.isdir(self.level_folder) else DEFAULT_LEVEL_SAVE_DIR
        path = filedialog.askopenfilename(
            initialdir=initial_dir,
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")]
        )
        if not path:
            return
        self._load_level_file(path)

    def save_json(self):
        self.sync_basic_fields()
        normalize_runtime_level(self.level)
        folder = self.level_folder or DEFAULT_LEVEL_SAVE_DIR
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, self.default_level_filename())
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.level, f, ensure_ascii=False, indent=2)
            self.current_file = path
            self.level_folder = folder
            self._refresh_level_folder_files()
            self._mark_current_level_saved()
            messagebox.showinfo("Save", f"Saved:\n{path}")
        except Exception as exc:
            messagebox.showerror("Save Error", str(exc))

    def default_level_filename(self) -> str:
        level_id = self.current_level_id()
        return f"{level_id}.json"

    def save_json_as(self):
        initial_dir = self.level_folder if self.level_folder else DEFAULT_LEVEL_SAVE_DIR
        if not os.path.isdir(initial_dir):
            os.makedirs(initial_dir, exist_ok=True)
        path = filedialog.asksaveasfilename(
            initialdir=initial_dir,
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")]
        )
        if not path:
            return
        file_level_id = self._level_id_from_path(path)
        if file_level_id is not None:
            self.level_var.set(str(file_level_id))
            self.file_level_var.set(str(file_level_id))
        self.sync_basic_fields()
        normalize_runtime_level(self.level)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.level, f, ensure_ascii=False, indent=2)
            self.current_file = path
            self.level_folder = os.path.dirname(path)
            self._refresh_level_folder_files()
            self._mark_current_level_saved()
            messagebox.showinfo("Save", f"Saved:\n{path}")
        except Exception as exc:
            messagebox.showerror("Save Error", str(exc))

    def record_history(self):
        self.undo_stack.append(copy.deepcopy(self.level))
        if len(self.undo_stack) > 80:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def undo(self):
        if not self.undo_stack:
            return
        self.redo_stack.append(copy.deepcopy(self.level))
        self.level = self.undo_stack.pop()
        self._refresh_all()

    def redo(self):
        if not self.redo_stack:
            return
        self.undo_stack.append(copy.deepcopy(self.level))
        self.level = self.redo_stack.pop()
        self._refresh_all()

    def copy_selected_cell(self):
        if not self.selected_cell:
            return
        entity = find_cell(self.level, *self.selected_cell).get("entity")
        self.clipboard_entity = copy.deepcopy(entity)

    def paste_selected_cell(self):
        if not self.selected_cell:
            return
        self.record_history()
        find_cell(self.level, *self.selected_cell)["entity"] = copy.deepcopy(self.clipboard_entity)
        self._update_selected_label()
        self._refresh_grid_button_states()
        self.refresh_json_preview()

    def show_info(self):
        messagebox.showinfo(
            "Level Editor Info",
            "Grid\n"
            "- Bật Paint on click để click một lần là fill ô theo config bên trái.\n"
            "- Tắt Paint on click nếu chỉ muốn click để chọn ô.\n"
            "- Right click clears xóa ô bằng chuột phải; double-click chuột phải vẫn xóa ô.\n"
            "- Double-click chuột trái luôn fill ô theo config hiện tại.\n"
            "- Kéo thả một ô shooter sang ô khác để hoán đổi vị trí.\n"
            "- Multi shooter select cho phép Ctrl/Shift-click chọn nhiều shooter rồi Paint/Clear Selected theo nhóm.\n"
            "- Copy / Paste are in Grid Tools and use the selected cell.\n\n"
            "Gate / Tray\n"
            "- Click vào bất kỳ vị trí nào trong cột gate để chọn gate; click tray để chọn tray.\n"
            "- Ctrl/Shift-click để chọn nhiều gate hoặc nhiều tray cùng lúc.\n"
            "- + Tray, + Layer, Up, Down, Delete thao tác trên selection hiện tại.\n"
            "- + Layer mặc định bị khóa; tick Enable +Layer trước khi thêm layer mới.\n"
            "- Gate Left / Gate Right đổi vị trí các gate đang chọn.\n"
            "- Kéo thả tray lên tray khác để hoán đổi, kể cả khác gate.\n"
            "- Max Visible Tray là số tray game nhìn thấy; editor vẫn scroll để thấy tray 5, 6, 7...\n\n"
            "Validate\n"
            "- Panel bên phải luôn hiển thị lỗi.\n"
            "- Color Balance hiển thị Shooter / Tray / Delta theo từng màu.\n"
            "- Auto check tự validate sau khi level đổi; tắt đi nếu muốn bấm Check Now thủ công.\n"
            "- Rule màu giống Unity: thiếu capacity là error, dư quá nhiều là warning, kèm delta và gợi ý sửa.\n\n"
            "History\n"
            "- Undo / Redo lưu các thay đổi level gần nhất.",
        )

    def sync_basic_fields(self):
        self.level["gameMode"] = self.game_mode_var.get()
        self.level["difficulty"] = self.difficulty_var.get()
        self.level["level"] = self.current_level_id()
        self.level["category"] = safe_int(str(self.category_var.get()), 0)
        self.level["time"] = safe_int(str(self.time_var.get()), 60)
        self.level["levelName"] = self.level_name_var.get().strip() or "New Level"
        self.level.setdefault("gateSystem", {})["gateCount"] = safe_int(str(self.gate_count_var.get()), 4)
        self.level.setdefault("gateSystem", {})["maxVisibleTrayPerGate"] = safe_int(str(self.max_visible_var.get()), 4)
        normalize_runtime_level(self.level)

    def resize_grid(self):
        self.record_history()
        rows = max(1, self.rows_var.get())
        cols = max(1, self.cols_var.get())
        set_grid_size(self.level, rows, cols)
        self._refresh_grid_buttons()
        self.refresh_json_preview()

    def apply_gate_system(self):
        self.record_history()
        self.sync_basic_fields()
        gate_count = self.gate_count_var.get()
        gs = self.level.setdefault("gateSystem", {})
        old_by_index = {g.get("gateIndex"): g for g in gs.get("gates", [])}
        gs["gateCount"] = gate_count
        gs["maxVisibleTrayPerGate"] = self.max_visible_var.get()
        gs["gates"] = [
            old_by_index.get(i, {"gateIndex": i, "trayQueue": []})
            for i in range(gate_count)
        ]
        self.refresh_gate_ui()
        self.refresh_gate_outputs()

    def apply_gate_text(self):
        self.record_history()
        self.sync_basic_fields()
        text = self.gate_text.get("1.0", "end")
        gate_count = self.gate_count_var.get()
        self.level.setdefault("gateSystem", {})["gates"] = parse_gate_text(text, gate_count)
        self.refresh_gate_ui()
        self.refresh_gate_outputs()

    def refresh_gate_text(self):
        gates = self.level.get("gateSystem", {}).get("gates", [])
        self.gate_text.delete("1.0", "end")
        self.gate_text.insert("1.0", gates_to_text(gates))

    def refresh_gate_outputs(self, validate_now: bool = True):
        self.refresh_gate_text()
        self.refresh_json_preview()
        if validate_now and hasattr(self, "validation_summary"):
            self.validate_level()

    def apply_gate_ui(self):
        self.normalize_gate_system()
        self.refresh_gate_ui()
        self.refresh_gate_outputs()

    def refresh_gate_ui(self):
        self.normalize_gate_system()
        self.clamp_gate_selection()
        self.refresh_gate_direct_controls()
        self.draw_gate_preview()

    def normalize_gate_system(self):
        gs = self.level.setdefault("gateSystem", {})
        gate_count = max(1, safe_int(str(self.gate_count_var.get()), gs.get("gateCount", 4)))
        max_visible = max(1, safe_int(str(self.max_visible_var.get()), gs.get("maxVisibleTrayPerGate", 4)))
        old_by_index = {g.get("gateIndex"): g for g in gs.get("gates", [])}
        gates = []
        for gate_index in range(gate_count):
            gate = old_by_index.get(gate_index, {"gateIndex": gate_index, "trayQueue": []})
            gate["gateIndex"] = gate_index
            gate.setdefault("trayQueue", [])
            gates.append(gate)
        gs["gateCount"] = gate_count
        gs["maxVisibleTrayPerGate"] = max_visible
        gs["gates"] = gates

    def clamp_gate_selection(self):
        gs = self.level.setdefault("gateSystem", {})
        gate_count = max(1, safe_int(str(gs.get("gateCount", 1)), 1))
        self.selected_gate_index = max(0, min(self.selected_gate_index, gate_count - 1))
        valid_gates = set(range(gate_count))
        if not hasattr(self, "selected_gate_indices"):
            self.selected_gate_indices = {self.selected_gate_index}
        if not hasattr(self, "selected_trays"):
            self.selected_trays = set()

        self.selected_gate_indices = {
            gate_index
            for gate_index in self.selected_gate_indices
            if gate_index in valid_gates
        }
        if not self.selected_gate_indices:
            self.selected_gate_indices = {self.selected_gate_index}

        valid_trays: Set[Tuple[int, int]] = set()
        for gate_index in valid_gates:
            gate = self._get_gate_by_index(gate_index)
            trays = gate.get("trayQueue", []) if gate else []
            valid_trays.update((gate_index, tray_index) for tray_index in range(len(trays)))

        self.selected_trays = {
            tray_ref
            for tray_ref in self.selected_trays
            if tray_ref in valid_trays
        }
        primary_tray = None
        if self.selected_tray_index is not None:
            primary_ref = (self.selected_gate_index, self.selected_tray_index)
            if primary_ref in valid_trays:
                primary_tray = primary_ref
                self.selected_trays.add(primary_ref)
            elif self.selected_trays:
                primary_tray = sorted(self.selected_trays)[0]
                self.selected_gate_index, self.selected_tray_index = primary_tray
            else:
                self.selected_tray_index = None
        elif self.selected_trays:
            primary_tray = sorted(self.selected_trays)[0]
            self.selected_gate_index, self.selected_tray_index = primary_tray

        if self.selected_tray_index is None:
            self.selected_layer_index = 0
            return

        if primary_tray is None:
            primary_tray = (self.selected_gate_index, self.selected_tray_index)
        gate = self._get_gate_by_index(self.selected_gate_index)
        trays = gate.get("trayQueue", []) if gate else []
        if primary_tray not in valid_trays or not trays:
            self.selected_tray_index = None
            self.selected_layer_index = 0
            return
        self.selected_tray_index = max(0, min(self.selected_tray_index, len(trays) - 1))
        layers = trays[self.selected_tray_index].setdefault("layers", [])
        if not layers:
            layers.append(self._default_tray_layer())
        self.selected_layer_index = max(0, min(self.selected_layer_index, len(layers) - 1))
        self.selected_gate_indices = {gate_index for gate_index, _ in self.selected_trays} or {self.selected_gate_index}

    def refresh_gate_direct_controls(self):
        if not hasattr(self, "gate_selection_label"):
            return
        gate = self._get_gate_by_index(self.selected_gate_index)
        trays = gate.get("trayQueue", []) if gate else []
        if self.selected_tray_index is None or not trays:
            self.gate_selection_label.configure(text=self._selection_summary())
            self.selected_tray_id_var.set("")
            self.selected_layer_var.set(0)
            self.selected_layer_color_var.set("Blue")
            self.selected_layer_count_var.set(3)
            self.selected_layer_spin.configure(to=0)
            return

        tray = trays[self.selected_tray_index]
        layers = tray.setdefault("layers", [])
        if not layers:
            layers.append(self._default_tray_layer())
        layer = layers[self.selected_layer_index]
        self.gate_selection_label.configure(
            text=f"{self._selection_summary()} / Layer {self.selected_layer_index}"
        )
        self.selected_tray_id_var.set(tray.get("trayId", ""))
        self.selected_layer_spin.configure(to=max(0, len(layers) - 1))
        self.selected_layer_var.set(self.selected_layer_index)
        self.selected_layer_color_var.set(layer.get("colorId", "Blue"))
        self.selected_layer_count_var.set(max(1, safe_int(str(layer.get("requiredCount", 3)), 3)))

    def _default_tray_layer(self) -> Dict[str, Any]:
        return {"colorId": "Blue", "requiredCount": 3}

    def _format_index_list(self, values: List[int]) -> str:
        if len(values) <= 4:
            return ", ".join(str(value) for value in values)
        head = ", ".join(str(value) for value in values[:4])
        return f"{head}, +{len(values) - 4}"

    def _selection_summary(self) -> str:
        tray_targets = self._selected_tray_targets()
        if tray_targets:
            if len(tray_targets) == 1:
                gate_index, tray_index = tray_targets[0]
                return f"Selected: Gate {gate_index} / Tray {tray_index}"
            gate_indices = sorted({gate_index for gate_index, _ in tray_targets})
            return (
                f"Selected: {len(tray_targets)} trays "
                f"(gates {self._format_index_list(gate_indices)}); "
                f"editing Gate {self.selected_gate_index} / Tray {self.selected_tray_index}"
            )

        gate_targets = self._selected_gate_targets()
        if len(gate_targets) == 1:
            return f"Selected: Gate {gate_targets[0]}"
        return f"Selected: {len(gate_targets)} gates ({self._format_index_list(gate_targets)})"

    def _selected_gate_targets(self) -> List[int]:
        gs = self.level.setdefault("gateSystem", {})
        gate_count = max(1, safe_int(str(gs.get("gateCount", 1)), 1))
        selected = set(getattr(self, "selected_gate_indices", {self.selected_gate_index}))
        if getattr(self, "selected_trays", set()):
            selected.update(gate_index for gate_index, _ in self.selected_trays)
        selected.add(self.selected_gate_index)
        return sorted(gate_index for gate_index in selected if 0 <= gate_index < gate_count)

    def _selected_tray_targets(self) -> List[Tuple[int, int]]:
        selected = set(getattr(self, "selected_trays", set()))
        if self.selected_tray_index is not None:
            selected.add((self.selected_gate_index, self.selected_tray_index))
        return sorted(tray_ref for tray_ref in selected if self._get_tray_by_ref(tray_ref) is not None)

    def _get_tray_by_ref(self, tray_ref: Tuple[int, int]) -> Optional[Dict[str, Any]]:
        gate_index, tray_index = tray_ref
        gate = self._get_gate_by_index(gate_index)
        trays = gate.get("trayQueue", []) if gate else []
        if 0 <= tray_index < len(trays):
            return trays[tray_index]
        return None

    def draw_gate_preview(self):
        if not hasattr(self, "gate_preview_canvas"):
            return

        canvas = self.gate_preview_canvas
        canvas.delete("all")
        self.gate_hit_areas.clear()

        gs = self.level.setdefault("gateSystem", {})
        gates = gs.get("gates", [])
        gate_count = max(1, safe_int(str(self.gate_count_var.get()), gs.get("gateCount", 4)))
        max_visible = max(1, safe_int(str(self.max_visible_var.get()), gs.get("maxVisibleTrayPerGate", 4)))
        width = max(canvas.winfo_width(), 1)
        height = max(canvas.winfo_height(), 1)

        gate_width = 64
        gap = 6
        base_height = 34
        tray_height = 24
        tray_gap = 3
        max_rows = max(
            max_visible,
            max((len(g.get("trayQueue", [])) for g in gates), default=0),
        )
        content_height = max(height, max_rows * (tray_height + tray_gap) + base_height + 80)
        total_width = gate_count * gate_width + max(0, gate_count - 1) * gap
        start_x = max(14, (width - total_width) // 2)
        base_y = content_height - 48
        max_stack_height = max_rows * tray_height + max(0, max_rows - 1) * tray_gap
        top_y = max(12, base_y - max_stack_height - 6)
        canvas.configure(scrollregion=(0, 0, max(width, total_width + 28), content_height))

        self._draw_gate_backplate(canvas, start_x - 8, top_y - 8, total_width + 16, base_y - top_y + base_height + 16)

        gate_by_index = {g.get("gateIndex"): g for g in gates}
        for gate_index in range(gate_count):
            gate = gate_by_index.get(gate_index, {"gateIndex": gate_index, "trayQueue": []})
            x = start_x + gate_index * (gate_width + gap)
            self._draw_gate_column(canvas, x, top_y, gate_width, base_y, base_height, tray_height, tray_gap, gate, max_visible)

    def _draw_gate_backplate(self, canvas: tk.Canvas, x: int, y: int, width: int, height: int):
        self._create_round_rect(canvas, x + 2, y + 4, x + width + 2, y + height + 4, 10, fill="#171C31", outline="")
        self._create_round_rect(canvas, x, y, x + width, y + height, 10, fill="#303757", outline="#67708F", width=2)

    def _draw_gate_column(
        self,
        canvas: tk.Canvas,
        x: int,
        top_y: int,
        width: int,
        base_y: int,
        base_height: int,
        tray_height: int,
        tray_gap: int,
        gate: Dict[str, Any],
        max_visible: int,
    ):
        trays = gate.get("trayQueue", [])
        visible_rows = max(max_visible, len(trays))
        gate_index = gate.get("gateIndex", 0)
        is_gate_selected = gate_index in getattr(self, "selected_gate_indices", {self.selected_gate_index})
        self.gate_hit_areas.append({
            "kind": "gate",
            "gateIndex": gate_index,
            "trayIndex": None,
            "bounds": (x - 2, top_y - 4, x + width + 2, base_y + base_height + 4),
        })
        if is_gate_selected:
            canvas.create_rectangle(
                x - 4,
                top_y - 5,
                x + width + 4,
                base_y + base_height + 5,
                outline="#FFD54A",
                width=2,
                dash=(4, 3),
            )

        for row in range(visible_rows):
            tray_y = base_y - (visible_rows - row) * (tray_height + tray_gap) + tray_gap
            tray = trays[row] if row < len(trays) else None
            self._draw_tray_block(canvas, x, tray_y, width, tray_height, tray, gate_index, row if tray else None)

        if len(trays) > max_visible:
            line_y = base_y - max_visible * (tray_height + tray_gap) - 2
            canvas.create_line(x, line_y, x + width, line_y, fill="#E8EEFB", dash=(3, 3))
            canvas.create_text(x + width // 2, line_y - 8, text=f"+{len(trays) - max_visible}", fill="#E8EEFB", font=("Arial", 8, "bold"))

        self._create_round_rect(
            canvas,
            x - 1,
            base_y - 2,
            x + width + 1,
            base_y + base_height + 2,
            8,
            fill="#515D78",
            outline="#FFD54A" if is_gate_selected else "#8F9BB8",
            width=3 if is_gate_selected else 2,
        )
        self._create_round_rect(canvas, x + 3, base_y + 2, x + width - 3, base_y + base_height - 5, 6, fill="#A9B6D0", outline="")
        self._create_round_rect(canvas, x + 5, base_y + 4, x + width - 5, base_y + 15, 5, fill="#CFD8EA", outline="")
        self._draw_gate_arrow(canvas, x + width // 2, base_y + 17)

    def _draw_tray_block(
        self,
        canvas: tk.Canvas,
        x: int,
        y: int,
        width: int,
        height: int,
        tray: Optional[Dict[str, Any]],
        gate_index: int,
        tray_index: Optional[int],
    ):
        color = self._tray_preview_color(tray)
        border = self._shade_hex(color, -0.35)
        highlight = self._shade_hex(color, 0.32)
        is_selected = (
            tray_index is not None
            and (
                (gate_index, tray_index) in getattr(self, "selected_trays", set())
                or (self.selected_gate_index == gate_index and self.selected_tray_index == tray_index)
            )
        )

        self._create_round_rect(canvas, x + 1, y + 2, x + width + 1, y + height + 2, 5, fill="#151A2E", outline="")
        self._create_round_rect(canvas, x, y, x + width, y + height, 5, fill=color, outline="#FFFFFF" if is_selected else border, width=3 if is_selected else 2)
        self._create_round_rect(canvas, x + 3, y + 3, x + width - 3, y + 8, 4, fill=highlight, outline="")
        if tray_index is not None:
            self.gate_hit_areas.append({
                "kind": "tray",
                "gateIndex": gate_index,
                "trayIndex": tray_index,
                "bounds": (x, y, x + width, y + height),
            })

        first_layer = (tray or {}).get("layers", [{}])[0] if (tray or {}).get("layers") else {}
        count = max(0, safe_int(str(first_layer.get("requiredCount", 0)), 0))
        if count > 1:
            dot_count = min(count, 4)
            for i in range(dot_count):
                dot_x = x + 11 + i * 15
                canvas.create_oval(dot_x - 4, y + 4, dot_x + 4, y + 12, fill=self._shade_hex(color, -0.12), outline=self._shade_hex(color, -0.4))

    def _is_multi_select_event(self, event) -> bool:
        state = getattr(event, "state", 0)
        return bool(state & 0x0001 or state & 0x0004)

    def _select_gate_area(self, gate_index: int, additive: bool):
        if additive:
            if gate_index in self.selected_gate_indices and len(self.selected_gate_indices) > 1:
                self.selected_gate_indices.remove(gate_index)
                self.selected_gate_index = sorted(self.selected_gate_indices)[0]
            else:
                self.selected_gate_indices.add(gate_index)
                self.selected_gate_index = gate_index
        else:
            self.selected_gate_indices = {gate_index}
            self.selected_gate_index = gate_index
        self.selected_trays.clear()
        self.selected_tray_index = None
        self.selected_layer_index = 0
        self.gate_drag_source = None

    def _select_tray_area(self, gate_index: int, tray_index: int, additive: bool):
        tray_ref = (gate_index, tray_index)
        if additive:
            if tray_ref in self.selected_trays and len(self.selected_trays) > 1:
                self.selected_trays.remove(tray_ref)
            else:
                self.selected_trays.add(tray_ref)
        else:
            self.selected_trays = {tray_ref}

        if tray_ref in self.selected_trays:
            self.selected_gate_index, self.selected_tray_index = tray_ref
        elif self.selected_trays:
            self.selected_gate_index, self.selected_tray_index = sorted(self.selected_trays)[0]
        else:
            self.selected_gate_index = gate_index
            self.selected_tray_index = None

        self.selected_gate_indices = {selected_gate for selected_gate, _ in self.selected_trays} or {self.selected_gate_index}
        self.selected_layer_index = 0
        self.gate_drag_source = tray_ref if tray_ref in self.selected_trays else None

    def on_gate_preview_click(self, event):
        y = self.gate_preview_canvas.canvasy(event.y)
        for area in reversed(self.gate_hit_areas):
            x1, y1, x2, y2 = area["bounds"]
            if x1 <= event.x <= x2 and y1 <= y <= y2:
                if area["kind"] == "tray":
                    self._select_tray_area(area["gateIndex"], area["trayIndex"], self._is_multi_select_event(event))
                else:
                    self._select_gate_area(area["gateIndex"], self._is_multi_select_event(event))
                self.clamp_gate_selection()
                self.refresh_gate_direct_controls()
                self.draw_gate_preview()
                return
        self.gate_drag_source = None

    def on_gate_preview_release(self, event):
        if self.gate_drag_source is None:
            return
        y = self.gate_preview_canvas.canvasy(event.y)
        target = None
        for area in reversed(self.gate_hit_areas):
            x1, y1, x2, y2 = area["bounds"]
            if area["kind"] == "tray" and x1 <= event.x <= x2 and y1 <= y <= y2:
                target = (area["gateIndex"], area["trayIndex"])
                break
        source = self.gate_drag_source
        self.gate_drag_source = None
        if target is None or source == target:
            return
        self.swap_trays(source, target)

    def select_layer_from_control(self):
        self.selected_layer_index = max(0, safe_int(str(self.selected_layer_var.get()), 0))
        self.clamp_gate_selection()
        self.refresh_gate_direct_controls()
        self.draw_gate_preview()

    def apply_selected_tray_fields(self):
        gate = self._get_gate_by_index(self.selected_gate_index)
        trays = gate.get("trayQueue", []) if gate else []
        if self.selected_tray_index is None or not (0 <= self.selected_tray_index < len(trays)):
            return
        old_id = trays[self.selected_tray_index].get("trayId", "")
        new_id = self.selected_tray_id_var.get().strip() or short_id("t")
        if old_id == new_id:
            return
        self.record_history()
        trays[self.selected_tray_index]["trayId"] = new_id
        self.refresh_gate_outputs()

    def apply_selected_layer_fields(self):
        targets = self._selected_tray_targets()
        if not targets:
            return
        color = self.selected_layer_color_var.get()
        if color not in BALL_COLORS or color == "None":
            color = "Blue"
        new_count = max(1, safe_int(str(self.selected_layer_count_var.get()), 3))

        pending: List[Tuple[Tuple[int, int], int]] = []
        for tray_ref in targets:
            tray = self._get_tray_by_ref(tray_ref)
            if tray is None:
                continue
            layers = tray.get("layers", [])
            if not layers:
                if self.selected_layer_index == 0:
                    pending.append((tray_ref, 0))
                continue
            if not 0 <= self.selected_layer_index < len(layers):
                continue
            layer = layers[self.selected_layer_index]
            if layer.get("colorId") != color or layer.get("requiredCount") != new_count:
                pending.append((tray_ref, self.selected_layer_index))

        if not pending:
            return
        self.record_history()
        for tray_ref, layer_index in pending:
            tray = self._get_tray_by_ref(tray_ref)
            if tray is None:
                continue
            layers = tray.setdefault("layers", [])
            while len(layers) <= layer_index:
                layers.append(self._default_tray_layer())
            layers[layer_index]["colorId"] = color
            layers[layer_index]["requiredCount"] = new_count
        self.draw_gate_preview()
        self.refresh_gate_outputs()

    def add_tray_to_selected_gate(self):
        targets = self._selected_gate_targets()
        if not targets:
            return
        self.record_history()
        gates = self.level.setdefault("gateSystem", {}).setdefault("gates", [])
        new_selection: Set[Tuple[int, int]] = set()
        primary_ref: Optional[Tuple[int, int]] = None
        for gate_index in targets:
            gate = self._get_gate_by_index(gate_index)
            if gate is None:
                gate = {"gateIndex": gate_index, "trayQueue": []}
                gates.append(gate)
            trays = gate.setdefault("trayQueue", [])
            new_index = len(trays)
            trays.append({
                "trayId": short_id("t"),
                "layers": [self._default_tray_layer()]
            })
            tray_ref = (gate_index, new_index)
            new_selection.add(tray_ref)
            if gate_index == self.selected_gate_index:
                primary_ref = tray_ref
        if not new_selection:
            return
        primary_ref = primary_ref or sorted(new_selection)[0]
        self.selected_gate_index, self.selected_tray_index = primary_ref
        self.selected_trays = new_selection
        self.selected_gate_indices = {gate_index for gate_index, _ in new_selection}
        self.selected_layer_index = 0
        self.clamp_gate_selection()
        self.refresh_gate_direct_controls()
        self.draw_gate_preview()
        self.refresh_gate_outputs()

    def add_layer_to_selected_tray(self):
        add_layer_enabled = getattr(self, "add_layer_enabled_var", None)
        if add_layer_enabled is None or not add_layer_enabled.get():
            return
        targets = self._selected_tray_targets()
        if not targets:
            return
        self.record_history()
        primary_ref = (self.selected_gate_index, self.selected_tray_index)
        next_index = 0
        for tray_ref in targets:
            tray = self._get_tray_by_ref(tray_ref)
            if tray is None:
                continue
            layers = tray.setdefault("layers", [])
            if tray_ref == primary_ref:
                next_index = len(layers)
            layers.append(self._default_tray_layer())
        self.selected_layer_index = next_index
        self.clamp_gate_selection()
        self.refresh_gate_direct_controls()
        self.draw_gate_preview()
        self.refresh_gate_outputs()

    def move_selected_tray(self, direction: int):
        if direction == 0:
            return
        targets = self._selected_tray_targets()
        if not targets:
            return
        selected_by_gate: Dict[int, Set[int]] = {}
        for gate_index, tray_index in targets:
            selected_by_gate.setdefault(gate_index, set()).add(tray_index)

        history_recorded = False
        moved_refs: Dict[Tuple[int, int], Tuple[int, int]] = {}
        for gate_index in sorted(selected_by_gate):
            gate = self._get_gate_by_index(gate_index)
            trays = gate.get("trayQueue", []) if gate else []
            order = sorted(selected_by_gate[gate_index], reverse=direction > 0)
            for tray_index in order:
                if tray_index not in selected_by_gate[gate_index]:
                    continue
                new_index = tray_index + direction
                if not (0 <= tray_index < len(trays) and 0 <= new_index < len(trays)):
                    continue
                if new_index in selected_by_gate[gate_index]:
                    continue
                if not history_recorded:
                    self.record_history()
                    history_recorded = True
                trays[tray_index], trays[new_index] = trays[new_index], trays[tray_index]
                selected_by_gate[gate_index].remove(tray_index)
                selected_by_gate[gate_index].add(new_index)
                moved_refs[(gate_index, tray_index)] = (gate_index, new_index)

        if not history_recorded:
            return
        self.selected_trays = {
            (gate_index, tray_index)
            for gate_index, tray_indices in selected_by_gate.items()
            for tray_index in tray_indices
        }
        primary_ref = moved_refs.get((self.selected_gate_index, self.selected_tray_index), (self.selected_gate_index, self.selected_tray_index))
        if primary_ref not in self.selected_trays:
            primary_ref = sorted(self.selected_trays)[0]
        self.selected_gate_index, self.selected_tray_index = primary_ref
        self.selected_gate_indices = {gate_index for gate_index, _ in self.selected_trays}
        self.clamp_gate_selection()
        self.refresh_gate_direct_controls()
        self.draw_gate_preview()
        self.refresh_gate_outputs()

    def remove_selected_tray(self):
        targets = self._selected_tray_targets()
        if not targets:
            return
        self.record_history()
        primary_gate_index = self.selected_gate_index
        remove_index_by_gate: Dict[int, int] = {}
        selected_gates = sorted({gate_index for gate_index, _ in targets})
        for gate_index, tray_index in targets:
            remove_index_by_gate[gate_index] = min(tray_index, remove_index_by_gate.get(gate_index, tray_index))

        for gate_index in selected_gates:
            gate = self._get_gate_by_index(gate_index)
            trays = gate.get("trayQueue", []) if gate else []
            remove_indices = sorted((tray_index for gi, tray_index in targets if gi == gate_index), reverse=True)
            for tray_index in remove_indices:
                if 0 <= tray_index < len(trays):
                    del trays[tray_index]

        next_ref: Optional[Tuple[int, int]] = None
        for gate_index in [primary_gate_index] + [gi for gi in selected_gates if gi != primary_gate_index]:
            gate = self._get_gate_by_index(gate_index)
            trays = gate.get("trayQueue", []) if gate else []
            if not trays:
                continue
            next_index = min(remove_index_by_gate.get(gate_index, 0), len(trays) - 1)
            next_ref = (gate_index, next_index)
            break

        self.selected_gate_indices = set(selected_gates) or {primary_gate_index}
        self.selected_trays.clear()
        if next_ref is None:
            self.selected_gate_index = primary_gate_index
            self.selected_tray_index = None
            self.selected_layer_index = 0
        else:
            self.selected_gate_index, self.selected_tray_index = next_ref
            self.selected_trays = {next_ref}
            self.selected_gate_indices = {next_ref[0]}
        self.clamp_gate_selection()
        self.refresh_gate_direct_controls()
        self.draw_gate_preview()
        self.refresh_gate_outputs()

    def remove_selected_layer(self):
        targets = self._selected_tray_targets()
        if not targets:
            return
        pending = []
        for tray_ref in targets:
            tray = self._get_tray_by_ref(tray_ref)
            layers = tray.get("layers", []) if tray else []
            if 0 <= self.selected_layer_index < len(layers):
                pending.append(tray_ref)
        if not pending:
            return
        self.record_history()
        for tray_ref in pending:
            tray = self._get_tray_by_ref(tray_ref)
            if tray is None:
                continue
            layers = tray.setdefault("layers", [])
            if 0 <= self.selected_layer_index < len(layers):
                del layers[self.selected_layer_index]
            if not layers:
                layers.append(self._default_tray_layer())
        self.clamp_gate_selection()
        self.refresh_gate_direct_controls()
        self.draw_gate_preview()
        self.refresh_gate_outputs()

    def move_selected_gate(self, direction: int):
        if direction == 0:
            return
        targets = set(self._selected_gate_targets())
        if not targets:
            return

        gs = self.level.setdefault("gateSystem", {})
        gates = gs.setdefault("gates", [])
        gates.sort(key=lambda gate: safe_int(str(gate.get("gateIndex", 0)), 0))
        gate_count = len(gates)
        if gate_count <= 1:
            return

        selected = {gate_index for gate_index in targets if 0 <= gate_index < gate_count}
        if not selected:
            return

        old_position_by_gate = {id(gate): gate_index for gate_index, gate in enumerate(gates)}
        old_primary_gate = self.selected_gate_index
        old_selected_trays = set(self.selected_trays)
        order = sorted(selected, reverse=direction > 0)
        history_recorded = False

        for gate_index in order:
            if gate_index not in selected:
                continue
            new_index = gate_index + direction
            if not (0 <= new_index < gate_count):
                continue
            if new_index in selected:
                continue
            if not history_recorded:
                self.record_history()
                history_recorded = True
            gates[gate_index], gates[new_index] = gates[new_index], gates[gate_index]
            selected.remove(gate_index)
            selected.add(new_index)

        if not history_recorded:
            return

        old_to_new_gate = {
            old_position_by_gate[id(gate)]: gate_index
            for gate_index, gate in enumerate(gates)
        }
        for gate_index, gate in enumerate(gates):
            gate["gateIndex"] = gate_index

        def remap_gate(gate_index: int) -> int:
            return old_to_new_gate.get(gate_index, gate_index)

        self.selected_gate_index = remap_gate(old_primary_gate)
        self.selected_gate_indices = selected
        self.selected_trays = {
            (remap_gate(gate_index), tray_index)
            for gate_index, tray_index in old_selected_trays
        }
        if self.selected_tray_index is not None:
            self.selected_tray_index = self.selected_tray_index
        self.clamp_gate_selection()
        self.refresh_gate_direct_controls()
        self.draw_gate_preview()
        self.refresh_gate_outputs()

    def _draw_gate_arrow(self, canvas: tk.Canvas, center_x: int, y: int):
        canvas.create_polygon(
            center_x,
            y,
            center_x - 10,
            y + 9,
            center_x - 4,
            y + 9,
            center_x - 4,
            y + 13,
            center_x + 4,
            y + 13,
            center_x + 4,
            y + 9,
            center_x + 10,
            y + 9,
            fill="#E8EEFB",
            outline="#CAD3E6",
        )

    def _tray_preview_color(self, tray: Optional[Dict[str, Any]]) -> str:
        if not tray:
            return "#3B4565"
        layers = tray.get("layers", [])
        if not layers:
            return "#3B4565"
        color_id = layers[0].get("colorId", "None")
        return COLOR_HEX.get(color_id, "#8A93AA")

    def _create_round_rect(self, canvas: tk.Canvas, x1: int, y1: int, x2: int, y2: int, radius: int, **kwargs):
        radius = max(1, min(radius, (x2 - x1) // 2, (y2 - y1) // 2))
        points = [
            x1 + radius, y1,
            x2 - radius, y1,
            x2, y1,
            x2, y1 + radius,
            x2, y2 - radius,
            x2, y2,
            x2 - radius, y2,
            x1 + radius, y2,
            x1, y2,
            x1, y2 - radius,
            x1, y1 + radius,
            x1, y1,
        ]
        return canvas.create_polygon(points, smooth=True, **kwargs)

    def _shade_hex(self, color: str, amount: float) -> str:
        color = color.lstrip("#")
        if len(color) != 6:
            return "#FFFFFF"
        channels = [int(color[i:i + 2], 16) for i in (0, 2, 4)]
        if amount >= 0:
            shaded = [round(c + (255 - c) * amount) for c in channels]
        else:
            shaded = [round(c * (1 + amount)) for c in channels]
        return "#" + "".join(f"{max(0, min(255, c)):02X}" for c in shaded)

    def add_tray_to_gate(self, gate_index: int):
        self.record_history()
        gates = self.level.setdefault("gateSystem", {}).setdefault("gates", [])
        gate = next((g for g in gates if g.get("gateIndex") == gate_index), None)
        if gate is None:
            gate = {"gateIndex": gate_index, "trayQueue": []}
            gates.append(gate)
        gate.setdefault("trayQueue", []).append({
            "trayId": short_id("t"),
            "layers": [{"colorId": "Blue", "requiredCount": 3}]
        })
        self.refresh_gate_ui()
        self.refresh_gate_outputs()

    def remove_tray(self, gate_index: int, tray_index: int):
        self.record_history()
        gate = self._get_gate_by_index(gate_index)
        if gate and 0 <= tray_index < len(gate.get("trayQueue", [])):
            del gate["trayQueue"][tray_index]
        self.refresh_gate_ui()
        self.refresh_gate_outputs()

    def move_tray(self, gate_index: int, tray_index: int, direction: int):
        self.record_history()
        gate = self._get_gate_by_index(gate_index)
        if not gate:
            return
        trays = gate.get("trayQueue", [])
        new_index = tray_index + direction
        if 0 <= tray_index < len(trays) and 0 <= new_index < len(trays):
            trays[tray_index], trays[new_index] = trays[new_index], trays[tray_index]
        self.refresh_gate_ui()
        self.refresh_gate_outputs()

    def add_layer_to_tray(self, gate_index: int, tray_index: int):
        self.record_history()
        gate = self._get_gate_by_index(gate_index)
        trays = gate.get("trayQueue", []) if gate else []
        if 0 <= tray_index < len(trays):
            trays[tray_index].setdefault("layers", []).append({"colorId": "Blue", "requiredCount": 3})
        self.refresh_gate_ui()
        self.refresh_gate_outputs()

    def remove_layer(self, gate_index: int, tray_index: int, layer_index: int):
        self.record_history()
        gate = self._get_gate_by_index(gate_index)
        trays = gate.get("trayQueue", []) if gate else []
        if 0 <= tray_index < len(trays):
            layers = trays[tray_index].setdefault("layers", [])
            if 0 <= layer_index < len(layers):
                del layers[layer_index]
        self.refresh_gate_ui()
        self.refresh_gate_outputs()

    def swap_trays(self, source: Tuple[int, int], target: Tuple[int, int]):
        source_gate = self._get_gate_by_index(source[0])
        target_gate = self._get_gate_by_index(target[0])
        if not source_gate or not target_gate:
            return
        source_trays = source_gate.get("trayQueue", [])
        target_trays = target_gate.get("trayQueue", [])
        if not (0 <= source[1] < len(source_trays) and 0 <= target[1] < len(target_trays)):
            return
        self.record_history()
        source_trays[source[1]], target_trays[target[1]] = target_trays[target[1]], source_trays[source[1]]
        self.selected_gate_index, self.selected_tray_index = target
        self.selected_gate_indices = {target[0]}
        self.selected_trays = {target}
        self.selected_layer_index = 0
        self.refresh_gate_ui()
        self.refresh_gate_outputs()

    def _get_gate_by_index(self, gate_index: int) -> Optional[Dict[str, Any]]:
        for gate in self.level.setdefault("gateSystem", {}).setdefault("gates", []):
            if gate.get("gateIndex") == gate_index:
                return gate
        return None

    def _grid_multi_shooter_select_enabled(self) -> bool:
        option = getattr(self, "grid_multi_shooter_select_var", None)
        return bool(option and option.get())

    def _selected_grid_targets(self) -> List[Tuple[int, int]]:
        selected_grid_cells = getattr(self, "selected_grid_cells", set())
        if self._grid_multi_shooter_select_enabled() and selected_grid_cells:
            return sorted(selected_grid_cells)
        return [self.selected_cell] if self.selected_cell else []

    def _is_shooter_cell(self, row: int, col: int) -> bool:
        return self._is_shooter_entity(find_cell(self.level, row, col).get("entity"))

    def _brush_modifiers(self) -> List[Dict[str, Any]]:
        return make_shooter_modifiers(
            hidden=self.brush_hidden_modifier.get(),
            ice=self.brush_ice_modifier.get(),
            ice_hp=max(1, safe_int(str(self.brush_ice_hp.get()), 1)),
            can_click_while_frozen=self.brush_ice_can_click.get(),
            blocks_activation=self.brush_ice_blocks_activation.get(),
        )

    def _selected_shooter_data(self) -> List[Dict[str, Any]]:
        shooters = []
        for row, col in self._selected_grid_targets():
            entity = find_cell(self.level, row, col).get("entity")
            if self._is_shooter_entity(entity):
                shooters.append(entity["shooter"])
            elif entity and entity.get("type") == "Tunnel":
                shooters.extend(entity.get("shooterQueue", []))
        return shooters

    def apply_modifiers_to_selected_shooters(self):
        shooters = self._selected_shooter_data()
        if not shooters:
            messagebox.showwarning("No Shooter", "Select a shooter cell or a tunnel with queued shooters first.")
            return
        self.record_history()
        modifiers = self._brush_modifiers()
        for shooter in shooters:
            shooter["modifiers"] = copy.deepcopy(modifiers)
        self._refresh_grid_button_states()
        self.refresh_json_preview()

    def remove_modifiers_from_selected_shooters(self):
        shooters = self._selected_shooter_data()
        if not shooters:
            messagebox.showwarning("No Shooter", "Select a shooter cell or a tunnel with queued shooters first.")
            return
        self.record_history()
        for shooter in shooters:
            shooter["modifiers"] = []
        self._refresh_grid_button_states()
        self.refresh_json_preview()

    def load_selected_shooter_modifiers(self):
        shooters = self._selected_shooter_data()
        if not shooters:
            messagebox.showwarning("No Shooter", "Select a shooter cell or a tunnel with queued shooters first.")
            return
        modifiers = shooters[0].get("modifiers", [])
        hidden = next((modifier for modifier in modifiers if modifier.get("type") == "Hidden"), None)
        ice = next((modifier for modifier in modifiers if modifier.get("type") == "Ice"), None)
        self.brush_hidden_modifier.set(hidden is not None)
        self.brush_ice_modifier.set(ice is not None)
        if ice is not None:
            self.brush_ice_hp.set(max(1, safe_int(str(ice.get("hp", 1)), 1)))
            self.brush_ice_can_click.set(bool(ice.get("canClickWhileFrozen", False)))
            self.brush_ice_blocks_activation.set(bool(ice.get("blocksActivation", True)))
        self.update_brush_modifier_state()

    def _grid_entity_fg(self, entity: Optional[Dict[str, Any]]) -> str:
        if entity and entity.get("type") == "Shooter" and entity.get("shooter", {}).get("colorId") in ["Yellow", "Wild", "Cyan", "Pink"]:
            return "#000000"
        return "#FFFFFF"

    def _grid_selection_frame_style(self, is_selected: bool, entity: Optional[Dict[str, Any]]) -> Tuple[str, int, int]:
        if not is_selected:
            return "#3A3A3A", 1, 1
        if self._is_shooter_entity(entity):
            return "#00E5FF", 5, 5
        return "#FFD54A", 4, 4

    def _update_selected_label(self):
        if not hasattr(self, "selected_label"):
            return
        if not self.selected_cell:
            self.selected_label.configure(text="Selected: none")
            return
        row, col = self.selected_cell
        ent = find_cell(self.level, row, col).get("entity")
        selected_count = len(self.selected_grid_cells) if self._grid_multi_shooter_select_enabled() else 0
        if selected_count > 1:
            self.selected_label.configure(text=f"Selected: {selected_count} shooters; active row={row}, column={col}")
        else:
            self.selected_label.configure(text=f"Selected: row={row}, column={col}, entity={ent.get('type') if ent else 'Empty'}")

    def apply_brush_to_selected(self):
        targets = self._selected_grid_targets()
        if not targets:
            messagebox.showwarning("No Cell", "Select a grid cell first.")
            return
        if len(targets) == 1:
            self.paint_cell(*targets[0])
            return
        self.record_history()
        for row, col in targets:
            self._apply_brush_to_cell(row, col)
        if self._grid_multi_shooter_select_enabled():
            self.selected_grid_cells = {
                (row, col)
                for row, col in targets
                if self._is_shooter_cell(row, col)
            }
        self._update_selected_label()
        self._refresh_grid_button_states()
        self.refresh_json_preview()

    def clear_selected_cell(self):
        targets = self._selected_grid_targets()
        if not targets:
            return
        self.record_history()
        for row, col in targets:
            find_cell(self.level, row, col)["entity"] = None
        if self._grid_multi_shooter_select_enabled():
            self.selected_grid_cells.clear()
        self._update_selected_label()
        self._refresh_grid_button_states()
        self.refresh_json_preview()

    def select_cell(self, row: int, col: int, paint: bool = False, additive: bool = False):
        self.selected_cell = (row, col)
        cell = find_cell(self.level, row, col)
        ent = cell.get("entity")
        if self._grid_multi_shooter_select_enabled() and self._is_shooter_entity(ent):
            cell_ref = (row, col)
            if additive:
                if cell_ref in self.selected_grid_cells and len(self.selected_grid_cells) > 1:
                    self.selected_grid_cells.remove(cell_ref)
                    self.selected_cell = sorted(self.selected_grid_cells)[0]
                else:
                    self.selected_grid_cells.add(cell_ref)
            else:
                self.selected_grid_cells = {cell_ref}
        else:
            self.selected_grid_cells.clear()

        self._update_selected_label()
        if paint:
            self.paint_cell(row, col)
        else:
            self._refresh_grid_button_states()

    def on_grid_cell_click(self, row: int, col: int, event=None):
        multi_shooter = self._grid_multi_shooter_select_enabled()
        additive = multi_shooter and event is not None and self._is_multi_select_event(event)
        paint_option = getattr(self, "grid_paint_on_click_var", None)
        paint_on_click = bool(paint_option and paint_option.get()) and not additive
        self.select_cell(row, col, paint=paint_on_click, additive=additive)

    def _apply_brush_to_cell(self, row: int, col: int):
        btype = self.brush_type.get()
        cell = find_cell(self.level, row, col)
        if btype == "Empty":
            cell["entity"] = None
        elif btype == "Shooter":
            cell["entity"] = make_shooter_entity(
                row,
                col,
                self.brush_color.get(),
                max(1, self.brush_capacity.get()),
                self._brush_modifiers(),
            )
        elif btype == "Wall":
            cell["entity"] = make_wall_entity(row, col)
        elif btype == "Tunnel":
            cell["entity"] = make_tunnel_entity(
                row,
                col,
                self.tunnel_direction.get(),
                self.tunnel_queue.get(),
                self._brush_modifiers(),
            )

    def paint_cell(self, row: int, col: int):
        self.record_history()
        self._apply_brush_to_cell(row, col)
        if self._grid_multi_shooter_select_enabled():
            self.selected_grid_cells = {
                (selected_row, selected_col)
                for selected_row, selected_col in self.selected_grid_cells
                if self._is_shooter_cell(selected_row, selected_col)
            }
            if self._is_shooter_cell(row, col):
                self.selected_grid_cells.add((row, col))
        self._update_selected_label()
        self._refresh_grid_button_states()
        self.refresh_json_preview()

    def validate_level(self):
        if self._validation_after_id is not None:
            self.after_cancel(self._validation_after_id)
            self._validation_after_id = None
        self.sync_basic_fields()
        errors, warnings = LevelValidator().validate(self.level)
        self.render_validation_results(errors, warnings)

    def render_validation_results(self, errors: List[str], warnings: List[str]):
        self.render_color_balance()
        self.validation_text.configure(state="normal")
        self.validation_text.delete("1.0", "end")
        if errors:
            self.validation_summary.configure(
                text=f"{len(errors)} error(s), {len(warnings)} warning/info",
                bg="#B91C1C",
                fg="#FFFFFF",
            )
            self.validation_text.insert("end", "ERRORS\n", "error_header")
            for e in errors:
                self.validation_text.insert("end", f"- {e}\n", "error_item")
        else:
            self.validation_summary.configure(
                text=f"OK, {len(warnings)} warning/info",
                bg="#047857",
                fg="#FFFFFF",
            )
            self.validation_text.insert("end", "ERRORS\n", "ok_header")
            self.validation_text.insert("end", "- Không có error.\n", "info_item")

        if warnings:
            self.validation_text.insert("end", "\nWARNINGS / INFO\n", "warning_header")
            item_tag = "warning_item" if errors else "info_item"
            for w in warnings:
                self.validation_text.insert("end", f"- {w}\n", item_tag)
        else:
            self.validation_text.insert("end", "\nWARNINGS / INFO\n", "ok_header")
            self.validation_text.insert("end", "- Không có warning.\n", "info_item")
        self.validation_text.configure(state="disabled")

    def render_color_balance(self):
        if not hasattr(self, "color_balance_tree"):
            return
        for item in self.color_balance_tree.get_children():
            self.color_balance_tree.delete(item)

        shooter_by_color, tray_by_color = self.collect_color_balance()
        for color in BALL_COLORS:
            if color == "None":
                continue
            shooter = shooter_by_color.get(color, 0)
            tray = tray_by_color.get(color, 0)
            if shooter == 0 and tray == 0:
                continue
            delta = shooter - tray
            tag = "ok" if delta == 0 else "bad"
            self.color_balance_tree.insert("", "end", values=(color, shooter, tray, f"{delta:+d}"), tags=(tag,))

        if not self.color_balance_tree.get_children():
            self.color_balance_tree.insert("", "end", values=("No data", 0, 0, "+0"), tags=("unused",))

    def collect_color_balance(self) -> Tuple[Dict[str, int], Dict[str, int]]:
        shooter_by_color: Dict[str, int] = {}
        tray_by_color: Dict[str, int] = {}
        for cell in self.level.get("grid", {}).get("cells", []):
            entity = cell.get("entity")
            if not entity:
                continue
            if entity.get("type") == "Shooter":
                shooter = entity.get("shooter", {})
                color = shooter.get("colorId")
                if color in BALL_COLORS and color != "None":
                    shooter_by_color[color] = shooter_by_color.get(color, 0) + max(0, safe_int(str(shooter.get("capacity", 0)), 0))
            if entity.get("type") == "Tunnel":
                for shooter in entity.get("shooterQueue", []):
                    color = shooter.get("colorId")
                    if color in BALL_COLORS and color != "None":
                        shooter_by_color[color] = shooter_by_color.get(color, 0) + max(0, safe_int(str(shooter.get("capacity", 0)), 0))

        for gate in self.level.get("gateSystem", {}).get("gates", []):
            for tray in gate.get("trayQueue", []):
                for layer in tray.get("layers", []):
                    color = layer.get("colorId")
                    if color in BALL_COLORS and color != "None":
                        tray_by_color[color] = tray_by_color.get(color, 0) + max(0, safe_int(str(layer.get("requiredCount", 0)), 0))
        return shooter_by_color, tray_by_color

    def mark_level_changed(self):
        if not hasattr(self, "validation_summary"):
            return
        if not self.auto_validate_var.get():
            self.validation_summary.configure(text="Changed, not checked", bg="#92400E", fg="#FFFFFF")
            return
        if self._validation_after_id is not None:
            self.after_cancel(self._validation_after_id)
        self.validation_summary.configure(text="Checking...", bg="#1D4ED8", fg="#FFFFFF")
        self._validation_after_id = self.after(250, self.validate_level)

    def refresh_json_preview(self):
        self.sync_basic_fields()
        self.json_text.delete("1.0", "end")
        self.json_text.insert("1.0", json.dumps(self.level, ensure_ascii=False, indent=2))
        self.mark_level_changed()

    def _refresh_all(self):
        grid = self.level.get("grid", {})
        self.rows_var.set(grid.get("rows", 4))
        self.cols_var.set(grid.get("columns", 4))
        self.game_mode_var.set(self.level.get("gameMode", "Classic"))
        self.difficulty_var.set(self.level.get("difficulty", "Normal"))
        self.level_var.set(str(self.level.get("level", 1)))
        self.file_level_var.set(str(self.level.get("level", 1)))
        self.category_var.set(self.level.get("category", 0))
        self.time_var.set(self.level.get("time", 60))
        self.level_name_var.set(self.level.get("levelName", "New Level"))

        gs = self.level.get("gateSystem", {})
        self.gate_count_var.set(gs.get("gateCount", 4))
        self.max_visible_var.set(gs.get("maxVisibleTrayPerGate", 4))

        self._refresh_grid_buttons()
        self.refresh_gate_ui()
        self.refresh_gate_text()
        self.refresh_json_preview()
        self._refresh_level_folder_files()

    def _refresh_grid_buttons(self):
        for child in self.grid_inner.winfo_children():
            child.destroy()
        self.grid_buttons.clear()
        self.grid_button_frames.clear()

        rows = self.level.get("grid", {}).get("rows", 4)
        cols = self.level.get("grid", {}).get("columns", 4)

        for r in range(rows):
            for c in range(cols):
                cell = find_cell(self.level, r, c)
                entity = cell.get("entity")
                is_selected = self.selected_cell == (r, c) or (r, c) in self.selected_grid_cells
                frame_bg, frame_padx, frame_pady = self._grid_selection_frame_style(is_selected, entity)
                border = tk.Frame(
                    self.grid_inner,
                    bg=frame_bg,
                    padx=frame_padx,
                    pady=frame_pady,
                )
                border.grid(row=r, column=c, padx=2, pady=2)
                btn = tk.Button(
                    border,
                    text=entity_label(entity),
                    width=10,
                    height=4,
                    relief="flat",
                    bg=entity_bg(entity),
                    fg=self._grid_entity_fg(entity),
                )
                btn.pack(fill="both", expand=True)
                btn.bind("<ButtonPress-1>", lambda e, rr=r, cc=c: self.start_grid_drag(e, rr, cc))
                btn.bind("<ButtonRelease-1>", self.end_grid_drag)
                btn.bind("<Double-Button-1>", lambda e, rr=r, cc=c: self.select_cell(rr, cc, paint=True))
                btn.bind("<Button-3>", lambda e, rr=r, cc=c: self.on_grid_right_click(rr, cc))
                btn.bind("<Double-Button-3>", lambda e, rr=r, cc=c: self.clear_grid_cell(rr, cc))
                self.grid_buttons[(r, c)] = btn
                self.grid_button_frames[(r, c)] = border

    def _refresh_grid_button_states(self):
        if not self.grid_buttons:
            return
        for (row, col), btn in self.grid_buttons.items():
            cell = find_cell(self.level, row, col)
            entity = cell.get("entity")
            is_selected = self.selected_cell == (row, col) or (row, col) in self.selected_grid_cells
            frame_bg, frame_padx, frame_pady = self._grid_selection_frame_style(is_selected, entity)
            frame = self.grid_button_frames.get((row, col))
            if frame is not None:
                frame.configure(
                    bg=frame_bg,
                    padx=frame_padx,
                    pady=frame_pady,
                )
            btn.configure(
                text=entity_label(entity),
                bg=entity_bg(entity),
                fg=self._grid_entity_fg(entity),
            )

    def start_grid_drag(self, event, row: int, col: int):
        self.grid_drag_cell = (row, col)

    def end_grid_drag(self, event):
        if self.grid_drag_cell is None:
            return
        target = self._cell_from_widget(self.winfo_containing(event.x_root, event.y_root))
        source = self.grid_drag_cell
        self.grid_drag_cell = None
        if target is None:
            return
        if target == source:
            self.on_grid_cell_click(source[0], source[1], event)
            return
        source_entity = find_cell(self.level, *source).get("entity")
        target_entity = find_cell(self.level, *target).get("entity")
        if not self._is_shooter_entity(source_entity) or not self._is_shooter_entity(target_entity):
            return
        self.record_history()
        find_cell(self.level, *source)["entity"], find_cell(self.level, *target)["entity"] = target_entity, source_entity
        self.selected_cell = target
        self.selected_grid_cells = {target} if self._grid_multi_shooter_select_enabled() else set()
        self._update_selected_label()
        self._refresh_grid_button_states()
        self.refresh_json_preview()

    def on_grid_right_click(self, row: int, col: int):
        right_clear_option = getattr(self, "grid_right_clear_var", None)
        if right_clear_option is None or right_clear_option.get():
            self.clear_grid_cell(row, col)
        else:
            self.select_cell(row, col, paint=False)
        return "break"

    def _cell_from_widget(self, widget) -> Optional[Tuple[int, int]]:
        while widget is not None:
            for cell, btn in self.grid_buttons.items():
                if widget == btn or widget == self.grid_button_frames.get(cell):
                    return cell
            widget = getattr(widget, "master", None)
        return None

    def _is_shooter_entity(self, entity: Optional[Dict[str, Any]]) -> bool:
        return bool(entity and entity.get("type") == "Shooter")

    def clear_grid_cell(self, row: int, col: int):
        self.record_history()
        find_cell(self.level, row, col)["entity"] = None
        self.selected_cell = (row, col)
        self.selected_grid_cells.clear()
        self._update_selected_label()
        self._refresh_grid_button_states()
        self.refresh_json_preview()

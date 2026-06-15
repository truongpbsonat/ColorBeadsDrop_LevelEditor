from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk
from typing import Optional

from .color_utils import SELECTABLE_BALL_COLORS, color_text_hex
from .constants import COLOR_HEX, DIRECTIONS, ENTITY_TYPES, LEVEL_DIFFICULTIES, TRAY_ICE_DEFAULT_HP
from .editor_paths import ICON_DIR


class EditorUiMixin:
    def _build_ui(self):
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)
        self.columnconfigure(2, weight=0)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)

        top = ttk.Frame(self, padding=(8, 8, 8, 0))
        top.grid(row=0, column=0, columnspan=3, sticky="ew")
        top.columnconfigure(0, weight=1)
        self._build_toolbar(top)

        left = ttk.Frame(self, padding=8)
        left.grid(row=1, column=0, sticky="ns")
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)

        left_inner = self._build_scrollable_sidebar(left)
        self._build_inspector_tabs(left_inner)

        workspace = ttk.Frame(self, padding=(0, 8, 8, 8))
        workspace.grid(row=1, column=1, sticky="nsew")
        workspace.rowconfigure(0, weight=1)
        workspace.columnconfigure(0, weight=13, minsize=560, uniform="workspace")
        workspace.columnconfigure(1, weight=7, minsize=240, uniform="workspace")

        grid_workspace = ttk.Frame(workspace, padding=(0, 0, 4, 0))
        gate_workspace = ttk.Frame(workspace, padding=(4, 0, 0, 0))
        grid_workspace.grid(row=0, column=0, sticky="nsew")
        gate_workspace.grid(row=0, column=1, sticky="nsew")
        self._build_grid_editor(grid_workspace)
        self._build_gate_editor(gate_workspace)

        utility_side = ttk.Frame(self, padding=(0, 8, 8, 8), width=300)
        utility_side.grid(row=1, column=2, sticky="ns")
        utility_side.grid_propagate(False)
        utility_side.rowconfigure(0, weight=6)
        utility_side.rowconfigure(1, weight=4)
        utility_side.columnconfigure(0, weight=1)
        self._build_validation_panel(utility_side)

        json_holder = ttk.LabelFrame(utility_side, text="JSON Preview", padding=6)
        json_holder.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        self._build_json_preview(json_holder)

    def _build_scrollable_sidebar(self, parent):
        self.left_canvas = tk.Canvas(parent, width=340, highlightthickness=0)
        left_scrollbar = ttk.Scrollbar(parent, orient="vertical", command=self.left_canvas.yview)
        self.left_canvas.configure(yscrollcommand=left_scrollbar.set)
        self.left_canvas.grid(row=0, column=0, sticky="nsew")
        left_scrollbar.grid(row=0, column=1, sticky="ns")

        content = ttk.Frame(self.left_canvas)
        window_id = self.left_canvas.create_window((0, 0), window=content, anchor="nw")
        content.bind("<Configure>", lambda e: self.left_canvas.configure(scrollregion=self.left_canvas.bbox("all")))
        self.left_canvas.bind("<Configure>", lambda e: self.left_canvas.itemconfigure(window_id, width=e.width))
        self.left_canvas.bind("<Enter>", lambda e: self.left_canvas.bind_all("<MouseWheel>", self._on_sidebar_mousewheel))
        self.left_canvas.bind("<Leave>", lambda e: self.left_canvas.unbind_all("<MouseWheel>"))
        return content

    def _build_inspector_tabs(self, parent):
        self.inspector_notebook = ttk.Notebook(parent)
        self.inspector_notebook.pack(fill="both", expand=True)
        tabs = {
            "Cells": ttk.Frame(self.inspector_notebook),
            "Grid Obstacles": ttk.Frame(self.inspector_notebook),
            "Shooter Groups": ttk.Frame(self.inspector_notebook),
            "Trays": ttk.Frame(self.inspector_notebook),
        }
        for title, tab in tabs.items():
            self.inspector_notebook.add(tab, text=title)
        self._build_cell_editor(tabs["Cells"])
        self._build_obstacle_editor(tabs["Grid Obstacles"])
        self._build_shooter_group_editor(tabs["Shooter Groups"])
        self._build_tray_tool_panel(tabs["Trays"])
        self.inspector_notebook.bind("<<NotebookTabChanged>>", self.on_inspector_tab_changed)

    def _on_sidebar_mousewheel(self, event):
        if not hasattr(self, "left_canvas"):
            return
        self.left_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _build_toolbar(self, parent):
        frame = ttk.LabelFrame(parent, text="File / Level", padding=(6, 5))
        frame.grid(row=0, column=0, sticky="ew")
        for col in range(19):
            frame.columnconfigure(col, weight=0)
        frame.columnconfigure(16, weight=1)

        ttk.Button(frame, text="New", command=self.new_level, width=5).grid(row=0, column=0, padx=(0, 2), pady=1)
        ttk.Button(frame, text="Folder", command=self.choose_level_folder, width=7).grid(row=0, column=1, padx=2, pady=1)
        ttk.Button(frame, text="Prev", command=self.load_previous_level, width=5).grid(row=0, column=2, padx=2, pady=1)
        level_entry = ttk.Entry(frame, textvariable=self.file_level_var, width=7)
        level_entry.grid(row=0, column=3, padx=2, pady=1, sticky="w")
        level_entry.bind("<Return>", lambda e: self.load_selected_level())
        ttk.Button(frame, text="Next", command=self.load_next_level, width=5).grid(row=0, column=4, padx=2, pady=1)
        ttk.Button(frame, text="Load", command=self.load_selected_level, width=5).grid(row=0, column=5, padx=(2, 8), pady=1)

        ttk.Label(frame, textvariable=self.level_folder_var, width=14, anchor="w").grid(row=0, column=6, padx=(4, 8), pady=1, sticky="w")

        ttk.Label(frame, text="Difficulty").grid(row=0, column=7, padx=(0, 3), pady=1, sticky="w")
        difficulty_combo = ttk.Combobox(frame, textvariable=self.difficulty_var, values=LEVEL_DIFFICULTIES, state="readonly", width=10)
        difficulty_combo.grid(row=0, column=8, padx=(0, 8), pady=1, sticky="w")
        difficulty_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh_json_preview())

        ttk.Button(frame, text="Save", command=self.save_json, width=5).grid(row=0, column=9, padx=2, pady=1)
        ttk.Button(frame, text="Save As", command=self.save_json_as, width=7).grid(row=0, column=10, padx=(2, 8), pady=1)
        ttk.Button(frame, text="Undo", command=self.undo, width=5).grid(row=0, column=11, padx=2, pady=1)
        ttk.Button(frame, text="Redo", command=self.redo, width=5).grid(row=0, column=12, padx=2, pady=1)
        ttk.Button(frame, text="Info", command=self.show_info, width=5).grid(row=0, column=13, padx=(2, 8), pady=1)
        ttk.Label(frame, textvariable=self.level_save_status_var, width=15, anchor="w").grid(row=0, column=14, padx=(0, 8), pady=1, sticky="w")
        ttk.Label(frame, textvariable=self.level_file_status_var, anchor="w").grid(row=0, column=15, sticky="w", pady=1)
        ttk.Button(frame, text="Color Tool", command=self.open_color_replace_tool, width=10).grid(row=0, column=16, padx=(8, 0), pady=1, sticky="e")
        ttk.Button(frame, text="Gen Level", command=self.open_level_generator, width=10).grid(row=0, column=17, padx=(8, 0), pady=1, sticky="e")
        ttk.Button(frame, text="Test Level", command=self.open_level_tester, width=10).grid(row=0, column=18, padx=(8, 0), pady=1, sticky="e")

        ttk.Label(frame, text="Mechanics").grid(row=1, column=0, padx=(0, 3), pady=(5, 1), sticky="w")
        mechanics_entry = ttk.Entry(frame, textvariable=self.mechanics_var)
        mechanics_entry.grid(row=1, column=1, columnspan=5, padx=(0, 4), pady=(5, 1), sticky="ew")
        mechanics_entry.bind("<Return>", lambda e: self.refresh_json_preview())
        mechanics_entry.bind("<FocusOut>", lambda e: self.refresh_json_preview())
        ttk.Button(frame, text="Auto-detect mechanics", command=self.auto_detect_mechanics).grid(
            row=1, column=6, columnspan=2, padx=(0, 4), pady=(5, 1), sticky="w"
        )
        ttk.Button(frame, text="Auto-detect folder", command=self.auto_detect_mechanics_for_folder).grid(
            row=1, column=8, columnspan=2, padx=(0, 8), pady=(5, 1), sticky="w"
        )

    def _load_icon_images(self):
        if not os.path.isdir(ICON_DIR):
            return
        for filename in os.listdir(ICON_DIR):
            if not filename.lower().endswith(".png"):
                continue
            path = os.path.join(ICON_DIR, filename)
            key = os.path.splitext(filename)[0]
            try:
                image = tk.PhotoImage(file=path)
                scale = max(1, max(image.width(), image.height()) // 28)
                if scale > 1:
                    image = image.subsample(scale, scale)
                self.icon_images[key] = image
            except tk.TclError:
                continue

    def _choice_button(
        self,
        parent,
        group: str,
        variable: tk.Variable,
        value: str,
        text: str,
        command=None,
        image=None,
        width: int = 8,
        height: Optional[int] = None,
        normal_bg: Optional[str] = None,
        normal_fg: str = "#111111",
        compound: str = "left",
    ) -> tk.Button:
        button_options = {
            "text": text,
            "image": image,
            "compound": compound,
            "width": width,
            "padx": 4,
            "pady": 3,
            "relief": "raised",
            "bd": 1,
            "bg": normal_bg or self.cget("bg"),
            "fg": normal_fg,
            "activebackground": normal_bg or self.cget("bg"),
            "command": lambda: self._set_choice_value(group, variable, value, command),
        }
        if height is not None:
            button_options["height"] = height
        button = tk.Button(parent, **button_options)
        self.choice_button_groups.setdefault(group, []).append({
            "button": button,
            "value": value,
            "variable": variable,
            "normal_bg": normal_bg or self.cget("bg"),
            "normal_fg": normal_fg,
        })
        return button

    def _set_choice_value(self, group: str, variable: tk.Variable, value: str, command=None):
        variable.set(value)
        self._refresh_choice_group(group)
        if command:
            command()

    def _refresh_choice_group(self, group: str):
        for item in self.choice_button_groups.get(group, []):
            selected = item["variable"].get() == item["value"]
            button = item["button"]
            if selected:
                if item["normal_bg"] == self.cget("bg"):
                    button.configure(relief="sunken", bd=3, bg="#D7ECFF", fg="#000000")
                else:
                    button.configure(relief="sunken", bd=4, bg=item["normal_bg"], fg=item["normal_fg"])
            else:
                button.configure(relief="raised", bd=1, bg=item["normal_bg"], fg=item["normal_fg"])

    def _set_choice_group_state(self, group: str, state: str):
        for item in self.choice_button_groups.get(group, []):
            item["button"].configure(state=state)

    def _toggle_button(self, parent, text: str, variable: tk.BooleanVar, command=None) -> tk.Checkbutton:
        return tk.Checkbutton(
            parent,
            text=text,
            variable=variable,
            command=command,
            indicatoron=False,
            width=8,
            height=2,
            relief="raised",
            bd=1,
            selectcolor="#D7ECFF",
            bg=self.cget("bg"),
            activebackground="#E8F3FF",
        )

    def _build_grid_editor(self, parent):
        parent.rowconfigure(2, weight=1)
        parent.columnconfigure(0, weight=1)

        tools = ttk.LabelFrame(parent, text="Grid Tools", padding=4)
        tools.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        tools.columnconfigure(13, weight=1)
        self.grid_paint_on_click_var = tk.BooleanVar(value=False)
        self.grid_right_clear_var = tk.BooleanVar(value=False)
        self.grid_multi_shooter_select_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(tools, text="Paint", variable=self.grid_paint_on_click_var).grid(row=0, column=0, sticky="w", padx=(0, 4))
        ttk.Checkbutton(tools, text="RClear", variable=self.grid_right_clear_var).grid(row=0, column=1, sticky="w", padx=(0, 4))
        ttk.Checkbutton(tools, text="Multi", variable=self.grid_multi_shooter_select_var).grid(row=0, column=2, sticky="w", padx=(0, 6))
        ttk.Button(tools, text="Paint", command=self.apply_brush_to_selected, width=6).grid(row=0, column=3, sticky="w", padx=1)
        ttk.Button(tools, text="Clear", command=self.clear_selected_cell, width=6).grid(row=0, column=4, sticky="w", padx=1)
        ttk.Button(tools, text="Wall", command=self.wall_selected_cell, width=6).grid(row=0, column=5, sticky="w", padx=1)
        ttk.Button(tools, text="Copy", command=self.copy_selected_cell, width=5).grid(row=0, column=6, sticky="w", padx=1)
        ttk.Button(tools, text="Paste", command=self.paste_selected_cell, width=5).grid(row=0, column=7, sticky="w", padx=(1, 6))
        ttk.Label(tools, text="R").grid(row=0, column=8, sticky="w", padx=(0, 2))
        ttk.Spinbox(tools, from_=1, to=20, textvariable=self.rows_var, width=4).grid(row=0, column=9, sticky="w")
        ttk.Label(tools, text="C").grid(row=0, column=10, sticky="w", padx=(4, 2))
        ttk.Spinbox(tools, from_=1, to=20, textvariable=self.cols_var, width=4).grid(row=0, column=11, sticky="w")
        ttk.Button(tools, text="Resize", command=self.resize_grid, width=6).grid(row=0, column=12, sticky="w", padx=(4, 0))
        ttk.Button(tools, text="Del Row", command=self.delete_selected_grid_row, width=8).grid(row=1, column=3, columnspan=2, sticky="w", padx=1, pady=(4, 0))
        ttk.Button(tools, text="Del Col", command=self.delete_selected_grid_column, width=8).grid(row=1, column=5, columnspan=2, sticky="w", padx=1, pady=(4, 0))

        grid_area = ttk.Frame(parent)
        grid_area.grid(row=2, column=0, sticky="nsew")
        grid_area.rowconfigure(0, weight=1)
        grid_area.columnconfigure(0, weight=1)

        grid_holder = ttk.LabelFrame(grid_area, text="Grid Click/Paint", padding=8)
        grid_holder.grid(row=0, column=0, sticky="nsew")
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

        self._build_tunnel_queue_panel(grid_area)

        self.selected_label = ttk.Label(parent, text="Selected: none")
        self.selected_label.grid(row=3, column=0, sticky="w", pady=(8, 0))

    def _build_tunnel_queue_panel(self, parent):
        self.tunnel_queue_panel = ttk.LabelFrame(parent, text="Tunnel Queue", padding=6, width=128)
        self.tunnel_queue_panel.grid(row=0, column=1, sticky="ns", padx=(8, 0))
        self.tunnel_queue_panel.pack_propagate(False)
        self.tunnel_queue_panel.grid_remove()

        self.tunnel_queue_grid = ttk.Frame(self.tunnel_queue_panel)
        self.tunnel_queue_grid.pack(fill="both", expand=True)
        self.tunnel_queue_grid.columnconfigure(0, weight=1)

        controls = ttk.Frame(self.tunnel_queue_panel)
        controls.pack(fill="x", pady=(8, 0))
        ttk.Button(controls, text="Add", command=self.add_tunnel_queue_shooter).grid(row=0, column=0, sticky="ew", pady=2)
        ttk.Button(controls, text="Delete", command=self.remove_tunnel_queue_shooter).grid(row=1, column=0, sticky="ew", pady=2)
        ttk.Button(controls, text="Up", command=lambda: self.move_tunnel_queue_shooter(-1)).grid(row=2, column=0, sticky="ew", pady=2)
        ttk.Button(controls, text="Down", command=lambda: self.move_tunnel_queue_shooter(1)).grid(row=3, column=0, sticky="ew", pady=2)
        controls.columnconfigure(0, weight=1)

    def _build_cell_editor(self, parent):
        frame = ttk.LabelFrame(parent, text="Cell Tool", padding=8)
        frame.pack(fill="x", pady=(0, 8))
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=0)

        self.cell_editor_status_var = tk.StringVar(value="Select a shooter or tunnel cell to edit.")
        self.cell_edit_entity_type = tk.StringVar(value="Shooter")
        self.cell_edit_color = tk.StringVar(value="Blue")
        self.cell_edit_capacity = tk.IntVar(value=9)
        self.cell_edit_hidden_modifier = tk.BooleanVar(value=False)
        self.cell_edit_ice_modifier = tk.BooleanVar(value=False)
        self.cell_edit_special_modifier = tk.BooleanVar(value=False)
        self.cell_edit_ice_hp = tk.IntVar(value=1)
        self.cell_edit_tunnel_direction = tk.StringVar(value="Up")
        self.cell_edit_tunnel_queue_index: Optional[int] = None

        ttk.Label(frame, textvariable=self.cell_editor_status_var).grid(row=0, column=0, columnspan=2, sticky="w")

        entity_frame = ttk.LabelFrame(frame, text="Entity", padding=6)
        entity_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        entity_icons = {
            "Shooter": self.icon_images.get("Shooter"),
            "Wall": self.icon_images.get("Wall"),
            "Tunnel": self.icon_images.get("Tunnel"),
        }
        for index, entity_type in enumerate(ENTITY_TYPES):
            button = self._choice_button(
                entity_frame,
                "cell_edit_entity",
                self.cell_edit_entity_type,
                entity_type,
                entity_type,
                command=self.auto_apply_cell_editor,
                image=entity_icons.get(entity_type),
                width=10,
                compound="top",
            )
            button.grid(row=index // 2, column=index % 2, sticky="nsew", padx=2, pady=2)
            entity_frame.rowconfigure(index // 2, weight=1, uniform="entity_rows")
            entity_frame.columnconfigure(index % 2, weight=1, uniform="entity_cols")

        shooter_frame = ttk.LabelFrame(frame, text="Shooter fields", padding=6)
        shooter_frame.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        shooter_frame.columnconfigure(0, weight=1)

        edit_color_buttons = ttk.Frame(shooter_frame)
        edit_color_buttons.grid(row=0, column=0, sticky="ew")
        for index, color in enumerate(SELECTABLE_BALL_COLORS):
            bg = COLOR_HEX.get(color, "#DDDDDD")
            fg = color_text_hex(color)
            button = self._choice_button(
                edit_color_buttons,
                "cell_edit_color",
                self.cell_edit_color,
                color,
                "",
                command=self.auto_apply_color_editor,
                width=2,
                height=1,
                normal_bg=bg,
                normal_fg=fg,
            )
            button.grid(row=index // 5, column=index % 5, padx=2, pady=2)
            edit_color_buttons.columnconfigure(index % 5, weight=1)

        capacity_row = ttk.Frame(shooter_frame)
        capacity_row.grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Label(capacity_row, text="Capacity").pack(side="left")
        self.cell_edit_capacity_spin = ttk.Spinbox(
            capacity_row,
            from_=1,
            to=999,
            textvariable=self.cell_edit_capacity,
            width=8,
            command=self.auto_apply_cell_editor,
        )
        self.cell_edit_capacity_spin.pack(side="left", padx=(6, 18))
        self.cell_edit_capacity_spin.bind("<Return>", self.auto_apply_cell_editor)
        self.cell_edit_capacity_spin.bind("<FocusOut>", self.auto_apply_cell_editor)

        modifier_frame = ttk.LabelFrame(frame, text="Modifiers", padding=6)
        modifier_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        modifier_frame.columnconfigure(0, weight=1, uniform="modifier_cols")
        modifier_frame.columnconfigure(1, weight=1, uniform="modifier_cols")
        modifier_frame.columnconfigure(2, weight=1, uniform="modifier_cols")
        self._toggle_button(
            modifier_frame,
            "Hidden",
            self.cell_edit_hidden_modifier,
            command=lambda: self.apply_modifier_button_change("Hidden"),
        ).grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        self._toggle_button(
            modifier_frame,
            "Ice",
            self.cell_edit_ice_modifier,
            command=lambda: self.apply_modifier_button_change("Ice"),
        ).grid(row=0, column=1, sticky="nsew", padx=2, pady=2)
        self._toggle_button(
            modifier_frame,
            "Special",
            self.cell_edit_special_modifier,
            command=lambda: self.apply_modifier_button_change("Special"),
        ).grid(row=0, column=2, sticky="nsew", padx=2, pady=2)

        ice_hp_row = ttk.Frame(modifier_frame)
        ice_hp_row.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        ttk.Label(ice_hp_row, text="Ice HP").pack(side="left")
        self.cell_edit_ice_hp_spin = ttk.Spinbox(
            ice_hp_row,
            from_=1,
            to=999,
            textvariable=self.cell_edit_ice_hp,
            width=8,
            command=self.apply_ice_hp_change,
        )
        self.cell_edit_ice_hp_spin.pack(side="left", padx=(6, 0))
        self.cell_edit_ice_hp_spin.bind("<Return>", self.apply_ice_hp_change)
        self.cell_edit_ice_hp_spin.bind("<FocusOut>", self.apply_ice_hp_change)

        tunnel_frame = ttk.LabelFrame(frame, text="Tunnel direction", padding=6)
        tunnel_frame.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        for index, direction in enumerate(DIRECTIONS):
            button = self._choice_button(
                tunnel_frame,
                "cell_edit_tunnel_direction",
                self.cell_edit_tunnel_direction,
                direction,
                direction,
                command=self.auto_apply_cell_editor,
                width=5,
            )
            button.grid(row=0, column=index, sticky="ew", padx=2, pady=2)
            tunnel_frame.columnconfigure(index, weight=1, uniform="direction_cols")

        action_frame = ttk.Frame(frame)
        action_frame.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Button(action_frame, text="Remove Modifiers", command=self.remove_cell_editor_modifiers).pack(side="left")

        self._refresh_choice_group("cell_edit_entity")
        self._refresh_choice_group("cell_edit_color")
        self._refresh_choice_group("cell_edit_tunnel_direction")
        self.update_cell_editor_modifier_state()

    def _build_gate_editor(self, parent):
        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=1)

        top = ttk.LabelFrame(parent, text="Gate System", padding=4)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        top.columnconfigure(4, weight=1)

        self.gate_count_var = tk.IntVar(value=4)
        self.max_visible_var = tk.IntVar(value=4)

        ttk.Label(top, text="Gate Count").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(top, from_=1, to=12, textvariable=self.gate_count_var, width=4).grid(row=0, column=1, sticky="w", padx=(3, 6))
        ttk.Label(top, text="Max Tray").grid(row=0, column=2, sticky="w")
        ttk.Spinbox(top, from_=1, to=10, textvariable=self.max_visible_var, width=4).grid(row=0, column=3, sticky="w", padx=(3, 6))

        ttk.Button(top, text="Apply Count", command=self.apply_gate_system, width=11).grid(row=1, column=0, columnspan=2, sticky="w", pady=(3, 0))
        ttk.Button(top, text="Refresh Gate", command=self.apply_gate_ui, width=12).grid(row=1, column=2, columnspan=2, sticky="w", padx=(4, 0), pady=(3, 0))

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

        text_tools = ttk.LabelFrame(parent, text="Text Import / Export", padding=4)
        text_tools.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        text_tools.columnconfigure(0, weight=1)
        self.gate_text = tk.Text(text_tools, height=3, wrap="none", font=("Consolas", 10))
        self.gate_text.grid(row=0, column=0, sticky="ew")
        btns = ttk.Frame(text_tools)
        btns.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        ttk.Button(btns, text="Parse Text", command=self.apply_gate_text, width=10).pack(side="left")
        ttk.Button(btns, text="Reload Text", command=self.refresh_gate_text, width=11).pack(side="left", padx=4)

    def _build_gate_direct_controls(self, parent):
        controls = ttk.Frame(parent, padding=(0, 6, 0, 0))
        controls.grid(row=1, column=0, sticky="ew")
        controls.columnconfigure(0, weight=1)

        self.gate_selection_label = ttk.Label(controls, text="Selected: Gate 0")
        self.gate_selection_label.grid(row=0, column=0, sticky="w", pady=(0, 4))
        self.add_layer_enabled_var = tk.BooleanVar(value=False)
        self.selected_tray_id_var = tk.StringVar()
        self.selected_tray_ice_modifier = tk.BooleanVar(value=False)
        self.selected_tray_ice_hp = tk.IntVar(value=TRAY_ICE_DEFAULT_HP)

        tray_buttons = ttk.Frame(controls)
        tray_buttons.grid(row=1, column=0, sticky="ew")
        ttk.Button(tray_buttons, text="+ Tray", command=self.add_tray_to_selected_gate, width=7).pack(side="left", padx=(0, 3), pady=1)
        ttk.Button(tray_buttons, text="Up", command=lambda: self.move_selected_tray(-1), width=5).pack(side="left", padx=3, pady=1)
        ttk.Button(tray_buttons, text="Down", command=lambda: self.move_selected_tray(1), width=6).pack(side="left", padx=3, pady=1)
        ttk.Button(tray_buttons, text="Delete Tray", command=self.remove_selected_tray, width=10).pack(side="left", padx=3, pady=1)

        gate_layer_buttons = ttk.Frame(controls)
        gate_layer_buttons.grid(row=2, column=0, sticky="ew", pady=(3, 0))
        ttk.Button(gate_layer_buttons, text="Gate Left", command=lambda: self.move_selected_gate(-1), width=9).pack(side="left", padx=(0, 3), pady=1)
        ttk.Button(gate_layer_buttons, text="Gate Right", command=lambda: self.move_selected_gate(1), width=10).pack(side="left", padx=3, pady=1)
        self.add_layer_button = ttk.Button(gate_layer_buttons, text="+ Layer", command=self.add_layer_to_selected_tray, state="disabled", width=8)
        self.add_layer_button.pack(side="left", padx=3, pady=1)
        ttk.Button(gate_layer_buttons, text="Delete Layer", command=self.remove_selected_layer, width=12).pack(side="left", padx=3, pady=1)
        ttk.Checkbutton(gate_layer_buttons, text="Enable Add", variable=self.add_layer_enabled_var, command=self.update_add_layer_button_state).pack(side="left", padx=(3, 0), pady=1)

        layer_fields = ttk.Frame(controls)
        layer_fields.grid(row=3, column=0, sticky="ew", pady=(3, 0))
        ttk.Label(layer_fields, text="Layer").pack(side="left")
        self.selected_layer_var = tk.IntVar(value=0)
        layer_spin = ttk.Spinbox(layer_fields, from_=0, to=0, textvariable=self.selected_layer_var, width=4, command=self.select_layer_from_control)
        layer_spin.pack(side="left", padx=(3, 10))
        layer_spin.bind("<Return>", lambda e: self.select_layer_from_control())
        layer_spin.bind("<FocusOut>", lambda e: self.select_layer_from_control())
        self.selected_layer_spin = layer_spin

        self.selected_layer_color_var = tk.StringVar(value="Blue")
        ttk.Label(layer_fields, text="Color: Tool").pack(side="left", padx=(0, 10))

        ttk.Label(layer_fields, text="Count").pack(side="left")
        self.selected_layer_count_var = tk.IntVar(value=3)
        count_spin = ttk.Spinbox(layer_fields, from_=1, to=999, textvariable=self.selected_layer_count_var, width=5, command=self.apply_selected_layer_fields)
        count_spin.pack(side="left", padx=(3, 0))
        count_spin.bind("<Return>", lambda e: self.apply_selected_layer_fields())
        count_spin.bind("<FocusOut>", lambda e: self.apply_selected_layer_fields())

        modifier_fields = ttk.Frame(controls)
        modifier_fields.grid(row=4, column=0, sticky="ew", pady=(3, 0))
        ttk.Checkbutton(
            modifier_fields,
            text="Tray Ice",
            variable=self.selected_tray_ice_modifier,
            command=self.on_selected_tray_modifier_change,
        ).pack(side="left")
        ttk.Label(modifier_fields, text="HP").pack(side="left", padx=(8, 3))
        self.selected_tray_ice_hp_spin = ttk.Spinbox(
            modifier_fields,
            from_=1,
            to=999,
            textvariable=self.selected_tray_ice_hp,
            width=5,
            command=self.apply_selected_tray_modifiers,
        )
        self.selected_tray_ice_hp_spin.pack(side="left")
        self.selected_tray_ice_hp_spin.bind("<Return>", self.apply_selected_tray_modifiers)
        self.selected_tray_ice_hp_spin.bind("<FocusOut>", self.apply_selected_tray_modifiers)
        ttk.Button(modifier_fields, text="Apply", command=self.apply_selected_tray_modifiers, width=7).pack(side="left", padx=(6, 0))
        ttk.Button(modifier_fields, text="Remove", command=self.remove_selected_tray_modifiers, width=8).pack(side="left", padx=3)
        self.update_selected_tray_modifier_state()

    def update_add_layer_button_state(self):
        if not hasattr(self, "add_layer_button"):
            return
        state = "normal" if self.add_layer_enabled_var.get() else "disabled"
        self.add_layer_button.configure(state=state)

    def update_selected_tray_modifier_state(self):
        if not hasattr(self, "selected_tray_ice_hp_spin"):
            return
        state = "normal" if self.selected_tray_ice_modifier.get() else "disabled"
        self.selected_tray_ice_hp_spin.configure(state=state)

    def _build_json_preview(self, parent):
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)
        self.json_text = tk.Text(parent, wrap="none", font=("Consolas", 10))
        self.json_text.grid(row=0, column=0, sticky="nsew")
        ttk.Button(parent, text="Refresh Preview", command=self.refresh_json_preview).grid(row=1, column=0, sticky="ew", pady=(8, 0))

    def _build_validation_panel(self, parent):
        parent.rowconfigure(0, weight=6)
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
            pady=4,
            anchor="w",
        )
        self.validation_summary.grid(row=0, column=0, sticky="ew", pady=(0, 4))

        actions = ttk.Frame(frame)
        actions.grid(row=1, column=0, sticky="ew", pady=(0, 4))
        actions.columnconfigure(1, weight=1)
        self.auto_validate_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(actions, text="Auto check", variable=self.auto_validate_var, command=self.mark_level_changed).grid(row=0, column=0, sticky="w")
        ttk.Button(actions, text="Check Now", command=self.validate_level).grid(row=0, column=1, sticky="e")

        balance_frame = ttk.LabelFrame(frame, text="Color Balance", padding=4)
        balance_frame.grid(row=2, column=0, sticky="ew", pady=(0, 4))
        balance_frame.columnconfigure(0, weight=1)
        columns = ("color", "shooter", "tray", "delta")
        self.color_balance_tree = ttk.Treeview(balance_frame, columns=columns, show="headings", height=5)
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
            height=8,
        )
        self.validation_text.grid(row=3, column=0, sticky="nsew")
        self.validation_text.tag_configure("error_header", foreground="#FFFFFF", background="#B91C1C", spacing1=6, spacing3=4)
        self.validation_text.tag_configure("warning_header", foreground="#111827", background="#FBBF24", spacing1=6, spacing3=4)
        self.validation_text.tag_configure("ok_header", foreground="#FFFFFF", background="#047857", spacing1=6, spacing3=4)
        self.validation_text.tag_configure("error_item", foreground="#FCA5A5", lmargin1=8, lmargin2=20, spacing3=3)
        self.validation_text.tag_configure("warning_item", foreground="#FDE68A", lmargin1=8, lmargin2=20, spacing3=3)
        self.validation_text.tag_configure("info_item", foreground="#A7F3D0", lmargin1=8, lmargin2=20, spacing3=3)

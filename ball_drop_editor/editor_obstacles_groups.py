from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Dict, List, Optional, Set, Tuple

from .color_utils import SELECTABLE_BALL_COLORS
from .constants import DIRECTIONS, GRID_OBSTACLE_SHAPE_TYPES, GRID_OBSTACLE_TYPES, SHOOTER_GROUP_TYPES
from .level_data import find_cell
from .utils import safe_int, short_id


class EditorObstacleGroupMixin:
    def _build_obstacle_editor(self, parent):
        frame = ttk.LabelFrame(parent, text="Grid Obstacle Tool", padding=8)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)

        self.obstacle_status_var = tk.StringVar(value="Select a cell to place or edit an obstacle.")
        self.obstacle_type_var = tk.StringVar(value="IceBlock")
        self.obstacle_shape_type_var = tk.StringVar(value="CustomCells")
        self.obstacle_origin_row_var = tk.IntVar(value=0)
        self.obstacle_origin_col_var = tk.IntVar(value=0)
        self.obstacle_width_var = tk.IntVar(value=1)
        self.obstacle_height_var = tk.IntVar(value=1)
        self.obstacle_hp_var = tk.IntVar(value=1)
        self.obstacle_direction_var = tk.StringVar(value="Right")
        self.obstacle_length_var = tk.IntVar(value=3)
        self.obstacle_glass_color_var = tk.StringVar(value="Blue")

        ttk.Label(frame, textvariable=self.obstacle_status_var).grid(row=0, column=0, sticky="w")

        type_frame = ttk.LabelFrame(frame, text="Type", padding=6)
        type_frame.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        for index, obstacle_type in enumerate(GRID_OBSTACLE_TYPES):
            button = self._choice_button(
                type_frame,
                "obstacle_type",
                self.obstacle_type_var,
                obstacle_type,
                obstacle_type,
                command=self.on_obstacle_type_changed,
                width=10,
            )
            button.grid(row=0, column=index, sticky="ew", padx=2, pady=2)
            type_frame.columnconfigure(index, weight=1, uniform="obstacle_type_cols")

        shape_frame = ttk.LabelFrame(frame, text="Shape", padding=6)
        shape_frame.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        for col in range(4):
            shape_frame.columnconfigure(col, weight=1)
        ttk.Label(shape_frame, text="Shape").grid(row=0, column=0, sticky="w")
        shape_combo = ttk.Combobox(
            shape_frame,
            textvariable=self.obstacle_shape_type_var,
            values=GRID_OBSTACLE_SHAPE_TYPES,
            state="readonly",
            width=16,
        )
        shape_combo.grid(row=0, column=1, columnspan=3, sticky="ew", padx=(4, 0))
        shape_combo.bind("<<ComboboxSelected>>", self.on_obstacle_shape_changed)

        ttk.Label(shape_frame, text="Row").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Spinbox(shape_frame, from_=0, to=99, textvariable=self.obstacle_origin_row_var, width=6).grid(
            row=1, column=1, sticky="ew", padx=(4, 8), pady=(6, 0)
        )
        ttk.Label(shape_frame, text="Col").grid(row=1, column=2, sticky="w", pady=(6, 0))
        ttk.Spinbox(shape_frame, from_=0, to=99, textvariable=self.obstacle_origin_col_var, width=6).grid(
            row=1, column=3, sticky="ew", padx=(4, 0), pady=(6, 0)
        )
        ttk.Label(shape_frame, text="W").grid(row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Spinbox(shape_frame, from_=1, to=99, textvariable=self.obstacle_width_var, width=6).grid(
            row=2, column=1, sticky="ew", padx=(4, 8), pady=(6, 0)
        )
        ttk.Label(shape_frame, text="H").grid(row=2, column=2, sticky="w", pady=(6, 0))
        ttk.Spinbox(shape_frame, from_=1, to=99, textvariable=self.obstacle_height_var, width=6).grid(
            row=2, column=3, sticky="ew", padx=(4, 0), pady=(6, 0)
        )

        ice_frame = ttk.LabelFrame(frame, text="IceBlock", padding=6)
        ice_frame.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        ttk.Label(ice_frame, text="HP").pack(side="left")
        ttk.Spinbox(ice_frame, from_=1, to=999, textvariable=self.obstacle_hp_var, width=7).pack(side="left", padx=(6, 0))

        lock_frame = ttk.LabelFrame(frame, text="LockBar / GlassBarrier (Direction & Length)", padding=6)
        lock_frame.grid(row=4, column=0, sticky="ew", pady=(6, 0))
        for index, direction in enumerate(DIRECTIONS):
            button = self._choice_button(
                lock_frame,
                "obstacle_direction",
                self.obstacle_direction_var,
                direction,
                direction,
                command=self.on_lockbar_direction_changed,
                width=5,
            )
            button.grid(row=0, column=index, sticky="ew", padx=2, pady=2)
            lock_frame.columnconfigure(index, weight=1, uniform="lock_direction_cols")
        ttk.Label(lock_frame, text="Length").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Spinbox(lock_frame, from_=1, to=99, textvariable=self.obstacle_length_var, width=7).grid(
            row=1, column=1, sticky="ew", padx=(4, 0), pady=(6, 0)
        )

        glass_frame = ttk.LabelFrame(frame, text="GlassBarrier", padding=6)
        glass_frame.grid(row=5, column=0, sticky="ew", pady=(6, 0))
        ttk.Label(glass_frame, text="Color").pack(side="left")
        ttk.Combobox(
            glass_frame,
            textvariable=self.obstacle_glass_color_var,
            values=list(SELECTABLE_BALL_COLORS),
            state="readonly",
            width=14,
        ).pack(side="left", padx=(6, 0))

        action_frame = ttk.Frame(frame)
        action_frame.grid(row=6, column=0, sticky="ew", pady=(8, 0))
        for col in range(3):
            action_frame.columnconfigure(col, weight=1)
        ttk.Button(action_frame, text="Add", command=self.add_obstacle_from_form).grid(row=0, column=0, sticky="ew", padx=(0, 2), pady=2)
        ttk.Button(action_frame, text="Apply", command=self.apply_obstacle_fields).grid(row=0, column=1, sticky="ew", padx=2, pady=2)
        ttk.Button(action_frame, text="Delete", command=self.delete_selected_obstacle).grid(row=0, column=2, sticky="ew", padx=(2, 0), pady=2)
        ttk.Button(action_frame, text="Duplicate", command=self.duplicate_selected_obstacle).grid(row=1, column=0, sticky="ew", padx=(0, 2), pady=2)
        ttk.Button(action_frame, text="Use Selected", command=self.use_selected_cells_for_obstacle).grid(row=1, column=1, sticky="ew", padx=2, pady=2)
        ttk.Button(action_frame, text="Clear Cells", command=self.clear_obstacle_custom_cells).grid(row=1, column=2, sticky="ew", padx=(2, 0), pady=2)

        list_frame = ttk.LabelFrame(frame, text="Obstacles", padding=6)
        list_frame.grid(row=7, column=0, sticky="nsew", pady=(8, 0))
        frame.rowconfigure(7, weight=1)
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)
        columns = ("type", "shape", "origin", "extra")
        self.obstacle_tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=8)
        for key, title, width in [
            ("type", "Type", 78),
            ("shape", "Shape", 94),
            ("origin", "Origin", 64),
            ("extra", "Extra", 92),
        ]:
            self.obstacle_tree.heading(key, text=title)
            self.obstacle_tree.column(key, width=width, minwidth=48, anchor="center", stretch=(key == "shape"))
        self.obstacle_tree.grid(row=0, column=0, sticky="nsew")
        obstacle_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.obstacle_tree.yview)
        obstacle_scroll.grid(row=0, column=1, sticky="ns")
        self.obstacle_tree.configure(yscrollcommand=obstacle_scroll.set)
        self.obstacle_tree.bind("<<TreeviewSelect>>", self.on_obstacle_tree_select)

        self._refresh_choice_group("obstacle_type")
        self._refresh_choice_group("obstacle_direction")
        self.update_obstacle_field_state()

    def _build_shooter_group_editor(self, parent):
        frame = ttk.LabelFrame(parent, text="Shooter Group Tool", padding=8)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)

        self.group_status_var = tk.StringVar(value="Select shooter cells to build a group.")
        self.group_type_var = tk.StringVar(value="Connected")
        ttk.Label(frame, textvariable=self.group_status_var).grid(row=0, column=0, sticky="w")

        type_frame = ttk.LabelFrame(frame, text="Type", padding=6)
        type_frame.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        for index, group_type in enumerate(SHOOTER_GROUP_TYPES):
            button = self._choice_button(
                type_frame,
                "group_type",
                self.group_type_var,
                group_type,
                group_type,
                command=self.apply_group_type_to_selection,
                width=9,
            )
            button.grid(row=0, column=index, sticky="ew", padx=2, pady=2)
            type_frame.columnconfigure(index, weight=1, uniform="group_type_cols")

        action_frame = ttk.Frame(frame)
        action_frame.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        for col in range(2):
            action_frame.columnconfigure(col, weight=1)
        ttk.Button(action_frame, text="New", command=self.add_empty_group).grid(row=0, column=0, sticky="ew", padx=(0, 2), pady=2)
        ttk.Button(action_frame, text="From Selected", command=self.add_group_from_selected_cells).grid(
            row=0, column=1, sticky="ew", padx=(2, 0), pady=2
        )
        ttk.Button(action_frame, text="Add Selected", command=self.add_selected_cells_to_group).grid(
            row=1, column=0, sticky="ew", padx=(0, 2), pady=2
        )
        ttk.Button(action_frame, text="Clear Members", command=self.clear_selected_group_members).grid(
            row=1, column=1, sticky="ew", padx=(2, 0), pady=2
        )
        ttk.Button(action_frame, text="Delete", command=self.delete_selected_group).grid(row=2, column=0, sticky="ew", padx=(0, 2), pady=2)
        ttk.Button(action_frame, text="Prune Missing", command=self.prune_missing_group_members).grid(
            row=2, column=1, sticky="ew", padx=(2, 0), pady=2
        )

        list_frame = ttk.LabelFrame(frame, text="Groups", padding=6)
        list_frame.grid(row=3, column=0, sticky="nsew", pady=(8, 0))
        frame.rowconfigure(3, weight=1)
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)
        columns = ("type", "count", "members")
        self.group_tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=10)
        for key, title, width in [
            ("type", "Type", 84),
            ("count", "Count", 52),
            ("members", "Members", 168),
        ]:
            self.group_tree.heading(key, text=title)
            self.group_tree.column(key, width=width, minwidth=46, anchor="center", stretch=(key == "members"))
        self.group_tree.grid(row=0, column=0, sticky="nsew")
        group_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.group_tree.yview)
        group_scroll.grid(row=0, column=1, sticky="ns")
        self.group_tree.configure(yscrollcommand=group_scroll.set)
        self.group_tree.bind("<<TreeviewSelect>>", self.on_group_tree_select)

        self._refresh_choice_group("group_type")

    def _build_tray_tool_panel(self, parent):
        frame = ttk.LabelFrame(parent, text="Tray Tool", padding=8)
        frame.pack(fill="x")
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

        ttk.Button(frame, text="+ Tray", command=self.add_tray_to_selected_gate).grid(row=0, column=0, sticky="ew", padx=(0, 2), pady=2)
        ttk.Button(frame, text="Delete Tray", command=self.remove_selected_tray).grid(row=0, column=1, sticky="ew", padx=(2, 0), pady=2)
        ttk.Button(frame, text="Tray Up", command=lambda: self.move_selected_tray(-1)).grid(row=1, column=0, sticky="ew", padx=(0, 2), pady=2)
        ttk.Button(frame, text="Tray Down", command=lambda: self.move_selected_tray(1)).grid(row=1, column=1, sticky="ew", padx=(2, 0), pady=2)
        ttk.Button(frame, text="+ Layer", command=self.add_layer_to_selected_tray_from_tool).grid(row=2, column=0, sticky="ew", padx=(0, 2), pady=2)
        ttk.Button(frame, text="Delete Layer", command=self.remove_selected_layer).grid(row=2, column=1, sticky="ew", padx=(2, 0), pady=2)

    def on_inspector_tab_changed(self, event=None):
        if not hasattr(self, "inspector_notebook"):
            return None
        tab_text = self.inspector_notebook.tab(self.inspector_notebook.select(), "text")
        if tab_text == "Grid Obstacles":
            self.editor_tool_mode.set("Obstacles")
        elif tab_text == "Shooter Groups":
            self.editor_tool_mode.set("Groups")
        else:
            self.editor_tool_mode.set("Cells")
        self._refresh_grid_button_states()
        return None

    def add_layer_to_selected_tray_from_tool(self):
        add_layer_enabled = getattr(self, "add_layer_enabled_var", None)
        if add_layer_enabled is not None:
            add_layer_enabled.set(True)
            self.update_add_layer_button_state()
        self.add_layer_to_selected_tray()

    def refresh_obstacle_group_ui(self):
        self._clamp_selected_obstacle_index()
        self._clamp_selected_group_index()
        if hasattr(self, "obstacle_tree"):
            self._refresh_obstacle_tree()
            self._sync_obstacle_form_from_selection()
        if hasattr(self, "group_tree"):
            self._refresh_group_tree()
            self._sync_group_form_from_selection()
        if hasattr(self, "grid_buttons"):
            self._refresh_grid_button_states()

    def update_obstacle_field_state(self):
        if not hasattr(self, "obstacle_type_var"):
            return
        obstacle_type = self.obstacle_type_var.get()
        if obstacle_type in ("LockBar", "GlassBarrier"):
            self.obstacle_shape_type_var.set(self._shape_type_for_lockbar())

    def on_obstacle_type_changed(self):
        self.update_obstacle_field_state()
        self._refresh_choice_group("obstacle_type")

    def on_obstacle_shape_changed(self, event=None):
        if self.obstacle_shape_type_var.get() == "CustomCells" and not self.obstacle_custom_cells:
            selected = self._selected_obstacle()
            if selected is not None:
                self.obstacle_custom_cells = set(self._obstacle_cells(selected))
        self._refresh_grid_button_states()
        return None

    def on_lockbar_direction_changed(self):
        self.obstacle_shape_type_var.set(self._shape_type_for_lockbar())
        self._refresh_choice_group("obstacle_direction")

    def add_obstacle_from_form(self):
        self.record_history()
        obstacle = self._obstacle_from_form()
        obstacles = self._grid_obstacles()
        obstacles.append(obstacle)
        self.selected_obstacle_index = len(obstacles) - 1
        self._after_obstacle_changed()

    def apply_obstacle_fields(self, event=None):
        obstacle = self._selected_obstacle()
        if obstacle is None:
            messagebox.showwarning("Obstacle", "Select an obstacle first.")
            return None
        self.record_history()
        obstacle_id = obstacle.get("obstacleId")
        next_obstacle = self._obstacle_from_form(existing_id=obstacle_id)
        obstacle.clear()
        obstacle.update(next_obstacle)
        self._after_obstacle_changed()
        return None

    def duplicate_selected_obstacle(self):
        obstacle = self._selected_obstacle()
        if obstacle is None:
            messagebox.showwarning("Obstacle", "Select an obstacle first.")
            return
        self.record_history()
        copied = self._copy_obstacle_with_new_id(obstacle)
        self._grid_obstacles().append(copied)
        self.selected_obstacle_index = len(self._grid_obstacles()) - 1
        self._after_obstacle_changed()

    def delete_selected_obstacle(self):
        index = self.selected_obstacle_index
        obstacles = self._grid_obstacles()
        if index is None or not (0 <= index < len(obstacles)):
            messagebox.showwarning("Obstacle", "Select an obstacle first.")
            return
        self.record_history()
        obstacles.pop(index)
        self.selected_obstacle_index = min(index, len(obstacles) - 1) if obstacles else None
        self.obstacle_custom_cells.clear()
        self._after_obstacle_changed()

    def use_selected_cells_for_obstacle(self):
        cells = set(getattr(self, "selected_grid_cells", set()) or set())
        if self.selected_cell:
            cells.add(self.selected_cell)
        if not cells:
            messagebox.showwarning("Obstacle", "Select one or more grid cells first.")
            return
        self.obstacle_custom_cells = cells
        self.obstacle_shape_type_var.set("CustomCells")
        self._set_obstacle_bounds_from_cells(cells)
        selected = self._selected_obstacle()
        if selected is not None:
            self.record_history()
            obstacle_id = selected.get("obstacleId")
            next_obstacle = self._obstacle_from_form(existing_id=obstacle_id)
            selected.clear()
            selected.update(next_obstacle)
            self._after_obstacle_changed()
        else:
            self._refresh_grid_button_states()

    def clear_obstacle_custom_cells(self):
        self.obstacle_custom_cells.clear()
        self._refresh_grid_button_states()

    def on_obstacle_tree_select(self, event=None):
        if not hasattr(self, "obstacle_tree"):
            return None
        selection = self.obstacle_tree.selection()
        if not selection:
            return None
        self.selected_obstacle_index = safe_int(str(selection[0]), 0)
        self._sync_obstacle_form_from_selection()
        self._refresh_grid_button_states()
        return None

    def on_obstacle_grid_click(self, row: int, col: int, event=None):
        self.selected_cell = (row, col)
        self.selected_grid_cells.clear()
        if self.selected_obstacle_index is None:
            self.obstacle_origin_row_var.set(row)
            self.obstacle_origin_col_var.set(col)
            if self.obstacle_shape_type_var.get() == "CustomCells":
                self.obstacle_custom_cells = {(row, col)}
            self.add_obstacle_from_form()
            self._update_selected_label()
            return "break"

        obstacle = self._selected_obstacle()
        if obstacle is None:
            return "break"
        self.record_history()
        if self.obstacle_shape_type_var.get() == "CustomCells" or obstacle.get("shape", {}).get("type") == "CustomCells":
            if (row, col) in self.obstacle_custom_cells:
                self.obstacle_custom_cells.remove((row, col))
            else:
                self.obstacle_custom_cells.add((row, col))
            if not self.obstacle_custom_cells:
                self.obstacle_custom_cells.add((row, col))
            self._set_obstacle_bounds_from_cells(self.obstacle_custom_cells)
            self.obstacle_shape_type_var.set("CustomCells")
        else:
            self.obstacle_origin_row_var.set(row)
            self.obstacle_origin_col_var.set(col)
        obstacle_id = obstacle.get("obstacleId")
        next_obstacle = self._obstacle_from_form(existing_id=obstacle_id)
        obstacle.clear()
        obstacle.update(next_obstacle)
        self._after_obstacle_changed()
        self._update_selected_label()
        return "break"

    def _after_obstacle_changed(self):
        self._refresh_obstacle_tree()
        self._sync_obstacle_form_from_selection()
        self._refresh_grid_button_states()
        self.refresh_json_preview()

    def _refresh_obstacle_tree(self):
        if not hasattr(self, "obstacle_tree"):
            return
        for item in self.obstacle_tree.get_children():
            self.obstacle_tree.delete(item)
        for index, obstacle in enumerate(self._grid_obstacles()):
            shape = obstacle.get("shape", {}) or {}
            origin = shape.get("origin", {}) or {}
            origin_text = f"{origin.get('row', 0)},{origin.get('column', 0)}"
            if obstacle.get("type") == "IceBlock":
                extra = f"hp {obstacle.get('hp', 1)}"
            elif obstacle.get("type") == "GlassBarrier":
                extra = f"{obstacle.get('direction', 'Right')} x{obstacle.get('length', 3)} {obstacle.get('color', '?')}"
            else:
                extra = f"{obstacle.get('direction', 'Right')} x{obstacle.get('length', 3)}"
            self.obstacle_tree.insert(
                "",
                "end",
                iid=str(index),
                values=(obstacle.get("type", ""), shape.get("type", "Rect"), origin_text, extra),
            )
        index = self.selected_obstacle_index
        if index is not None and 0 <= index < len(self._grid_obstacles()):
            self.obstacle_tree.selection_set(str(index))
            self.obstacle_tree.see(str(index))

    def _sync_obstacle_form_from_selection(self):
        if not hasattr(self, "obstacle_status_var"):
            return
        obstacle = self._selected_obstacle()
        if obstacle is None:
            self.obstacle_status_var.set("Select a cell to place or edit an obstacle.")
            return
        shape = obstacle.get("shape", {}) or {}
        origin = shape.get("origin", {}) or {}
        self.obstacle_type_var.set(obstacle.get("type", "IceBlock"))
        self.obstacle_shape_type_var.set(shape.get("type", "Rect"))
        self.obstacle_origin_row_var.set(safe_int(str(origin.get("row", 0)), 0))
        self.obstacle_origin_col_var.set(safe_int(str(origin.get("column", 0)), 0))
        self.obstacle_width_var.set(max(1, safe_int(str(shape.get("width", 1)), 1)))
        self.obstacle_height_var.set(max(1, safe_int(str(shape.get("height", 1)), 1)))
        self.obstacle_hp_var.set(max(1, safe_int(str(obstacle.get("hp", 1)), 1)))
        self.obstacle_direction_var.set(obstacle.get("direction", "Right"))
        self.obstacle_length_var.set(max(1, safe_int(str(obstacle.get("length", 3)), 3)))
        if obstacle.get("type") == "GlassBarrier":
            self.obstacle_glass_color_var.set(obstacle.get("color", "Blue"))
        self.obstacle_custom_cells = set(self._shape_cells(shape, default_size=1)) if shape.get("type") == "CustomCells" else set()
        self._refresh_choice_group("obstacle_type")
        self._refresh_choice_group("obstacle_direction")
        self.obstacle_status_var.set(f"Editing obstacle #{self.selected_obstacle_index + 1}: {obstacle.get('obstacleId')}")

    def _obstacle_from_form(self, existing_id: Optional[str] = None) -> Dict[str, Any]:
        obstacle_type = self.obstacle_type_var.get()
        origin_row = max(0, safe_int(str(self.obstacle_origin_row_var.get()), 0))
        origin_col = max(0, safe_int(str(self.obstacle_origin_col_var.get()), 0))
        if obstacle_type in ("LockBar", "GlassBarrier"):
            direction = self.obstacle_direction_var.get()
            length = max(1, safe_int(str(self.obstacle_length_var.get()), 3))
            shape = {
                "type": self._shape_type_for_lockbar(),
                "origin": {"row": origin_row, "column": origin_col},
                "width": 1 if direction in {"Up", "Down"} else length,
                "height": length if direction in {"Up", "Down"} else 1,
                "cells": [],
            }
            if obstacle_type == "GlassBarrier":
                return {
                    "obstacleId": existing_id or short_id("glass"),
                    "type": "GlassBarrier",
                    "direction": direction,
                    "length": length,
                    "color": self.obstacle_glass_color_var.get(),
                    "shape": shape,
                }
            return {
                "obstacleId": existing_id or short_id("lock"),
                "type": "LockBar",
                "direction": direction,
                "length": length,
                "shape": shape,
            }

        shape_type = self.obstacle_shape_type_var.get()
        width = max(1, safe_int(str(self.obstacle_width_var.get()), 1))
        height = max(1, safe_int(str(self.obstacle_height_var.get()), 1))
        cells: List[Dict[str, int]] = []
        if shape_type == "CustomCells":
            if not self.obstacle_custom_cells:
                self.obstacle_custom_cells = {(origin_row, origin_col)}
            self._set_obstacle_bounds_from_cells(self.obstacle_custom_cells)
            cells = [
                {"row": cell_row, "column": cell_col}
                for cell_row, cell_col in sorted(self.obstacle_custom_cells)
            ]
            origin_row = min(cell["row"] for cell in cells)
            origin_col = min(cell["column"] for cell in cells)
            width = max(cell["column"] for cell in cells) - origin_col + 1
            height = max(cell["row"] for cell in cells) - origin_row + 1

        return {
            "obstacleId": existing_id or short_id("ice"),
            "type": "IceBlock",
            "hp": max(1, safe_int(str(self.obstacle_hp_var.get()), 1)),
            "shape": {
                "type": shape_type,
                "origin": {"row": origin_row, "column": origin_col},
                "width": width,
                "height": height,
                "cells": cells,
            },
        }

    def _copy_obstacle_with_new_id(self, obstacle: Dict[str, Any]) -> Dict[str, Any]:
        id_prefix = {"LockBar": "lock", "GlassBarrier": "glass"}.get(obstacle.get("type"), "ice")
        copied = {
            "obstacleId": short_id(id_prefix),
            "type": obstacle.get("type"),
            "shape": {
                "type": obstacle.get("shape", {}).get("type", "Rect"),
                "origin": dict(obstacle.get("shape", {}).get("origin", {})),
                "width": obstacle.get("shape", {}).get("width", 1),
                "height": obstacle.get("shape", {}).get("height", 1),
                "cells": [dict(cell) for cell in obstacle.get("shape", {}).get("cells", [])],
            },
        }
        if obstacle.get("type") == "IceBlock":
            copied["hp"] = obstacle.get("hp", 1)
        if obstacle.get("type") in ("LockBar", "GlassBarrier"):
            copied["direction"] = obstacle.get("direction", "Right")
            copied["length"] = obstacle.get("length", 3)
        if obstacle.get("type") == "GlassBarrier":
            copied["color"] = obstacle.get("color", "None")
        return copied

    def _shape_type_for_lockbar(self) -> str:
        return "LineVertical" if self.obstacle_direction_var.get() in {"Up", "Down"} else "LineHorizontal"

    def _set_obstacle_bounds_from_cells(self, cells: Set[Tuple[int, int]]):
        if not cells:
            return
        min_row = min(row for row, _col in cells)
        min_col = min(col for _row, col in cells)
        max_row = max(row for row, _col in cells)
        max_col = max(col for _row, col in cells)
        self.obstacle_origin_row_var.set(min_row)
        self.obstacle_origin_col_var.set(min_col)
        self.obstacle_width_var.set(max_col - min_col + 1)
        self.obstacle_height_var.set(max_row - min_row + 1)

    def add_empty_group(self):
        self.record_history()
        groups = self._grid_groups()
        groups.append({
            "groupId": short_id("group"),
            "type": self.group_type_var.get(),
            "shooterIds": [],
        })
        self.selected_group_index = len(groups) - 1
        self._after_group_changed()

    def add_group_from_selected_cells(self):
        shooter_ids = self._selected_direct_shooter_ids()
        if not shooter_ids:
            messagebox.showwarning("Shooter Group", "Select one or more shooter cells first.")
            return
        self.record_history()
        groups = self._grid_groups()
        groups.append({
            "groupId": short_id("group"),
            "type": self.group_type_var.get(),
            "shooterIds": shooter_ids,
        })
        self.selected_group_index = len(groups) - 1
        self._after_group_changed()

    def add_selected_cells_to_group(self):
        group = self._selected_group()
        if group is None:
            self.add_group_from_selected_cells()
            return
        shooter_ids = self._selected_direct_shooter_ids()
        if not shooter_ids:
            messagebox.showwarning("Shooter Group", "Select one or more shooter cells first.")
            return
        self.record_history()
        current = list(group.get("shooterIds", []) or [])
        for shooter_id in shooter_ids:
            if shooter_id not in current:
                current.append(shooter_id)
        group["shooterIds"] = current
        self._after_group_changed()

    def apply_group_type_to_selection(self):
        group = self._selected_group()
        if group is None:
            self._refresh_choice_group("group_type")
            return
        self.record_history()
        group["type"] = self.group_type_var.get()
        self._after_group_changed()

    def clear_selected_group_members(self):
        group = self._selected_group()
        if group is None:
            messagebox.showwarning("Shooter Group", "Select a group first.")
            return
        self.record_history()
        group["shooterIds"] = []
        self._after_group_changed()

    def delete_selected_group(self):
        index = self.selected_group_index
        groups = self._grid_groups()
        if index is None or not (0 <= index < len(groups)):
            messagebox.showwarning("Shooter Group", "Select a group first.")
            return
        self.record_history()
        groups.pop(index)
        self.selected_group_index = min(index, len(groups) - 1) if groups else None
        self._after_group_changed()

    def prune_missing_group_members(self):
        valid_ids = {shooter_id for _row, _col, shooter_id in self._direct_shooter_id_entries()}
        changes = []
        for group in self._grid_groups():
            next_ids = [shooter_id for shooter_id in group.get("shooterIds", []) or [] if shooter_id in valid_ids]
            if next_ids != group.get("shooterIds", []):
                changes.append((group, next_ids))
        if changes:
            self.record_history()
            for group, next_ids in changes:
                group["shooterIds"] = next_ids
            self._after_group_changed()
        else:
            self._refresh_group_tree()

    def on_group_tree_select(self, event=None):
        if not hasattr(self, "group_tree"):
            return None
        selection = self.group_tree.selection()
        if not selection:
            return None
        self.selected_group_index = safe_int(str(selection[0]), 0)
        self._sync_group_form_from_selection()
        self._refresh_grid_button_states()
        return None

    def on_group_grid_click(self, row: int, col: int, event=None):
        self.selected_cell = (row, col)
        self.selected_grid_cells = {(row, col)}
        shooter_id = self._direct_shooter_id_at(row, col)
        if not shooter_id:
            self._update_selected_label()
            return "break"
        group = self._selected_group()
        if group is None:
            self.record_history()
            groups = self._grid_groups()
            groups.append({
                "groupId": short_id("group"),
                "type": self.group_type_var.get(),
                "shooterIds": [shooter_id],
            })
            self.selected_group_index = len(groups) - 1
        else:
            self.record_history()
            members = list(group.get("shooterIds", []) or [])
            if shooter_id in members:
                members.remove(shooter_id)
            else:
                members.append(shooter_id)
            group["shooterIds"] = members
        self._after_group_changed()
        self._update_selected_label()
        return "break"

    def _after_group_changed(self):
        self._refresh_group_tree()
        self._sync_group_form_from_selection()
        self._refresh_grid_button_states()
        self.refresh_json_preview()

    def _refresh_group_tree(self):
        if not hasattr(self, "group_tree"):
            return
        for item in self.group_tree.get_children():
            self.group_tree.delete(item)
        valid_ids = {shooter_id for _row, _col, shooter_id in self._direct_shooter_id_entries()}
        for index, group in enumerate(self._grid_groups()):
            members = list(group.get("shooterIds", []) or [])
            missing = [shooter_id for shooter_id in members if shooter_id not in valid_ids]
            member_text = ", ".join(members[:3])
            if len(members) > 3:
                member_text += f", +{len(members) - 3}"
            if missing:
                member_text += f" ({len(missing)} missing)"
            self.group_tree.insert(
                "",
                "end",
                iid=str(index),
                values=(group.get("type", "Connected"), len(members), member_text),
            )
        index = self.selected_group_index
        if index is not None and 0 <= index < len(self._grid_groups()):
            self.group_tree.selection_set(str(index))
            self.group_tree.see(str(index))

    def _sync_group_form_from_selection(self):
        if not hasattr(self, "group_status_var"):
            return
        group = self._selected_group()
        if group is None:
            self.group_status_var.set("Select shooter cells to build a group.")
            return
        self.group_type_var.set(group.get("type", "Connected"))
        self._refresh_choice_group("group_type")
        members = group.get("shooterIds", []) or []
        self.group_status_var.set(f"Editing group #{self.selected_group_index + 1}: {len(members)} shooter(s).")

    def grid_cell_frame_style(self, row: int, col: int, base: Tuple[str, int, int]) -> Tuple[str, int, int]:
        cell = (row, col)
        mode = self.editor_tool_mode.get() if hasattr(self, "editor_tool_mode") else "Cells"
        if mode == "Obstacles" and cell in self.obstacle_custom_cells:
            return "#22D3EE", 5, 5
        obstacle_indexes = self._obstacle_indexes_at(row, col)
        if self.selected_obstacle_index in obstacle_indexes:
            return "#F59E0B", 5, 5
        if obstacle_indexes:
            return "#60A5FA", 3, 3

        group_indexes = self._group_indexes_at(row, col)
        if self.selected_group_index in group_indexes:
            return "#C084FC", 5, 5
        if group_indexes:
            return "#7C3AED", 3, 3
        return base

    def grid_cell_extra_label(self, row: int, col: int) -> str:
        labels = []
        for index in self._obstacle_indexes_at(row, col):
            obstacle = self._grid_obstacles()[index]
            prefix = {"LockBar": "L", "GlassBarrier": "B"}.get(obstacle.get("type"), "I")
            labels.append(prefix + str(index + 1))
        for index in self._group_indexes_at(row, col):
            labels.append("G" + str(index + 1))
        return "\n" + " ".join(labels) if labels else ""

    def grid_cell_bg(self, row: int, col: int, base: str) -> str:
        entity = find_cell(self.level, row, col).get("entity")
        if entity is not None:
            return base
        if self.selected_obstacle_index in self._obstacle_indexes_at(row, col):
            return "#374151"
        if self._obstacle_indexes_at(row, col):
            return "#2F4858"
        return base

    def grid_cell_fg(self, row: int, col: int, base: str) -> str:
        if self._obstacle_indexes_at(row, col) or self._group_indexes_at(row, col):
            return "#FFFFFF"
        return base

    def draw_group_connectors(self):
        if not hasattr(self, "grid_canvas"):
            return
        canvas = self.grid_canvas
        try:
            canvas.delete("group_connector")
            self.update_idletasks()
            positions = self._direct_shooter_positions_by_id()
            for index, group in enumerate(self._grid_groups()):
                points = []
                for shooter_id in group.get("shooterIds", []) or []:
                    cell = positions.get(shooter_id)
                    if cell is None:
                        continue
                    frame = self.grid_button_frames.get(cell)
                    if frame is None:
                        continue
                    x = frame.winfo_rootx() - canvas.winfo_rootx() + frame.winfo_width() / 2
                    y = frame.winfo_rooty() - canvas.winfo_rooty() + frame.winfo_height() / 2
                    points.append((canvas.canvasx(x), canvas.canvasy(y)))
                if len(points) < 2:
                    continue
                color = "#C084FC" if index == self.selected_group_index else "#7C3AED"
                width = 4 if index == self.selected_group_index else 2
                for first, second in zip(points, points[1:]):
                    canvas.create_line(
                        first[0],
                        first[1],
                        second[0],
                        second[1],
                        fill=color,
                        width=width,
                        tags="group_connector",
                    )
        except tk.TclError:
            return

    def on_grid_right_click(self, row: int, col: int):
        mode = self.editor_tool_mode.get() if hasattr(self, "editor_tool_mode") else "Cells"
        if mode == "Obstacles":
            return self._remove_obstacle_at_cell(row, col)
        if mode == "Groups":
            return self._remove_group_member_at_cell(row, col)
        return super().on_grid_right_click(row, col)

    def clear_grid_cell(self, row: int, col: int):
        mode = self.editor_tool_mode.get() if hasattr(self, "editor_tool_mode") else "Cells"
        if mode == "Obstacles":
            return self._remove_obstacle_at_cell(row, col)
        if mode == "Groups":
            return self._remove_group_member_at_cell(row, col)
        return super().clear_grid_cell(row, col)

    def _remove_obstacle_at_cell(self, row: int, col: int):
        obstacle_indexes = self._obstacle_indexes_at(row, col)
        if not obstacle_indexes:
            return "break"
        index = self.selected_obstacle_index if self.selected_obstacle_index in obstacle_indexes else obstacle_indexes[0]
        self.selected_obstacle_index = index
        self._sync_obstacle_form_from_selection()
        obstacle = self._grid_obstacles()[index]
        shape = obstacle.get("shape", {}) or {}
        self.record_history()
        if shape.get("type") == "CustomCells":
            cells = set(self._shape_cells(shape, default_size=1))
            cells.discard((row, col))
            if cells:
                self.obstacle_custom_cells = cells
                self._set_obstacle_bounds_from_cells(cells)
                obstacle_id = obstacle.get("obstacleId")
                next_obstacle = self._obstacle_from_form(existing_id=obstacle_id)
                obstacle.clear()
                obstacle.update(next_obstacle)
            else:
                self._grid_obstacles().pop(index)
                self.selected_obstacle_index = None
        else:
            self._grid_obstacles().pop(index)
            self.selected_obstacle_index = None
        self._after_obstacle_changed()
        return "break"

    def _remove_group_member_at_cell(self, row: int, col: int):
        shooter_id = self._direct_shooter_id_at(row, col)
        if not shooter_id:
            return "break"
        group_indexes = self._group_indexes_at(row, col)
        if not group_indexes:
            return "break"
        index = self.selected_group_index if self.selected_group_index in group_indexes else group_indexes[0]
        group = self._grid_groups()[index]
        self.record_history()
        group["shooterIds"] = [member_id for member_id in group.get("shooterIds", []) or [] if member_id != shooter_id]
        self.selected_group_index = index
        self._after_group_changed()
        return "break"

    def _grid_obstacles(self) -> List[Dict[str, Any]]:
        return self.level.setdefault("grid", {}).setdefault("obstacles", [])

    def _grid_groups(self) -> List[Dict[str, Any]]:
        return self.level.setdefault("grid", {}).setdefault("shooterGroups", [])

    def _selected_obstacle(self) -> Optional[Dict[str, Any]]:
        index = self.selected_obstacle_index
        obstacles = self._grid_obstacles()
        if index is None or not (0 <= index < len(obstacles)):
            return None
        return obstacles[index]

    def _selected_group(self) -> Optional[Dict[str, Any]]:
        index = self.selected_group_index
        groups = self._grid_groups()
        if index is None or not (0 <= index < len(groups)):
            return None
        return groups[index]

    def _clamp_selected_obstacle_index(self):
        obstacles = self._grid_obstacles()
        if not obstacles:
            self.selected_obstacle_index = None
        elif self.selected_obstacle_index is None or self.selected_obstacle_index >= len(obstacles):
            self.selected_obstacle_index = 0

    def _clamp_selected_group_index(self):
        groups = self._grid_groups()
        if not groups:
            self.selected_group_index = None
        elif self.selected_group_index is None or self.selected_group_index >= len(groups):
            self.selected_group_index = 0

    def _obstacle_indexes_at(self, row: int, col: int) -> List[int]:
        result = []
        for index, obstacle in enumerate(self._grid_obstacles()):
            if (row, col) in self._obstacle_cells(obstacle):
                result.append(index)
        return result

    def _group_indexes_at(self, row: int, col: int) -> List[int]:
        shooter_id = self._direct_shooter_id_at(row, col)
        if not shooter_id:
            return []
        return [
            index
            for index, group in enumerate(self._grid_groups())
            if shooter_id in (group.get("shooterIds", []) or [])
        ]

    def _obstacle_cells(self, obstacle: Dict[str, Any]) -> Set[Tuple[int, int]]:
        if obstacle.get("type") in ("LockBar", "GlassBarrier"):
            return set(self._lockbar_cells(obstacle))
        return set(self._shape_cells(obstacle.get("shape", {}) or {}, default_size=3))

    def _lockbar_cells(self, obstacle: Dict[str, Any]) -> List[Tuple[int, int]]:
        shape = obstacle.get("shape", {}) or {}
        origin = shape.get("origin", {}) or {}
        row = safe_int(str(origin.get("row", 0)), 0)
        col = safe_int(str(origin.get("column", 0)), 0)
        cells = [(row, col)]
        for _index in range(1, max(1, safe_int(str(obstacle.get("length", 3)), 3))):
            row, col = self._offset_cell(row, col, obstacle.get("direction", "Right"))
            cells.append((row, col))
        return cells

    def _shape_cells(self, shape: Dict[str, Any], default_size: int = 1) -> List[Tuple[int, int]]:
        origin = shape.get("origin", {}) or {}
        origin_row = safe_int(str(origin.get("row", 0)), 0)
        origin_col = safe_int(str(origin.get("column", 0)), 0)
        shape_type = shape.get("type", "Rect")
        if shape_type == "CustomCells":
            return [
                (safe_int(str(cell.get("row", 0)), 0), safe_int(str(cell.get("column", 0)), 0))
                for cell in shape.get("cells", []) or []
            ]
        if shape_type == "Plus":
            return [
                (origin_row, origin_col),
                (origin_row - 1, origin_col),
                (origin_row + 1, origin_col),
                (origin_row, origin_col - 1),
                (origin_row, origin_col + 1),
            ]
        if shape_type == "LineHorizontal":
            width = max(1, safe_int(str(shape.get("width", default_size)), default_size))
            return [(origin_row, origin_col + offset) for offset in range(width)]
        if shape_type == "LineVertical":
            height = max(1, safe_int(str(shape.get("height", default_size)), default_size))
            return [(origin_row + offset, origin_col) for offset in range(height)]
        width = max(1, safe_int(str(shape.get("width", default_size)), default_size))
        height = max(1, safe_int(str(shape.get("height", default_size)), default_size))
        return [
            (origin_row + row_offset, origin_col + col_offset)
            for row_offset in range(height)
            for col_offset in range(width)
        ]

    def _offset_cell(self, row: int, col: int, direction: str) -> Tuple[int, int]:
        if direction == "Up":
            return row - 1, col
        if direction == "Down":
            return row + 1, col
        if direction == "Left":
            return row, col - 1
        return row, col + 1

    def _direct_shooter_id_at(self, row: int, col: int) -> Optional[str]:
        entity = find_cell(self.level, row, col).get("entity")
        if not entity or entity.get("type") != "Shooter":
            return None
        shooter_id = entity.get("shooter", {}).get("shooterId")
        return str(shooter_id) if shooter_id else None

    def _direct_shooter_id_entries(self) -> List[Tuple[int, int, str]]:
        entries = []
        for cell in self.level.get("grid", {}).get("cells", []) or []:
            row = safe_int(str(cell.get("row", 0)), 0)
            col = safe_int(str(cell.get("column", 0)), 0)
            entity = cell.get("entity")
            if entity and entity.get("type") == "Shooter":
                shooter_id = entity.get("shooter", {}).get("shooterId")
                if shooter_id:
                    entries.append((row, col, str(shooter_id)))
        return entries

    def _direct_shooter_positions_by_id(self) -> Dict[str, Tuple[int, int]]:
        return {shooter_id: (row, col) for row, col, shooter_id in self._direct_shooter_id_entries()}

    def _selected_direct_shooter_ids(self) -> List[str]:
        targets = set(getattr(self, "selected_grid_cells", set()) or set())
        if self.selected_cell:
            targets.add(self.selected_cell)
        result = []
        for row, col in sorted(targets):
            shooter_id = self._direct_shooter_id_at(row, col)
            if shooter_id and shooter_id not in result:
                result.append(shooter_id)
        return result

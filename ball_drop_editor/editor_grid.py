from __future__ import annotations

import tkinter as tk
from typing import Any, Dict, Optional, Tuple

from .level_data import entity_bg, entity_label, find_cell


class EditorGridMixin:
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
        self.mechanics_var.set(", ".join(self.level.get("mechanics", []) or []))

        gs = self.level.get("gateSystem", {})
        self.gate_count_var.set(gs.get("gateCount", 4))
        self.max_visible_var.set(gs.get("maxVisibleTrayPerGate", 4))

        self._refresh_grid_buttons()
        self._update_selected_label()
        self.refresh_gate_ui()
        self.refresh_gate_text()
        if hasattr(self, "refresh_obstacle_group_ui"):
            self.refresh_obstacle_group_ui()
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
                if hasattr(self, "grid_cell_frame_style"):
                    frame_bg, frame_padx, frame_pady = self.grid_cell_frame_style(r, c, (frame_bg, frame_padx, frame_pady))
                label = entity_label(entity)
                if hasattr(self, "grid_cell_extra_label"):
                    label += self.grid_cell_extra_label(r, c)
                bg = entity_bg(entity)
                if hasattr(self, "grid_cell_bg"):
                    bg = self.grid_cell_bg(r, c, bg)
                fg = self._grid_entity_fg(entity)
                if hasattr(self, "grid_cell_fg"):
                    fg = self.grid_cell_fg(r, c, fg)
                border = tk.Frame(
                    self.grid_inner,
                    bg=frame_bg,
                    padx=frame_padx,
                    pady=frame_pady,
                )
                border.grid(row=r, column=c, padx=2, pady=2)
                btn = tk.Button(
                    border,
                    text=label,
                    width=10,
                    height=4,
                    relief="flat",
                    bg=bg,
                    fg=fg,
                )
                btn.pack(fill="both", expand=True)
                btn.bind("<ButtonPress-1>", lambda e, rr=r, cc=c: self.start_grid_drag(e, rr, cc))
                btn.bind("<ButtonRelease-1>", self.end_grid_drag)
                btn.bind("<Double-Button-1>", lambda e, rr=r, cc=c: self.select_cell(rr, cc, paint=True))
                btn.bind("<Button-3>", lambda e, rr=r, cc=c: self.on_grid_right_click(rr, cc))
                btn.bind("<Double-Button-3>", lambda e, rr=r, cc=c: self.clear_grid_cell(rr, cc))
                self.grid_buttons[(r, c)] = btn
                self.grid_button_frames[(r, c)] = border
        if hasattr(self, "draw_group_connectors"):
            self.after_idle(self.draw_group_connectors)

    def _refresh_grid_button_states(self):
        if not self.grid_buttons:
            return
        for (row, col), btn in self.grid_buttons.items():
            cell = find_cell(self.level, row, col)
            entity = cell.get("entity")
            is_selected = self.selected_cell == (row, col) or (row, col) in self.selected_grid_cells
            frame_bg, frame_padx, frame_pady = self._grid_selection_frame_style(is_selected, entity)
            if hasattr(self, "grid_cell_frame_style"):
                frame_bg, frame_padx, frame_pady = self.grid_cell_frame_style(row, col, (frame_bg, frame_padx, frame_pady))
            label = entity_label(entity)
            if hasattr(self, "grid_cell_extra_label"):
                label += self.grid_cell_extra_label(row, col)
            bg = entity_bg(entity)
            if hasattr(self, "grid_cell_bg"):
                bg = self.grid_cell_bg(row, col, bg)
            fg = self._grid_entity_fg(entity)
            if hasattr(self, "grid_cell_fg"):
                fg = self.grid_cell_fg(row, col, fg)
            frame = self.grid_button_frames.get((row, col))
            if frame is not None:
                frame.configure(
                    bg=frame_bg,
                    padx=frame_padx,
                    pady=frame_pady,
                )
            btn.configure(
                text=label,
                bg=bg,
                fg=fg,
            )
        if hasattr(self, "draw_group_connectors"):
            self.after_idle(self.draw_group_connectors)

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
        mode = self.editor_tool_mode.get() if hasattr(self, "editor_tool_mode") else "Cells"
        if mode in {"Obstacles", "Groups"}:
            self.on_grid_cell_click(target[0], target[1], event)
            return
        if target == source:
            self.on_grid_cell_click(source[0], source[1], event)
            return
        if not self._swap_grid_cells(source, target):
            return
        self.selected_cell = target
        self.selected_grid_cells = {target} if self._grid_multi_shooter_select_enabled() else set()
        self._update_selected_label()
        self._refresh_grid_button_states()
        self.refresh_json_preview()

    def _swap_grid_cells(self, source: Tuple[int, int], target: Tuple[int, int]) -> bool:
        if source == target:
            return False
        source_cell = find_cell(self.level, *source)
        target_cell = find_cell(self.level, *target)
        source_entity = source_cell.get("entity")
        target_entity = target_cell.get("entity")
        if source_entity is None and target_entity is None:
            return True
        self.record_history()
        source_cell["entity"], target_cell["entity"] = target_entity, source_entity
        return True

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

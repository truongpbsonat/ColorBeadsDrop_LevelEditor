from __future__ import annotations

import copy
import tkinter as tk
from tkinter import messagebox
from typing import Any, Dict, List, Optional, Tuple

from .color_utils import color_text_hex
from .constants import ENTITY_TYPES
from .level_data import (
    entity_bg,
    entity_label,
    find_cell,
    make_shooter_entity,
    make_shooter_modifiers,
    make_tunnel_entity,
    make_wall_entity,
)
from .utils import safe_int, short_id


class EditorCellsMixin:
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
        return self._cell_editor_modifiers()

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
        self._update_selected_label()
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
        self._update_selected_label()
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
        special = next((modifier for modifier in modifiers if modifier.get("type") == "Special"), None)
        self.cell_edit_hidden_modifier.set(hidden is not None)
        self.cell_edit_ice_modifier.set(ice is not None)
        self.cell_edit_special_modifier.set(special is not None)
        if ice is not None:
            self.cell_edit_ice_hp.set(max(1, safe_int(str(ice.get("hp", 1)), 1)))
        self.update_cell_editor_modifier_state()

    def update_cell_editor_modifier_state(self):
        if not hasattr(self, "cell_edit_ice_hp_spin"):
            return
        state = "normal" if self.cell_edit_ice_modifier.get() else "disabled"
        self.cell_edit_ice_hp_spin.configure(state=state)

    def on_cell_editor_modifier_change(self):
        self.update_cell_editor_modifier_state()
        self.apply_modifier_button_change("Ice")

    def auto_apply_cell_editor(self, event=None):
        if self._syncing_cell_editor:
            return None
        if self.selected_cell:
            self.apply_cell_editor_to_selected(show_warning=False)
        return None

    def auto_apply_color_editor(self, event=None):
        if self._syncing_cell_editor:
            return None
        target = getattr(self, "_active_color_target", "cell")
        if target == "tray" and self.selected_tray_index is not None:
            self.apply_selected_layer_fields()
        elif target == "cell" and self.selected_cell:
            self.apply_cell_editor_to_selected(show_warning=False)
        return None

    def apply_modifier_button_change(self, modifier_type: str):
        if self._syncing_cell_editor:
            return None
        self.set_selected_modifier_enabled(
            modifier_type,
            self._cell_editor_modifier_var(modifier_type).get(),
        )
        return None

    def apply_ice_hp_change(self, event=None):
        if self._syncing_cell_editor:
            return None
        shooters = self._cell_editor_target_shooters()
        if not shooters:
            return None
        self.record_history()
        hp = max(1, safe_int(str(self.cell_edit_ice_hp.get()), 1))
        for shooter in shooters:
            modifiers = [copy.deepcopy(modifier) for modifier in shooter.get("modifiers", [])]
            ice = next((modifier for modifier in modifiers if modifier.get("type") == "Ice"), None)
            if ice is None:
                modifiers.append({"type": "Ice", "hp": hp})
                self.cell_edit_ice_modifier.set(True)
            else:
                ice["hp"] = hp
            shooter["modifiers"] = modifiers
        self.update_cell_editor_modifier_state()
        self._update_selected_label()
        self._refresh_grid_button_states()
        self._refresh_cell_tunnel_queue(self._selected_tunnel_queue_index())
        self.refresh_json_preview()
        return None

    def _cell_editor_modifiers(self) -> List[Dict[str, Any]]:
        return make_shooter_modifiers(
            hidden=self.cell_edit_hidden_modifier.get(),
            ice=self.cell_edit_ice_modifier.get(),
            ice_hp=max(1, safe_int(str(self.cell_edit_ice_hp.get()), 1)),
            special=self.cell_edit_special_modifier.get(),
        )

    def _cell_editor_shooter_payload(self, existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        shooter = copy.deepcopy(existing or {})
        shooter["shooterId"] = shooter.get("shooterId") or short_id("s_tunnel")
        shooter["colorId"] = self.cell_edit_color.get()
        shooter["capacity"] = max(1, safe_int(str(self.cell_edit_capacity.get()), 1))
        shooter["modifiers"] = self._cell_editor_modifiers()
        return shooter

    def _modifier_summary(self, modifiers: List[Dict[str, Any]]) -> str:
        labels = []
        for modifier in modifiers:
            if modifier.get("type") == "Hidden":
                labels.append("Hidden")
            elif modifier.get("type") == "Ice":
                labels.append(f"Ice {modifier.get('hp', 1)}")
            elif modifier.get("type") == "Special":
                labels.append("Special")
        return ", ".join(labels)

    def _selected_tunnel_entity(self) -> Optional[Dict[str, Any]]:
        if not self.selected_cell:
            return None
        entity = find_cell(self.level, *self.selected_cell).get("entity")
        if entity and entity.get("type") == "Tunnel":
            return entity
        return None

    def _selected_tunnel_queue_index(self) -> Optional[int]:
        return self.cell_edit_tunnel_queue_index

    def _refresh_cell_tunnel_queue(self, select_index: Optional[int] = None):
        if not hasattr(self, "tunnel_queue_grid"):
            return
        for child in self.tunnel_queue_grid.winfo_children():
            child.destroy()
        self.tunnel_queue_buttons.clear()
        self.tunnel_queue_button_frames.clear()

        entity = self._selected_tunnel_entity()
        if not entity:
            if hasattr(self, "tunnel_queue_panel"):
                self.tunnel_queue_panel.grid_remove()
            self.cell_edit_tunnel_queue_index = None
            return

        self.tunnel_queue_panel.grid()
        queue = entity.get("shooterQueue", [])
        if select_index is None:
            select_index = self.cell_edit_tunnel_queue_index
        for index, shooter in enumerate(queue):
            is_selected = select_index == index
            border = tk.Frame(
                self.tunnel_queue_grid,
                bg="#00E5FF" if is_selected else "#3A3A3A",
                padx=5 if is_selected else 1,
                pady=5 if is_selected else 1,
            )
            border.grid(row=index, column=0, sticky="ew", padx=2, pady=2)
            shooter_entity = {"type": "Shooter", "shooter": shooter}
            btn = tk.Button(
                border,
                text=f"#{index + 1}\n{entity_label(shooter_entity)}",
                width=10,
                height=4,
                relief="flat",
                bg=entity_bg(shooter_entity),
                fg=self._grid_entity_fg(shooter_entity),
            )
            btn.pack(fill="both", expand=True)
            btn.bind("<ButtonPress-1>", lambda e, idx=index: self.start_tunnel_queue_drag(idx))
            btn.bind("<ButtonRelease-1>", lambda e, idx=index: self.end_tunnel_queue_drag(e, idx))
            btn.bind("<Double-Button-1>", lambda e: self.update_tunnel_queue_shooter())
            btn.bind("<Button-3>", lambda e, idx=index: self.remove_tunnel_queue_shooter(idx))
            self.tunnel_queue_buttons[index] = btn
            self.tunnel_queue_button_frames[index] = border

        if select_index is not None and 0 <= select_index < len(queue):
            self.cell_edit_tunnel_queue_index = select_index
            self._load_tunnel_queue_shooter_to_editor(select_index)
        else:
            self.cell_edit_tunnel_queue_index = None

    def _load_tunnel_queue_shooter_to_editor(self, index: int):
        entity = self._selected_tunnel_entity()
        if not entity:
            return
        queue = entity.get("shooterQueue", [])
        if not (0 <= index < len(queue)):
            return
        shooter = queue[index]
        self.cell_edit_tunnel_queue_index = index
        was_syncing = self._syncing_cell_editor
        self._syncing_cell_editor = True
        try:
            self.cell_edit_color.set(shooter.get("colorId", "Blue"))
            self.cell_edit_capacity.set(max(1, safe_int(str(shooter.get("capacity", 9)), 9)))
            self._set_cell_editor_modifiers(shooter.get("modifiers", []))
            self._refresh_choice_group("cell_edit_color")
        finally:
            self._syncing_cell_editor = was_syncing

    def select_tunnel_queue_shooter(self, index: int):
        self._active_color_target = "cell"
        self.cell_edit_tunnel_queue_index = index
        self._refresh_cell_tunnel_queue(index)

    def start_tunnel_queue_drag(self, index: int):
        self.tunnel_queue_drag_index = index

    def end_tunnel_queue_drag(self, event, index: int):
        if self.tunnel_queue_drag_index is None:
            return
        source = self.tunnel_queue_drag_index
        self.tunnel_queue_drag_index = None
        target = self._tunnel_queue_index_from_widget(self.winfo_containing(event.x_root, event.y_root))
        if target is None or target == source:
            self.select_tunnel_queue_shooter(index)
            return
        self.swap_tunnel_queue_shooters(source, target)

    def _tunnel_queue_index_from_widget(self, widget) -> Optional[int]:
        while widget is not None:
            for index, btn in self.tunnel_queue_buttons.items():
                if widget == btn or widget == self.tunnel_queue_button_frames.get(index):
                    return index
            widget = getattr(widget, "master", None)
        return None

    def on_tunnel_queue_select(self, event=None):
        index = self._selected_tunnel_queue_index()
        if index is not None:
            self.select_tunnel_queue_shooter(index)
        return None

    def _set_cell_editor_modifiers(self, modifiers: List[Dict[str, Any]]):
        hidden = next((modifier for modifier in modifiers if modifier.get("type") == "Hidden"), None)
        ice = next((modifier for modifier in modifiers if modifier.get("type") == "Ice"), None)
        special = next((modifier for modifier in modifiers if modifier.get("type") == "Special"), None)
        self.cell_edit_hidden_modifier.set(hidden is not None)
        self.cell_edit_ice_modifier.set(ice is not None)
        self.cell_edit_special_modifier.set(special is not None)
        if ice is not None:
            self.cell_edit_ice_hp.set(max(1, safe_int(str(ice.get("hp", 1)), 1)))
        self.update_cell_editor_modifier_state()

    def _sync_cell_editor_from_selection(self, show_warning: bool = False):
        if not hasattr(self, "cell_editor_status_var"):
            return
        was_syncing = self._syncing_cell_editor
        self._syncing_cell_editor = True
        try:
            if not self.selected_cell:
                self.cell_editor_status_var.set("Select a shooter or tunnel cell to edit.")
                self.cell_edit_tunnel_queue_index = None
                self._refresh_cell_tunnel_queue(None)
                return

            row, col = self.selected_cell
            entity = find_cell(self.level, row, col).get("entity")
            if self._is_shooter_entity(entity):
                self.cell_edit_entity_type.set("Shooter")
                shooter = entity.get("shooter", {})
                self.cell_edit_color.set(shooter.get("colorId", "Blue"))
                self.cell_edit_capacity.set(max(1, safe_int(str(shooter.get("capacity", 9)), 9)))
                self._set_cell_editor_modifiers(shooter.get("modifiers", []))
                self.cell_edit_tunnel_queue_index = None
                self.cell_editor_status_var.set(f"Editing shooter at row={row}, column={col}.")
            elif entity and entity.get("type") == "Tunnel":
                self.cell_edit_entity_type.set("Tunnel")
                self.cell_edit_tunnel_direction.set(entity.get("outputDirection", "Up"))
                queue = entity.get("shooterQueue", [])
                if queue:
                    current_index = self.cell_edit_tunnel_queue_index
                    self.cell_edit_tunnel_queue_index = current_index if current_index is not None and 0 <= current_index < len(queue) else 0
                else:
                    self.cell_edit_tunnel_queue_index = None
                self.cell_editor_status_var.set(f"Editing tunnel at row={row}, column={col}.")
            else:
                entity_name = entity.get("type") if entity else "Empty"
                self.cell_edit_entity_type.set(entity_name if entity_name in ENTITY_TYPES else "Empty")
                self.cell_edit_tunnel_queue_index = None
                self.cell_editor_status_var.set(f"Selected cell is {entity_name}. Choose an entity type to edit this cell.")

            self._refresh_choice_group("cell_edit_entity")
            self._refresh_choice_group("cell_edit_color")
            self._refresh_choice_group("cell_edit_tunnel_direction")
            self._refresh_cell_tunnel_queue(self.cell_edit_tunnel_queue_index)
        finally:
            self._syncing_cell_editor = was_syncing

    def load_selected_cell_to_editor(self):
        if not self.selected_cell:
            messagebox.showwarning("Cell Tool", "Select a grid cell first.")
            return
        self._sync_cell_editor_from_selection(show_warning=True)

    def apply_cell_editor_to_selected(self, show_warning: bool = True):
        targets = self._selected_grid_targets()
        if not targets:
            if show_warning:
                messagebox.showwarning("No Cell", "Select a grid cell first.")
            return

        entity_type = self.cell_edit_entity_type.get()
        modifiers = self._cell_editor_modifiers()
        self.record_history()
        queue_index = self._selected_tunnel_queue_index()
        for row, col in targets:
            cell = find_cell(self.level, row, col)
            entity = cell.get("entity")
            if entity_type == "Empty":
                cell["entity"] = None
            elif entity_type == "Wall":
                cell["entity"] = make_wall_entity(row, col)
            elif entity_type == "Shooter":
                if not self._is_shooter_entity(entity):
                    entity = make_shooter_entity(row, col, self.cell_edit_color.get(), max(1, safe_int(str(self.cell_edit_capacity.get()), 1)), modifiers)
                    cell["entity"] = entity
                shooter = entity["shooter"]
                shooter["colorId"] = self.cell_edit_color.get()
                shooter["capacity"] = max(1, safe_int(str(self.cell_edit_capacity.get()), 1))
                shooter["modifiers"] = copy.deepcopy(modifiers)
            elif entity_type == "Tunnel":
                if not (entity and entity.get("type") == "Tunnel"):
                    entity = make_tunnel_entity(
                        row,
                        col,
                        self.cell_edit_tunnel_direction.get(),
                        f"{self.cell_edit_color.get()}:{max(1, safe_int(str(self.cell_edit_capacity.get()), 1))}",
                        modifiers,
                    )
                    cell["entity"] = entity
                queue = entity.setdefault("shooterQueue", [])
                entity["outputDirection"] = self.cell_edit_tunnel_direction.get()
                if queue_index is not None and 0 <= queue_index < len(queue):
                    queue[queue_index] = self._cell_editor_shooter_payload(queue[queue_index])
                elif not queue:
                    queue.append(self._cell_editor_shooter_payload())

        self._update_selected_label()
        self._refresh_grid_button_states()
        self._refresh_cell_tunnel_queue(queue_index)
        self.refresh_json_preview()

    def _require_selected_tunnel(self) -> Optional[Dict[str, Any]]:
        entity = self._selected_tunnel_entity()
        if not entity:
            messagebox.showwarning("Tunnel", "Select a tunnel cell first.")
            return None
        return entity

    def add_tunnel_queue_shooter(self):
        entity = self._require_selected_tunnel()
        if not entity:
            return
        self.record_history()
        queue = entity.setdefault("shooterQueue", [])
        queue.append(self._cell_editor_shooter_payload())
        new_index = len(queue) - 1
        self._refresh_cell_tunnel_queue(new_index)
        self._update_selected_label()
        self._refresh_grid_button_states()
        self.refresh_json_preview()

    def update_tunnel_queue_shooter(self):
        entity = self._require_selected_tunnel()
        if not entity:
            return
        index = self._selected_tunnel_queue_index()
        queue = entity.setdefault("shooterQueue", [])
        if index is None or not (0 <= index < len(queue)):
            messagebox.showwarning("Tunnel", "Select a shooter in the tunnel list first.")
            return
        self.record_history()
        queue[index] = self._cell_editor_shooter_payload(queue[index])
        self._refresh_cell_tunnel_queue(index)
        self._update_selected_label()
        self._refresh_grid_button_states()
        self.refresh_json_preview()

    def remove_tunnel_queue_shooter(self, index: Optional[int] = None):
        entity = self._require_selected_tunnel()
        if not entity:
            return
        if index is None:
            index = self._selected_tunnel_queue_index()
        queue = entity.setdefault("shooterQueue", [])
        if index is None or not (0 <= index < len(queue)):
            messagebox.showwarning("Tunnel", "Select a shooter in the tunnel list first.")
            return
        self.record_history()
        queue.pop(index)
        next_index = min(index, len(queue) - 1) if queue else None
        self._refresh_cell_tunnel_queue(next_index)
        self._update_selected_label()
        self._refresh_grid_button_states()
        self.refresh_json_preview()

    def swap_tunnel_queue_shooters(self, source: int, target: int):
        entity = self._require_selected_tunnel()
        if not entity:
            return
        queue = entity.setdefault("shooterQueue", [])
        if not (0 <= source < len(queue) and 0 <= target < len(queue)):
            return
        self.record_history()
        queue[source], queue[target] = queue[target], queue[source]
        self._refresh_cell_tunnel_queue(target)
        self._update_selected_label()
        self._refresh_grid_button_states()
        self.refresh_json_preview()

    def move_tunnel_queue_shooter(self, direction: int):
        entity = self._require_selected_tunnel()
        if not entity:
            return
        index = self._selected_tunnel_queue_index()
        queue = entity.setdefault("shooterQueue", [])
        if index is None or not (0 <= index < len(queue)):
            messagebox.showwarning("Tunnel", "Select a shooter in the tunnel list first.")
            return
        target = index + direction
        if not (0 <= target < len(queue)):
            return
        self.record_history()
        queue[index], queue[target] = queue[target], queue[index]
        self._refresh_cell_tunnel_queue(target)
        self._update_selected_label()
        self._refresh_grid_button_states()
        self.refresh_json_preview()

    def _cell_editor_target_shooters(self) -> List[Dict[str, Any]]:
        entity = self._selected_tunnel_entity()
        index = self._selected_tunnel_queue_index()
        if entity and index is not None:
            queue = entity.get("shooterQueue", [])
            if 0 <= index < len(queue):
                return [queue[index]]
        return self._selected_shooter_data()

    def remove_cell_editor_modifiers(self):
        shooters = self._cell_editor_target_shooters()
        if not shooters:
            messagebox.showwarning("No Shooter", "Select a shooter cell or a tunnel shooter first.")
            return
        self.record_history()
        for shooter in shooters:
            shooter["modifiers"] = []
        self._update_selected_label()
        self._refresh_grid_button_states()
        self._refresh_cell_tunnel_queue(self._selected_tunnel_queue_index())
        self.refresh_json_preview()

    def toggle_selected_modifier(self, modifier_type: str):
        shooters = self._cell_editor_target_shooters()
        enabled = not any(
            any(modifier.get("type") == modifier_type for modifier in shooter.get("modifiers", []))
            for shooter in shooters
        )
        self.set_selected_modifier_enabled(modifier_type, enabled)

    def set_selected_modifier_enabled(self, modifier_type: str, enabled: bool):
        shooters = self._cell_editor_target_shooters()
        if not shooters:
            messagebox.showwarning("No Shooter", "Select a shooter cell or a tunnel with queued shooters first.")
            return

        self.record_history()
        for shooter in shooters:
            modifiers = [copy.deepcopy(modifier) for modifier in shooter.get("modifiers", [])]
            existing = any(modifier.get("type") == modifier_type for modifier in modifiers)
            if not enabled and existing:
                modifiers = [modifier for modifier in modifiers if modifier.get("type") != modifier_type]
            elif enabled and not existing and modifier_type == "Hidden":
                modifiers.append({"type": "Hidden"})
            elif enabled and not existing and modifier_type == "Ice":
                modifiers.append({
                    "type": "Ice",
                    "hp": max(1, safe_int(str(self.cell_edit_ice_hp.get()), 1)),
                })
            elif enabled and not existing and modifier_type == "Special":
                modifiers.append({"type": "Special"})
            shooter["modifiers"] = modifiers

        if modifier_type == "Hidden":
            self.cell_edit_hidden_modifier.set(enabled)
        elif modifier_type == "Ice":
            self.cell_edit_ice_modifier.set(enabled)
            self.update_cell_editor_modifier_state()
        elif modifier_type == "Special":
            self.cell_edit_special_modifier.set(enabled)
        self._update_selected_label()
        self._refresh_grid_button_states()
        self._refresh_cell_tunnel_queue(self._selected_tunnel_queue_index())
        self.refresh_json_preview()

    def _cell_editor_modifier_var(self, modifier_type: str) -> tk.BooleanVar:
        if modifier_type == "Hidden":
            return self.cell_edit_hidden_modifier
        if modifier_type == "Special":
            return self.cell_edit_special_modifier
        return self.cell_edit_ice_modifier

    def _grid_entity_fg(self, entity: Optional[Dict[str, Any]]) -> str:
        if entity and entity.get("type") == "Shooter":
            return color_text_hex(entity.get("shooter", {}).get("colorId", "None"))
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
            self._sync_cell_editor_from_selection(show_warning=False)
            return
        row, col = self.selected_cell
        ent = find_cell(self.level, row, col).get("entity")
        selected_count = len(self.selected_grid_cells) if self._grid_multi_shooter_select_enabled() else 0
        if selected_count > 1:
            self.selected_label.configure(text=f"Selected: {selected_count} cells; active row={row}, column={col}")
        else:
            self.selected_label.configure(text=f"Selected: row={row}, column={col}, entity={ent.get('type') if ent else 'Empty'}")
        self._sync_cell_editor_from_selection(show_warning=False)

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
            self.selected_grid_cells = set(targets)
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

    def wall_selected_cell(self):
        targets = self._selected_grid_targets()
        if not targets:
            messagebox.showwarning("No Cell", "Select a grid cell first.")
            return
        self.record_history()
        for row, col in targets:
            find_cell(self.level, row, col)["entity"] = make_wall_entity(row, col)
        if self._grid_multi_shooter_select_enabled():
            self.selected_grid_cells = set(targets)
        self._update_selected_label()
        self._refresh_grid_button_states()
        self.refresh_json_preview()

    def select_cell(self, row: int, col: int, paint: bool = False, additive: bool = False):
        self._active_color_target = "cell"
        self.selected_cell = (row, col)
        cell = find_cell(self.level, row, col)
        ent = cell.get("entity")
        if self._grid_multi_shooter_select_enabled():
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
        mode = self.editor_tool_mode.get() if hasattr(self, "editor_tool_mode") else "Cells"
        if mode == "Obstacles" and hasattr(self, "on_obstacle_grid_click"):
            return self.on_obstacle_grid_click(row, col, event)
        if mode == "Groups" and hasattr(self, "on_group_grid_click"):
            return self.on_group_grid_click(row, col, event)
        multi_shooter = self._grid_multi_shooter_select_enabled()
        additive = multi_shooter and event is not None and self._is_multi_select_event(event)
        paint_option = getattr(self, "grid_paint_on_click_var", None)
        paint_on_click = bool(paint_option and paint_option.get()) and not additive
        self.select_cell(row, col, paint=paint_on_click, additive=additive)

    def _apply_brush_to_cell(self, row: int, col: int):
        btype = self.cell_edit_entity_type.get()
        cell = find_cell(self.level, row, col)
        if btype == "Empty":
            cell["entity"] = None
        elif btype == "Shooter":
            cell["entity"] = make_shooter_entity(
                row,
                col,
                self.cell_edit_color.get(),
                max(1, safe_int(str(self.cell_edit_capacity.get()), 1)),
                self._brush_modifiers(),
            )
        elif btype == "Wall":
            cell["entity"] = make_wall_entity(row, col)
        elif btype == "Tunnel":
            queue_text = f"{self.cell_edit_color.get()}:{max(1, safe_int(str(self.cell_edit_capacity.get()), 1))}"
            cell["entity"] = make_tunnel_entity(
                row,
                col,
                self.cell_edit_tunnel_direction.get(),
                queue_text,
                self._brush_modifiers(),
            )

    def paint_cell(self, row: int, col: int):
        self.record_history()
        self._apply_brush_to_cell(row, col)
        if self._grid_multi_shooter_select_enabled():
            self.selected_grid_cells.add((row, col))
        self._update_selected_label()
        self._refresh_grid_button_states()
        self.refresh_json_preview()

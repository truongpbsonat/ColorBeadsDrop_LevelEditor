from __future__ import annotations

import copy
import tkinter as tk
from typing import Any, Dict, List, Optional, Set, Tuple

from .constants import BALL_COLORS, COLOR_HEX, TRAY_ICE_DEFAULT_HP
from .gate_text import gates_to_text, parse_gate_text
from .level_data import make_tray_modifiers
from .utils import safe_int, short_id


class EditorGateMixin:
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
        was_syncing = self._syncing_gate_direct_controls
        self._syncing_gate_direct_controls = True
        try:
            gate = self._get_gate_by_index(self.selected_gate_index)
            trays = gate.get("trayQueue", []) if gate else []
            if self.selected_tray_index is None or not trays:
                self.gate_selection_label.configure(text=self._selection_summary())
                self.selected_tray_id_var.set("")
                self.selected_tray_ice_modifier.set(False)
                self.selected_tray_ice_hp.set(TRAY_ICE_DEFAULT_HP)
                self.update_selected_tray_modifier_state()
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
            ice_modifier = self._tray_ice_modifier(tray)
            self.gate_selection_label.configure(
                text=f"{self._selection_summary()} / Layer {self.selected_layer_index}"
            )
            self.selected_tray_id_var.set(tray.get("trayId", ""))
            self.selected_tray_ice_modifier.set(ice_modifier is not None)
            self.selected_tray_ice_hp.set(
                max(1, safe_int(str(ice_modifier.get("hp", TRAY_ICE_DEFAULT_HP)), TRAY_ICE_DEFAULT_HP))
                if ice_modifier is not None else TRAY_ICE_DEFAULT_HP
            )
            self.update_selected_tray_modifier_state()
            self.selected_layer_spin.configure(to=max(0, len(layers) - 1))
            self.selected_layer_var.set(self.selected_layer_index)
            layer_color = layer.get("colorId", "Blue")
            self.selected_layer_color_var.set(layer_color)
            if hasattr(self, "cell_edit_color") and layer_color in BALL_COLORS and layer_color != "None":
                self.cell_edit_color.set(layer_color)
                self._refresh_choice_group("cell_edit_color")
            self.selected_layer_count_var.set(max(1, safe_int(str(layer.get("requiredCount", 3)), 3)))
        finally:
            self._syncing_gate_direct_controls = was_syncing

    def _default_tray_layer(self) -> Dict[str, Any]:
        color = self.cell_edit_color.get() if hasattr(self, "cell_edit_color") else "Blue"
        if color not in BALL_COLORS or color == "None":
            color = "Blue"
        return {"colorId": color, "requiredCount": 3}

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

    def _tray_ice_modifier(self, tray: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not tray:
            return None
        return next((modifier for modifier in tray.get("modifiers", []) if modifier.get("type") == "Ice"), None)

    def _selected_tray_modifiers(self) -> List[Dict[str, Any]]:
        return make_tray_modifiers(
            ice=self.selected_tray_ice_modifier.get(),
            ice_hp=max(1, safe_int(str(self.selected_tray_ice_hp.get()), TRAY_ICE_DEFAULT_HP)),
        )

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
            self._draw_gate_column(canvas, x, top_y, gate_width, base_y, base_height, tray_height, tray_gap, gate, max_visible, max_rows)

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
        max_rows: int,
    ):
        trays = gate.get("trayQueue", [])
        # Mọi cột dùng chung chiều cao bằng cột cao nhất (max_rows) để toggle
        # "dồn tray về cổng" luôn có tác dụng, không phụ thuộc Max Tray.
        visible_rows = max(max_rows, len(trays))
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

        # Khi bật "dồn tray về cổng", các tray được đẩy xuống sát cổng (đáy) giống
        # game thực tế, ô trống dồn lên trên. Mặc định tray neo ở phía trên.
        stack_to_gate = getattr(self, "tray_stack_to_gate_var", None)
        push_to_gate = bool(stack_to_gate.get()) if stack_to_gate is not None else False
        slot_offset = (visible_rows - len(trays)) if push_to_gate else 0

        for slot in range(visible_rows):
            tray_y = base_y - (visible_rows - slot) * (tray_height + tray_gap) + tray_gap
            tray_index = slot - slot_offset
            tray = trays[tray_index] if 0 <= tray_index < len(trays) else None
            self._draw_tray_block(canvas, x, tray_y, width, tray_height, tray, gate_index, tray_index if tray else None)

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

        ice_modifier = self._tray_ice_modifier(tray)
        if ice_modifier is not None:
            hp = max(1, safe_int(str(ice_modifier.get("hp", TRAY_ICE_DEFAULT_HP)), TRAY_ICE_DEFAULT_HP))
            self._create_round_rect(
                canvas,
                x + width - 28,
                y + height - 13,
                x + width - 4,
                y + height - 3,
                4,
                fill="#DFF8FF",
                outline="#72D7F7",
                width=1,
            )
            canvas.create_text(x + width - 16, y + height - 8, text=f"I{hp}", fill="#0F3E5E", font=("Arial", 7, "bold"))

    def _is_multi_select_event(self, event) -> bool:
        state = getattr(event, "state", 0)
        return bool(state & 0x0001 or state & 0x0004)

    def _select_gate_area(self, gate_index: int, additive: bool):
        self._active_color_target = "gate"
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
        self._active_color_target = "tray"
        # Selecting a tray makes the tray the active edit target. Drop any grid-cell
        # selection so a stray cell apply cannot push the tray color into a shooter.
        had_cell_selection = self.selected_cell is not None or bool(self.selected_grid_cells)
        self.selected_cell = None
        self.selected_grid_cells.clear()
        if had_cell_selection and hasattr(self, "_refresh_grid_button_states"):
            self._refresh_grid_button_states()
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
        self._active_color_target = "tray"
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

    def on_selected_tray_modifier_change(self):
        self.update_selected_tray_modifier_state()
        self.apply_selected_tray_modifiers()

    def apply_selected_tray_modifiers(self, event=None):
        if self._syncing_gate_direct_controls:
            return None
        targets = self._selected_tray_targets()
        if not targets:
            return None

        modifiers = self._selected_tray_modifiers()
        pending = []
        for tray_ref in targets:
            tray = self._get_tray_by_ref(tray_ref)
            if tray is not None and tray.get("modifiers", []) != modifiers:
                pending.append(tray_ref)

        if not pending:
            return None

        self.record_history()
        for tray_ref in pending:
            tray = self._get_tray_by_ref(tray_ref)
            if tray is not None:
                tray["modifiers"] = copy.deepcopy(modifiers)
        self.refresh_gate_direct_controls()
        self.draw_gate_preview()
        self.refresh_gate_outputs()
        return None

    def remove_selected_tray_modifiers(self):
        targets = self._selected_tray_targets()
        if not targets:
            return

        pending = []
        for tray_ref in targets:
            tray = self._get_tray_by_ref(tray_ref)
            if tray is not None and tray.get("modifiers"):
                pending.append(tray_ref)

        if not pending:
            self.selected_tray_ice_modifier.set(False)
            self.update_selected_tray_modifier_state()
            return

        self.record_history()
        for tray_ref in pending:
            tray = self._get_tray_by_ref(tray_ref)
            if tray is not None:
                tray["modifiers"] = []
        self.selected_tray_ice_modifier.set(False)
        self.selected_tray_ice_hp.set(TRAY_ICE_DEFAULT_HP)
        self.update_selected_tray_modifier_state()
        self.refresh_gate_direct_controls()
        self.draw_gate_preview()
        self.refresh_gate_outputs()

    def apply_selected_layer_fields(self):
        targets = self._selected_tray_targets()
        if not targets:
            return
        color = self.cell_edit_color.get() if hasattr(self, "cell_edit_color") else self.selected_layer_color_var.get()
        if color not in BALL_COLORS or color == "None":
            color = "Blue"
        self.selected_layer_color_var.set(color)
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
                "layers": [self._default_tray_layer()],
                "modifiers": []
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
            "layers": [{"colorId": "Blue", "requiredCount": 3}],
            "modifiers": []
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

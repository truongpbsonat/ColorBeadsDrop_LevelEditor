from __future__ import annotations

import json
from typing import Dict, List, Tuple

from .constants import BALL_COLORS
from .utils import safe_int
from .validator import LevelValidator


class EditorValidationMixin:
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
        self._update_level_save_status()
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

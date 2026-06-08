from __future__ import annotations

import copy
import json
from tkinter import filedialog, messagebox
from typing import Any, Dict

from .level_data import normalize_runtime_level
from .level_generator import build_config_from_template, load_template_folder, select_template_for_config
from .level_tester_score import SolverScoreAdapter
from .utils import safe_float
from .validator import LevelValidator


class LevelGeneratorWindowSourceMixin:
    def use_current_as_template(self) -> None:
        self.template_level = copy.deepcopy(getattr(self.master, "level", {}) or {})
        self.template_levels = [self.template_level] if self.template_level else []
        self.mode_var.set("Template Folder")
        self._apply_template_to_fields()
        self._log("Loaded current editor level as generator template.")

    def load_template(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose template level JSON",
            filetypes=(("JSON files", "*.json"), ("All files", "*.*")),
        )
        if not path:
            return

        with open(path, "r", encoding="utf-8") as fh:
            self.template_level = json.load(fh)
        self.template_levels = [self.template_level]
        self.mode_var.set("Template Folder")
        self._apply_template_to_fields()
        self._log(f"Loaded template: {path}")

    def load_reference_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose reference level JSON",
            filetypes=(("JSON files", "*.json"), ("All files", "*.*")),
        )
        if path:
            self._load_reference_path(path)

    def _load_reference_path(self, path: str) -> None:
        with open(path, "r", encoding="utf-8") as fh:
            level = json.load(fh)
        normalize_runtime_level(level)
        self.reference_level = copy.deepcopy(level)
        self.reference_file_var.set(path)
        self.mode_var.set("Reference Level File")

        self._apply_reference_to_fields(level)
        errors, warnings = LevelValidator().validate(level)
        for error in errors[:5]:
            self._log(f"REFERENCE ERROR: {error}")
        for warning in warnings[:5]:
            self._log(f"REFERENCE WARN: {warning}")

        adapter = SolverScoreAdapter(time_budget=max(0.1, safe_float(str(self.budget_var.get()), 20.0)))
        score = adapter.score_level(level)
        self.reference_score = score
        if score.status == "PASS" and score.per_click_scores:
            self.reference_curve_targets = [item.score for item in score.per_click_scores]
            phase_rows = self._reference_phase_rows(score)
            self._replace_phase_rows(phase_rows)
            self._log(
                f"Loaded reference: {path}. Source solve=PASS, colors={self.color_count_var.get()}, "
                f"clicks={len(score.per_click_scores)}, phases={len(phase_rows)}."
            )
        else:
            self.reference_curve_targets = []
            self._log(
                f"Loaded reference: {path}. Source solve={score.status}; curve cloning requires a PASS source."
            )
        self._sync_source_state()
        self._sync_color_state()

    def _apply_reference_to_fields(self, level: Dict[str, Any]) -> None:
        config = build_config_from_template(level, self._build_config())
        self.rows_var.set(config.rows)
        self.cols_var.set(config.cols)
        self.gates_var.set(config.gate_count)
        self.visible_var.set(config.max_visible_tray_per_gate)
        self.time_var.set(config.time)
        self.difficulty_var.set(config.difficulty)
        self.shooter_count_var.set(config.shooter_count)
        self.wall_count_var.set(config.wall_count)
        colors = self._level_colors(level)
        self.color_count_var.set(max(1, len(colors)))
        self.color_mode_var.set("Manual")
        for color, var in self.manual_color_vars.items():
            var.set(color in colors)
        self.capacity_var.set(config.shooter_capacity)
        self.tray_unit_var.set(self._estimate_tray_unit(level))

    def choose_template_folder(self) -> None:
        folder = filedialog.askdirectory(title="Choose template folder")
        if folder:
            self.template_folder_var.set(folder)
            self.mode_var.set("Template Folder")
            self.analyze_templates()

    def analyze_templates(self) -> None:
        folder = self.template_folder_var.get().strip()
        self.template_levels = load_template_folder(folder)
        if not self.template_levels:
            self._log(f"No JSON templates found in: {folder}")
            return
        selected = select_template_for_config(self.template_levels, self._build_config())
        self.template_level = selected
        self._apply_template_to_fields()
        self._log(f"Analyzed {len(self.template_levels)} template(s). Selected closest archetype.")

    def _apply_template_to_fields(self) -> None:
        if not self.template_level:
            return
        config = build_config_from_template(self.template_level, self._build_config())
        self.rows_var.set(config.rows)
        self.cols_var.set(config.cols)
        self.gates_var.set(config.gate_count)
        self.visible_var.set(config.max_visible_tray_per_gate)
        self.time_var.set(config.time)
        self.difficulty_var.set(config.difficulty)
        self.shooter_count_var.set(config.shooter_count)
        self.wall_count_var.set(config.wall_count)
        self.color_count_var.set(config.color_count)
        self.capacity_var.set(config.shooter_capacity)
        self._load_default_phases()

    def choose_export_folder(self) -> None:
        folder = filedialog.askdirectory(title="Choose export folder")
        if folder:
            self.export_folder_var.set(folder)

    def _ensure_reference_ready(self) -> bool:
        if self.mode_var.get() != "Reference Level File":
            return True
        if self.reference_level and self.reference_curve_targets:
            return True
        messagebox.showwarning(
            "Reference Level",
            "Load a reference level that solver can PASS before generating in Reference Level File mode.",
        )
        return False

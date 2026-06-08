from __future__ import annotations

import copy
import os
import queue
import threading
from tkinter import messagebox
from typing import List, Optional

from .color_utils import SELECTABLE_BALL_COLORS
from .level_generator import (
    CandidateResult,
    DifficultyCurveGenerator,
    GeneratorConfig,
    export_level,
    build_config_from_template,
    load_template_folder,
    select_template_for_config,
)
from .level_generator_window_constants import EMPTY_CELL_STRATEGIES
from .utils import safe_float, safe_int


class LevelGeneratorWindowActionsMixin:
    def _has_enabled_phase(self) -> bool:
        return any(
            self._parse_phase_tree_values(self.phase_tree.item(item, "values"))[0]
            for item in self.phase_tree.get_children()
        )

    def _ensure_active_phase(self) -> bool:
        if self._has_enabled_phase():
            return True
        messagebox.showwarning("Phase Table", "Enable at least one phase before generation.")
        return False

    def generate_preview(self) -> None:
        if self._busy():
            return
        if not self._ensure_active_phase():
            return
        if not self._ensure_reference_ready():
            return
        self._start_worker("1 level", self._worker_preview)

    def export_single(self) -> None:
        if self._busy():
            return
        if not self._ensure_active_phase():
            return
        if not self._ensure_reference_ready():
            return
        folder = self.export_folder_var.get().strip()
        if not folder:
            messagebox.showwarning("Export", "Choose export folder first.")
            return
        level_id = max(1, safe_int(str(self.level_var.get()), 1))
        path = os.path.join(folder, f"{level_id}.json")
        if os.path.exists(path):
            messagebox.showwarning("Export", f"File already exists and will not be overwritten:\n{path}")
            return
        if self.preview_candidate and self.preview_candidate.score.status == "PASS":
            if self._export_candidate(self.preview_candidate, path, level_id):
                self.status_var.set(f"Exported level {level_id}.")
                self._log(f"Exported PASS preview: {path}")
            else:
                self.status_var.set("Export skipped.")
                self._log(f"Skip existing: {path}")
            return
        self._log("No PASS preview found. Generating one level before export.")
        self._start_worker("single export", self._worker_single_export)

    def batch_export(self) -> None:
        if self._busy():
            return
        if not self._ensure_active_phase():
            return
        if not self._ensure_reference_ready():
            return
        folder = self.export_folder_var.get().strip()
        if not folder:
            messagebox.showwarning("Export", "Choose export folder first.")
            return
        self._start_worker("batch", self._worker_batch)

    def apply_to_editor(self) -> None:
        if self._busy():
            return
        if self.preview_candidate and self.preview_candidate.score.status == "PASS":
            self._apply_candidate_to_editor(self.preview_candidate)
            return
        if not self._ensure_active_phase():
            return
        if not self._ensure_reference_ready():
            return
        self._log("No PASS preview found. Generating one level before apply.")
        self._start_worker("apply", self._worker_apply)

    def _apply_candidate_to_editor(self, candidate: CandidateResult) -> None:
        if hasattr(self.master, "apply_generated_level"):
            self.master.apply_generated_level(copy.deepcopy(candidate.level))
            self.preview_candidate = candidate
            self.status_var.set("Applied generated level to editor.")
            self._log("Applied generated level to editor.")
        else:
            messagebox.showerror("Apply", "Editor does not expose apply_generated_level().")

    def cancel(self) -> None:
        self.cancel_event.set()
        self.status_var.set("Cancelling...")

    def close(self) -> None:
        self.cancel_event.set()
        self.destroy()

    def _busy(self) -> bool:
        return bool(self.worker and self.worker.is_alive())

    def _start_worker(self, label: str, target) -> None:
        self.cancel_event.clear()
        self.status_var.set(f"Running {label}...")
        self.worker = threading.Thread(target=target, daemon=True)
        self.worker.start()

    def _worker_preview(self) -> None:
        config = self._build_config()
        generator = DifficultyCurveGenerator(config)
        try:
            candidate = generator.generate_best(progress=self._progress, cancel_check=self.cancel_event.is_set)
            self.result_queue.put(("preview", candidate))
        except Exception as exc:
            self.result_queue.put(("error", str(exc)))

    def _worker_apply(self) -> None:
        config = self._build_config()
        generator = DifficultyCurveGenerator(config)
        try:
            candidate = generator.generate_best(progress=self._progress, cancel_check=self.cancel_event.is_set)
            self.result_queue.put(("apply_done", candidate))
        except Exception as exc:
            self.result_queue.put(("error", str(exc)))

    def _worker_single_export(self) -> None:
        folder = self.export_folder_var.get().strip()
        level_id = max(1, safe_int(str(self.level_var.get()), 1))
        path = os.path.join(folder, f"{level_id}.json")
        if os.path.exists(path):
            self.result_queue.put(("single_done", False, f"Skip existing: {path}", None))
            return

        config = self._build_config()
        config.level_id = level_id
        config.level_name = f"Level_{level_id}"
        generator = DifficultyCurveGenerator(config)
        try:
            candidate = generator.generate_best(progress=self._progress, cancel_check=self.cancel_event.is_set)
            if candidate.score.status == "PASS" and self._export_candidate(candidate, path, level_id):
                self.result_queue.put(("single_done", True, f"Exported PASS: {path}", candidate))
            else:
                self.result_queue.put(("single_done", False, f"Failed level {level_id}: {candidate.score.status}", candidate))
        except Exception as exc:
            self.result_queue.put(("error", str(exc)))

    def _export_candidate(self, candidate: CandidateResult, path: str, level_id: int) -> bool:
        level = copy.deepcopy(candidate.level)
        level["level"] = max(1, int(level_id))
        level["levelName"] = f"Level_{level['level']}"
        return export_level(path, level, overwrite=False)

    def _worker_batch(self) -> None:
        folder = self.export_folder_var.get().strip()
        start_id = max(1, safe_int(str(self.batch_start_var.get()), self.level_var.get()))
        count = max(1, safe_int(str(self.batch_count_var.get()), 1))
        exported = 0
        skipped = 0
        failed = 0
        for offset in range(count):
            if self.cancel_event.is_set():
                break
            level_id = start_id + offset
            path = os.path.join(folder, f"{level_id}.json")
            if os.path.exists(path):
                skipped += 1
                self.result_queue.put(("log", f"Skip existing: {path}"))
                continue
            config = self._build_config()
            config.level_id = level_id
            config.level_name = f"Level_{level_id}"
            generator = DifficultyCurveGenerator(config)
            try:
                candidate = generator.generate_best(progress=self._progress, cancel_check=self.cancel_event.is_set)
                if candidate.score.status == "PASS" and export_level(path, candidate.level, overwrite=False):
                    exported += 1
                    self.result_queue.put(("log", f"Exported PASS: {path}"))
                else:
                    failed += 1
                    self.result_queue.put(("log", f"Failed level {level_id}: {candidate.score.status}"))
                for note in candidate.notes:
                    self.result_queue.put(("log", f"NOTE: {note}"))
            except Exception as exc:
                failed += 1
                self.result_queue.put(("log", f"Failed level {level_id}: {exc}"))
        self.result_queue.put(("batch_done", exported, skipped, failed))

    def _poll_results(self) -> None:
        try:
            while True:
                item = self.result_queue.get_nowait()
                kind = item[0]
                if kind == "preview":
                    self.preview_candidate = item[1]
                    self._render_candidate(self.preview_candidate)
                elif kind == "apply_done":
                    candidate = item[1]
                    self.preview_candidate = candidate
                    self._render_candidate(candidate)
                    if candidate.score.status == "PASS":
                        self._apply_candidate_to_editor(candidate)
                    else:
                        self.status_var.set(f"Apply failed: {candidate.score.status}")
                        self._log(self.status_var.get())
                elif kind == "single_done":
                    _, exported, message, candidate = item
                    if candidate is not None:
                        self.preview_candidate = candidate
                        self._render_candidate(candidate)
                    self.status_var.set("Single export done." if exported else "Single export failed.")
                    self._log(message)
                elif kind == "batch_done":
                    _, exported, skipped, failed = item
                    self.status_var.set(f"Batch done. Exported={exported}, skipped={skipped}, failed={failed}")
                    self._log(self.status_var.get())
                elif kind == "log":
                    self._log(item[1])
                elif kind == "error":
                    self.status_var.set("Error")
                    self._log(item[1])
                    messagebox.showerror("Generator Error", item[1])
        except queue.Empty:
            pass
        self.after(100, self._poll_results)

    def _build_config(self) -> GeneratorConfig:
        phases = self._read_phases()
        capacity = max(1, safe_int(str(self.capacity_var.get()), 9)) if self.override_capacity_var.get() else 9
        tray_unit = max(1, safe_int(str(self.tray_unit_var.get()), 3)) if self.override_capacity_var.get() else 3
        allowed_devices = []
        if self.allow_wall_var.get():
            allowed_devices.append("Wall")
        if self.allow_tunnel_var.get():
            allowed_devices.append("Tunnel")
        if self.allow_iceblock_var.get():
            allowed_devices.append("IceBlock")
        if self.allow_icetray_var.get():
            allowed_devices.append("IceTray")
        if self.allow_special_var.get():
            allowed_devices.append("Special")
        if self.allow_connected_group_var.get():
            allowed_devices.append("ConnectedGroup")
        if self.allow_lockbar_var.get():
            allowed_devices.append("LockBar")
        config = GeneratorConfig(
            rows=max(1, safe_int(str(self.rows_var.get()), 6)),
            cols=max(1, safe_int(str(self.cols_var.get()), 5)),
            gate_count=max(1, safe_int(str(self.gates_var.get()), 4)),
            max_visible_tray_per_gate=max(1, safe_int(str(self.visible_var.get()), 4)),
            level_id=max(1, safe_int(str(self.level_var.get()), 1)),
            level_name=f"Level_{max(1, safe_int(str(self.level_var.get()), 1))}",
            difficulty=self.difficulty_var.get(),
            category=0,
            time=max(0, safe_int(str(self.time_var.get()), 60)),
            shooter_count=max(1, safe_int(str(self.shooter_count_var.get()), 20)),
            wall_count=max(0, safe_int(str(self.wall_count_var.get()), 5)),
            color_count=max(1, safe_int(str(self.color_count_var.get()), 5)),
            color_mode=self.color_mode_var.get(),
            manual_colors=self._manual_colors(),
            allowed_devices=allowed_devices,
            tunnel_queue_min=max(1, safe_int(str(self.tunnel_queue_min_var.get()), 1)),
            tunnel_queue_max=max(1, safe_int(str(self.tunnel_queue_max_var.get()), 2)),
            empty_cell_strategy=self.empty_cell_strategy_var.get()
            if self.empty_cell_strategy_var.get() in EMPTY_CELL_STRATEGIES
            else EMPTY_CELL_STRATEGIES[0],
            shooter_capacity=capacity,
            tray_unit=tray_unit,
            solver_budget=max(0.1, safe_float(str(self.budget_var.get()), 20.0)),
            candidate_attempts=max(1, safe_int(str(self.attempts_var.get()), 30)),
            phases=phases,
            seed=self._seed_value(),
        )
        if self.mode_var.get() == "Reference Level File":
            if self.reference_level:
                config.reference_level = copy.deepcopy(self.reference_level)
                config.reference_curve_targets = list(self.reference_curve_targets)
                config.reference_min_difference = 0.30
            config.level_id = max(1, safe_int(str(self.level_var.get()), 1))
            config.level_name = f"Level_{config.level_id}"
        elif self.mode_var.get() == "Template Folder":
            if not self.template_levels and self.template_folder_var.get().strip():
                self.template_levels = load_template_folder(self.template_folder_var.get().strip())
            selected = select_template_for_config(self.template_levels, config) if self.template_levels else self.template_level
            if selected:
                self.template_level = selected
                config = build_config_from_template(selected, config)
            config.phases = phases
            config.level_id = max(1, safe_int(str(self.level_var.get()), 1))
            config.level_name = f"Level_{config.level_id}"
            config.color_mode = self.color_mode_var.get()
            config.manual_colors = self._manual_colors()
            config.allowed_devices = allowed_devices
            if not self.override_capacity_var.get():
                config.shooter_capacity = max(1, config.shooter_capacity)
                config.tray_unit = 3
        else:
            config.level_name = f"Level_{config.level_id}"
        return config

    def _manual_colors(self) -> List[str]:
        return [
            color
            for color, var in self.manual_color_vars.items()
            if var.get() and color in SELECTABLE_BALL_COLORS
        ]

    def _seed_value(self) -> Optional[int]:
        seed = self.seed_var.get().strip()
        if not seed:
            return None
        return safe_int(seed, None)  # type: ignore[arg-type]

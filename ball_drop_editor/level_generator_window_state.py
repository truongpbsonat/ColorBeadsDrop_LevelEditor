from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk
from typing import Dict, List

from .color_utils import SELECTABLE_BALL_COLORS
from .level_generator_window_constants import EMPTY_CELL_STRATEGIES


class LevelGeneratorWindowStateMixin:
    def _init_vars(self) -> None:
        level = getattr(self.master, "level", {}) or {}
        grid = level.get("grid", {})
        gate_system = level.get("gateSystem", {})
        self.mode_var = tk.StringVar(value="Preset")
        self.template_folder_var = tk.StringVar(value="")
        self.reference_file_var = tk.StringVar(value="")
        self.rows_var = tk.IntVar(value=int(grid.get("rows", 6) or 6))
        self.cols_var = tk.IntVar(value=int(grid.get("columns", 5) or 5))
        self.gates_var = tk.IntVar(value=int(gate_system.get("gateCount", 4) or 4))
        self.visible_var = tk.IntVar(value=int(gate_system.get("maxVisibleTrayPerGate", 4) or 4))
        self.level_var = tk.IntVar(value=int(level.get("level", 1) or 1))
        self.difficulty_var = tk.StringVar(value=level.get("difficulty", "Hard"))
        self.time_var = tk.IntVar(value=int(level.get("time", 60) or 60))
        self.shooter_count_var = tk.IntVar(value=self._count_entities("Shooter") or 20)
        self.wall_count_var = tk.IntVar(value=self._count_entities("Wall") or 5)
        self.color_mode_var = tk.StringVar(value="Auto")
        self.color_count_var = tk.IntVar(value=5)
        self.generator_palette = list(SELECTABLE_BALL_COLORS)
        self.manual_color_vars: Dict[str, tk.BooleanVar] = {
            color: tk.BooleanVar(value=index < 5)
            for index, color in enumerate(self.generator_palette)
        }
        self.manual_color_buttons: List[tk.Checkbutton] = []
        self.preset_entries: List[ttk.Entry] = []
        self.allow_wall_var = tk.BooleanVar(value=True)
        self.allow_tunnel_var = tk.BooleanVar(value=True)
        self.allow_iceblock_var = tk.BooleanVar(value=True)
        self.allow_icetray_var = tk.BooleanVar(value=True)
        self.tunnel_queue_min_var = tk.IntVar(value=1)
        self.tunnel_queue_max_var = tk.IntVar(value=2)
        self.empty_cell_strategy_var = tk.StringVar(value=EMPTY_CELL_STRATEGIES[0])
        self.override_capacity_var = tk.BooleanVar(value=False)
        self.capacity_var = tk.IntVar(value=9)
        self.tray_unit_var = tk.IntVar(value=3)
        self.budget_var = tk.DoubleVar(value=20.0)
        self.attempts_var = tk.IntVar(value=30)
        self.seed_var = tk.StringVar(value="")
        self.batch_start_var = tk.IntVar(value=self.level_var.get())
        self.batch_count_var = tk.IntVar(value=5)
        self.export_folder_var = tk.StringVar(value=getattr(self.master, "level_folder", os.getcwd()))
        self.status_var = tk.StringVar(value="Ready")

        self.phase_enabled_var = tk.BooleanVar(value=True)
        self.phase_name_var = tk.StringVar(value="Spike")
        self.phase_start_var = tk.IntVar(value=1)
        self.phase_end_var = tk.IntVar(value=5)
        self.phase_target_var = tk.StringVar(value="Hard")
        self.phase_decision_var = tk.IntVar(value=2)
        self.phase_conveyor_var = tk.IntVar(value=2)
        self.phase_unlock_var = tk.IntVar(value=2)
        self.phase_same_color_var = tk.IntVar(value=1)
        self.phase_tunnel_var = tk.IntVar(value=1)
        self.phase_obstacle_var = tk.IntVar(value=1)

    def _count_entities(self, entity_type: str) -> int:
        level = getattr(self.master, "level", {}) or {}
        return sum(
            1
            for cell in level.get("grid", {}).get("cells", [])
            if (cell.get("entity") or {}).get("type") == entity_type
        )

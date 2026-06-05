from __future__ import annotations

import copy
import json
import os
import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict, List, Optional

from .constants import BALL_COLORS, COLOR_HEX, GRID_OBSTACLE_TYPES, LEVEL_DIFFICULTIES
from .level_generator import (
    DIFFICULTY_TARGETS,
    CandidateResult,
    DifficultyCurveGenerator,
    GeneratorConfig,
    GeneratorPhase,
    build_config_from_template,
    export_level,
    load_template_folder,
    select_template_for_config,
)
from .level_data import normalize_runtime_level
from .level_tester_score import SolverScoreAdapter, SolverScoreResult
from .utils import safe_float, safe_int
from .validator import LevelValidator

EMPTY_CELL_STRATEGIES = ("Add Shooters", "Compact Grid Then Add Shooters")


class LevelGeneratorWindow(tk.Toplevel):
    def __init__(self, master=None):
        super().__init__(master)
        self.title("BallDropParty Level Generator")
        self.geometry("1280x820")
        self.minsize(1080, 680)

        self.result_queue: queue.Queue = queue.Queue()
        self.worker: Optional[threading.Thread] = None
        self.cancel_event = threading.Event()
        self.preview_candidate: Optional[CandidateResult] = None
        self.template_level: Optional[Dict[str, Any]] = None
        self.template_levels: List[Dict[str, Any]] = []
        self.reference_level: Optional[Dict[str, Any]] = None
        self.reference_curve_targets: List[float] = []
        self.reference_score: Optional[SolverScoreResult] = None

        self._init_vars()
        self._build_ui()
        self._load_default_phases()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(100, self._poll_results)

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
        self.generator_palette = [color for color in BALL_COLORS if color != "None"]
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

    def _build_ui(self) -> None:
        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")
        ttk.Label(top, textvariable=self.status_var).pack(side="left")
        actions = ttk.Frame(top)
        actions.pack(side="right")
        ttk.Button(actions, text="Gen 1 Level", command=self.generate_preview).pack(side="left", padx=(0, 4))
        ttk.Button(actions, text="Apply to Editor", command=self.apply_to_editor).pack(side="left", padx=4)
        ttk.Button(actions, text="Export Level", command=self.export_single).pack(side="left", padx=4)
        ttk.Button(actions, text="Cancel", command=self.cancel).pack(side="left", padx=(4, 0))

        body = ttk.PanedWindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        left = ttk.Frame(body)
        left.columnconfigure(0, weight=1)
        body.add(left, weight=3)

        right = ttk.Frame(body)
        right.rowconfigure(0, weight=3)
        right.rowconfigure(1, weight=2)
        right.columnconfigure(0, weight=1)
        body.add(right, weight=2)

        self._build_config_panel(left)
        self._build_phase_panel(left)
        self._build_report_panel(right)

    def _build_config_panel(self, parent) -> None:
        frame = ttk.LabelFrame(parent, text="Generator Config", padding=8)
        frame.grid(row=0, column=0, sticky="ew")
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

        meta = ttk.LabelFrame(frame, text="Level Metadata", padding=6)
        meta.grid(row=0, column=0, sticky="ew", padx=(0, 4), pady=(0, 6))
        for col in range(4):
            meta.columnconfigure(col, weight=0)
        ttk.Label(meta, text="Level").grid(row=0, column=0, sticky="w")
        ttk.Entry(meta, textvariable=self.level_var, width=8).grid(row=0, column=1, padx=(4, 10), sticky="w")
        ttk.Label(meta, text="Difficulty").grid(row=0, column=2, sticky="w")
        ttk.Combobox(meta, textvariable=self.difficulty_var, values=LEVEL_DIFFICULTIES, width=10, state="readonly").grid(row=0, column=3, padx=(4, 10), sticky="w")

        source = ttk.LabelFrame(frame, text="Generation Source", padding=6)
        source.grid(row=0, column=1, sticky="ew", padx=(4, 0), pady=(0, 6))
        source.columnconfigure(1, weight=1)
        ttk.Radiobutton(source, text="Preset Generation", variable=self.mode_var, value="Preset", command=self._sync_source_state).grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(source, text="Template Folder Generation", variable=self.mode_var, value="Template Folder", command=self._sync_source_state).grid(row=1, column=0, sticky="w")
        ttk.Radiobutton(source, text="Reference Level File", variable=self.mode_var, value="Reference Level File", command=self._sync_source_state).grid(row=2, column=0, sticky="w")
        ttk.Entry(source, textvariable=self.template_folder_var).grid(row=1, column=1, sticky="ew", padx=(8, 4))
        ttk.Button(source, text="Folder", command=self.choose_template_folder, width=8).grid(row=1, column=2, padx=2)
        ttk.Button(source, text="Analyze", command=self.analyze_templates, width=9).grid(row=1, column=3, padx=2)
        ttk.Button(source, text="Use Current", command=self.use_current_as_template, width=11).grid(row=0, column=3, padx=2)
        ttk.Entry(source, textvariable=self.reference_file_var).grid(row=2, column=1, sticky="ew", padx=(8, 4))
        ttk.Button(source, text="Load Reference", command=self.load_reference_file, width=14).grid(row=2, column=2, columnspan=2, sticky="w", padx=2)

        preset = ttk.LabelFrame(frame, text="Preset Generation", padding=6)
        preset.grid(row=1, column=0, sticky="ew", padx=(0, 4), pady=(0, 6))
        preset_fields = [
            ("Rows", self.rows_var),
            ("Cols", self.cols_var),
            ("Gates", self.gates_var),
            ("Visible", self.visible_var),
            ("Shooters", self.shooter_count_var),
            ("Walls", self.wall_count_var),
        ]
        for idx, (label, var) in enumerate(preset_fields):
            row = idx // 3
            col = (idx % 3) * 2
            ttk.Label(preset, text=label).grid(row=row, column=col, sticky="w", pady=2)
            entry = ttk.Entry(preset, textvariable=var, width=8)
            entry.grid(row=row, column=col + 1, sticky="w", padx=(4, 10), pady=2)
            self.preset_entries.append(entry)

        color_frame = ttk.LabelFrame(frame, text="Color Setup", padding=6)
        color_frame.grid(row=1, column=1, sticky="ew", padx=(4, 0), pady=(0, 6))
        ttk.Label(color_frame, text="Mode").grid(row=0, column=0, sticky="w")
        color_mode_combo = ttk.Combobox(
            color_frame,
            textvariable=self.color_mode_var,
            values=("Auto", "Manual"),
            width=9,
            state="readonly",
        )
        color_mode_combo.grid(row=0, column=1, sticky="w", padx=(4, 10))
        color_mode_combo.bind("<<ComboboxSelected>>", lambda _e: self._sync_color_state())
        ttk.Label(color_frame, text="Color Count").grid(row=0, column=2, sticky="w")
        ttk.Entry(color_frame, textvariable=self.color_count_var, width=8).grid(row=0, column=3, sticky="w", padx=(4, 10))
        palette = ttk.Frame(color_frame)
        palette.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(4, 0))
        for idx, color in enumerate(self.generator_palette):
            fg = "#000000" if color not in {"Black", "Blue", "Brown", "Gray", "Purple", "Red", "Teal", "Violet"} else "#FFFFFF"
            button = tk.Checkbutton(
                palette,
                text="",
                variable=self.manual_color_vars[color],
                width=3,
                bg=COLOR_HEX.get(color, "#BBBBBB"),
                fg=fg,
                activebackground=COLOR_HEX.get(color, "#BBBBBB"),
                selectcolor=COLOR_HEX.get(color, "#BBBBBB"),
            )
            button.grid(row=idx // 6, column=idx % 6, sticky="w", padx=(0, 5), pady=2)
            self.manual_color_buttons.append(button)

        devices = ttk.LabelFrame(frame, text="Allowed Obstacles / Devices", padding=6)
        devices.grid(row=2, column=0, sticky="ew", padx=(0, 4), pady=(0, 6))
        ttk.Checkbutton(devices, text="Wall", variable=self.allow_wall_var).grid(row=0, column=0, sticky="w", padx=(0, 12))
        ttk.Checkbutton(devices, text="Tunnel", variable=self.allow_tunnel_var).grid(row=0, column=1, sticky="w", padx=(0, 12))
        ttk.Checkbutton(devices, text="IceBlock", variable=self.allow_iceblock_var).grid(row=0, column=2, sticky="w", padx=(0, 12))
        ttk.Checkbutton(devices, text="Ice Tray", variable=self.allow_icetray_var).grid(row=0, column=3, sticky="w", padx=(0, 12))
        ttk.Label(devices, text="Tunnel Queue Min").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Entry(devices, textvariable=self.tunnel_queue_min_var, width=7).grid(row=1, column=1, sticky="w", pady=(4, 0))
        ttk.Label(devices, text="Max").grid(row=1, column=2, sticky="w", pady=(4, 0))
        ttk.Entry(devices, textvariable=self.tunnel_queue_max_var, width=7).grid(row=1, column=3, sticky="w", pady=(4, 0))

        capacity = ttk.LabelFrame(frame, text="Capacity / Tray Override", padding=6)
        capacity.grid(row=2, column=1, sticky="ew", padx=(4, 0), pady=(0, 6))
        ttk.Checkbutton(
            capacity,
            text="Override Capacity / Tray",
            variable=self.override_capacity_var,
            command=self._sync_capacity_state,
        ).grid(row=0, column=0, columnspan=4, sticky="w")
        ttk.Label(capacity, text="Capacity").grid(row=1, column=0, sticky="w", pady=2)
        self.capacity_entry = ttk.Entry(capacity, textvariable=self.capacity_var, width=8)
        self.capacity_entry.grid(row=1, column=1, sticky="w", padx=(4, 10), pady=2)
        ttk.Label(capacity, text="Tray Unit").grid(row=1, column=2, sticky="w", pady=2)
        self.tray_unit_entry = ttk.Entry(capacity, textvariable=self.tray_unit_var, width=8)
        self.tray_unit_entry.grid(row=1, column=3, sticky="w", padx=(4, 10), pady=2)

        runtime = ttk.LabelFrame(frame, text="Single Level Workflow", padding=6)
        runtime.grid(row=3, column=0, columnspan=2, sticky="ew")
        runtime.columnconfigure(3, weight=1)
        ttk.Label(runtime, text="Budget").grid(row=0, column=0, sticky="w", pady=2)
        ttk.Entry(runtime, textvariable=self.budget_var, width=8).grid(row=0, column=1, sticky="w", padx=(4, 10), pady=2)
        ttk.Label(runtime, text="Attempts").grid(row=0, column=2, sticky="w", pady=2)
        ttk.Entry(runtime, textvariable=self.attempts_var, width=8).grid(row=0, column=3, sticky="w", padx=(4, 10), pady=2)
        ttk.Label(runtime, text="Seed").grid(row=0, column=4, sticky="w", pady=2)
        ttk.Entry(runtime, textvariable=self.seed_var, width=12).grid(row=0, column=5, sticky="w", padx=(4, 10), pady=2)
        ttk.Label(runtime, text="Export").grid(row=1, column=0, sticky="w", pady=2)
        ttk.Entry(runtime, textvariable=self.export_folder_var, width=36).grid(row=1, column=1, columnspan=3, sticky="ew", padx=(4, 4), pady=2)
        ttk.Button(runtime, text="Folder", command=self.choose_export_folder, width=8).grid(row=1, column=4, sticky="w", pady=2)
        ttk.Label(runtime, text="Empty Cells").grid(row=1, column=5, sticky="w", pady=2)
        ttk.Combobox(
            runtime,
            textvariable=self.empty_cell_strategy_var,
            values=EMPTY_CELL_STRATEGIES,
            width=28,
            state="readonly",
        ).grid(row=1, column=6, sticky="w", padx=(4, 0), pady=2)
        help_text = (
            "Seed: optional random seed; same config + same seed recreates the same candidate order. "
            "Gen 1 Level creates a PASS preview candidate. Apply to Editor and Export Level use that preview; "
            "if no PASS preview exists, they generate one first. Existing files are skipped, not overwritten."
        )
        ttk.Label(runtime, text=help_text, wraplength=900, foreground="#4B5563").grid(
            row=2,
            column=0,
            columnspan=7,
            sticky="w",
            pady=(6, 0),
        )

        batch = ttk.LabelFrame(frame, text="Batch Export (Optional)", padding=6)
        batch.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        batch.columnconfigure(7, weight=1)
        ttk.Label(batch, text="Batch Start").grid(row=0, column=0, sticky="w", pady=2)
        ttk.Entry(batch, textvariable=self.batch_start_var, width=8).grid(row=0, column=1, sticky="w", padx=(4, 10), pady=2)
        ttk.Label(batch, text="Count").grid(row=0, column=2, sticky="w", pady=2)
        ttk.Entry(batch, textvariable=self.batch_count_var, width=8).grid(row=0, column=3, sticky="w", padx=(4, 10), pady=2)
        ttk.Button(batch, text="Batch Export", command=self.batch_export).grid(row=0, column=4, sticky="w", padx=(4, 10), pady=2)
        ttk.Label(
            batch,
            text="Uses the same config to export multiple files; existing files are skipped.",
            foreground="#4B5563",
        ).grid(row=0, column=5, columnspan=3, sticky="w", pady=2)

        self._sync_capacity_state()
        self._sync_source_state()
        self._sync_color_state()

    def _build_phase_panel(self, parent) -> None:
        frame = ttk.LabelFrame(parent, text="Phase Table", padding=8)
        frame.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        parent.rowconfigure(1, weight=1)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        columns = ("enabled", "name", "start", "end", "target", "decision", "conveyor", "unlock", "same", "tunnel", "obstacle")
        self.phase_tree = ttk.Treeview(frame, columns=columns, show="headings", height=8, selectmode="browse")
        headings = [
            ("enabled", "Use", 45),
            ("name", "Phase", 110),
            ("start", "Start", 55),
            ("end", "End", 55),
            ("target", "Target", 78),
            ("decision", "Decision", 70),
            ("conveyor", "Conveyor", 75),
            ("unlock", "Unlock", 65),
            ("same", "SameClr", 65),
            ("tunnel", "Tunnel", 65),
            ("obstacle", "Obstacle", 70),
        ]
        for key, title, width in headings:
            self.phase_tree.heading(key, text=title)
            self.phase_tree.column(key, width=width, anchor="center", stretch=(key == "name"))
        self.phase_tree.tag_configure("disabled", foreground="#6B7280")
        self.phase_tree.grid(row=0, column=0, sticky="nsew")
        self.phase_tree.bind("<<TreeviewSelect>>", self.load_selected_phase)
        self.phase_tree.bind("<Button-1>", self.toggle_phase_enabled)

        form = ttk.Frame(frame)
        form.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        for col in range(14):
            form.columnconfigure(col, weight=0)
        ttk.Label(form, text="Use").grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(form, variable=self.phase_enabled_var).grid(row=1, column=0, padx=(0, 4), sticky="w")
        widgets = [
            ("Name", self.phase_name_var, 10),
            ("Start", self.phase_start_var, 5),
            ("End", self.phase_end_var, 5),
            ("Target", self.phase_target_var, 9),
            ("Decision", self.phase_decision_var, 4),
            ("Conv", self.phase_conveyor_var, 4),
            ("Unlock", self.phase_unlock_var, 4),
            ("Same", self.phase_same_color_var, 4),
            ("Tunnel", self.phase_tunnel_var, 4),
            ("Obs", self.phase_obstacle_var, 4),
        ]
        col = 1
        for label, var, width in widgets:
            ttk.Label(form, text=label).grid(row=0, column=col, sticky="w")
            if label == "Target":
                ttk.Combobox(form, textvariable=var, values=tuple(DIFFICULTY_TARGETS), width=width, state="readonly").grid(row=1, column=col, padx=(0, 4), sticky="w")
            else:
                ttk.Entry(form, textvariable=var, width=width).grid(row=1, column=col, padx=(0, 4), sticky="w")
            col += 1
        ttk.Button(form, text="Add/Update", command=self.upsert_phase).grid(row=1, column=col, padx=4)
        ttk.Button(form, text="Delete", command=self.delete_phase).grid(row=1, column=col + 1, padx=4)
        ttk.Button(form, text="Defaults", command=self._load_default_phases).grid(row=1, column=col + 2, padx=4)

    def _build_report_panel(self, parent) -> None:
        chart_frame = ttk.LabelFrame(parent, text="Target vs Actual Curve", padding=6)
        chart_frame.grid(row=0, column=0, sticky="nsew")
        chart_frame.rowconfigure(0, weight=1)
        chart_frame.columnconfigure(0, weight=1)
        self.chart_canvas = tk.Canvas(chart_frame, bg="#111827", height=250, highlightthickness=0)
        self.chart_canvas.grid(row=0, column=0, sticky="nsew")

        log_frame = ttk.LabelFrame(parent, text="Log", padding=6)
        log_frame.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        log_frame.rowconfigure(1, weight=1)
        log_frame.columnconfigure(0, weight=1)
        ttk.Button(log_frame, text="Clear Log", command=self.clear_log).grid(row=0, column=0, sticky="w", pady=(0, 4))
        self.log_text = tk.Text(log_frame, wrap="word", height=12, font=("Consolas", 10))
        self.log_text.grid(row=1, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll.set)
        scroll.grid(row=1, column=1, sticky="ns")

    def _load_default_phases(self) -> None:
        if not hasattr(self, "phase_tree"):
            return
        for item in self.phase_tree.get_children():
            self.phase_tree.delete(item)
        shooter_count = max(1, safe_int(str(self.shooter_count_var.get()), 20))
        segments = [
            ("Warmup", 1, max(1, shooter_count // 5), "Easy", 1, 1, 1, 0, 0, 0),
            ("Decision Spike", max(2, shooter_count // 5 + 1), max(2, shooter_count // 2), "Hard", 3, 2, 2, 3, 1, 1),
            ("Relief", max(3, shooter_count // 2 + 1), max(3, shooter_count * 3 // 5), "Normal", 1, 1, 1, 0, 0, 0),
            ("Pressure Spike", max(4, shooter_count * 3 // 5 + 1), max(4, shooter_count * 4 // 5), "Hard", 2, 3, 2, 1, 2, 2),
            ("Final Maze", max(5, shooter_count * 4 // 5 + 1), shooter_count, "VeryHard", 3, 3, 3, 2, 3, 3),
        ]
        for segment in segments:
            if segment[1] <= segment[2]:
                values = self._make_phase_tree_values(True, *segment)
                self.phase_tree.insert("", "end", values=values)

    def _phase_enabled_label(self, enabled: bool) -> str:
        return "[x]" if enabled else "[ ]"

    def _phase_label_is_enabled(self, value: Any) -> bool:
        return str(value).strip().lower() in {"[x]", "x", "yes", "true", "1", "on", "enabled"}

    def _make_phase_tree_values(
        self,
        enabled: bool,
        name: Any,
        start: Any,
        end: Any,
        target: Any,
        decision: Any,
        conveyor: Any,
        unlock: Any,
        same_color: Any,
        tunnel: Any,
        obstacle: Any,
    ) -> tuple[Any, ...]:
        target_name = target if target in DIFFICULTY_TARGETS else "Normal"
        return (
            self._phase_enabled_label(bool(enabled)),
            str(name).strip() or "Phase",
            max(1, safe_int(str(start), 1)),
            max(1, safe_int(str(end), 1)),
            target_name,
            max(0, safe_int(str(decision), 0)),
            max(0, safe_int(str(conveyor), 0)),
            max(0, safe_int(str(unlock), 0)),
            max(0, safe_int(str(same_color), 0)),
            max(0, safe_int(str(tunnel), 0)),
            max(0, safe_int(str(obstacle), 0)),
        )

    def _parse_phase_tree_values(self, values: Any) -> tuple[Any, ...]:
        raw_values = list(values or [])
        if len(raw_values) >= 11:
            enabled = self._phase_label_is_enabled(raw_values[0])
            phase_values = raw_values[1:]
        else:
            enabled = True
            phase_values = raw_values
        phase_values = phase_values + [""] * max(0, 10 - len(phase_values))
        target_name = phase_values[3] if phase_values[3] in DIFFICULTY_TARGETS else "Normal"
        return (
            enabled,
            str(phase_values[0]).strip() or "Phase",
            max(1, safe_int(str(phase_values[1]), 1)),
            max(1, safe_int(str(phase_values[2]), 1)),
            target_name,
            max(0, safe_int(str(phase_values[4]), 0)),
            max(0, safe_int(str(phase_values[5]), 0)),
            max(0, safe_int(str(phase_values[6]), 0)),
            max(0, safe_int(str(phase_values[7]), 0)),
            max(0, safe_int(str(phase_values[8]), 0)),
            max(0, safe_int(str(phase_values[9]), 0)),
        )

    def load_selected_phase(self, _event=None) -> None:
        selected = self.phase_tree.selection()
        if not selected:
            return
        values = self.phase_tree.item(selected[0], "values")
        (
            enabled,
            name,
            start,
            end,
            target,
            decision,
            conveyor,
            unlock,
            same_color,
            tunnel,
            obstacle,
        ) = self._parse_phase_tree_values(values)
        self.phase_enabled_var.set(enabled)
        self.phase_name_var.set(name)
        self.phase_start_var.set(start)
        self.phase_end_var.set(end)
        self.phase_target_var.set(target)
        self.phase_decision_var.set(decision)
        self.phase_conveyor_var.set(conveyor)
        self.phase_unlock_var.set(unlock)
        self.phase_same_color_var.set(same_color)
        self.phase_tunnel_var.set(tunnel)
        self.phase_obstacle_var.set(obstacle)

    def toggle_phase_enabled(self, event) -> Optional[str]:
        if self.phase_tree.identify_region(event.x, event.y) != "cell":
            return None
        if self.phase_tree.identify_column(event.x) != "#1":
            return None
        item = self.phase_tree.identify_row(event.y)
        if not item:
            return "break"
        values = self.phase_tree.item(item, "values")
        (
            enabled,
            name,
            start,
            end,
            target,
            decision,
            conveyor,
            unlock,
            same_color,
            tunnel,
            obstacle,
        ) = self._parse_phase_tree_values(values)
        new_values = self._make_phase_tree_values(
            not enabled,
            name,
            start,
            end,
            target,
            decision,
            conveyor,
            unlock,
            same_color,
            tunnel,
            obstacle,
        )
        self.phase_tree.item(item, values=new_values, tags=() if not enabled else ("disabled",))
        self.phase_tree.selection_set(item)
        self.phase_enabled_var.set(not enabled)
        return "break"

    def upsert_phase(self) -> None:
        values = self._make_phase_tree_values(
            self.phase_enabled_var.get(),
            self.phase_name_var.get().strip() or "Phase",
            max(1, safe_int(str(self.phase_start_var.get()), 1)),
            max(1, safe_int(str(self.phase_end_var.get()), 1)),
            self.phase_target_var.get() if self.phase_target_var.get() in DIFFICULTY_TARGETS else "Normal",
            max(0, safe_int(str(self.phase_decision_var.get()), 0)),
            max(0, safe_int(str(self.phase_conveyor_var.get()), 0)),
            max(0, safe_int(str(self.phase_unlock_var.get()), 0)),
            max(0, safe_int(str(self.phase_same_color_var.get()), 0)),
            max(0, safe_int(str(self.phase_tunnel_var.get()), 0)),
            max(0, safe_int(str(self.phase_obstacle_var.get()), 0)),
        )
        tags = () if self.phase_enabled_var.get() else ("disabled",)
        selected = self.phase_tree.selection()
        if selected:
            self.phase_tree.item(selected[0], values=values, tags=tags)
        else:
            self.phase_tree.insert("", "end", values=values, tags=tags)

    def delete_phase(self) -> None:
        for item in self.phase_tree.selection():
            self.phase_tree.delete(item)

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

    def _level_colors(self, level: Dict[str, Any]) -> List[str]:
        colors: set[str] = set()
        for cell in level.get("grid", {}).get("cells", []) or []:
            entity = cell.get("entity") or {}
            if entity.get("type") == "Shooter":
                color = entity.get("shooter", {}).get("colorId")
                if color in BALL_COLORS and color != "None":
                    colors.add(color)
            elif entity.get("type") == "Tunnel":
                for shooter in entity.get("shooterQueue", []) or []:
                    color = shooter.get("colorId")
                    if color in BALL_COLORS and color != "None":
                        colors.add(color)
        for gate in level.get("gateSystem", {}).get("gates", []) or []:
            for tray in gate.get("trayQueue", []) or []:
                for layer in tray.get("layers", []) or []:
                    color = layer.get("colorId")
                    if color in BALL_COLORS and color != "None":
                        colors.add(color)
        return [color for color in self.generator_palette if color in colors]

    def _estimate_tray_unit(self, level: Dict[str, Any]) -> int:
        counts: Dict[int, int] = {}
        for gate in level.get("gateSystem", {}).get("gates", []) or []:
            for tray in gate.get("trayQueue", []) or []:
                for layer in tray.get("layers", []) or []:
                    required = max(1, safe_int(str(layer.get("requiredCount", 0)), 1))
                    counts[required] = counts.get(required, 0) + 1
        if not counts:
            return max(1, safe_int(str(self.tray_unit_var.get()), 3))
        return max(counts, key=lambda value: (counts[value], value))

    def _reference_phase_rows(self, score: SolverScoreResult) -> List[tuple[Any, ...]]:
        groups: List[Dict[str, Any]] = []
        for item in score.per_click_scores:
            target = self._target_name_for_score(item.score)
            if not groups or groups[-1]["target"] != target:
                groups.append({"target": target, "items": []})
            groups[-1]["items"].append(item)
        while len(groups) > 8:
            merge_index = min(
                range(len(groups) - 1),
                key=lambda index: abs(self._group_average(groups[index]) - self._group_average(groups[index + 1])),
            )
            groups[merge_index]["items"].extend(groups[merge_index + 1]["items"])
            groups[merge_index]["target"] = self._target_name_for_score(self._group_average(groups[merge_index]))
            groups.pop(merge_index + 1)

        rows: List[tuple[Any, ...]] = []
        for index, group in enumerate(groups, start=1):
            items = group["items"]
            avg_score = self._group_average(group)
            target = self._target_name_for_score(avg_score)
            metrics = [item.metrics for item in items]
            active = sum(metric.active_choices for metric in metrics) / max(1, len(metrics))
            decoys = sum(metric.decoys for metric in metrics) / max(1, len(metrics))
            same = sum(metric.same_color_route_traps for metric in metrics) / max(1, len(metrics))
            conveyor = sum(metric.conveyor_pressure for metric in metrics) / max(1, len(metrics))
            unlock = sum(metric.unlock_depth for metric in metrics) / max(1, len(metrics))
            tunnel = sum(metric.tunnel_pressure for metric in metrics) / max(1, len(metrics))
            obstacle = sum(metric.obstacle_pressure for metric in metrics) / max(1, len(metrics))
            rows.append(
                self._make_phase_tree_values(
                    True,
                    f"Ref {index} {target}",
                    items[0].click_index,
                    items[-1].click_index,
                    target,
                    self._clamp_phase_weight(round((max(0.0, active - 1.0) + decoys) / 2.0)),
                    self._clamp_phase_weight(round(conveyor * 3.0)),
                    self._clamp_phase_weight(round(unlock * 3.0)),
                    self._clamp_phase_weight(round(same)),
                    self._clamp_phase_weight(round(tunnel * 3.0)),
                    self._clamp_phase_weight(round(obstacle * 3.0)),
                )
            )
        return rows

    def _group_average(self, group: Dict[str, Any]) -> float:
        items = group.get("items", [])
        return sum(item.score for item in items) / max(1, len(items))

    def _target_name_for_score(self, score: float) -> str:
        return min(DIFFICULTY_TARGETS, key=lambda name: abs(DIFFICULTY_TARGETS[name] - score))

    def _clamp_phase_weight(self, value: int) -> int:
        return max(0, min(3, int(value)))

    def _replace_phase_rows(self, rows: List[tuple[Any, ...]]) -> None:
        for item in self.phase_tree.get_children():
            self.phase_tree.delete(item)
        for values in rows:
            self.phase_tree.insert("", "end", values=values)

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

    def clear_log(self) -> None:
        self.log_text.delete("1.0", "end")

    def _sync_capacity_state(self) -> None:
        state = "normal" if self.override_capacity_var.get() else "disabled"
        if hasattr(self, "capacity_entry"):
            self.capacity_entry.configure(state=state)
        if hasattr(self, "tray_unit_entry"):
            self.tray_unit_entry.configure(state=state)

    def _sync_source_state(self) -> None:
        preset_state = "normal" if self.mode_var.get() == "Preset" else "disabled"
        for entry in getattr(self, "preset_entries", []):
            entry.configure(state=preset_state)
        if not hasattr(self, "log_text"):
            return
        if self.mode_var.get() == "Preset":
            self._log("Using preset generation inputs.")
        elif self.mode_var.get() == "Reference Level File":
            self._log("Using reference level file generation inputs.")
        else:
            self._log("Using template folder generation inputs.")

    def _sync_color_state(self) -> None:
        state = "normal" if self.color_mode_var.get() == "Manual" else "disabled"
        for button in getattr(self, "manual_color_buttons", []):
            button.configure(state=state)

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

    def _progress(
        self,
        attempt: int,
        total: int,
        candidate: CandidateResult,
        best: Optional[CandidateResult],
    ) -> None:
        best_label = best.score.status if best else "-"
        reference_extra = ""
        if candidate.structural_difference or candidate.reference_curve_error:
            reference_extra = (
                f", ref diff {candidate.structural_difference * 100:.1f}%, "
                f"curve {candidate.reference_curve_error:.1f}"
            )
        self.result_queue.put(
            (
                "log",
                f"Attempt {attempt}/{total}: {candidate.score.status}, "
                f"target error {candidate.target_error:.1f}{reference_extra}, best {best_label}",
            )
        )

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

    def _render_candidate(self, candidate: CandidateResult) -> None:
        score = candidate.score
        self.status_var.set(
            f"Preview: {score.status}, score={score.overall_score:.1f}, "
            f"target error={candidate.target_error:.1f}, attempt={candidate.attempt}"
        )
        self._log(self.status_var.get())
        for error in candidate.errors[:8]:
            self._log(f"ERROR: {error}")
        for warning in candidate.warnings[:8]:
            self._log(f"WARN: {warning}")
        for note in candidate.notes[:12]:
            self._log(f"NOTE: {note}")
        self._render_chart(candidate)

    def _render_chart(self, candidate: CandidateResult) -> None:
        canvas = self.chart_canvas
        canvas.delete("all")
        width = max(1, canvas.winfo_width())
        height = max(1, canvas.winfo_height())
        pad = 28
        canvas.create_rectangle(0, 0, width, height, fill="#111827", outline="")
        canvas.create_line(pad, height - pad, width - pad, height - pad, fill="#6B7280")
        canvas.create_line(pad, pad, pad, height - pad, fill="#6B7280")
        scores = candidate.score.per_click_scores
        if not scores:
            canvas.create_text(width // 2, height // 2, text="No PASS solution curve", fill="#E5E7EB")
            return
        max_click = max(item.click_index for item in scores)

        def xy(click_index: int, value: float) -> tuple[float, float]:
            x = pad + (width - pad * 2) * ((click_index - 1) / max(1, max_click - 1))
            y = height - pad - (height - pad * 2) * (max(0.0, min(100.0, value)) / 100.0)
            return x, y

        actual_points = [xy(item.click_index, item.score) for item in scores]
        for left, right in zip(actual_points, actual_points[1:]):
            canvas.create_line(*left, *right, fill="#38BDF8", width=2)
        for x, y in actual_points:
            canvas.create_oval(x - 2, y - 2, x + 2, y + 2, fill="#38BDF8", outline="")

        for phase in candidate.score.phase_scores:
            x1, y1 = xy(phase.start_click, phase.target_score)
            x2, y2 = xy(phase.end_click, phase.target_score)
            canvas.create_line(x1, y1, x2, y2, fill="#FBBF24", width=2, dash=(4, 3))
            canvas.create_text((x1 + x2) / 2, y1 - 10, text=phase.name, fill="#FDE68A", font=("Arial", 8))
        canvas.create_text(width - pad, pad, text="Actual blue / Target yellow", fill="#E5E7EB", anchor="ne")

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
            if var.get() and color in BALL_COLORS and color != "None"
        ]

    def _read_phases(self) -> List[GeneratorPhase]:
        phases: List[GeneratorPhase] = []
        for item in self.phase_tree.get_children():
            values = self.phase_tree.item(item, "values")
            if not values:
                continue
            (
                enabled,
                name,
                start,
                end,
                target,
                decision,
                conveyor,
                unlock,
                same_color,
                tunnel,
                obstacle,
            ) = self._parse_phase_tree_values(values)
            if not enabled:
                continue
            phases.append(
                GeneratorPhase(
                    name=name,
                    start_click=start,
                    end_click=end,
                    target=target,
                    decision_trap=decision,
                    conveyor_pressure=conveyor,
                    unlock_maze=unlock,
                    same_color_route=same_color,
                    tunnel_pressure=tunnel,
                    obstacle_pressure=obstacle,
                    obstacle_types=list(GRID_OBSTACLE_TYPES) + ["IceTray"],
                )
            )
        return phases

    def _seed_value(self) -> Optional[int]:
        seed = self.seed_var.get().strip()
        if not seed:
            return None
        return safe_int(seed, None)  # type: ignore[arg-type]

    def _log(self, message: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{timestamp}] {message}\n")
        self.log_text.see("end")


def open_level_generator(master=None) -> LevelGeneratorWindow:
    window = LevelGeneratorWindow(master)
    window.focus()
    return window

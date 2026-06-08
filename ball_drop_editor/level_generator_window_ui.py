from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .constants import BALL_COLORS, COLOR_HEX, GRID_OBSTACLE_TYPES, LEVEL_DIFFICULTIES
from .level_generator import DIFFICULTY_TARGETS
from .level_generator_window_constants import EMPTY_CELL_STRATEGIES


class LevelGeneratorWindowUiMixin:
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
        ttk.Checkbutton(devices, text="Special", variable=self.allow_special_var).grid(row=1, column=0, sticky="w", padx=(0, 12), pady=(4, 0))
        ttk.Checkbutton(devices, text="Connected Group", variable=self.allow_connected_group_var).grid(row=1, column=1, sticky="w", padx=(0, 12), pady=(4, 0))
        ttk.Checkbutton(devices, text="LockBar", variable=self.allow_lockbar_var).grid(row=1, column=2, sticky="w", padx=(0, 12), pady=(4, 0))
        ttk.Label(devices, text="Tunnel Queue Min").grid(row=2, column=0, sticky="w", pady=(4, 0))
        ttk.Entry(devices, textvariable=self.tunnel_queue_min_var, width=7).grid(row=2, column=1, sticky="w", pady=(4, 0))
        ttk.Label(devices, text="Max").grid(row=2, column=2, sticky="w", pady=(4, 0))
        ttk.Entry(devices, textvariable=self.tunnel_queue_max_var, width=7).grid(row=2, column=3, sticky="w", pady=(4, 0))

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

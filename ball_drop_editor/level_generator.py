from __future__ import annotations

import copy
import json
import os
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .constants import BALL_COLORS, GRID_OBSTACLE_TYPES, LEVEL_DIFFICULTIES
from .level_data import find_cell, make_empty_level, make_shooter_entity, make_wall_entity, normalize_runtime_level
from .level_tester_score import SolverScoreAdapter, SolverScoreResult
from .utils import short_id
from .validator import LevelValidator

DEFAULT_GENERATOR_COLORS = ["Blue", "Orange", "Green", "Purple", "Red", "Yellow", "Cyan", "Pink"]
DIFFICULTY_TARGETS = {
    "Easy": 18.0,
    "Normal": 38.0,
    "Hard": 62.0,
    "VeryHard": 78.0,
    "SuperHard": 90.0,
}


@dataclass
class GeneratorPhase:
    name: str
    start_click: int
    end_click: int
    target: str = "Normal"
    decision_trap: int = 1
    conveyor_pressure: int = 1
    unlock_maze: int = 1
    same_color_route: int = 0
    obstacle_pressure: int = 0
    obstacle_types: List[str] = field(default_factory=lambda: ["IceBlock"])

    @property
    def target_score(self) -> float:
        return DIFFICULTY_TARGETS.get(self.target, DIFFICULTY_TARGETS["Normal"])

    def to_score_phase(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "start_click": self.start_click,
            "end_click": self.end_click,
            "target_score": self.target_score,
        }


@dataclass
class GeneratorConfig:
    rows: int = 6
    cols: int = 5
    gate_count: int = 4
    max_visible_tray_per_gate: int = 4
    level_id: int = 1
    level_name: str = "Generated Level"
    difficulty: str = "Hard"
    category: int = 0
    time: int = 60
    shooter_count: int = 20
    wall_count: int = 5
    color_count: int = 5
    shooter_capacity: int = 9
    tray_unit: int = 3
    solver_budget: float = 20.0
    candidate_attempts: int = 30
    phases: List[GeneratorPhase] = field(default_factory=list)
    seed: Optional[int] = None

    def normalized_phases(self) -> List[GeneratorPhase]:
        if self.phases:
            return sorted(self.phases, key=lambda phase: (phase.start_click, phase.end_click))
        third = max(1, self.shooter_count // 3)
        return [
            GeneratorPhase("Warmup", 1, third, "Easy", 1, 1, 1, 0, 0),
            GeneratorPhase("Spike A", third + 1, third * 2, "Hard", 3, 2, 2, 2, 1),
            GeneratorPhase("Spike B", third * 2 + 1, self.shooter_count, "VeryHard", 3, 3, 3, 2, 2),
        ]


@dataclass
class CandidateResult:
    level: Dict[str, Any]
    score: SolverScoreResult
    errors: List[str]
    warnings: List[str]
    target_error: float
    attempt: int


class DifficultyCurveGenerator:
    def __init__(self, config: GeneratorConfig):
        self.config = copy.deepcopy(config)
        self.rng = random.Random(config.seed)
        self.validator = LevelValidator()
        self.solver = SolverScoreAdapter(time_budget=config.solver_budget)

    def generate_best(self, progress=None, cancel_check=None) -> CandidateResult:
        best_pass: Optional[CandidateResult] = None
        best_any: Optional[CandidateResult] = None
        attempts = max(1, self.config.candidate_attempts)
        for attempt in range(1, attempts + 1):
            if cancel_check and cancel_check():
                break
            level = self._build_candidate(attempt)
            errors, warnings = self.validator.validate(level)
            if errors:
                score = SolverScoreResult(status="INVALID", message="Validator errors.")
                candidate = CandidateResult(level, score, errors, warnings, 9999.0, attempt)
            else:
                score = self.solver.score_level(
                    level,
                    phases=[phase.to_score_phase() for phase in self.config.normalized_phases()],
                    cancel_check=cancel_check,
                )
                candidate = CandidateResult(level, score, errors, warnings, self._target_error(score), attempt)

            if best_any is None or candidate.target_error < best_any.target_error:
                best_any = candidate
            if candidate.score.status == "PASS":
                if best_pass is None or candidate.target_error < best_pass.target_error:
                    best_pass = candidate
            if progress:
                progress(attempt, attempts, candidate, best_pass or best_any)

        if best_pass is not None:
            return best_pass
        if best_any is not None:
            return best_any
        raise RuntimeError("Generator was cancelled before creating any candidate.")

    def _build_candidate(self, attempt: int) -> Dict[str, Any]:
        rows = max(1, int(self.config.rows))
        cols = max(1, int(self.config.cols))
        shooter_count = max(1, min(int(self.config.shooter_count), rows * cols))
        wall_count = max(0, min(int(self.config.wall_count), rows * cols - shooter_count))
        gate_count = max(1, int(self.config.gate_count))

        level = make_empty_level(rows, cols, gate_count)
        level["level"] = max(1, int(self.config.level_id))
        level["levelName"] = self.config.level_name or f"Level_{level['level']}"
        level["difficulty"] = self.config.difficulty if self.config.difficulty in LEVEL_DIFFICULTIES else "Hard"
        level["category"] = max(0, int(self.config.category))
        level["time"] = max(0, int(self.config.time))
        level["gateSystem"]["maxVisibleTrayPerGate"] = max(1, int(self.config.max_visible_tray_per_gate))

        shooter_positions = self._choose_shooter_positions(rows, cols, shooter_count)
        colors = self._build_solution_colors(shooter_count)
        for index, (row, col) in enumerate(shooter_positions):
            find_cell(level, row, col)["entity"] = make_shooter_entity(
                row,
                col,
                colors[index],
                max(1, int(self.config.shooter_capacity)),
            )

        self._place_walls(level, shooter_positions, wall_count)
        self._place_obstacles(level, shooter_positions)
        self._build_gates(level, colors)
        normalize_runtime_level(level)
        return level

    def _choose_shooter_positions(self, rows: int, cols: int, count: int) -> List[Tuple[int, int]]:
        positions: List[Tuple[int, int]] = []
        column_order = list(range(cols))
        self.rng.shuffle(column_order)
        for row in range(rows):
            columns = list(column_order)
            if row > 0:
                self.rng.shuffle(columns)
            for col in columns:
                positions.append((row, col))
                if len(positions) >= count:
                    return positions
        return positions

    def _place_walls(
        self,
        level: Dict[str, Any],
        shooter_positions: Sequence[Tuple[int, int]],
        wall_count: int,
    ) -> None:
        rows = level["grid"]["rows"]
        cols = level["grid"]["columns"]
        shooter_set = set(shooter_positions)
        candidates = [(row, col) for row in range(rows) for col in range(cols) if (row, col) not in shooter_set]
        self.rng.shuffle(candidates)
        for row, col in candidates[:wall_count]:
            find_cell(level, row, col)["entity"] = make_wall_entity(row, col)

    def _place_obstacles(
        self,
        level: Dict[str, Any],
        shooter_positions: Sequence[Tuple[int, int]],
    ) -> None:
        phases = self.config.normalized_phases()
        if not GRID_OBSTACLE_TYPES:
            return
        total_intensity = sum(max(0, int(phase.obstacle_pressure)) for phase in phases)
        if total_intensity <= 0:
            return
        max_obstacles = min(len(shooter_positions), max(1, total_intensity))
        late_positions = list(shooter_positions[len(shooter_positions) // 3 :])
        self.rng.shuffle(late_positions)
        obstacles = []
        for index, (row, col) in enumerate(late_positions[:max_obstacles], start=1):
            obstacles.append(
                {
                    "obstacleId": short_id("ice"),
                    "type": "IceBlock",
                    "hp": 1 + (index % 3),
                    "blocksPath": False,
                    "locksShooter": True,
                    "shape": {
                        "type": "CustomCells",
                        "origin": {"row": row, "column": col},
                        "width": 1,
                        "height": 1,
                        "cells": [{"row": row, "column": col}],
                    },
                }
            )
        level.setdefault("grid", {})["obstacles"] = obstacles

    def _build_solution_colors(self, count: int) -> List[str]:
        palette = [color for color in DEFAULT_GENERATOR_COLORS if color in BALL_COLORS][: max(1, self.config.color_count)]
        if not palette:
            palette = ["Blue"]
        phases = self.config.normalized_phases()
        colors: List[str] = []
        previous = self.rng.choice(palette)
        for click_index in range(1, count + 1):
            phase = self._phase_for_click(phases, click_index)
            repeat_chance = min(0.75, 0.12 + phase.same_color_route * 0.18)
            switch_pressure = min(0.85, 0.18 + phase.conveyor_pressure * 0.16)
            if colors and self.rng.random() < repeat_chance:
                color = previous
            elif self.rng.random() < switch_pressure:
                options = [color for color in palette if color != previous] or palette
                color = self.rng.choice(options)
            else:
                color = self.rng.choice(palette)
            colors.append(color)
            previous = color
        return colors

    def _phase_for_click(self, phases: Sequence[GeneratorPhase], click_index: int) -> GeneratorPhase:
        for phase in phases:
            if phase.start_click <= click_index <= phase.end_click:
                return phase
        return phases[-1]

    def _build_gates(self, level: Dict[str, Any], solution_colors: Sequence[str]) -> None:
        gate_count = level["gateSystem"]["gateCount"]
        gates = [{"gateIndex": gate_index, "trayQueue": []} for gate_index in range(gate_count)]
        tray_unit = max(1, int(self.config.tray_unit))
        capacity = max(1, int(self.config.shooter_capacity))
        for click_index, color in enumerate(solution_colors):
            gate_index = click_index % gate_count
            remaining = capacity
            while remaining > 0:
                required = min(tray_unit, remaining)
                gates[gate_index]["trayQueue"].append(
                    {
                        "trayId": short_id("t"),
                        "layers": [{"colorId": color, "requiredCount": required}],
                    }
                )
                remaining -= required
        level["gateSystem"]["gates"] = gates

    def _target_error(self, score: SolverScoreResult) -> float:
        if score.status != "PASS":
            return 9999.0
        if not score.phase_scores:
            return abs(score.overall_score - self._overall_target())
        return sum(abs(phase.delta) for phase in score.phase_scores) / max(1, len(score.phase_scores))

    def _overall_target(self) -> float:
        phases = self.config.normalized_phases()
        return sum(phase.target_score for phase in phases) / max(1, len(phases))


def build_config_from_template(template: Dict[str, Any], base: GeneratorConfig) -> GeneratorConfig:
    config = copy.deepcopy(base)
    level = copy.deepcopy(template)
    normalize_runtime_level(level)
    grid = level.get("grid", {})
    gate_system = level.get("gateSystem", {})
    cells = grid.get("cells", [])
    shooters = [cell for cell in cells if (cell.get("entity") or {}).get("type") == "Shooter"]
    walls = [cell for cell in cells if (cell.get("entity") or {}).get("type") == "Wall"]
    colors = {
        cell.get("entity", {}).get("shooter", {}).get("colorId")
        for cell in shooters
        if cell.get("entity", {}).get("shooter", {}).get("colorId") in BALL_COLORS
    }
    capacities = [
        int(cell.get("entity", {}).get("shooter", {}).get("capacity", config.shooter_capacity) or config.shooter_capacity)
        for cell in shooters
    ]
    config.rows = int(grid.get("rows", config.rows))
    config.cols = int(grid.get("columns", config.cols))
    config.gate_count = int(gate_system.get("gateCount", config.gate_count))
    config.max_visible_tray_per_gate = int(
        gate_system.get("maxVisibleTrayPerGate", config.max_visible_tray_per_gate)
    )
    config.time = int(level.get("time", config.time))
    config.difficulty = level.get("difficulty", config.difficulty)
    config.category = int(level.get("category", config.category))
    config.shooter_count = len(shooters) or config.shooter_count
    config.wall_count = len(walls)
    config.color_count = max(1, len([color for color in colors if color and color != "None"]))
    if capacities:
        config.shooter_capacity = max(1, round(sum(capacities) / len(capacities)))
    return config


def export_level(path: str, level: Dict[str, Any], overwrite: bool = False) -> bool:
    if os.path.exists(path) and not overwrite:
        return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(level, fh, ensure_ascii=False, indent=2)
    return True

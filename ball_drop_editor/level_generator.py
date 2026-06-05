from __future__ import annotations

import copy
import json
import os
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .constants import BALL_COLORS, GRID_OBSTACLE_TYPES, LEVEL_DIFFICULTIES
from .level_data import (
    detect_mechanics,
    find_cell,
    make_empty_level,
    make_shooter_entity,
    make_tunnel_entity,
    make_wall_entity,
    normalize_runtime_level,
)
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
    tunnel_pressure: int = 0
    obstacle_pressure: int = 0
    obstacle_types: List[str] = field(default_factory=lambda: ["IceBlock", "IceTray"])

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
    color_mode: str = "Auto"
    manual_colors: List[str] = field(default_factory=list)
    allowed_devices: List[str] = field(default_factory=lambda: ["Wall", "Tunnel", "IceBlock", "IceTray"])
    tunnel_queue_min: int = 1
    tunnel_queue_max: int = 2
    empty_cell_strategy: str = "Add Shooters"
    shooter_capacity: int = 9
    tray_unit: int = 3
    solver_budget: float = 20.0
    candidate_attempts: int = 30
    phases: List[GeneratorPhase] = field(default_factory=list)
    seed: Optional[int] = None
    reference_level: Optional[Dict[str, Any]] = None
    reference_curve_targets: List[float] = field(default_factory=list)
    reference_min_difference: float = 0.0

    def normalized_phases(self) -> List[GeneratorPhase]:
        if self.phases:
            return sorted(self.phases, key=lambda phase: (phase.start_click, phase.end_click))
        third = max(1, self.shooter_count // 3)
        return [
            GeneratorPhase("Warmup", 1, third, "Easy", 1, 1, 1, 0, 0, 0),
            GeneratorPhase("Spike A", third + 1, third * 2, "Hard", 3, 2, 2, 2, 1, 1),
            GeneratorPhase("Spike B", third * 2 + 1, self.shooter_count, "VeryHard", 3, 3, 3, 2, 2, 2),
        ]


@dataclass
class CandidateResult:
    level: Dict[str, Any]
    score: SolverScoreResult
    errors: List[str]
    warnings: List[str]
    target_error: float
    attempt: int
    notes: List[str] = field(default_factory=list)
    structural_difference: float = 0.0
    reference_curve_error: float = 0.0


class DifficultyCurveGenerator:
    def __init__(self, config: GeneratorConfig):
        self.config = copy.deepcopy(config)
        self.rng = random.Random(config.seed)
        self.validator = LevelValidator()
        self.solver = SolverScoreAdapter(time_budget=config.solver_budget)
        self._candidate_notes: List[str] = []

    def _note(self, message: str) -> None:
        if message not in self._candidate_notes:
            self._candidate_notes.append(message)

    def _note_final_counts(self, level: Dict[str, Any]) -> None:
        cells = level.get("grid", {}).get("cells", []) or []
        shooters = 0
        walls = 0
        tunnels = 0
        tunnel_queue = 0
        empty = 0
        for cell in cells:
            entity = cell.get("entity")
            if not entity:
                empty += 1
                continue
            entity_type = entity.get("type")
            if entity_type == "Shooter":
                shooters += 1
            elif entity_type == "Wall":
                walls += 1
            elif entity_type == "Tunnel":
                tunnels += 1
                tunnel_queue += len(entity.get("shooterQueue", []) or [])
        rows = level.get("grid", {}).get("rows", 0)
        cols = level.get("grid", {}).get("columns", 0)
        self._note(
            f"Final generated counts: grid={rows}x{cols}, shooters={shooters}, walls={walls}, "
            f"tunnels={tunnels}, tunnelQueue={tunnel_queue}, empty={empty}."
        )

    def _reference_structural_difference(self, candidate_level: Dict[str, Any]) -> float:
        if not self.config.reference_level:
            return 0.0
        return structural_difference(self.config.reference_level, candidate_level)

    def _reference_curve_error(self, score: SolverScoreResult) -> float:
        targets = [float(value) for value in self.config.reference_curve_targets if value is not None]
        if not targets:
            return 0.0
        if score.status != "PASS" or not score.per_click_scores:
            return 9999.0
        actual = [float(item.score) for item in score.per_click_scores]
        sampled = _resample_values(actual, len(targets))
        return sum(abs(left - right) for left, right in zip(sampled, targets)) / max(1, len(targets))

    def generate_best(self, progress=None, cancel_check=None) -> CandidateResult:
        best_pass: Optional[CandidateResult] = None
        best_any: Optional[CandidateResult] = None
        attempts = max(1, self.config.candidate_attempts)
        for attempt in range(1, attempts + 1):
            if cancel_check and cancel_check():
                break
            level = self._build_candidate(attempt)
            notes = list(self._candidate_notes)
            structural_difference = self._reference_structural_difference(level)
            errors, warnings = self.validator.validate(level)
            if errors:
                score = SolverScoreResult(status="INVALID", message="Validator errors.")
                candidate = CandidateResult(
                    level,
                    score,
                    errors,
                    warnings,
                    9999.0,
                    attempt,
                    notes,
                    structural_difference,
                    9999.0 if self.config.reference_curve_targets else 0.0,
                )
            else:
                score = self.solver.score_level(
                    level,
                    phases=[phase.to_score_phase() for phase in self.config.normalized_phases()],
                    cancel_check=cancel_check,
                )
                reference_curve_error = self._reference_curve_error(score)
                target_error = self._target_error(score)
                if self.config.reference_curve_targets and score.status == "PASS":
                    target_error = (target_error + reference_curve_error) / 2.0
                candidate_notes = list(notes)
                if self.config.reference_level:
                    candidate_notes.append(
                        f"Reference structural difference={structural_difference * 100:.1f}%, "
                        f"curve error={reference_curve_error:.1f}."
                    )
                    if (
                        score.status == "PASS"
                        and structural_difference < max(0.0, float(self.config.reference_min_difference))
                    ):
                        candidate_notes.append(
                            f"Reference candidate rejected: structural difference "
                            f"{structural_difference * 100:.1f}% < "
                            f"{float(self.config.reference_min_difference) * 100:.1f}%."
                        )
                        score = copy.deepcopy(score)
                        score.status = "FAIL"
                        score.message = "Reference structural difference below threshold."
                candidate = CandidateResult(
                    level,
                    score,
                    errors,
                    warnings,
                    target_error,
                    attempt,
                    candidate_notes,
                    structural_difference,
                    reference_curve_error,
                )

            if best_any is None or candidate.target_error < best_any.target_error:
                best_any = candidate
            pass_meets_reference = (
                not self.config.reference_level
                or candidate.structural_difference >= max(0.0, float(self.config.reference_min_difference))
            )
            if candidate.score.status == "PASS" and pass_meets_reference:
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
        self._candidate_notes = []
        rows = max(1, int(self.config.rows))
        cols = max(1, int(self.config.cols))
        rows, cols = self._reference_grid_size(rows, cols, attempt)
        requested_shooter_count = max(1, int(self.config.shooter_count))
        requested_wall_count = max(0, int(self.config.wall_count))
        if "Wall" not in self.config.allowed_devices:
            requested_wall_count = 0
        rows, cols = self._effective_grid_size(rows, cols, requested_shooter_count, requested_wall_count)
        total_cells = rows * cols
        wall_positions = self._choose_wall_positions(rows, cols, requested_wall_count)
        wall_count = len(wall_positions)
        if wall_count < requested_wall_count:
            self._note(
                f"Reduced walls from {requested_wall_count} to {wall_count} because edge rows/columns cannot be all wall."
            )
        shooter_positions = self._ordered_non_wall_positions(rows, cols, wall_positions)
        shooter_count = len(shooter_positions)
        if requested_shooter_count < shooter_count:
            self._note(
                f"Grid {rows}x{cols} has {total_cells} cells but requested {requested_shooter_count} shooters "
                f"+ {wall_count} walls leaves empty cells. Added {shooter_count - requested_shooter_count} shooters."
            )
        elif requested_shooter_count > shooter_count:
            self._note(
                f"Requested {requested_shooter_count} shooters but grid has {shooter_count} non-wall cells; "
                f"using {shooter_count} physical shooter/tunnel slots."
            )
        gate_count = max(1, int(self.config.gate_count))

        level = make_empty_level(rows, cols, gate_count)
        level["level"] = max(1, int(self.config.level_id))
        level["levelName"] = f"Level_{level['level']}"
        level["difficulty"] = self.config.difficulty if self.config.difficulty in LEVEL_DIFFICULTIES else "Hard"
        level["category"] = max(0, int(self.config.category))
        level["time"] = max(0, int(self.config.time))
        level["gateSystem"]["maxVisibleTrayPerGate"] = max(1, int(self.config.max_visible_tray_per_gate))

        colors = self._build_solution_colors(shooter_count)
        tunnel_groups = self._choose_tunnel_groups(shooter_positions)
        tunnel_consumed = {
            color_index
            for color_indices in tunnel_groups.values()
            for color_index in color_indices
        }
        replacement_indices = sorted(index for index in tunnel_consumed if index not in tunnel_groups)
        replacement_colors = self._build_solution_colors(len(replacement_indices)) if replacement_indices else []
        replacement_by_index = dict(zip(replacement_indices, replacement_colors))
        solution_colors = list(colors) + replacement_colors
        if replacement_indices:
            self._note(
                f"Refilled {len(replacement_indices)} tunnel-queued grid cells with replacement shooters to remove empty cells."
            )

        for index, (row, col) in enumerate(shooter_positions):
            if index in tunnel_groups:
                queue_text = ", ".join(
                    f"{colors[color_index]}:{max(1, int(self.config.shooter_capacity))}"
                    for color_index in tunnel_groups[index]
                )
                find_cell(level, row, col)["entity"] = make_tunnel_entity(
                    row,
                    col,
                    "Up",
                    queue_text,
                )
            elif index in tunnel_consumed:
                find_cell(level, row, col)["entity"] = make_shooter_entity(
                    row,
                    col,
                    replacement_by_index[index],
                    max(1, int(self.config.shooter_capacity)),
                )
            else:
                find_cell(level, row, col)["entity"] = make_shooter_entity(
                    row,
                    col,
                    colors[index],
                    max(1, int(self.config.shooter_capacity)),
                )

        self._place_walls(level, wall_positions)
        solution_colors.extend(self._fill_empty_cells(level))
        self._place_obstacles(level, shooter_positions)
        self._build_gates(level, solution_colors)
        self._place_ice_trays(level)
        normalize_runtime_level(level)
        level["mechanics"] = detect_mechanics(level)
        self._note_final_counts(level)
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

    def _effective_grid_size(
        self,
        rows: int,
        cols: int,
        requested_shooter_count: int,
        requested_wall_count: int,
    ) -> Tuple[int, int]:
        if self.config.empty_cell_strategy != "Compact Grid Then Add Shooters":
            return rows, cols
        target_cells = max(1, requested_shooter_count + requested_wall_count)
        if target_cells >= rows * cols:
            return rows, cols

        best: Optional[Tuple[int, int, int, int, int]] = None
        for candidate_rows in range(1, rows + 1):
            for candidate_cols in range(1, cols + 1):
                area = candidate_rows * candidate_cols
                if area < target_cells:
                    continue
                score = (area - target_cells, abs(candidate_rows - rows) + abs(candidate_cols - cols), area)
                if best is None or score < best[:3]:
                    best = (score[0], score[1], score[2], candidate_rows, candidate_cols)
        if best is None:
            return rows, cols
        compact_rows, compact_cols = best[3], best[4]
        if compact_rows != rows or compact_cols != cols:
            self._note(
                f"Compacted grid from {rows}x{cols} to {compact_rows}x{compact_cols} "
                f"for {target_cells} requested shooter/wall cells."
            )
        return compact_rows, compact_cols

    def _reference_grid_size(self, rows: int, cols: int, attempt: int) -> Tuple[int, int]:
        if not self.config.reference_level or self.config.reference_min_difference <= 0:
            return rows, cols
        ref_grid = self.config.reference_level.get("grid", {}) if isinstance(self.config.reference_level, dict) else {}
        ref_rows = max(1, int(ref_grid.get("rows", rows) or rows))
        ref_cols = max(1, int(ref_grid.get("columns", cols) or cols))
        if (rows, cols) != (ref_rows, ref_cols):
            return rows, cols

        variants: List[Tuple[float, int, int, int]] = []
        for candidate_rows in range(max(1, rows - 3), rows + 4):
            for candidate_cols in range(max(1, cols - 3), cols + 4):
                if (candidate_rows, candidate_cols) == (rows, cols):
                    continue
                diff = _rect_shape_difference(ref_rows, ref_cols, candidate_rows, candidate_cols)
                if diff < self.config.reference_min_difference:
                    continue
                area_delta = abs(candidate_rows * candidate_cols - rows * cols)
                variants.append((area_delta, candidate_rows + candidate_cols, candidate_rows, candidate_cols))
        if not variants:
            return rows, cols
        variants.sort()
        _, _, variant_rows, variant_cols = variants[(max(1, attempt) - 1) % len(variants)]
        self._note(
            f"Reference mode changed grid from {rows}x{cols} to {variant_rows}x{variant_cols} "
            f"to enforce structural difference without counting color."
        )
        return variant_rows, variant_cols

    def _choose_wall_positions(self, rows: int, cols: int, wall_count: int) -> set[Tuple[int, int]]:
        if wall_count <= 0:
            return set()
        candidates = [(row, col) for row in range(rows) for col in range(cols)]
        self.rng.shuffle(candidates)
        wall_positions: set[Tuple[int, int]] = set()
        for row, col in candidates:
            if len(wall_positions) >= wall_count:
                break
            candidate = set(wall_positions)
            candidate.add((row, col))
            if self._has_full_edge_wall(candidate, rows, cols):
                continue
            wall_positions = candidate
        return wall_positions

    def _has_full_edge_wall(self, wall_positions: set[Tuple[int, int]], rows: int, cols: int) -> bool:
        if rows <= 0 or cols <= 0:
            return False
        top_full = all((0, col) in wall_positions for col in range(cols))
        bottom_full = all((rows - 1, col) in wall_positions for col in range(cols))
        left_full = all((row, 0) in wall_positions for row in range(rows))
        right_full = all((row, cols - 1) in wall_positions for row in range(rows))
        return top_full or bottom_full or left_full or right_full

    def _ordered_non_wall_positions(
        self,
        rows: int,
        cols: int,
        wall_positions: set[Tuple[int, int]],
    ) -> List[Tuple[int, int]]:
        positions: List[Tuple[int, int]] = []
        column_order = list(range(cols))
        self.rng.shuffle(column_order)
        for row in range(rows):
            columns = list(column_order)
            if row > 0:
                self.rng.shuffle(columns)
            for col in columns:
                if (row, col) not in wall_positions:
                    positions.append((row, col))
        return positions

    def _place_walls(
        self,
        level: Dict[str, Any],
        wall_positions: set[Tuple[int, int]],
    ) -> None:
        for row, col in wall_positions:
            find_cell(level, row, col)["entity"] = make_wall_entity(row, col)

    def _fill_empty_cells(self, level: Dict[str, Any]) -> List[str]:
        empty_cells = [
            cell
            for cell in level.get("grid", {}).get("cells", []) or []
            if cell.get("entity") is None
        ]
        if not empty_cells:
            return []
        colors = self._build_solution_colors(len(empty_cells))
        for cell, color in zip(empty_cells, colors):
            cell["entity"] = make_shooter_entity(
                cell.get("row", 0),
                cell.get("column", 0),
                color,
                max(1, int(self.config.shooter_capacity)),
            )
        self._note(f"Filled {len(empty_cells)} unexpected empty cells with shooters.")
        return colors

    def _place_obstacles(
        self,
        level: Dict[str, Any],
        shooter_positions: Sequence[Tuple[int, int]],
    ) -> None:
        if "IceBlock" not in self.config.allowed_devices:
            return
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

    def _place_ice_trays(self, level: Dict[str, Any]) -> None:
        if "IceTray" not in self.config.allowed_devices:
            return
        phases = self.config.normalized_phases()
        total_intensity = sum(max(0, int(phase.obstacle_pressure)) for phase in phases)
        if total_intensity <= 0:
            return

        gates = level.get("gateSystem", {}).get("gates", []) or []
        if sum(1 for gate in gates if gate.get("trayQueue")) < 2:
            self._note("Ice Tray requested, but at least two gates with trays are needed for dynamic neighbor thaw.")
            return

        depth_counts: Dict[int, int] = {}
        candidates: List[Tuple[int, int, Dict[str, Any]]] = []
        for gate in gates:
            gate_index = int(gate.get("gateIndex", 0) or 0)
            for tray_index, tray in enumerate(gate.get("trayQueue", []) or []):
                depth_counts[tray_index] = depth_counts.get(tray_index, 0) + 1
                if tray_index == 0:
                    continue
                if any(modifier.get("type") == "Ice" for modifier in tray.get("modifiers", []) or []):
                    continue
                candidates.append((tray_index, gate_index, tray))

        candidates = [
            item
            for item in candidates
            if depth_counts.get(item[0], 0) >= 2
        ]
        if not candidates:
            self._note("Ice Tray requested, but no non-front tray had a possible dynamic neighbor.")
            return

        self.rng.shuffle(candidates)
        max_ice_trays = min(len(candidates), max(1, total_intensity))
        frozen_by_depth: Dict[int, int] = {}
        placed = 0
        for tray_index, _gate_index, tray in candidates:
            if placed >= max_ice_trays:
                break
            frozen_at_depth = frozen_by_depth.get(tray_index, 0)
            if frozen_at_depth + 1 >= depth_counts.get(tray_index, 0):
                continue
            modifiers = [
                copy.deepcopy(modifier)
                for modifier in tray.get("modifiers", []) or []
                if modifier.get("type") != "Ice"
            ]
            modifiers.append({"type": "Ice", "hp": 3})
            tray["modifiers"] = modifiers
            frozen_by_depth[tray_index] = frozen_at_depth + 1
            placed += 1

        if placed:
            self._note(f"Placed {placed} Ice Tray modifier(s) with hp=3.")
        else:
            self._note("Ice Tray requested, but placement was skipped to avoid freezing an entire tray row.")

    def _build_solution_colors(self, count: int) -> List[str]:
        count = max(0, int(count))
        if count <= 0:
            return []
        palette = self._active_palette()
        if not palette:
            palette = ["Blue"]
        phases = self.config.normalized_phases()
        guaranteed = list(palette)
        self.rng.shuffle(guaranteed)
        if count < len(guaranteed):
            self._note(
                f"Only {count} color slot(s) available for requested {len(guaranteed)} colors; "
                f"using {count} color(s)."
            )
            guaranteed = guaranteed[:count]
        colors: List[str] = guaranteed[:count]
        previous = colors[-1] if colors else self.rng.choice(palette)
        for click_index in range(len(colors) + 1, count + 1):
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

    def _active_palette(self) -> List[str]:
        requested = max(1, int(self.config.color_count))
        if self.config.color_mode == "Manual":
            selected = [
                color
                for color in self.config.manual_colors
                if color in BALL_COLORS and color != "None"
            ]
            return selected[:requested] or selected
        auto_palette: List[str] = []
        for color in DEFAULT_GENERATOR_COLORS + BALL_COLORS:
            if color == "None" or color not in BALL_COLORS or color in auto_palette:
                continue
            auto_palette.append(color)
        if requested > len(auto_palette):
            self._note(f"Auto requested {requested} colors, but only {len(auto_palette)} colors are available.")
        return auto_palette[:requested]

    def _choose_tunnel_groups(self, shooter_positions: Sequence[Tuple[int, int]]) -> Dict[int, List[int]]:
        if "Tunnel" not in self.config.allowed_devices:
            return {}
        phases = self.config.normalized_phases()
        total_intensity = sum(max(0, int(phase.tunnel_pressure)) for phase in phases)
        if total_intensity <= 0:
            return {}
        by_pos = {position: index for index, position in enumerate(shooter_positions)}
        candidates: List[int] = []
        for index, (row, col) in enumerate(shooter_positions):
            if row <= 0:
                continue
            output_index = by_pos.get((row - 1, col))
            if output_index is None or output_index >= index:
                continue
            candidates.append(index)
        self.rng.shuffle(candidates)
        groups: Dict[int, List[int]] = {}
        consumed: set[int] = set()
        blocked_outputs: set[int] = set()
        max_tunnels = min(len(candidates), max(1, total_intensity))
        by_index = {index: position for index, position in enumerate(shooter_positions)}
        skipped_for_min = 0
        queue_min = max(1, int(self.config.tunnel_queue_min))
        queue_max = max(queue_min, int(self.config.tunnel_queue_max))
        for index in candidates:
            row, col = by_index[index]
            output_index = by_pos.get((row - 1, col))
            if output_index is None or output_index in groups or output_index in blocked_outputs or index in consumed:
                continue
            available_indices = [index]
            for next_index in range(index + 1, len(shooter_positions)):
                if len(available_indices) >= queue_max:
                    break
                if next_index in consumed or next_index in groups or next_index == output_index:
                    continue
                available_indices.append(next_index)
            if len(available_indices) < queue_min:
                skipped_for_min += 1
                continue
            queue_len = self.rng.randint(queue_min, min(queue_max, len(available_indices)))
            queue_indices = available_indices[:queue_len]
            groups[index] = queue_indices
            consumed.update(queue_indices)
            blocked_outputs.add(output_index)
            if len(groups) >= max_tunnels:
                break
        if total_intensity > 0:
            if groups:
                self._note(
                    f"Created {len(groups)} tunnel(s) with queue length in [{queue_min}, {queue_max}]."
                )
            if skipped_for_min:
                self._note(
                    f"Skipped {skipped_for_min} tunnel candidate(s) because Tunnel Queue Min={queue_min} "
                    f"requires enough queued shooters."
                )
            elif not groups and not candidates:
                self._note("Tunnel pressure requested, but no valid tunnel output cells were available.")
            elif not groups:
                self._note("Tunnel pressure requested, but no candidate survived the tunnel placement constraints.")
        return groups

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


def _resample_values(values: Sequence[float], target_count: int) -> List[float]:
    if target_count <= 0:
        return []
    if not values:
        return [0.0] * target_count
    if target_count == 1:
        return [float(values[0])]
    if len(values) == 1:
        return [float(values[0])] * target_count
    result: List[float] = []
    source_max = len(values) - 1
    for index in range(target_count):
        position = source_max * (index / max(1, target_count - 1))
        left = int(position)
        right = min(source_max, left + 1)
        ratio = position - left
        result.append(float(values[left]) * (1.0 - ratio) + float(values[right]) * ratio)
    return result


def _rect_shape_difference(ref_rows: int, ref_cols: int, rows: int, cols: int) -> float:
    max_rows = max(ref_rows, rows)
    max_cols = max(ref_cols, cols)
    max_area = max(1, max_rows * max_cols)
    common_area = min(ref_rows, rows) * min(ref_cols, cols)
    return (max_area - common_area) / max_area


def structural_difference(reference: Dict[str, Any], candidate: Dict[str, Any]) -> float:
    ref = copy.deepcopy(reference)
    cand = copy.deepcopy(candidate)
    normalize_runtime_level(ref)
    normalize_runtime_level(cand)

    ref_grid = ref.get("grid", {}) or {}
    cand_grid = cand.get("grid", {}) or {}
    ref_rows = max(1, int(ref_grid.get("rows", 1) or 1))
    ref_cols = max(1, int(ref_grid.get("columns", 1) or 1))
    cand_rows = max(1, int(cand_grid.get("rows", 1) or 1))
    cand_cols = max(1, int(cand_grid.get("columns", 1) or 1))
    max_rows = max(ref_rows, cand_rows)
    max_cols = max(ref_cols, cand_cols)
    max_cells = max(1, max_rows * max_cols)

    ref_cells = {
        (cell.get("row"), cell.get("column")): _cell_structure_signature(cell.get("entity"))
        for cell in ref_grid.get("cells", []) or []
    }
    cand_cells = {
        (cell.get("row"), cell.get("column")): _cell_structure_signature(cell.get("entity"))
        for cell in cand_grid.get("cells", []) or []
    }
    cell_mismatches = 0
    for row in range(max_rows):
        for col in range(max_cols):
            ref_sig = ref_cells.get((row, col), "Missing")
            cand_sig = cand_cells.get((row, col), "Missing")
            if ref_sig != cand_sig:
                cell_mismatches += 1
    cell_score = cell_mismatches / max_cells

    ref_obstacles = _obstacle_structure_signatures(ref_grid)
    cand_obstacles = _obstacle_structure_signatures(cand_grid)
    obstacle_union = ref_obstacles | cand_obstacles
    obstacle_score = 0.0
    if obstacle_union:
        obstacle_score = len(ref_obstacles ^ cand_obstacles) / max(1, len(obstacle_union))

    grid_score = _rect_shape_difference(ref_rows, ref_cols, cand_rows, cand_cols)
    combined = cell_score * 0.75 + obstacle_score * 0.20 + grid_score * 0.05
    return min(1.0, max(cell_score, obstacle_score, grid_score, combined))


def _cell_structure_signature(entity: Optional[Dict[str, Any]]) -> Any:
    if not entity:
        return "Empty"
    entity_type = entity.get("type")
    if entity_type == "Shooter":
        return "Shooter"
    if entity_type == "Wall":
        return "Wall"
    if entity_type == "Tunnel":
        return (
            "Tunnel",
            entity.get("outputDirection", "Up"),
            len(entity.get("shooterQueue", []) or []),
        )
    return entity_type or "Unknown"


def _obstacle_structure_signatures(grid: Dict[str, Any]) -> set[Any]:
    signatures: set[Any] = set()
    for obstacle in grid.get("obstacles", []) or []:
        shape = obstacle.get("shape", {}) or {}
        cells = tuple(
            sorted(
                (int(cell.get("row", 0) or 0), int(cell.get("column", 0) or 0))
                for cell in shape.get("cells", []) or []
            )
        )
        if not cells:
            origin = shape.get("origin", {}) or {}
            height = max(1, int(shape.get("height", 1) or 1))
            width = max(1, int(shape.get("width", 1) or 1))
            origin_row = int(origin.get("row", 0) or 0)
            origin_col = int(origin.get("column", 0) or 0)
            cells = tuple(
                (origin_row + row, origin_col + col)
                for row in range(height)
                for col in range(width)
            )
        signatures.add((obstacle.get("type"), shape.get("type"), cells))
    return signatures


def build_config_from_template(template: Dict[str, Any], base: GeneratorConfig) -> GeneratorConfig:
    config = copy.deepcopy(base)
    level = copy.deepcopy(template)
    normalize_runtime_level(level)
    grid = level.get("grid", {})
    gate_system = level.get("gateSystem", {})
    cells = grid.get("cells", [])
    shooters = [cell for cell in cells if (cell.get("entity") or {}).get("type") == "Shooter"]
    walls = [cell for cell in cells if (cell.get("entity") or {}).get("type") == "Wall"]
    tunnels = [cell for cell in cells if (cell.get("entity") or {}).get("type") == "Tunnel"]
    colors = {
        cell.get("entity", {}).get("shooter", {}).get("colorId")
        for cell in shooters
        if cell.get("entity", {}).get("shooter", {}).get("colorId") in BALL_COLORS
    }
    for cell in tunnels:
        for shooter in cell.get("entity", {}).get("shooterQueue", []) or []:
            color = shooter.get("colorId")
            if color in BALL_COLORS:
                colors.add(color)
    capacities = [
        int(cell.get("entity", {}).get("shooter", {}).get("capacity", config.shooter_capacity) or config.shooter_capacity)
        for cell in shooters
    ]
    for cell in tunnels:
        for shooter in cell.get("entity", {}).get("shooterQueue", []) or []:
            capacities.append(int(shooter.get("capacity", config.shooter_capacity) or config.shooter_capacity))
    config.rows = int(grid.get("rows", config.rows))
    config.cols = int(grid.get("columns", config.cols))
    config.gate_count = int(gate_system.get("gateCount", config.gate_count))
    config.max_visible_tray_per_gate = int(
        gate_system.get("maxVisibleTrayPerGate", config.max_visible_tray_per_gate)
    )
    config.time = int(level.get("time", config.time))
    config.difficulty = level.get("difficulty", config.difficulty)
    config.category = int(level.get("category", config.category))
    config.shooter_count = (len(shooters) + sum(len((cell.get("entity") or {}).get("shooterQueue", []) or []) for cell in tunnels)) or config.shooter_count
    config.wall_count = len(walls)
    config.color_count = max(1, len([color for color in colors if color and color != "None"]))
    config.manual_colors = [color for color in DEFAULT_GENERATOR_COLORS if color in colors]
    if capacities:
        config.shooter_capacity = max(1, round(sum(capacities) / len(capacities)))
    return config


def load_template_folder(folder: str) -> List[Dict[str, Any]]:
    if not os.path.isdir(folder):
        return []
    templates: List[Dict[str, Any]] = []
    for filename in sorted(os.listdir(folder)):
        if not filename.lower().endswith(".json"):
            continue
        path = os.path.join(folder, filename)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                level = json.load(fh)
            level["_templatePath"] = path
            templates.append(level)
        except Exception:
            continue
    return templates


def select_template_for_config(templates: Sequence[Dict[str, Any]], base: GeneratorConfig) -> Optional[Dict[str, Any]]:
    best_template: Optional[Dict[str, Any]] = None
    best_score: Optional[float] = None
    for template in templates:
        config = build_config_from_template(template, base)
        score = 0.0
        score += abs(config.color_count - base.color_count) * 12
        score += abs(config.shooter_count - base.shooter_count) * 2
        score += abs(config.wall_count - base.wall_count)
        score += abs(config.rows * config.cols - base.rows * base.cols)
        score += abs(config.gate_count - base.gate_count) * 5
        if config.difficulty != base.difficulty:
            score += 10
        if best_score is None or score < best_score:
            best_score = score
            best_template = template
    return best_template


def export_level(path: str, level: Dict[str, Any], overwrite: bool = False) -> bool:
    if os.path.exists(path) and not overwrite:
        return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(level, fh, ensure_ascii=False, indent=2)
    return True

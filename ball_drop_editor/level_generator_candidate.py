from __future__ import annotations

import copy
from collections import Counter
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .color_utils import SELECTABLE_BALL_COLORS
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
from .level_generator_analysis import _rect_shape_difference
from .level_generator_gates import build_tray_chunks, schedule_tray_chunks
from .level_generator_models import DEFAULT_GENERATOR_COLORS, GeneratorPhase
from .utils import short_id


class DifficultyCurveCandidateMixin:
    def _build_candidate(self, attempt: int) -> Dict[str, Any]:
        self._candidate_notes = []
        rows = max(1, int(self.config.rows))
        cols = max(1, int(self.config.cols))
        rows, cols = self._reference_grid_size(rows, cols, attempt)
        requested_shooter_count = max(1, int(self.config.shooter_count))
        requested_wall_count = self._device_target("Wall", max(0, int(self.config.wall_count)))
        if not self._device_enabled("Wall"):
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
        self._place_special_shooters(level)
        self._place_connected_groups(level)
        solution_colors = self._solution_colors_from_grid(level)
        self._build_gates(level, solution_colors)
        self._apply_phase_color_layout(level)
        self._place_obstacles(level)
        self._place_ice_shooters(level)
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
            f"to help reach the reference difference benchmark."
        )
        return variant_rows, variant_cols

    def _choose_wall_positions(self, rows: int, cols: int, wall_count: int) -> set[Tuple[int, int]]:
        if wall_count <= 0:
            return set()
        candidates = [(row, col) for row in range(rows) for col in range(cols)]
        unlock_weight = self._average_phase_weight("unlock_maze")
        if unlock_weight >= 1.0 and rows >= 3:
            center = (rows - 1) / 2.0
            candidates.sort(
                key=lambda position: (
                    1 if position[0] in {0, rows - 1} else 0,
                    abs(position[0] - center),
                    self.rng.random(),
                )
            )
        else:
            self.rng.shuffle(candidates)
        wall_positions: set[Tuple[int, int]] = set()
        for row, col in candidates:
            if len(wall_positions) >= wall_count:
                break
            candidate = set(wall_positions)
            candidate.add((row, col))
            if self._has_full_edge_wall(candidate, rows, cols):
                continue
            if not self._non_wall_cells_reach_top(candidate, rows, cols):
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

    def _non_wall_cells_reach_top(
        self,
        wall_positions: set[Tuple[int, int]],
        rows: int,
        cols: int,
    ) -> bool:
        non_walls = {
            (row, col)
            for row in range(rows)
            for col in range(cols)
            if (row, col) not in wall_positions
        }
        frontier = [position for position in non_walls if position[0] == 0]
        visited = set(frontier)
        while frontier:
            row, col = frontier.pop()
            for neighbor in (
                (row - 1, col),
                (row + 1, col),
                (row, col - 1),
                (row, col + 1),
            ):
                if neighbor in non_walls and neighbor not in visited:
                    visited.add(neighbor)
                    frontier.append(neighbor)
        return visited == non_walls

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
    ) -> None:
        allow_iceblock = self._device_enabled("IceBlock")
        allow_lockbar = self._device_enabled("LockBar")
        if not allow_iceblock and not allow_lockbar:
            return
        phases = self.config.normalized_phases()
        total_intensity = sum(max(0, int(phase.obstacle_pressure)) for phase in phases)
        iceblock_target = self._device_target("IceBlock", total_intensity)
        lockbar_target = self._device_target(
            "LockBar",
            max(1, total_intensity // 2) if total_intensity > 0 else 0,
        )
        if iceblock_target <= 0 and lockbar_target <= 0:
            return
        obstacles = level.setdefault("grid", {}).setdefault("obstacles", [])
        if allow_iceblock and iceblock_target > 0:
            protected_ids = self._protected_initial_shooter_ids(level)
            available_positions = [
                (row, col)
                for row, col, shooter in self._grid_shooter_entries(level)
                if id(shooter) not in protected_ids
            ]
            max_obstacles = min(len(available_positions), iceblock_target)
            late_positions = list(available_positions[len(available_positions) // 3 :])
            if len(late_positions) < max_obstacles:
                late_positions = list(available_positions)
            self.rng.shuffle(late_positions)
            for index, (row, col) in enumerate(late_positions[:max_obstacles], start=1):
                obstacles.append(
                    {
                        "obstacleId": short_id("ice"),
                        "type": "IceBlock",
                        "hp": max(1, int(self.config.tray_unit)) * (1 + ((index - 1) % 3)),
                        "shape": {
                            "type": "CustomCells",
                            "origin": {"row": row, "column": col},
                            "width": 1,
                            "height": 1,
                            "cells": [{"row": row, "column": col}],
                        },
                    }
                )
        if allow_lockbar and lockbar_target > 0:
            self._place_lock_bars(level, lockbar_target)

    def _place_special_shooters(self, level: Dict[str, Any]) -> None:
        if not self._device_enabled("Special"):
            return
        phases = self.config.normalized_phases()
        total_intensity = sum(max(0, int(phase.obstacle_pressure + phase.decision_trap)) for phase in phases)
        target_count = self._device_target(
            "Special",
            max(1, total_intensity // 2) if total_intensity > 0 else 0,
        )
        if target_count <= 0:
            return
        shooters = self._grid_shooter_entries(level)
        if not shooters:
            return
        self.rng.shuffle(shooters)
        count = min(len(shooters), target_count)
        placed = 0
        for _row, _col, shooter in shooters[:count]:
            modifiers = [
                copy.deepcopy(modifier)
                for modifier in shooter.get("modifiers", []) or []
                if modifier.get("type") != "Special"
            ]
            modifiers.append({"type": "Special"})
            shooter["modifiers"] = modifiers
            placed += 1
        if placed:
            self._note(f"Placed {placed} Special shooter modifier(s).")

    def _place_ice_shooters(self, level: Dict[str, Any]) -> None:
        if not self._device_enabled("IceShooter"):
            return
        phases = self.config.normalized_phases()
        total_intensity = sum(max(0, int(phase.obstacle_pressure)) for phase in phases)
        target_count = self._device_target(
            "IceShooter",
            max(1, total_intensity // 2) if total_intensity > 0 else 0,
        )
        if target_count <= 0:
            return

        records = self._color_records(level)
        if len(records) <= 1:
            self._note("Ice Shooter requested, but at least one shooter must remain available.")
            return

        ice_blocked = self._ice_blocked_positions(level)
        protected_ids = self._protected_initial_shooter_ids(level, ice_blocked)
        candidates = [
            record
            for record in records
            if id(record["shooter"]) not in protected_ids
            and not any(
                modifier.get("type") == "Ice"
                for modifier in record["shooter"].get("modifiers", []) or []
            )
            and (
                not record["is_grid_shooter"]
                or (record["row"], record["column"]) not in ice_blocked
            )
        ]
        self.rng.shuffle(candidates)
        candidates.sort(key=lambda record: record["unlock_order"], reverse=True)
        count = min(len(candidates), target_count)
        max_unlock_order = max((record["unlock_order"] for record in records), default=1.0)
        hp_values: List[int] = []
        for index, record in enumerate(candidates[:count], start=1):
            depth_ratio = record["unlock_order"] / max(1.0, max_unlock_order)
            hp = self._ice_unlock_hp(level, index, count, depth_ratio)
            modifiers = [
                copy.deepcopy(modifier)
                for modifier in record["shooter"].get("modifiers", []) or []
                if modifier.get("type") != "Ice"
            ]
            modifiers.append({"type": "Ice", "hp": hp})
            record["shooter"]["modifiers"] = modifiers
            hp_values.append(hp)

        if hp_values:
            self._note(
                f"Placed {len(hp_values)} Ice Shooter modifier(s) with per-ball unlock HP "
                f"{', '.join(str(value) for value in hp_values)}."
            )
        if count < target_count:
            self._note(
                f"Ice Shooter requested {target_count}, but only {count} placement(s) kept an initial shooter available."
            )

    def _place_connected_groups(self, level: Dict[str, Any]) -> None:
        if not self._device_enabled("ConnectedGroup"):
            return
        shooters = self._grid_shooter_entries(level)
        by_pos = {(row, col): shooter for row, col, shooter in shooters}
        candidates: List[Tuple[Tuple[int, int], Tuple[int, int]]] = []
        for row, col, _shooter in shooters:
            for neighbor in ((row, col + 1), (row + 1, col)):
                if neighbor in by_pos:
                    candidates.append(((row, col), neighbor))
        self.rng.shuffle(candidates)
        used_ids: set[str] = set()
        groups = level.setdefault("grid", {}).setdefault("shooterGroups", [])
        placed = 0
        fallback_count = max(
            1,
            sum(max(0, int(phase.decision_trap)) for phase in self.config.normalized_phases()) // 2,
        )
        if not any(phase.decision_trap > 0 for phase in self.config.normalized_phases()):
            fallback_count = 0
        max_groups = self._device_target("ConnectedGroup", fallback_count)
        for first, second in candidates:
            if placed >= max_groups:
                break
            first_shooter = by_pos[first]
            second_shooter = by_pos[second]
            first_id = first_shooter.get("shooterId")
            second_id = second_shooter.get("shooterId")
            if not first_id or not second_id or first_id in used_ids or second_id in used_ids:
                continue
            groups.append({
                "groupId": short_id("group"),
                "type": "Connected",
                "shooterIds": [first_id, second_id],
            })
            used_ids.update([first_id, second_id])
            placed += 1
        if placed:
            self._note(f"Created {placed} Connected shooter group(s).")
        else:
            self._note("Connected Group requested, but no adjacent shooter pairs were available.")

    def _place_lock_bars(self, level: Dict[str, Any], target_count: int) -> None:
        grid = level.setdefault("grid", {})
        rows = int(grid.get("rows", 0) or 0)
        cols = int(grid.get("columns", 0) or 0)
        if rows <= 0 or cols <= 0:
            return
        candidates = []
        for cell in grid.get("cells", []) or []:
            entity = cell.get("entity") or {}
            if entity.get("type") != "Wall":
                continue
            wall = (int(cell.get("row", 0) or 0), int(cell.get("column", 0) or 0))
            for direction in ("Up", "Down", "Left", "Right"):
                head = self._offset(wall, self._opposite_direction(direction))
                body = self._offset(wall, direction)
                trigger = self._offset(head, self._opposite_direction(direction))
                if not (self._inside(head, rows, cols) and self._inside(body, rows, cols) and self._inside(trigger, rows, cols)):
                    continue
                trigger_entity = self._cell_entity(level, trigger)
                if trigger_entity is None:
                    continue
                if self._cell_entity(level, head) is None and self._cell_entity(level, body) is None:
                    candidates.append((head, direction, [head, wall, body], trigger))
                elif (self._cell_entity(level, head) or {}).get("type") == "Shooter" and (self._cell_entity(level, body) or {}).get("type") == "Shooter":
                    candidates.append((head, direction, [head, wall, body], trigger))
        self.rng.shuffle(candidates)
        max_lockbars = min(len(candidates), max(0, target_count))
        placed = 0
        occupied: set[Tuple[int, int]] = set()
        for head, direction, cells, trigger in candidates:
            if placed >= max_lockbars:
                break
            if any(cell in occupied for cell in cells) or trigger in occupied:
                continue
            for index, position in enumerate(cells):
                if index != 1:
                    find_cell(level, position[0], position[1])["entity"] = None
            grid.setdefault("obstacles", []).append({
                "obstacleId": short_id("lock"),
                "type": "LockBar",
                "direction": direction,
                "length": 3,
                "shape": {
                    "type": "LineVertical" if direction in {"Up", "Down"} else "LineHorizontal",
                    "origin": {"row": head[0], "column": head[1]},
                    "width": 1 if direction in {"Up", "Down"} else 3,
                    "height": 3 if direction in {"Up", "Down"} else 1,
                    "cells": [],
                },
            })
            occupied.update(cells)
            occupied.add(trigger)
            placed += 1
        if placed:
            self._note(f"Placed {placed} LockBar obstacle(s).")
        else:
            self._note("LockBar requested, but no safe wall/head/trigger layout was found.")

    def _place_ice_trays(self, level: Dict[str, Any]) -> None:
        if not self._device_enabled("IceTray"):
            return
        phases = self.config.normalized_phases()
        total_intensity = sum(max(0, int(phase.obstacle_pressure)) for phase in phases)
        target_count = self._device_target("IceTray", total_intensity)
        if target_count <= 0:
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
        max_ice_trays = min(len(candidates), target_count)
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

    def _solution_colors_from_grid(self, level: Dict[str, Any]) -> List[str]:
        colors: List[str] = []
        for cell in level.get("grid", {}).get("cells", []) or []:
            entity = cell.get("entity") or {}
            if entity.get("type") == "Shooter":
                shooter = entity.get("shooter", {}) or {}
                repeat = 2 if self._shooter_has_special(shooter) else 1
                colors.extend([shooter.get("colorId", "Blue")] * repeat)
            elif entity.get("type") == "Tunnel":
                for shooter in entity.get("shooterQueue", []) or []:
                    repeat = 2 if self._shooter_has_special(shooter) else 1
                    colors.extend([shooter.get("colorId", "Blue")] * repeat)
        return [color for color in colors if color in BALL_COLORS and color != "None"]

    def _grid_shooter_entries(self, level: Dict[str, Any]) -> List[Tuple[int, int, Dict[str, Any]]]:
        entries: List[Tuple[int, int, Dict[str, Any]]] = []
        for cell in level.get("grid", {}).get("cells", []) or []:
            entity = cell.get("entity") or {}
            if entity.get("type") != "Shooter":
                continue
            shooter = entity.get("shooter")
            if not shooter:
                continue
            entries.append((int(cell.get("row", 0) or 0), int(cell.get("column", 0) or 0), shooter))
        return entries

    def _shooter_has_special(self, shooter: Dict[str, Any]) -> bool:
        return any(modifier.get("type") == "Special" for modifier in shooter.get("modifiers", []) or [])

    def _ice_blocked_positions(self, level: Dict[str, Any]) -> set[Tuple[int, int]]:
        positions: set[Tuple[int, int]] = set()
        for obstacle in level.get("grid", {}).get("obstacles", []) or []:
            if obstacle.get("type") != "IceBlock":
                continue
            shape = obstacle.get("shape", {}) or {}
            cells = shape.get("cells", []) or []
            if cells:
                positions.update(
                    (int(cell.get("row", 0) or 0), int(cell.get("column", 0) or 0))
                    for cell in cells
                )
                continue
            origin = shape.get("origin", {}) or {}
            origin_row = int(origin.get("row", 0) or 0)
            origin_col = int(origin.get("column", 0) or 0)
            height = max(1, int(shape.get("height", 1) or 1))
            width = max(1, int(shape.get("width", 1) or 1))
            positions.update(
                (origin_row + row, origin_col + col)
                for row in range(height)
                for col in range(width)
            )
        return positions

    def _protected_initial_shooter_ids(
        self,
        level: Dict[str, Any],
        blocked_positions: Optional[set[Tuple[int, int]]] = None,
    ) -> set[int]:
        blocked = blocked_positions or set()
        gates = level.get("gateSystem", {}).get("gates", []) or []
        demand = self._gate_colors_at_depth(gates, 0)
        protected: set[int] = set()
        protected_colors: set[str] = set()
        for record in self._color_records(level):
            color = str(record["shooter"].get("colorId", "None"))
            position = (record["row"], record["column"])
            if (
                color not in demand
                or color in protected_colors
                or not record["is_grid_shooter"]
                or record["row"] != 0
                or position in blocked
            ):
                continue
            protected.add(id(record["shooter"]))
            protected_colors.add(color)
        return protected

    def _ice_unlock_hp(
        self,
        level: Dict[str, Any],
        index: int,
        count: int,
        depth_ratio: float,
    ) -> int:
        total_balls = sum(
            self._effective_shooter_capacity(record["shooter"])
            for record in self._color_records(level)
        )
        tray_unit = max(1, int(self.config.tray_unit))
        if total_balls <= tray_unit:
            return tray_unit
        order_ratio = max(0.0, min(1.0, index / max(1, count + 1)))
        phase_pressure = (
            self._average_phase_weight("obstacle_pressure")
            + self._average_phase_weight("unlock_maze")
        ) / 6.0
        unlock_fraction = min(
            0.45,
            0.03
            + order_ratio * 0.20
            + max(0.0, min(1.0, depth_ratio)) * 0.10
            + phase_pressure * 0.10,
        )
        hp = int(round((total_balls * unlock_fraction) / tray_unit)) * tray_unit
        max_hp = max(tray_unit, total_balls - tray_unit)
        return max(tray_unit, min(max_hp, hp))

    def _cell_entity(self, level: Dict[str, Any], position: Tuple[int, int]) -> Optional[Dict[str, Any]]:
        return find_cell(level, position[0], position[1]).get("entity")

    def _offset(self, position: Tuple[int, int], direction: str) -> Tuple[int, int]:
        row, col = position
        if direction == "Up":
            return row - 1, col
        if direction == "Down":
            return row + 1, col
        if direction == "Left":
            return row, col - 1
        return row, col + 1

    def _opposite_direction(self, direction: str) -> str:
        return {
            "Up": "Down",
            "Down": "Up",
            "Left": "Right",
            "Right": "Left",
        }.get(direction, "Left")

    def _inside(self, position: Tuple[int, int], rows: int, cols: int) -> bool:
        return 0 <= position[0] < rows and 0 <= position[1] < cols

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
        counts = Counter(colors)
        last_seen = {color: index for index, color in enumerate(colors)}
        for click_index in range(len(colors) + 1, count + 1):
            phase = self._phase_for_click(phases, click_index)
            conveyor = self._phase_weight(phase.conveyor_pressure)
            same_route = self._phase_weight(phase.same_color_route)
            decision = self._phase_weight(phase.decision_trap)
            minimum_gap = 1 + conveyor
            scored: List[Tuple[Tuple[float, ...], str]] = []
            for color in palette:
                gap = (click_index - 1) - last_seen.get(color, -len(palette) - minimum_gap)
                gap_penalty = max(0, minimum_gap - gap)
                if same_route > 0 and counts[color] > 0:
                    repeat_preference = abs(gap - (minimum_gap + 1)) / max(1, same_route)
                else:
                    repeat_preference = float(counts[color])
                ambiguity_preference = -float(counts[color]) * (decision / 3.0)
                scored.append(
                    (
                        (
                            float(gap_penalty),
                            repeat_preference,
                            ambiguity_preference,
                            self.rng.random(),
                        ),
                        color,
                    )
                )
            color = min(scored, key=lambda item: item[0])[1]
            colors.append(color)
            counts[color] += 1
            last_seen[color] = click_index - 1
        return colors

    def _active_palette(self) -> List[str]:
        requested = max(1, int(self.config.color_count))
        if self.config.color_mode == "Manual":
            selected = [
                color
                for color in self.config.manual_colors
                if color in SELECTABLE_BALL_COLORS
            ]
            return selected[:requested] or selected
        auto_palette: List[str] = []
        for color in DEFAULT_GENERATOR_COLORS + list(SELECTABLE_BALL_COLORS):
            if color not in SELECTABLE_BALL_COLORS or color in auto_palette:
                continue
            auto_palette.append(color)
        if requested > len(auto_palette):
            self._note(f"Auto requested {requested} colors, but only {len(auto_palette)} colors are available.")
        return auto_palette[:requested]

    def _choose_tunnel_groups(self, shooter_positions: Sequence[Tuple[int, int]]) -> Dict[int, List[int]]:
        if not self._device_enabled("Tunnel"):
            return {}
        phases = self.config.normalized_phases()
        total_intensity = sum(max(0, int(phase.tunnel_pressure)) for phase in phases)
        target_count = self._device_target("Tunnel", total_intensity)
        if target_count <= 0:
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
        max_tunnels = min(len(candidates), target_count)
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

    def _device_enabled(self, device: str) -> bool:
        if device in self.config.exact_device_counts:
            return max(0, int(self.config.exact_device_counts[device])) > 0
        return device in self.config.allowed_devices

    def _device_target(self, device: str, fallback: int) -> int:
        if device in self.config.exact_device_counts:
            return max(0, int(self.config.exact_device_counts[device]))
        return max(0, int(fallback))

    def _phase_for_click(self, phases: Sequence[GeneratorPhase], click_index: int) -> GeneratorPhase:
        for phase in phases:
            if phase.start_click <= click_index <= phase.end_click:
                return phase
        return phases[-1]

    def _build_gates(self, level: Dict[str, Any], solution_colors: Sequence[str]) -> None:
        gate_count = level["gateSystem"]["gateCount"]
        chunks = build_tray_chunks(
            solution_colors,
            shooter_capacity=max(1, int(self.config.shooter_capacity)),
            tray_unit=max(1, int(self.config.tray_unit)),
        )
        gates, metrics = schedule_tray_chunks(chunks, gate_count, self.rng)
        level["gateSystem"]["gates"] = gates
        self._gate_layout_metrics = metrics
        self._note(
            "Tray layout: "
            f"maxRun={metrics.max_same_color_run}, adjacent={metrics.adjacent_same_pairs}, "
            f"duplicateDepth={metrics.duplicate_depth_pairs}, avgGap={metrics.average_repeat_gap:.1f}, "
            f"queueImbalance={metrics.queue_imbalance}."
        )
        if metrics.max_same_color_run > 1 or metrics.duplicate_depth_pairs > 0:
            self._note(
                "Some tray color repetition remains because the available color counts cannot fill every "
                "gate/depth position uniquely."
            )

    def _apply_phase_color_layout(self, level: Dict[str, Any]) -> None:
        records = self._color_records(level)
        if len(records) < 2:
            return
        gates = level.get("gateSystem", {}).get("gates", []) or []
        max_depth = max((len(gate.get("trayQueue", []) or []) for gate in gates), default=1)
        phases = self.config.normalized_phases()
        assigned_positions: Dict[Tuple[int, int], str] = {}
        placed_by_color: Dict[str, List[Tuple[int, int]]] = {}

        buckets: Dict[int, List[Dict[str, Any]]] = {}
        for record in records:
            buckets.setdefault(record["effective_capacity"], []).append(record)

        for bucket_records in buckets.values():
            available = Counter(record["shooter"].get("colorId", "Blue") for record in bucket_records)
            phase_progress: Dict[Tuple[str, int, int], Dict[str, int]] = {}
            ordered = sorted(
                bucket_records,
                key=lambda record: (
                    record["unlock_order"],
                    record["row"],
                    record["column"],
                    record["queue_index"],
                ),
            )
            for order_index, record in enumerate(ordered, start=1):
                phase = self._phase_for_click(phases, min(order_index, phases[-1].end_click))
                decision = self._phase_weight(phase.decision_trap)
                unlock = self._phase_weight(phase.unlock_maze)
                same_route = self._phase_weight(phase.same_color_route)
                progress = (order_index - 1) / max(1, len(ordered) - 1)
                depth = min(max_depth - 1, int(progress * max_depth))
                demand = self._gate_colors_at_depth(gates, depth)
                target_decoy = (0.10, 0.25, 0.40, 0.55)[decision]
                target_decoy = min(0.80, target_decoy + (unlock / 3.0) * (1.0 - progress) * 0.15)
                phase_key = (phase.name, phase.start_click, phase.end_click)
                progress_counts = phase_progress.setdefault(phase_key, {"total": 0, "decoys": 0})
                next_total = progress_counts["total"] + 1
                target_decoys = round(target_decoy * next_total)
                force_match = order_index == 1
                want_decoy = not force_match and progress_counts["decoys"] < target_decoys
                candidates = [color for color, count in available.items() if count > 0]
                preferred = [
                    color
                    for color in candidates
                    if (color not in demand) == want_decoy
                ]
                if preferred:
                    candidates = preferred

                position = (record["row"], record["column"])
                scored: List[Tuple[Tuple[float, ...], str]] = []
                for color in candidates:
                    neighbor_matches = sum(
                        assigned_positions.get(neighbor) == color
                        for neighbor in (
                            (position[0] - 1, position[1]),
                            (position[0] + 1, position[1]),
                            (position[0], position[1] - 1),
                            (position[0], position[1] + 1),
                        )
                    )
                    route_positions = placed_by_color.get(color, [])
                    route_match = any(
                        other_col != position[1]
                        and abs(other_row - position[0]) + abs(other_col - position[1]) > 1
                        for other_row, other_col in route_positions
                    )
                    scored.append(
                        (
                            (
                                float(neighbor_matches),
                                -float(same_route) if route_match else 0.0,
                                -float(available[color]),
                                self.rng.random(),
                            ),
                            color,
                        )
                    )
                selected = min(scored, key=lambda item: item[0])[1]
                record["shooter"]["colorId"] = selected
                available[selected] -= 1
                progress_counts["total"] += 1
                if selected not in demand:
                    progress_counts["decoys"] += 1
                assigned_positions[position] = selected
                placed_by_color.setdefault(selected, []).append(position)

        self._ensure_initial_demand_match(level, records)
        self._note("Applied phase-aware shooter color placement for decision, unlock, and route pressure.")

    def _color_records(self, level: Dict[str, Any]) -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []
        rows = max(1, int(level.get("grid", {}).get("rows", 1) or 1))
        for cell in level.get("grid", {}).get("cells", []) or []:
            row = int(cell.get("row", 0) or 0)
            column = int(cell.get("column", 0) or 0)
            entity = cell.get("entity") or {}
            if entity.get("type") == "Shooter" and entity.get("shooter"):
                shooter = entity["shooter"]
                records.append(
                    {
                        "shooter": shooter,
                        "row": row,
                        "column": column,
                        "queue_index": 0,
                        "unlock_order": float(row),
                        "effective_capacity": self._effective_shooter_capacity(shooter),
                        "is_grid_shooter": True,
                    }
                )
            elif entity.get("type") == "Tunnel":
                for queue_index, shooter in enumerate(entity.get("shooterQueue", []) or [], start=1):
                    records.append(
                        {
                            "shooter": shooter,
                            "row": row,
                            "column": column,
                            "queue_index": queue_index,
                            "unlock_order": float(rows + row + queue_index),
                            "effective_capacity": self._effective_shooter_capacity(shooter),
                            "is_grid_shooter": False,
                        }
                    )
        return records

    def _effective_shooter_capacity(self, shooter: Dict[str, Any]) -> int:
        multiplier = 2 if self._shooter_has_special(shooter) else 1
        return max(1, int(shooter.get("capacity", self.config.shooter_capacity) or 1)) * multiplier

    def _gate_colors_at_depth(self, gates: Sequence[Dict[str, Any]], depth: int) -> set[str]:
        colors: set[str] = set()
        for gate in gates:
            queue = gate.get("trayQueue", []) or []
            if not queue:
                continue
            tray = queue[min(depth, len(queue) - 1)]
            layers = tray.get("layers", []) or []
            if layers:
                colors.add(str(layers[0].get("colorId", "None")))
        return colors

    def _ensure_initial_demand_match(
        self,
        level: Dict[str, Any],
        records: Sequence[Dict[str, Any]],
    ) -> None:
        gates = level.get("gateSystem", {}).get("gates", []) or []
        demand = self._gate_colors_at_depth(gates, 0)
        active = [
            record
            for record in records
            if record["is_grid_shooter"] and record["row"] == 0
        ]
        if not active or any(record["shooter"].get("colorId") in demand for record in active):
            return
        for target in active:
            for source in records:
                if source["effective_capacity"] != target["effective_capacity"]:
                    continue
                if source["shooter"].get("colorId") not in demand:
                    continue
                target_color = target["shooter"].get("colorId")
                target["shooter"]["colorId"] = source["shooter"].get("colorId")
                source["shooter"]["colorId"] = target_color
                return

    def _phase_weight(self, value: int) -> int:
        return max(0, min(3, int(value)))

    def _average_phase_weight(self, field_name: str) -> float:
        phases = self.config.normalized_phases()
        values = [self._phase_weight(getattr(phase, field_name, 0)) for phase in phases]
        return sum(values) / max(1, len(values))

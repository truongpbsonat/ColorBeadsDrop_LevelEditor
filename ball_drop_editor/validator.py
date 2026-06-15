from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Tuple

from .constants import (
    BALL_COLORS,
    DIRECTIONS,
    GRID_OBSTACLE_SHAPE_TYPES,
    GRID_OBSTACLE_TYPES,
    MECHANIC_IDS,
    RUNTIME_ENTITY_TYPES,
    SHOOTER_FIXED_CAPACITY,
    SHOOTER_GROUP_TYPES,
    SHOOTER_MODIFIER_TYPES,
    TRAY_ICE_DEFAULT_HP,
    TRAY_MODIFIER_TYPES,
)
from .level_data import detect_mechanics
from .utils import safe_int

LEGACY_GRID_CELL_FIELDS = {"type", "shooter", "wall", "tunnel", "portal", "generator", "blocker"}

class LevelValidator:
    def validate(self, level: Dict[str, Any]) -> Tuple[List[str], List[str]]:
        errors: List[str] = []
        warnings: List[str] = []

        grid = level.get("grid", {})
        rows = grid.get("rows", 0)
        cols = grid.get("columns", 0)
        if rows <= 0 or cols <= 0:
            errors.append("Grid rows/columns phải > 0.")

        shooter_ids = set()
        color_capacity = defaultdict(int)
        blocked = [[False for _ in range(max(1, cols))] for _ in range(max(1, rows))]
        has_initial_active_shooter = False

        for cell in grid.get("cells", []):
            r, c = cell.get("row"), cell.get("column")
            for legacy_field in LEGACY_GRID_CELL_FIELDS:
                if legacy_field in cell:
                    errors.append(f"GridCell ({r},{c}) dùng legacy field '{legacy_field}'. Hãy đặt content trong entity.type.")

            if not (0 <= r < rows and 0 <= c < cols):
                errors.append(f"Cell ngoài grid: row={r}, column={c}.")
                continue

            entity = cell.get("entity")
            if entity is None:
                continue
            etype = entity.get("type")

            if etype not in RUNTIME_ENTITY_TYPES:
                errors.append(f"GridEntity type không hỗ trợ hoặc thiếu: {etype} at ({r},{c}).")
            if entity.get("blocksPath", True):
                blocked[r][c] = True

            if etype == "Shooter":
                shooter = entity.get("shooter")
                if not shooter:
                    errors.append(f"Shooter entity thiếu ShooterData at ({r},{c}).")
                    continue
                sid = shooter.get("shooterId")
                if not sid:
                    errors.append(f"Shooter thiếu shooterId at ({r},{c}).")
                elif sid in shooter_ids:
                    errors.append(f"Duplicate shooterId: {sid}.")
                else:
                    shooter_ids.add(sid)
                color = shooter.get("colorId")
                cap = safe_int(str(shooter.get("capacity", 0)), 0)
                if color not in BALL_COLORS or color == "None":
                    errors.append(f"Shooter {sid} có colorId không hợp lệ: {color}.")
                if cap <= 0:
                    errors.append(f"Shooter {sid} capacity phải > 0.")
                self._validate_fixed_shooter_capacity(shooter, sid, f"at ({r},{c})", warnings)
                color_capacity[color] += self._effective_capacity(shooter)
                self._validate_modifiers(shooter, sid, errors)

            if etype == "Tunnel":
                direction = entity.get("outputDirection")
                if direction not in DIRECTIONS:
                    errors.append(f"Tunnel {entity.get('entityId')} outputDirection không hợp lệ: {direction}.")
                else:
                    output = self._offset(r, c, direction)
                    if not (0 <= output[0] < rows and 0 <= output[1] < cols):
                        errors.append(f"Tunnel {entity.get('entityId')} output cell {output} ngoài grid.")
                    else:
                        output_cell = self._find_cell(grid, output[0], output[1])
                        output_entity = output_cell.get("entity") if output_cell else None
                        if output_entity and output_entity.get("type") != "Shooter":
                            warnings.append(f"Tunnel {entity.get('entityId')} output cell {output} đang bị chặn bởi {output_entity.get('type')}.")
                q = entity.get("shooterQueue", [])
                if not q:
                    warnings.append(f"Tunnel {entity.get('entityId')} không có shooterQueue.")
                for shooter in q:
                    sid = shooter.get("shooterId")
                    if sid in shooter_ids:
                        errors.append(f"Duplicate shooterId trong tunnel: {sid}.")
                    shooter_ids.add(sid)
                    color = shooter.get("colorId")
                    cap = safe_int(str(shooter.get("capacity", 0)), 0)
                    if color not in BALL_COLORS or color == "None":
                        errors.append(f"Tunnel shooter {sid} có colorId không hợp lệ: {color}.")
                    if cap <= 0:
                        errors.append(f"Tunnel shooter {sid} capacity phải > 0.")
                    self._validate_fixed_shooter_capacity(shooter, sid, f"in tunnel {entity.get('entityId')}", warnings)
                    color_capacity[color] += self._effective_capacity(shooter)
                    self._validate_modifiers(shooter, sid, errors)

        self._validate_obstacles(grid, blocked, errors)
        self._validate_shooter_groups(grid, shooter_ids, errors, warnings)

        for cell in grid.get("cells", []):
            entity = cell.get("entity")
            if entity and entity.get("type") == "Shooter" and self._has_path_to_top(grid, cell.get("row"), cell.get("column"), blocked):
                has_initial_active_shooter = True
                break

        gate_system = level.get("gateSystem", {})
        gate_count = gate_system.get("gateCount", 0)
        max_visible = gate_system.get("maxVisibleTrayPerGate", 0)
        gates = gate_system.get("gates", [])
        if gate_count <= 0:
            errors.append("gateSystem.gateCount phải > 0.")
        if max_visible <= 0:
            errors.append("gateSystem.maxVisibleTrayPerGate phải > 0.")
        if len(gates) != gate_count:
            errors.append(f"gates.Count phải bằng gateCount. Current={len(gates)}, gateCount={gate_count}.")

        seen_gate = set()
        color_need = defaultdict(int)
        for gate in gates:
            gi = gate.get("gateIndex")
            if gi in seen_gate:
                errors.append(f"Duplicate gateIndex: {gi}.")
            seen_gate.add(gi)
            if not isinstance(gi, int) or gi < 0 or gi >= gate_count:
                errors.append(f"gateIndex ngoài phạm vi: {gi}.")
            if not gate.get("trayQueue"):
                warnings.append(f"Gate {gi} không có trayQueue.")
            for tray_index, tray in enumerate(gate.get("trayQueue", [])):
                if not str(tray.get("trayId", "")).strip():
                    errors.append(f"Gate {gi} has an empty trayId at index {tray_index}.")
                layers = tray.get("layers", [])
                if not layers:
                    errors.append(f"Tray {tray.get('trayId')} không có layers.")
                for layer in layers:
                    color = layer.get("colorId")
                    required = layer.get("requiredCount", 0)
                    if color not in BALL_COLORS or color == "None":
                        errors.append(f"Tray {tray.get('trayId')} có layer color không hợp lệ: {color}.")
                    if required <= 0:
                        errors.append(f"Tray {tray.get('trayId')} layer requiredCount phải > 0.")
                    color_need[color] += max(0, required)
                self._validate_tray_modifiers(tray, errors)

        for color in sorted(color_need):
            if color not in BALL_COLORS or color == "None":
                continue
            need = color_need.get(color, 0)
            cap = color_capacity.get(color, 0)
            delta = cap - need
            if cap < need:
                missing = need - cap
                shooter_count = (missing + SHOOTER_FIXED_CAPACITY - 1) // SHOOTER_FIXED_CAPACITY
                tray_count = (missing + 2) // 3
                errors.append(
                    f"Không đủ ball màu {color}: shooterCapacity={cap}, trayRequired={need}, "
                    f"delta={delta:+d}. Gợi ý: thêm {missing} capacity shooter màu {color} "
                    f"(khoảng {shooter_count} shooter thường capacity 9) hoặc giảm {missing} trayRequired "
                    f"(khoảng {tray_count} tray/layer capacity 3)."
                )
            elif cap > need * 2:
                extra = cap - need
                shooter_count = (extra + SHOOTER_FIXED_CAPACITY - 1) // SHOOTER_FIXED_CAPACITY
                tray_count = (extra + 2) // 3
                warnings.append(
                    f"Dư ball màu {color}: shooterCapacity={cap}, trayRequired={need}, "
                    f"delta={delta:+d}. Gợi ý: giảm {extra} capacity shooter màu {color} "
                    f"(khoảng {shooter_count} shooter thường capacity 9) hoặc thêm {extra} trayRequired "
                    f"(khoảng {tray_count} tray/layer capacity 3)."
                )

        if not has_initial_active_shooter:
            warnings.append("No shooter active initially.")

        self._validate_mechanics(level, errors, warnings)

        if not errors and not warnings:
            warnings.append("OK: Không phát hiện lỗi cơ bản.")

        return errors, warnings

    def _validate_modifiers(self, shooter: Dict[str, Any], shooter_id: str, errors: List[str]) -> None:
        for modifier in shooter.get("modifiers", []):
            mtype = modifier.get("type")
            if mtype not in SHOOTER_MODIFIER_TYPES:
                errors.append(f"Shooter modifier type không hỗ trợ: {mtype}.")
            if mtype == "Ice" and modifier.get("hp", 1) <= 0:
                errors.append(f"Ice shooter {shooter_id} hp phải > 0.")

    def _validate_fixed_shooter_capacity(
        self,
        shooter: Dict[str, Any],
        shooter_id: str,
        location: str,
        warnings: List[str],
    ) -> None:
        capacity = safe_int(str(shooter.get("capacity", 0)), 0)
        if capacity == SHOOTER_FIXED_CAPACITY:
            return
        modifier_types = {
            modifier.get("type")
            for modifier in shooter.get("modifiers", []) or []
            if isinstance(modifier, dict)
        }
        special_note = " Special shooter vẫn để capacity=9 và chỉ thêm modifier Special." if "Special" in modifier_types else ""
        warnings.append(
            f"Shooter {shooter_id or '?'} {location} capacity={capacity}, "
            f"nhưng shooter capacity hiện cố định là {SHOOTER_FIXED_CAPACITY}.{special_note}"
        )

    def _effective_capacity(self, shooter: Dict[str, Any]) -> int:
        capacity = max(0, safe_int(str(shooter.get("capacity", 0)), 0))
        if any(modifier.get("type") == "Special" for modifier in shooter.get("modifiers", []) or []):
            return capacity * 2
        return capacity

    def _validate_tray_modifiers(self, tray: Dict[str, Any], errors: List[str]) -> None:
        tray_id = tray.get("trayId")
        for modifier in tray.get("modifiers", []):
            mtype = modifier.get("type")
            if mtype not in TRAY_MODIFIER_TYPES:
                errors.append(f"Tray modifier type không hỗ trợ: {mtype}.")
            if mtype == "Ice" and modifier.get("hp", TRAY_ICE_DEFAULT_HP) <= 0:
                errors.append(f"Ice tray {tray_id} hp phải > 0.")

    def _validate_obstacles_legacy(self, grid: Dict[str, Any], blocked: List[List[bool]], errors: List[str]) -> None:
        rows = grid.get("rows", 0)
        cols = grid.get("columns", 0)
        for obstacle in grid.get("obstacles", []):
            if obstacle.get("type") not in GRID_OBSTACLE_TYPES:
                errors.append(f"GridObstacle type không hỗ trợ: {obstacle.get('type')}.")
                continue
            if obstacle.get("hp", 1) <= 0:
                errors.append(f"IceBlock {obstacle.get('obstacleId')} hp phải > 0.")
            shape_type = obstacle.get("shape", {}).get("type", "Rect")
            if shape_type not in GRID_OBSTACLE_SHAPE_TYPES:
                errors.append(f"Obstacle {obstacle.get('obstacleId')} has unsupported shape type: {shape_type}.")
                continue
            for r, c in self._expand_shape(obstacle.get("shape", {}), 3, 3):
                if not (0 <= r < rows and 0 <= c < cols):
                    errors.append(f"Obstacle {obstacle.get('obstacleId')} shape cell ({r},{c}) ngoài grid.")
                    continue
                blocked[r][c] = True

    def _validate_shooter_groups_legacy(self, grid: Dict[str, Any], shooter_ids: set, errors: List[str]) -> None:
        for group in grid.get("shooterGroups", []):
            group_id = group.get("groupId")
            if group.get("type") not in SHOOTER_GROUP_TYPES:
                errors.append(f"ShooterGroup {group_id} has invalid type: {group.get('type')}.")
            for shooter_id in group.get("shooterIds", []):
                if shooter_id not in shooter_ids:
                    errors.append(f"ShooterGroup {group.get('groupId')} tham chiếu shooterId không tồn tại: {shooter_id}.")

    def _validate_obstacles(self, grid: Dict[str, Any], blocked: List[List[bool]], errors: List[str]) -> None:
        rows = grid.get("rows", 0)
        cols = grid.get("columns", 0)
        entities_by_pos = {
            (cell.get("row"), cell.get("column")): cell.get("entity")
            for cell in grid.get("cells", [])
            if cell.get("entity") is not None
        }
        for obstacle in grid.get("obstacles", []):
            obstacle_type = obstacle.get("type")
            if obstacle_type not in GRID_OBSTACLE_TYPES:
                errors.append(f"GridObstacle type is unsupported: {obstacle_type}.")
                continue

            if obstacle_type == "IceBlock":
                if obstacle.get("hp", 1) <= 0:
                    errors.append(f"IceBlock {obstacle.get('obstacleId')} hp must be > 0.")
                shape_type = obstacle.get("shape", {}).get("type", "Rect")
                if shape_type not in GRID_OBSTACLE_SHAPE_TYPES:
                    errors.append(f"Obstacle {obstacle.get('obstacleId')} has unsupported shape type: {shape_type}.")
                    continue
                affected_cells = self._expand_shape(obstacle.get("shape", {}), 3, 3)
            elif obstacle_type == "LockBar":
                direction = obstacle.get("direction")
                if direction not in DIRECTIONS:
                    errors.append(f"LockBar {obstacle.get('obstacleId')} direction is invalid: {direction}.")
                    continue
                if obstacle.get("length", 0) <= 0:
                    errors.append(f"LockBar {obstacle.get('obstacleId')} length must be > 0.")
                affected_cells = self._expand_lockbar_shape(obstacle)
                self._validate_lockbar_cells(obstacle, affected_cells, entities_by_pos, rows, cols, errors)
            else:
                continue

            for r, c in affected_cells:
                if not (0 <= r < rows and 0 <= c < cols):
                    errors.append(f"Obstacle {obstacle.get('obstacleId')} shape cell ({r},{c}) outside grid.")
                    continue
                blocked[r][c] = True

    def _validate_lockbar_cells(
        self,
        obstacle: Dict[str, Any],
        affected_cells: List[Tuple[int, int]],
        entities_by_pos: Dict[Tuple[int, int], Dict[str, Any]],
        rows: int,
        cols: int,
        errors: List[str],
    ) -> None:
        obstacle_id = obstacle.get("obstacleId")
        for index, position in enumerate(affected_cells):
            if not (0 <= position[0] < rows and 0 <= position[1] < cols):
                continue
            entity = entities_by_pos.get(position)
            if index == 1:
                if not entity or entity.get("type") != "Wall":
                    errors.append(f"LockBar {obstacle_id} cell {position} (slot 2) must have a Wall entity.")
            elif entity is not None:
                errors.append(f"LockBar {obstacle_id} cell {position} (slot {index + 1}) cannot have any entity.")

        if not affected_cells:
            return
        trigger = self._offset(
            affected_cells[0][0],
            affected_cells[0][1],
            self._opposite_direction(obstacle.get("direction", "Right")),
        )
        if not (0 <= trigger[0] < rows and 0 <= trigger[1] < cols):
            errors.append(f"LockBar {obstacle_id} trigger cell {trigger} is outside grid.")
        elif trigger not in entities_by_pos:
            errors.append(f"LockBar {obstacle_id} trigger cell {trigger} must have a blocking entity.")

    def _validate_shooter_groups(self, grid: Dict[str, Any], shooter_ids: set, errors: List[str], warnings: List[str]) -> None:
        seen_group_ids = set()
        for group in grid.get("shooterGroups", []):
            group_id = group.get("groupId")
            if not str(group_id or "").strip():
                errors.append("ShooterGroup is missing groupId.")
            elif group_id in seen_group_ids:
                errors.append(f"Duplicate ShooterGroup groupId: {group_id}.")
            else:
                seen_group_ids.add(group_id)
            group_type = group.get("type")
            if group_type not in SHOOTER_GROUP_TYPES:
                errors.append(f"ShooterGroup {group_id} has invalid type: {group_type}.")
            elif group_type in {"Chain", "Pair"}:
                warnings.append(f"ShooterGroup {group_id} type {group_type} is data-only; Connected has the current runtime behavior.")
            for shooter_id in group.get("shooterIds", []):
                if shooter_id not in shooter_ids:
                    errors.append(f"ShooterGroup {group_id} references missing shooterId: {shooter_id}.")
            if group_type == "Connected" and len(group.get("shooterIds", []) or []) < 2:
                warnings.append(f"ShooterGroup {group_id} Connected should have at least 2 shooters.")

    def _validate_mechanics(self, level: Dict[str, Any], errors: List[str], warnings: List[str]) -> None:
        mechanics = level.get("mechanics", [])
        if not isinstance(mechanics, list):
            errors.append("mechanics phải là list các mechanic id.")
            return

        authored = set()
        for mechanic in mechanics:
            if not isinstance(mechanic, str) or not mechanic.strip():
                errors.append(f"mechanics chứa id không hợp lệ: {mechanic!r}.")
                continue
            mid = mechanic.strip()
            if mid in authored:
                warnings.append(f"mechanics có id trùng lặp: {mid}.")
            authored.add(mid)
            if mid not in MECHANIC_IDS:
                warnings.append(f"mechanics có id không nằm trong danh sách chuẩn: {mid}.")

        for mid in sorted(set(detect_mechanics(level)) - authored):
            warnings.append(f"Mechanic '{mid}' xuất hiện trong level nhưng chưa khai báo trong 'mechanics' (dùng Auto-detect).")

    def _expand_shape(self, shape: Dict[str, Any], default_width: int = 1, default_height: int = 1) -> List[Tuple[int, int]]:
        origin = shape.get("origin", {})
        origin_row = origin.get("row", 0)
        origin_col = origin.get("column", 0)
        if shape.get("type") == "CustomCells":
            return [(cell.get("row", 0), cell.get("column", 0)) for cell in shape.get("cells", [])]
        if shape.get("type") == "Plus":
            return [
                (origin_row, origin_col),
                (origin_row - 1, origin_col),
                (origin_row + 1, origin_col),
                (origin_row, origin_col - 1),
                (origin_row, origin_col + 1),
            ]
        if shape.get("type") == "LineHorizontal":
            return [(origin_row, origin_col + col) for col in range(max(1, shape.get("width", default_width)))]
        if shape.get("type") == "LineVertical":
            return [(origin_row + row, origin_col) for row in range(max(1, shape.get("height", default_height)))]
        width = max(1, shape.get("width", 1))
        height = max(1, shape.get("height", 1))
        height = max(1, safe_int(str(shape.get("height", default_height)), default_height))
        width = max(1, safe_int(str(shape.get("width", default_width)), default_width))
        return [(origin_row + row, origin_col + col) for row in range(height) for col in range(width)]

    def _expand_lockbar_shape(self, obstacle: Dict[str, Any]) -> List[Tuple[int, int]]:
        shape = obstacle.get("shape", {}) or {}
        origin = shape.get("origin", {}) or {}
        row = origin.get("row", 0)
        col = origin.get("column", 0)
        cells = [(row, col)]
        for _ in range(1, max(1, obstacle.get("length", 3))):
            row, col = self._offset(row, col, obstacle.get("direction", "Right"))
            cells.append((row, col))
        return cells

    def _has_path_to_top(self, grid: Dict[str, Any], start_row: int, start_col: int, blocked: List[List[bool]]) -> bool:
        rows = grid.get("rows", 0)
        cols = grid.get("columns", 0)
        queue = [(start_row, start_col)]
        visited = {(start_row, start_col)}
        while queue:
            row, col = queue.pop(0)
            if row == 0:
                return True
            for next_row, next_col in ((row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1)):
                if not (0 <= next_row < rows and 0 <= next_col < cols):
                    continue
                if (next_row, next_col) in visited:
                    continue
                if (next_row, next_col) != (start_row, start_col) and blocked[next_row][next_col]:
                    continue
                visited.add((next_row, next_col))
                queue.append((next_row, next_col))
        return False

    def _find_cell(self, grid: Dict[str, Any], row: int, col: int) -> Dict[str, Any]:
        for cell in grid.get("cells", []):
            if cell.get("row") == row and cell.get("column") == col:
                return cell
        return {}

    def _offset(self, row: int, col: int, direction: str) -> Tuple[int, int]:
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

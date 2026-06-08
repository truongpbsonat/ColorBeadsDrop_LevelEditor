from __future__ import annotations

import copy
from typing import Any, Dict, List, Tuple

from .level_data import normalize_runtime_level


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

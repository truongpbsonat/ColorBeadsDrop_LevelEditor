from __future__ import annotations

import copy
import uuid
from typing import Any, Dict, List, Optional

from .constants import BALL_COLORS, COLOR_HEX, DIRECTIONS, GAME_MODES, LEVEL_DIFFICULTIES
from .utils import safe_int

def make_empty_level(rows: int = 4, cols: int = 4, gate_count: int = 4) -> Dict[str, Any]:
    level = {
        "gameMode": "Classic",
        "difficulty": "Normal",
        "level": 1,
        "category": 0,
        "time": 60,
        "levelName": "New Level",
        "grid": {
            "rows": rows,
            "columns": cols,
            "cells": [
                {"row": r, "column": c, "entity": None}
                for r in range(rows) for c in range(cols)
            ],
            "obstacles": [],
            "shooterGroups": []
        },
        "gateSystem": {
            "gateCount": gate_count,
            "maxVisibleTrayPerGate": 4,
            "gates": [
                {"gateIndex": i, "trayQueue": []}
                for i in range(gate_count)
            ]
        }
    }
    normalize_runtime_level(level)
    return level

def normalize_runtime_level(level: Dict[str, Any]) -> Dict[str, Any]:
    level["gameMode"] = _enum_name(level.get("gameMode"), GAME_MODES, "Classic")
    level["difficulty"] = _enum_name(level.get("difficulty"), LEVEL_DIFFICULTIES, "Normal")
    level["level"] = max(1, safe_int(str(level.get("level", level.get("levelId", 1))), 1))
    level["category"] = max(0, safe_int(str(level.get("category", 0)), 0))
    level["time"] = max(0, safe_int(str(level.get("time", 60)), 60))
    level["levelName"] = str(level.get("levelName") or "").strip() or "New Level"

    grid = level.setdefault("grid", {})
    rows = max(1, safe_int(str(grid.get("rows", 4)), 4))
    cols = max(1, safe_int(str(grid.get("columns", 4)), 4))
    grid["rows"] = rows
    grid["columns"] = cols
    grid["obstacles"] = [_normalize_obstacle(obstacle) for obstacle in grid.get("obstacles", []) or []]
    grid["shooterGroups"] = [_normalize_shooter_group(group) for group in grid.get("shooterGroups", []) or []]
    set_grid_size(level, rows, cols)

    gate_system = level.setdefault("gateSystem", {})
    gate_count = max(1, safe_int(str(gate_system.get("gateCount", 4)), 4))
    gate_system["gateCount"] = gate_count
    gate_system["maxVisibleTrayPerGate"] = max(1, safe_int(str(gate_system.get("maxVisibleTrayPerGate", 4)), 4))
    old_by_index = {safe_int(str(gate.get("gateIndex", -1)), -1): gate for gate in gate_system.get("gates", []) or []}
    gate_system["gates"] = [
        _normalize_gate(old_by_index.get(i, {}), i)
        for i in range(gate_count)
    ]

    _retain_keys(level, {"gameMode", "difficulty", "level", "category", "time", "levelName", "grid", "gateSystem"})
    _retain_keys(grid, {"rows", "columns", "cells", "obstacles", "shooterGroups"})
    _retain_keys(gate_system, {"gateCount", "maxVisibleTrayPerGate", "gates"})
    return level


def make_shooter_entity(row: int, col: int, color: str, capacity: int) -> Dict[str, Any]:
    sid = f"s_{row}_{col}_{uuid.uuid4().hex[:4]}"
    return {
        "type": "Shooter",
        "entityId": f"entity_{sid}",
        "blocksPath": True,
        "shooter": {
            "shooterId": sid,
            "colorId": color,
            "capacity": capacity,
            "modifiers": []
        }
    }


def make_wall_entity(row: int, col: int) -> Dict[str, Any]:
    return {
        "type": "Wall",
        "entityId": f"wall_{row}_{col}_{uuid.uuid4().hex[:4]}",
        "blocksPath": True
    }


def parse_tunnel_queue(text: str) -> List[Dict[str, Any]]:
    """
    Syntax:
        Blue:5, Red:6, Orange:4
    or:
        Blue 5
        Red 6
    """
    result = []
    normalized = text.replace("\n", ",")
    parts = [p.strip() for p in normalized.split(",") if p.strip()]
    for idx, part in enumerate(parts):
        if ":" in part:
            color, count = part.split(":", 1)
        else:
            raw = part.split()
            if len(raw) < 2:
                continue
            color, count = raw[0], raw[1]
        color = color.strip()
        if color not in BALL_COLORS or color == "None":
            continue
        capacity = max(1, safe_int(count.strip(), 1))
        result.append({
            "shooterId": f"s_tunnel_{uuid.uuid4().hex[:6]}",
            "colorId": color,
            "capacity": capacity,
            "modifiers": []
        })
    return result


def make_tunnel_entity(row: int, col: int, direction: str, queue_text: str) -> Dict[str, Any]:
    return {
        "type": "Tunnel",
        "entityId": f"tunnel_{row}_{col}_{uuid.uuid4().hex[:4]}",
        "blocksPath": True,
        "outputDirection": direction,
        "shooterQueue": parse_tunnel_queue(queue_text)
    }


def iter_cells(level: Dict[str, Any]) -> List[Dict[str, Any]]:
    return level.setdefault("grid", {}).setdefault("cells", [])


def find_cell(level: Dict[str, Any], row: int, col: int) -> Dict[str, Any]:
    for cell in iter_cells(level):
        if cell.get("row") == row and cell.get("column") == col:
            return cell
    cell = {"row": row, "column": col, "entity": None}
    iter_cells(level).append(cell)
    return cell


def set_grid_size(level: Dict[str, Any], rows: int, cols: int) -> None:
    old = {(c.get("row"), c.get("column")): c for c in iter_cells(level)}
    level["grid"]["rows"] = rows
    level["grid"]["columns"] = cols
    cells = []
    for r in range(rows):
        for c in range(cols):
            cells.append(_normalize_cell(copy.deepcopy(old.get((r, c), {})), r, c))
    level["grid"]["cells"] = cells


def entity_label(entity: Optional[Dict[str, Any]]) -> str:
    if not entity:
        return ""
    t = entity.get("type", "")
    if t == "Shooter":
        shooter = entity.get("shooter", {})
        return f"{shooter.get('colorId', '?')}\n{shooter.get('capacity', '?')}"
    if t == "Wall":
        return "WALL"
    if t == "Tunnel":
        q = len(entity.get("shooterQueue", []))
        return f"TUN\n{entity.get('outputDirection','?')}:{q}"
    return t


def entity_bg(entity: Optional[Dict[str, Any]]) -> str:
    if not entity:
        return "#2B2B2B"
    t = entity.get("type")
    if t == "Shooter":
        return COLOR_HEX.get(entity.get("shooter", {}).get("colorId", "None"), "#888888")
    if t == "Wall":
        return "#555555"
    if t == "Tunnel":
        return "#8E6E53"
    return "#777777"


def _enum_name(value: Any, allowed: List[str], default: str) -> str:
    return value if value in allowed else default


def _retain_keys(data: Dict[str, Any], allowed: set[str]) -> None:
    for key in list(data):
        if key not in allowed:
            data.pop(key, None)


def _normalize_cell(cell: Dict[str, Any], row: int, col: int) -> Dict[str, Any]:
    cell["row"] = row
    cell["column"] = col
    cell["entity"] = _normalize_entity(cell.get("entity"))
    _retain_keys(cell, {"row", "column", "entity"})
    return cell


def _normalize_entity(entity: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(entity, dict):
        return None

    entity_type = entity.get("type")
    normalized = {
        "type": entity_type,
        "entityId": str(entity.get("entityId", "")).strip(),
        "blocksPath": bool(entity.get("blocksPath", True)),
    }
    if entity_type == "Shooter":
        normalized["shooter"] = _normalize_shooter(entity.get("shooter", {}))
        return normalized
    if entity_type == "Tunnel":
        normalized["outputDirection"] = _enum_name(entity.get("outputDirection"), DIRECTIONS, "Up")
        normalized["shooterQueue"] = [_normalize_shooter(shooter) for shooter in entity.get("shooterQueue", [])]
        return normalized
    if entity_type == "Wall":
        return normalized
    return normalized


def _normalize_shooter(shooter: Dict[str, Any]) -> Dict[str, Any]:
    normalized = {
        "shooterId": str(shooter.get("shooterId", "")).strip(),
        "colorId": _enum_name(shooter.get("colorId"), BALL_COLORS, "None"),
        "capacity": safe_int(str(shooter.get("capacity", 0)), 0),
        "modifiers": [_normalize_modifier(modifier) for modifier in shooter.get("modifiers", [])],
    }
    return normalized


def _normalize_modifier(modifier: Dict[str, Any]) -> Dict[str, Any]:
    modifier_type = modifier.get("type")
    normalized = {"type": modifier_type}
    if modifier_type == "Ice":
        normalized["hp"] = safe_int(str(modifier.get("hp", 1)), 1)
        normalized["canClickWhileFrozen"] = bool(modifier.get("canClickWhileFrozen", False))
        normalized["blocksActivation"] = bool(modifier.get("blocksActivation", True))
    if modifier_type == "Locked":
        normalized["requiredKeyId"] = str(modifier.get("requiredKeyId", "")).strip()
        normalized["blocksActivation"] = bool(modifier.get("blocksActivation", True))
    return normalized


def _normalize_obstacle(obstacle: Dict[str, Any]) -> Dict[str, Any]:
    normalized = {
        "obstacleId": str(obstacle.get("obstacleId", "")).strip(),
        "type": obstacle.get("type"),
        "shape": _normalize_obstacle_shape(obstacle.get("shape", {})),
    }
    if normalized["type"] == "IceBlock":
        normalized["hp"] = safe_int(str(obstacle.get("hp", 1)), 1)
        normalized["blocksPath"] = bool(obstacle.get("blocksPath", True))
        normalized["locksShooter"] = bool(obstacle.get("locksShooter", True))
    return normalized


def _normalize_obstacle_shape(shape: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": str(shape.get("type", "")).strip(),
        "origin": _normalize_position(shape.get("origin", {})),
        "width": max(1, safe_int(str(shape.get("width", 1)), 1)),
        "height": max(1, safe_int(str(shape.get("height", 1)), 1)),
        "cells": [_normalize_position(cell) for cell in shape.get("cells", [])],
    }


def _normalize_position(position: Dict[str, Any]) -> Dict[str, int]:
    return {
        "row": safe_int(str(position.get("row", 0)), 0),
        "column": safe_int(str(position.get("column", 0)), 0),
    }


def _normalize_shooter_group(group: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "groupId": str(group.get("groupId", "")).strip(),
        "type": group.get("type", "None"),
        "shooterIds": [str(shooter_id) for shooter_id in group.get("shooterIds", [])],
        "rule": group.get("rule", "None"),
    }


def _normalize_gate(gate: Dict[str, Any], gate_index: int) -> Dict[str, Any]:
    return {
        "gateIndex": gate_index,
        "trayQueue": [_normalize_tray(tray) for tray in gate.get("trayQueue", [])],
    }


def _normalize_tray(tray: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "trayId": str(tray.get("trayId", "")).strip(),
        "layers": [_normalize_tray_layer(layer) for layer in tray.get("layers", [])],
    }


def _normalize_tray_layer(layer: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "colorId": _enum_name(layer.get("colorId"), BALL_COLORS, "None"),
        "requiredCount": safe_int(str(layer.get("requiredCount", 0)), 0),
    }

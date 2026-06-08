from __future__ import annotations

import copy
import json
import os
from typing import Any, Dict, List, Optional, Sequence

from .constants import BALL_COLORS
from .level_data import normalize_runtime_level
from .level_generator_models import DEFAULT_GENERATOR_COLORS, GeneratorConfig


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

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

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

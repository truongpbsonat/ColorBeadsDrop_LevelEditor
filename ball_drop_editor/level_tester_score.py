from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .level_tester_core import (
    CONVEYOR_SLOTS,
    BallDropSimulator,
    ClickAction,
    DeepSearchSolver,
    GameState,
    SolveResult,
)


@dataclass
class DifficultyMetrics:
    active_choices: int = 0
    decoys: int = 0
    same_color_route_traps: int = 0
    conveyor_pressure: float = 0.0
    unlock_depth: float = 0.0
    tunnel_pressure: float = 0.0
    obstacle_pressure: float = 0.0
    tray_switching_pressure: float = 0.0
    consecutive_tray_relief: float = 0.0
    parallel_same_color_relief: float = 0.0


@dataclass
class PerClickScore:
    click_index: int
    row: int
    column: int
    color: str
    score: float
    metrics: DifficultyMetrics


@dataclass
class PhaseScore:
    name: str
    start_click: int
    end_click: int
    target_score: float
    actual_score: float
    delta: float


@dataclass
class SolverScoreResult:
    status: str
    solution: List[ClickAction] = field(default_factory=list)
    overall_score: float = 0.0
    per_click_scores: List[PerClickScore] = field(default_factory=list)
    phase_scores: List[PhaseScore] = field(default_factory=list)
    metrics: DifficultyMetrics = field(default_factory=DifficultyMetrics)
    solve_result: Optional[SolveResult] = None
    message: str = ""


class SolverScoreAdapter:
    """Stable generator-facing API around the level tester solver."""

    def __init__(self, time_budget: float = 20.0):
        self.time_budget = max(0.1, float(time_budget))

    def score_level(
        self,
        level: Dict[str, Any],
        phases: Optional[List[Dict[str, Any]]] = None,
        cancel_check=None,
    ) -> SolverScoreResult:
        simulator = BallDropSimulator(copy.deepcopy(level))
        solver = DeepSearchSolver(simulator, time_budget=self.time_budget)
        result = solver.solve_file("<generated>", cancel_check=cancel_check)
        scored = self._score_solution(simulator, result, phases or [])
        scored.status = result.status
        scored.solution = list(result.solution)
        scored.solve_result = result
        scored.message = result.message
        return scored

    def score_solve_result(
        self,
        simulator: BallDropSimulator,
        result: SolveResult,
        phases: Optional[List[Dict[str, Any]]] = None,
    ) -> SolverScoreResult:
        return self._score_solution(simulator, result, phases or [])

    def _score_solution(
        self,
        simulator: BallDropSimulator,
        result: SolveResult,
        phases: List[Dict[str, Any]],
    ) -> SolverScoreResult:
        if result.status != "PASS" or not result.solution:
            return SolverScoreResult(status=result.status, solve_result=result, message=result.message)

        state = simulator.initial_state()
        per_click: List[PerClickScore] = []
        for index, action in enumerate(result.solution, start=1):
            simulator.advance_to_decision(state)
            metrics = self._measure_click(simulator, state, action)
            score = self._metrics_score(metrics)
            per_click.append(
                PerClickScore(
                    click_index=index,
                    row=action.row,
                    column=action.column,
                    color=action.color,
                    score=score,
                    metrics=metrics,
                )
            )
            if not simulator.click(state, action.row, action.column):
                break

        phase_scores = self._score_phases(per_click, phases)
        overall = sum(item.score for item in per_click) / max(1, len(per_click))
        return SolverScoreResult(
            status=result.status,
            solution=list(result.solution),
            overall_score=overall,
            per_click_scores=per_click,
            phase_scores=phase_scores,
            metrics=self._average_metrics(per_click),
            solve_result=result,
            message=result.message,
        )

    def _measure_click(
        self,
        simulator: BallDropSimulator,
        state: GameState,
        action: ClickAction,
    ) -> DifficultyMetrics:
        active = simulator.active_shooters(state)
        active_colors = [shooter.color for _, _, shooter in active]
        front_colors = set(simulator.front_gate_colors(state))
        decoys = sum(1 for color in active_colors if color not in front_colors)
        same_color = sum(1 for color in active_colors if color == action.color)
        moving = len(state.hopper) + sum(1 for slot in state.conveyor if slot is not None)
        unlock_depth = action.row / max(1, state.rows - 1)
        tray_switching, tray_relief, parallel_relief = self._tray_layout_pressure(state)
        return DifficultyMetrics(
            active_choices=len(active),
            decoys=decoys,
            same_color_route_traps=max(0, same_color - 1) if action.color in front_colors else 0,
            conveyor_pressure=moving / max(1, CONVEYOR_SLOTS),
            unlock_depth=unlock_depth,
            tunnel_pressure=self._tunnel_pressure(state, action.row, action.column),
            obstacle_pressure=self._obstacle_pressure(state, action.row, action.column),
            tray_switching_pressure=tray_switching,
            consecutive_tray_relief=tray_relief,
            parallel_same_color_relief=parallel_relief,
        )

    def _tray_layout_pressure(self, state: GameState) -> Tuple[float, float, float]:
        front_colors: List[str] = []
        switch_count = 0
        comparable = 0
        for gate in state.gates:
            if not gate or not gate[0].layers:
                continue
            front_color = str(gate[0].layers[0][0])
            front_colors.append(front_color)
            next_color = self._next_gate_color(gate)
            if next_color is None:
                continue
            comparable += 1
            if next_color != front_color:
                switch_count += 1

        switch_rate = switch_count / max(1, comparable)
        consecutive_relief = (comparable - switch_count) / max(1, comparable)
        if len(front_colors) <= 1:
            front_diversity = 0.0
            parallel_relief = 0.0
        else:
            front_diversity = (len(set(front_colors)) - 1) / (len(front_colors) - 1)
            parallel_relief = (len(front_colors) - len(set(front_colors))) / (len(front_colors) - 1)
        switching_pressure = (switch_rate + front_diversity) / 2.0
        return switching_pressure, consecutive_relief, parallel_relief

    def _next_gate_color(self, gate) -> Optional[str]:
        front = gate[0]
        if len(front.layers) > 1:
            return str(front.layers[1][0])
        if len(gate) > 1 and gate[1].layers:
            return str(gate[1].layers[0][0])
        return None

    def _tunnel_pressure(self, state: GameState, row: int, col: int) -> float:
        pressure = 0.0
        for index, cell in enumerate(state.cells):
            if cell.type != "Tunnel":
                continue
            rr, cc = divmod(index, state.cols)
            if cell.queue:
                pressure += 0.08 * len(cell.queue)
            if abs(rr - row) + abs(cc - col) <= 2:
                pressure += 0.25
        return min(1.0, pressure)

    def _obstacle_pressure(self, state: GameState, row: int, col: int) -> float:
        pressure = 0.0
        remaining_balls = sum(
            int(layer[1])
            for gate in state.gates
            for tray in gate
            for layer in tray.layers
        )
        if state.obstacle_blocked:
            for rr, cc in ((row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1)):
                if 0 <= rr < state.rows and 0 <= cc < state.cols and state.obstacle_blocked[rr][cc]:
                    pressure += 0.35
        for index, cell in enumerate(state.cells):
            rr, cc = divmod(index, state.cols)
            shooters = []
            if cell.type == "Shooter" and cell.shooter:
                shooters = [cell.shooter]
            elif cell.type == "Tunnel":
                shooters = cell.queue
            for shooter in shooters:
                if shooter.ice_hp <= 0:
                    continue
                delay = min(1.0, shooter.ice_hp / max(1, remaining_balls))
                distance = abs(rr - row) + abs(cc - col)
                proximity = 1.0 if distance <= 2 else 0.4
                pressure += (0.12 + delay * 0.38) * proximity
        for ice_block in state.ice_blocks:
            if ice_block.hp <= 0:
                continue
            delay = min(1.0, ice_block.hp / max(1, remaining_balls))
            distance = min(
                (abs(rr - row) + abs(cc - col) for rr, cc in ice_block.cells),
                default=state.rows + state.cols,
            )
            proximity = 1.0 if distance <= 2 else 0.4
            pressure += (0.12 + delay * 0.38) * proximity
        front_trays = [
            (gate_index, gate[0])
            for gate_index, gate in enumerate(state.gates)
            if gate
        ]
        for index, (_gate_index, tray) in enumerate(front_trays):
            if tray.ice_hp <= 0:
                continue
            pressure += 0.12
            for neighbor_index in (index - 1, index + 1):
                if not (0 <= neighbor_index < len(front_trays)):
                    continue
                _neighbor_gate_index, neighbor = front_trays[neighbor_index]
                if neighbor.ice_hp <= 0 and neighbor.layers:
                    pressure += 0.10
        return min(1.0, pressure)

    def _metrics_score(self, metrics: DifficultyMetrics) -> float:
        score = 0.0
        decoy_ratio = metrics.decoys / max(1, metrics.active_choices)
        score += max(0, metrics.active_choices - 1) * 5.0
        score += decoy_ratio * 20.0
        score += metrics.same_color_route_traps * 8.0
        score += metrics.conveyor_pressure * 20.0
        score += metrics.unlock_depth * 10.0
        score += metrics.tunnel_pressure * 8.0
        score += metrics.obstacle_pressure * 10.0
        score += metrics.tray_switching_pressure * 18.0
        score -= metrics.consecutive_tray_relief * 20.0
        score -= metrics.parallel_same_color_relief * 10.0
        return min(100.0, max(0.0, score))

    def _score_phases(
        self,
        per_click: List[PerClickScore],
        phases: List[Dict[str, Any]],
    ) -> List[PhaseScore]:
        scored: List[PhaseScore] = []
        for idx, phase in enumerate(phases, start=1):
            start = int(phase.get("start_click", 1))
            end = int(phase.get("end_click", start))
            target = float(phase.get("target_score", 50.0))
            items = [item for item in per_click if start <= item.click_index <= end]
            actual = sum(item.score for item in items) / max(1, len(items))
            scored.append(
                PhaseScore(
                    name=str(phase.get("name") or f"Phase {idx}"),
                    start_click=start,
                    end_click=end,
                    target_score=target,
                    actual_score=actual,
                    delta=actual - target,
                )
            )
        return scored

    def _average_metrics(self, per_click: List[PerClickScore]) -> DifficultyMetrics:
        if not per_click:
            return DifficultyMetrics()
        count = len(per_click)
        return DifficultyMetrics(
            active_choices=math.ceil(sum(item.metrics.active_choices for item in per_click) / count),
            decoys=math.ceil(sum(item.metrics.decoys for item in per_click) / count),
            same_color_route_traps=math.ceil(
                sum(item.metrics.same_color_route_traps for item in per_click) / count
            ),
            conveyor_pressure=sum(item.metrics.conveyor_pressure for item in per_click) / count,
            unlock_depth=sum(item.metrics.unlock_depth for item in per_click) / count,
            tunnel_pressure=sum(item.metrics.tunnel_pressure for item in per_click) / count,
            obstacle_pressure=sum(item.metrics.obstacle_pressure for item in per_click) / count,
            tray_switching_pressure=sum(
                item.metrics.tray_switching_pressure for item in per_click
            ) / count,
            consecutive_tray_relief=sum(
                item.metrics.consecutive_tray_relief for item in per_click
            ) / count,
            parallel_same_color_relief=sum(
                item.metrics.parallel_same_color_relief for item in per_click
            ) / count,
        )


def difficulty_label(score: float) -> str:
    if score < 20:
        return "Easy"
    if score < 40:
        return "Medium"
    if score < 60:
        return "Hard"
    if score < 80:
        return "Very Hard"
    return "Extreme"

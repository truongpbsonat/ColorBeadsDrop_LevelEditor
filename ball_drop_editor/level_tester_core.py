from __future__ import annotations

import copy
import heapq
import json
import os
import random
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .level_data import normalize_runtime_level

CONVEYOR_SLOTS = 30
GATE_PICKUP_RANGES = {
    3: range(10, 14),
    2: range(13, 17),
    1: range(16, 21),
    0: range(21, 24),
}
GATE_PRIORITY = (3, 2, 1, 0)
HOPPER_CLICK_LIMIT = 10
DEFAULT_MAX_STEPS = 3000


@dataclass
class ShooterState:
    color: str
    capacity: int
    ice_hp: int = 0

    def key(self) -> Tuple[str, int, int]:
        return self.color, self.capacity, self.ice_hp


@dataclass
class CellState:
    type: str
    shooter: Optional[ShooterState] = None
    output_direction: str = "Up"
    queue: List[ShooterState] = field(default_factory=list)

    def key(self) -> Tuple[Any, ...]:
        if self.type == "Empty":
            return ("E",)
        if self.type == "Wall":
            return ("W",)
        if self.type == "Shooter" and self.shooter:
            return ("S",) + self.shooter.key()
        if self.type == "Tunnel":
            return (
                "T",
                self.output_direction,
                tuple(shooter.key() for shooter in self.queue),
            )
        return (self.type,)


@dataclass
class ClickAction:
    row: int
    column: int
    color: str

    def label(self) -> str:
        return f"{self.row},{self.column},{self.color}"


@dataclass
class GameState:
    rows: int
    cols: int
    cells: List[CellState]
    gates: List[List[List[List[Any]]]]
    conveyor: List[Optional[str]] = field(default_factory=lambda: [None] * CONVEYOR_SLOTS)
    hopper: List[str] = field(default_factory=list)
    steps: int = 0
    clicks: List[ClickAction] = field(default_factory=list)
    lost: bool = False

    def clone(self) -> "GameState":
        return copy.deepcopy(self)

    def key(self) -> Tuple[Any, ...]:
        return (
            tuple(cell.key() for cell in self.cells),
            tuple(
                tuple(
                    tuple(tuple(layer) for layer in tray)
                    for tray in gate
                )
                for gate in self.gates
            ),
            tuple(self.conveyor),
            tuple(self.hopper),
            self.lost,
        )


@dataclass
class SolveResult:
    file_path: str
    status: str
    attempt: int = 0
    elapsed: float = 0.0
    steps: int = 0
    clicks: int = 0
    nodes: int = 0
    solution: List[ClickAction] = field(default_factory=list)
    message: str = ""


class BallDropSimulator:
    def __init__(self, data: Dict[str, Any]):
        self.level = normalize_runtime_level(copy.deepcopy(data))

    @classmethod
    def from_file(cls, path: str) -> "BallDropSimulator":
        with open(path, "r", encoding="utf-8") as fh:
            return cls(json.load(fh))

    def initial_state(self) -> GameState:
        grid = self.level.get("grid", {})
        rows = int(grid.get("rows", 0))
        cols = int(grid.get("columns", 0))
        cell_by_pos = {
            (cell.get("row"), cell.get("column")): cell
            for cell in grid.get("cells", [])
        }
        cells: List[CellState] = []
        for row in range(rows):
            for col in range(cols):
                raw = cell_by_pos.get((row, col), {})
                cells.append(self._parse_cell(raw.get("entity")))

        gates = []
        gate_system = self.level.get("gateSystem", {})
        gates_by_index = {
            int(gate.get("gateIndex", index)): gate
            for index, gate in enumerate(gate_system.get("gates", []))
        }
        for gate_index in range(int(gate_system.get("gateCount", 0))):
            gate = []
            for tray in gates_by_index.get(gate_index, {}).get("trayQueue", []):
                layers = []
                for layer in tray.get("layers", []):
                    color = layer.get("colorId")
                    remaining = int(layer.get("requiredCount", 0))
                    if color and remaining > 0:
                        layers.append([color, remaining])
                if layers:
                    gate.append(layers)
            gates.append(gate)

        state = GameState(rows=rows, cols=cols, cells=cells, gates=gates)
        self.settle_tunnels(state)
        return state

    def _parse_cell(self, entity: Optional[Dict[str, Any]]) -> CellState:
        if not entity:
            return CellState("Empty")
        entity_type = entity.get("type")
        if entity_type == "Wall":
            return CellState("Wall")
        if entity_type == "Shooter":
            return CellState("Shooter", shooter=self._parse_shooter(entity.get("shooter", {})))
        if entity_type == "Tunnel":
            return CellState(
                "Tunnel",
                output_direction=str(entity.get("outputDirection", "Up")),
                queue=[self._parse_shooter(item) for item in entity.get("shooterQueue", [])],
            )
        return CellState("Wall")

    def _parse_shooter(self, shooter: Dict[str, Any]) -> ShooterState:
        ice_hp = 0
        for modifier in shooter.get("modifiers", []) or []:
            if modifier.get("type") == "Ice":
                ice_hp = max(ice_hp, int(modifier.get("hp", 1)))
        return ShooterState(
            color=str(shooter.get("colorId", "None")),
            capacity=max(0, int(shooter.get("capacity", 0))),
            ice_hp=ice_hp,
        )

    def is_win(self, state: GameState) -> bool:
        return (
            not state.lost
            and all(not gate for gate in state.gates)
            and not state.hopper
            and all(slot is None for slot in state.conveyor)
        )

    def is_dead(self, state: GameState) -> bool:
        if state.lost:
            return True
        has_available_balls = any(
            cell.type == "Shooter" and cell.shooter and cell.shooter.capacity > 0
            for cell in state.cells
        )
        has_available_balls = has_available_balls or bool(state.hopper) or any(
            slot is not None for slot in state.conveyor
        )
        return has_available_balls and all(not gate for gate in state.gates)

    def active_shooters(self, state: GameState) -> List[Tuple[int, int, ShooterState]]:
        active = []
        for index, cell in enumerate(state.cells):
            if cell.type != "Shooter" or not cell.shooter:
                continue
            if cell.shooter.capacity <= 0 or cell.shooter.ice_hp > 0:
                continue
            row, col = divmod(index, state.cols)
            if self.has_path_to_exit(state, row, col):
                active.append((row, col, cell.shooter))
        return active

    def has_path_to_exit(self, state: GameState, start_row: int, start_col: int) -> bool:
        if start_row == 0:
            return True
        queue = [(start_row, start_col)]
        visited = {(start_row, start_col)}
        while queue:
            row, col = queue.pop(0)
            if row == 0:
                return True
            for next_row, next_col in (
                (row - 1, col),
                (row + 1, col),
                (row, col - 1),
                (row, col + 1),
            ):
                if not (0 <= next_row < state.rows and 0 <= next_col < state.cols):
                    continue
                if (next_row, next_col) in visited:
                    continue
                if (next_row, next_col) != (start_row, start_col) and not self.is_passable(state, next_row, next_col):
                    continue
                visited.add((next_row, next_col))
                queue.append((next_row, next_col))
        return False

    def is_passable(self, state: GameState, row: int, col: int) -> bool:
        cell = state.cells[row * state.cols + col]
        return cell.type == "Empty"

    def click(self, state: GameState, row: int, col: int) -> bool:
        index = row * state.cols + col
        cell = state.cells[index]
        if cell.type != "Shooter" or not cell.shooter:
            return False
        shooter = cell.shooter
        if shooter.capacity <= 0 or shooter.ice_hp > 0:
            return False
        if not self.has_path_to_exit(state, row, col):
            return False
        state.hopper.extend([shooter.color] * shooter.capacity)
        state.clicks.append(ClickAction(row, col, shooter.color))
        state.cells[index] = CellState("Empty")
        self.settle_tunnels(state)
        return True

    def settle_tunnels(self, state: GameState) -> None:
        changed = True
        guard = 0
        while changed and guard < len(state.cells) + 1:
            guard += 1
            changed = False
            for index, cell in enumerate(state.cells):
                if cell.type != "Tunnel" or not cell.queue:
                    continue
                row, col = divmod(index, state.cols)
                out = self._offset(row, col, cell.output_direction)
                if out is None:
                    continue
                out_row, out_col = out
                out_index = out_row * state.cols + out_col
                if state.cells[out_index].type != "Empty":
                    continue
                state.cells[out_index] = CellState("Shooter", shooter=cell.queue.pop(0))
                changed = True

    def step(self, state: GameState) -> None:
        if state.lost:
            return
        state.steps += 1
        last = state.conveyor[-1]
        for index in range(CONVEYOR_SLOTS - 1, 0, -1):
            state.conveyor[index] = state.conveyor[index - 1]
        state.conveyor[0] = last

        consumed_slots: set[int] = set()
        consumed_gates: set[int] = set()
        for gate_index in GATE_PRIORITY:
            if gate_index >= len(state.gates) or not state.gates[gate_index]:
                continue
            for slot in GATE_PICKUP_RANGES[gate_index]:
                slot %= CONVEYOR_SLOTS
                if slot in consumed_slots or gate_index in consumed_gates:
                    continue
                ball = state.conveyor[slot]
                if ball is not None and self._gate_needs_color(state, gate_index, ball):
                    state.conveyor[slot] = None
                    consumed_slots.add(slot)
                    consumed_gates.add(gate_index)
                    self._consume_gate_ball(state, gate_index)
                    self.decrement_ice(state)
                    self.settle_tunnels(state)
                    break

        if state.hopper and state.conveyor[0] is None:
            state.conveyor[0] = state.hopper.pop(0)

        if state.hopper and all(slot is not None for slot in state.conveyor):
            needed = set(self.front_gate_colors(state))
            if not needed or not any(slot in needed for slot in state.conveyor if slot is not None):
                state.lost = True

    def _gate_needs_color(self, state: GameState, gate_index: int, color: str) -> bool:
        gate = state.gates[gate_index]
        if not gate or not gate[0] or not gate[0][0]:
            return False
        return gate[0][0][0] == color

    def _consume_gate_ball(self, state: GameState, gate_index: int) -> None:
        layer = state.gates[gate_index][0][0]
        layer[1] -= 1
        if layer[1] > 0:
            return
        state.gates[gate_index][0].pop(0)
        if not state.gates[gate_index][0]:
            state.gates[gate_index].pop(0)

    def decrement_ice(self, state: GameState) -> None:
        for cell in state.cells:
            if cell.type == "Shooter" and cell.shooter and cell.shooter.ice_hp > 0:
                cell.shooter.ice_hp -= 1
            if cell.type == "Tunnel":
                for shooter in cell.queue:
                    if shooter.ice_hp > 0:
                        shooter.ice_hp -= 1

    def front_gate_colors(self, state: GameState) -> List[str]:
        colors = []
        for gate in state.gates:
            if gate and gate[0] and gate[0][0]:
                colors.append(gate[0][0][0])
        return colors

    def advance_to_decision(self, state: GameState, max_steps: int = DEFAULT_MAX_STEPS) -> None:
        while (
            not self.is_win(state)
            and not self.is_dead(state)
            and state.steps < max_steps
        ):
            if len(state.hopper) < HOPPER_CLICK_LIMIT and self.active_shooters(state):
                return
            before_key = state.key()
            self.step(state)
            if state.key() == before_key and not self.active_shooters(state):
                state.lost = True
                return

    def _offset(self, row: int, col: int, direction: str) -> Optional[Tuple[int, int]]:
        if direction == "Up":
            row -= 1
        elif direction == "Down":
            row += 1
        elif direction == "Left":
            col -= 1
        else:
            col += 1
        if 0 <= row < self.level["grid"]["rows"] and 0 <= col < self.level["grid"]["columns"]:
            return row, col
        return None


class DeepSearchSolver:
    def __init__(
        self,
        simulator: BallDropSimulator,
        time_budget: float = 180.0,
        max_steps: int = DEFAULT_MAX_STEPS,
        beam_width: int = 650,
        max_nodes_per_attempt: int = 35000,
    ):
        self.simulator = simulator
        self.time_budget = time_budget
        self.max_steps = max_steps
        self.beam_width = beam_width
        self.max_nodes_per_attempt = max_nodes_per_attempt

    def solve_file(self, path: str, cancel_check=None) -> SolveResult:
        started = time.monotonic()
        nodes_total = 0
        attempt = 0
        best_state: Optional[GameState] = None
        while time.monotonic() - started < self.time_budget:
            if cancel_check and cancel_check():
                return SolveResult(
                    file_path=path,
                    status="CANCELLED",
                    attempt=attempt,
                    elapsed=time.monotonic() - started,
                    nodes=nodes_total,
                    message="Cancelled",
                )
            attempt += 1
            remaining = max(0.1, self.time_budget - (time.monotonic() - started))
            result, nodes, best_state = self._solve_attempt(
                seed=attempt,
                deadline=time.monotonic() + remaining,
                cancel_check=cancel_check,
            )
            nodes_total += nodes
            if result:
                result.file_path = path
                result.attempt = attempt
                result.elapsed = time.monotonic() - started
                result.nodes = nodes_total
                return result
            if nodes < self.max_nodes_per_attempt:
                break
        status = "TIMEOUT" if time.monotonic() - started >= self.time_budget else "FAIL"
        return SolveResult(
            file_path=path,
            status=status,
            attempt=attempt,
            elapsed=time.monotonic() - started,
            steps=best_state.steps if best_state else 0,
            clicks=len(best_state.clicks) if best_state else 0,
            nodes=nodes_total,
            solution=best_state.clicks if best_state else [],
            message="No solution found within search budget.",
        )

    def _solve_attempt(self, seed: int, deadline: float, cancel_check=None) -> Tuple[Optional[SolveResult], int, GameState]:
        randomizer = random.Random(seed)
        initial = self.simulator.initial_state()
        self.simulator.advance_to_decision(initial, self.max_steps)
        frontier: List[Tuple[float, int, GameState]] = []
        counter = 0
        heapq.heappush(frontier, (self._score(initial, randomizer), counter, initial))
        visited = {initial.key()}
        nodes = 0
        best_state = initial

        while frontier and nodes < self.max_nodes_per_attempt and time.monotonic() < deadline:
            if cancel_check and cancel_check():
                break
            _, _, state = heapq.heappop(frontier)
            nodes += 1
            if self._progress_score(state) > self._progress_score(best_state):
                best_state = state
            if self.simulator.is_win(state):
                return (
                    SolveResult(
                        file_path="",
                        status="PASS",
                        steps=state.steps,
                        clicks=len(state.clicks),
                        solution=state.clicks,
                    ),
                    nodes,
                    state,
                )
            if self.simulator.is_dead(state) or state.steps >= self.max_steps:
                continue

            active = self.simulator.active_shooters(state)
            active = self._ordered_actions(state, active, randomizer)
            for row, col, _ in active:
                child = state.clone()
                if not self.simulator.click(child, row, col):
                    continue
                self.simulator.advance_to_decision(child, self.max_steps)
                key = child.key()
                if key in visited:
                    continue
                visited.add(key)
                counter += 1
                heapq.heappush(frontier, (self._score(child, randomizer), counter, child))

            if len(frontier) > self.beam_width:
                frontier = heapq.nsmallest(self.beam_width, frontier)
                heapq.heapify(frontier)

        return None, nodes, best_state

    def _ordered_actions(
        self,
        state: GameState,
        active: List[Tuple[int, int, ShooterState]],
        randomizer: random.Random,
    ) -> List[Tuple[int, int, ShooterState]]:
        needed = set(self.simulator.front_gate_colors(state))
        scored = []
        for action in active:
            row, col, shooter = action
            demand = self._remaining_color_need(state, shooter.color)
            front_bonus = 100 if shooter.color in needed else 0
            unlock_bonus = row * 3
            jitter = randomizer.random()
            scored.append((-(front_bonus + demand + unlock_bonus) + jitter, action))
        scored.sort(key=lambda item: item[0])
        return [action for _, action in scored]

    def _score(self, state: GameState, randomizer: random.Random) -> float:
        remaining = self._remaining_total_need(state)
        blocked = sum(
            1
            for cell in state.cells
            if cell.type == "Shooter" and cell.shooter and cell.shooter.capacity > 0
        )
        moving = len(state.hopper) + sum(1 for slot in state.conveyor if slot is not None)
        return remaining * 20 + blocked * 5 + moving + state.steps * 0.03 + randomizer.random()

    def _progress_score(self, state: GameState) -> int:
        return -self._remaining_total_need(state) * 100 - len(state.hopper) - state.steps

    def _remaining_total_need(self, state: GameState) -> int:
        total = 0
        for gate in state.gates:
            for tray in gate:
                for _, remaining in tray:
                    total += int(remaining)
        return total

    def _remaining_color_need(self, state: GameState, color: str) -> int:
        total = 0
        for gate in state.gates:
            for tray in gate:
                for layer_color, remaining in tray:
                    if layer_color == color:
                        total += int(remaining)
        return total


def solve_level_file(
    path: str,
    time_budget: float = 180.0,
    cancel_check=None,
) -> SolveResult:
    simulator = BallDropSimulator.from_file(path)
    return DeepSearchSolver(simulator, time_budget=time_budget).solve_file(path, cancel_check=cancel_check)


def iter_json_files(path: str) -> List[str]:
    if os.path.isfile(path) and path.lower().endswith(".json"):
        return [path]
    if not os.path.isdir(path):
        return []
    files = [
        os.path.join(path, filename)
        for filename in os.listdir(path)
        if filename.lower().endswith(".json")
    ]
    return sorted(files, key=_natural_sort_key)


def _natural_sort_key(path: str) -> List[Any]:
    import re

    name = os.path.basename(path)
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", name)]

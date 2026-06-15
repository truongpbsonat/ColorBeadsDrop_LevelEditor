from __future__ import annotations

import copy
import heapq
import json
import os
import random
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .constants import TRAY_ICE_DEFAULT_HP
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
    shooter_id: str = ""
    ice_hp: int = 0

    def key(self) -> Tuple[str, int, str, int]:
        return self.color, self.capacity, self.shooter_id, self.ice_hp


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
class TrayState:
    layers: List[List[Any]]
    ice_hp: int = 0

    def key(self) -> Tuple[Any, ...]:
        return (
            self.ice_hp,
            tuple(tuple(layer) for layer in self.layers),
        )


@dataclass
class ClickAction:
    row: int
    column: int
    color: str

    def label(self) -> str:
        return f"{self.row},{self.column},{self.color}"


@dataclass
class LockBarState:
    cells: Tuple[Tuple[int, int], ...]
    trigger: Tuple[int, int]
    active: bool = True

    def key(self) -> Tuple[Any, ...]:
        return self.cells, self.trigger, self.active


@dataclass
class IceBlockState:
    cells: Tuple[Tuple[int, int], ...]
    hp: int

    def key(self) -> Tuple[Any, ...]:
        return self.cells, self.hp


@dataclass
class GameState:
    rows: int
    cols: int
    cells: List[CellState]
    gates: List[List[TrayState]]
    base_obstacle_blocked: Tuple[Tuple[bool, ...], ...] = field(default_factory=tuple)
    obstacle_blocked: Tuple[Tuple[bool, ...], ...] = field(default_factory=tuple)
    ice_blocks: List[IceBlockState] = field(default_factory=list)
    lock_bars: List[LockBarState] = field(default_factory=list)
    connected_groups: Tuple[Tuple[str, ...], ...] = field(default_factory=tuple)
    conveyor: List[Optional[str]] = field(default_factory=lambda: [None] * CONVEYOR_SLOTS)
    hopper: List[str] = field(default_factory=list)
    steps: int = 0
    clicks: List[ClickAction] = field(default_factory=list)
    lost: bool = False

    def clone(self) -> "GameState":
        cells = []
        for cell in self.cells:
            shooter = None
            if cell.shooter is not None:
                shooter = ShooterState(
                    color=cell.shooter.color,
                    capacity=cell.shooter.capacity,
                    shooter_id=cell.shooter.shooter_id,
                    ice_hp=cell.shooter.ice_hp,
                )
            queue = [
                ShooterState(
                    color=queued.color,
                    capacity=queued.capacity,
                    shooter_id=queued.shooter_id,
                    ice_hp=queued.ice_hp,
                )
                for queued in cell.queue
            ]
            cells.append(
                CellState(
                    type=cell.type,
                    shooter=shooter,
                    output_direction=cell.output_direction,
                    queue=queue,
                )
            )

        gates = [
            [
                TrayState(
                    layers=[list(layer) for layer in tray.layers],
                    ice_hp=tray.ice_hp,
                )
                for tray in gate
            ]
            for gate in self.gates
        ]
        return GameState(
            rows=self.rows,
            cols=self.cols,
            cells=cells,
            gates=gates,
            base_obstacle_blocked=self.base_obstacle_blocked,
            obstacle_blocked=self.obstacle_blocked,
            ice_blocks=[
                IceBlockState(cells=ice_block.cells, hp=ice_block.hp)
                for ice_block in self.ice_blocks
            ],
            lock_bars=[
                LockBarState(
                    cells=lock_bar.cells,
                    trigger=lock_bar.trigger,
                    active=lock_bar.active,
                )
                for lock_bar in self.lock_bars
            ],
            connected_groups=self.connected_groups,
            conveyor=list(self.conveyor),
            hopper=list(self.hopper),
            steps=self.steps,
            clicks=list(self.clicks),
            lost=self.lost,
        )

    def key(self) -> Tuple[Any, ...]:
        return (
            tuple(cell.key() for cell in self.cells),
            self.obstacle_blocked,
            tuple(
                tuple(tray.key() for tray in gate)
                for gate in self.gates
            ),
            tuple(self.conveyor),
            tuple(self.hopper),
            tuple(ice_block.key() for ice_block in self.ice_blocks),
            tuple(lock_bar.key() for lock_bar in self.lock_bars),
            self.lost,
        )


@dataclass
class SolveResult:
    file_path: str
    status: str
    attempt: int = 0
    difficulty_score: Optional[float] = None
    difficulty_label: str = ""
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
                    gate.append(TrayState(layers=layers, ice_hp=self._parse_tray_ice(tray)))
            gates.append(gate)

        obstacle_blocked = [[False for _ in range(cols)] for _ in range(rows)]
        ice_blocks: List[IceBlockState] = []
        lock_bars: List[LockBarState] = []
        for obstacle in grid.get("obstacles", []) or []:
            obstacle_type = obstacle.get("type")
            if obstacle_type == "IceBlock":
                obstacle_cells = tuple(
                    (row, col)
                    for row, col in self._expand_obstacle_cells(obstacle)
                    if 0 <= row < rows and 0 <= col < cols
                )
                hp = max(1, int(obstacle.get("hp", 1) or 1))
                if obstacle_cells:
                    ice_blocks.append(IceBlockState(cells=obstacle_cells, hp=hp))
            elif obstacle_type == "LockBar":
                lock_cells = self._expand_lockbar_cells(obstacle)
                if lock_cells:
                    head = lock_cells[0]
                    trigger = self._offset_unbounded(head[0], head[1], self._opposite_direction(obstacle.get("direction", "Right")))
                    lock_bars.append(LockBarState(cells=tuple(lock_cells), trigger=trigger))

        connected_groups = self._parse_connected_groups(grid)
        base_obstacle_blocked = tuple(tuple(row) for row in obstacle_blocked)

        state = GameState(
            rows=rows,
            cols=cols,
            cells=cells,
            gates=gates,
            base_obstacle_blocked=base_obstacle_blocked,
            obstacle_blocked=base_obstacle_blocked,
            ice_blocks=ice_blocks,
            lock_bars=lock_bars,
            connected_groups=connected_groups,
        )
        self.settle_tunnels(state)
        self.refresh_obstacle_blocking(state)
        return state

    def capacity_balance_errors(self) -> List[str]:
        state = self.initial_state()
        shooter_capacity: Dict[str, int] = {}
        tray_required: Dict[str, int] = {}

        for cell in state.cells:
            if cell.type == "Shooter" and cell.shooter:
                shooter_capacity[cell.shooter.color] = (
                    shooter_capacity.get(cell.shooter.color, 0) + cell.shooter.capacity
                )
            elif cell.type == "Tunnel":
                for shooter in cell.queue:
                    shooter_capacity[shooter.color] = (
                        shooter_capacity.get(shooter.color, 0) + shooter.capacity
                    )

        for gate in state.gates:
            for tray in gate:
                for color, required in tray.layers:
                    tray_required[color] = tray_required.get(color, 0) + int(required)

        errors = []
        for color in sorted(set(shooter_capacity) | set(tray_required)):
            capacity = shooter_capacity.get(color, 0)
            required = tray_required.get(color, 0)
            if capacity == required:
                continue
            errors.append(
                f"{color}: shooter capacity={capacity}, tray required={required}, "
                f"delta={capacity - required:+d}"
            )
        return errors

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
        multiplier = 1
        for modifier in shooter.get("modifiers", []) or []:
            if modifier.get("type") == "Ice":
                ice_hp = max(ice_hp, int(modifier.get("hp", 1)))
            elif modifier.get("type") == "Special":
                multiplier = 2
        return ShooterState(
            color=str(shooter.get("colorId", "None")),
            capacity=max(0, int(shooter.get("capacity", 0))) * multiplier,
            shooter_id=str(shooter.get("shooterId", "")),
            ice_hp=ice_hp,
        )

    def _parse_tray_ice(self, tray: Dict[str, Any]) -> int:
        ice_hp = 0
        for modifier in tray.get("modifiers", []) or []:
            if modifier.get("type") == "Ice":
                ice_hp = max(ice_hp, int(modifier.get("hp", TRAY_ICE_DEFAULT_HP)))
        return ice_hp

    def _parse_connected_groups(self, grid: Dict[str, Any]) -> Tuple[Tuple[str, ...], ...]:
        groups = []
        for group in grid.get("shooterGroups", []) or []:
            if group.get("type") != "Connected":
                continue
            members = tuple(str(shooter_id) for shooter_id in group.get("shooterIds", []) or [] if str(shooter_id))
            if len(members) >= 2:
                groups.append(members)
        return tuple(groups)

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
        active_ids = set()
        for index, cell in enumerate(state.cells):
            if cell.type != "Shooter" or not cell.shooter:
                continue
            if cell.shooter.capacity <= 0 or cell.shooter.ice_hp > 0:
                continue
            row, col = divmod(index, state.cols)
            if state.obstacle_blocked and state.obstacle_blocked[row][col]:
                continue
            if self.has_path_to_exit(state, row, col):
                active.append((row, col, cell.shooter))
                if cell.shooter.shooter_id:
                    active_ids.add(cell.shooter.shooter_id)

        for group in state.connected_groups:
            if not any(shooter_id in active_ids for shooter_id in group):
                continue
            group_ids = set(group)
            for index, cell in enumerate(state.cells):
                if cell.type != "Shooter" or not cell.shooter:
                    continue
                if cell.shooter.shooter_id not in group_ids:
                    continue
                if cell.shooter.capacity <= 0 or cell.shooter.ice_hp > 0:
                    continue
                row, col = divmod(index, state.cols)
                if state.obstacle_blocked and state.obstacle_blocked[row][col]:
                    continue
                action = (row, col, cell.shooter)
                if action not in active:
                    active.append(action)
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
        if state.obstacle_blocked and state.obstacle_blocked[row][col]:
            return False
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
        if state.obstacle_blocked and state.obstacle_blocked[row][col]:
            return False
        if not self.has_path_to_exit(state, row, col):
            if not self._can_group_member_click(state, shooter):
                return False
        state.clicks.append(ClickAction(row, col, shooter.color))
        group_members = self._connected_group_member_indexes(state, shooter)
        released_balls = 0
        if group_members:
            ordered_members = [index] + [member_index for member_index in group_members if member_index != index]
            for member_index in ordered_members:
                member = state.cells[member_index]
                if member.type == "Shooter" and member.shooter:
                    released_balls += member.shooter.capacity
                    state.hopper.extend([member.shooter.color] * member.shooter.capacity)
                    state.cells[member_index] = CellState("Empty")
        else:
            released_balls = shooter.capacity
            state.hopper.extend([shooter.color] * shooter.capacity)
            state.cells[index] = CellState("Empty")
        # Ice progress is awarded when a cleared shooter releases its balls.
        self.damage_ice(state, released_balls)
        self.refresh_obstacle_blocking(state)
        self.settle_tunnels(state)
        self.refresh_obstacle_blocking(state)
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
                if state.obstacle_blocked and state.obstacle_blocked[out_row][out_col]:
                    continue
                state.cells[out_index] = CellState("Shooter", shooter=cell.queue.pop(0))
                changed = True

    def refresh_obstacle_blocking(self, state: GameState) -> None:
        for lock_bar in state.lock_bars:
            if not lock_bar.active:
                continue
            trigger_row, trigger_col = lock_bar.trigger
            if not (0 <= trigger_row < state.rows and 0 <= trigger_col < state.cols):
                lock_bar.active = False
                continue
            trigger_cell = state.cells[trigger_row * state.cols + trigger_col]
            if trigger_cell.type == "Empty":
                lock_bar.active = False

        blocked = [list(row) for row in (state.base_obstacle_blocked or state.obstacle_blocked)]
        for ice_block in state.ice_blocks:
            if ice_block.hp <= 0:
                continue
            for row, col in ice_block.cells:
                if 0 <= row < state.rows and 0 <= col < state.cols:
                    blocked[row][col] = True
        for lock_bar in state.lock_bars:
            if not lock_bar.active:
                continue
            for row, col in lock_bar.cells:
                if 0 <= row < state.rows and 0 <= col < state.cols:
                    blocked[row][col] = True
        state.obstacle_blocked = tuple(tuple(row) for row in blocked)

    def refresh_lock_bars(self, state: GameState) -> None:
        self.refresh_obstacle_blocking(state)

    def _can_group_member_click(self, state: GameState, shooter: ShooterState) -> bool:
        if not shooter.shooter_id:
            return False
        group = self._connected_group_for_shooter(state, shooter.shooter_id)
        if not group:
            return False
        group_ids = set(group)
        for index, cell in enumerate(state.cells):
            if cell.type != "Shooter" or not cell.shooter:
                continue
            if cell.shooter.shooter_id not in group_ids:
                continue
            if cell.shooter.capacity <= 0 or cell.shooter.ice_hp > 0:
                continue
            row, col = divmod(index, state.cols)
            if state.obstacle_blocked and state.obstacle_blocked[row][col]:
                continue
            if self.has_path_to_exit(state, row, col):
                return True
        return False

    def _connected_group_member_indexes(self, state: GameState, shooter: ShooterState) -> List[int]:
        if not shooter.shooter_id:
            return []
        group = self._connected_group_for_shooter(state, shooter.shooter_id)
        if not group:
            return []
        group_ids = set(group)
        return [
            index
            for index, cell in enumerate(state.cells)
            if cell.type == "Shooter" and cell.shooter and cell.shooter.shooter_id in group_ids
        ]

    def _connected_group_for_shooter(self, state: GameState, shooter_id: str) -> Optional[Tuple[str, ...]]:
        for group in state.connected_groups:
            if shooter_id in group:
                return group
        return None

    def step(self, state: GameState) -> None:
        if state.lost:
            return
        state.steps += 1
        last = state.conveyor[-1]
        for index in range(CONVEYOR_SLOTS - 1, 0, -1):
            state.conveyor[index] = state.conveyor[index - 1]
        state.conveyor[0] = last

        consumed_slots: set[int] = set()
        for gate_index in GATE_PRIORITY:
            if gate_index >= len(state.gates) or not state.gates[gate_index]:
                continue
            for slot in GATE_PICKUP_RANGES[gate_index]:
                slot %= CONVEYOR_SLOTS
                if slot in consumed_slots:
                    continue
                ball = state.conveyor[slot]
                if (
                    ball is not None
                    and self._gate_needs_color(state, gate_index, ball)
                    and not self._earlier_gate_needs_color(state, gate_index, ball)
                ):
                    state.conveyor[slot] = None
                    consumed_slots.add(slot)
                    self._consume_gate_ball(state, gate_index)
                    self.settle_tunnels(state)

        if state.hopper and state.conveyor[0] is None:
            state.conveyor[0] = state.hopper.pop(0)

        if state.hopper and all(slot is not None for slot in state.conveyor):
            needed = set(self.front_gate_colors(state))
            if not needed or not any(slot in needed for slot in state.conveyor if slot is not None):
                state.lost = True

    def _gate_needs_color(self, state: GameState, gate_index: int, color: str) -> bool:
        tray = self._front_tray(state, gate_index)
        if not tray or tray.ice_hp > 0 or not tray.layers or not tray.layers[0]:
            return False
        return tray.layers[0][0] == color

    def _earlier_gate_needs_color(self, state: GameState, gate_index: int, color: str) -> bool:
        for earlier_gate_index in GATE_PRIORITY:
            if earlier_gate_index == gate_index:
                return False
            if self._gate_needs_color(state, earlier_gate_index, color):
                return True
        return False

    def _consume_gate_ball(self, state: GameState, gate_index: int) -> None:
        tray = state.gates[gate_index][0]
        layer = tray.layers[0]
        layer[1] -= 1
        self.decrement_adjacent_tray_ice(state, gate_index)
        if layer[1] > 0:
            return
        tray.layers.pop(0)
        if not tray.layers:
            state.gates[gate_index].pop(0)

    def decrement_ice(self, state: GameState) -> None:
        self.damage_ice(state, 1)

    def damage_ice(self, state: GameState, amount: int) -> None:
        amount = max(0, int(amount))
        if amount <= 0:
            return
        for cell in state.cells:
            if cell.type == "Shooter" and cell.shooter and cell.shooter.ice_hp > 0:
                cell.shooter.ice_hp = max(0, cell.shooter.ice_hp - amount)
            if cell.type == "Tunnel":
                for shooter in cell.queue:
                    if shooter.ice_hp > 0:
                        shooter.ice_hp = max(0, shooter.ice_hp - amount)
        for ice_block in state.ice_blocks:
            if ice_block.hp > 0:
                ice_block.hp = max(0, ice_block.hp - amount)
        self.refresh_obstacle_blocking(state)

    def decrement_adjacent_tray_ice(self, state: GameState, gate_index: int) -> None:
        front_trays = self._front_tray_refs(state)
        receiving_index = next(
            (index for index, (front_gate_index, _tray) in enumerate(front_trays) if front_gate_index == gate_index),
            None,
        )
        if receiving_index is None:
            return
        for neighbor_index in (receiving_index - 1, receiving_index + 1):
            if not (0 <= neighbor_index < len(front_trays)):
                continue
            _front_gate_index, tray = front_trays[neighbor_index]
            if tray.ice_hp > 0:
                tray.ice_hp -= 1

    def front_gate_colors(self, state: GameState) -> List[str]:
        colors = []
        for gate_index in range(len(state.gates)):
            tray = self._front_tray(state, gate_index)
            if tray and tray.ice_hp <= 0 and tray.layers and tray.layers[0]:
                colors.append(tray.layers[0][0])
        return colors

    def _front_tray(self, state: GameState, gate_index: int) -> Optional[TrayState]:
        if not (0 <= gate_index < len(state.gates)):
            return None
        gate = state.gates[gate_index]
        return gate[0] if gate else None

    def _front_tray_refs(self, state: GameState) -> List[Tuple[int, TrayState]]:
        return [
            (gate_index, gate[0])
            for gate_index, gate in enumerate(state.gates)
            if gate
        ]

    def advance_to_decision(self, state: GameState, max_steps: int = DEFAULT_MAX_STEPS) -> None:
        while (
            not self.is_win(state)
            and not self.is_dead(state)
            and state.steps < max_steps
        ):
            active = self.active_shooters(state)
            if len(state.hopper) < HOPPER_CLICK_LIMIT and active:
                if not self._should_wait_for_in_flight_balls(state, active):
                    return
            before_key = state.key()
            self.step(state)
            if state.key() == before_key and not self.active_shooters(state):
                state.lost = True
                return

    def _should_wait_for_in_flight_balls(
        self,
        state: GameState,
        active: Sequence[Tuple[int, int, ShooterState]],
    ) -> bool:
        needed = set(self.front_gate_colors(state))
        if not needed:
            return False
        if any(shooter.color in needed for _row, _col, shooter in active):
            return False
        in_flight = set(state.hopper)
        in_flight.update(ball for ball in state.conveyor if ball is not None)
        return bool(needed & in_flight)

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

    def _expand_obstacle_cells(self, obstacle: Dict[str, Any]) -> List[Tuple[int, int]]:
        shape = obstacle.get("shape", {}) or {}
        origin = shape.get("origin", {}) or {}
        origin_row = int(origin.get("row", 0) or 0)
        origin_col = int(origin.get("column", 0) or 0)
        shape_type = shape.get("type", "Rect")
        default_size = 3 if obstacle.get("type") == "IceBlock" else 1
        if shape_type == "CustomCells":
            return [
                (int(cell.get("row", 0) or 0), int(cell.get("column", 0) or 0))
                for cell in shape.get("cells", []) or []
            ]
        if shape_type == "Plus":
            return [
                (origin_row, origin_col),
                (origin_row - 1, origin_col),
                (origin_row + 1, origin_col),
                (origin_row, origin_col - 1),
                (origin_row, origin_col + 1),
            ]
        if shape_type == "LineHorizontal":
            width = max(1, int(shape.get("width", default_size) or default_size))
            return [(origin_row, origin_col + col) for col in range(width)]
        if shape_type == "LineVertical":
            height = max(1, int(shape.get("height", default_size) or default_size))
            return [(origin_row + row, origin_col) for row in range(height)]
        width = max(1, int(shape.get("width", default_size) or default_size))
        height = max(1, int(shape.get("height", default_size) or default_size))
        return [
            (origin_row + row, origin_col + col)
            for row in range(height)
            for col in range(width)
        ]

    def _expand_lockbar_cells(self, obstacle: Dict[str, Any]) -> List[Tuple[int, int]]:
        shape = obstacle.get("shape", {}) or {}
        origin = shape.get("origin", {}) or {}
        row = int(origin.get("row", 0) or 0)
        col = int(origin.get("column", 0) or 0)
        cells = [(row, col)]
        for _ in range(1, max(1, int(obstacle.get("length", 3) or 3))):
            row, col = self._offset_unbounded(row, col, obstacle.get("direction", "Right"))
            cells.append((row, col))
        return cells

    def _offset_unbounded(self, row: int, col: int, direction: str) -> Tuple[int, int]:
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
        balance_errors = self.simulator.capacity_balance_errors()
        if balance_errors:
            return SolveResult(
                file_path=path,
                status="ERROR",
                elapsed=time.monotonic() - started,
                message="Capacity/tray mismatch:\n" + "\n".join(
                    f"- {error}" for error in balance_errors
                ),
            )
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
        needed = set(self.simulator.front_gate_colors(state))
        active = self.simulator.active_shooters(state)
        matching = sum(1 for _row, _col, shooter in active if shooter.color in needed)
        decoys = max(0, len(active) - matching)
        deadlock_pressure = 0.0
        if needed and active and matching == 0:
            deadlock_pressure = 2500.0
        elif needed:
            deadlock_pressure = decoys * 12.0 - matching * 20.0
        hopper_pressure = max(0, len(state.hopper) - HOPPER_CLICK_LIMIT // 2) * 10.0
        return (
            remaining * 20
            + blocked * 5
            + moving * 2
            + hopper_pressure
            + deadlock_pressure
            + state.steps * 0.03
            + randomizer.random()
        )

    def _progress_score(self, state: GameState) -> int:
        return -self._remaining_total_need(state) * 100 - len(state.hopper) - state.steps

    def _remaining_total_need(self, state: GameState) -> int:
        total = 0
        for gate in state.gates:
            for tray in gate:
                for _, remaining in tray.layers:
                    total += int(remaining)
        return total

    def _remaining_color_need(self, state: GameState, color: str) -> int:
        total = 0
        for gate in state.gates:
            for tray in gate:
                for layer_color, remaining in tray.layers:
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

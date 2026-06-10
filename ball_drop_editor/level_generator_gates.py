from __future__ import annotations

import random
from typing import Any, Dict, List, Sequence, Tuple

from .level_generator_models import GateLayoutMetrics
from .utils import short_id

TrayChunk = Tuple[str, int]


def build_tray_chunks(
    solution_colors: Sequence[str],
    shooter_capacity: int,
    tray_unit: int,
) -> List[TrayChunk]:
    chunks: List[TrayChunk] = []
    capacity = max(1, int(shooter_capacity))
    unit = max(1, int(tray_unit))
    for color in solution_colors:
        remaining = capacity
        while remaining > 0:
            required = min(unit, remaining)
            chunks.append((str(color), required))
            remaining -= required
    return chunks


def analyze_gate_layout(gates: Sequence[Dict[str, Any]]) -> GateLayoutMetrics:
    queues = [_gate_chunks(gate) for gate in gates]
    metrics = analyze_chunk_layout(queues)
    metrics.avoidable_repeats = _count_improving_swaps(queues)
    return metrics


def analyze_chunk_layout(queues: Sequence[Sequence[TrayChunk]]) -> GateLayoutMetrics:
    max_run = 0
    adjacent = 0
    repeat_gaps: List[int] = []
    for queue in queues:
        previous = None
        run = 0
        last_seen: Dict[str, int] = {}
        for index, (color, _required) in enumerate(queue):
            if color == previous:
                run += 1
                adjacent += 1
            else:
                run = 1
            max_run = max(max_run, run)
            if color in last_seen:
                repeat_gaps.append(max(0, index - last_seen[color] - 1))
            last_seen[color] = index
            previous = color

    duplicate_depth = 0
    max_depth = max((len(queue) for queue in queues), default=0)
    for depth in range(max_depth):
        colors = [queue[depth][0] for queue in queues if depth < len(queue)]
        duplicate_depth += max(0, len(colors) - len(set(colors)))

    lengths = [len(queue) for queue in queues]
    average_gap = sum(repeat_gaps) / len(repeat_gaps) if repeat_gaps else float(max_depth)
    return GateLayoutMetrics(
        max_same_color_run=max_run,
        adjacent_same_pairs=adjacent,
        duplicate_depth_pairs=duplicate_depth,
        average_repeat_gap=average_gap,
        queue_imbalance=(max(lengths) - min(lengths)) if lengths else 0,
    )


def schedule_tray_chunks(
    chunks: Sequence[TrayChunk],
    gate_count: int,
    rng: random.Random,
    candidate_count: int | None = None,
) -> tuple[List[Dict[str, Any]], GateLayoutMetrics]:
    gate_count = max(1, int(gate_count))
    attempts = max(16, gate_count * 8, int(candidate_count or 0))
    best_queues: List[List[TrayChunk]] | None = None
    best_metrics: GateLayoutMetrics | None = None

    for _attempt in range(attempts):
        queues = _build_greedy_layout(chunks, gate_count, rng)
        metrics = analyze_chunk_layout(queues)
        if best_metrics is None or metrics.rank() < best_metrics.rank():
            best_queues = queues
            best_metrics = metrics

    if best_queues is None or best_metrics is None:
        best_queues = [[] for _ in range(gate_count)]
        best_metrics = analyze_chunk_layout(best_queues)

    best_queues, best_metrics = _improve_by_swapping(best_queues)
    best_metrics.avoidable_repeats = _count_improving_swaps(best_queues)
    gates = [
        {
            "gateIndex": gate_index,
            "trayQueue": [
                {
                    "trayId": short_id("t"),
                    "layers": [{"colorId": color, "requiredCount": required}],
                }
                for color, required in queue
            ],
        }
        for gate_index, queue in enumerate(best_queues)
    ]
    return gates, best_metrics


def _build_greedy_layout(
    chunks: Sequence[TrayChunk],
    gate_count: int,
    rng: random.Random,
) -> List[List[TrayChunk]]:
    remaining = list(chunks)
    rng.shuffle(remaining)
    queues: List[List[TrayChunk]] = [[] for _ in range(gate_count)]
    gate_order = list(range(gate_count))
    rng.shuffle(gate_order)

    while remaining:
        min_length = min(len(queue) for queue in queues)
        eligible_gates = [gate for gate in gate_order if len(queues[gate]) == min_length]
        if not eligible_gates:
            eligible_gates = list(gate_order)
        for gate_index in eligible_gates:
            if not remaining:
                break
            depth = len(queues[gate_index])
            depth_colors = {
                queues[other][depth][0]
                for other in range(gate_count)
                if depth < len(queues[other])
            }
            previous = queues[gate_index][-1][0] if queues[gate_index] else None
            last_seen = _last_seen_by_color(queues[gate_index])
            scored: List[tuple[tuple[float, ...], int]] = []
            for index, (color, _required) in enumerate(remaining):
                repeat_gap = depth - last_seen.get(color, -gate_count - 2) - 1
                score = (
                    1.0 if color == previous else 0.0,
                    1.0 if color in depth_colors else 0.0,
                    -float(repeat_gap),
                    rng.random(),
                )
                scored.append((score, index))
            _, selected_index = min(scored, key=lambda item: item[0])
            queues[gate_index].append(remaining.pop(selected_index))
        gate_order = gate_order[1:] + gate_order[:1]
    return queues


def _improve_by_swapping(
    queues: Sequence[Sequence[TrayChunk]],
) -> tuple[List[List[TrayChunk]], GateLayoutMetrics]:
    current = [list(queue) for queue in queues]
    current_metrics = analyze_chunk_layout(current)
    positions = [(gate, index) for gate, queue in enumerate(current) for index in range(len(queue))]
    max_rounds = max(1, len(positions))

    for _round in range(max_rounds):
        best_swap = None
        best_metrics = current_metrics
        for left_index, (left_gate, left_pos) in enumerate(positions):
            for right_gate, right_pos in positions[left_index + 1 :]:
                if current[left_gate][left_pos][0] == current[right_gate][right_pos][0]:
                    continue
                current[left_gate][left_pos], current[right_gate][right_pos] = (
                    current[right_gate][right_pos],
                    current[left_gate][left_pos],
                )
                metrics = analyze_chunk_layout(current)
                current[left_gate][left_pos], current[right_gate][right_pos] = (
                    current[right_gate][right_pos],
                    current[left_gate][left_pos],
                )
                if metrics.rank() < best_metrics.rank():
                    best_swap = (left_gate, left_pos, right_gate, right_pos)
                    best_metrics = metrics
        if best_swap is None:
            break
        left_gate, left_pos, right_gate, right_pos = best_swap
        current[left_gate][left_pos], current[right_gate][right_pos] = (
            current[right_gate][right_pos],
            current[left_gate][left_pos],
        )
        current_metrics = best_metrics
    return current, current_metrics


def _count_improving_swaps(queues: Sequence[Sequence[TrayChunk]]) -> int:
    current = [list(queue) for queue in queues]
    current_rank = analyze_chunk_layout(current).rank()
    positions = [(gate, index) for gate, queue in enumerate(current) for index in range(len(queue))]
    improving = 0
    for left_index, (left_gate, left_pos) in enumerate(positions):
        for right_gate, right_pos in positions[left_index + 1 :]:
            if current[left_gate][left_pos][0] == current[right_gate][right_pos][0]:
                continue
            current[left_gate][left_pos], current[right_gate][right_pos] = (
                current[right_gate][right_pos],
                current[left_gate][left_pos],
            )
            if analyze_chunk_layout(current).rank() < current_rank:
                improving += 1
            current[left_gate][left_pos], current[right_gate][right_pos] = (
                current[right_gate][right_pos],
                current[left_gate][left_pos],
            )
    return improving


def _last_seen_by_color(queue: Sequence[TrayChunk]) -> Dict[str, int]:
    return {color: index for index, (color, _required) in enumerate(queue)}


def _gate_chunks(gate: Dict[str, Any]) -> List[TrayChunk]:
    chunks: List[TrayChunk] = []
    for tray in gate.get("trayQueue", []) or []:
        layers = tray.get("layers", []) or []
        if not layers:
            continue
        layer = layers[0]
        chunks.append((str(layer.get("colorId", "None")), int(layer.get("requiredCount", 0) or 0)))
    return chunks

from __future__ import annotations

from typing import Any, Dict, List

from .constants import BALL_COLORS, GRID_OBSTACLE_TYPES
from .level_generator import DIFFICULTY_TARGETS, GeneratorPhase
from .level_tester_score import SolverScoreResult
from .utils import safe_int


class LevelGeneratorWindowPhaseMixin:
    def _load_default_phases(self) -> None:
        if not hasattr(self, "phase_tree"):
            return
        for item in self.phase_tree.get_children():
            self.phase_tree.delete(item)
        shooter_count = max(1, safe_int(str(self.shooter_count_var.get()), 20))
        segments = [
            ("Warmup", 1, max(1, shooter_count // 5), "Easy", 1, 1, 1, 0, 0, 0),
            ("Decision Spike", max(2, shooter_count // 5 + 1), max(2, shooter_count // 2), "Hard", 3, 2, 2, 3, 1, 1),
            ("Relief", max(3, shooter_count // 2 + 1), max(3, shooter_count * 3 // 5), "Normal", 1, 1, 1, 0, 0, 0),
            ("Pressure Spike", max(4, shooter_count * 3 // 5 + 1), max(4, shooter_count * 4 // 5), "Hard", 2, 3, 2, 1, 2, 2),
            ("Final Maze", max(5, shooter_count * 4 // 5 + 1), shooter_count, "VeryHard", 3, 3, 3, 2, 3, 3),
        ]
        for segment in segments:
            if segment[1] <= segment[2]:
                values = self._make_phase_tree_values(True, *segment)
                self.phase_tree.insert("", "end", values=values)

    def _phase_enabled_label(self, enabled: bool) -> str:
        return "[x]" if enabled else "[ ]"

    def _phase_label_is_enabled(self, value: Any) -> bool:
        return str(value).strip().lower() in {"[x]", "x", "yes", "true", "1", "on", "enabled"}

    def _make_phase_tree_values(
        self,
        enabled: bool,
        name: Any,
        start: Any,
        end: Any,
        target: Any,
        decision: Any,
        conveyor: Any,
        unlock: Any,
        same_color: Any,
        tunnel: Any,
        obstacle: Any,
    ) -> tuple[Any, ...]:
        target_name = target if target in DIFFICULTY_TARGETS else "Normal"
        return (
            self._phase_enabled_label(bool(enabled)),
            str(name).strip() or "Phase",
            max(1, safe_int(str(start), 1)),
            max(1, safe_int(str(end), 1)),
            target_name,
            max(0, safe_int(str(decision), 0)),
            max(0, safe_int(str(conveyor), 0)),
            max(0, safe_int(str(unlock), 0)),
            max(0, safe_int(str(same_color), 0)),
            max(0, safe_int(str(tunnel), 0)),
            max(0, safe_int(str(obstacle), 0)),
        )

    def _parse_phase_tree_values(self, values: Any) -> tuple[Any, ...]:
        raw_values = list(values or [])
        if len(raw_values) >= 11:
            enabled = self._phase_label_is_enabled(raw_values[0])
            phase_values = raw_values[1:]
        else:
            enabled = True
            phase_values = raw_values
        phase_values = phase_values + [""] * max(0, 10 - len(phase_values))
        target_name = phase_values[3] if phase_values[3] in DIFFICULTY_TARGETS else "Normal"
        return (
            enabled,
            str(phase_values[0]).strip() or "Phase",
            max(1, safe_int(str(phase_values[1]), 1)),
            max(1, safe_int(str(phase_values[2]), 1)),
            target_name,
            max(0, safe_int(str(phase_values[4]), 0)),
            max(0, safe_int(str(phase_values[5]), 0)),
            max(0, safe_int(str(phase_values[6]), 0)),
            max(0, safe_int(str(phase_values[7]), 0)),
            max(0, safe_int(str(phase_values[8]), 0)),
            max(0, safe_int(str(phase_values[9]), 0)),
        )

    def load_selected_phase(self, _event=None) -> None:
        selected = self.phase_tree.selection()
        if not selected:
            return
        values = self.phase_tree.item(selected[0], "values")
        (
            enabled,
            name,
            start,
            end,
            target,
            decision,
            conveyor,
            unlock,
            same_color,
            tunnel,
            obstacle,
        ) = self._parse_phase_tree_values(values)
        self.phase_enabled_var.set(enabled)
        self.phase_name_var.set(name)
        self.phase_start_var.set(start)
        self.phase_end_var.set(end)
        self.phase_target_var.set(target)
        self.phase_decision_var.set(decision)
        self.phase_conveyor_var.set(conveyor)
        self.phase_unlock_var.set(unlock)
        self.phase_same_color_var.set(same_color)
        self.phase_tunnel_var.set(tunnel)
        self.phase_obstacle_var.set(obstacle)

    def toggle_phase_enabled(self, event) -> Optional[str]:
        if self.phase_tree.identify_region(event.x, event.y) != "cell":
            return None
        if self.phase_tree.identify_column(event.x) != "#1":
            return None
        item = self.phase_tree.identify_row(event.y)
        if not item:
            return "break"
        values = self.phase_tree.item(item, "values")
        (
            enabled,
            name,
            start,
            end,
            target,
            decision,
            conveyor,
            unlock,
            same_color,
            tunnel,
            obstacle,
        ) = self._parse_phase_tree_values(values)
        new_values = self._make_phase_tree_values(
            not enabled,
            name,
            start,
            end,
            target,
            decision,
            conveyor,
            unlock,
            same_color,
            tunnel,
            obstacle,
        )
        self.phase_tree.item(item, values=new_values, tags=() if not enabled else ("disabled",))
        self.phase_tree.selection_set(item)
        self.phase_enabled_var.set(not enabled)
        return "break"

    def upsert_phase(self) -> None:
        values = self._make_phase_tree_values(
            self.phase_enabled_var.get(),
            self.phase_name_var.get().strip() or "Phase",
            max(1, safe_int(str(self.phase_start_var.get()), 1)),
            max(1, safe_int(str(self.phase_end_var.get()), 1)),
            self.phase_target_var.get() if self.phase_target_var.get() in DIFFICULTY_TARGETS else "Normal",
            max(0, safe_int(str(self.phase_decision_var.get()), 0)),
            max(0, safe_int(str(self.phase_conveyor_var.get()), 0)),
            max(0, safe_int(str(self.phase_unlock_var.get()), 0)),
            max(0, safe_int(str(self.phase_same_color_var.get()), 0)),
            max(0, safe_int(str(self.phase_tunnel_var.get()), 0)),
            max(0, safe_int(str(self.phase_obstacle_var.get()), 0)),
        )
        tags = () if self.phase_enabled_var.get() else ("disabled",)
        selected = self.phase_tree.selection()
        if selected:
            self.phase_tree.item(selected[0], values=values, tags=tags)
        else:
            self.phase_tree.insert("", "end", values=values, tags=tags)

    def delete_phase(self) -> None:
        for item in self.phase_tree.selection():
            self.phase_tree.delete(item)

    def _level_colors(self, level: Dict[str, Any]) -> List[str]:
        colors: set[str] = set()
        for cell in level.get("grid", {}).get("cells", []) or []:
            entity = cell.get("entity") or {}
            if entity.get("type") == "Shooter":
                color = entity.get("shooter", {}).get("colorId")
                if color in BALL_COLORS and color != "None":
                    colors.add(color)
            elif entity.get("type") == "Tunnel":
                for shooter in entity.get("shooterQueue", []) or []:
                    color = shooter.get("colorId")
                    if color in BALL_COLORS and color != "None":
                        colors.add(color)
        for gate in level.get("gateSystem", {}).get("gates", []) or []:
            for tray in gate.get("trayQueue", []) or []:
                for layer in tray.get("layers", []) or []:
                    color = layer.get("colorId")
                    if color in BALL_COLORS and color != "None":
                        colors.add(color)
        return [color for color in self.generator_palette if color in colors]

    def _estimate_tray_unit(self, level: Dict[str, Any]) -> int:
        counts: Dict[int, int] = {}
        for gate in level.get("gateSystem", {}).get("gates", []) or []:
            for tray in gate.get("trayQueue", []) or []:
                for layer in tray.get("layers", []) or []:
                    required = max(1, safe_int(str(layer.get("requiredCount", 0)), 1))
                    counts[required] = counts.get(required, 0) + 1
        if not counts:
            return max(1, safe_int(str(self.tray_unit_var.get()), 3))
        return max(counts, key=lambda value: (counts[value], value))

    def _reference_phase_rows(self, score: SolverScoreResult) -> List[tuple[Any, ...]]:
        groups: List[Dict[str, Any]] = []
        for item in score.per_click_scores:
            target = self._target_name_for_score(item.score)
            if not groups or groups[-1]["target"] != target:
                groups.append({"target": target, "items": []})
            groups[-1]["items"].append(item)
        while len(groups) > 8:
            merge_index = min(
                range(len(groups) - 1),
                key=lambda index: abs(self._group_average(groups[index]) - self._group_average(groups[index + 1])),
            )
            groups[merge_index]["items"].extend(groups[merge_index + 1]["items"])
            groups[merge_index]["target"] = self._target_name_for_score(self._group_average(groups[merge_index]))
            groups.pop(merge_index + 1)

        rows: List[tuple[Any, ...]] = []
        for index, group in enumerate(groups, start=1):
            items = group["items"]
            avg_score = self._group_average(group)
            target = self._target_name_for_score(avg_score)
            metrics = [item.metrics for item in items]
            active = sum(metric.active_choices for metric in metrics) / max(1, len(metrics))
            decoys = sum(metric.decoys for metric in metrics) / max(1, len(metrics))
            same = sum(metric.same_color_route_traps for metric in metrics) / max(1, len(metrics))
            conveyor = sum(metric.conveyor_pressure for metric in metrics) / max(1, len(metrics))
            unlock = sum(metric.unlock_depth for metric in metrics) / max(1, len(metrics))
            tunnel = sum(metric.tunnel_pressure for metric in metrics) / max(1, len(metrics))
            obstacle = sum(metric.obstacle_pressure for metric in metrics) / max(1, len(metrics))
            rows.append(
                self._make_phase_tree_values(
                    True,
                    f"Ref {index} {target}",
                    items[0].click_index,
                    items[-1].click_index,
                    target,
                    self._clamp_phase_weight(round((max(0.0, active - 1.0) + decoys) / 2.0)),
                    self._clamp_phase_weight(round(conveyor * 3.0)),
                    self._clamp_phase_weight(round(unlock * 3.0)),
                    self._clamp_phase_weight(round(same)),
                    self._clamp_phase_weight(round(tunnel * 3.0)),
                    self._clamp_phase_weight(round(obstacle * 3.0)),
                )
            )
        return rows

    def _group_average(self, group: Dict[str, Any]) -> float:
        items = group.get("items", [])
        return sum(item.score for item in items) / max(1, len(items))

    def _target_name_for_score(self, score: float) -> str:
        return min(DIFFICULTY_TARGETS, key=lambda name: abs(DIFFICULTY_TARGETS[name] - score))

    def _clamp_phase_weight(self, value: int) -> int:
        return max(0, min(3, int(value)))

    def _replace_phase_rows(self, rows: List[tuple[Any, ...]]) -> None:
        for item in self.phase_tree.get_children():
            self.phase_tree.delete(item)
        for values in rows:
            self.phase_tree.insert("", "end", values=values)

    def _read_phases(self) -> List[GeneratorPhase]:
        phases: List[GeneratorPhase] = []
        for item in self.phase_tree.get_children():
            values = self.phase_tree.item(item, "values")
            if not values:
                continue
            (
                enabled,
                name,
                start,
                end,
                target,
                decision,
                conveyor,
                unlock,
                same_color,
                tunnel,
                obstacle,
            ) = self._parse_phase_tree_values(values)
            if not enabled:
                continue
            phases.append(
                GeneratorPhase(
                    name=name,
                    start_click=start,
                    end_click=end,
                    target=target,
                    decision_trap=decision,
                    conveyor_pressure=conveyor,
                    unlock_maze=unlock,
                    same_color_route=same_color,
                    tunnel_pressure=tunnel,
                    obstacle_pressure=obstacle,
                    obstacle_types=list(GRID_OBSTACLE_TYPES) + ["IceTray"],
                )
            )
        return phases

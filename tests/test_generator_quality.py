from __future__ import annotations

import unittest
from unittest.mock import patch

from ball_drop_editor.level_generator import (
    CandidateResult,
    DifficultyCurveGenerator,
    GateLayoutMetrics,
    GeneratorConfig,
    GeneratorPhase,
    count_generator_devices,
    infer_template_pressures,
)
from ball_drop_editor.level_generator_window_actions import LevelGeneratorWindowActionsMixin
from ball_drop_editor.level_data import find_cell, make_empty_level, make_shooter_entity
from ball_drop_editor.level_tester_core import BallDropSimulator
from ball_drop_editor.level_tester_score import SolverScoreResult


class GeneratorQualityTests(unittest.TestCase):
    def test_phase_weights_are_clamped(self) -> None:
        phase = GeneratorPhase("Test", 1, 5, decision_trap=9, conveyor_pressure=-2)
        self.assertEqual(phase.decision_trap, 3)
        self.assertEqual(phase.conveyor_pressure, 0)

    def test_high_phase_pressure_changes_generated_structure(self) -> None:
        common = dict(
            seed=17,
            rows=6,
            cols=5,
            shooter_count=25,
            wall_count=5,
            color_count=5,
            allowed_devices=["Wall"],
            candidate_attempts=1,
            solver_budget=0.1,
        )
        low_level = DifficultyCurveGenerator(
            GeneratorConfig(
                **common,
                phases=[GeneratorPhase("All", 1, 30, "Hard", 0, 0, 0, 0, 0, 0)],
            )
        )._build_candidate(1)
        high_level = DifficultyCurveGenerator(
            GeneratorConfig(
                **common,
                phases=[GeneratorPhase("All", 1, 30, "Hard", 3, 3, 3, 3, 0, 0)],
            )
        )._build_candidate(1)

        low_decoy_ratio = self._initial_decoy_ratio(low_level)
        high_decoy_ratio = self._initial_decoy_ratio(high_level)
        low_interior_walls = self._interior_wall_count(low_level)
        high_interior_walls = self._interior_wall_count(high_level)

        self.assertGreater(high_decoy_ratio, low_decoy_ratio)
        self.assertGreater(high_interior_walls, low_interior_walls)

    def test_fixed_seed_candidate_passes_solver_and_quality_gate(self) -> None:
        config = GeneratorConfig(
            seed=2,
            rows=4,
            cols=4,
            shooter_count=12,
            wall_count=4,
            color_count=4,
            allowed_devices=["Wall"],
            candidate_attempts=1,
            solver_budget=2.0,
            phases=[GeneratorPhase("All", 1, 20, "Normal", 2, 2, 1, 1, 0, 0)],
        )
        candidate = DifficultyCurveGenerator(config).generate_best()
        self.assertEqual(candidate.score.status, "PASS")
        self.assertTrue(candidate.quality_passed, candidate.quality_reasons)
        self.assertEqual(candidate.layout_metrics.avoidable_repeats, 0)

    def test_default_mechanics_candidate_remains_solvable(self) -> None:
        candidate = DifficultyCurveGenerator(
            GeneratorConfig(
                seed=0,
                candidate_attempts=1,
                solver_budget=5.0,
            )
        ).generate_best()
        self.assertEqual(candidate.score.status, "PASS")

    def test_exact_device_counts_are_honored(self) -> None:
        expected = {
            "Wall": 3,
            "Tunnel": 2,
            "IceBlock": 2,
            "IceShooter": 2,
            "IceTray": 2,
            "Special": 2,
            "ConnectedGroup": 1,
            "LockBar": 0,
        }
        config = GeneratorConfig(
            seed=0,
            rows=5,
            cols=5,
            shooter_count=20,
            wall_count=3,
            allowed_devices=list(expected),
            candidate_attempts=1,
            solver_budget=0.1,
            phases=[GeneratorPhase("All", 1, 30, "Hard", 3, 3, 3, 3, 3, 3)],
            exact_device_counts=expected,
        )
        level = DifficultyCurveGenerator(config)._build_candidate(1)
        self.assertEqual(count_generator_devices(level), expected)

    def test_exact_lockbar_count_is_honored_when_layout_allows_it(self) -> None:
        expected = {
            "Wall": 5,
            "Tunnel": 0,
            "IceBlock": 0,
            "IceShooter": 0,
            "IceTray": 0,
            "Special": 0,
            "ConnectedGroup": 0,
            "LockBar": 1,
        }
        config = GeneratorConfig(
            seed=0,
            rows=6,
            cols=5,
            shooter_count=25,
            wall_count=5,
            allowed_devices=["Wall", "LockBar"],
            candidate_attempts=1,
            solver_budget=0.1,
            phases=[GeneratorPhase("All", 1, 30, "Hard", 3, 3, 3, 3, 3, 3)],
            exact_device_counts=expected,
        )
        level = DifficultyCurveGenerator(config)._build_candidate(1)
        self.assertEqual(count_generator_devices(level)["LockBar"], 1)

    def test_template_analysis_counts_devices_and_infers_pressure(self) -> None:
        level = make_empty_level(3, 3, 2)
        find_cell(level, 0, 0)["entity"] = make_shooter_entity(
            0,
            0,
            "Blue",
            9,
            [{"type": "Special"}, {"type": "Ice", "hp": 9}],
        )
        level["grid"]["obstacles"] = [
            {
                "obstacleId": "ice_0",
                "type": "IceBlock",
                "hp": 1,
                "shape": {
                    "type": "CustomCells",
                    "origin": {"row": 0, "column": 0},
                    "width": 1,
                    "height": 1,
                    "cells": [{"row": 0, "column": 0}],
                },
            }
        ]

        counts = count_generator_devices(level)
        pressures = infer_template_pressures(level)
        self.assertEqual(counts["Special"], 1)
        self.assertEqual(counts["IceShooter"], 1)
        self.assertEqual(counts["IceBlock"], 1)
        self.assertGreater(pressures["decision"], 0)
        self.assertGreater(pressures["obstacle"], 0)

    def test_generated_ice_shooters_use_per_ball_progress_counts(self) -> None:
        config = GeneratorConfig(
            seed=4,
            rows=4,
            cols=4,
            shooter_count=14,
            wall_count=2,
            tray_unit=3,
            allowed_devices=["Wall", "IceShooter"],
            exact_device_counts={
                "Wall": 2,
                "Tunnel": 0,
                "IceBlock": 0,
                "IceShooter": 3,
                "IceTray": 0,
                "Special": 0,
                "ConnectedGroup": 0,
                "LockBar": 0,
            },
            phases=[GeneratorPhase("All", 1, 20, "Hard", 2, 2, 2, 1, 0, 3)],
        )
        level = DifficultyCurveGenerator(config)._build_candidate(1)
        hp_values = []
        for cell in level["grid"]["cells"]:
            entity = cell.get("entity") or {}
            shooters = []
            if entity.get("type") == "Shooter":
                shooters = [entity.get("shooter") or {}]
            elif entity.get("type") == "Tunnel":
                shooters = entity.get("shooterQueue", []) or []
            for shooter in shooters:
                hp_values.extend(
                    int(modifier["hp"])
                    for modifier in shooter.get("modifiers", []) or []
                    if modifier.get("type") == "Ice"
                )

        self.assertEqual(len(hp_values), 3)
        self.assertTrue(all(hp > 0 and hp % config.tray_unit == 0 for hp in hp_values))

    def test_quality_rejects_exact_count_mismatch(self) -> None:
        config = GeneratorConfig(
            phases=[GeneratorPhase("All", 1, 1, "Easy")],
            exact_device_counts={"IceBlock": 2},
        )
        generator = DifficultyCurveGenerator(config)
        score = SolverScoreResult(status="PASS", overall_score=100.0)
        passed, reasons = generator._quality_status(
            score,
            GateLayoutMetrics(),
            make_empty_level(1, 1, 1),
        )
        self.assertFalse(passed)
        self.assertTrue(any("IceBlock count" in reason for reason in reasons))

    def _initial_decoy_ratio(self, level) -> float:
        simulator = BallDropSimulator(level)
        state = simulator.initial_state()
        active = simulator.active_shooters(state)
        demand = set(simulator.front_gate_colors(state))
        decoys = sum(shooter.color not in demand for _, _, shooter in active)
        return decoys / max(1, len(active))

    def _interior_wall_count(self, level) -> int:
        rows = level["grid"]["rows"]
        return sum(
            1
            for cell in level["grid"]["cells"]
            if (cell.get("entity") or {}).get("type") == "Wall"
            and cell["row"] not in {0, rows - 1}
        )


class QualityConfirmationTests(unittest.TestCase):
    def test_quality_candidate_does_not_prompt(self) -> None:
        candidate = CandidateResult(
            level={},
            score=SolverScoreResult(status="PASS"),
            errors=[],
            warnings=[],
            target_error=0.0,
            attempt=1,
            quality_passed=True,
            layout_metrics=GateLayoutMetrics(),
        )
        with patch(
            "ball_drop_editor.level_generator_window_actions.messagebox.askyesno"
        ) as prompt:
            self.assertTrue(
                LevelGeneratorWindowActionsMixin._confirm_candidate_quality(
                    object(), candidate, "export"
                )
            )
            prompt.assert_not_called()

    def test_review_candidate_prompts_each_time(self) -> None:
        candidate = CandidateResult(
            level={},
            score=SolverScoreResult(status="PASS"),
            errors=[],
            warnings=[],
            target_error=20.0,
            attempt=1,
            quality_passed=False,
            quality_reasons=["Overall score is below target."],
            layout_metrics=GateLayoutMetrics(),
        )
        with patch(
            "ball_drop_editor.level_generator_window_actions.messagebox.askyesno",
            return_value=True,
        ) as prompt:
            for _ in range(2):
                self.assertTrue(
                    LevelGeneratorWindowActionsMixin._confirm_candidate_quality(
                        object(), candidate, "apply"
                    )
                )
            self.assertEqual(prompt.call_count, 2)


if __name__ == "__main__":
    unittest.main()

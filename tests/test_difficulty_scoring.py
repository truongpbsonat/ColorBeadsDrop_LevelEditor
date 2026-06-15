from __future__ import annotations

import unittest

from ball_drop_editor.level_tester_core import BallDropSimulator, DeepSearchSolver
from ball_drop_editor.level_tester_score import DifficultyMetrics, SolverScoreAdapter


def make_layout_level(gate_colors):
    return {
        "grid": {
            "rows": 1,
            "columns": 1,
            "cells": [{"row": 0, "column": 0, "entity": None}],
            "obstacles": [],
            "shooterGroups": [],
        },
        "gateSystem": {
            "gateCount": len(gate_colors),
            "maxVisibleTrayPerGate": 4,
            "gates": [
                {
                    "gateIndex": gate_index,
                    "trayQueue": [
                        {
                            "trayId": f"t_{gate_index}_{tray_index}",
                            "layers": [{"colorId": color, "requiredCount": 3}],
                        }
                        for tray_index, color in enumerate(colors)
                    ],
                }
                for gate_index, colors in enumerate(gate_colors)
            ],
        },
    }


class DifficultyScoringTests(unittest.TestCase):
    def test_alternating_trays_score_harder_than_grouped_trays(self) -> None:
        adapter = SolverScoreAdapter()
        grouped_state = BallDropSimulator(
            make_layout_level([["Blue", "Blue", "Red"], ["Red", "Red", "Blue"]])
        ).initial_state()
        mixed_state = BallDropSimulator(
            make_layout_level([["Blue", "Red", "Blue"], ["Red", "Blue", "Red"]])
        ).initial_state()

        grouped = adapter._tray_layout_pressure(grouped_state)
        mixed = adapter._tray_layout_pressure(mixed_state)
        base = dict(
            active_choices=3,
            decoys=1,
            same_color_route_traps=1,
            conveyor_pressure=0.5,
            unlock_depth=0.5,
            tunnel_pressure=0.0,
            obstacle_pressure=0.0,
        )
        grouped_score = adapter._metrics_score(
            DifficultyMetrics(
                **base,
                tray_switching_pressure=grouped[0],
                consecutive_tray_relief=grouped[1],
                parallel_same_color_relief=grouped[2],
            )
        )
        mixed_score = adapter._metrics_score(
            DifficultyMetrics(
                **base,
                tray_switching_pressure=mixed[0],
                consecutive_tray_relief=mixed[1],
                parallel_same_color_relief=mixed[2],
            )
        )

        self.assertGreater(mixed[0], grouped[0])
        self.assertLess(mixed[1], grouped[1])
        self.assertGreater(mixed_score, grouped_score)

    def test_ice_block_on_shooter_does_not_remain_a_permanent_wall(self) -> None:
        level = make_layout_level([["Blue"]])
        level["grid"] = {
            "rows": 1,
            "columns": 1,
            "cells": [
                {
                    "row": 0,
                    "column": 0,
                    "entity": {
                        "type": "Shooter",
                        "blocksPath": True,
                        "shooter": {
                            "shooterId": "s_0",
                            "colorId": "Blue",
                            "capacity": 3,
                            "modifiers": [],
                        },
                    },
                }
            ],
            "obstacles": [
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
            ],
            "shooterGroups": [],
        }
        simulator = BallDropSimulator(level)
        state = simulator.initial_state()

        self.assertTrue(state.obstacle_blocked[0][0])
        self.assertEqual(state.ice_blocks[0].hp, 1)
        simulator.damage_ice(state, 1)
        self.assertFalse(state.obstacle_blocked[0][0])
        self.assertTrue(simulator.click(state, 0, 0))
        self.assertTrue(simulator.is_passable(state, 0, 0))

    def test_ice_shooter_loses_hp_for_each_ball_released_by_a_shooter(self) -> None:
        level = make_layout_level([["Blue"]])
        level["grid"] = {
            "rows": 1,
            "columns": 2,
            "cells": [
                {
                    "row": 0,
                    "column": 0,
                    "entity": {
                        "type": "Shooter",
                        "blocksPath": True,
                        "shooter": {
                            "shooterId": "s_blue",
                            "colorId": "Blue",
                            "capacity": 9,
                            "modifiers": [],
                        },
                    },
                },
                {
                    "row": 0,
                    "column": 1,
                    "entity": {
                        "type": "Shooter",
                        "blocksPath": True,
                        "shooter": {
                            "shooterId": "s_red",
                            "colorId": "Red",
                            "capacity": 9,
                            "modifiers": [{"type": "Ice", "hp": 9}],
                        },
                    },
                },
            ],
            "obstacles": [],
            "shooterGroups": [],
        }
        simulator = BallDropSimulator(level)
        state = simulator.initial_state()
        frozen = state.cells[1].shooter

        self.assertTrue(simulator.click(state, 0, 0))
        self.assertEqual(frozen.ice_hp, 0)

    def test_solver_unlocks_ice_shooter_when_blocking_shooter_is_cleared(self) -> None:
        level = make_layout_level([["Blue", "Green", "White"]])
        for tray in level["gateSystem"]["gates"][0]["trayQueue"]:
            tray["layers"][0]["requiredCount"] = 9
        level["grid"] = {
            "rows": 1,
            "columns": 3,
            "cells": [
                {
                    "row": 0,
                    "column": 0,
                    "entity": {
                        "type": "Shooter",
                        "blocksPath": True,
                        "shooter": {
                            "shooterId": "s_blue",
                            "colorId": "Blue",
                            "capacity": 9,
                            "modifiers": [],
                        },
                    },
                },
                {
                    "row": 0,
                    "column": 1,
                    "entity": {
                        "type": "Shooter",
                        "blocksPath": True,
                        "shooter": {
                            "shooterId": "s_green",
                            "colorId": "Green",
                            "capacity": 9,
                            "modifiers": [{"type": "Ice", "hp": 9}],
                        },
                    },
                },
                {
                    "row": 0,
                    "column": 2,
                    "entity": {
                        "type": "Shooter",
                        "blocksPath": True,
                        "shooter": {
                            "shooterId": "s_white",
                            "colorId": "White",
                            "capacity": 9,
                            "modifiers": [],
                        },
                    },
                },
            ],
            "obstacles": [],
            "shooterGroups": [],
        }
        simulator = BallDropSimulator(level)
        state = simulator.initial_state()

        self.assertTrue(simulator.click(state, 0, 0))
        frozen = state.cells[1].shooter
        self.assertIsNotNone(frozen)
        self.assertEqual(frozen.ice_hp, 0)
        self.assertFalse(state.lost)
        self.assertIn(
            "Green",
            [shooter.color for _row, _col, shooter in simulator.active_shooters(state)],
        )

        result = DeepSearchSolver(simulator, time_budget=2.0).solve_file("<ice-wait>")
        self.assertEqual(result.status, "PASS")

    def test_larger_ice_count_adds_more_obstacle_pressure(self) -> None:
        adapter = SolverScoreAdapter()
        low_level = make_layout_level([["Blue", "Blue", "Blue"]])
        high_level = make_layout_level([["Blue", "Blue", "Blue"]])
        for level, hp in ((low_level, 3), (high_level, 24)):
            level["grid"] = {
                "rows": 1,
                "columns": 2,
                "cells": [
                    {
                        "row": 0,
                        "column": 0,
                        "entity": {
                            "type": "Shooter",
                            "shooter": {
                                "shooterId": "active",
                                "colorId": "Blue",
                                "capacity": 3,
                                "modifiers": [],
                            },
                        },
                    },
                    {
                        "row": 0,
                        "column": 1,
                        "entity": {
                            "type": "Shooter",
                            "shooter": {
                                "shooterId": "frozen",
                                "colorId": "Red",
                                "capacity": 3,
                                "modifiers": [{"type": "Ice", "hp": hp}],
                            },
                        },
                    },
                ],
                "obstacles": [],
                "shooterGroups": [],
            }

        low_state = BallDropSimulator(low_level).initial_state()
        high_state = BallDropSimulator(high_level).initial_state()
        self.assertGreater(
            adapter._obstacle_pressure(high_state, 0, 0),
            adapter._obstacle_pressure(low_state, 0, 0),
        )


if __name__ == "__main__":
    unittest.main()

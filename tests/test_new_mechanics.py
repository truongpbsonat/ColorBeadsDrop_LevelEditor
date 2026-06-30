from __future__ import annotations

import copy
import unittest

from ball_drop_editor.level_data import (
    detect_mechanics,
    make_shooter_modifiers,
    make_tray_modifiers,
    normalize_runtime_level,
)
from ball_drop_editor.validator import LevelValidator


def _level_with_new_mechanics(connection_id_b: str = "link") -> dict:
    """A small but balanced level exercising GlassBarrier, Hammer, Arrow and
    a RemoteConnected tray pair. `connection_id_b` lets a test break the pair."""
    return {
        "level": 1,
        "time": 60,
        "levelName": "t",
        "mechanics": [],
        "grid": {
            "rows": 2,
            "columns": 3,
            "cells": [
                {
                    "row": 0,
                    "column": 0,
                    "entity": {
                        "type": "Shooter",
                        "entityId": "e1",
                        "blocksPath": True,
                        "shooter": {
                            "shooterId": "s1",
                            "colorId": "Blue",
                            "capacity": 9,
                            "modifiers": make_shooter_modifiers(
                                hammer=True,
                                hammer_color="Blue",
                                arrow=True,
                                arrow_direction="Right",
                            ),
                        },
                    },
                },
                # Walls sit on the two end cells of the Blue GlassBarrier below.
                {
                    "row": 1,
                    "column": 0,
                    "entity": {"type": "Wall", "entityId": "wL", "blocksPath": True},
                },
                {
                    "row": 1,
                    "column": 2,
                    "entity": {"type": "Wall", "entityId": "wR", "blocksPath": True},
                },
            ],
            "obstacles": [
                {
                    "obstacleId": "g1",
                    "type": "GlassBarrier",
                    "direction": "Right",
                    "length": 3,
                    "color": "Blue",
                    "shape": {
                        "type": "LineHorizontal",
                        "origin": {"row": 1, "column": 0},
                        "width": 3,
                        "height": 1,
                        "cells": [],
                    },
                }
            ],
            "shooterGroups": [],
        },
        "gateSystem": {
            "gateCount": 2,
            "maxVisibleTrayPerGate": 4,
            "gates": [
                {
                    "gateIndex": 0,
                    "trayQueue": [
                        {
                            "trayId": "t1",
                            "layers": [{"colorId": "Blue", "requiredCount": 3}],
                            "modifiers": make_tray_modifiers(remote=True, connection_id="link"),
                        }
                    ],
                },
                {
                    "gateIndex": 1,
                    "trayQueue": [
                        {
                            "trayId": "t2",
                            "layers": [{"colorId": "Blue", "requiredCount": 3}],
                            "modifiers": make_tray_modifiers(remote=True, connection_id=connection_id_b),
                        }
                    ],
                },
            ],
        },
    }


class NewMechanicNormalizeTests(unittest.TestCase):
    def test_normalize_round_trips_new_fields(self) -> None:
        norm = normalize_runtime_level(copy.deepcopy(_level_with_new_mechanics()))

        obstacle = norm["grid"]["obstacles"][0]
        self.assertEqual(obstacle["type"], "GlassBarrier")
        self.assertEqual(obstacle["direction"], "Right")
        self.assertEqual(obstacle["length"], 3)
        self.assertEqual(obstacle["color"], "Blue")

        modifiers = norm["grid"]["cells"][0]["entity"]["shooter"]["modifiers"]
        self.assertIn({"type": "Hammer", "color": "Blue"}, modifiers)
        self.assertIn({"type": "Arrow", "direction": "Right"}, modifiers)

        tray_modifiers = norm["gateSystem"]["gates"][0]["trayQueue"][0]["modifiers"]
        self.assertEqual(tray_modifiers, [{"type": "RemoteConnected", "connectionId": "link"}])

    def test_detect_mechanics_folds_hammer_into_glass_barrier(self) -> None:
        norm = normalize_runtime_level(copy.deepcopy(_level_with_new_mechanics()))
        mechanics = detect_mechanics(norm)
        self.assertIn("GlassBarrier", mechanics)
        self.assertIn("ArrowShooter", mechanics)
        self.assertIn("ConnectedTray", mechanics)
        self.assertNotIn("HammerShooter", mechanics)


class NewMechanicValidationTests(unittest.TestCase):
    def test_balanced_pair_has_no_new_mechanic_errors(self) -> None:
        norm = normalize_runtime_level(copy.deepcopy(_level_with_new_mechanics()))
        errors, _warnings = LevelValidator().validate(norm)
        self.assertEqual(errors, [])

    def test_unpaired_connection_id_is_error(self) -> None:
        norm = normalize_runtime_level(copy.deepcopy(_level_with_new_mechanics(connection_id_b="other")))
        errors, _warnings = LevelValidator().validate(norm)
        self.assertTrue(any("link" in error and "2 tray" in error for error in errors))

    def test_empty_connection_id_is_error(self) -> None:
        level = _level_with_new_mechanics()
        level["gateSystem"]["gates"][0]["trayQueue"][0]["modifiers"] = [
            {"type": "RemoteConnected", "connectionId": ""}
        ]
        norm = normalize_runtime_level(copy.deepcopy(level))
        errors, _warnings = LevelValidator().validate(norm)
        self.assertTrue(any("connectionId" in error for error in errors))

    def test_invalid_hammer_color_is_error(self) -> None:
        level = _level_with_new_mechanics()
        level["grid"]["cells"][0]["entity"]["shooter"]["modifiers"] = [
            {"type": "Hammer", "color": "None"}
        ]
        norm = normalize_runtime_level(copy.deepcopy(level))
        errors, _warnings = LevelValidator().validate(norm)
        self.assertTrue(any("Hammer" in error for error in errors))

    def test_glass_barrier_end_without_wall_is_error(self) -> None:
        level = _level_with_new_mechanics()
        # Remove the right-end wall, leaving that end of the barrier unanchored.
        level["grid"]["cells"] = [
            cell for cell in level["grid"]["cells"]
            if not (cell["row"] == 1 and cell["column"] == 2)
        ]
        norm = normalize_runtime_level(copy.deepcopy(level))
        errors, _warnings = LevelValidator().validate(norm)
        self.assertTrue(any("GlassBarrier" in error and "Wall" in error for error in errors))

    def test_arrow_pointing_out_of_grid_is_error(self) -> None:
        level = _level_with_new_mechanics()
        # Shooter sits at row 0, so an upward arrow leaves the grid.
        level["grid"]["cells"][0]["entity"]["shooter"]["modifiers"] = make_shooter_modifiers(
            arrow=True, arrow_direction="Up"
        )
        norm = normalize_runtime_level(copy.deepcopy(level))
        errors, _warnings = LevelValidator().validate(norm)
        self.assertTrue(any("Arrow" in error and "ngoài grid" in error for error in errors))

    def test_arrow_pointing_into_wall_is_error(self) -> None:
        level = _level_with_new_mechanics()
        level["grid"]["cells"][0]["entity"]["shooter"]["modifiers"] = make_shooter_modifiers(
            arrow=True, arrow_direction="Right"
        )
        # Put a Wall in the arrow's target cell (0,1).
        level["grid"]["cells"].append({
            "row": 0,
            "column": 1,
            "entity": {"type": "Wall", "entityId": "w1", "blocksPath": True},
        })
        norm = normalize_runtime_level(copy.deepcopy(level))
        errors, _warnings = LevelValidator().validate(norm)
        self.assertTrue(any("Arrow" in error and "Wall" in error for error in errors))

    def test_connected_tray_same_gate_is_error(self) -> None:
        level = _level_with_new_mechanics()
        # Move both ends of the connection into gate 0.
        gate0 = level["gateSystem"]["gates"][0]
        gate0["trayQueue"].append({
            "trayId": "t3",
            "layers": [{"colorId": "Blue", "requiredCount": 3}],
            "modifiers": make_tray_modifiers(remote=True, connection_id="link"),
        })
        level["gateSystem"]["gates"][1]["trayQueue"][0]["modifiers"] = make_tray_modifiers()
        norm = normalize_runtime_level(copy.deepcopy(level))
        errors, _warnings = LevelValidator().validate(norm)
        self.assertTrue(any("cùng" in error and "gate" in error for error in errors))

    def test_connected_tray_non_adjacent_gates_is_error(self) -> None:
        level = _level_with_new_mechanics()
        level["gateSystem"]["gateCount"] = 3
        level["gateSystem"]["gates"].append({
            "gateIndex": 2,
            "trayQueue": [{
                "trayId": "t3",
                "layers": [{"colorId": "Blue", "requiredCount": 3}],
                "modifiers": make_tray_modifiers(remote=True, connection_id="link"),
            }],
        })
        # Re-point the gate 0 end to the gate 2 tray (gate 0 <-> gate 2 are not adjacent).
        level["gateSystem"]["gates"][1]["trayQueue"][0]["modifiers"] = make_tray_modifiers()
        norm = normalize_runtime_level(copy.deepcopy(level))
        errors, _warnings = LevelValidator().validate(norm)
        self.assertTrue(any("cạnh nhau" in error for error in errors))

    def test_connected_trays_crossing_is_error(self) -> None:
        level = _level_with_new_mechanics()
        # gate 0: tray at pos0 -> link, tray at pos1 -> link2
        level["gateSystem"]["gates"][0]["trayQueue"].append({
            "trayId": "t1b",
            "layers": [{"colorId": "Blue", "requiredCount": 3}],
            "modifiers": make_tray_modifiers(remote=True, connection_id="link2"),
        })
        # gate 1: tray at pos0 -> link2, tray at pos1 -> link  => the two pairs cross.
        level["gateSystem"]["gates"][1]["trayQueue"][0]["modifiers"] = make_tray_modifiers(
            remote=True, connection_id="link2"
        )
        level["gateSystem"]["gates"][1]["trayQueue"].append({
            "trayId": "t2b",
            "layers": [{"colorId": "Blue", "requiredCount": 3}],
            "modifiers": make_tray_modifiers(remote=True, connection_id="link"),
        })
        norm = normalize_runtime_level(copy.deepcopy(level))
        errors, _warnings = LevelValidator().validate(norm)
        self.assertTrue(any("bắt chéo" in error for error in errors))

    def test_glass_barrier_without_hammer_is_error(self) -> None:
        level = _level_with_new_mechanics()
        # Drop the Hammer modifier, keep the Blue GlassBarrier unpaired.
        level["grid"]["cells"][0]["entity"]["shooter"]["modifiers"] = make_shooter_modifiers(
            arrow=True, arrow_direction="Right"
        )
        norm = normalize_runtime_level(copy.deepcopy(level))
        errors, _warnings = LevelValidator().validate(norm)
        self.assertTrue(any("GlassBarrier" in error and "Hammer" in error for error in errors))

    def test_hammer_without_glass_barrier_is_error(self) -> None:
        level = _level_with_new_mechanics()
        level["grid"]["obstacles"] = []
        norm = normalize_runtime_level(copy.deepcopy(level))
        errors, _warnings = LevelValidator().validate(norm)
        self.assertTrue(any("Hammer" in error and "GlassBarrier" in error for error in errors))

    def test_duplicate_color_glass_hammer_pair_is_error(self) -> None:
        level = _level_with_new_mechanics()
        # Second Blue GlassBarrier + second Blue Hammer => two Blue pairs.
        level["grid"]["obstacles"].append({
            "obstacleId": "g2",
            "type": "GlassBarrier",
            "direction": "Right",
            "length": 1,
            "color": "Blue",
            "shape": {
                "type": "LineHorizontal",
                "origin": {"row": 1, "column": 2},
                "width": 1,
                "height": 1,
                "cells": [],
            },
        })
        level["grid"]["cells"][0]["entity"]["shooter"]["modifiers"] = [
            {"type": "Hammer", "color": "Blue"},
            {"type": "Hammer", "color": "Blue"},
        ]
        norm = normalize_runtime_level(copy.deepcopy(level))
        errors, _warnings = LevelValidator().validate(norm)
        self.assertTrue(any("nhiều cặp" in error and "Blue" in error for error in errors))


if __name__ == "__main__":
    unittest.main()

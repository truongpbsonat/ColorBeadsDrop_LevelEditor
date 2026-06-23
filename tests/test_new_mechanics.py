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
                                arrow_direction="Up",
                            ),
                        },
                    },
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
        self.assertIn({"type": "Arrow", "direction": "Up"}, modifiers)

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


if __name__ == "__main__":
    unittest.main()

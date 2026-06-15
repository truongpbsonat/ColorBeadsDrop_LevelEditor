from __future__ import annotations

import unittest

from ball_drop_editor.validator import LevelValidator


def make_level_with_shooter(shooter):
    required_count = shooter.get("capacity", 0)
    if any(
        modifier.get("type") == "Special"
        for modifier in shooter.get("modifiers", []) or []
    ):
        required_count *= 2
    return {
        "level": 1,
        "mechanics": ["SpecialShooter"] if any(
            modifier.get("type") == "Special"
            for modifier in shooter.get("modifiers", []) or []
        ) else [],
        "grid": {
            "rows": 1,
            "columns": 1,
            "cells": [
                {
                    "row": 0,
                    "column": 0,
                    "entity": {
                        "type": "Shooter",
                        "blocksPath": True,
                        "shooter": shooter,
                    },
                }
            ],
            "obstacles": [],
            "shooterGroups": [],
        },
        "gateSystem": {
            "gateCount": 1,
            "maxVisibleTrayPerGate": 4,
            "gates": [
                {
                    "gateIndex": 0,
                    "trayQueue": [
                        {
                            "trayId": "t_0",
                            "layers": [{"colorId": "Blue", "requiredCount": required_count}],
                            "modifiers": [],
                        }
                    ],
                }
            ],
        },
    }


class ValidatorTests(unittest.TestCase):
    def test_warns_when_shooter_capacity_is_not_fixed_value(self) -> None:
        level = make_level_with_shooter(
            {
                "shooterId": "s_bad",
                "colorId": "Blue",
                "capacity": 18,
                "modifiers": [],
            }
        )

        _errors, warnings = LevelValidator().validate(level)

        self.assertTrue(any("s_bad" in warning and "capacity=18" in warning for warning in warnings))

    def test_special_shooter_capacity_warning_mentions_special_modifier(self) -> None:
        level = make_level_with_shooter(
            {
                "shooterId": "s_special",
                "colorId": "Blue",
                "capacity": 18,
                "modifiers": [{"type": "Special"}],
            }
        )

        _errors, warnings = LevelValidator().validate(level)

        self.assertTrue(
            any(
                "s_special" in warning
                and "capacity=18" in warning
                and "Special" in warning
                for warning in warnings
            )
        )


if __name__ == "__main__":
    unittest.main()

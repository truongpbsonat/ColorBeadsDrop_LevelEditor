from __future__ import annotations

import json
import os
import tempfile
import unittest

from ball_drop_editor.level_data import make_shooter_modifiers, make_tray_modifiers
from ball_drop_editor.level_tester_core import BallDropSimulator, DeepSearchSolver


def _shooter_cell(row, col, color, capacity=3, modifiers=None):
    return {
        "row": row,
        "column": col,
        "entity": {
            "type": "Shooter",
            "entityId": f"e_{row}_{col}",
            "blocksPath": True,
            "shooter": {
                "shooterId": f"s_{row}_{col}",
                "colorId": color,
                "capacity": capacity,
                "modifiers": modifiers or [],
            },
        },
    }


def _wall_cell(row, col):
    return {"row": row, "column": col, "entity": {"type": "Wall", "entityId": f"w_{row}_{col}", "blocksPath": True}}


def _empty_cell(row, col):
    return {"row": row, "column": col, "entity": None}


def _tray(tray_id, color, count=3, modifiers=None):
    return {"trayId": tray_id, "layers": [{"colorId": color, "requiredCount": count}], "modifiers": modifiers or []}


def _build(rows, cols, cells, gates=None, obstacles=None):
    gates = gates if gates is not None else [{"gateIndex": 0, "trayQueue": []}]
    level = {
        "gameMode": "Classic",
        "difficulty": "Normal",
        "level": 1,
        "time": 60,
        "levelName": "t",
        "mechanics": [],
        "grid": {
            "rows": rows,
            "columns": cols,
            "cells": cells,
            "obstacles": obstacles or [],
            "shooterGroups": [],
        },
        "gateSystem": {"gateCount": len(gates), "maxVisibleTrayPerGate": 4, "gates": gates},
    }
    return BallDropSimulator(level)


def _active_positions(sim, state):
    return {(row, col) for row, col, _ in sim.active_shooters(state)}


class BomLoadingTest(unittest.TestCase):
    def test_from_file_reads_utf8_bom(self) -> None:
        level = {
            "gameMode": "Classic", "difficulty": "Normal", "level": 1, "time": 60, "levelName": "t",
            "grid": {"rows": 1, "columns": 1, "cells": [_shooter_cell(0, 0, "Blue")], "obstacles": [], "shooterGroups": []},
            "gateSystem": {"gateCount": 1, "maxVisibleTrayPerGate": 4, "gates": [{"gateIndex": 0, "trayQueue": [_tray("t1", "Blue")]}]},
        }
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            with open(path, "w", encoding="utf-8-sig") as fh:  # writes a BOM
                json.dump(level, fh)
            sim = BallDropSimulator.from_file(path)
            self.assertEqual(sim.initial_state().rows, 1)
        finally:
            os.remove(path)


class ArrowShooterTest(unittest.TestCase):
    """(1,0) can reach the top only via the right cell; the up cell is a wall."""

    def _sim(self, modifiers):
        cells = [_wall_cell(0, 0), _empty_cell(0, 1), _shooter_cell(1, 0, "Blue", modifiers=modifiers), _empty_cell(1, 1)]
        return _build(2, 2, cells)

    def test_normal_shooter_routes_sideways_up(self) -> None:
        sim = self._sim([])
        self.assertIn((1, 0), _active_positions(sim, sim.initial_state()))

    def test_arrow_up_blocked_by_wall(self) -> None:
        sim = self._sim(make_shooter_modifiers(arrow=True, arrow_direction="Up"))
        self.assertNotIn((1, 0), _active_positions(sim, sim.initial_state()))

    def test_arrow_right_reaches_top(self) -> None:
        sim = self._sim(make_shooter_modifiers(arrow=True, arrow_direction="Right"))
        self.assertIn((1, 0), _active_positions(sim, sim.initial_state()))

    def test_arrow_left_off_grid_is_inactive(self) -> None:
        sim = self._sim(make_shooter_modifiers(arrow=True, arrow_direction="Left"))
        self.assertNotIn((1, 0), _active_positions(sim, sim.initial_state()))


class ShutterShooterTest(unittest.TestCase):
    def _sim(self):
        cells = [
            _shooter_cell(0, 0, "Blue"),
            _shooter_cell(0, 1, "Red", modifiers=make_shooter_modifiers(shutter=True, shutter_is_open=False)),
        ]
        return _build(1, 2, cells)

    def test_closed_shutter_is_inactive(self) -> None:
        sim = self._sim()
        active = _active_positions(sim, sim.initial_state())
        self.assertIn((0, 0), active)
        self.assertNotIn((0, 1), active)

    def test_firing_another_shooter_opens_shutter(self) -> None:
        sim = self._sim()
        state = sim.initial_state()
        self.assertTrue(sim.click(state, 0, 0))
        # The closed shutter at (0,1) should now be open and clickable.
        self.assertIn((0, 1), _active_positions(sim, state))


class GlassBarrierTest(unittest.TestCase):
    def _sim(self):
        cells = [
            _shooter_cell(0, 0, "Green", modifiers=make_shooter_modifiers(hammer=True, hammer_color="Blue")),
            _empty_cell(1, 0),
            _shooter_cell(2, 0, "Red"),
        ]
        obstacles = [{
            "obstacleId": "g1", "type": "GlassBarrier", "direction": "Down", "length": 1, "color": "Blue",
            "shape": {"type": "Rect", "origin": {"row": 1, "column": 0}, "width": 1, "height": 1, "cells": []},
        }]
        return _build(3, 1, cells, obstacles=obstacles)

    def test_barrier_blocks_until_hammer_fires(self) -> None:
        sim = self._sim()
        state = sim.initial_state()
        self.assertTrue(state.obstacle_blocked[1][0])
        active = _active_positions(sim, state)
        self.assertIn((0, 0), active)  # hammer at top is active
        self.assertNotIn((2, 0), active)  # red is trapped behind barrier
        self.assertTrue(sim.click(state, 0, 0))  # fire the Blue hammer
        self.assertFalse(state.obstacle_blocked[1][0])
        self.assertIn((2, 0), _active_positions(sim, state))


class ConnectedTrayTest(unittest.TestCase):
    def _sim(self):
        gates = [
            {"gateIndex": 0, "trayQueue": [_tray("a", "Blue", modifiers=[{"type": "RemoteConnected", "connectionId": "1"}])]},
            {"gateIndex": 1, "trayQueue": [
                _tray("b", "Red"),
                _tray("c", "Blue", modifiers=[{"type": "RemoteConnected", "connectionId": "1"}]),
            ]},
        ]
        return _build(1, 1, [_shooter_cell(0, 0, "Blue")], gates=gates)

    def test_connected_tray_locked_until_partner_at_front(self) -> None:
        sim = self._sim()
        state = sim.initial_state()
        # Partner (tray c) is behind tray b, so gate 0's connected tray is blocked.
        self.assertTrue(sim._front_tray_blocked(state, 0))
        self.assertFalse(sim._gate_needs_color(state, 0, "Blue"))
        # Pop gate 1's front (tray b) so the partner reaches the front.
        state.gates[1].pop(0)
        self.assertFalse(sim._front_tray_blocked(state, 0))
        self.assertTrue(sim._gate_needs_color(state, 0, "Blue"))


class KeyLockTest(unittest.TestCase):
    def test_locked_tray_blocks_until_key_fires(self) -> None:
        gates = [{"gateIndex": 0, "trayQueue": [_tray("t1", "Blue", count=3, modifiers=[{"type": "Lock"}])]}]
        sim = _build(1, 1, [_shooter_cell(0, 0, "Blue", modifiers=make_shooter_modifiers(key=True))], gates=gates)
        state = sim.initial_state()
        self.assertTrue(state.gates[0][0].locked)
        self.assertFalse(sim._gate_needs_color(state, 0, "Blue"))
        self.assertTrue(sim.click(state, 0, 0))  # fire the Key shooter
        self.assertFalse(state.gates[0][0].locked)

    def test_key_unlocks_front_row_rightmost_gate_first(self) -> None:
        gates = [
            {"gateIndex": 0, "trayQueue": [_tray("g0", "Blue", modifiers=[{"type": "Lock"}])]},
            {"gateIndex": 1, "trayQueue": [_tray("g1", "Red", modifiers=[{"type": "Lock"}])]},
        ]
        sim = _build(1, 1, [_shooter_cell(0, 0, "Blue")], gates=gates)
        state = sim.initial_state()
        sim._unlock_next_locked_tray(state)
        # Right-most gate (index 1) in the front row unlocks first.
        self.assertTrue(state.gates[0][0].locked)
        self.assertFalse(state.gates[1][0].locked)

    def test_key_unlocks_front_row_before_deeper_row(self) -> None:
        gates = [
            {"gateIndex": 0, "trayQueue": [
                _tray("front", "Blue", modifiers=[{"type": "Lock"}]),
                _tray("deep", "Red", modifiers=[{"type": "Lock"}]),
            ]},
        ]
        sim = _build(1, 1, [_shooter_cell(0, 0, "Blue")], gates=gates)
        state = sim.initial_state()
        sim._unlock_next_locked_tray(state)
        self.assertFalse(state.gates[0][0].locked)  # front row unlocked
        self.assertTrue(state.gates[0][1].locked)   # deeper row still locked


def _solve(sim, budget=8.0):
    return DeepSearchSolver(sim, time_budget=budget).solve_file("<test>")


class EndToEndSolveTest(unittest.TestCase):
    """Full pipeline (validation + simulation + search) for each new mechanic."""

    def test_key_lock_count_mismatch_is_error(self) -> None:
        sim = _build(1, 1, [_shooter_cell(0, 0, "Blue", 9, make_shooter_modifiers(key=True))],
                     gates=[{"gateIndex": 0, "trayQueue": [_tray("t1", "Blue", 9)]}])
        result = _solve(sim)
        self.assertEqual(result.status, "ERROR")
        self.assertIn("Key", result.message)
        self.assertIn("Lock", result.message)

    def test_key_lock_level_solves(self) -> None:
        sim = _build(1, 1, [_shooter_cell(0, 0, "Blue", 9, make_shooter_modifiers(key=True))],
                     gates=[{"gateIndex": 0, "trayQueue": [_tray("t1", "Blue", 9, modifiers=[{"type": "Lock"}])]}])
        self.assertEqual(_solve(sim).status, "PASS")

    def test_glass_barrier_level_solves(self) -> None:
        cells = [
            _shooter_cell(0, 0, "Green", 3, make_shooter_modifiers(hammer=True, hammer_color="Blue")),
            _empty_cell(1, 0),
            _shooter_cell(2, 0, "Blue", 3),
        ]
        obstacles = [{
            "obstacleId": "g1", "type": "GlassBarrier", "direction": "Down", "length": 1, "color": "Blue",
            "shape": {"type": "Rect", "origin": {"row": 1, "column": 0}, "width": 1, "height": 1, "cells": []},
        }]
        gates = [{"gateIndex": 0, "trayQueue": [_tray("t1", "Green"), _tray("t2", "Blue")]}]
        self.assertEqual(_solve(_build(3, 1, cells, gates=gates, obstacles=obstacles)).status, "PASS")

    def test_connected_tray_level_solves(self) -> None:
        cells = [_shooter_cell(0, 0, "Blue", 3), _shooter_cell(0, 1, "Blue", 3)]
        gates = [
            {"gateIndex": 0, "trayQueue": [_tray("a", "Blue", modifiers=make_tray_modifiers(remote=True, connection_id="1"))]},
            {"gateIndex": 1, "trayQueue": [_tray("b", "Blue", modifiers=make_tray_modifiers(remote=True, connection_id="1"))]},
        ]
        self.assertEqual(_solve(_build(1, 2, cells, gates=gates)).status, "PASS")

    def test_connected_tray_staggered_solves(self) -> None:
        # The gate-1 partner sits behind a Red tray, so the pair only meets at the
        # front after Red completes; the permanent unlock must survive that.
        cells = [_shooter_cell(0, 0, "Red", 3), _shooter_cell(0, 1, "Blue", 3), _shooter_cell(0, 2, "Blue", 3)]
        gates = [
            {"gateIndex": 0, "trayQueue": [_tray("a", "Blue", modifiers=make_tray_modifiers(remote=True, connection_id="1"))]},
            {"gateIndex": 1, "trayQueue": [
                _tray("b", "Red"),
                _tray("c", "Blue", modifiers=make_tray_modifiers(remote=True, connection_id="1")),
            ]},
        ]
        self.assertEqual(_solve(_build(1, 3, cells, gates=gates)).status, "PASS")

    def test_shutter_level_solves(self) -> None:
        cells = [
            _shooter_cell(0, 0, "Blue", 3),
            _shooter_cell(0, 1, "Red", 3, make_shooter_modifiers(shutter=True, shutter_is_open=False)),
        ]
        gates = [{"gateIndex": 0, "trayQueue": [_tray("t1", "Blue"), _tray("t2", "Red")]}]
        self.assertEqual(_solve(_build(1, 2, cells, gates=gates)).status, "PASS")


if __name__ == "__main__":
    unittest.main()

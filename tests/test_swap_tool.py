from __future__ import annotations

import json
import os
import tempfile
import unittest

from ball_drop_editor.swap_tool import apply_level_order


def _write(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file)


def _read(path: str) -> dict:
    with open(path, "r", encoding="utf-8-sig") as file:
        return json.load(file)


class SwapToolTests(unittest.TestCase):
    def test_pairwise_swap_exchanges_content_keeps_slot_level(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path_a = os.path.join(folder, "1.json")
            path_b = os.path.join(folder, "5.json")
            _write(path_a, {"level": 1, "levelName": "Alpha", "difficulty": "Normal", "grid": {"a": 1}})
            _write(path_b, {"level": 5, "levelName": "Bravo", "difficulty": "Hard", "grid": {"b": 2}})

            # Slots stay [1.json, 5.json]; contents are swapped.
            changed = apply_level_order([path_a, path_b], [path_b, path_a])

            self.assertCountEqual(changed, [path_a, path_b])

            # 1.json keeps its own level field but now holds Bravo's content.
            new_a = _read(path_a)
            self.assertEqual(new_a["level"], 1)
            self.assertEqual(new_a["levelName"], "Bravo")
            self.assertEqual(new_a["difficulty"], "Hard")
            self.assertEqual(new_a["grid"], {"b": 2})

            new_b = _read(path_b)
            self.assertEqual(new_b["level"], 5)
            self.assertEqual(new_b["levelName"], "Alpha")
            self.assertEqual(new_b["difficulty"], "Normal")
            self.assertEqual(new_b["grid"], {"a": 1})

    def test_multi_reorder_1234_to_1423(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            paths = [os.path.join(folder, f"{n}.json") for n in (1, 2, 3, 4)]
            for index, path in enumerate(paths, start=1):
                _write(path, {"level": index, "levelName": f"L{index}"})

            slots = list(paths)  # 1,2,3,4
            # New order of contents: 1,4,2,3 -> content from files [1,4,2,3] land in slots [1,2,3,4]
            ordered = [paths[0], paths[3], paths[1], paths[2]]

            changed = apply_level_order(slots, ordered)

            # Slot 1 unchanged (content 1 stays), slots 2/3/4 changed.
            self.assertCountEqual(changed, [paths[1], paths[2], paths[3]])

            # Each slot keeps its own level number; content follows the new order.
            self.assertEqual(_read(paths[0]), {"level": 1, "levelName": "L1"})
            self.assertEqual(_read(paths[1]), {"level": 2, "levelName": "L4"})
            self.assertEqual(_read(paths[2]), {"level": 3, "levelName": "L2"})
            self.assertEqual(_read(paths[3]), {"level": 4, "levelName": "L3"})

    def test_identity_order_changes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            paths = [os.path.join(folder, f"{n}.json") for n in (1, 2, 3)]
            for index, path in enumerate(paths, start=1):
                _write(path, {"level": index})

            changed = apply_level_order(paths, list(paths))

            self.assertEqual(changed, [])

    def test_rejects_non_permutation(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path_a = os.path.join(folder, "1.json")
            path_b = os.path.join(folder, "2.json")
            _write(path_a, {"level": 1})
            _write(path_b, {"level": 2})
            with self.assertRaises(ValueError):
                apply_level_order([path_a, path_b], [path_a, path_a])

    def test_rejects_non_object_root_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path_a = os.path.join(folder, "1.json")
            path_b = os.path.join(folder, "2.json")
            _write(path_a, {"level": 1, "levelName": "keep"})
            with open(path_b, "w", encoding="utf-8") as file:
                file.write("[1, 2, 3]")
            with self.assertRaises(ValueError):
                apply_level_order([path_a, path_b], [path_b, path_a])
            # Valid file must be untouched when another file is invalid.
            self.assertEqual(_read(path_a), {"level": 1, "levelName": "keep"})


if __name__ == "__main__":
    unittest.main()

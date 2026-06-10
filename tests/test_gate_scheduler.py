from __future__ import annotations

import random
import unittest
from collections import Counter

from ball_drop_editor.level_generator_gates import (
    build_tray_chunks,
    schedule_tray_chunks,
)


def layout_signature(gates):
    return [
        [
            (
                tray["layers"][0]["colorId"],
                tray["layers"][0]["requiredCount"],
            )
            for tray in gate["trayQueue"]
        ]
        for gate in gates
    ]


class GateSchedulerTests(unittest.TestCase):
    def test_balances_and_fully_mixes_balanced_palette(self) -> None:
        chunks = build_tray_chunks(["A", "B", "C", "D"] * 8, 3, 3)
        gates, metrics = schedule_tray_chunks(chunks, 4, random.Random(7))

        actual = Counter(
            (color, required)
            for queue in layout_signature(gates)
            for color, required in queue
        )
        self.assertEqual(actual, Counter(chunks))
        self.assertEqual(metrics.max_same_color_run, 1)
        self.assertEqual(metrics.adjacent_same_pairs, 0)
        self.assertEqual(metrics.duplicate_depth_pairs, 0)
        self.assertEqual(metrics.queue_imbalance, 0)
        self.assertEqual(metrics.avoidable_repeats, 0)

    def test_falls_back_cleanly_for_single_color(self) -> None:
        chunks = build_tray_chunks(["Blue"] * 8, 9, 3)
        gates, metrics = schedule_tray_chunks(chunks, 4, random.Random(3))

        self.assertEqual(sum(len(gate["trayQueue"]) for gate in gates), 24)
        self.assertGreater(metrics.max_same_color_run, 1)
        self.assertGreater(metrics.duplicate_depth_pairs, 0)
        self.assertEqual(metrics.queue_imbalance, 0)
        self.assertEqual(metrics.avoidable_repeats, 0)

    def test_same_seed_recreates_layout(self) -> None:
        chunks = build_tray_chunks(["Red", "Blue", "Green", "Yellow"] * 6, 9, 3)
        left, _ = schedule_tray_chunks(chunks, 4, random.Random(99))
        right, _ = schedule_tray_chunks(chunks, 4, random.Random(99))
        self.assertEqual(layout_signature(left), layout_signature(right))


if __name__ == "__main__":
    unittest.main()

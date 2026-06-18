from __future__ import annotations

import json
import os
import tempfile
import unittest

from ball_drop_editor.constants import canonical_level_difficulty, normalize_level_difficulty
from ball_drop_editor.difficulty_tool import (
    difficulty_label,
    list_level_json_files,
    load_level_difficulty_summary,
    set_level_difficulty,
)


class DifficultyToolTests(unittest.TestCase):
    def test_canonical_difficulty_accepts_super_hard_display_text(self) -> None:
        self.assertEqual(canonical_level_difficulty("Super Hard"), "SuperHard")
        self.assertEqual(canonical_level_difficulty("super-hard"), "SuperHard")
        self.assertEqual(normalize_level_difficulty("unknown"), "Normal")
        self.assertEqual(difficulty_label("SuperHard"), "Super Hard")

    def test_set_level_difficulty_writes_canonical_value(self) -> None:
        level = {"difficulty": "Super Hard"}

        self.assertTrue(set_level_difficulty(level, "Super Hard"))
        self.assertEqual(level["difficulty"], "SuperHard")
        self.assertFalse(set_level_difficulty(level, "SuperHard"))

    def test_load_summary_reports_invalid_difficulty_without_parse_error(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "12.json")
            with open(path, "w", encoding="utf-8") as file:
                json.dump({"level": 7, "levelName": "Odd", "difficulty": "Nightmare"}, file)

            summary = load_level_difficulty_summary(path)

        self.assertIsNone(summary.error)
        self.assertEqual(summary.level_id, 12)
        self.assertEqual(summary.level_name, "Odd")
        self.assertIsNone(summary.difficulty)
        self.assertEqual(summary.raw_difficulty, "Nightmare")

    def test_list_level_json_files_sorts_numeric_names_first(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            for name in ("10.json", "2.json", "alpha.json", "notes.txt"):
                with open(os.path.join(folder, name), "w", encoding="utf-8") as file:
                    file.write("{}")

            names = [os.path.basename(path) for path in list_level_json_files(folder)]

        self.assertEqual(names, ["2.json", "10.json", "alpha.json"])


if __name__ == "__main__":
    unittest.main()

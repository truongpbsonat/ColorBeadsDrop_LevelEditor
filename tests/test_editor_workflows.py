from __future__ import annotations

import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ball_drop_editor.editor_file_actions import EditorFileActionsMixin


class FakeWindow:
    def __init__(self) -> None:
        self.exists = True
        self.calls = []
        self.destroy_binding = None

    def winfo_exists(self):
        return self.exists

    def deiconify(self):
        self.calls.append("deiconify")

    def lift(self):
        self.calls.append("lift")

    def attributes(self, name, value):
        self.calls.append((name, value))

    def focus_force(self):
        self.calls.append("focus_force")

    def after_idle(self, callback):
        self.calls.append("after_idle")
        callback()

    def bind(self, event_name, callback, add=None):
        self.calls.append(("bind", event_name, add))
        self.destroy_binding = callback

    def destroy(self):
        self.exists = False
        if self.destroy_binding:
            self.destroy_binding(SimpleNamespace(widget=self))


class WorkflowHarness(EditorFileActionsMixin):
    def __init__(self) -> None:
        self.level = {}
        self.current_file = None
        self.level_folder = ""
        self.level_folders = []
        self.rendered_validation = None
        self.saved = False

    def render_validation_results(self, errors, warnings):
        self.rendered_validation = (errors, warnings)

    def _register_folder(self, path, make_active=False):
        if make_active:
            self.level_folder = os.path.abspath(path)

    def _refresh_level_folder_files(self):
        pass

    def _mark_current_level_saved(self):
        self.saved = True


class EditorWorkflowTests(unittest.TestCase):
    def test_tool_window_is_reused_focused_and_cleared_on_destroy(self) -> None:
        harness = WorkflowHarness()
        created = []

        def factory():
            window = FakeWindow()
            created.append(window)
            return window

        first = harness._open_or_focus_tool_window("_test_window", factory)
        second = harness._open_or_focus_tool_window("_test_window", factory)

        self.assertIs(first, second)
        self.assertEqual(len(created), 1)
        self.assertGreaterEqual(first.calls.count("deiconify"), 2)
        self.assertGreaterEqual(first.calls.count("lift"), 2)
        self.assertGreaterEqual(first.calls.count("focus_force"), 2)
        self.assertIn(("-topmost", True), first.calls)
        self.assertIn(("-topmost", False), first.calls)

        first.destroy()
        self.assertIsNone(harness._test_window)

        third = harness._open_or_focus_tool_window("_test_window", factory)
        self.assertIsNot(third, first)
        self.assertEqual(len(created), 2)

    def test_validation_ok_info_does_not_prompt(self) -> None:
        harness = WorkflowHarness()
        validator = Mock()
        validator.validate.return_value = ([], ["OK: No basic issues found."])

        with (
            patch(
                "ball_drop_editor.editor_file_actions.LevelValidator",
                return_value=validator,
            ),
            patch(
                "ball_drop_editor.editor_file_actions.messagebox.askyesno"
            ) as prompt,
        ):
            self.assertTrue(harness._confirm_validation_before_save())

        prompt.assert_not_called()
        self.assertEqual(
            harness.rendered_validation,
            ([], ["OK: No basic issues found."]),
        )

    def test_validation_errors_and_warnings_require_confirmation(self) -> None:
        harness = WorkflowHarness()
        validator = Mock()
        validator.validate.return_value = (
            ["Not enough Blue balls."],
            ["Tunnel output is blocked by Wall."],
        )

        with (
            patch(
                "ball_drop_editor.editor_file_actions.LevelValidator",
                return_value=validator,
            ),
            patch(
                "ball_drop_editor.editor_file_actions.messagebox.askyesno",
                return_value=False,
            ) as prompt,
        ):
            self.assertFalse(harness._confirm_validation_before_save())

        message = prompt.call_args.args[1]
        self.assertIn("ERROR: Not enough Blue balls.", message)
        self.assertIn("WARNING: Tunnel output is blocked by Wall.", message)

    def test_cancelled_validation_stops_before_overwrite_and_write(self) -> None:
        harness = WorkflowHarness()
        harness._confirm_validation_before_save = Mock(return_value=False)
        harness._confirm_overwrite_before_save = Mock(return_value=True)

        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "1.json")
            self.assertFalse(harness._save_level_to_path(path))
            self.assertFalse(os.path.exists(path))

        harness._confirm_overwrite_before_save.assert_not_called()
        self.assertFalse(harness.saved)

    def test_overwrite_prompt_skips_current_file_only(self) -> None:
        harness = WorkflowHarness()
        with tempfile.TemporaryDirectory() as folder:
            current = os.path.join(folder, "1.json")
            other = os.path.join(folder, "2.json")
            for path in (current, other):
                with open(path, "w", encoding="utf-8") as file:
                    file.write("{}")
            harness.current_file = current

            with patch(
                "ball_drop_editor.editor_file_actions.messagebox.askyesno",
                return_value=False,
            ) as prompt:
                self.assertTrue(harness._confirm_overwrite_before_save(current))
                prompt.assert_not_called()
                self.assertFalse(harness._confirm_overwrite_before_save(other))
                prompt.assert_called_once()

    def test_load_level_accepts_utf8_bom(self) -> None:
        harness = WorkflowHarness()
        harness.undo_stack = [object()]
        harness.redo_stack = [object()]
        harness._confirm_discard_unsaved_changes = Mock(return_value=True)
        harness._refresh_all = Mock()

        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "35.json")
            with open(path, "w", encoding="utf-8-sig") as file:
                file.write('{"level": 35, "levelName": "Level_35"}')

            self.assertTrue(harness._load_level_file(path))

        self.assertEqual(harness.level["level"], 35)
        self.assertEqual(harness.level["levelName"], "Level_35")
        self.assertEqual(harness.undo_stack, [])
        self.assertEqual(harness.redo_stack, [])
        harness._refresh_all.assert_called_once_with()
        self.assertTrue(harness.saved)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import os
import tkinter as tk


class EditorStateMixin:
    def _init_level_meta_vars(self):
        self.game_mode_var = tk.StringVar(value="Classic")
        self.difficulty_var = tk.StringVar(value="Normal")
        self.level_var = tk.StringVar(value="1")
        self.file_level_var = tk.StringVar(value="1")
        self.category_var = tk.IntVar(value=0)
        self.time_var = tk.IntVar(value=60)
        self.level_name_var = tk.StringVar(value="New Level")
        self.mechanics_var = tk.StringVar(value="")
        self.active_folder_var = tk.StringVar(value=self._level_folder_label())
        self.level_file_status_var = tk.StringVar(value="No file loaded")
        self.level_save_status_var = tk.StringVar(value="Status: Saved")
        self.rows_var = tk.IntVar(value=4)
        self.cols_var = tk.IntVar(value=4)
        self.editor_tool_mode = tk.StringVar(value="Cells")

    def _level_folder_label(self) -> str:
        folder_name = os.path.basename(os.path.normpath(self.level_folder)) or self.level_folder
        return f"Folder: {folder_name}"

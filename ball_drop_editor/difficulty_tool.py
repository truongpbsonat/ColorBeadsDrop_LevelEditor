from __future__ import annotations

import json
import os
import tkinter as tk
from dataclasses import dataclass
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable, Dict, List, Optional, Sequence

from .constants import (
    LEVEL_DIFFICULTIES,
    LEVEL_DIFFICULTY_LABELS,
    canonical_level_difficulty,
)
from .utils import safe_int


DIFFICULTY_STYLES: Dict[str, Dict[str, str]] = {
    "Normal": {
        "bg": "#DDF7C8",
        "fg": "#16813B",
        "border": "#7ACB5E",
        "active": "#C9F0AD",
    },
    "Hard": {
        "bg": "#FAD3CD",
        "fg": "#C1121F",
        "border": "#F19A90",
        "active": "#F7BDB5",
    },
    "SuperHard": {
        "bg": "#E9D5FF",
        "fg": "#7E22CE",
        "border": "#C084FC",
        "active": "#D8B4FE",
    },
}
UNKNOWN_DIFFICULTY_STYLE = {
    "bg": "#E5E7EB",
    "fg": "#374151",
    "border": "#9CA3AF",
    "active": "#D1D5DB",
}


@dataclass
class LevelDifficultySummary:
    path: str
    level_id: Optional[int]
    level_name: str = ""
    difficulty: Optional[str] = None
    raw_difficulty: str = ""
    error: Optional[str] = None


def load_level_difficulty_summary(path: str) -> LevelDifficultySummary:
    try:
        with open(path, "r", encoding="utf-8-sig") as file:
            level = json.load(file)
        if not isinstance(level, dict):
            return LevelDifficultySummary(path=path, level_id=_level_id_from_path(path), error="Root JSON is not an object.")

        level_id = _level_id_from_path(path) or safe_int(str(level.get("level", 0)), 0) or None
        raw_difficulty = str(level.get("difficulty", "") or "").strip()
        return LevelDifficultySummary(
            path=path,
            level_id=level_id,
            level_name=str(level.get("levelName", "") or "").strip(),
            difficulty=canonical_level_difficulty(raw_difficulty),
            raw_difficulty=raw_difficulty,
        )
    except Exception as exc:
        return LevelDifficultySummary(path=path, level_id=_level_id_from_path(path), error=str(exc))


def set_level_difficulty(level: Dict[str, Any], target_difficulty: str) -> bool:
    target = canonical_level_difficulty(target_difficulty)
    if target is None:
        raise ValueError(f"Unknown difficulty: {target_difficulty}")
    if level.get("difficulty") == target:
        return False
    level["difficulty"] = target
    return True


def list_level_json_files(folder: str) -> List[str]:
    if not os.path.isdir(folder):
        return []
    paths = []
    for name in os.listdir(folder):
        stem, ext = os.path.splitext(name)
        if ext.lower() == ".json" and stem:
            paths.append(os.path.join(folder, name))
    return sorted(paths, key=_level_path_sort_key)


def open_difficulty_tool(
    parent: tk.Misc,
    initial_folder: str,
    on_levels_changed: Optional[Callable[[Sequence[str]], None]] = None,
) -> "LevelDifficultyTool":
    tool = LevelDifficultyTool(parent, initial_folder, on_levels_changed)
    tool.focus_set()
    return tool


class LevelDifficultyTool(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        initial_folder: str,
        on_levels_changed: Optional[Callable[[Sequence[str]], None]] = None,
    ):
        super().__init__(parent)
        self.title("Level Difficulty Tool")
        self.geometry("940x620")
        self.minsize(820, 500)
        self.on_levels_changed = on_levels_changed
        self.summaries: List[LevelDifficultySummary] = []
        self.selected_level_paths: set[str] = set()
        self.focus_level_path: Optional[str] = None
        self.level_row_height = 30
        self.folder_var = tk.StringVar(value=initial_folder or "")
        self.target_difficulty_var = tk.StringVar(value="Normal")
        self.status_var = tk.StringVar(value="Choose a folder to scan level difficulties.")
        self.folder_summary_var = tk.StringVar(value="")
        self.selection_summary_var = tk.StringVar(value="No levels selected.")
        self.difficulty_buttons: Dict[str, tk.Button] = {}

        self._build_ui()
        if initial_folder:
            self.scan_folder()

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=10)
        root.pack(fill="both", expand=True)
        root.rowconfigure(1, weight=1)
        root.columnconfigure(0, weight=1)

        folder_frame = ttk.LabelFrame(root, text="Level Folder", padding=6)
        folder_frame.grid(row=0, column=0, sticky="ew")
        folder_frame.columnconfigure(1, weight=1)
        ttk.Button(folder_frame, text="Choose Folder", command=self.choose_folder).grid(row=0, column=0, padx=(0, 6))
        ttk.Entry(folder_frame, textvariable=self.folder_var, state="readonly").grid(row=0, column=1, sticky="ew")
        ttk.Button(folder_frame, text="Refresh", command=self.scan_folder).grid(row=0, column=2, padx=(6, 0))

        level_frame = ttk.LabelFrame(root, text="Levels", padding=6)
        level_frame.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        level_frame.rowconfigure(1, weight=1)
        level_frame.columnconfigure(0, weight=1)

        self.level_header = tk.Canvas(level_frame, height=24, highlightthickness=0, bg="#F3F4F6")
        self.level_header.grid(row=0, column=0, sticky="ew")

        self.level_canvas = tk.Canvas(level_frame, highlightthickness=1, highlightbackground="#9CA3AF", bg="#FFFFFF")
        self.level_canvas.grid(row=1, column=0, sticky="nsew")
        level_scroll_y = ttk.Scrollbar(level_frame, orient="vertical", command=self.level_canvas.yview)
        level_scroll_y.grid(row=1, column=1, sticky="ns")
        self.level_canvas.configure(yscrollcommand=level_scroll_y.set)
        self.level_canvas.bind("<Button-1>", self.on_level_canvas_click)
        self.level_canvas.bind("<Control-a>", self.select_all_levels)
        self.level_canvas.bind("<Control-A>", self.select_all_levels)
        self.level_canvas.bind("<Configure>", lambda _event: self.draw_level_list())
        self.level_canvas.bind("<MouseWheel>", self.on_level_canvas_mousewheel)

        level_actions = ttk.Frame(level_frame)
        level_actions.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Button(level_actions, text="Select All", command=self.select_all_levels).pack(side="left")
        ttk.Button(level_actions, text="Clear Selection", command=self.clear_level_selection).pack(side="left", padx=(6, 0))
        ttk.Label(level_actions, textvariable=self.folder_summary_var, anchor="e").pack(side="right")

        apply_frame = ttk.LabelFrame(root, text="Set Difficulty", padding=8)
        apply_frame.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        apply_frame.columnconfigure(1, weight=1)
        ttk.Label(apply_frame, textvariable=self.selection_summary_var).grid(row=0, column=0, sticky="w")

        button_frame = ttk.Frame(apply_frame)
        button_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        for index, difficulty in enumerate(LEVEL_DIFFICULTIES):
            style = difficulty_style(difficulty)
            button = tk.Button(
                button_frame,
                text=difficulty_label(difficulty),
                width=13,
                height=1,
                bg=style["bg"],
                fg=style["fg"],
                activebackground=style["active"],
                activeforeground=style["fg"],
                command=lambda next_difficulty=difficulty: self.set_target_difficulty(next_difficulty),
            )
            button.grid(row=0, column=index, sticky="ew", padx=(0 if index == 0 else 6, 0))
            button_frame.columnconfigure(index, weight=0)
            self.difficulty_buttons[difficulty] = button

        ttk.Button(apply_frame, text="Apply To Selected Level(s)", command=self.apply_difficulty).grid(
            row=1,
            column=2,
            sticky="e",
            padx=(12, 0),
            pady=(8, 0),
        )

        ttk.Label(root, textvariable=self.status_var, anchor="w").grid(row=3, column=0, sticky="ew", pady=(8, 0))
        self.refresh_target_buttons()

    def choose_folder(self) -> None:
        initial_dir = self.folder_var.get()
        if not os.path.isdir(initial_dir):
            initial_dir = os.getcwd()
        folder = filedialog.askdirectory(initialdir=initial_dir, title="Choose folder with level JSON files")
        if not folder:
            return
        self.folder_var.set(folder)
        self.scan_folder()

    def scan_folder(self, select_paths: Optional[Sequence[str]] = None) -> None:
        folder = self.folder_var.get()
        if not os.path.isdir(folder):
            messagebox.showwarning("Difficulty Tool", "Choose a valid level folder first.")
            return

        selected_paths = {os.path.normcase(os.path.abspath(path)) for path in (select_paths or self.selected_paths())}
        self.summaries = [load_level_difficulty_summary(path) for path in list_level_json_files(folder)]
        self.populate_level_tree(selected_paths)
        self.update_folder_summary()
        self.status_var.set(f"Scanned {len(self.summaries)} JSON level file(s).")

    def populate_level_tree(self, selected_paths: set[str]) -> None:
        self.selected_level_paths.clear()
        for summary in self.summaries:
            normalized_path = os.path.normcase(os.path.abspath(summary.path))
            if normalized_path in selected_paths:
                self.selected_level_paths.add(summary.path)

        if not self.selected_level_paths and self.summaries:
            self.selected_level_paths.add(self.summaries[0].path)
        self.focus_level_path = next(iter(self.selected_level_paths), None)
        self.draw_level_list()
        self.on_level_selection_changed()

    def level_column_layout(self) -> List[tuple[str, int, int]]:
        canvas_width = max(self.level_canvas.winfo_width(), 1)
        level_width = 70
        difficulty_width = 170
        file_width = 125
        name_width = max(180, canvas_width - level_width - difficulty_width - file_width - 2)
        return [
            ("level", 0, level_width),
            ("name", level_width, name_width),
            ("difficulty", level_width + name_width, difficulty_width),
            ("file", level_width + name_width + difficulty_width, file_width),
        ]

    def draw_level_list(self) -> None:
        if not hasattr(self, "level_canvas"):
            return
        columns = self.level_column_layout()
        table_width = columns[-1][1] + columns[-1][2]
        self.draw_level_header(columns, table_width)

        canvas = self.level_canvas
        canvas.delete("all")
        row_height = self.level_row_height
        total_height = max(row_height * len(self.summaries), canvas.winfo_height())
        canvas.configure(scrollregion=(0, 0, table_width, total_height))

        for index, summary in enumerate(self.summaries):
            y = index * row_height
            is_selected = summary.path in self.selected_level_paths
            fill = "#0B78D0" if is_selected else ("#FFFFFF" if index % 2 == 0 else "#F9FAFB")
            fg = "#FFFFFF" if is_selected else ("#B91C1C" if summary.error else "#111827")
            canvas.create_rectangle(0, y, table_width, y + row_height, fill=fill, outline="#E5E7EB")
            self.draw_level_text_cell(canvas, columns[0], y, _level_display(summary), fg)
            self.draw_level_text_cell(canvas, columns[1], y, summary.level_name, fg)
            self.draw_level_difficulty_cell(canvas, columns[2], y, summary, is_selected)
            self.draw_level_text_cell(canvas, columns[3], y, os.path.basename(summary.path), fg)

    def draw_level_header(self, columns: List[tuple[str, int, int]], table_width: int) -> None:
        header = self.level_header
        header.delete("all")
        header.configure(scrollregion=(0, 0, table_width, 24))
        titles = {
            "level": "Level",
            "name": "Name",
            "difficulty": "Difficulty",
            "file": "File",
        }
        for key, x, width in columns:
            header.create_rectangle(x, 0, x + width, 24, fill="#F3F4F6", outline="#D1D5DB")
            header.create_text(x + width // 2, 12, text=titles[key], fill="#111827", font=("Arial", 9, "bold"))

    def draw_level_text_cell(
        self,
        canvas: tk.Canvas,
        column: tuple[str, int, int],
        y: int,
        text: str,
        fill: str,
    ) -> None:
        _key, x, width = column
        canvas.create_text(
            x + 6,
            y + self.level_row_height // 2,
            text=text,
            anchor="w",
            fill=fill,
            font=("Arial", 9),
            width=max(20, width - 12),
        )

    def draw_level_difficulty_cell(
        self,
        canvas: tk.Canvas,
        column: tuple[str, int, int],
        y: int,
        summary: LevelDifficultySummary,
        is_selected: bool,
    ) -> None:
        _key, x, width = column
        text = summary_difficulty_text(summary)
        style = difficulty_style(summary.difficulty)
        pill_x1 = x + 10
        pill_y1 = y + 5
        pill_x2 = x + width - 10
        pill_y2 = y + self.level_row_height - 5
        _rounded_rect(
            canvas,
            pill_x1,
            pill_y1,
            pill_x2,
            pill_y2,
            9,
            fill=style["bg"],
            outline="#FFFFFF" if is_selected else style["border"],
            width=2 if is_selected else 1,
        )
        canvas.create_text(
            (pill_x1 + pill_x2) // 2 - 7,
            y + self.level_row_height // 2,
            text=text,
            fill=style["fg"],
            font=("Arial", 9, "bold"),
        )
        arrow_x = pill_x2 - 17
        arrow_y = y + self.level_row_height // 2
        canvas.create_polygon(
            arrow_x - 5,
            arrow_y - 2,
            arrow_x + 5,
            arrow_y - 2,
            arrow_x,
            arrow_y + 4,
            fill=style["fg"],
            outline=style["fg"],
        )

    def on_level_canvas_click(self, event: tk.Event) -> str:
        canvas_y = self.level_canvas.canvasy(event.y)
        index = int(canvas_y // self.level_row_height)
        if not (0 <= index < len(self.summaries)):
            return "break"

        path = self.summaries[index].path
        state = getattr(event, "state", 0)
        shift_pressed = bool(state & 0x0001)
        ctrl_pressed = bool(state & 0x0004)
        if shift_pressed and self.focus_level_path:
            focus_index = next((i for i, summary in enumerate(self.summaries) if summary.path == self.focus_level_path), index)
            start, end = sorted((focus_index, index))
            if not ctrl_pressed:
                self.selected_level_paths.clear()
            self.selected_level_paths.update(summary.path for summary in self.summaries[start:end + 1])
        elif ctrl_pressed:
            if path in self.selected_level_paths and len(self.selected_level_paths) > 1:
                self.selected_level_paths.remove(path)
            else:
                self.selected_level_paths.add(path)
            self.focus_level_path = path
        else:
            self.selected_level_paths = {path}
            self.focus_level_path = path

        self.draw_level_list()
        self.on_level_selection_changed()
        return "break"

    def on_level_canvas_mousewheel(self, event: tk.Event) -> str:
        self.level_canvas.yview_scroll(int(-event.delta / 120), "units")
        return "break"

    def on_level_selection_changed(self) -> None:
        summaries = self.selected_summaries()
        self.selection_summary_var.set(selected_summary_text(summaries))
        if summaries:
            self.status_var.set(f"Selected {len(summaries)} level(s).")

    def selected_paths(self) -> List[str]:
        return [
            summary.path
            for summary in self.summaries
            if summary.path in self.selected_level_paths
        ]

    def selected_summaries(self) -> List[LevelDifficultySummary]:
        selected = {os.path.normcase(os.path.abspath(path)) for path in self.selected_paths()}
        return [
            summary
            for summary in self.summaries
            if os.path.normcase(os.path.abspath(summary.path)) in selected
        ]

    def select_all_levels(self, _event: Optional[tk.Event] = None) -> str:
        self.selected_level_paths = {summary.path for summary in self.summaries}
        self.focus_level_path = self.summaries[0].path if self.summaries else None
        self.draw_level_list()
        self.on_level_selection_changed()
        return "break"

    def clear_level_selection(self) -> None:
        self.selected_level_paths.clear()
        self.focus_level_path = None
        self.draw_level_list()
        self.on_level_selection_changed()

    def set_target_difficulty(self, difficulty: str) -> None:
        target = canonical_level_difficulty(difficulty)
        if target is None:
            return
        self.target_difficulty_var.set(target)
        self.refresh_target_buttons()

    def refresh_target_buttons(self) -> None:
        selected = self.target_difficulty_var.get()
        for difficulty, button in self.difficulty_buttons.items():
            style = difficulty_style(difficulty)
            button.configure(
                relief="sunken" if difficulty == selected else "raised",
                bd=4 if difficulty == selected else 1,
                bg=style["bg"],
                fg=style["fg"],
                activebackground=style["active"],
            )

    def update_folder_summary(self) -> None:
        self.folder_summary_var.set(selected_summary_text(self.summaries, prefix="Folder"))

    def apply_difficulty(self) -> None:
        paths = self.selected_paths()
        if not paths:
            messagebox.showwarning("Difficulty Tool", "Select one or more levels first.")
            return

        target = canonical_level_difficulty(self.target_difficulty_var.get())
        if target is None:
            messagebox.showwarning("Difficulty Tool", "Choose a valid target difficulty.")
            return

        target_paths = [summary.path for summary in self.selected_summaries() if not summary.error]
        if not target_paths:
            messagebox.showwarning("Difficulty Tool", "No valid selected level JSON files to update.")
            return

        if not messagebox.askyesno(
            "Set Difficulty",
            f"Set difficulty to {difficulty_label(target)} in {len(target_paths)} selected level file(s)?\n\n"
            "This edits the JSON files on disk.",
        ):
            return

        changed_paths: List[str] = []
        unchanged = 0
        errors: List[str] = []
        for path in target_paths:
            try:
                with open(path, "r", encoding="utf-8-sig") as file:
                    level = json.load(file)
                if not isinstance(level, dict):
                    errors.append(f"{os.path.basename(path)}: root JSON is not an object")
                    continue
                changed = set_level_difficulty(level, target)
                if not changed:
                    unchanged += 1
                    continue
                with open(path, "w", encoding="utf-8") as file:
                    json.dump(level, file, ensure_ascii=False, indent=2)
                    file.write("\n")
                changed_paths.append(path)
            except Exception as exc:
                errors.append(f"{os.path.basename(path)}: {exc}")

        self.scan_folder(select_paths=changed_paths or paths)
        if changed_paths and self.on_levels_changed:
            self.on_levels_changed(changed_paths)

        message = (
            f"Updated {len(changed_paths)} level file(s) to {difficulty_label(target)}."
            f"\nUnchanged: {unchanged}"
        )
        if errors:
            message += "\n\nErrors:\n" + "\n".join(errors[:8])
            if len(errors) > 8:
                message += f"\n...and {len(errors) - 8} more."
            messagebox.showwarning("Difficulty Tool", message)
        elif changed_paths:
            messagebox.showinfo("Difficulty Tool", message)
        else:
            messagebox.showinfo("Difficulty Tool", f"Selected level(s) already use {difficulty_label(target)}.")
        self.status_var.set(message)


def difficulty_style(difficulty: Optional[str]) -> Dict[str, str]:
    if difficulty in DIFFICULTY_STYLES:
        return DIFFICULTY_STYLES[difficulty]
    return UNKNOWN_DIFFICULTY_STYLE


def difficulty_label(difficulty: Optional[str]) -> str:
    if difficulty in LEVEL_DIFFICULTY_LABELS:
        return LEVEL_DIFFICULTY_LABELS[difficulty]
    return str(difficulty or "Unknown")


def summary_difficulty_text(summary: LevelDifficultySummary) -> str:
    if summary.error:
        return "Error"
    if summary.difficulty:
        return difficulty_label(summary.difficulty)
    if summary.raw_difficulty:
        return f"Invalid: {summary.raw_difficulty}"
    return "Missing"


def selected_summary_text(summaries: Sequence[LevelDifficultySummary], prefix: str = "Selected") -> str:
    if not summaries:
        return f"{prefix}: 0"

    counts = {difficulty: 0 for difficulty in LEVEL_DIFFICULTIES}
    invalid = 0
    errors = 0
    for summary in summaries:
        if summary.error:
            errors += 1
        elif summary.difficulty in counts:
            counts[summary.difficulty] += 1
        else:
            invalid += 1

    parts = [f"{difficulty_label(difficulty)}: {counts[difficulty]}" for difficulty in LEVEL_DIFFICULTIES]
    if invalid:
        parts.append(f"Invalid/Missing: {invalid}")
    if errors:
        parts.append(f"Errors: {errors}")
    return f"{prefix}: {len(summaries)} | " + " | ".join(parts)


def _rounded_rect(
    canvas: tk.Canvas,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    radius: int,
    **kwargs: Any,
) -> int:
    points = [
        x1 + radius,
        y1,
        x2 - radius,
        y1,
        x2,
        y1,
        x2,
        y1 + radius,
        x2,
        y2 - radius,
        x2,
        y2,
        x2 - radius,
        y2,
        x1 + radius,
        y2,
        x1,
        y2,
        x1,
        y2 - radius,
        x1,
        y1 + radius,
        x1,
        y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


def _level_id_from_path(path: str) -> Optional[int]:
    stem = os.path.splitext(os.path.basename(path))[0]
    if stem.isdigit():
        level_id = int(stem)
        return level_id if level_id > 0 else None
    return None


def _level_path_sort_key(path: str) -> tuple[int, int, str]:
    level_id = _level_id_from_path(path)
    if level_id is not None:
        return (0, level_id, os.path.basename(path).lower())
    return (1, 0, os.path.basename(path).lower())


def _level_display(summary: LevelDifficultySummary) -> str:
    if summary.level_id is not None:
        return str(summary.level_id)
    return "?"

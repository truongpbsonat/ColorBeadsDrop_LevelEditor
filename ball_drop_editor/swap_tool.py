from __future__ import annotations

import copy
import json
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable, Dict, List, Optional, Sequence

from .difficulty_tool import (
    LevelDifficultySummary,
    _level_display,
    _rounded_rect,
    difficulty_style,
    list_level_json_files,
    load_level_difficulty_summary,
    summary_difficulty_text,
)


def _norm(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


def apply_level_order(slot_paths: Sequence[str], ordered_paths: Sequence[str]) -> List[str]:
    """Reorder level contents across a fixed set of file slots.

    ``slot_paths`` are the destination files in their original order (the fixed
    anchors). ``ordered_paths`` is a permutation of the same files describing,
    for each slot, whose gameplay content should end up there. Each slot keeps
    its own file name and its own ``level`` field; only the gameplay content is
    moved between files.

    All files are read up front, so a permutation (where a file is both a source
    and a destination) is applied safely. Returns the destination paths whose
    content actually changed.
    """
    if len(slot_paths) != len(ordered_paths):
        raise ValueError("Slot and order lists must be the same length.")
    if sorted(_norm(p) for p in slot_paths) != sorted(_norm(p) for p in ordered_paths):
        raise ValueError("The new order must be a permutation of the same files.")

    contents = {_norm(path): _load_level_dict(path) for path in slot_paths}
    dest_levels = {_norm(path): contents[_norm(path)].get("level") for path in slot_paths}

    changed: List[str] = []
    for slot_path, source_path in zip(slot_paths, ordered_paths):
        if _norm(source_path) == _norm(slot_path):
            continue
        content = copy.deepcopy(contents[_norm(source_path)])
        content["level"] = dest_levels[_norm(slot_path)]
        _write_level_dict(slot_path, content)
        changed.append(slot_path)
    return changed


def _load_level_dict(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8-sig") as file:
        level = json.load(file)
    if not isinstance(level, dict):
        raise ValueError(f"{os.path.basename(path)}: root JSON is not an object.")
    return level


def _write_level_dict(path: str, level: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as file:
        json.dump(level, file, ensure_ascii=False, indent=2)
        file.write("\n")


def open_swap_tool(
    parent: tk.Misc,
    initial_folder: str,
    on_levels_changed: Optional[Callable[[Sequence[str]], None]] = None,
) -> "LevelSwapTool":
    tool = LevelSwapTool(parent, initial_folder, on_levels_changed)
    tool.focus_set()
    return tool


class LevelSwapTool(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        initial_folder: str,
        on_levels_changed: Optional[Callable[[Sequence[str]], None]] = None,
    ):
        super().__init__(parent)
        self.title("Level Swap Tool")
        self.geometry("940x640")
        self.minsize(820, 520)
        self.on_levels_changed = on_levels_changed

        # ``summaries`` are the fixed anchors (destination slots) in their
        # original sorted order. ``order`` is a permutation of range(len) giving
        # the current display order: display row k shows summaries[order[k]].
        self.summaries: List[LevelDifficultySummary] = []
        self.order: List[int] = []
        self.level_row_height = 30
        self.selected_display_index: Optional[int] = None

        # Drag-and-drop (reorder) state.
        self._press_display_index: Optional[int] = None
        self._press_y: float = 0.0
        self._dragging = False
        self._drop_index: Optional[int] = None
        self._drag_pointer_y: float = 0.0

        self.folder_var = tk.StringVar(value=initial_folder or "")
        self.status_var = tk.StringVar(
            value="Kéo & thả để sắp xếp lại thứ tự level, rồi bấm \"Apply Reorder\" để xác nhận."
        )
        self.folder_summary_var = tk.StringVar(value="")
        self.pending_var = tk.StringVar(value="Chưa có thay đổi.")

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
        ttk.Button(folder_frame, text="Refresh", command=self.confirm_discard_then_scan).grid(row=0, column=2, padx=(6, 0))

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
        self.level_canvas.bind("<ButtonPress-1>", self.on_level_canvas_press)
        self.level_canvas.bind("<B1-Motion>", self.on_level_canvas_drag)
        self.level_canvas.bind("<ButtonRelease-1>", self.on_level_canvas_release)
        self.level_canvas.bind("<Configure>", lambda _event: self.draw_level_list())
        self.level_canvas.bind("<MouseWheel>", self.on_level_canvas_mousewheel)

        level_actions = ttk.Frame(level_frame)
        level_actions.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Label(
            level_actions,
            text="Kéo một level tới vị trí mới; các level đã đổi chỗ sẽ được tô vàng.",
            anchor="w",
        ).pack(side="left")
        ttk.Label(level_actions, textvariable=self.folder_summary_var, anchor="e").pack(side="right")

        apply_frame = ttk.LabelFrame(root, text="Apply Reorder", padding=8)
        apply_frame.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        apply_frame.columnconfigure(0, weight=1)
        ttk.Label(apply_frame, textvariable=self.pending_var, anchor="w").grid(row=0, column=0, sticky="w")
        self.reset_button = ttk.Button(apply_frame, text="Reset Order", command=self.reset_order, state="disabled")
        self.reset_button.grid(row=0, column=1, padx=(12, 0))
        self.apply_button = ttk.Button(apply_frame, text="Apply Reorder", command=self.apply_reorder, state="disabled")
        self.apply_button.grid(row=0, column=2, padx=(6, 0))

        ttk.Label(root, textvariable=self.status_var, anchor="w").grid(row=3, column=0, sticky="ew", pady=(8, 0))

    # ------------------------------------------------------------------ folder

    def choose_folder(self) -> None:
        if not self.confirm_discard_pending():
            return
        initial_dir = self.folder_var.get()
        if not os.path.isdir(initial_dir):
            initial_dir = os.getcwd()
        folder = filedialog.askdirectory(initialdir=initial_dir, title="Choose folder with level JSON files")
        if not folder:
            return
        self.folder_var.set(folder)
        self.scan_folder()

    def confirm_discard_then_scan(self) -> None:
        if self.confirm_discard_pending():
            self.scan_folder()

    def confirm_discard_pending(self) -> bool:
        if not self.is_dirty():
            return True
        return messagebox.askyesno(
            "Swap Tool",
            "Bạn đang có thay đổi thứ tự chưa áp dụng. Bỏ các thay đổi này?",
        )

    def scan_folder(self, select_path: Optional[str] = None) -> None:
        folder = self.folder_var.get()
        if not os.path.isdir(folder):
            messagebox.showwarning("Swap Tool", "Choose a valid level folder first.")
            return

        self.summaries = [load_level_difficulty_summary(path) for path in list_level_json_files(folder)]
        self.order = list(range(len(self.summaries)))
        self.selected_display_index = None
        if select_path is not None:
            target = _norm(select_path)
            for display_index, summary_index in enumerate(self.order):
                if _norm(self.summaries[summary_index].path) == target:
                    self.selected_display_index = display_index
                    break
        self._reset_drag_state()
        self.draw_level_list()
        self.update_folder_summary()
        self.update_pending_state()
        self.status_var.set(f"Scanned {len(self.summaries)} JSON level file(s).")

    # ------------------------------------------------------------------ drawing

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
        total_height = max(row_height * len(self.order), canvas.winfo_height())
        canvas.configure(scrollregion=(0, 0, table_width, total_height))

        for display_index, summary_index in enumerate(self.order):
            summary = self.summaries[summary_index]
            y = display_index * row_height
            is_moved = summary_index != display_index
            is_source = self._dragging and display_index == self._press_display_index
            is_selected = display_index == self.selected_display_index

            if is_source:
                fill = "#DBEAFE"
            elif is_selected:
                fill = "#0B78D0"
            elif is_moved:
                fill = "#FEF08A"
            else:
                fill = "#FFFFFF" if display_index % 2 == 0 else "#F9FAFB"
            fg = "#FFFFFF" if is_selected and not is_source else ("#B91C1C" if summary.error else "#111827")

            canvas.create_rectangle(0, y, table_width, y + row_height, fill=fill, outline="#E5E7EB")
            self.draw_level_text_cell(canvas, columns[0], y, _level_display(summary), fg)
            self.draw_level_text_cell(canvas, columns[1], y, summary.level_name, fg)
            self.draw_level_difficulty_cell(canvas, columns[2], y, summary)
            self.draw_level_text_cell(canvas, columns[3], y, os.path.basename(summary.path), fg)

        if self._dragging and self._drop_index is not None:
            line_y = self._drop_index * row_height
            canvas.create_line(0, line_y, table_width, line_y, fill="#F59E0B", width=3)
        if self._dragging and self._press_display_index is not None:
            self.draw_drag_ghost(table_width)

    def draw_drag_ghost(self, table_width: int) -> None:
        summary = self.summaries[self.order[self._press_display_index]]
        canvas = self.level_canvas
        y = self._drag_pointer_y
        label = f"{_level_display(summary)}  {os.path.basename(summary.path)}"
        ghost_width = min(260, table_width - 20)
        x1 = 12
        _rounded_rect(canvas, x1, y - 13, x1 + ghost_width, y + 13, 8, fill="#1F2937", outline="#111827")
        canvas.create_text(x1 + 12, y, text=label, anchor="w", fill="#FFFFFF", font=("Arial", 9, "bold"))

    def draw_level_header(self, columns: List[tuple[str, int, int]], table_width: int) -> None:
        header = self.level_header
        header.delete("all")
        header.configure(scrollregion=(0, 0, table_width, 24))
        titles = {"level": "Level", "name": "Name", "difficulty": "Difficulty", "file": "File"}
        for key, x, width in columns:
            header.create_rectangle(x, 0, x + width, 24, fill="#F3F4F6", outline="#D1D5DB")
            header.create_text(x + width // 2, 12, text=titles[key], fill="#111827", font=("Arial", 9, "bold"))

    def draw_level_text_cell(self, canvas: tk.Canvas, column: tuple[str, int, int], y: int, text: str, fill: str) -> None:
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
    ) -> None:
        _key, x, width = column
        text = summary_difficulty_text(summary)
        style = difficulty_style(summary.difficulty)
        pill_x1 = x + 10
        pill_y1 = y + 5
        pill_x2 = x + width - 10
        pill_y2 = y + self.level_row_height - 5
        _rounded_rect(canvas, pill_x1, pill_y1, pill_x2, pill_y2, 9, fill=style["bg"], outline=style["border"])
        canvas.create_text(
            (pill_x1 + pill_x2) // 2,
            y + self.level_row_height // 2,
            text=text,
            fill=style["fg"],
            font=("Arial", 9, "bold"),
        )

    # ------------------------------------------------------------- interaction

    def _display_index_at_event(self, event: tk.Event) -> Optional[int]:
        canvas_y = self.level_canvas.canvasy(event.y)
        index = int(canvas_y // self.level_row_height)
        if 0 <= index < len(self.order):
            return index
        return None

    def _drop_index_at_event(self, event: tk.Event) -> int:
        canvas_y = self.level_canvas.canvasy(event.y)
        boundary = int(canvas_y / self.level_row_height + 0.5)
        return max(0, min(boundary, len(self.order)))

    def on_level_canvas_press(self, event: tk.Event) -> str:
        index = self._display_index_at_event(event)
        self._press_display_index = index
        self._press_y = self.level_canvas.canvasy(event.y)
        self._dragging = False
        self._drop_index = None
        if index is not None:
            self.selected_display_index = index
            self.draw_level_list()
        return "break"

    def on_level_canvas_drag(self, event: tk.Event) -> str:
        if self._press_display_index is None:
            return "break"
        canvas_y = self.level_canvas.canvasy(event.y)
        if not self._dragging and abs(canvas_y - self._press_y) < 5:
            return "break"
        self._dragging = True
        self._drag_pointer_y = canvas_y
        self._drop_index = self._drop_index_at_event(event)
        self.draw_level_list()
        return "break"

    def on_level_canvas_release(self, event: tk.Event) -> str:
        was_dragging = self._dragging
        source = self._press_display_index
        drop_index = self._drop_index_at_event(event) if was_dragging else None
        self._reset_drag_state()

        if not was_dragging or source is None or drop_index is None:
            self.draw_level_list()
            return "break"

        # Convert an insertion boundary into a destination index after removal.
        destination = drop_index - 1 if drop_index > source else drop_index
        destination = max(0, min(destination, len(self.order) - 1))
        if destination != source:
            item = self.order.pop(source)
            self.order.insert(destination, item)
            self.selected_display_index = destination
        else:
            self.selected_display_index = source

        self.draw_level_list()
        self.update_pending_state()
        return "break"

    def on_level_canvas_mousewheel(self, event: tk.Event) -> str:
        self.level_canvas.yview_scroll(int(-event.delta / 120), "units")
        return "break"

    def _reset_drag_state(self) -> None:
        self._press_display_index = None
        self._dragging = False
        self._drop_index = None

    # ----------------------------------------------------------------- pending

    def is_dirty(self) -> bool:
        return any(summary_index != display_index for display_index, summary_index in enumerate(self.order))

    def moved_display_indices(self) -> List[int]:
        return [
            display_index
            for display_index, summary_index in enumerate(self.order)
            if summary_index != display_index
        ]

    def update_pending_state(self) -> None:
        moved = self.moved_display_indices()
        has_error = any(self.summaries[i].error for i in range(len(self.summaries)))
        if moved:
            self.pending_var.set(f"{len(moved)} level sẽ được đổi chỗ.")
            self.apply_button.configure(state="disabled" if has_error else "normal")
            self.reset_button.configure(state="normal")
        else:
            self.pending_var.set("Chưa có thay đổi.")
            self.apply_button.configure(state="disabled")
            self.reset_button.configure(state="disabled")
        if has_error and moved:
            self.status_var.set("Có level lỗi đọc JSON — không thể áp dụng cho tới khi khắc phục.")

    def reset_order(self) -> None:
        self.order = list(range(len(self.summaries)))
        self.selected_display_index = None
        self.draw_level_list()
        self.update_pending_state()
        self.status_var.set("Đã khôi phục thứ tự ban đầu.")

    def apply_reorder(self) -> None:
        moved = self.moved_display_indices()
        if not moved:
            messagebox.showinfo("Swap Tool", "Không có thay đổi thứ tự để áp dụng.")
            return
        if any(self.summaries[i].error for i in range(len(self.summaries))):
            messagebox.showwarning(
                "Swap Tool",
                "Có level lỗi đọc JSON trong folder. Hãy khắc phục hoặc bỏ các file lỗi trước khi đổi chỗ.",
            )
            return

        preview_lines = []
        for display_index in moved:
            slot = self.summaries[display_index]
            content = self.summaries[self.order[display_index]]
            preview_lines.append(
                f"• {os.path.basename(content.path)} → {os.path.basename(slot.path)} (Level {_level_display(slot)})"
            )
        preview = "\n".join(preview_lines[:12])
        if len(preview_lines) > 12:
            preview += f"\n… và {len(preview_lines) - 12} thay đổi khác."

        if not messagebox.askyesno(
            "Apply Reorder",
            f"Áp dụng đổi chỗ cho {len(moved)} level?\n\n"
            f"{preview}\n\n"
            "Mỗi file giữ nguyên tên và trường \"level\"; chỉ nội dung được tráo giữa các file.\n"
            "Thao tác này ghi trực tiếp lên các file JSON.",
        ):
            return

        slot_paths = [summary.path for summary in self.summaries]
        ordered_paths = [self.summaries[summary_index].path for summary_index in self.order]

        selected_path = None
        if self.selected_display_index is not None and 0 <= self.selected_display_index < len(self.summaries):
            selected_path = self.summaries[self.selected_display_index].path

        try:
            changed = apply_level_order(slot_paths, ordered_paths)
        except Exception as exc:
            messagebox.showerror("Swap Tool", f"Đổi chỗ thất bại:\n{exc}")
            self.scan_folder()
            return

        self.scan_folder(select_path=selected_path)
        if changed and self.on_levels_changed:
            self.on_levels_changed(changed)

        message = f"Đã đổi chỗ, cập nhật {len(changed)} file level."
        self.status_var.set(message)
        messagebox.showinfo("Swap Tool", message)

    def update_folder_summary(self) -> None:
        self.folder_summary_var.set(f"Folder: {len(self.summaries)} level(s)")

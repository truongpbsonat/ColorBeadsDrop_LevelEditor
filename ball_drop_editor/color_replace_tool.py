from __future__ import annotations

import json
import os
import tkinter as tk
from dataclasses import dataclass, field
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from .color_utils import SELECTABLE_BALL_COLORS, color_text_hex
from .constants import BALL_COLORS, COLOR_HEX
from .utils import safe_int


@dataclass
class ColorUsage:
    shooter_refs: int = 0
    shooter_capacity: int = 0
    tray_refs: int = 0
    tray_required: int = 0

    @property
    def total_refs(self) -> int:
        return self.shooter_refs + self.tray_refs

    def add(self, other: "ColorUsage") -> None:
        self.shooter_refs += other.shooter_refs
        self.shooter_capacity += other.shooter_capacity
        self.tray_refs += other.tray_refs
        self.tray_required += other.tray_required


@dataclass
class LevelColorSummary:
    path: str
    level_id: Optional[int]
    level_name: str = ""
    colors: Dict[str, ColorUsage] = field(default_factory=dict)
    error: Optional[str] = None


def collect_level_color_usage(level: Dict[str, Any]) -> Dict[str, ColorUsage]:
    colors: Dict[str, ColorUsage] = {}
    for shooter in _iter_level_shooters(level):
        color = _valid_color_id(shooter.get("colorId"))
        if not color:
            continue
        usage = colors.setdefault(color, ColorUsage())
        usage.shooter_refs += 1
        usage.shooter_capacity += max(0, safe_int(str(shooter.get("capacity", 0)), 0))

    for layer in _iter_level_tray_layers(level):
        color = _valid_color_id(layer.get("colorId"))
        if not color:
            continue
        usage = colors.setdefault(color, ColorUsage())
        usage.tray_refs += 1
        usage.tray_required += max(0, safe_int(str(layer.get("requiredCount", 0)), 0))
    return colors


def replace_level_color(level: Dict[str, Any], source_color: str, replacement_color: str) -> int:
    changed = 0
    if not source_color or source_color == replacement_color:
        return changed

    for shooter in _iter_level_shooters(level):
        if shooter.get("colorId") == source_color:
            shooter["colorId"] = replacement_color
            changed += 1

    for layer in _iter_level_tray_layers(level):
        if layer.get("colorId") == source_color:
            layer["colorId"] = replacement_color
            changed += 1
    return changed


def load_level_color_summary(path: str) -> LevelColorSummary:
    try:
        with open(path, "r", encoding="utf-8") as file:
            level = json.load(file)
        if not isinstance(level, dict):
            return LevelColorSummary(path=path, level_id=_level_id_from_path(path), error="Root JSON is not an object.")
        level_id = _level_id_from_path(path) or safe_int(str(level.get("level", 0)), 0) or None
        level_name = str(level.get("levelName", "") or "").strip()
        return LevelColorSummary(
            path=path,
            level_id=level_id,
            level_name=level_name,
            colors=collect_level_color_usage(level),
        )
    except Exception as exc:
        return LevelColorSummary(path=path, level_id=_level_id_from_path(path), error=str(exc))


def list_level_json_files(folder: str) -> List[str]:
    if not os.path.isdir(folder):
        return []
    paths = []
    for name in os.listdir(folder):
        stem, ext = os.path.splitext(name)
        if ext.lower() == ".json" and stem:
            paths.append(os.path.join(folder, name))
    return sorted(paths, key=_level_path_sort_key)


def open_color_replace_tool(
    parent: tk.Misc,
    initial_folder: str,
    on_levels_changed: Optional[Callable[[Sequence[str]], None]] = None,
) -> "LevelColorReplaceTool":
    tool = LevelColorReplaceTool(parent, initial_folder, on_levels_changed)
    tool.focus_set()
    return tool


class LevelColorReplaceTool(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        initial_folder: str,
        on_levels_changed: Optional[Callable[[Sequence[str]], None]] = None,
    ):
        super().__init__(parent)
        self.title("Level Color Replace Tool")
        self.geometry("1040x660")
        self.minsize(900, 540)
        self.on_levels_changed = on_levels_changed
        self.summaries: List[LevelColorSummary] = []
        self.selected_level_paths: set[str] = set()
        self.focus_level_path: Optional[str] = None
        self.color_by_usage_item: Dict[str, str] = {}
        self.source_color_buttons: Dict[str, tk.Button] = {}
        self.level_row_height = 28
        self.folder_var = tk.StringVar(value=initial_folder or "")
        self.source_color_var = tk.StringVar()
        self.replacement_color_var = tk.StringVar(value="Blue")
        self.status_var = tk.StringVar(value="Choose a folder to scan level colors.")

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

        pane = ttk.PanedWindow(root, orient="horizontal")
        pane.grid(row=1, column=0, sticky="nsew", pady=(8, 0))

        level_frame = ttk.LabelFrame(pane, text="Levels", padding=6)
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

        usage_frame = ttk.LabelFrame(pane, text="Selected Color Usage", padding=6)
        usage_frame.rowconfigure(0, weight=1)
        usage_frame.columnconfigure(0, weight=1)
        self.usage_tree = ttk.Treeview(
            usage_frame,
            columns=("color", "shooter", "tray", "refs"),
            show="headings",
            selectmode="browse",
        )
        for key, title, width in [
            ("color", "Color", 110),
            ("shooter", "Shooter refs/cap", 120),
            ("tray", "Tray layers/need", 120),
            ("refs", "Total refs", 80),
        ]:
            self.usage_tree.heading(key, text=title)
            self.usage_tree.column(key, width=width, minwidth=70, anchor="center", stretch=(key == "color"))
        self.usage_tree.grid(row=0, column=0, sticky="nsew")
        usage_scroll = ttk.Scrollbar(usage_frame, orient="vertical", command=self.usage_tree.yview)
        usage_scroll.grid(row=0, column=1, sticky="ns")
        self.usage_tree.configure(yscrollcommand=usage_scroll.set)
        self.usage_tree.bind("<<TreeviewSelect>>", self.on_usage_color_selected)

        pane.add(level_frame, weight=3)
        pane.add(usage_frame, weight=2)

        replace_frame = ttk.LabelFrame(root, text="Replace Color", padding=8)
        replace_frame.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        replace_frame.columnconfigure(5, weight=1)

        ttk.Label(replace_frame, text="Source").grid(row=0, column=0, sticky="w")
        self.source_palette = ttk.Frame(replace_frame)
        self.source_palette.grid(row=0, column=1, columnspan=5, sticky="ew", padx=(4, 14))

        ttk.Label(replace_frame, text="Replacement").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.replacement_combo = ttk.Combobox(
            replace_frame,
            textvariable=self.replacement_color_var,
            values=SELECTABLE_BALL_COLORS,
            state="readonly",
            width=18,
        )
        self.replacement_combo.grid(row=1, column=1, sticky="w", padx=(4, 14), pady=(8, 0))
        self.replacement_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_replacement_preview())

        self.replacement_preview = tk.Label(replace_frame, width=10, relief="solid", bd=1)
        self.replacement_preview.grid(row=1, column=2, sticky="w", pady=(8, 0))

        palette = ttk.Frame(replace_frame)
        palette.grid(row=2, column=0, columnspan=6, sticky="ew", pady=(8, 0))
        for index, color in enumerate(SELECTABLE_BALL_COLORS):
            button = tk.Button(
                palette,
                text=_short_color_label(color),
                width=4,
                height=1,
                bg=COLOR_HEX.get(color, "#DDDDDD"),
                fg=color_text_hex(color),
                activebackground=COLOR_HEX.get(color, "#DDDDDD"),
                command=lambda next_color=color: self.set_replacement_color(next_color),
            )
            button.grid(row=index // 11, column=index % 11, padx=2, pady=2)

        ttk.Button(replace_frame, text="Apply To Selected Level(s)", command=self.apply_replace).grid(
            row=0,
            column=6,
            sticky="e",
            padx=(12, 0),
        )

        ttk.Label(root, textvariable=self.status_var, anchor="w").grid(row=3, column=0, sticky="ew", pady=(8, 0))
        self.refresh_replacement_preview()

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
            messagebox.showwarning("Color Tool", "Choose a valid level folder first.")
            return

        selected_paths = {os.path.normcase(os.path.abspath(path)) for path in (select_paths or self.selected_paths())}
        self.summaries = [load_level_color_summary(path) for path in list_level_json_files(folder)]
        self.populate_level_tree(selected_paths)
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
        name_width = 150
        file_width = 110
        colors_width = max(160, canvas_width - level_width - name_width - file_width - 2)
        columns = [
            ("level", 0, level_width),
            ("name", level_width, name_width),
            ("colors", level_width + name_width, colors_width),
            ("file", level_width + name_width + colors_width, file_width),
        ]
        return columns

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
            if summary.error:
                self.draw_level_text_cell(canvas, columns[2], y, summary.error, fg)
            else:
                self.draw_level_color_cells(canvas, columns[2], y, summary.colors, is_selected)
            self.draw_level_text_cell(canvas, columns[3], y, os.path.basename(summary.path), fg)

    def draw_level_header(self, columns: List[tuple[str, int, int]], table_width: int) -> None:
        header = self.level_header
        header.delete("all")
        header.configure(scrollregion=(0, 0, table_width, 24))
        titles = {
            "level": "Level",
            "name": "Name",
            "colors": "Colors Used",
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

    def draw_level_color_cells(
        self,
        canvas: tk.Canvas,
        column: tuple[str, int, int],
        y: int,
        colors: Dict[str, ColorUsage],
        is_selected: bool,
    ) -> None:
        _key, x, width = column
        if not colors:
            canvas.create_text(x + 6, y + self.level_row_height // 2, text="No colors", anchor="w", fill="#FFFFFF" if is_selected else "#6B7280")
            return

        box_size = 18
        gap = 5
        start_x = x + 8
        max_boxes = max(1, (width - 18) // (box_size + gap))
        ordered_colors = sorted(colors, key=color_sort_key)
        visible_colors = ordered_colors[:max_boxes]
        for index, color in enumerate(visible_colors):
            bx = start_x + index * (box_size + gap)
            by = y + (self.level_row_height - box_size) // 2
            canvas.create_rectangle(
                bx,
                by,
                bx + box_size,
                by + box_size,
                fill=COLOR_HEX.get(color, "#DDDDDD"),
                outline="#FFFFFF" if is_selected else "#374151",
                width=2 if color == "White" else 1,
            )

        hidden_count = len(ordered_colors) - len(visible_colors)
        if hidden_count > 0:
            tx = start_x + len(visible_colors) * (box_size + gap) + 2
            canvas.create_text(tx, y + self.level_row_height // 2, text=f"+{hidden_count}", anchor="w", fill="#FFFFFF" if is_selected else "#374151")

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

    def on_level_selection_changed(self, _event: Optional[tk.Event] = None) -> None:
        summaries = self.selected_summaries()
        merged = merge_color_usages(summary.colors for summary in summaries if not summary.error)
        self.populate_usage_tree(merged)
        self.update_source_colors(merged)
        if summaries:
            self.status_var.set(f"Selected {len(summaries)} level(s).")

    def populate_usage_tree(self, usages: Dict[str, ColorUsage]) -> None:
        self.color_by_usage_item.clear()
        for item in self.usage_tree.get_children():
            self.usage_tree.delete(item)

        for index, color in enumerate(sorted(usages, key=color_sort_key)):
            usage = usages[color]
            tag = f"color_{index}"
            bg = COLOR_HEX.get(color, "#E5E7EB")
            fg = color_text_hex(color) if color in COLOR_HEX else "#111111"
            self.usage_tree.tag_configure(tag, background=bg, foreground=fg)
            item = self.usage_tree.insert(
                "",
                "end",
                values=(
                    color,
                    f"{usage.shooter_refs} / {usage.shooter_capacity}",
                    f"{usage.tray_refs} / {usage.tray_required}",
                    usage.total_refs,
                ),
                tags=(tag,),
            )
            self.color_by_usage_item[item] = color

        if not usages:
            self.usage_tree.insert("", "end", values=("No colors", "0 / 0", "0 / 0", 0))

    def update_source_colors(self, usages: Dict[str, ColorUsage]) -> None:
        colors = tuple(sorted(usages, key=color_sort_key))
        current = self.source_color_var.get()
        if colors and current not in colors:
            self.source_color_var.set(colors[0])
        elif not colors:
            self.source_color_var.set("")
        self.rebuild_source_color_buttons(colors, usages)

    def on_usage_color_selected(self, _event: Optional[tk.Event] = None) -> None:
        selection = self.usage_tree.selection()
        if not selection:
            return
        color = self.color_by_usage_item.get(selection[0])
        if color:
            self.set_source_color(color)

    def rebuild_source_color_buttons(self, colors: Sequence[str], usages: Dict[str, ColorUsage]) -> None:
        for child in self.source_palette.winfo_children():
            child.destroy()
        self.source_color_buttons.clear()

        if not colors:
            ttk.Label(self.source_palette, text="No colors in selected level(s)").grid(row=0, column=0, sticky="w")
            return

        for index, color in enumerate(colors):
            usage = usages[color]
            bg = COLOR_HEX.get(color, "#DDDDDD")
            button = tk.Button(
                self.source_palette,
                text=f"{color}\n{usage.total_refs}",
                width=10,
                height=2,
                bg=bg,
                fg=color_text_hex(color) if color in COLOR_HEX else "#111111",
                activebackground=bg,
                command=lambda next_color=color: self.set_source_color(next_color),
            )
            button.grid(row=index // 6, column=index % 6, padx=2, pady=2, sticky="ew")
            self.source_palette.columnconfigure(index % 6, weight=1)
            self.source_color_buttons[color] = button
        self.refresh_source_color_buttons()

    def set_source_color(self, color: str) -> None:
        self.source_color_var.set(color)
        self.refresh_source_color_buttons()

    def refresh_source_color_buttons(self) -> None:
        selected = self.source_color_var.get()
        for color, button in self.source_color_buttons.items():
            button.configure(relief="sunken" if color == selected else "raised", bd=4 if color == selected else 1)

    def set_replacement_color(self, color: str) -> None:
        self.replacement_color_var.set(color)
        self.refresh_replacement_preview()

    def refresh_replacement_preview(self) -> None:
        color = self.replacement_color_var.get()
        bg = COLOR_HEX.get(color, "#DDDDDD")
        self.replacement_preview.configure(text=color, bg=bg, fg=color_text_hex(color) if color in COLOR_HEX else "#111111")

    def selected_paths(self) -> List[str]:
        return [
            summary.path
            for summary in self.summaries
            if summary.path in self.selected_level_paths
        ]

    def selected_summaries(self) -> List[LevelColorSummary]:
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

    def apply_replace(self) -> None:
        paths = self.selected_paths()
        if not paths:
            messagebox.showwarning("Color Tool", "Select one or more levels first.")
            return

        source_color = self.source_color_var.get()
        replacement_color = self.replacement_color_var.get()
        if not source_color:
            messagebox.showwarning("Color Tool", "Choose a source color first.")
            return
        if replacement_color not in SELECTABLE_BALL_COLORS:
            messagebox.showwarning("Color Tool", "Choose a replacement color from the palette.")
            return
        if source_color == replacement_color:
            messagebox.showinfo("Color Tool", "Source and replacement colors are the same.")
            return

        target_paths = [
            summary.path
            for summary in self.selected_summaries()
            if not summary.error and source_color in summary.colors
        ]
        if not target_paths:
            messagebox.showinfo("Color Tool", f"No selected level uses {source_color}.")
            return

        if not messagebox.askyesno(
            "Replace Color",
            f"Replace all {source_color} colorId fields with {replacement_color} in "
            f"{len(target_paths)} selected level file(s)?\n\n"
            "This edits the JSON files on disk.",
        ):
            return

        changed_paths: List[str] = []
        total_changes = 0
        errors: List[str] = []
        for path in target_paths:
            try:
                with open(path, "r", encoding="utf-8") as file:
                    level = json.load(file)
                if not isinstance(level, dict):
                    errors.append(f"{os.path.basename(path)}: root JSON is not an object")
                    continue
                changes = replace_level_color(level, source_color, replacement_color)
                if changes <= 0:
                    continue
                with open(path, "w", encoding="utf-8") as file:
                    json.dump(level, file, ensure_ascii=False, indent=2)
                    file.write("\n")
                changed_paths.append(path)
                total_changes += changes
            except Exception as exc:
                errors.append(f"{os.path.basename(path)}: {exc}")

        self.scan_folder(select_paths=changed_paths or paths)
        if changed_paths and self.on_levels_changed:
            self.on_levels_changed(changed_paths)

        message = f"Updated {len(changed_paths)} level file(s), {total_changes} colorId field(s)."
        if errors:
            message += "\n\nErrors:\n" + "\n".join(errors[:8])
            if len(errors) > 8:
                message += f"\n...and {len(errors) - 8} more."
            messagebox.showwarning("Color Tool", message)
        else:
            messagebox.showinfo("Color Tool", message)
        self.status_var.set(message)


def merge_color_usages(color_maps: Iterable[Dict[str, ColorUsage]]) -> Dict[str, ColorUsage]:
    merged: Dict[str, ColorUsage] = {}
    for colors in color_maps:
        for color, usage in colors.items():
            merged.setdefault(color, ColorUsage()).add(usage)
    return merged


def color_sort_key(color: str) -> tuple[int, int, str]:
    if color in BALL_COLORS:
        return (0, BALL_COLORS.index(color), color)
    return (1, 999, color)


def _iter_level_shooters(level: Dict[str, Any]):
    grid = level.get("grid", {}) if isinstance(level, dict) else {}
    cells = grid.get("cells", []) if isinstance(grid, dict) else []
    for cell in cells or []:
        if not isinstance(cell, dict):
            continue
        entity = cell.get("entity")
        if not isinstance(entity, dict):
            continue
        entity_type = entity.get("type")
        if entity_type == "Shooter":
            shooter = entity.get("shooter")
            if isinstance(shooter, dict):
                yield shooter
        elif entity_type == "Tunnel":
            for shooter in entity.get("shooterQueue", []) or []:
                if isinstance(shooter, dict):
                    yield shooter


def _iter_level_tray_layers(level: Dict[str, Any]):
    gate_system = level.get("gateSystem", {}) if isinstance(level, dict) else {}
    gates = gate_system.get("gates", []) if isinstance(gate_system, dict) else []
    for gate in gates or []:
        if not isinstance(gate, dict):
            continue
        for tray in gate.get("trayQueue", []) or []:
            if not isinstance(tray, dict):
                continue
            for layer in tray.get("layers", []) or []:
                if isinstance(layer, dict):
                    yield layer


def _valid_color_id(value: Any) -> Optional[str]:
    color = str(value or "").strip()
    if not color or color == "None":
        return None
    return color


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


def _level_display(summary: LevelColorSummary) -> str:
    if summary.level_id is not None:
        return str(summary.level_id)
    return "?"


def _short_color_label(color: str) -> str:
    parts = []
    token = ""
    for char in color:
        if char.isupper() and token:
            parts.append(token)
            token = char
        else:
            token += char
    if token:
        parts.append(token)
    if len(parts) > 1:
        return "".join(part[0] for part in parts)[:3]
    return color[:3]

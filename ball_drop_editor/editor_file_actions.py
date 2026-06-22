from __future__ import annotations

import copy
import json
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable, Dict, List, Optional, Tuple

from .editor_paths import (
    DEFAULT_LEVEL_SAVE_DIR,
    RECENT_FOLDERS_LIMIT,
    load_recent_folders,
    save_recent_folders,
)
from .level_data import (
    delete_grid_column,
    delete_grid_row,
    detect_mechanics,
    find_cell,
    make_empty_level,
    normalize_runtime_level,
    set_grid_size,
)
from .utils import safe_int
from .validator import LevelValidator


class EditorFileActionsMixin:
    def new_level(self):
        if self.has_unsaved_changes():
            if not self._confirm_discard_unsaved_changes("creating a new level"):
                return
        elif not messagebox.askyesno("New Level", "Create a new level?"):
            return
        self.record_history()
        self.level = make_empty_level()
        self.current_file = None
        self._refresh_all()
        self._mark_current_level_saved()

    def current_level_id(self) -> int:
        return max(1, safe_int(str(self.level_var.get()), 1))

    def selected_file_level_id(self) -> int:
        return max(1, safe_int(str(self.file_level_var.get()), self.current_level_id()))

    def _mark_current_level_saved(self):
        self.sync_basic_fields()
        self.saved_level_snapshot = copy.deepcopy(self.level)
        self._update_level_save_status()

    def has_unsaved_changes(self) -> bool:
        self.sync_basic_fields()
        return self.level != self.saved_level_snapshot

    def _update_level_save_status(self):
        if self.level != self.saved_level_snapshot:
            self.level_save_status_var.set("Status: Modified")
        else:
            self.level_save_status_var.set("Status: Saved")

    def _confirm_discard_unsaved_changes(self, action: str) -> bool:
        if not self.has_unsaved_changes():
            return True
        change_log = "\n".join(f"- {item}" for item in self.unsaved_change_log())
        choice = self._ask_unsaved_changes_action(action, change_log)
        if choice == "save":
            return self._save_current_level_before_proceed()
        if choice == "discard":
            return True
        return False

    def _save_current_level_before_proceed(self) -> bool:
        if self.current_file:
            file_level_id = self._level_id_from_path(self.current_file)
            self._prepare_level_for_save(file_level_id)
            return self._save_level_to_path(self.current_file)
        return self.save_json()

    def _ask_unsaved_changes_action(self, action: str, change_log: str) -> Optional[str]:
        result: Dict[str, Optional[str]] = {"choice": None}
        dialog = tk.Toplevel(self)
        dialog.title("Unsaved Changes")
        dialog.transient(self)
        dialog.resizable(False, False)

        body = ttk.Frame(dialog, padding=12)
        body.grid(row=0, column=0, sticky="nsew")
        ttk.Label(
            body,
            text=f"Current level has unsaved changes before {action}.",
            font=("", 10, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(body, text="Unsaved changes:").grid(row=1, column=0, sticky="w", pady=(10, 3))

        log_box = tk.Text(body, width=78, height=8, wrap="word")
        log_box.grid(row=2, column=0, sticky="ew")
        log_box.insert("1.0", change_log)
        log_box.configure(state="disabled")

        buttons = ttk.Frame(body)
        buttons.grid(row=3, column=0, sticky="e", pady=(12, 0))

        def choose(choice: Optional[str]) -> None:
            result["choice"] = choice
            dialog.destroy()

        ttk.Button(buttons, text="Cancel", command=lambda: choose(None)).pack(side="right", padx=(6, 0))
        ttk.Button(buttons, text="Discard & Proceed", command=lambda: choose("discard")).pack(side="right", padx=(6, 0))
        ttk.Button(buttons, text="Save & Proceed", command=lambda: choose("save")).pack(side="right")

        dialog.protocol("WM_DELETE_WINDOW", lambda: choose(None))
        self._center_dialog(dialog)
        try:
            dialog.grab_set()
        except tk.TclError:
            pass
        dialog.wait_window()
        return result["choice"]

    def _center_dialog(self, dialog: tk.Toplevel) -> None:
        dialog.update_idletasks()
        try:
            parent_x = self.winfo_rootx()
            parent_y = self.winfo_rooty()
            parent_w = self.winfo_width()
            parent_h = self.winfo_height()
            width = dialog.winfo_width()
            height = dialog.winfo_height()
            x = parent_x + max(0, (parent_w - width) // 2)
            y = parent_y + max(0, (parent_h - height) // 2)
            dialog.geometry(f"+{x}+{y}")
        except tk.TclError:
            pass

    def close_editor(self):
        if self.has_unsaved_changes() and not self._confirm_discard_unsaved_changes("closing the tool"):
            return
        if self._validation_after_id is not None:
            self.after_cancel(self._validation_after_id)
            self._validation_after_id = None
        self.destroy()

    def unsaved_change_log(self, max_items: int = 20) -> List[str]:
        changes: List[str] = []
        self._collect_changed_paths(self.saved_level_snapshot, self.level, "", changes, max_items + 1)
        if not changes:
            return ["No detailed changes found."]
        if len(changes) > max_items:
            return changes[:max_items] + ["... more changes not shown"]
        return changes

    def _collect_changed_paths(self, before: Any, after: Any, path: str, changes: List[str], limit: int):
        if len(changes) >= limit:
            return
        label = path or "level"
        if type(before) is not type(after):
            changes.append(f"{label}: {self._format_change_value(before)} -> {self._format_change_value(after)}")
            return
        if isinstance(before, dict):
            for key in sorted(set(before) | set(after), key=str):
                child_path = f"{label}.{key}" if path else str(key)
                if key not in before:
                    changes.append(f"{child_path}: added {self._format_change_value(after[key])}")
                elif key not in after:
                    changes.append(f"{child_path}: removed {self._format_change_value(before[key])}")
                else:
                    self._collect_changed_paths(before[key], after[key], child_path, changes, limit)
                if len(changes) >= limit:
                    return
            return
        if isinstance(before, list):
            if len(before) != len(after):
                changes.append(f"{label}: list length {len(before)} -> {len(after)}")
                if len(changes) >= limit:
                    return
            for idx, (before_item, after_item) in enumerate(zip(before, after)):
                self._collect_changed_paths(before_item, after_item, f"{label}[{idx}]", changes, limit)
                if len(changes) >= limit:
                    return
            return
        if before != after:
            changes.append(f"{label}: {self._format_change_value(before)} -> {self._format_change_value(after)}")

    def _format_change_value(self, value: Any) -> str:
        if isinstance(value, dict):
            entity_type = value.get("type")
            if entity_type:
                return f"{entity_type} object"
            return f"object({len(value)} keys)"
        if isinstance(value, list):
            return f"list({len(value)})"
        text = repr(value)
        return text if len(text) <= 80 else f"{text[:77]}..."

    def _level_id_from_path(self, path: str) -> Optional[int]:
        stem = os.path.splitext(os.path.basename(path))[0]
        if not stem.isdigit():
            return None
        level_id = int(stem)
        return level_id if level_id > 0 else None

    def _refresh_level_folder_files(self):
        ids: List[int] = []
        if os.path.isdir(self.level_folder):
            try:
                names = os.listdir(self.level_folder)
            except OSError:
                names = []
            for name in names:
                stem, ext = os.path.splitext(name)
                if ext.lower() == ".json" and stem.isdigit():
                    ids.append(int(stem))
        self.level_file_ids = sorted(set(ids))
        self._update_level_file_status()

    def _update_level_file_status(self):
        self._refresh_folder_combobox()
        loaded = f"Loaded: {os.path.basename(self.current_file)}" if self.current_file else "No file loaded"
        if self.level_file_ids:
            count = len(self.level_file_ids)
            files = f"{count} numeric JSON file(s) in folder"
        else:
            files = "0 numeric JSON files in folder"
        self.level_file_status_var.set(f"{loaded}\n{files}")

    def choose_level_folder(self):
        initial_dir = self.level_folder if os.path.isdir(self.level_folder) else DEFAULT_LEVEL_SAVE_DIR
        path = filedialog.askdirectory(initialdir=initial_dir, title="Choose folder with level JSON files")
        if not path:
            return
        self._register_folder(path, make_active=True)
        self.current_file = None
        self._refresh_level_folder_files()

    def _init_folder_history(self) -> None:
        self.level_folders = load_recent_folders()
        active = os.path.abspath(self.level_folder)
        if not any(self._normalized_path(folder) == self._normalized_path(active) for folder in self.level_folders):
            self.level_folders.insert(0, active)
        del self.level_folders[RECENT_FOLDERS_LIMIT:]

    def _register_folder(self, path: str, make_active: bool = False) -> None:
        if not path:
            return
        path = os.path.abspath(path)
        norm = self._normalized_path(path)
        self.level_folders = [folder for folder in self.level_folders if self._normalized_path(folder) != norm]
        self.level_folders.insert(0, path)
        del self.level_folders[RECENT_FOLDERS_LIMIT:]
        save_recent_folders(self.level_folders)
        if make_active:
            self.level_folder = path
        self._refresh_folder_combobox()

    def _folder_display_label(self, path: str, all_paths: List[str]) -> str:
        base = os.path.basename(os.path.normpath(path)) or path
        collisions = [
            other for other in all_paths
            if (os.path.basename(os.path.normpath(other)) or other) == base
        ]
        if len(collisions) > 1:
            parent = os.path.basename(os.path.dirname(os.path.normpath(path)))
            if parent:
                return f"{parent}/{base}"
        return base

    def _refresh_folder_combobox(self) -> None:
        if not hasattr(self, "folder_combo"):
            return
        paths = list(self.level_folders)
        self._folder_display_to_path = {}
        displays: List[str] = []
        for folder in paths:
            label = self._folder_display_label(folder, paths)
            self._folder_display_to_path[label] = folder
            displays.append(label)
        self.folder_combo["values"] = displays
        self.active_folder_var.set(self._folder_display_label(self.level_folder, paths))

    def _on_folder_combo_selected(self, event=None) -> None:
        path = getattr(self, "_folder_display_to_path", {}).get(self.active_folder_var.get())
        if not path or self._normalized_path(path) == self._normalized_path(self.level_folder):
            return
        self.level_folder = path
        self.current_file = None
        self._refresh_level_folder_files()

    def load_selected_level(self):
        level_id = self.selected_file_level_id()
        self._load_level_by_id(level_id)

    def _load_level_by_id(self, level_id: int):
        self._refresh_level_folder_files()
        path = os.path.join(self.level_folder, f"{level_id}.json")
        if not os.path.isfile(path):
            messagebox.showerror("Load Error", f"Cannot find {level_id}.json in:\n{self.level_folder}")
            return False
        return self._load_level_file(path, level_id=level_id)

    def _neighbor_level_id(self, direction: int) -> Optional[int]:
        self._refresh_level_folder_files()
        if not self.level_file_ids:
            return None
        current = self.selected_file_level_id()
        if current in self.level_file_ids:
            next_index = self.level_file_ids.index(current) + direction
            if 0 <= next_index < len(self.level_file_ids):
                return self.level_file_ids[next_index]
            return None
        if direction < 0:
            before = [level_id for level_id in self.level_file_ids if level_id < current]
            return before[-1] if before else None
        after = [level_id for level_id in self.level_file_ids if level_id > current]
        return after[0] if after else None

    def load_previous_level(self):
        level_id = self._neighbor_level_id(-1)
        if level_id is None:
            if not self.level_file_ids:
                messagebox.showwarning("Load", "Choose a folder with numeric JSON files first.")
                return
            messagebox.showinfo("Load", "Already at the first level in this folder.")
            return
        self._load_level_by_id(level_id)

    def load_next_level(self):
        level_id = self._neighbor_level_id(1)
        if level_id is None:
            if not self.level_file_ids:
                messagebox.showwarning("Load", "Choose a folder with numeric JSON files first.")
                return
            messagebox.showinfo("Load", "Already at the last level in this folder.")
            return
        self._load_level_by_id(level_id)

    def _load_level_file(self, path: str, level_id: Optional[int] = None) -> bool:
        if not self._confirm_discard_unsaved_changes("loading another level"):
            return False
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                loaded_level = json.load(f)
            normalize_runtime_level(loaded_level)
            file_level_id = level_id if level_id is not None else self._level_id_from_path(path)
            if file_level_id is not None:
                loaded_level["level"] = file_level_id
            self.level = loaded_level
            self.current_file = path
            self._register_folder(os.path.dirname(path), make_active=True)
            self.undo_stack.clear()
            self.redo_stack.clear()
            self._refresh_all()
            self._mark_current_level_saved()
            return True
        except Exception as exc:
            messagebox.showerror("Load Error", str(exc))
            return False

    def open_json(self):
        initial_dir = self.level_folder if os.path.isdir(self.level_folder) else DEFAULT_LEVEL_SAVE_DIR
        path = filedialog.askopenfilename(
            initialdir=initial_dir,
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")]
        )
        if not path:
            return
        self._load_level_file(path)

    def save_json(self) -> bool:
        level_id = self.selected_file_level_id()
        folder = self.level_folder or DEFAULT_LEVEL_SAVE_DIR
        path = os.path.join(folder, f"{level_id}.json")
        self._prepare_level_for_save(level_id)
        return self._save_level_to_path(path)

    def _prepare_level_for_save(self, level_id: Optional[int] = None) -> None:
        if level_id is not None:
            self.level_var.set(str(level_id))
            self.file_level_var.set(str(level_id))
        self.sync_basic_fields()
        self.merge_detected_mechanics()
        normalize_runtime_level(self.level)

    def _save_level_to_path(self, path: str, switch_active_folder: bool = True) -> bool:
        path = os.path.abspath(path)
        if not self._confirm_validation_before_save():
            return False
        if not self._confirm_overwrite_before_save(path):
            return False

        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.level, f, ensure_ascii=False, indent=2)
            self.current_file = path
            self._register_folder(os.path.dirname(path), make_active=switch_active_folder)
            self._refresh_level_folder_files()
            self._mark_current_level_saved()
            messagebox.showinfo("Save", f"Saved:\n{path}")
            return True
        except Exception as exc:
            messagebox.showerror("Save Error", str(exc))
            return False

    def _confirm_validation_before_save(self) -> bool:
        errors, warnings = LevelValidator().validate(self.level)
        self.render_validation_results(errors, warnings)
        actionable_warnings = [
            warning
            for warning in warnings
            if not warning.lstrip().startswith("OK:")
        ]
        if not errors and not actionable_warnings:
            return True

        items = [
            *(f"ERROR: {error}" for error in errors),
            *(f"WARNING: {warning}" for warning in actionable_warnings),
        ]
        shown = items[:12]
        if len(items) > len(shown):
            shown.append(f"... and {len(items) - len(shown)} more.")
        details = "\n".join(f"- {item}" for item in shown)
        return messagebox.askyesno(
            "Level Validation",
            "This level has validation issues:\n\n"
            f"{details}\n\n"
            "Save anyway?",
        )

    def _confirm_overwrite_before_save(self, path: str) -> bool:
        if not os.path.isfile(path):
            return True
        if self.current_file and self._normalized_path(path) == self._normalized_path(self.current_file):
            return True
        return messagebox.askyesno(
            "Overwrite Level",
            f"This level file already exists:\n{path}\n\nOverwrite it?",
        )

    def _normalized_path(self, path: str) -> str:
        return os.path.normcase(os.path.abspath(path))

    def default_level_filename(self) -> str:
        level_id = self.selected_file_level_id()
        return f"{level_id}.json"

    def save_json_as(self):
        initial_dir = self.level_folder if self.level_folder else DEFAULT_LEVEL_SAVE_DIR
        if not os.path.isdir(initial_dir):
            os.makedirs(initial_dir, exist_ok=True)
        path = filedialog.asksaveasfilename(
            initialdir=initial_dir,
            initialfile=self.default_level_filename(),
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")],
            confirmoverwrite=False,
        )
        if not path:
            return
        file_level_id = self._level_id_from_path(path)
        self._prepare_level_for_save(file_level_id)
        self._save_level_to_path(path, switch_active_folder=False)

    def record_history(self):
        self.undo_stack.append(copy.deepcopy(self.level))
        if len(self.undo_stack) > 80:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def undo(self):
        if not self.undo_stack:
            return
        self.redo_stack.append(copy.deepcopy(self.level))
        self.level = self.undo_stack.pop()
        self._refresh_all()

    def redo(self):
        if not self.redo_stack:
            return
        self.undo_stack.append(copy.deepcopy(self.level))
        self.level = self.redo_stack.pop()
        self._refresh_all()

    def copy_selected_cell(self):
        if not self.selected_cell:
            return
        entity = find_cell(self.level, *self.selected_cell).get("entity")
        self.clipboard_entity = copy.deepcopy(entity)

    def paste_selected_cell(self):
        if not self.selected_cell:
            return
        self.record_history()
        find_cell(self.level, *self.selected_cell)["entity"] = copy.deepcopy(self.clipboard_entity)
        self._update_selected_label()
        self._refresh_grid_button_states()
        self.refresh_json_preview()

    def open_level_tester(self):
        from .level_tester_app import open_level_tester

        return self._open_or_focus_tool_window(
            "_level_tester_window",
            lambda: open_level_tester(self, self.level_folder),
        )

    def open_level_generator(self):
        from .level_generator_window import open_level_generator

        return self._open_or_focus_tool_window(
            "_level_generator_window",
            lambda: open_level_generator(self),
        )

    def open_color_replace_tool(self):
        from .color_replace_tool import open_color_replace_tool

        return self._open_or_focus_tool_window(
            "_color_replace_window",
            lambda: open_color_replace_tool(
                self,
                self.level_folder,
                self.on_color_replace_tool_changed,
            ),
        )

    def open_difficulty_tool(self):
        from .difficulty_tool import open_difficulty_tool

        return self._open_or_focus_tool_window(
            "_difficulty_tool_window",
            lambda: open_difficulty_tool(
                self,
                self.level_folder,
                self.on_difficulty_tool_changed,
            ),
        )

    def _open_or_focus_tool_window(
        self,
        attribute_name: str,
        factory: Callable[[], tk.Toplevel],
    ) -> tk.Toplevel:
        window = getattr(self, attribute_name, None)
        if self._tool_window_exists(window):
            self._bring_tool_window_to_front(window)
            return window

        window = factory()
        setattr(self, attribute_name, window)
        window.bind(
            "<Destroy>",
            lambda event, name=attribute_name, target=window: self._on_tool_window_destroyed(
                name,
                target,
                event.widget,
            ),
            add="+",
        )
        self._bring_tool_window_to_front(window)
        return window

    def _tool_window_exists(self, window: Optional[tk.Toplevel]) -> bool:
        if window is None:
            return False
        try:
            return bool(window.winfo_exists())
        except tk.TclError:
            return False

    def _bring_tool_window_to_front(self, window: tk.Toplevel) -> None:
        try:
            window.deiconify()
            window.lift()
            window.attributes("-topmost", True)
            window.focus_force()
            window.after_idle(lambda target=window: self._release_tool_window_topmost(target))
        except tk.TclError:
            pass

    def _release_tool_window_topmost(self, window: tk.Toplevel) -> None:
        try:
            if window.winfo_exists():
                window.attributes("-topmost", False)
        except tk.TclError:
            pass

    def _on_tool_window_destroyed(
        self,
        attribute_name: str,
        window: tk.Toplevel,
        destroyed_widget: tk.Misc,
    ) -> None:
        if destroyed_widget is window and getattr(self, attribute_name, None) is window:
            setattr(self, attribute_name, None)

    def on_color_replace_tool_changed(self, changed_paths: List[str]):
        if not self.current_file:
            self._refresh_level_folder_files()
            return

        current_path = os.path.normcase(os.path.abspath(self.current_file))
        changed = {os.path.normcase(os.path.abspath(path)) for path in changed_paths}
        if current_path not in changed:
            self._refresh_level_folder_files()
            return

        if self.has_unsaved_changes():
            messagebox.showwarning(
                "Color Tool",
                "The currently loaded level was changed on disk, but this editor still has unsaved changes.\n\n"
                "Save or reload the current level before saving again, otherwise the disk color change may be overwritten.",
            )
            self._refresh_level_folder_files()
            return

        self._load_level_file(self.current_file, level_id=self._level_id_from_path(self.current_file))

    def on_difficulty_tool_changed(self, changed_paths: List[str]):
        if not self.current_file:
            self._refresh_level_folder_files()
            return

        current_path = os.path.normcase(os.path.abspath(self.current_file))
        changed = {os.path.normcase(os.path.abspath(path)) for path in changed_paths}
        if current_path not in changed:
            self._refresh_level_folder_files()
            return

        if self.has_unsaved_changes():
            messagebox.showwarning(
                "Difficulty Tool",
                "The currently loaded level was changed on disk, but this editor still has unsaved changes.\n\n"
                "Save or reload the current level before saving again, otherwise the disk difficulty change may be overwritten.",
            )
            self._refresh_level_folder_files()
            return

        self._load_level_file(self.current_file, level_id=self._level_id_from_path(self.current_file))

    def apply_generated_level(self, level: Dict[str, Any]):
        self.record_history()
        normalize_runtime_level(level)
        self.level = level
        self.current_file = None
        self.selected_cell = None
        self.selected_grid_cells.clear()
        self.selected_tray_index = None
        self.selected_trays.clear()
        self.selected_gate_index = 0
        self.selected_gate_indices = {0}
        self.selected_layer_index = 0
        self._refresh_all()

    def show_info(self):
        messagebox.showinfo(
            "Level Editor Info",
            "Grid\n"
            "- Bật Paint on click để click một lần là fill ô theo config bên trái.\n"
            "- Tắt Paint on click nếu chỉ muốn click để chọn ô.\n"
            "- Right click clears xóa ô bằng chuột phải; double-click chuột phải vẫn xóa ô.\n"
            "- Double-click chuột trái luôn fill ô theo config hiện tại.\n"
            "- Kéo thả một ô shooter sang ô khác để hoán đổi vị trí.\n"
            "- Multi cell select cho phép Ctrl/Shift-click chọn nhiều cell rồi Paint/Clear Selected theo nhóm.\n"
            "- Copy / Paste are in Grid Tools and use the selected cell.\n\n"
            "Gate / Tray\n"
            "- Click vào bất kỳ vị trí nào trong cột gate để chọn gate; click tray để chọn tray.\n"
            "- Ctrl/Shift-click để chọn nhiều gate hoặc nhiều tray cùng lúc.\n"
            "- + Tray, + Layer, Up, Down, Delete thao tác trên selection hiện tại.\n"
            "- + Layer mặc định bị khóa; tick Enable +Layer trước khi thêm layer mới.\n"
            "- Gate Left / Gate Right đổi vị trí các gate đang chọn.\n"
            "- Kéo thả tray lên tray khác để hoán đổi, kể cả khác gate.\n"
            "- Max Visible Tray là số tray game nhìn thấy; editor vẫn scroll để thấy tray 5, 6, 7...\n\n"
            "Validate\n"
            "- Panel bên phải luôn hiển thị lỗi.\n"
            "- Color Balance hiển thị Shooter / Tray / Delta theo từng màu.\n"
            "- Auto check tự validate sau khi level đổi; tắt đi nếu muốn bấm Check Now thủ công.\n"
            "- Rule màu giống Unity: thiếu capacity là error, dư quá nhiều là warning, kèm delta và gợi ý sửa.\n\n"
            "History\n"
            "- Undo / Redo lưu các thay đổi level gần nhất.",
        )

    def sync_basic_fields(self):
        self.level["gameMode"] = self.game_mode_var.get()
        self.level["difficulty"] = self.difficulty_var.get()
        self.level["level"] = self.current_level_id()
        self.level["category"] = safe_int(str(self.category_var.get()), 0)
        self.level["time"] = safe_int(str(self.time_var.get()), 60)
        self.level["levelName"] = self.level_name_var.get().strip() or "New Level"
        self.level["mechanics"] = [m.strip() for m in self.mechanics_var.get().split(",") if m.strip()]
        self.level.setdefault("gateSystem", {})["gateCount"] = safe_int(str(self.gate_count_var.get()), 4)
        self.level.setdefault("gateSystem", {})["maxVisibleTrayPerGate"] = safe_int(str(self.max_visible_var.get()), 4)
        normalize_runtime_level(self.level)
        self.mechanics_var.set(", ".join(self.level.get("mechanics", []) or []))

    def auto_detect_mechanics(self):
        detected = detect_mechanics(self.level)
        self.mechanics_var.set(", ".join(detected))
        self.refresh_json_preview()

    def auto_detect_mechanics_for_folder(self):
        if self.has_unsaved_changes():
            if not self._confirm_discard_unsaved_changes("auto-detecting mechanics for the folder"):
                return

        self._refresh_level_folder_files()
        if not os.path.isdir(self.level_folder):
            messagebox.showwarning("Auto-detect Mechanics", "Choose a folder with level JSON files first.")
            return

        paths = [
            os.path.join(self.level_folder, f"{level_id}.json")
            for level_id in self.level_file_ids
        ]
        if not paths:
            messagebox.showwarning("Auto-detect Mechanics", "No numeric JSON level files found in this folder.")
            return

        updated = 0
        unchanged = 0
        failures: List[str] = []
        current_path = self._normalized_path(self.current_file) if self.current_file else None
        current_detected: Optional[List[str]] = None

        for path in paths:
            changed, detected, error = self._auto_detect_mechanics_for_level_file(path)
            if error is not None:
                failures.append(f"{os.path.basename(path)}: {error}")
                continue
            if changed:
                updated += 1
            else:
                unchanged += 1
            if current_path and self._normalized_path(path) == current_path:
                current_detected = detected

        if current_detected is not None:
            self.level["mechanics"] = current_detected
            self.mechanics_var.set(", ".join(current_detected))
            self._mark_current_level_saved()
            self.refresh_json_preview()

        self._refresh_level_folder_files()
        summary = (
            f"Processed {len(paths)} file(s).\n"
            f"Updated: {updated}\n"
            f"Unchanged: {unchanged}"
        )
        if failures:
            shown = "\n".join(failures[:8])
            extra = "" if len(failures) <= 8 else f"\n... and {len(failures) - 8} more."
            messagebox.showwarning(
                "Auto-detect Mechanics",
                f"{summary}\nFailed: {len(failures)}\n\n{shown}{extra}",
            )
        else:
            messagebox.showinfo("Auto-detect Mechanics", summary)

    def _auto_detect_mechanics_for_level_file(self, path: str) -> Tuple[bool, List[str], Optional[str]]:
        try:
            with open(path, "r", encoding="utf-8-sig") as file:
                level = json.load(file)
            if not isinstance(level, dict):
                return False, [], "JSON root is not an object"
            detected = detect_mechanics(level)
            if level.get("mechanics", []) == detected:
                return False, detected, None
            level["mechanics"] = detected
            with open(path, "w", encoding="utf-8") as file:
                json.dump(level, file, ensure_ascii=False, indent=2)
            return True, detected, None
        except Exception as exc:
            return False, [], str(exc)

    def merge_detected_mechanics(self):
        authored = self.level.get("mechanics", []) or []
        detected = detect_mechanics(self.level)
        merged = list(dict.fromkeys([*authored, *detected]))
        self.level["mechanics"] = merged
        normalize_runtime_level(self.level)
        self.mechanics_var.set(", ".join(self.level.get("mechanics", []) or []))

    def resize_grid(self):
        rows = max(1, self.rows_var.get())
        cols = max(1, self.cols_var.get())
        current_grid = self.level.get("grid", {})
        current_rows = current_grid.get("rows", 4)
        current_cols = current_grid.get("columns", 4)
        risky_cells = []
        for cell in current_grid.get("cells", []):
            row = cell.get("row", 0)
            col = cell.get("column", 0)
            entity = cell.get("entity")
            if row >= rows or col >= cols:
                entity_type = entity.get("type") if entity else None
                if entity_type in {"Shooter", "Tunnel"}:
                    risky_cells.append((row, col, entity_type))

        if risky_cells:
            examples = ", ".join(f"({row},{col}) {entity_type}" for row, col, entity_type in risky_cells[:8])
            extra = "" if len(risky_cells) <= 8 else f"\n...and {len(risky_cells) - 8} more."
            if not messagebox.askyesno(
                "Resize Grid",
                "This resize will remove Shooter/Tunnel cells outside the new grid.\n\n"
                f"New size: {rows} x {cols}\n"
                f"Cells affected: {len(risky_cells)}\n"
                f"{examples}{extra}\n\nContinue?"
            ):
                self.rows_var.set(current_rows)
                self.cols_var.set(current_cols)
                return

        self.record_history()
        set_grid_size(self.level, rows, cols)
        if self.selected_cell:
            selected_row, selected_col = self.selected_cell
            if selected_row >= rows or selected_col >= cols:
                self.selected_cell = None
        self.selected_grid_cells = {
            (row, col)
            for row, col in self.selected_grid_cells
            if row < rows and col < cols
        }
        self._refresh_grid_buttons()
        self._update_selected_label()
        self.refresh_json_preview()

    def delete_selected_grid_row(self):
        if not self.selected_cell:
            messagebox.showwarning("Delete Row", "Select a grid cell first.")
            return
        row, _ = self.selected_cell
        grid = self.level.get("grid", {})
        current_rows = grid.get("rows", 4)
        current_cols = grid.get("columns", 4)
        if current_rows <= 1:
            messagebox.showwarning("Delete Row", "The grid must keep at least one row.")
            return
        if not self._confirm_delete_grid_line("row", row):
            return

        self.record_history()
        delete_grid_row(self.level, row)
        self.rows_var.set(current_rows - 1)
        self.cols_var.set(current_cols)
        self._shift_selection_after_grid_line_delete("row", row)
        self._refresh_grid_buttons()
        self._update_selected_label()
        self.refresh_json_preview()

    def delete_selected_grid_column(self):
        if not self.selected_cell:
            messagebox.showwarning("Delete Column", "Select a grid cell first.")
            return
        _, col = self.selected_cell
        grid = self.level.get("grid", {})
        current_rows = grid.get("rows", 4)
        current_cols = grid.get("columns", 4)
        if current_cols <= 1:
            messagebox.showwarning("Delete Column", "The grid must keep at least one column.")
            return
        if not self._confirm_delete_grid_line("column", col):
            return

        self.record_history()
        delete_grid_column(self.level, col)
        self.rows_var.set(current_rows)
        self.cols_var.set(current_cols - 1)
        self._shift_selection_after_grid_line_delete("column", col)
        self._refresh_grid_buttons()
        self._update_selected_label()
        self.refresh_json_preview()

    def _confirm_delete_grid_line(self, axis: str, index: int) -> bool:
        axis_label = "row" if axis == "row" else "column"
        affected = []
        for cell in self.level.get("grid", {}).get("cells", []):
            row = cell.get("row", 0)
            col = cell.get("column", 0)
            if (axis == "row" and row != index) or (axis == "column" and col != index):
                continue
            entity = cell.get("entity")
            if entity:
                affected.append((row, col, entity.get("type", "Unknown")))

        if not affected:
            return True

        examples = ", ".join(f"({row},{col}) {entity_type}" for row, col, entity_type in affected[:8])
        extra = "" if len(affected) <= 8 else f"\n...and {len(affected) - 8} more."
        return messagebox.askyesno(
            f"Delete {axis_label.title()}",
            f"This will remove {axis_label} {index} and shift the grid.\n\n"
            f"Non-empty cells affected: {len(affected)}\n"
            f"{examples}{extra}\n\nContinue?"
        )

    def _shift_selection_after_grid_line_delete(self, axis: str, index: int):
        grid = self.level.get("grid", {})
        rows = grid.get("rows", 1)
        cols = grid.get("columns", 1)

        def shifted(cell):
            if cell is None:
                return None
            row, col = cell
            if axis == "row":
                if row == index:
                    return None
                row = row - 1 if row > index else row
            else:
                if col == index:
                    return None
                col = col - 1 if col > index else col
            if 0 <= row < rows and 0 <= col < cols:
                return row, col
            return None

        self.selected_cell = shifted(self.selected_cell)
        self.selected_grid_cells = {
            next_cell
            for cell in self.selected_grid_cells
            for next_cell in [shifted(cell)]
            if next_cell is not None
        }
        if self.selected_cell is None and self.selected_grid_cells:
            self.selected_cell = sorted(self.selected_grid_cells)[0]

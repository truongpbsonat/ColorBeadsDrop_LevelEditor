from __future__ import annotations

import copy
import tkinter as tk
from typing import Any, Dict, List, Optional, Set, Tuple

from .editor_cells import EditorCellsMixin
from .editor_file_actions import EditorFileActionsMixin
from .editor_gates import EditorGateMixin
from .editor_grid import EditorGridMixin
from .editor_obstacles_groups import EditorObstacleGroupMixin
from .editor_paths import DEFAULT_LEVEL_SAVE_DIR
from .editor_state import EditorStateMixin
from .editor_ui import EditorUiMixin
from .editor_validation import EditorValidationMixin
from .level_data import make_empty_level


class BallDropLevelEditor(
    EditorStateMixin,
    EditorUiMixin,
    EditorFileActionsMixin,
    EditorGateMixin,
    EditorObstacleGroupMixin,
    EditorCellsMixin,
    EditorValidationMixin,
    EditorGridMixin,
    tk.Tk,
):
    def __init__(self):
        super().__init__()
        self.title("BallDropParty Level Editor - Python GUI")
        self.geometry("1600x920")
        self.minsize(1360, 780)
        try:
            self.state("zoomed")
        except tk.TclError:
            pass

        self.level = make_empty_level()
        self.current_file: Optional[str] = None
        self.saved_level_snapshot = copy.deepcopy(self.level)
        self.level_folder = DEFAULT_LEVEL_SAVE_DIR
        self.level_file_ids: List[int] = []
        self.selected_cell: Optional[Tuple[int, int]] = None
        self.selected_grid_cells: Set[Tuple[int, int]] = set()
        self.grid_buttons: Dict[Tuple[int, int], tk.Button] = {}
        self.grid_button_frames: Dict[Tuple[int, int], tk.Frame] = {}
        self.gate_hit_areas: List[Dict[str, Any]] = []
        self.selected_gate_index = 0
        self.selected_gate_indices: Set[int] = {0}
        self.selected_tray_index: Optional[int] = None
        self.selected_trays: Set[Tuple[int, int]] = set()
        self.selected_layer_index = 0
        self._validation_after_id: Optional[str] = None
        self.undo_stack: List[Dict[str, Any]] = []
        self.redo_stack: List[Dict[str, Any]] = []
        self.clipboard_entity: Optional[Dict[str, Any]] = None
        self.grid_drag_cell: Optional[Tuple[int, int]] = None
        self.gate_drag_source: Optional[Tuple[int, int]] = None
        self.icon_images: Dict[str, tk.PhotoImage] = {}
        self.choice_button_groups: Dict[str, List[Dict[str, Any]]] = {}
        self.tunnel_queue_buttons: Dict[int, tk.Button] = {}
        self.tunnel_queue_button_frames: Dict[int, tk.Frame] = {}
        self.tunnel_queue_drag_index: Optional[int] = None
        self.selected_obstacle_index: Optional[int] = None
        self.selected_group_index: Optional[int] = None
        self.obstacle_custom_cells: Set[Tuple[int, int]] = set()
        self._active_color_target = "cell"
        self._syncing_cell_editor = False
        self._syncing_gate_direct_controls = False
        self._level_tester_window: Optional[tk.Toplevel] = None
        self._level_generator_window: Optional[tk.Toplevel] = None
        self._color_replace_window: Optional[tk.Toplevel] = None
        self._difficulty_tool_window: Optional[tk.Toplevel] = None

        self._init_level_meta_vars()
        self._load_icon_images()
        self._build_ui()
        self._refresh_all()
        self._mark_current_level_saved()
        self.protocol("WM_DELETE_WINDOW", self.close_editor)

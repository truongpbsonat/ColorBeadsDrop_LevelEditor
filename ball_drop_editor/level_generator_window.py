from __future__ import annotations

import queue
import threading
import tkinter as tk
from typing import Any, Dict, List, Optional

from .level_generator import CandidateResult
from .level_generator_window_actions import LevelGeneratorWindowActionsMixin
from .level_generator_window_constants import EMPTY_CELL_STRATEGIES
from .level_generator_window_phases import LevelGeneratorWindowPhaseMixin
from .level_generator_window_render import LevelGeneratorWindowRenderMixin
from .level_generator_window_sources import LevelGeneratorWindowSourceMixin
from .level_generator_window_state import LevelGeneratorWindowStateMixin
from .level_generator_window_ui import LevelGeneratorWindowUiMixin
from .level_tester_score import SolverScoreResult


class LevelGeneratorWindow(
    LevelGeneratorWindowStateMixin,
    LevelGeneratorWindowUiMixin,
    LevelGeneratorWindowPhaseMixin,
    LevelGeneratorWindowSourceMixin,
    LevelGeneratorWindowActionsMixin,
    LevelGeneratorWindowRenderMixin,
    tk.Toplevel,
):
    def __init__(self, master=None):
        super().__init__(master)
        self.title("BallDropParty Level Generator")
        self.geometry("1280x820")
        self.minsize(1080, 680)

        self.result_queue: queue.Queue = queue.Queue()
        self.worker: Optional[threading.Thread] = None
        self.cancel_event = threading.Event()
        self.preview_candidate: Optional[CandidateResult] = None
        self.template_level: Optional[Dict[str, Any]] = None
        self.template_levels: List[Dict[str, Any]] = []
        self.reference_level: Optional[Dict[str, Any]] = None
        self.reference_curve_targets: List[float] = []
        self.reference_score: Optional[SolverScoreResult] = None

        self._init_vars()
        self._build_ui()
        self._load_default_phases()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(100, self._poll_results)


def open_level_generator(master=None) -> LevelGeneratorWindow:
    window = LevelGeneratorWindow(master)
    window.focus()
    return window

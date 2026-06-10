from __future__ import annotations

import copy
import random
from typing import List

from .level_generator_candidate import DifficultyCurveCandidateMixin
from .level_generator_models import GateLayoutMetrics, GeneratorConfig
from .level_generator_scoring import DifficultyCurveScoringMixin
from .level_tester_score import SolverScoreAdapter
from .validator import LevelValidator


class DifficultyCurveGenerator(
    DifficultyCurveScoringMixin,
    DifficultyCurveCandidateMixin,
):
    def __init__(self, config: GeneratorConfig):
        self.config = copy.deepcopy(config)
        self.rng = random.Random(config.seed)
        self.validator = LevelValidator()
        self.solver = SolverScoreAdapter(time_budget=config.solver_budget)
        self._candidate_notes: List[str] = []
        self._gate_layout_metrics = GateLayoutMetrics()

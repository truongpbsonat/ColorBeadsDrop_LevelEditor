from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

from .level_generator_analysis import _resample_values, structural_difference
from .level_generator_models import CandidateResult
from .level_tester_score import SolverScoreResult


class DifficultyCurveScoringMixin:
    def _note(self, message: str) -> None:
        if message not in self._candidate_notes:
            self._candidate_notes.append(message)

    def _note_final_counts(self, level: Dict[str, Any]) -> None:
        cells = level.get("grid", {}).get("cells", []) or []
        shooters = 0
        walls = 0
        tunnels = 0
        tunnel_queue = 0
        empty = 0
        for cell in cells:
            entity = cell.get("entity")
            if not entity:
                empty += 1
                continue
            entity_type = entity.get("type")
            if entity_type == "Shooter":
                shooters += 1
            elif entity_type == "Wall":
                walls += 1
            elif entity_type == "Tunnel":
                tunnels += 1
                tunnel_queue += len(entity.get("shooterQueue", []) or [])
        rows = level.get("grid", {}).get("rows", 0)
        cols = level.get("grid", {}).get("columns", 0)
        self._note(
            f"Final generated counts: grid={rows}x{cols}, shooters={shooters}, walls={walls}, "
            f"tunnels={tunnels}, tunnelQueue={tunnel_queue}, empty={empty}."
        )

    def _reference_structural_difference(self, candidate_level: Dict[str, Any]) -> float:
        if not self.config.reference_level:
            return 0.0
        return structural_difference(self.config.reference_level, candidate_level)

    def _reference_curve_error(self, score: SolverScoreResult) -> float:
        targets = [float(value) for value in self.config.reference_curve_targets if value is not None]
        if not targets:
            return 0.0
        if score.status != "PASS" or not score.per_click_scores:
            return 9999.0
        actual = [float(item.score) for item in score.per_click_scores]
        sampled = _resample_values(actual, len(targets))
        return sum(abs(left - right) for left, right in zip(sampled, targets)) / max(1, len(targets))

    def generate_best(self, progress=None, cancel_check=None) -> CandidateResult:
        best_pass: Optional[CandidateResult] = None
        best_any: Optional[CandidateResult] = None
        attempts = max(1, self.config.candidate_attempts)
        for attempt in range(1, attempts + 1):
            if cancel_check and cancel_check():
                break
            level = self._build_candidate(attempt)
            notes = list(self._candidate_notes)
            structural_difference = self._reference_structural_difference(level)
            errors, warnings = self.validator.validate(level)
            if errors:
                score = SolverScoreResult(status="INVALID", message="Validator errors.")
                candidate = CandidateResult(
                    level,
                    score,
                    errors,
                    warnings,
                    9999.0,
                    attempt,
                    notes,
                    structural_difference,
                    9999.0 if self.config.reference_curve_targets else 0.0,
                )
            else:
                score = self.solver.score_level(
                    level,
                    phases=[phase.to_score_phase() for phase in self.config.normalized_phases()],
                    cancel_check=cancel_check,
                )
                reference_curve_error = self._reference_curve_error(score)
                target_error = self._target_error(score)
                if self.config.reference_curve_targets and score.status == "PASS":
                    target_error = (target_error + reference_curve_error) / 2.0
                candidate_notes = list(notes)
                if self.config.reference_level:
                    candidate_notes.append(
                        f"Reference difference={structural_difference * 100:.1f}%, "
                        f"curve error={reference_curve_error:.1f}."
                    )
                    if (
                        score.status == "PASS"
                        and structural_difference < max(0.0, float(self.config.reference_min_difference))
                    ):
                        candidate_notes.append(
                            f"Reference candidate rejected: difference "
                            f"{structural_difference * 100:.1f}% < "
                            f"{float(self.config.reference_min_difference) * 100:.1f}%."
                        )
                        score = copy.deepcopy(score)
                        score.status = "FAIL"
                        score.message = "Reference difference below threshold."
                candidate = CandidateResult(
                    level,
                    score,
                    errors,
                    warnings,
                    target_error,
                    attempt,
                    candidate_notes,
                    structural_difference,
                    reference_curve_error,
                )

            if best_any is None or candidate.target_error < best_any.target_error:
                best_any = candidate
            pass_meets_reference = (
                not self.config.reference_level
                or candidate.structural_difference >= max(0.0, float(self.config.reference_min_difference))
            )
            if candidate.score.status == "PASS" and pass_meets_reference:
                if best_pass is None or candidate.target_error < best_pass.target_error:
                    best_pass = candidate
            if progress:
                progress(attempt, attempts, candidate, best_pass or best_any)

        if best_pass is not None:
            return best_pass
        if best_any is not None:
            return best_any
        raise RuntimeError("Generator was cancelled before creating any candidate.")

    def _target_error(self, score: SolverScoreResult) -> float:
        if score.status != "PASS":
            return 9999.0
        if not score.phase_scores:
            return abs(score.overall_score - self._overall_target())
        return sum(abs(phase.delta) for phase in score.phase_scores) / max(1, len(score.phase_scores))

    def _overall_target(self) -> float:
        phases = self.config.normalized_phases()
        return sum(phase.target_score for phase in phases) / max(1, len(phases))

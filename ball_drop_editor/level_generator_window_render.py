from __future__ import annotations

import time
from typing import Optional

from .level_generator import CandidateResult


class LevelGeneratorWindowRenderMixin:
    def clear_log(self) -> None:
        self.log_text.delete("1.0", "end")

    def _progress(
        self,
        attempt: int,
        total: int,
        candidate: CandidateResult,
        best: Optional[CandidateResult],
    ) -> None:
        best_label = best.score.status if best else "-"
        reference_extra = ""
        if candidate.structural_difference or candidate.reference_curve_error:
            reference_extra = (
                f", ref diff {candidate.structural_difference * 100:.1f}%, "
                f"curve {candidate.reference_curve_error:.1f}"
            )
        self.result_queue.put(
            (
                "log",
                f"Attempt {attempt}/{total}: {candidate.score.status}, "
                f"target error {candidate.target_error:.1f}{reference_extra}, best {best_label}",
            )
        )

    def _render_candidate(self, candidate: CandidateResult) -> None:
        score = candidate.score
        self.status_var.set(
            f"Preview: {score.status}, score={score.overall_score:.1f}, "
            f"target error={candidate.target_error:.1f}, attempt={candidate.attempt}"
        )
        self._log(self.status_var.get())
        for error in candidate.errors[:8]:
            self._log(f"ERROR: {error}")
        for warning in candidate.warnings[:8]:
            self._log(f"WARN: {warning}")
        for note in candidate.notes[:12]:
            self._log(f"NOTE: {note}")
        self._render_chart(candidate)

    def _render_chart(self, candidate: CandidateResult) -> None:
        canvas = self.chart_canvas
        canvas.delete("all")
        width = max(1, canvas.winfo_width())
        height = max(1, canvas.winfo_height())
        pad = 28
        canvas.create_rectangle(0, 0, width, height, fill="#111827", outline="")
        canvas.create_line(pad, height - pad, width - pad, height - pad, fill="#6B7280")
        canvas.create_line(pad, pad, pad, height - pad, fill="#6B7280")
        scores = candidate.score.per_click_scores
        if not scores:
            canvas.create_text(width // 2, height // 2, text="No PASS solution curve", fill="#E5E7EB")
            return
        max_click = max(item.click_index for item in scores)

        def xy(click_index: int, value: float) -> tuple[float, float]:
            x = pad + (width - pad * 2) * ((click_index - 1) / max(1, max_click - 1))
            y = height - pad - (height - pad * 2) * (max(0.0, min(100.0, value)) / 100.0)
            return x, y

        actual_points = [xy(item.click_index, item.score) for item in scores]
        for left, right in zip(actual_points, actual_points[1:]):
            canvas.create_line(*left, *right, fill="#38BDF8", width=2)
        for x, y in actual_points:
            canvas.create_oval(x - 2, y - 2, x + 2, y + 2, fill="#38BDF8", outline="")

        for phase in candidate.score.phase_scores:
            x1, y1 = xy(phase.start_click, phase.target_score)
            x2, y2 = xy(phase.end_click, phase.target_score)
            canvas.create_line(x1, y1, x2, y2, fill="#FBBF24", width=2, dash=(4, 3))
            canvas.create_text((x1 + x2) / 2, y1 - 10, text=phase.name, fill="#FDE68A", font=("Arial", 8))
        canvas.create_text(width - pad, pad, text="Actual blue / Target yellow", fill="#E5E7EB", anchor="ne")

    def _log(self, message: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{timestamp}] {message}\n")
        self.log_text.see("end")

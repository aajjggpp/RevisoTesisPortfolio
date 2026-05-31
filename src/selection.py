"""Selection engine — Topology A.

Rules:
- If ``config.pin`` is set to a valid src_symbol → analyse that ticker.
- Otherwise → analyse the ticker with the highest score.
- In both cases compute the top-3 by score and attach a reason to each.
- Execution is fully automatic; no human gate mid-run.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .scoring import StockScore


@dataclass
class SelectionResult:
    selected: StockScore        # The ticker to analyse
    top3: List[StockScore]      # Top-3 candidates by score (always populated)
    pin_used: bool              # True when a pin override was applied


def select(
    scores: List[StockScore],
    pin: Optional[str] = None,
) -> SelectionResult:
    """Select which stock to analyse.

    Parameters
    ----------
    scores:
        Pre-computed scores for all universe entries.
    pin:
        Optional src_symbol override from ``config.pin``.  When set the pinned
        ticker is always selected regardless of score.

    Returns
    -------
    SelectionResult with the chosen stock and the top-3 candidates.

    Raises
    ------
    ValueError:
        If *scores* is empty, or if *pin* does not match any entry in *scores*.
    """
    if not scores:
        raise ValueError("scores list is empty — universe may be misconfigured")

    sorted_scores = sorted(scores, key=lambda s: s.total_score, reverse=True)
    top3 = sorted_scores[:3]

    if pin:
        pinned = next((s for s in scores if s.src_symbol == pin), None)
        if pinned is None:
            raise ValueError(
                f"Pinned symbol '{pin}' not found in scores. "
                "Check config.pin against universe.yaml src_symbol values."
            )
        selected = pinned
        # Ensure the pinned ticker appears in top3 so the output is complete.
        if pinned not in top3:
            top3 = [pinned] + top3[:2]
        return SelectionResult(selected=selected, top3=top3, pin_used=True)

    return SelectionResult(selected=sorted_scores[0], top3=top3, pin_used=False)

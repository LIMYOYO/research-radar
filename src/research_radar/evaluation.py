"""Offline ranking evaluation against reviewed candidate fixtures."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .discovery import Candidate
from .project import ingest_project
from .ranking import RankedCandidate, rank_candidates


@dataclass(frozen=True)
class EvaluationResult:
    candidate_count: int
    relevant_count: int
    precision_at_5: float
    precision_at_10: float
    recall_in_visible: float
    reciprocal_rank: float
    visible_identities: tuple[str, ...]
    suppressed_identities: tuple[str, ...]


def _precision(ranked: list[RankedCandidate], relevant: set[str], k: int) -> float:
    top = ranked[:k]
    if not top:
        return 0.0
    return sum(item.candidate.identity in relevant for item in top) / len(top)


def evaluate_fixture(
    project: str | Path,
    fixture: str | Path,
) -> EvaluationResult:
    snapshot = ingest_project(project)
    payload = json.loads(Path(fixture).read_text(encoding="utf-8"))
    cases = payload.get("candidates")
    if not isinstance(cases, list) or not cases:
        raise ValueError("Evaluation fixture must contain a non-empty candidates list.")

    candidates: list[Candidate] = []
    relevant: set[str] = set()
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("candidate"), dict):
            raise ValueError("Each evaluation case must contain a candidate object.")
        candidate = Candidate.from_dict(case["candidate"])
        candidates.append(candidate)
        if case.get("judgment") == "relevant":
            relevant.add(candidate.identity)

    ranked = rank_candidates(snapshot, candidates)
    visible = [item for item in ranked if not item.suppressed and item.recommended_action != "weak"]
    found_relevant = sum(item.candidate.identity in relevant for item in visible)
    first_relevant_rank = next(
        (index for index, item in enumerate(visible, start=1) if item.candidate.identity in relevant),
        None,
    )
    return EvaluationResult(
        candidate_count=len(candidates),
        relevant_count=len(relevant),
        precision_at_5=round(_precision(visible, relevant, 5), 4),
        precision_at_10=round(_precision(visible, relevant, 10), 4),
        recall_in_visible=round(found_relevant / len(relevant), 4) if relevant else 0.0,
        reciprocal_rank=round(1 / first_relevant_rank, 4) if first_relevant_rank else 0.0,
        visible_identities=tuple(item.candidate.identity for item in visible),
        suppressed_identities=tuple(
            item.candidate.identity for item in ranked if item.suppressed
        ),
    )

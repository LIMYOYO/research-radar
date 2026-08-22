"""Explainable baseline ranking conditioned on the local research project."""

from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass, replace
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from .config import load_config
from .discovery import Candidate
from .project import ProjectSnapshot


STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "how",
    "in", "into", "is", "it", "of", "on", "or", "our", "that", "the", "their",
    "this", "to", "under", "we", "what", "when", "which", "with", "without",
    "paper", "project", "research", "study", "using", "model", "models",
}
SUPPRESS_LABELS = {"known", "off-topic", "weak", "duplicate"}
POSITIVE_FEEDBACK = {"read-now": 0.20, "cite": 0.18, "watch": 0.10}


@dataclass(frozen=True)
class RankedCandidate:
    candidate: Candidate
    score: float
    scores: dict[str, float]
    matched_concepts: tuple[str, ...]
    relationship: str
    recommended_action: str
    why_it_matters: str
    distillation: str
    evidence_note: str
    suppressed: bool
    suppression_reason: str | None

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["candidate"] = self.candidate.to_dict()
        return value


def tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z][a-z0-9]{2,}", text.lower().replace("-", " "))
        if token not in STOPWORDS
    }


def _profile_exclusion_phrases(text: str) -> list[set[str]]:
    """Parse semantic exclusion clauses without treating Markdown wraps as clauses."""
    blocks: list[str] = []
    current: list[str] = []

    def flush() -> None:
        if current:
            blocks.append(" ".join(current))
            current.clear()

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            flush()
            continue
        bullet = re.match(r"^[-*+]\s+(.*)$", line)
        if bullet:
            flush()
            current.append(bullet.group(1))
            continue
        current.append(line)
    flush()

    phrases: list[set[str]] = []
    for block in blocks:
        for clause in re.split(r"[;.!?]+", block):
            phrase = tokens(clause)
            if phrase:
                phrases.append(phrase)
    return phrases


def _overlap(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / math.sqrt(len(left) * len(right))


def _recency(year: int | None) -> float:
    if year is None:
        return 0.25
    age = max(0, date.today().year - year)
    return max(0.0, 1.0 - age / 10.0)


def _lane_score(lanes: Iterable[str]) -> float:
    score = 0.0
    for lane in lanes:
        if "forward-citations" in lane:
            score = max(score, 1.0)
        elif "related" in lane:
            score = max(score, 0.75)
        elif "keywords" in lane:
            score = max(score, 0.45)
    return score


def _venue_score(venue: str | None, watched: Iterable[str]) -> float:
    if not venue:
        return 0.0
    normalized = venue.lower()
    return 1.0 if any(str(item).lower() in normalized for item in watched) else 0.25


def _relationship(candidate: Candidate, matched: set[str]) -> str:
    corpus = f"{candidate.title} {candidate.abstract or ''}".lower()
    if any(word in corpus for word in ("contradict", "counterexample", "fails to")):
        return "contradicts"
    if any("forward-citations" in lane for lane in candidate.discovered_by):
        return "extends"
    if any(word in corpus for word in ("estimator", "algorithm", "method", "identification")):
        return "method-lead"
    if len(matched) >= 4:
        return "competes"
    if any("related" in lane for lane in candidate.discovered_by):
        return "background"
    return "unknown"


def _sentences(value: str | None, limit: int = 2) -> str:
    if not value:
        return "No abstract was available; only bibliographic metadata was used."
    parts = re.split(r"(?<=[.!?])\s+", value.strip())
    return " ".join(parts[:limit])


def load_local_access(project: str | Path) -> dict[str, dict[str, Any]]:
    path = Path(project).expanduser().resolve() / ".research-radar" / "access-ledger.jsonl"
    if not path.is_file():
        return {}
    records: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("doi"):
            records[str(record["doi"])] = record
    return records


def _with_access(candidate: Candidate, records: dict[str, dict[str, Any]]) -> Candidate:
    if not candidate.doi or candidate.doi not in records:
        return candidate
    record = records[candidate.doi]
    if record.get("codex_eligible"):
        return replace(candidate, access_status="full-text")
    return candidate


def rank_candidates(
    snapshot: ProjectSnapshot,
    candidates: Iterable[Candidate],
    *,
    feedback: dict[str, dict[str, object]] | None = None,
) -> tuple[RankedCandidate, ...]:
    config = load_config(snapshot.project_root)
    feedback = feedback or {}
    local_access = load_local_access(snapshot.project_root)

    topical_text = " ".join(
        [snapshot.profile.project_name, snapshot.profile.raw_markdown, snapshot.manuscript_text]
    )
    topical_terms = tokens(topical_text)
    structural_text = " ".join(
        snapshot.profile.sections.get(name, "")
        for name in ("framework-and-primitives", "central-mechanism", "contribution-delta", "method")
    )
    structural_terms = tokens(structural_text)
    watched_venues = list(config.get("watch", {}).get("venues", []))
    watch_section = snapshot.profile.sections.get("watch", "")
    venue_line = re.search(r"(?im)^\s*[-*]?\s*venues?(?:\s+or\s+working-paper\s+series)?\s*:\s*(.+)$", watch_section)
    if venue_line:
        watched_venues.extend(item.strip() for item in venue_line.group(1).split(","))
    exclusion_phrases: list[set[str]] = []
    for item in config.get("exclude", {}).get("keywords", []):
        phrase = tokens(str(item))
        if phrase:
            exclusion_phrases.append(phrase)
    exclusion_phrases.extend(
        _profile_exclusion_phrases(snapshot.profile.sections.get("exclude", ""))
    )

    ranked: list[RankedCandidate] = []
    for original in candidates:
        candidate = _with_access(original, local_access)
        candidate_terms = tokens(f"{candidate.title} {candidate.abstract or ''}")
        matched = candidate_terms & topical_terms
        scores = {
            "topical_fit": _overlap(candidate_terms, topical_terms),
            "structural_fit": _overlap(candidate_terms, structural_terms),
            "citation_relation": _lane_score(candidate.discovered_by),
            "recency": _recency(candidate.year),
            "venue_prior": _venue_score(candidate.venue, watched_venues),
            "evidence": {"metadata": 0.2, "abstract": 0.65, "full-text": 1.0}.get(candidate.evidence_level, 0.2),
        }
        closest_seed_overlap = max(
            (
                _overlap(candidate_terms, tokens(seed.title or ""))
                for seed in snapshot.seeds
                if seed.title
            ),
            default=0.0,
        )
        fit = max(scores["topical_fit"], scores["structural_fit"])
        scores["novelty"] = max(0.0, 1.0 - closest_seed_overlap) * fit
        scores["priority_risk"] = min(
            1.0,
            2.0
            * fit
            * max(scores["citation_relation"], 0.25)
            * max(scores["recency"], 0.25),
        )
        base = (
            0.27 * scores["structural_fit"]
            + 0.23 * scores["topical_fit"]
            + 0.18 * scores["citation_relation"]
            + 0.08 * scores["recency"]
            + 0.04 * scores["venue_prior"]
            + 0.08 * scores["evidence"]
            + 0.04 * scores["novelty"]
            + 0.08 * scores["priority_risk"]
        )
        feedback_item = feedback.get(candidate.identity, {})
        label = str(feedback_item.get("label") or "")
        suppression_reason = None
        if label in SUPPRESS_LABELS:
            suppression_reason = f"feedback:{label}"
        exclusion_matches: list[tuple[float, set[str]]] = []
        for phrase in exclusion_phrases:
            hits = phrase & candidate_terms
            coverage = len(hits) / len(phrase)
            if len(hits) >= 2 and coverage >= 0.30:
                exclusion_matches.append((coverage, hits))
        if exclusion_matches and scores["structural_fit"] < 0.25:
            _, best_hits = max(exclusion_matches, key=lambda item: item[0])
            suppression_reason = "profile-exclusion:" + ", ".join(sorted(best_hits)[:4])
        score = max(0.0, min(1.0, base + POSITIVE_FEEDBACK.get(label, 0.0)))
        relationship = _relationship(candidate, matched)
        action = "read-now" if score >= 0.58 else ("watch" if score >= 0.34 else "weak")
        if relationship == "competes" and score >= 0.48:
            action = "read-now"
        concepts = tuple(sorted(matched, key=lambda value: (-len(value), value))[:8])
        concept_text = ", ".join(concepts) if concepts else "no strong lexical concept match"
        lane_text = ", ".join(candidate.discovered_by)
        why = (
            f"Matched project concepts: {concept_text}. Discovery evidence: {lane_text}. "
            f"The baseline classifies the relationship as {relationship}."
        )
        evidence_note = (
            "A local full-text file is available; this baseline card still uses indexed metadata/abstract until full-text distillation runs."
            if candidate.access_status == "full-text" and candidate.evidence_level != "full-text"
            else f"Distillation evidence level: {candidate.evidence_level}."
        )
        ranked.append(
            RankedCandidate(
                candidate=candidate,
                score=round(score, 4),
                scores={key: round(value, 4) for key, value in scores.items()},
                matched_concepts=concepts,
                relationship=relationship,
                recommended_action=action,
                why_it_matters=why,
                distillation=_sentences(candidate.abstract),
                evidence_note=evidence_note,
                suppressed=suppression_reason is not None,
                suppression_reason=suppression_reason,
            )
        )
    return tuple(sorted(ranked, key=lambda item: (item.suppressed, -item.score, item.candidate.title)))


def apply_distillations(
    ranked: Iterable[RankedCandidate],
    distillations: dict[str, dict[str, object]],
) -> tuple[RankedCandidate, ...]:
    """Overlay persisted deep-reading results without hiding the baseline score trace."""
    hydrated: list[RankedCandidate] = []
    for item in ranked:
        payload = distillations.get(item.candidate.identity)
        if not payload:
            hydrated.append(item)
            continue
        evidence_level = str(payload["evidence_level"])
        candidate = replace(
            item.candidate,
            evidence_level=evidence_level,
            access_status=(
                "full-text" if evidence_level == "full-text" else item.candidate.access_status
            ),
        )
        action = str(payload["recommended_action"])
        scores = dict(item.scores)
        scores["distillation_confidence"] = float(payload["confidence"])
        hydrated.append(
            replace(
                item,
                candidate=candidate,
                scores=scores,
                relationship=str(payload["project_relationship"]),
                recommended_action="weak" if action == "ignore" else action,
                why_it_matters=(
                    f"Contribution delta: {payload['contribution_delta']} "
                    f"Project consequence: {payload['project_consequence']}"
                ),
                distillation=(
                    f"Paper type: {payload['paper_type']}. "
                    f"Question/setting: {payload['research_question_and_setting']} "
                    f"Framework: {payload['framework']} "
                    f"Mechanism: {payload['mechanism_or_identification']} "
                    f"Main result: {payload['main_result']}"
                ),
                evidence_note=(
                    f"Deep distillation evidence: {evidence_level}; confidence "
                    f"{float(payload['confidence']):.2f}; sources: "
                    + ", ".join(str(source) for source in payload["evidence_sources"])
                ),
            )
        )
    return tuple(hydrated)

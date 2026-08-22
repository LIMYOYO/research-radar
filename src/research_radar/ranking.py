"""Explainable baseline ranking conditioned on the local research project."""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import asdict, dataclass, replace
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from .access import paper_filename
from .config import load_config
from .discovery import Candidate, profile_queries
from .project import ProjectSnapshot, normalize_title


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


def _profile_exclusion_rules(text: str) -> list[tuple[set[str], set[str], float]]:
    """Parse exclusion targets and the conditions that rescue a candidate.

    Clauses such as ``generic X with no Y`` or ``X unless Y`` mean that X is
    unwanted only when Y is absent. Keeping the two sides separate prevents
    positive exception terms such as ``responders`` or ``retrieval`` from
    becoming exclusion keywords themselves.
    """
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

    rules: list[tuple[set[str], set[str], float]] = []
    for block in blocks:
        for clause in re.split(r"[;.!?]+", block):
            parts = re.split(
                r"\b(?:without|with\s+no|that\s+do\s+not|unless)\b",
                clause,
                maxsplit=1,
                flags=re.IGNORECASE,
            )
            target = tokens(parts[0])
            rescue = tokens(parts[1]) if len(parts) == 2 else set()
            if target:
                # Free-form prose is semantically rich and should require a
                # strong target match before causing hard suppression.
                rules.append((target, rescue, 0.50))
    return rules


def _overlap(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / math.sqrt(len(left) * len(right))


def _phrase_fit(candidate_text: str, phrases: Iterable[str]) -> float:
    """Reward coverage of a few project-authored multiword watch phrases."""
    candidate_terms = tokens(candidate_text)
    candidate_sequence = " ".join(
        token
        for token in re.findall(r"[a-z][a-z0-9]{2,}", candidate_text.lower().replace("-", " "))
        if token not in STOPWORDS
    )
    matches: list[float] = []
    for raw_phrase in phrases:
        phrase = tokens(raw_phrase)
        if not phrase:
            continue
        phrase_sequence = " ".join(
            token
            for token in re.findall(
                r"[a-z][a-z0-9]{2,}", raw_phrase.lower().replace("-", " ")
            )
            if token not in STOPWORDS
        )
        if phrase_sequence and phrase_sequence in candidate_sequence:
            matches.append(1.0)
            continue
        coverage = len(candidate_terms & phrase) / len(phrase)
        if coverage <= 0:
            continue
        specificity = min(1.0, len(phrase) / 3.0)
        # Partial overlap with a multiword watch phrase is common noise (for
        # example, "public access" without "defibrillator"). Cubing coverage
        # rewards near-complete phrase matches while sharply discounting those
        # generic fragments.
        matches.append(0.25 * (coverage**3) * specificity)
    strongest = sorted(matches, reverse=True)[:3]
    return sum(strongest) / len(strongest) if strongest else 0.0


def _watch_vocabulary_fit(candidate_terms: set[str], phrases: Iterable[str]) -> float:
    """Measure overlap with concepts repeated across researcher watch phrases."""
    frequencies = Counter(
        term
        for phrase in phrases
        for term in tokens(phrase)
    )
    if not frequencies:
        return 0.0
    weights = {term: count * count for term, count in frequencies.items()}
    denominator = sum(sorted(weights.values(), reverse=True)[:5]) or 1
    matched = sum(weight for term, weight in weights.items() if term in candidate_terms)
    return min(1.0, matched / denominator)


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
    if any(
        phrase in corpus
        for phrase in ("extends ", "generalizes ", "builds on ", "builds upon ")
    ):
        return "extends"
    if any(word in corpus for word in ("estimator", "algorithm", "method", "identification")):
        return "method-lead"
    if len(matched) >= 4:
        return "competes"
    if any("related" in lane for lane in candidate.discovered_by):
        return "background"
    # A citation edge proves chronology and linkage, not whether a paper
    # supports, extends, or competes with the seed.
    if any("forward-citations" in lane for lane in candidate.discovered_by):
        return "unknown"
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


def _with_access(
    candidate: Candidate,
    records: dict[str, dict[str, Any]],
    *,
    project: str | Path,
) -> Candidate:
    if not candidate.doi or candidate.doi not in records:
        return replace(candidate, local_access_status="none")
    record = records[candidate.doi]
    root = Path(project).expanduser().resolve()
    relative_pdf = record.get("file")
    if not record.get("codex_eligible") or not isinstance(relative_pdf, str):
        return replace(candidate, local_access_status="none")
    pdf_path = (root / relative_pdf).resolve()
    try:
        pdf_path.relative_to(root)
    except ValueError:
        return replace(candidate, local_access_status="none")
    if not pdf_path.is_file():
        return replace(candidate, local_access_status="none")
    text_path = (
        root
        / ".research-radar"
        / "texts"
        / f"{Path(paper_filename(candidate.doi)).stem}.txt"
    )
    local_status = "text" if text_path.is_file() and text_path.stat().st_size > 0 else "pdf"
    return replace(candidate, local_access_status=local_status)


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
    watch_phrases = list(profile_queries(snapshot, config))
    seed_titles = {
        normalize_title(seed.title) for seed in snapshot.seeds if seed.title
    }
    exclusion_rules: list[tuple[set[str], set[str], float]] = []
    for item in config.get("exclude", {}).get("keywords", []):
        phrase = tokens(str(item))
        if phrase:
            # Explicit config entries are deliberate machine-readable rules.
            exclusion_rules.append((phrase, set(), 0.30))
    exclusion_rules.extend(
        _profile_exclusion_rules(snapshot.profile.sections.get("exclude", ""))
    )

    ranked: list[RankedCandidate] = []
    for original in candidates:
        candidate = _with_access(
            original,
            local_access,
            project=snapshot.project_root,
        )
        candidate_terms = tokens(f"{candidate.title} {candidate.abstract or ''}")
        matched = candidate_terms & topical_terms
        scores = {
            "topical_fit": _overlap(candidate_terms, topical_terms),
            "structural_fit": _overlap(candidate_terms, structural_terms),
            "watch_phrase_fit": _phrase_fit(
                f"{candidate.title} {candidate.abstract or ''}", watch_phrases
            ),
            "watch_vocabulary_fit": _watch_vocabulary_fit(
                candidate_terms, watch_phrases
            ),
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
        scores["seed_similarity"] = closest_seed_overlap
        fit = max(
            scores["topical_fit"],
            scores["structural_fit"],
            scores["watch_phrase_fit"],
        )
        scores["novelty"] = max(0.0, 1.0 - closest_seed_overlap) * fit
        scores["priority_risk"] = min(
            1.0,
            2.0
            * fit
            * max(scores["citation_relation"], 0.25)
            * max(scores["recency"], 0.25),
        )
        if len(watch_phrases) >= 6:
            base = 2.0 * (
                0.18 * scores["structural_fit"]
                + 0.45 * scores["topical_fit"]
                + 0.07 * scores["watch_phrase_fit"]
                + 0.18 * scores["watch_vocabulary_fit"]
                + 0.03 * scores["citation_relation"]
                + 0.02 * scores["recency"]
                + 0.02 * scores["venue_prior"]
                + 0.02 * scores["evidence"]
                + 0.01 * scores["novelty"]
                + 0.02 * scores["priority_risk"]
            )
        else:
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
        # Citation neighborhoods are intentionally high recall. Require some
        # independent project anchor before allowing a citation edge alone to
        # dominate the shortlist. This especially controls forward citations
        # of broad methodological or application seeds.
        scores["anchor_penalty"] = (
            max(
                0.0,
                0.08
                * (
                    1.0
                    - 4.0 * scores["watch_phrase_fit"]
                    - 2.0 * scores["watch_vocabulary_fit"]
                    - 3.0 * scores["structural_fit"]
                ),
            )
            if len(watch_phrases) >= 6
            else 0.0
        )
        scores["keyword_lane_penalty"] = (
            0.12
            if set(candidate.discovered_by) == {"crossref:keywords"}
            and scores["watch_phrase_fit"] < 0.50
            else 0.0
        )
        base -= scores["anchor_penalty"] + scores["keyword_lane_penalty"]
        feedback_item = feedback.get(candidate.identity, {})
        label = str(feedback_item.get("label") or "")
        suppression_reason = (
            "already-in-bibliography"
            if normalize_title(candidate.title) in seed_titles
            else None
        )
        if label in SUPPRESS_LABELS:
            suppression_reason = f"feedback:{label}"
        exclusion_matches: list[tuple[float, set[str]]] = []
        for target, rescue, minimum_coverage in exclusion_rules:
            hits = target & candidate_terms
            coverage = len(hits) / len(target)
            rescue_coverage = len(rescue & candidate_terms) / len(rescue) if rescue else 0.0
            if (
                len(hits) >= 2
                and coverage >= minimum_coverage
                and rescue_coverage < 0.60
            ):
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
        if candidate.local_access_status in {"pdf", "text"} and candidate.evidence_level != "full-text":
            evidence_note = (
                f"Verified local {candidate.local_access_status} is available; this baseline "
                "card still uses indexed metadata/abstract until full-text distillation runs."
            )
        elif candidate.access_status == "full-text" and candidate.evidence_level != "full-text":
            evidence_note = (
                "A metadata provider reports a full-text route, but no verified local PDF "
                "has been imported; this card uses indexed metadata/abstract only."
            )
        else:
            evidence_note = f"Distillation evidence level: {candidate.evidence_level}."
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

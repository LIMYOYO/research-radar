"""Validation and context assembly for project-conditioned paper distillations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .access import paper_filename
from .discovery import Candidate
from .project import ProjectSnapshot
from .ranking import load_local_access


class DistillationError(ValueError):
    """Raised when a distillation cannot be trusted or persisted."""


REQUIRED_FIELDS = {
    "schema_version",
    "candidate_identity",
    "paper_type",
    "research_question_and_setting",
    "framework",
    "mechanism_or_identification",
    "main_result",
    "project_relationship",
    "contribution_delta",
    "project_consequence",
    "recommended_action",
    "evidence_level",
    "evidence_sources",
    "confidence",
}
OPTIONAL_FIELDS = {"boundary_conditions", "unresolved_questions"}
RELATIONSHIPS = {
    "supports",
    "contradicts",
    "extends",
    "competes",
    "method-lead",
    "background",
    "unknown",
}
ACTIONS = {"read-now", "cite", "watch", "ignore"}
EVIDENCE_LEVELS = {"full-text", "abstract", "metadata"}
PAPER_TYPES = {"analytical", "empirical", "experimental", "methods"}
TEXT_FIELDS = {
    "candidate_identity",
    "research_question_and_setting",
    "framework",
    "mechanism_or_identification",
    "main_result",
    "contribution_delta",
    "project_consequence",
}


def validate_distillation(value: object) -> dict[str, Any]:
    """Validate the checked-in distillation contract without a runtime schema dependency."""
    if not isinstance(value, dict):
        raise DistillationError("A distillation must be a JSON object.")
    missing = sorted(REQUIRED_FIELDS - value.keys())
    if missing:
        raise DistillationError(f"Missing distillation field(s): {', '.join(missing)}")
    unknown = sorted(value.keys() - REQUIRED_FIELDS - OPTIONAL_FIELDS)
    if unknown:
        raise DistillationError(f"Unknown distillation field(s): {', '.join(unknown)}")
    if value.get("schema_version") != 1:
        raise DistillationError("schema_version must equal 1.")
    for field in sorted(TEXT_FIELDS):
        if not isinstance(value.get(field), str) or not value[field].strip():
            raise DistillationError(f"{field} must be a non-empty string.")
    if value.get("project_relationship") not in RELATIONSHIPS:
        raise DistillationError("project_relationship is not in the supported taxonomy.")
    if value.get("recommended_action") not in ACTIONS:
        raise DistillationError("recommended_action must be read-now, cite, watch, or ignore.")
    if value.get("evidence_level") not in EVIDENCE_LEVELS:
        raise DistillationError("evidence_level must be full-text, abstract, or metadata.")
    if value.get("paper_type") not in PAPER_TYPES:
        raise DistillationError(
            "paper_type must be analytical, empirical, experimental, or methods."
        )
    sources = value.get("evidence_sources")
    if (
        not isinstance(sources, list)
        or not sources
        or any(not isinstance(item, str) or not item.strip() for item in sources)
    ):
        raise DistillationError("evidence_sources must contain at least one non-empty source.")
    confidence = value.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise DistillationError("confidence must be a number between 0 and 1.")
    if not 0 <= float(confidence) <= 1:
        raise DistillationError("confidence must be between 0 and 1.")
    for field in OPTIONAL_FIELDS:
        items = value.get(field, [])
        if not isinstance(items, list) or any(not isinstance(item, str) for item in items):
            raise DistillationError(f"{field} must be an array of strings.")
    return dict(value)


def available_evidence(project: str | Path, candidate: Candidate) -> dict[str, Any]:
    """Return evidence levels that are actually available to a local run."""
    root = Path(project).expanduser().resolve()
    levels = ["metadata"]
    if candidate.abstract:
        levels.append("abstract")
    local_record = load_local_access(root).get(candidate.doi or "")
    pdf_file: str | None = None
    text_file: str | None = None
    if local_record and local_record.get("codex_eligible"):
        relative_pdf = local_record.get("file")
        if isinstance(relative_pdf, str) and (root / relative_pdf).is_file():
            levels.append("full-text")
            pdf_file = relative_pdf
        if candidate.doi:
            candidate_text = (
                root
                / ".research-radar"
                / "texts"
                / f"{Path(paper_filename(candidate.doi)).stem}.txt"
            )
            if candidate_text.is_file():
                text_file = candidate_text.relative_to(root).as_posix()
    return {
        "levels": levels,
        "local_pdf": pdf_file,
        "local_text": text_file,
        "full_text_export_command": (
            f"research-radar access text {candidate.doi} --project {root}"
            if "full-text" in levels and not text_file and candidate.doi
            else None
        ),
    }


def validate_for_project(
    value: object,
    *,
    project: str | Path,
    candidate: Candidate,
) -> dict[str, Any]:
    normalized = validate_distillation(value)
    if normalized["candidate_identity"] != candidate.identity:
        raise DistillationError(
            "candidate_identity does not match the selected project candidate."
        )
    evidence = available_evidence(project, candidate)
    if normalized["evidence_level"] not in evidence["levels"]:
        raise DistillationError(
            f"Evidence level {normalized['evidence_level']!r} is unavailable for "
            f"{candidate.identity}; available levels: {', '.join(evidence['levels'])}."
        )
    return normalized


def build_context(
    snapshot: ProjectSnapshot,
    candidate: Candidate,
) -> dict[str, Any]:
    evidence = available_evidence(snapshot.project_root, candidate)
    return {
        "schema_version": 1,
        "project": {
            "name": snapshot.profile.project_name,
            "fingerprint": snapshot.fingerprint,
            "profile_source": snapshot.profile.source_file,
            "profile_markdown": snapshot.profile.raw_markdown,
            "manuscript_sources": [
                source.path for source in snapshot.source_files if source.kind == "tex"
            ],
        },
        "candidate": candidate.to_dict(),
        "available_evidence": evidence,
        "output_contract": {
            "schema": "schemas/distillation.schema.json",
            "required_fields": sorted(REQUIRED_FIELDS),
            "relationship_taxonomy": sorted(RELATIONSHIPS),
            "actions": sorted(ACTIONS),
            "paper_types": sorted(PAPER_TYPES),
        },
    }

"""Deterministic Markdown briefings for fast researcher triage."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .ranking import RankedCandidate


@dataclass(frozen=True)
class ReportResult:
    path: Path
    duplicate: bool
    shown_count: int
    suppressed_count: int


def _digest_item(item: RankedCandidate) -> dict[str, object]:
    return {
        "identity": item.candidate.identity,
        "candidate": item.candidate.to_dict(),
        "score": item.score,
        "scores": item.scores,
        "matched_concepts": item.matched_concepts,
        "access_status": item.candidate.access_status,
        "evidence_level": item.candidate.evidence_level,
        "evidence_note": item.evidence_note,
        "relationship": item.relationship,
        "recommended_action": item.recommended_action,
        "why_it_matters": item.why_it_matters,
        "distillation": item.distillation,
        "suppressed": item.suppressed,
        "suppression_reason": item.suppression_reason,
    }


def render_briefing(
    *,
    project_name: str,
    project_fingerprint: str,
    ranked: Iterable[RankedCandidate],
    manifest: dict[str, Any],
    top_n: int,
) -> str:
    ranked = tuple(ranked)
    visible = [
        item
        for item in ranked
        if not item.suppressed and item.recommended_action != "weak"
    ][:top_n]
    suppressed = [item for item in ranked if item.suppressed]
    generated_at = str(
        manifest.get("generated_at")
        or f"{manifest['search_to']}T00:00:00+00:00"
    )
    lines = [
        f"# Research Radar — {project_name}",
        "",
        f"- Generated: {generated_at}",
        f"- Search window: {manifest['search_from']} to {manifest['search_to']}",
        f"- Project fingerprint: `{project_fingerprint}`",
        f"- Candidates found: {manifest['candidate_count']}; new: {manifest.get('new_candidate_count', manifest['candidate_count'])}; shown: {len(visible)}; suppressed: {len(suppressed)}",
        "",
        "## Executive signal",
        "",
    ]
    if visible:
        lines.append(
            f"{len(visible)} candidate(s) passed the current triage threshold. "
            f"The leading signal is **{visible[0].candidate.title}** ({visible[0].recommended_action})."
        )
    else:
        lines.append("No unseen high-signal change passed the current triage rules.")

    lines.extend(["", "## Top papers", ""])
    if not visible:
        lines.append("No papers to show.")
    for index, item in enumerate(visible, start=1):
        paper = item.candidate
        authors = ", ".join(paper.authors) or "Authors unavailable"
        link = paper.url or (f"https://doi.org/{paper.doi}" if paper.doi else "")
        title = f"[{paper.title}]({link})" if link else paper.title
        lines.extend(
            [
                f"### {index}. {title}",
                "",
                f"- **Signal:** {item.recommended_action}; score {item.score:.3f}; relationship `{item.relationship}`",
                f"- **Metadata:** {authors}; {paper.venue or 'venue unavailable'}; {paper.year or 'year unavailable'}",
                f"- **Identity:** `{paper.identity}`",
                f"- **Access/evidence:** `{paper.access_status}` / `{paper.evidence_level}`",
                f"- **Found through:** {', '.join(paper.discovered_by)}",
                f"- **Why it matters:** {item.why_it_matters}",
                f"- **Distillation:** {item.distillation}",
                f"- **Evidence note:** {item.evidence_note}",
                f"- **Score trace:** " + ", ".join(f"{name}={value:.3f}" for name, value in item.scores.items()),
            ]
        )
        if paper.doi and paper.access_status != "full-text":
            lines.append(
                f"- **Access next step:** `research-radar access acquire {paper.doi} --project .`"
            )
        lines.append("")

    lines.extend(["## Search audit", ""])
    lines.append("- Queries: " + "; ".join(manifest.get("queries", [])))
    for adapter, status in sorted(manifest.get("adapter_status", {}).items()):
        lines.append(f"- {adapter}: {status}")
    for error in manifest.get("errors", []):
        lines.append(f"- Error: {error}")
    if suppressed:
        lines.extend(["", "## Suppressed candidates", ""])
        for item in suppressed:
            lines.append(
                f"- `{item.candidate.identity}` — {item.candidate.title}: {item.suppression_reason}"
            )
    lines.extend(
        [
            "",
            "## Feedback",
            "",
            "Use `research-radar feedback IDENTITY LABEL --project .` with "
            "`read-now`, `cite`, `watch`, `known`, `off-topic`, `weak`, or `duplicate`.",
            "",
        ]
    )
    return "\n".join(lines)


def write_briefing(
    project: str | Path,
    *,
    project_name: str,
    project_fingerprint: str,
    ranked: Iterable[RankedCandidate],
    manifest: dict[str, Any],
    top_n: int,
) -> ReportResult:
    ranked = tuple(ranked)
    stable_payload = {
        "project_fingerprint": project_fingerprint,
        "search_from": manifest["search_from"],
        "search_to": manifest["search_to"],
        "queries": manifest.get("queries", ()),
        "adapter_status": manifest.get("adapter_status", {}),
        "errors": manifest.get("errors", ()),
        "ranked": [_digest_item(item) for item in ranked],
        "top_n": top_n,
    }
    digest = hashlib.sha256(
        json.dumps(stable_payload, sort_keys=True).encode("utf-8")
    ).hexdigest()[:10]
    report_dir = Path(project).expanduser().resolve() / ".research-radar" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"{manifest['search_to']}-{digest}.md"
    duplicate = path.exists()
    if not duplicate:
        path.write_text(
            render_briefing(
                project_name=project_name,
                project_fingerprint=project_fingerprint,
                ranked=ranked,
                manifest=manifest,
                top_n=top_n,
            ),
            encoding="utf-8",
        )
    return ReportResult(
        path=path,
        duplicate=duplicate,
        shown_count=len(
            [
                item
                for item in ranked
                if not item.suppressed and item.recommended_action != "weak"
            ][:top_n]
        ),
        suppressed_count=sum(item.suppressed for item in ranked),
    )


def render_weekly(
    *,
    project_name: str,
    project_fingerprint: str,
    ranked: Iterable[RankedCandidate],
    feedback: dict[str, dict[str, object]],
    days: int,
    top_n: int,
) -> str:
    ranked = tuple(ranked)
    visible = [
        item
        for item in ranked
        if not item.suppressed and item.recommended_action != "weak"
    ][:top_n]
    concepts = Counter(
        concept for item in visible for concept in item.matched_concepts
    )
    relationships = Counter(item.relationship for item in visible)
    venues = Counter(item.candidate.venue or "venue unavailable" for item in visible)
    feedback_counts = Counter(
        str(item.get("label")) for item in feedback.values() if item.get("label")
    )
    generated_at = datetime.now(timezone.utc).isoformat()
    lines = [
        f"# Research Radar Weekly — {project_name}",
        "",
        f"- Generated: {generated_at}",
        f"- Window: last {days} day(s)",
        f"- Project fingerprint: `{project_fingerprint}`",
        f"- First-seen candidates: {len(ranked)}; high-signal shown: {len(visible)}",
        "",
        "## Weekly signal",
        "",
    ]
    if visible:
        lines.append(
            f"{len(visible)} candidate(s) remain after feedback and triage. "
            f"Highest priority: **{visible[0].candidate.title}** ({visible[0].recommended_action})."
        )
    else:
        lines.append("No high-signal paper was first seen during this window.")
    lines.extend(["", "## Strongest papers", ""])
    if not visible:
        lines.append("No papers to show.")
    for index, item in enumerate(visible, start=1):
        paper = item.candidate
        link = paper.url or (f"https://doi.org/{paper.doi}" if paper.doi else None)
        title = f"[{paper.title}]({link})" if link else paper.title
        lines.extend(
            [
                f"### {index}. {title}",
                "",
                f"- **Action/relationship:** `{item.recommended_action}` / `{item.relationship}`; score {item.score:.3f}",
                f"- **Why it matters:** {item.why_it_matters}",
                f"- **Evidence:** `{paper.evidence_level}`; access `{paper.access_status}`",
                f"- **Distillation:** {item.distillation}",
                "",
            ]
        )
    lines.extend(["## Pattern synthesis", ""])
    lines.append(
        "- Repeated concepts: "
        + (", ".join(f"{name} ({count})" for name, count in concepts.most_common(8)) or "none")
    )
    lines.append(
        "- Relationships: "
        + (", ".join(f"{name} ({count})" for name, count in relationships.most_common()) or "none")
    )
    lines.append(
        "- Venues: "
        + (", ".join(f"{name} ({count})" for name, count in venues.most_common(8)) or "none")
    )
    lines.append(
        "- Feedback: "
        + (", ".join(f"{name} ({count})" for name, count in feedback_counts.most_common()) or "none recorded")
    )
    unresolved = [item for item in visible if item.candidate.access_status != "full-text"]
    lines.extend(["", "## Full-text queue", ""])
    if not unresolved:
        lines.append("No high-signal item is waiting for full text.")
    for item in unresolved:
        paper = item.candidate
        if paper.doi:
            lines.append(
                f"- `{paper.doi}` — {paper.title}: run `research-radar access acquire {paper.doi} --project .`"
            )
        else:
            lines.append(f"- `{paper.identity}` — {paper.title}: stable DOI unresolved")
    lines.append("")
    return "\n".join(lines)


def write_weekly(
    project: str | Path,
    *,
    project_name: str,
    project_fingerprint: str,
    ranked: Iterable[RankedCandidate],
    feedback: dict[str, dict[str, object]],
    days: int,
    top_n: int,
) -> ReportResult:
    ranked = tuple(ranked)
    stable_payload = {
        "project_fingerprint": project_fingerprint,
        "days": days,
        "ranked": [_digest_item(item) for item in ranked],
        "top_n": top_n,
        "feedback": feedback,
    }
    digest = hashlib.sha256(
        json.dumps(stable_payload, sort_keys=True).encode("utf-8")
    ).hexdigest()[:10]
    report_dir = Path(project).expanduser().resolve() / ".research-radar" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"weekly-{datetime.now(timezone.utc).date().isoformat()}-{digest}.md"
    duplicate = path.exists()
    if not duplicate:
        path.write_text(
            render_weekly(
                project_name=project_name,
                project_fingerprint=project_fingerprint,
                ranked=ranked,
                feedback=feedback,
                days=days,
                top_n=top_n,
            ),
            encoding="utf-8",
        )
    visible_count = len(
        [
            item
            for item in ranked
            if not item.suppressed and item.recommended_action != "weak"
        ][:top_n]
    )
    return ReportResult(
        path=path,
        duplicate=duplicate,
        shown_count=visible_count,
        suppressed_count=sum(item.suppressed for item in ranked),
    )

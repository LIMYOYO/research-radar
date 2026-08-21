"""Deterministic Markdown briefings for fast researcher triage."""

from __future__ import annotations

import hashlib
import json
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
    generated_at = datetime.now(timezone.utc).isoformat()
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
                "",
            ]
        )

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
        "candidate_identities": [
            item.candidate.identity
            for item in ranked
            if not item.suppressed and item.recommended_action != "weak"
        ][:top_n],
        "suppressed": [item.candidate.identity for item in ranked if item.suppressed],
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

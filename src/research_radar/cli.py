"""Command-line entry point for Research Radar."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import webbrowser
from dataclasses import asdict
from datetime import date
from pathlib import Path

from .access import (
    UOFT_EBSCO_URL,
    AccessError,
    doi_url,
    export_pdf_text,
    import_pdf,
    inspect_pdf,
    libkey_url,
)
from .config import load_config
from .discovery import Candidate, discover
from .evaluation import evaluate_fixture
from .project import ProjectError, ingest_project
from .ranking import rank_candidates
from .reporting import write_briefing
from .state import (
    FEEDBACK_LABELS,
    latest_feedback,
    load_candidates,
    save_discovery,
    save_feedback,
    save_snapshot,
    state_counts,
)


TEMPLATE_ROOT = Path(__file__).resolve().parent / "templates"


DEFAULT_CONFIG = """schema_version: 1
cadence: daily
top_n: 5
lookback_days: 14
sources:
  - crossref
  - openalex
discovery_lanes:
  - forward-citations
  - related
  - keywords
watch:
  keywords: []
  authors: []
  venues: []
exclude:
  keywords: []
access:
  institution: uoft
  analysis_policy: local-test
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="research-radar")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser(
        "init", help="Initialize Research Radar state in a research project."
    )
    init.add_argument("project", nargs="?", type=Path, default=Path.cwd())
    init.add_argument(
        "--force-profile", action="store_true", help="Replace an empty generated profile."
    )

    profile = subparsers.add_parser(
        "profile", help="Parse TeX, BibTeX, and the research profile into local state."
    )
    profile.add_argument("--project", type=Path, default=Path.cwd())
    profile.add_argument("--include-text", action="store_true")

    doctor = subparsers.add_parser(
        "doctor", help="Check whether a project is ready for discovery."
    )
    doctor.add_argument("--project", type=Path, default=Path.cwd())

    discovery = subparsers.add_parser(
        "discover", help="Find forward citations, related work, and keyword matches."
    )
    discovery.add_argument("--project", type=Path, default=Path.cwd())
    discovery.add_argument("--from", dest="search_from")
    discovery.add_argument("--to", dest="search_to")
    discovery.add_argument("--limit-per-lane", type=int, default=20)

    run = subparsers.add_parser(
        "run", help="Ingest, discover, rank, and write one incremental briefing."
    )
    run.add_argument("--project", type=Path, default=Path.cwd())
    run.add_argument("--from", dest="search_from")
    run.add_argument("--to", dest="search_to")
    run.add_argument("--limit-per-lane", type=int, default=20)
    run.add_argument("--top-n", type=int)

    feedback = subparsers.add_parser(
        "feedback", help="Record a researcher decision for one candidate."
    )
    feedback.add_argument("identity")
    feedback.add_argument("label", choices=tuple(sorted(FEEDBACK_LABELS)))
    feedback.add_argument("--project", type=Path, default=Path.cwd())
    feedback.add_argument("--note")

    brief = subparsers.add_parser(
        "brief", help="Re-rank stored candidates and write a briefing without network access."
    )
    brief.add_argument("--project", type=Path, default=Path.cwd())
    brief.add_argument("--top-n", type=int)

    evaluate = subparsers.add_parser(
        "evaluate", help="Evaluate ranking against a reviewed offline fixture."
    )
    evaluate.add_argument("--project", type=Path, required=True)
    evaluate.add_argument("--fixture", type=Path, required=True)

    access = subparsers.add_parser(
        "access", help="Open a legal access route or archive a downloaded PDF."
    )
    access_subparsers = access.add_subparsers(dest="access_command", required=True)

    session = access_subparsers.add_parser(
        "session", help="Open U of T Business Source Premier through OpenAthens."
    )
    session.add_argument(
        "--print-only", action="store_true", help="Print the URL without opening it."
    )

    open_paper = access_subparsers.add_parser(
        "open", help="Open a DOI through LibKey or doi.org."
    )
    open_paper.add_argument("doi")
    open_paper.add_argument(
        "--route", choices=("libkey", "doi"), default="libkey"
    )
    open_paper.add_argument(
        "--print-only", action="store_true", help="Print the URL without opening it."
    )

    import_command = access_subparsers.add_parser(
        "import", help="Validate and archive one downloaded PDF."
    )
    import_command.add_argument("pdf", type=Path)
    import_command.add_argument("--doi", required=True)
    import_command.add_argument("--project", type=Path, default=Path.cwd())
    import_command.add_argument(
        "--route",
        choices=("libkey", "uoft-ebsco", "open-access", "publisher", "manual"),
        required=True,
    )
    import_command.add_argument("--allow-image-only", action="store_true")
    import_command.add_argument(
        "--ai-use-status",
        choices=("allowed", "prohibited", "unknown"),
        default="unknown",
        help="Whether the source terms permit AI-assisted reading.",
    )
    import_command.add_argument(
        "--analysis-policy",
        choices=("local-test", "strict"),
        default="local-test",
        help="Use local-test for the private prototype or strict to enforce AI-use status.",
    )
    import_command.add_argument(
        "--license-name", help="License or terms label, such as CC BY 4.0."
    )
    import_command.add_argument("--license-url")

    verify = access_subparsers.add_parser(
        "verify", help="Check that a local PDF can be parsed and read by Codex."
    )
    verify.add_argument("pdf", type=Path)

    path = access_subparsers.add_parser(
        "path", help="Print the private local paper directory for a project."
    )
    path.add_argument("--project", type=Path, default=Path.cwd())

    text_export = access_subparsers.add_parser(
        "text", help="Export page-delimited text from an archived PDF for Codex."
    )
    text_export.add_argument("doi")
    text_export.add_argument("--project", type=Path, default=Path.cwd())

    return parser


def _initialize_project(project: Path, force_profile: bool = False) -> dict[str, object]:
    root = project.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    radar_root = root / ".research-radar"
    for directory in (radar_root, radar_root / "papers", radar_root / "reports"):
        directory.mkdir(parents=True, exist_ok=True)

    config = radar_root / "config.yaml"
    if not config.exists():
        config.write_text(DEFAULT_CONFIG, encoding="utf-8")

    explicit_profile = root / "RESEARCH_PROFILE.md"
    readme = root / "README.md"
    profile_created = False
    if force_profile or (not explicit_profile.exists() and not readme.exists()):
        template = TEMPLATE_ROOT / "RESEARCH_PROFILE.md"
        if not template.is_file():
            raise ProjectError(f"Bundled profile template is missing: {template}")
        if explicit_profile.exists() and not force_profile:
            raise ProjectError(f"Profile already exists: {explicit_profile}")
        shutil.copyfile(template, explicit_profile)
        profile_created = True

    return {
        "project": str(root),
        "radar_root": str(radar_root),
        "config": str(config),
        "profile_created": profile_created,
        "next": f"Edit {explicit_profile if profile_created else (explicit_profile if explicit_profile.exists() else readme)}, then run research-radar profile --project {root}",
    }


def _doctor(project: Path) -> tuple[dict[str, object], int]:
    root = project.expanduser().resolve()
    checks: list[dict[str, object]] = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "ok": ok, "detail": detail})

    check("project-directory", root.is_dir(), str(root))
    if not root.is_dir():
        return {"ready": False, "checks": checks}, 2

    profile_files = [name for name in ("RESEARCH_PROFILE.md", "README.md") if (root / name).is_file()]
    tex_files = [path for path in root.rglob("*.tex") if ".research-radar" not in path.parts]
    bib_files = [path for path in root.rglob("*.bib") if ".research-radar" not in path.parts]
    check("research-profile", bool(profile_files), ", ".join(profile_files) or "missing")
    check("tex-source", bool(tex_files), f"{len(tex_files)} file(s)")
    check("bibtex-source", bool(bib_files), f"{len(bib_files)} file(s)")
    try:
        snapshot = ingest_project(root)
    except ProjectError as exc:
        check("ingestion", False, str(exc))
    else:
        check("ingestion", True, f"{len(snapshot.seeds)} seed paper(s)")
        check(
            "stable-identifiers",
            any(seed.doi for seed in snapshot.seeds),
            f"{sum(bool(seed.doi) for seed in snapshot.seeds)} DOI-bearing seed(s)",
        )
        check(
            "duplicate-identities",
            not snapshot.duplicate_identities,
            json.dumps(snapshot.duplicate_identities, ensure_ascii=False, sort_keys=True),
        )
    ready = all(item["ok"] for item in checks if item["check"] != "duplicate-identities")
    return {"project": str(root), "ready": ready, "checks": checks}, 0 if ready else 2


def _open_or_print(url: str, print_only: bool) -> int:
    print(url)
    if not print_only and not webbrowser.open(url, new=2):
        print("Could not open a browser; copy the URL above manually.", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "init":
            print(
                json.dumps(
                    _initialize_project(args.project, args.force_profile),
                    indent=2,
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 0

        if args.command == "profile":
            snapshot = ingest_project(args.project)
            state_file = save_snapshot(snapshot)
            result = snapshot.to_dict(include_text=args.include_text)
            result["state_file"] = str(state_file)
            result["state_counts"] = state_counts(args.project)
            print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
            return 0

        if args.command == "doctor":
            result, exit_code = _doctor(args.project)
            print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
            return exit_code

        if args.command == "discover":
            snapshot = ingest_project(args.project)
            save_snapshot(snapshot)
            outcome = discover(
                snapshot,
                search_from=args.search_from,
                search_to=args.search_to,
                limit_per_lane=args.limit_per_lane,
            )
            candidate_dicts = [candidate.to_dict() for candidate in outcome.candidates]
            manifest = {
                "search_from": outcome.search_from,
                "search_to": outcome.search_to,
                "queries": outcome.queries,
                "adapter_status": outcome.adapter_status,
                "errors": outcome.errors,
                "candidate_count": len(candidate_dicts),
            }
            status = "success" if not outcome.errors else "partial"
            run_id, newly_seen = save_discovery(
                args.project,
                candidates=candidate_dicts,
                manifest=manifest,
                status=status,
            )
            print(
                json.dumps(
                    {
                        **manifest,
                        "run_id": run_id,
                        "status": status,
                        "newly_seen": newly_seen,
                        "candidates": candidate_dicts,
                    },
                    indent=2,
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 0 if status == "success" else 1

        if args.command == "run":
            snapshot = ingest_project(args.project)
            save_snapshot(snapshot)
            outcome = discover(
                snapshot,
                search_from=args.search_from,
                search_to=args.search_to,
                limit_per_lane=args.limit_per_lane,
            )
            candidate_dicts = [candidate.to_dict() for candidate in outcome.candidates]
            manifest = {
                "search_from": outcome.search_from,
                "search_to": outcome.search_to,
                "queries": outcome.queries,
                "adapter_status": outcome.adapter_status,
                "errors": outcome.errors,
                "candidate_count": len(candidate_dicts),
            }
            status = "success" if not outcome.errors else "partial"
            run_id, newly_seen = save_discovery(
                args.project,
                candidates=candidate_dicts,
                manifest=manifest,
                status=status,
            )
            ranked = rank_candidates(
                snapshot,
                outcome.candidates,
                feedback=latest_feedback(args.project),
            )
            config = load_config(args.project)
            report = write_briefing(
                args.project,
                project_name=snapshot.profile.project_name,
                project_fingerprint=snapshot.fingerprint,
                ranked=ranked,
                manifest=manifest,
                top_n=args.top_n or int(config.get("top_n", 5)),
            )
            print(
                json.dumps(
                    {
                        "status": status,
                        "run_id": run_id,
                        "candidate_count": len(candidate_dicts),
                        "newly_seen": newly_seen,
                        "report": str(report.path),
                        "report_duplicate": report.duplicate,
                        "shown_count": report.shown_count,
                        "suppressed_count": report.suppressed_count,
                        "adapter_status": outcome.adapter_status,
                        "errors": outcome.errors,
                    },
                    indent=2,
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 0 if status == "success" else 1

        if args.command == "feedback":
            save_feedback(
                args.project,
                identity=args.identity,
                label=args.label,
                note=args.note,
            )
            print(
                json.dumps(
                    {"identity": args.identity, "label": args.label, "saved": True},
                    indent=2,
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 0

        if args.command == "brief":
            snapshot = ingest_project(args.project)
            save_snapshot(snapshot)
            stored = tuple(Candidate.from_dict(item) for item in load_candidates(args.project))
            ranked = rank_candidates(
                snapshot,
                stored,
                feedback=latest_feedback(args.project),
            )
            config = load_config(args.project)
            today = date.today().isoformat()
            manifest = {
                "search_from": "stored-state",
                "search_to": today,
                "queries": (),
                "adapter_status": {"network": "not-run"},
                "errors": (),
                "candidate_count": len(stored),
            }
            report = write_briefing(
                args.project,
                project_name=snapshot.profile.project_name,
                project_fingerprint=snapshot.fingerprint,
                ranked=ranked,
                manifest=manifest,
                top_n=args.top_n or int(config.get("top_n", 5)),
            )
            print(
                json.dumps(
                    {
                        "report": str(report.path),
                        "report_duplicate": report.duplicate,
                        "shown_count": report.shown_count,
                        "suppressed_count": report.suppressed_count,
                    },
                    indent=2,
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 0

        if args.command == "evaluate":
            result = evaluate_fixture(args.project, args.fixture)
            print(
                json.dumps(
                    asdict(result),
                    indent=2,
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 0

        if args.command == "access" and args.access_command == "session":
            return _open_or_print(UOFT_EBSCO_URL, args.print_only)

        if args.command == "access" and args.access_command == "open":
            url = libkey_url(args.doi) if args.route == "libkey" else doi_url(args.doi)
            return _open_or_print(url, args.print_only)

        if args.command == "access" and args.access_command == "verify":
            inspection = inspect_pdf(args.pdf)
            print(json.dumps(asdict(inspection), indent=2, sort_keys=True))
            return 0 if inspection.codex_readable else 2

        if args.command == "access" and args.access_command == "path":
            destination = args.project.expanduser().resolve() / ".research-radar" / "papers"
            print(destination)
            return 0

        if args.command == "access" and args.access_command == "text":
            destination, record, duplicate = export_pdf_text(
                args.project,
                doi=args.doi,
            )
            result = asdict(record)
            result["absolute_text_file"] = str(destination)
            result["duplicate"] = duplicate
            print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
            return 0

        if args.command == "access" and args.access_command == "import":
            destination, record, duplicate = import_pdf(
                args.pdf,
                doi=args.doi,
                project=args.project,
                route=args.route,
                allow_image_only=args.allow_image_only,
                ai_use_status=args.ai_use_status,
                analysis_policy=args.analysis_policy,
                license_name=args.license_name,
                license_url=args.license_url,
            )
            result = asdict(record)
            result["absolute_file"] = str(destination)
            result["duplicate"] = duplicate
            print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
            return 0
    except (AccessError, ProjectError, ValueError) as exc:
        parser.error(str(exc))

    parser.error("Unsupported command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

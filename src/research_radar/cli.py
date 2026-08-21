"""Command-line entry point for Research Radar."""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from dataclasses import asdict
from pathlib import Path

from .access import (
    UOFT_EBSCO_URL,
    AccessError,
    doi_url,
    import_pdf,
    inspect_pdf,
    libkey_url,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="research-radar")
    subparsers = parser.add_subparsers(dest="command", required=True)

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

    return parser


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

        if args.command == "access" and args.access_command == "import":
            destination, record, duplicate = import_pdf(
                args.pdf,
                doi=args.doi,
                project=args.project,
                route=args.route,
                allow_image_only=args.allow_image_only,
                ai_use_status=args.ai_use_status,
                license_name=args.license_name,
                license_url=args.license_url,
            )
            result = asdict(record)
            result["absolute_file"] = str(destination)
            result["duplicate"] = duplicate
            print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
            return 0
    except AccessError as exc:
        parser.error(str(exc))

    parser.error("Unsupported command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Single-paper automatic acquisition with validated institutional fallback."""

from __future__ import annotations

import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .access import (
    AccessError,
    export_pdf_text,
    import_pdf,
    latest_acquisition_record,
    normalize_doi,
    VERIFIED_IDENTITY_STATUSES,
)
from .resolution import AccessOption, AccessResolution, resolve_access


USER_AGENT = "research-radar/0.2 (single-paper acquisition)"
DEFAULT_MAX_BYTES = 100 * 1024 * 1024


@dataclass(frozen=True)
class DownloadReceipt:
    url: str
    final_url: str
    content_type: str | None
    size_bytes: int


@dataclass(frozen=True)
class AcquisitionAttempt:
    route: str
    url: str
    status: str
    detail: str


@dataclass(frozen=True)
class AutomaticAcquisition:
    schema_version: int
    doi: str
    status: str
    pdf_file: str | None
    text_file: str | None
    route: str | None
    license: str | None
    sha256: str | None
    pages: int | None
    text_characters: int | None
    codex_eligible: bool
    identity_verification: str | None
    reading_mode: str | None
    attempts: tuple[AcquisitionAttempt, ...]
    handoff_url: str | None
    resolver_errors: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


Downloader = Callable[[str, Path, int, float], DownloadReceipt]


def download_candidate(
    url: str,
    destination: Path,
    max_bytes: int = DEFAULT_MAX_BYTES,
    timeout: float = 30.0,
) -> DownloadReceipt:
    """Stream one candidate URL to a temporary path with a hard size bound."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise AccessError(f"Unsupported download URL: {url}")
    request = Request(
        url,
        headers={
            "Accept": "application/pdf,application/octet-stream;q=0.9,*/*;q=0.1",
            "User-Agent": USER_AGENT,
        },
    )
    total = 0
    prefix = b""
    with urlopen(request, timeout=timeout) as response, destination.open("wb") as stream:
        content_length = response.headers.get("Content-Length")
        if content_length:
            try:
                declared = int(content_length)
            except ValueError:
                declared = 0
            if declared > max_bytes:
                raise AccessError(
                    f"Candidate PDF declares {declared} bytes, above the {max_bytes}-byte limit."
                )
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise AccessError(
                    f"Candidate PDF exceeded the {max_bytes}-byte download limit."
                )
            if len(prefix) < 5:
                prefix += chunk[: 5 - len(prefix)]
            stream.write(chunk)
        final_url = response.geturl()
        content_type = response.headers.get("Content-Type")
    if not prefix.startswith(b"%PDF-"):
        raise AccessError(
            "The candidate URL returned HTML or another non-PDF payload; authentication may be required."
        )
    return DownloadReceipt(
        url=url,
        final_url=final_url,
        content_type=content_type,
        size_bytes=total,
    )


def _download_options(resolution: AccessResolution) -> tuple[AccessOption, ...]:
    allowed_routes = {"open-access-pdf", "crossref-link"}
    allowed_types = {"full-text", "full-text-candidate"}
    return tuple(
        option
        for option in resolution.options
        if option.route in allowed_routes and option.access_type in allowed_types
    )


def _handoff(resolution: AccessResolution) -> str | None:
    return next(
        (option.url for option in resolution.options if option.route == "libkey"),
        None,
    )


def _recorded_pdf(root: Path, record: dict[str, object]) -> Path | None:
    relative = record.get("file")
    if not isinstance(relative, str):
        return None
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def _policy_restriction(record: dict[str, object], analysis_policy: str) -> str | None:
    if analysis_policy == "strict" and record.get("ai_use_status") == "prohibited":
        return (
            "The existing PDF is recorded as prohibited for AI analysis, so strict "
            "policy will not extract or return its text."
        )
    return None


def acquire_pdf(
    doi: str,
    *,
    project: str | Path,
    analysis_policy: str = "local-test",
    max_bytes: int = DEFAULT_MAX_BYTES,
    timeout: float = 30.0,
    resolution: AccessResolution | None = None,
    downloader: Downloader = download_candidate,
    expected_title: str | None = None,
) -> AutomaticAcquisition:
    """Acquire exactly one DOI, or return an explicit browser-authentication handoff."""
    normalized = normalize_doi(doi)
    root = Path(project).expanduser().resolve()
    attempts: list[AcquisitionAttempt] = []
    existing = latest_acquisition_record(root, normalized)
    existing_pdf = _recorded_pdf(root, existing) if existing else None
    if existing and existing_pdf:
        restriction = _policy_restriction(existing, analysis_policy)
        if restriction:
            return AutomaticAcquisition(
                schema_version=2,
                doi=normalized,
                status="unavailable",
                pdf_file=None,
                text_file=None,
                route=None,
                license=None,
                sha256=None,
                pages=None,
                text_characters=None,
                codex_eligible=False,
                identity_verification=(
                    str(existing.get("identity_verification"))
                    if existing.get("identity_verification")
                    else None
                ),
                reading_mode=(
                    str(existing.get("reading_mode"))
                    if existing.get("reading_mode")
                    else None
                ),
                attempts=(
                    AcquisitionAttempt(
                        route="local-ledger",
                        url=existing_pdf.as_uri(),
                        status="failed",
                        detail=restriction,
                    ),
                ),
                handoff_url=None,
                resolver_errors=(),
            )
        identity_verified = (
            existing.get("identity_verification") in VERIFIED_IDENTITY_STATUSES
        )
        if (
            analysis_policy == "local-test"
            and (not existing.get("codex_eligible") or not identity_verified)
        ):
            try:
                _, refreshed, _ = import_pdf(
                    existing_pdf,
                    doi=normalized,
                    project=root,
                    route=str(existing.get("route") or "manual"),
                    expected_title=expected_title,
                    ai_use_status=str(existing.get("ai_use_status") or "unknown"),
                    analysis_policy=analysis_policy,
                    license_name=(
                        str(existing["license_name"])
                        if existing.get("license_name")
                        else None
                    ),
                    license_url=(
                        str(existing["license_url"])
                        if existing.get("license_url")
                        else None
                    ),
                )
                existing = asdict(refreshed)
            except AccessError as exc:
                attempts.append(
                    AcquisitionAttempt(
                        route="local-ledger",
                        url=existing_pdf.as_uri(),
                        status="failed",
                        detail=f"Existing PDF identity refresh failed: {exc}",
                    )
                )
                existing = None
        if existing.get("codex_eligible"):
            if existing.get("reading_mode") == "visual":
                return AutomaticAcquisition(
                    schema_version=2,
                    doi=normalized,
                    status="existing",
                    pdf_file=existing_pdf.relative_to(root).as_posix(),
                    text_file=None,
                    route=str(existing.get("route") or "existing"),
                    license=(
                        str(existing.get("license_name"))
                        if existing.get("license_name")
                        else None
                    ),
                    sha256=(
                        str(existing.get("sha256"))
                        if existing.get("sha256")
                        else None
                    ),
                    pages=(
                        int(existing["pages"])
                        if existing.get("pages") is not None
                        else None
                    ),
                    text_characters=0,
                    codex_eligible=True,
                    identity_verification=str(existing.get("identity_verification")),
                    reading_mode="visual",
                    attempts=tuple(attempts),
                    handoff_url=None,
                    resolver_errors=(),
                )
            text_path, export, _ = export_pdf_text(root, doi=normalized)
            return AutomaticAcquisition(
                schema_version=2,
                doi=normalized,
                status="existing",
                pdf_file=existing_pdf.relative_to(root).as_posix(),
                text_file=text_path.relative_to(root).as_posix(),
                route=str(existing.get("route") or "existing"),
                license=str(existing.get("license_name")) if existing.get("license_name") else None,
                sha256=str(existing.get("sha256")) if existing.get("sha256") else None,
                pages=int(existing["pages"]) if existing.get("pages") is not None else export.pages,
                text_characters=export.text_characters,
                codex_eligible=bool(existing.get("codex_eligible")),
                identity_verification=str(existing.get("identity_verification")),
                reading_mode=str(existing.get("reading_mode") or "text"),
                attempts=(),
                handoff_url=None,
                resolver_errors=(),
            )

    resolution = resolution or resolve_access(
        normalized,
        cache_dir=root / ".research-radar" / "cache" / "access",
    )
    with tempfile.TemporaryDirectory(prefix="research-radar-acquire-") as temporary:
        candidate_path = Path(temporary) / "candidate.pdf"
        for option in _download_options(resolution):
            try:
                receipt = downloader(option.url, candidate_path, max_bytes, timeout)
                route = "open-access" if option.route == "open-access-pdf" else "publisher"
                destination, record, duplicate = import_pdf(
                    candidate_path,
                    doi=normalized,
                    project=root,
                    route=route,
                    expected_title=expected_title,
                    ai_use_status="allowed" if option.license else "unknown",
                    analysis_policy=analysis_policy,
                    license_name=option.license,
                )
                text_path, export, _ = export_pdf_text(root, doi=normalized)
                attempts.append(
                    AcquisitionAttempt(
                        route=option.route,
                        url=option.url,
                        status="acquired" if not duplicate else "existing",
                        detail=(
                            f"{receipt.size_bytes} bytes; final URL {receipt.final_url}"
                        ),
                    )
                )
                return AutomaticAcquisition(
                    schema_version=2,
                    doi=normalized,
                    status="existing" if duplicate else "acquired",
                    pdf_file=destination.relative_to(root).as_posix(),
                    text_file=text_path.relative_to(root).as_posix(),
                    route=record.route,
                    license=record.license_name,
                    sha256=record.sha256,
                    pages=record.pages,
                    text_characters=export.text_characters,
                    codex_eligible=record.codex_eligible,
                    identity_verification=record.identity_verification,
                    reading_mode=record.reading_mode,
                    attempts=tuple(attempts),
                    handoff_url=None,
                    resolver_errors=resolution.errors,
                )
            except Exception as exc:
                attempts.append(
                    AcquisitionAttempt(
                        route=option.route,
                        url=option.url,
                        status="failed",
                        detail=str(exc),
                    )
                )
                candidate_path.unlink(missing_ok=True)

    handoff = _handoff(resolution)
    return AutomaticAcquisition(
        schema_version=2,
        doi=normalized,
        status="authentication-required" if handoff else "unavailable",
        pdf_file=None,
        text_file=None,
        route=None,
        license=None,
        sha256=None,
        pages=None,
        text_characters=None,
        codex_eligible=False,
        identity_verification=None,
        reading_mode=None,
        attempts=tuple(attempts),
        handoff_url=handoff,
        resolver_errors=resolution.errors,
    )

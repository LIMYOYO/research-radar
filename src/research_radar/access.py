"""Legal paper-access routing and local PDF ingestion."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from pypdf import PdfReader


DOI_PATTERN = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
UOFT_EBSCO_URL = (
    "https://go.openathens.net/redirector/utoronto.ca?url="
    "https%3A%2F%2Fresearch.ebsco.com%2Fc%2Fgsemyh%2Fsearch%2Fadvanced%2Ffilters"
    "%3Fautocorrect%3Dy%26defaultdb%3Dbuh"
)
VALID_ROUTES = {
    "libkey",
    "uoft-ebsco",
    "open-access",
    "publisher",
    "manual",
}
AI_USE_STATUSES = {"allowed", "prohibited", "unknown"}


class AccessError(ValueError):
    """Raised when an access or PDF-ingestion input is invalid."""


@dataclass(frozen=True)
class PdfInspection:
    path: str
    sha256: str
    size_bytes: int
    pages: int
    text_characters: int
    encrypted: bool
    codex_readable: bool
    text_extraction_performed: bool


@dataclass(frozen=True)
class AcquisitionRecord:
    schema_version: int
    acquired_at: str
    doi: str
    route: str
    file: str
    source_filename: str
    sha256: str
    size_bytes: int
    pages: int
    text_characters: int
    codex_readable: bool
    text_extraction_performed: bool
    ai_use_status: str
    codex_eligible: bool
    license_name: str | None
    license_url: str | None


def normalize_doi(value: str) -> str:
    """Extract and normalize a DOI from a DOI, URL, or surrounding text."""
    if not isinstance(value, str) or not value.strip():
        raise AccessError("A DOI is required.")

    match = DOI_PATTERN.search(value.strip())
    if not match:
        raise AccessError(f"No valid DOI found in: {value!r}")

    doi = match.group(0).rstrip(".,;:!?\"'`")
    pairs = (("(", ")"), ("[", "]"), ("{", "}"), ("<", ">"))
    for opening, closing in pairs:
        while doi.endswith(closing) and doi.count(closing) > doi.count(opening):
            doi = doi[:-1]
    return doi.lower()


def doi_url(doi: str) -> str:
    normalized = normalize_doi(doi)
    encoded = "/".join(quote(part, safe="") for part in normalized.split("/"))
    return f"https://doi.org/{encoded}"


def libkey_url(doi: str) -> str:
    normalized = normalize_doi(doi)
    encoded = "/".join(quote(part, safe="") for part in normalized.split("/"))
    return f"https://libkey.io/{encoded}"


def paper_filename(doi: str) -> str:
    normalized = normalize_doi(doi)
    safe_name = re.sub(r"[^a-z0-9._-]+", "_", normalized)
    return f"{safe_name}.pdf"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_pdf(
    path: str | Path, *, extract_text: bool = True
) -> PdfInspection:
    """Validate a PDF and optionally test whether it exposes extractable text."""
    pdf_path = Path(path).expanduser().resolve()
    if not pdf_path.is_file():
        raise AccessError(f"PDF does not exist: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise AccessError(f"Expected a .pdf file: {pdf_path}")

    try:
        reader = PdfReader(str(pdf_path))
        encrypted = bool(reader.is_encrypted)
        if encrypted:
            raise AccessError(
                "The PDF is encrypted and cannot be safely archived for Codex reading."
            )
        pages = len(reader.pages)
        if pages < 1:
            raise AccessError("The PDF contains no pages.")
        extracted = (
            "".join((page.extract_text() or "") for page in reader.pages)
            if extract_text
            else ""
        )
    except AccessError:
        raise
    except Exception as exc:
        raise AccessError(f"The file is not a readable PDF: {exc}") from exc

    text_characters = len(extracted.strip())
    return PdfInspection(
        path=str(pdf_path),
        sha256=sha256_file(pdf_path),
        size_bytes=pdf_path.stat().st_size,
        pages=pages,
        text_characters=text_characters,
        encrypted=encrypted,
        codex_readable=extract_text and text_characters > 0,
        text_extraction_performed=extract_text,
    )


def import_pdf(
    source: str | Path,
    *,
    doi: str,
    project: str | Path,
    route: str,
    allow_image_only: bool = False,
    ai_use_status: str = "unknown",
    license_name: str | None = None,
    license_url: str | None = None,
) -> tuple[Path, AcquisitionRecord, bool]:
    """Validate and archive one user-authorized PDF under a research project."""
    normalized_doi = normalize_doi(doi)
    if route not in VALID_ROUTES:
        choices = ", ".join(sorted(VALID_ROUTES))
        raise AccessError(f"Unknown route {route!r}; choose one of: {choices}")
    if ai_use_status not in AI_USE_STATUSES:
        choices = ", ".join(sorted(AI_USE_STATUSES))
        raise AccessError(
            f"Unknown AI-use status {ai_use_status!r}; choose one of: {choices}"
        )

    source_path = Path(source).expanduser().resolve()
    inspection = inspect_pdf(
        source_path, extract_text=ai_use_status != "prohibited"
    )
    if (
        ai_use_status != "prohibited"
        and not inspection.codex_readable
        and not allow_image_only
    ):
        raise AccessError(
            "The PDF has no extractable text. Use --allow-image-only to archive it "
            "for later OCR or visual reading."
        )

    project_root = Path(project).expanduser().resolve()
    radar_root = project_root / ".research-radar"
    papers_dir = radar_root / "papers"
    papers_dir.mkdir(parents=True, exist_ok=True)
    destination = papers_dir / paper_filename(normalized_doi)

    duplicate = False
    if destination.exists():
        if sha256_file(destination) == inspection.sha256:
            duplicate = True
        else:
            destination = destination.with_name(
                f"{destination.stem}-{inspection.sha256[:8]}.pdf"
            )

    if not duplicate:
        shutil.copy2(source_path, destination)

    relative_file = destination.relative_to(project_root).as_posix()
    record = AcquisitionRecord(
        schema_version=1,
        acquired_at=datetime.now(timezone.utc).isoformat(),
        doi=normalized_doi,
        route=route,
        file=relative_file,
        source_filename=source_path.name,
        sha256=inspection.sha256,
        size_bytes=inspection.size_bytes,
        pages=inspection.pages,
        text_characters=inspection.text_characters,
        codex_readable=inspection.codex_readable,
        text_extraction_performed=inspection.text_extraction_performed,
        ai_use_status=ai_use_status,
        codex_eligible=inspection.codex_readable and ai_use_status == "allowed",
        license_name=license_name,
        license_url=license_url,
    )

    if not duplicate:
        ledger = radar_root / "access-ledger.jsonl"
        with ledger.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(asdict(record), ensure_ascii=False, sort_keys=True))
            stream.write("\n")

    return destination, record, duplicate

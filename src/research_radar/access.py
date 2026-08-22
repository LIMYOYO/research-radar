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
ANALYSIS_POLICIES = {"local-test", "strict"}


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
    analysis_policy: str
    codex_eligible: bool
    license_name: str | None
    license_url: str | None


@dataclass(frozen=True)
class TextExport:
    schema_version: int
    doi: str
    pdf_file: str
    text_file: str
    pages: int
    text_characters: int
    sha256: str
    analysis_policy: str


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
    analysis_policy: str = "local-test",
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
    if analysis_policy not in ANALYSIS_POLICIES:
        choices = ", ".join(sorted(ANALYSIS_POLICIES))
        raise AccessError(
            f"Unknown analysis policy {analysis_policy!r}; choose one of: {choices}"
        )

    source_path = Path(source).expanduser().resolve()
    extraction_allowed = not (
        analysis_policy == "strict" and ai_use_status == "prohibited"
    )
    inspection = inspect_pdf(
        source_path, extract_text=extraction_allowed
    )
    if (
        extraction_allowed
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
        analysis_policy=analysis_policy,
        codex_eligible=inspection.codex_readable and extraction_allowed,
        license_name=license_name,
        license_url=license_url,
    )

    record_value = asdict(record)
    comparison_fields = tuple(
        key for key in record_value if key not in {"acquired_at", "source_filename"}
    )
    previous = latest_acquisition_record(project_root, normalized_doi) if duplicate else None
    policy_changed = bool(
        duplicate
        and (
            previous is None
            or any(previous.get(key) != record_value[key] for key in comparison_fields)
        )
    )
    if not duplicate or policy_changed:
        ledger = radar_root / "access-ledger.jsonl"
        with ledger.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record_value, ensure_ascii=False, sort_keys=True))
            stream.write("\n")

    return destination, record, duplicate


def _ledger_records(project_root: Path) -> list[dict[str, object]]:
    ledger = project_root / ".research-radar" / "access-ledger.jsonl"
    if not ledger.is_file():
        return []
    records: list[dict[str, object]] = []
    for number, line in enumerate(ledger.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AccessError(f"Invalid access ledger JSON on line {number}: {exc}") from exc
        if isinstance(value, dict):
            records.append(value)
    return records


def latest_acquisition_record(
    project: str | Path, doi: str
) -> dict[str, object] | None:
    """Return the newest ledger record for one DOI, if any."""
    root = Path(project).expanduser().resolve()
    normalized = normalize_doi(doi)
    matching = [
        record for record in _ledger_records(root) if record.get("doi") == normalized
    ]
    return matching[-1] if matching else None


def export_pdf_text(
    project: str | Path,
    *,
    doi: str,
) -> tuple[Path, TextExport, bool]:
    """Export page-delimited text from an archived PDF for local Codex reading."""
    normalized_doi = normalize_doi(doi)
    project_root = Path(project).expanduser().resolve()
    matching = [
        record
        for record in _ledger_records(project_root)
        if record.get("doi") == normalized_doi
    ]
    if not matching:
        raise AccessError(
            f"No archived access record for {normalized_doi}. Run `research-radar access import` first."
        )
    record = matching[-1]
    if not record.get("codex_eligible"):
        raise AccessError(
            f"The archived record for {normalized_doi} is not eligible for Codex reading under its recorded policy."
        )
    relative_pdf = record.get("file")
    if not isinstance(relative_pdf, str):
        raise AccessError(f"The access record for {normalized_doi} has no valid file path.")
    pdf_path = (project_root / relative_pdf).resolve()
    try:
        pdf_path.relative_to(project_root)
    except ValueError as exc:
        raise AccessError("The access ledger points outside the research project.") from exc
    inspection = inspect_pdf(pdf_path)
    reader = PdfReader(str(pdf_path))
    page_text = [
        f"\n\n--- Page {index} ---\n\n{page.extract_text() or ''}"
        for index, page in enumerate(reader.pages, start=1)
    ]
    text = "".join(page_text).strip() + "\n"
    if not text.strip():
        raise AccessError(f"No extractable text found in {pdf_path}.")
    text_dir = project_root / ".research-radar" / "texts"
    text_dir.mkdir(parents=True, exist_ok=True)
    destination = text_dir / f"{Path(paper_filename(normalized_doi)).stem}.txt"
    duplicate = destination.is_file() and destination.read_text(encoding="utf-8") == text
    if not duplicate:
        destination.write_text(text, encoding="utf-8")
    result = TextExport(
        schema_version=1,
        doi=normalized_doi,
        pdf_file=pdf_path.relative_to(project_root).as_posix(),
        text_file=destination.relative_to(project_root).as_posix(),
        pages=inspection.pages,
        text_characters=len(text),
        sha256=inspection.sha256,
        analysis_policy=str(record.get("analysis_policy") or "legacy"),
    )
    return destination, result, duplicate

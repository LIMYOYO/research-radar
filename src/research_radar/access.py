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
VERIFIED_IDENTITY_STATUSES = {
    "doi-match",
    "title-match",
    "visual-doi-match",
    "visual-title-match",
}
VISUAL_IDENTITY_STATUSES = {"visual-doi-match", "visual-title-match"}


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
    detected_dois: tuple[str, ...]
    identity_verification: str
    identity_note: str


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
    identity_verification: str
    identity_note: str
    detected_dois: tuple[str, ...]
    reading_mode: str
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
    text_sha256: str
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


def _identity_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def inspect_pdf(
    path: str | Path,
    *,
    extract_text: bool = True,
    expected_doi: str | None = None,
    expected_title: str | None = None,
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
    detected_dois = tuple(
        dict.fromkeys(
            normalize_doi(match.group(0))
            for match in DOI_PATTERN.finditer(extracted)
        )
    )
    normalized_expected = normalize_doi(expected_doi) if expected_doi else None
    normalized_title = _identity_text(expected_title or "")
    normalized_text = _identity_text(extracted)
    if normalized_expected is None:
        identity_verification = "not-checked"
        identity_note = "No expected DOI was supplied for identity verification."
    elif not extract_text:
        identity_verification = "not-checked-policy"
        identity_note = "Text extraction was disabled by the selected policy."
    elif normalized_expected in detected_dois:
        identity_verification = "doi-match"
        identity_note = f"The extracted PDF text contains {normalized_expected}."
    elif (
        len(normalized_title) >= 24
        and len(normalized_title.split()) >= 4
        and normalized_title in normalized_text
    ):
        identity_verification = "title-match"
        identity_note = "The normalized expected title appears in the extracted PDF text."
    elif text_characters == 0:
        identity_verification = "pending-visual"
        identity_note = "The PDF has no extractable text; identity requires visual review or OCR."
    else:
        identity_verification = "unverified"
        identity_note = (
            "Neither the expected DOI nor the full normalized expected title was found "
            "in the extracted PDF text."
        )
    return PdfInspection(
        path=str(pdf_path),
        sha256=sha256_file(pdf_path),
        size_bytes=pdf_path.stat().st_size,
        pages=pages,
        text_characters=text_characters,
        encrypted=encrypted,
        codex_readable=extract_text and text_characters > 0,
        text_extraction_performed=extract_text,
        detected_dois=detected_dois,
        identity_verification=identity_verification,
        identity_note=identity_note,
    )


def import_pdf(
    source: str | Path,
    *,
    doi: str,
    project: str | Path,
    route: str,
    allow_image_only: bool = False,
    expected_title: str | None = None,
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
        source_path,
        extract_text=extraction_allowed,
        expected_doi=normalized_doi,
        expected_title=expected_title,
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
    identity_verified = inspection.identity_verification in VERIFIED_IDENTITY_STATUSES
    if (
        extraction_allowed
        and inspection.codex_readable
        and not identity_verified
    ):
        raise AccessError(
            f"PDF identity could not be verified for {normalized_doi}: "
            f"{inspection.identity_note} Refusing to archive it under that DOI."
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
        schema_version=2,
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
        codex_eligible=(
            inspection.codex_readable and extraction_allowed and identity_verified
        ),
        identity_verification=inspection.identity_verification,
        identity_note=inspection.identity_note,
        detected_dois=inspection.detected_dois,
        reading_mode=(
            "text"
            if inspection.codex_readable and identity_verified
            else (
                "visual-pending"
                if inspection.identity_verification == "pending-visual"
                else "unavailable"
            )
        ),
        license_name=license_name,
        license_url=license_url,
    )

    # Compare the same JSON-native representation that is persisted in the
    # append-only ledger (dataclass tuples otherwise reload as lists).
    record_value = json.loads(
        json.dumps(asdict(record), ensure_ascii=False, sort_keys=True)
    )
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


def confirm_visual_pdf(
    project: str | Path,
    *,
    doi: str,
    identity_verification: str,
    pages_reviewed: int,
    note: str,
) -> AcquisitionRecord:
    """Record an explicit all-page visual review of an archived image-only PDF."""
    if identity_verification not in VISUAL_IDENTITY_STATUSES:
        raise AccessError(
            "Visual identity must be visual-doi-match or visual-title-match."
        )
    if not note.strip():
        raise AccessError("A visual-review note is required.")
    project_root = Path(project).expanduser().resolve()
    normalized_doi = normalize_doi(doi)
    previous = latest_acquisition_record(project_root, normalized_doi)
    if not previous:
        raise AccessError(f"No archived PDF exists for {normalized_doi}.")
    if previous.get("identity_verification") != "pending-visual":
        raise AccessError(
            "Visual confirmation is only valid for an image-only PDF recorded as "
            "pending-visual."
        )
    if (
        previous.get("analysis_policy") == "strict"
        and previous.get("ai_use_status") == "prohibited"
    ):
        raise AccessError(
            "Strict policy prohibits promoting this PDF for Codex visual reading."
        )
    relative_pdf = previous.get("file")
    if not isinstance(relative_pdf, str):
        raise AccessError("The access ledger has no valid PDF path.")
    pdf_path = (project_root / relative_pdf).resolve()
    try:
        pdf_path.relative_to(project_root)
    except ValueError as exc:
        raise AccessError("The access ledger points outside the research project.") from exc
    inspection = inspect_pdf(pdf_path, extract_text=False)
    if inspection.sha256 != previous.get("sha256"):
        raise AccessError("The archived PDF checksum changed before visual confirmation.")
    if pages_reviewed != inspection.pages:
        raise AccessError(
            f"Visual confirmation requires all {inspection.pages} page(s); "
            f"received {pages_reviewed}."
        )
    updated = dict(previous)
    updated.update(
        {
            "schema_version": 2,
            "acquired_at": datetime.now(timezone.utc).isoformat(),
            "codex_eligible": True,
            "identity_verification": identity_verification,
            "identity_note": note.strip(),
            "reading_mode": "visual",
        }
    )
    ledger = project_root / ".research-radar" / "access-ledger.jsonl"
    with ledger.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(updated, ensure_ascii=False, sort_keys=True))
        stream.write("\n")
    updated["detected_dois"] = tuple(updated.get("detected_dois") or ())
    return AcquisitionRecord(**updated)


def verified_pdf_path(project: str | Path, doi: str) -> Path | None:
    """Return an archived PDF only when identity, containment, and checksum verify."""
    project_root = Path(project).expanduser().resolve()
    normalized_doi = normalize_doi(doi)
    record = latest_acquisition_record(project_root, normalized_doi)
    if (
        not record
        or not record.get("codex_eligible")
        or record.get("identity_verification") not in VERIFIED_IDENTITY_STATUSES
    ):
        return None
    relative_pdf = record.get("file")
    if not isinstance(relative_pdf, str):
        return None
    pdf_path = (project_root / relative_pdf).resolve()
    try:
        pdf_path.relative_to(project_root)
    except ValueError:
        return None
    if not pdf_path.is_file() or sha256_file(pdf_path) != record.get("sha256"):
        return None
    return pdf_path


def verified_text_path(project: str | Path, doi: str) -> Path | None:
    """Return exported text only when its PDF and sidecar checksums still verify."""
    project_root = Path(project).expanduser().resolve()
    normalized_doi = normalize_doi(doi)
    record = latest_acquisition_record(project_root, normalized_doi)
    if not record:
        return None
    if verified_pdf_path(project_root, normalized_doi) is None:
        return None
    stem = Path(paper_filename(normalized_doi)).stem
    text_path = project_root / ".research-radar" / "texts" / f"{stem}.txt"
    sidecar = text_path.with_suffix(".json")
    if not text_path.is_file() or not sidecar.is_file():
        return None
    try:
        metadata = json.loads(sidecar.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if (
        metadata.get("doi") != normalized_doi
        or metadata.get("sha256") != record.get("sha256")
        or metadata.get("text_sha256") != sha256_file(text_path)
    ):
        return None
    return text_path


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
    recorded_sha256 = record.get("sha256")
    if recorded_sha256 and inspection.sha256 != recorded_sha256:
        raise AccessError(
            f"The archived PDF checksum for {normalized_doi} no longer matches its ledger record."
        )
    if record.get("identity_verification") not in VERIFIED_IDENTITY_STATUSES:
        raise AccessError(
            f"The archived PDF for {normalized_doi} lacks verified DOI/title identity; "
            "re-import it with the current Research Radar version."
        )
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
        text_sha256=sha256_file(destination),
        analysis_policy=str(record.get("analysis_policy") or "legacy"),
    )
    sidecar = destination.with_suffix(".json")
    sidecar_payload = json.dumps(
        asdict(result), ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n"
    if not sidecar.is_file() or sidecar.read_text(encoding="utf-8") != sidecar_payload:
        sidecar.write_text(sidecar_payload, encoding="utf-8")
    return destination, result, duplicate

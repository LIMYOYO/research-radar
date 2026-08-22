"""Read a research folder without modifying its manuscript sources."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import bibtexparser

from .access import AccessError, normalize_doi


IGNORED_DIRECTORIES = {".git", ".research-radar", ".venv", "node_modules"}
PROFILE_FILENAMES = ("RESEARCH_PROFILE.md", "README.md")
CITATION_PATTERN = re.compile(
    r"\\(?:cite|citep|citet|parencite|textcite|autocite)\*?"
    r"(?:\[[^\]]*\]){0,2}\{([^}]+)\}"
)
INPUT_PATTERN = re.compile(r"\\(?:input|include)\{([^}]+)\}")
BIBLIOGRAPHY_PATTERN = re.compile(r"\\bibliography\{([^}]+)\}")
ADDBIBRESOURCE_PATTERN = re.compile(
    r"\\addbibresource(?:\[[^\]]*\])?\{([^}]+)\}"
)
COMMAND_WITH_TEXT_PATTERN = re.compile(
    r"\\(?:title|section|subsection|subsubsection|paragraph|emph|textbf|textit)"
    r"\*?\{([^{}]*)\}"
)
DOI_FIELD_CANDIDATES = ("doi", "url", "note")
ARXIV_PATTERN = re.compile(
    r"(?:arxiv(?:\.org/(?:abs|pdf)/|:)?\s*)?(\d{4}\.\d{4,5}(?:v\d+)?)",
    re.IGNORECASE,
)


class ProjectError(ValueError):
    """Raised when a research project cannot be ingested safely."""


@dataclass(frozen=True)
class SourceFile:
    path: str
    kind: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class SeedPaper:
    citation_key: str
    title: str | None
    authors: tuple[str, ...]
    year: int | None
    venue: str | None
    doi: str | None
    preprint_id: str | None
    url: str | None
    entry_type: str | None
    source_file: str
    cited_in_manuscript: bool

    @property
    def identity(self) -> str:
        if self.doi:
            return f"doi:{self.doi}"
        if self.preprint_id:
            return f"preprint:{self.preprint_id.lower()}"
        normalized_title = normalize_title(self.title or "")
        if normalized_title:
            return f"title:{normalized_title}"
        return f"bibkey:{self.citation_key.lower()}"


@dataclass(frozen=True)
class ResearchProfile:
    source_file: str
    project_name: str
    raw_markdown: str
    sections: dict[str, str]


@dataclass(frozen=True)
class ProjectSnapshot:
    schema_version: int
    project_root: str
    fingerprint: str
    profile: ResearchProfile
    manuscript_text: str
    cited_keys: tuple[str, ...]
    seeds: tuple[SeedPaper, ...]
    duplicate_identities: dict[str, tuple[str, ...]]
    source_files: tuple[SourceFile, ...]

    def to_dict(self, *, include_text: bool = False) -> dict[str, object]:
        value = asdict(self)
        if not include_text:
            value["manuscript_text"] = ""
            profile = dict(value["profile"])
            profile["raw_markdown"] = ""
            value["profile"] = profile
        return value


def _is_ignored(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    return any(part in IGNORED_DIRECTORIES for part in relative.parts)


def discover_files(root: Path, suffix: str) -> list[Path]:
    return sorted(
        path
        for path in root.rglob(f"*{suffix}")
        if path.is_file() and not _is_ignored(path, root)
    )


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_file(path: Path, root: Path, kind: str) -> SourceFile:
    return SourceFile(
        path=path.relative_to(root).as_posix(),
        kind=kind,
        sha256=sha256_path(path),
        size_bytes=path.stat().st_size,
    )


def find_profile(root: Path) -> Path:
    for filename in PROFILE_FILENAMES:
        candidate = root / filename
        if candidate.is_file():
            return candidate
    choices = " or ".join(PROFILE_FILENAMES)
    raise ProjectError(f"No research profile found. Add {choices} to {root}.")


def parse_markdown_sections(markdown: str) -> tuple[str, dict[str, str]]:
    project_name = "Untitled research project"
    sections: dict[str, list[str]] = {"overview": []}
    current = "overview"
    for line in markdown.splitlines():
        heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if heading:
            title = heading.group(2).strip().strip("#").strip()
            if len(heading.group(1)) == 1 and project_name == "Untitled research project":
                project_name = title
            current = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "section"
            sections.setdefault(current, [])
        else:
            sections.setdefault(current, []).append(line)
    normalized = {
        name: "\n".join(lines).strip()
        for name, lines in sections.items()
        if "\n".join(lines).strip()
    }
    return project_name, normalized


def read_profile(root: Path) -> tuple[ResearchProfile, SourceFile]:
    path = find_profile(root)
    markdown = path.read_text(encoding="utf-8")
    if not markdown.strip():
        raise ProjectError(f"Research profile is empty: {path}")
    project_name, sections = parse_markdown_sections(markdown)
    return (
        ResearchProfile(
            source_file=path.relative_to(root).as_posix(),
            project_name=project_name,
            raw_markdown=markdown,
            sections=sections,
        ),
        _source_file(path, root, "profile"),
    )


def strip_tex_comments(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        match = re.search(r"(?<!\\)%", line)
        lines.append(line[: match.start()] if match else line)
    return "\n".join(lines)


def tex_to_text(text: str) -> str:
    cleaned = strip_tex_comments(text)
    previous = None
    while previous != cleaned:
        previous = cleaned
        cleaned = COMMAND_WITH_TEXT_PATTERN.sub(r"\1\n", cleaned)
    cleaned = re.sub(r"\\begin\{[^}]+\}|\\end\{[^}]+\}", "\n", cleaned)
    cleaned = re.sub(r"\\(?:label|ref|eqref|cite\w*)\*?(?:\[[^\]]*\]){0,2}\{[^}]*\}", " ", cleaned)
    cleaned = re.sub(r"\\[a-zA-Z@]+\*?(?:\[[^\]]*\])?", " ", cleaned)
    cleaned = cleaned.replace("{", " ").replace("}", " ")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _resolve_local_source(
    root: Path,
    parent: Path,
    value: str,
    suffix: str,
) -> Path | None:
    candidate = (parent / value.strip()).resolve()
    if not candidate.suffix:
        candidate = candidate.with_suffix(suffix)
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate if candidate.is_file() and not _is_ignored(candidate, root) else None


def _main_tex_files(root: Path) -> list[Path]:
    preferred = root / "paper.tex"
    if preferred.is_file():
        return [preferred]
    discovered = discover_files(root, ".tex")
    named_paper = [path for path in discovered if path.name.lower() == "paper.tex"]
    if len(named_paper) == 1:
        return named_paper
    return discovered


def _manuscript_graph(root: Path) -> list[Path]:
    queue = list(_main_tex_files(root))
    visited: set[Path] = set()
    ordered: list[Path] = []
    while queue:
        path = queue.pop(0).resolve()
        if path in visited:
            continue
        visited.add(path)
        ordered.append(path)
        raw = strip_tex_comments(path.read_text(encoding="utf-8"))
        for match in INPUT_PATTERN.finditer(raw):
            child = _resolve_local_source(root, path.parent, match.group(1), ".tex")
            if child and child not in visited:
                queue.append(child)
    return ordered


def read_manuscript(
    root: Path,
) -> tuple[str, tuple[str, ...], list[SourceFile], tuple[Path, ...]]:
    tex_files = _manuscript_graph(root)
    parts: list[str] = []
    cited: set[str] = set()
    sources: list[SourceFile] = []
    bibliography_files: set[Path] = set()
    for path in tex_files:
        raw = path.read_text(encoding="utf-8")
        uncommented = strip_tex_comments(raw)
        for match in CITATION_PATTERN.finditer(uncommented):
            cited.update(key.strip() for key in match.group(1).split(",") if key.strip())
        for match in BIBLIOGRAPHY_PATTERN.finditer(uncommented):
            for value in match.group(1).split(","):
                bibliography = _resolve_local_source(root, path.parent, value, ".bib")
                if bibliography:
                    bibliography_files.add(bibliography)
        for match in ADDBIBRESOURCE_PATTERN.finditer(uncommented):
            bibliography = _resolve_local_source(
                root, path.parent, match.group(1), ".bib"
            )
            if bibliography:
                bibliography_files.add(bibliography)
        rendered = tex_to_text(raw)
        if rendered:
            parts.append(rendered)
        sources.append(_source_file(path, root, "tex"))
    return (
        "\n\n".join(parts),
        tuple(sorted(cited)),
        sources,
        tuple(sorted(bibliography_files)),
    )


def normalize_title(value: str) -> str:
    value = re.sub(r"[{}]", "", value or "")
    value = re.sub(r"\\[a-zA-Z]+", "", value)
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _clean_bib_value(value: object) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"\s+", " ", str(value)).strip()
    return cleaned or None


def _parse_year(value: object) -> int | None:
    match = re.search(r"(?:19|20)\d{2}", str(value or ""))
    return int(match.group(0)) if match else None


def _parse_authors(value: object) -> tuple[str, ...]:
    cleaned = _clean_bib_value(value)
    if not cleaned:
        return ()
    return tuple(part.strip() for part in re.split(r"\s+and\s+", cleaned) if part.strip())


def _entry_doi(entry: dict[str, object]) -> str | None:
    for field in DOI_FIELD_CANDIDATES:
        value = entry.get(field)
        if not value:
            continue
        try:
            return normalize_doi(str(value))
        except AccessError:
            continue
    return None


def _entry_preprint_id(entry: dict[str, object]) -> str | None:
    archive = str(entry.get("archiveprefix") or entry.get("archivePrefix") or "")
    values = [entry.get("eprint"), entry.get("url"), entry.get("note")]
    for value in values:
        if not value:
            continue
        match = ARXIV_PATTERN.search(str(value))
        if match and (archive.lower() == "arxiv" or "arxiv" in str(value).lower()):
            return f"arxiv:{match.group(1).lower()}"
    return None


def _validate_bibtex_structure(text: str, relative_path: Path) -> int:
    """Detect common corruption that bibtexparser otherwise drops silently."""
    entry_starts: list[tuple[str, int, bool]] = []
    for match in re.finditer(r"(?m)^\s*@([A-Za-z]+)\s*([^\s])?", text):
        entry_type = match.group(1).lower()
        if entry_type in {"comment", "preamble", "string"}:
            continue
        line = text.count("\n", 0, match.start()) + 1
        entry_starts.append((entry_type, line, match.group(2) in {"{", "("}))
    malformed_start = next((item for item in entry_starts if not item[2]), None)
    if malformed_start:
        entry_type, line, _ = malformed_start
        raise ProjectError(
            f"Malformed BibTeX in {relative_path} at line {line}: "
            f"@{entry_type} must be followed by '{{' or '('."
        )

    depth = 0
    escaped = False
    in_comment = False
    for offset, character in enumerate(text):
        if in_comment:
            if character == "\n":
                in_comment = False
            continue
        if character == "%" and not escaped:
            in_comment = True
            continue
        if character == "\\" and not escaped:
            escaped = True
            continue
        if character == "{" and not escaped:
            depth += 1
        elif character == "}" and not escaped:
            depth -= 1
            if depth < 0:
                line = text.count("\n", 0, offset) + 1
                raise ProjectError(
                    f"Malformed BibTeX in {relative_path} at line {line}: "
                    "unexpected closing brace."
                )
        escaped = False
    if depth:
        raise ProjectError(
            f"Malformed BibTeX in {relative_path}: {depth} unclosed '{{' delimiter(s)."
        )
    return len(entry_starts)


def parse_bibliography(
    root: Path,
    cited_keys: Iterable[str],
    bibliography_files: Iterable[Path] = (),
) -> tuple[tuple[SeedPaper, ...], list[SourceFile]]:
    cited = {key.lower() for key in cited_keys}
    seeds: list[SeedPaper] = []
    sources: list[SourceFile] = []
    selected = tuple(bibliography_files)
    paths = list(selected) if selected else discover_files(root, ".bib")
    for path in paths:
        relative = path.relative_to(root)
        raw_bibtex = path.read_text(encoding="utf-8")
        expected_entries = _validate_bibtex_structure(raw_bibtex, relative)
        try:
            database = bibtexparser.loads(raw_bibtex)
        except Exception as exc:
            raise ProjectError(f"Could not parse BibTeX file {relative}: {exc}") from exc
        if len(database.entries) != expected_entries:
            raise ProjectError(
                f"Malformed BibTeX in {relative}: found {expected_entries} entry "
                f"start(s) but parsed {len(database.entries)}. Check commas, citation keys, "
                "and closing delimiters."
            )
        for entry in database.entries:
            key = str(entry.get("ID") or "").strip()
            if not key:
                raise ProjectError(
                    f"BibTeX entry without a citation key in {path.relative_to(root)}"
                )
            venue = entry.get("journal") or entry.get("booktitle") or entry.get("publisher")
            seeds.append(
                SeedPaper(
                    citation_key=key,
                    title=_clean_bib_value(entry.get("title")),
                    authors=_parse_authors(entry.get("author")),
                    year=_parse_year(entry.get("year")),
                    venue=_clean_bib_value(venue),
                    doi=_entry_doi(entry),
                    preprint_id=_entry_preprint_id(entry),
                    url=_clean_bib_value(entry.get("url")),
                    entry_type=_clean_bib_value(entry.get("ENTRYTYPE")),
                    source_file=path.relative_to(root).as_posix(),
                    cited_in_manuscript=key.lower() in cited,
                )
            )
        sources.append(_source_file(path, root, "bib"))
    return tuple(seeds), sources


def duplicate_identities(seeds: Iterable[SeedPaper]) -> dict[str, tuple[str, ...]]:
    identities: dict[str, list[str]] = {}
    for seed in seeds:
        identities.setdefault(seed.identity, []).append(seed.citation_key)
    return {
        identity: tuple(keys)
        for identity, keys in identities.items()
        if len(keys) > 1
    }


def ingest_project(project: str | Path) -> ProjectSnapshot:
    root = Path(project).expanduser().resolve()
    if not root.is_dir():
        raise ProjectError(f"Project directory does not exist: {root}")

    profile, profile_source = read_profile(root)
    manuscript_text, cited_keys, manuscript_sources, bibliography_files = read_manuscript(root)
    seeds, bib_sources = parse_bibliography(root, cited_keys, bibliography_files)
    source_files = tuple([profile_source, *manuscript_sources, *bib_sources])
    fingerprint_payload = {
        "profile": profile.raw_markdown,
        "manuscript_text": manuscript_text,
        "seeds": [asdict(seed) for seed in seeds],
    }
    fingerprint = hashlib.sha256(
        json.dumps(fingerprint_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return ProjectSnapshot(
        schema_version=1,
        project_root=str(root),
        fingerprint=fingerprint,
        profile=profile,
        manuscript_text=manuscript_text,
        cited_keys=cited_keys,
        seeds=seeds,
        duplicate_identities=duplicate_identities(seeds),
        source_files=source_files,
    )

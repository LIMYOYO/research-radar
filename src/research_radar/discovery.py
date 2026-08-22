"""Crossref/OpenAlex discovery with source provenance and failure isolation."""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import time
from difflib import SequenceMatcher
from dataclasses import asdict, dataclass, replace
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from .access import AccessError, normalize_doi
from .config import configured_watch, load_config
from .project import ProjectSnapshot, SeedPaper, normalize_title, require_profile_ready


CROSSREF_API = "https://api.crossref.org"
OPENALEX_API = "https://api.openalex.org"
SEMANTIC_SCHOLAR_API = "https://api.semanticscholar.org/graph/v1"
USER_AGENT = "research-radar/0.2 (https://github.com/research-radar/research-radar)"


class DiscoveryError(RuntimeError):
    """Raised for a failed discovery source request."""


class JsonClient(Protocol):
    def get_json(self, url: str) -> dict[str, Any]: ...


@dataclass(frozen=True)
class Candidate:
    schema_version: int
    identity: str
    doi: str | None
    openalex_id: str | None
    title: str
    authors: tuple[str, ...]
    year: int | None
    venue: str | None
    abstract: str | None
    url: str | None
    discovered_by: tuple[str, ...]
    access_status: str
    evidence_level: str
    cited_by_count: int | None = None
    publication_date: str | None = None
    semantic_scholar_id: str | None = None
    identity_status: str = "persistent"
    local_access_status: str = "none"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Candidate":
        normalized = dict(value)
        normalized["authors"] = tuple(normalized.get("authors") or ())
        normalized["discovered_by"] = tuple(normalized.get("discovered_by") or ())
        # Version-1 candidate records predate explicit local-content state.
        # A provider availability flag must never be promoted to local access.
        normalized.setdefault("local_access_status", "none")
        return cls(**normalized)


@dataclass(frozen=True)
class DiscoveryOutcome:
    candidates: tuple[Candidate, ...]
    adapter_status: dict[str, str]
    errors: tuple[str, ...]
    search_from: str
    search_to: str
    queries: tuple[str, ...]
    source_windows: dict[str, dict[str, str]]


class HttpJsonClient:
    def __init__(
        self,
        *,
        cache_dir: Path | None = None,
        timeout: float = 20.0,
        retries: int = 2,
        cache_ttl_seconds: int = 86400,
    ) -> None:
        self.cache_dir = cache_dir
        self.timeout = timeout
        self.retries = retries
        self.cache_ttl_seconds = cache_ttl_seconds
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, url: str) -> Path | None:
        if self.cache_dir is None:
            return None
        name = hashlib.sha256(url.encode("utf-8")).hexdigest() + ".json"
        return self.cache_dir / name

    def get_json(self, url: str) -> dict[str, Any]:
        cache_path = self._cache_path(url)
        if cache_path and cache_path.is_file():
            age = time.time() - cache_path.stat().st_mtime
            if age <= self.cache_ttl_seconds:
                return json.loads(cache_path.read_text(encoding="utf-8"))

        error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
                api_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
                if api_key and url.startswith(SEMANTIC_SCHOLAR_API):
                    headers["x-api-key"] = api_key
                request = Request(url, headers=headers)
                with urlopen(request, timeout=self.timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                if cache_path:
                    cache_path.write_text(
                        json.dumps(payload, ensure_ascii=False, sort_keys=True),
                        encoding="utf-8",
                    )
                return payload
            except HTTPError as exc:
                error = exc
                if attempt < self.retries:
                    retry_after = exc.headers.get("Retry-After") if exc.headers else None
                    try:
                        requested_delay = float(retry_after) if retry_after else 0.0
                    except ValueError:
                        requested_delay = 0.0
                    delay = (
                        min(10.0, max(0.5 * (2**attempt), requested_delay))
                        if exc.code in {429, 503}
                        else 0.5 * (2**attempt)
                    )
                    time.sleep(delay)
            except (URLError, TimeoutError, json.JSONDecodeError) as exc:
                error = exc
                if attempt < self.retries:
                    time.sleep(0.5 * (2**attempt))
        raise DiscoveryError(f"Request failed after {self.retries + 1} attempt(s): {url}: {error}")


def _first(value: object) -> object | None:
    return value[0] if isinstance(value, list) and value else None


def _clean_markup(value: object) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"<[^>]+>", " ", html.unescape(str(value)))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or None


def _safe_doi(value: object) -> str | None:
    try:
        return normalize_doi(str(value)) if value else None
    except AccessError:
        return None


def _candidate_identity(
    *, doi: str | None, openalex_id: str | None, title: str
) -> str:
    if doi:
        return f"doi:{doi}"
    if openalex_id:
        return f"openalex:{openalex_id.rsplit('/', 1)[-1].lower()}"
    return f"title:{normalize_title(title)}"


def _crossref_date(item: dict[str, Any]) -> str | None:
    for name in ("published-print", "published-online", "published", "issued", "created"):
        block = item.get(name)
        if not isinstance(block, dict):
            continue
        parts = _first(block.get("date-parts"))
        if isinstance(parts, list) and parts:
            numeric: list[int] = []
            for part in parts[:3]:
                try:
                    numeric.append(int(part))
                except (TypeError, ValueError):
                    break
            if numeric:
                return "-".join(
                    [f"{numeric[0]:04d}"]
                    + [f"{part:02d}" for part in numeric[1:]]
                )
    return None


def candidate_from_crossref(item: dict[str, Any], lane: str) -> Candidate | None:
    title = _clean_markup(_first(item.get("title")))
    if not title:
        return None
    doi = _safe_doi(item.get("DOI"))
    authors = tuple(
        " ".join(part for part in (author.get("given"), author.get("family")) if part).strip()
        for author in item.get("author", [])
        if isinstance(author, dict)
    )
    publication_date = _crossref_date(item)
    year = int(publication_date[:4]) if publication_date else None
    venue = _clean_markup(_first(item.get("container-title")))
    url = str(item.get("URL")) if item.get("URL") else (f"https://doi.org/{doi}" if doi else None)
    abstract = _clean_markup(item.get("abstract"))
    return Candidate(
        schema_version=1,
        identity=_candidate_identity(doi=doi, openalex_id=None, title=title),
        doi=doi,
        openalex_id=None,
        title=title,
        authors=tuple(author for author in authors if author),
        year=year,
        venue=venue,
        abstract=abstract,
        url=url,
        discovered_by=(lane,),
        access_status="abstract" if abstract else "metadata-only",
        evidence_level="abstract" if abstract else "metadata",
        cited_by_count=item.get("is-referenced-by-count"),
        publication_date=publication_date,
        identity_status="persistent" if doi else "title-fallback",
    )


def _openalex_abstract(inverted: object) -> str | None:
    if not isinstance(inverted, dict):
        return None
    tokens: list[tuple[int, str]] = []
    for word, positions in inverted.items():
        if isinstance(positions, list):
            tokens.extend((int(position), str(word)) for position in positions)
    return " ".join(word for _, word in sorted(tokens)) or None


def candidate_from_openalex(item: dict[str, Any], lane: str) -> Candidate | None:
    title = _clean_markup(item.get("title") or item.get("display_name"))
    if not title:
        return None
    ids = item.get("ids") if isinstance(item.get("ids"), dict) else {}
    doi = _safe_doi(item.get("doi") or ids.get("doi"))
    openalex_id = str(item.get("id") or ids.get("openalex") or "") or None
    authors = tuple(
        str(authorship.get("author", {}).get("display_name"))
        for authorship in item.get("authorships", [])
        if isinstance(authorship, dict) and authorship.get("author", {}).get("display_name")
    )
    source = (item.get("primary_location") or {}).get("source") or {}
    venue = source.get("display_name")
    abstract = _openalex_abstract(item.get("abstract_inverted_index"))
    best = item.get("best_oa_location") or {}
    url = best.get("landing_page_url") or best.get("pdf_url") or item.get("doi") or openalex_id
    has_full_text = bool(item.get("has_fulltext") or best.get("pdf_url"))
    access_status = "full-text" if has_full_text else ("abstract" if abstract else "metadata-only")
    # Availability is not evidence use: until the local distiller actually reads the
    # file, all claims here are still based on the indexed abstract or metadata.
    evidence_level = "abstract" if abstract else "metadata"
    year = item.get("publication_year")
    return Candidate(
        schema_version=1,
        identity=_candidate_identity(doi=doi, openalex_id=openalex_id, title=title),
        doi=doi,
        openalex_id=openalex_id,
        title=title,
        authors=authors,
        year=int(year) if year else None,
        venue=str(venue) if venue else None,
        abstract=abstract,
        url=str(url) if url else None,
        discovered_by=(lane,),
        access_status=access_status,
        evidence_level=evidence_level,
        cited_by_count=item.get("cited_by_count"),
        publication_date=item.get("publication_date"),
        identity_status="persistent" if (doi or openalex_id) else "title-fallback",
    )


def candidate_from_semantic_scholar(
    item: dict[str, Any], lane: str
) -> Candidate | None:
    title = _clean_markup(item.get("title"))
    if not title:
        return None
    external_ids = item.get("externalIds") if isinstance(item.get("externalIds"), dict) else {}
    doi = _safe_doi(external_ids.get("DOI"))
    semantic_scholar_id = str(item.get("paperId") or "") or None
    identity = (
        f"doi:{doi}"
        if doi
        else (
            f"semantic-scholar:{semantic_scholar_id.lower()}"
            if semantic_scholar_id
            else f"title:{normalize_title(title)}"
        )
    )
    authors = tuple(
        str(author.get("name"))
        for author in (item.get("authors") or [])
        if isinstance(author, dict) and author.get("name")
    )
    abstract = _clean_markup(item.get("abstract"))
    open_pdf = item.get("openAccessPdf") if isinstance(item.get("openAccessPdf"), dict) else {}
    url = open_pdf.get("url") or item.get("url") or (f"https://doi.org/{doi}" if doi else None)
    year = item.get("year")
    return Candidate(
        schema_version=1,
        identity=identity,
        doi=doi,
        openalex_id=None,
        title=title,
        authors=authors,
        year=int(year) if year else None,
        venue=str(item.get("venue")) if item.get("venue") else None,
        abstract=abstract,
        url=str(url) if url else None,
        discovered_by=(lane,),
        access_status=("full-text" if open_pdf.get("url") else ("abstract" if abstract else "metadata-only")),
        evidence_level="abstract" if abstract else "metadata",
        cited_by_count=item.get("citationCount"),
        publication_date=item.get("publicationDate"),
        semantic_scholar_id=semantic_scholar_id,
        identity_status=(
            "persistent" if (doi or semantic_scholar_id) else "title-fallback"
        ),
    )


class CrossrefAdapter:
    name = "crossref"

    def __init__(self, client: JsonClient) -> None:
        self.client = client

    def search(
        self,
        query: str,
        *,
        from_date: str,
        until_date: str,
        limit: int = 20,
        field: str = "query.bibliographic",
        lane: str = "crossref:keywords",
    ) -> list[Candidate]:
        params = urlencode(
            {
                field: query,
                "filter": f"from-pub-date:{from_date},until-pub-date:{until_date}",
                "rows": limit,
                "select": "DOI,title,author,published-print,published-online,published,issued,created,container-title,abstract,URL,is-referenced-by-count",
            }
        )
        payload = self.client.get_json(f"{CROSSREF_API}/works?{params}")
        items = payload.get("message", {}).get("items", [])
        return [
            candidate
            for item in items
            if (candidate := candidate_from_crossref(item, lane))
        ]

    def resolve_seed(self, seed: SeedPaper) -> Candidate | None:
        if not seed.title:
            return None
        query = " ".join([seed.title, *seed.authors[:1]])
        params = urlencode(
            {
                "query.bibliographic": query,
                "rows": 3,
                "select": "DOI,title,author,published-print,published-online,published,issued,created,container-title,abstract,URL,is-referenced-by-count",
            }
        )
        payload = self.client.get_json(f"{CROSSREF_API}/works?{params}")
        candidates = [
            candidate
            for item in payload.get("message", {}).get("items", [])
            if (candidate := candidate_from_crossref(item, "crossref:seed-resolution"))
            and candidate.doi
        ]
        target = normalize_title(seed.title)

        def similarity(candidate: Candidate) -> float:
            resolved = normalize_title(candidate.title)
            target_tokens = set(target.split())
            resolved_tokens = set(resolved.split())
            union = target_tokens | resolved_tokens
            jaccard = len(target_tokens & resolved_tokens) / len(union) if union else 0.0
            sequence = SequenceMatcher(None, target, resolved).ratio()
            return max(jaccard, sequence)

        if not candidates:
            return None
        best = max(candidates, key=similarity)
        return best if similarity(best) >= 0.82 else None


class OpenAlexAdapter:
    name = "openalex"

    def __init__(self, client: JsonClient) -> None:
        self.client = client

    def resolve_seed(self, seed: SeedPaper) -> dict[str, Any] | None:
        if not seed.doi:
            return None
        identifier = quote(f"https://doi.org/{seed.doi}", safe=":/")
        return self.client.get_json(f"{OPENALEX_API}/works/{identifier}")

    def citing(
        self,
        openalex_id: str,
        *,
        from_date: str,
        until_date: str,
        limit: int = 20,
    ) -> list[Candidate]:
        short_id = openalex_id.rsplit("/", 1)[-1]
        params = urlencode(
            {
                "filter": f"cites:{short_id},from_publication_date:{from_date},to_publication_date:{until_date}",
                "per-page": limit,
            }
        )
        payload = self.client.get_json(f"{OPENALEX_API}/works?{params}")
        return [candidate for item in payload.get("results", []) if (candidate := candidate_from_openalex(item, "openalex:forward-citations"))]

    def related(self, work: dict[str, Any], *, limit: int = 10) -> list[Candidate]:
        candidates: list[Candidate] = []
        for related_id in work.get("related_works", [])[:limit]:
            identifier = quote(str(related_id).rsplit("/", 1)[-1], safe="")
            item = self.client.get_json(f"{OPENALEX_API}/works/{identifier}")
            candidate = candidate_from_openalex(item, "openalex:related")
            if candidate:
                candidates.append(candidate)
        return candidates

    def search(
        self, query: str, *, from_date: str, until_date: str, limit: int = 20
    ) -> list[Candidate]:
        params = urlencode(
            {
                "search": query,
                "filter": f"from_publication_date:{from_date},to_publication_date:{until_date}",
                "per-page": limit,
            }
        )
        payload = self.client.get_json(f"{OPENALEX_API}/works?{params}")
        return [candidate for item in payload.get("results", []) if (candidate := candidate_from_openalex(item, "openalex:keywords"))]


class SemanticScholarAdapter:
    name = "semanticscholar"
    fields = (
        "paperId,externalIds,title,authors,year,venue,abstract,url,"
        "citationCount,publicationDate,openAccessPdf"
    )

    def __init__(self, client: JsonClient) -> None:
        self.client = client
        self.coverage_notes: list[str] = []

    @staticmethod
    def _seed_identifier(seed: SeedPaper) -> str | None:
        if seed.doi:
            return quote(f"DOI:{seed.doi}", safe=":")
        if seed.preprint_id and seed.preprint_id.startswith("arxiv:"):
            return quote(f"ARXIV:{seed.preprint_id.removeprefix('arxiv:')}", safe=":")
        return None

    def citing(self, seed: SeedPaper, *, limit: int = 20) -> list[Candidate]:
        identifier = self._seed_identifier(seed)
        if not identifier:
            return []
        params = urlencode({"fields": self.fields, "limit": min(limit, 1000)})
        payload = self.client.get_json(
            f"{SEMANTIC_SCHOLAR_API}/paper/{identifier}/citations?{params}"
        )
        if payload.get("data") is None:
            self.coverage_notes.append(
                f"{seed.citation_key}: citation data unavailable or publisher-elided"
            )
            return []
        return [
            candidate
            for record in (payload.get("data") or [])
            if isinstance(record, dict)
            and isinstance(record.get("citingPaper"), dict)
            and (
                candidate := candidate_from_semantic_scholar(
                    record["citingPaper"], "semanticscholar:forward-citations"
                )
            )
        ]

    def references(self, seed: SeedPaper, *, limit: int = 20) -> list[Candidate]:
        identifier = self._seed_identifier(seed)
        if not identifier:
            return []
        params = urlencode({"fields": self.fields, "limit": min(limit, 1000)})
        payload = self.client.get_json(
            f"{SEMANTIC_SCHOLAR_API}/paper/{identifier}/references?{params}"
        )
        if payload.get("data") is None:
            self.coverage_notes.append(
                f"{seed.citation_key}: reference data unavailable or publisher-elided"
            )
            return []
        return [
            candidate
            for record in payload.get("data", [])
            if isinstance(record, dict)
            and isinstance(record.get("citedPaper"), dict)
            and (
                candidate := candidate_from_semantic_scholar(
                    record["citedPaper"], "semanticscholar:reference-neighborhood"
                )
            )
        ]


def _merge_candidate(left: Candidate, right: Candidate) -> Candidate:
    lanes = tuple(sorted(set(left.discovered_by) | set(right.discovered_by)))
    authors = left.authors if len(left.authors) >= len(right.authors) else right.authors
    evidence_rank = {"metadata": 0, "abstract": 1, "full-text": 2}
    richer = right if evidence_rank[right.evidence_level] > evidence_rank[left.evidence_level] else left
    merged_doi = left.doi or right.doi
    merged_openalex_id = left.openalex_id or right.openalex_id
    merged_semantic_scholar_id = left.semantic_scholar_id or right.semantic_scholar_id
    merged_identity = _candidate_identity(
        doi=merged_doi,
        openalex_id=merged_openalex_id,
        title=left.title if len(left.title) >= len(right.title) else right.title,
    )
    if (
        not merged_doi
        and not merged_openalex_id
        and merged_semantic_scholar_id
    ):
        merged_identity = f"semantic-scholar:{merged_semantic_scholar_id.lower()}"
    return replace(
        richer,
        identity=merged_identity,
        doi=merged_doi,
        openalex_id=merged_openalex_id,
        semantic_scholar_id=merged_semantic_scholar_id,
        identity_status=(
            "persistent"
            if (merged_doi or merged_openalex_id or merged_semantic_scholar_id)
            else "title-fallback"
        ),
        title=left.title if len(left.title) >= len(right.title) else right.title,
        authors=authors,
        year=left.year or right.year,
        venue=left.venue or right.venue,
        abstract=left.abstract or right.abstract,
        url=richer.url or left.url or right.url,
        discovered_by=lanes,
        cited_by_count=max(value for value in (left.cited_by_count, right.cited_by_count) if value is not None)
        if any(value is not None for value in (left.cited_by_count, right.cited_by_count))
        else None,
        publication_date=left.publication_date or right.publication_date,
    )


def merge_candidates(candidates: Iterable[Candidate]) -> tuple[Candidate, ...]:
    merged: dict[str, Candidate] = {}
    title_index: dict[str, str] = {}
    for candidate in candidates:
        normalized = normalize_title(candidate.title)
        identity = candidate.identity
        existing_identity = identity if identity in merged else title_index.get(normalized)
        if existing_identity:
            updated = _merge_candidate(merged[existing_identity], candidate)
            if updated.identity != existing_identity:
                del merged[existing_identity]
            merged[updated.identity] = updated
            title_index[normalized] = updated.identity
        else:
            merged[identity] = candidate
            title_index[normalized] = identity
    return tuple(sorted(merged.values(), key=lambda item: (item.publication_date or "", item.title), reverse=True))


def profile_queries(snapshot: ProjectSnapshot, config: dict[str, Any]) -> tuple[str, ...]:
    def plain_query(value: str) -> str:
        value = re.sub(r"[*_`{}]", " ", value)
        value = re.sub(r"\\[A-Za-z]+", " ", value)
        return re.sub(r"\s+", " ", value).strip(" .:;-–—")

    queries: list[str] = []
    watched = config.get("watch", {}).get("keywords", [])
    if isinstance(watched, list):
        queries.extend(plain_query(str(item)) for item in watched if plain_query(str(item)))
    watch_section = snapshot.profile.sections.get("watch", "")
    keyword_value = _watch_field(watch_section, r"keywords?")
    if keyword_value:
        queries.extend(
            plain_query(part)
            for part in keyword_value.split(",")
            if plain_query(part)
        )
    if not queries:
        research_question = snapshot.profile.sections.get("research-question")
        if research_question:
            queries.append(research_question.splitlines()[0].strip())
        else:
            core_question = re.search(
                r"(?im)^\s*(?:\*\*)?core question(?:\*\*)?\s*:\s*(.+)$",
                snapshot.profile.raw_markdown,
            )
            if core_question:
                parts = [core_question.group(1).strip()]
                remaining = snapshot.profile.raw_markdown[core_question.end() :]
                remaining = re.sub(r"^\r?\n", "", remaining, count=1)
                for line in remaining.splitlines():
                    if not line.strip() or line.lstrip().startswith(("#", "---")):
                        break
                    parts.append(line.strip())
                queries.append(plain_query(" ".join(parts)))
            else:
                queries.append(plain_query(snapshot.profile.project_name))
    return tuple(dict.fromkeys(queries))


def _watch_field(watch_section: str, label: str) -> str | None:
    """Read one labeled watch-list field including Markdown continuation lines."""
    lines = watch_section.splitlines()
    for index, raw_line in enumerate(lines):
        match = re.match(
            rf"(?i)^\s*[-*]?\s*{label}\s*:\s*(.*)$",
            raw_line,
        )
        if not match:
            continue
        parts = [match.group(1).strip()]
        for continuation in lines[index + 1 :]:
            stripped = continuation.strip()
            if not stripped or stripped.startswith("#"):
                break
            if re.match(r"^[-*]\s+[A-Za-z][^:]{0,80}:\s*", stripped):
                break
            parts.append(stripped)
        value = " ".join(part for part in parts if part)
        return value or None
    return None


def profile_watch_items(
    snapshot: ProjectSnapshot,
    config: dict[str, Any],
    kind: str,
) -> tuple[str, ...]:
    items = list(configured_watch(config, kind))
    watch_section = snapshot.profile.sections.get("watch", "")
    label = "authors?" if kind == "authors" else "venues?(?:\\s+or\\s+working-paper\\s+series)?"
    value = _watch_field(watch_section, label)
    if value:
        items.extend(part.strip() for part in value.split(",") if part.strip())
    return tuple(dict.fromkeys(items))


def _author_watch_match(candidate: Candidate, watched: str) -> bool:
    target = normalize_title(watched).split()
    if not target:
        return False
    target_first = target[0]
    target_last = target[-1]
    for author in candidate.authors:
        parts = normalize_title(author).split()
        if not parts or parts[-1] != target_last:
            continue
        if len(target) == 1:
            return True
        if parts[0] == target_first or parts[0][:1] == target_first[:1]:
            return True
    return False


def _venue_watch_match(candidate: Candidate, watched: str) -> bool:
    if not candidate.venue:
        return False
    actual = normalize_title(candidate.venue)
    target = normalize_title(watched)
    return bool(actual and target and (actual == target or target in actual or actual in target))


def _published_in_window(
    candidate: Candidate,
    *,
    from_date: str,
    until_date: str,
) -> bool:
    """Filter graph results locally when the provider has no date parameter."""
    published = candidate.publication_date
    if not published and candidate.year:
        published = f"{candidate.year:04d}-01-01"
    if not published:
        # Preserve high-recall behavior when the provider omits a date.
        return True
    normalized = str(published)[:10]
    return from_date <= normalized <= until_date


def discover(
    snapshot: ProjectSnapshot,
    *,
    search_from: str | None = None,
    search_to: str | None = None,
    search_from_by_source: dict[str, str] | None = None,
    client: JsonClient | None = None,
    limit_per_lane: int = 20,
) -> DiscoveryOutcome:
    require_profile_ready(snapshot.profile)
    root = Path(snapshot.project_root)
    config = load_config(root)
    today = date.today()
    search_to = search_to or today.isoformat()
    default_search_from = (
        today - timedelta(days=int(config.get("lookback_days", 14)))
    ).isoformat()
    if client is None:
        client = HttpJsonClient(cache_dir=root / ".research-radar" / "cache")

    sources = set(config.get("sources", []))
    prior_windows = search_from_by_source or {}
    source_windows = {
        source: {
            "from": search_from or prior_windows.get(source) or default_search_from,
            "to": search_to,
        }
        for source in sorted(sources)
    }
    search_from = min(
        (window["from"] for window in source_windows.values()),
        default=search_from or default_search_from,
    )
    lanes = set(config.get("discovery_lanes", []))
    queries = profile_queries(snapshot, config)
    author_queries = profile_watch_items(snapshot, config, "authors")
    venue_queries = profile_watch_items(snapshot, config, "venues")
    found: list[Candidate] = []
    statuses: dict[str, str] = {}
    errors: list[str] = []

    cited_seeds = [seed for seed in snapshot.seeds if seed.cited_in_manuscript]
    active_seeds = cited_seeds or list(snapshot.seeds)
    effective_seeds = list(active_seeds)

    if "crossref" in sources:
        adapter = CrossrefAdapter(client)
        source_from = source_windows[adapter.name]["from"]
        resolved_count = 0
        resolution_attempts = 0
        try:
            if "keywords" in lanes:
                for query in queries:
                    found.extend(adapter.search(query, from_date=source_from, until_date=search_to, limit=limit_per_lane))
            watch_limit = max(0, int(config.get("max_watch_queries", 8)))
            if "authors" in lanes:
                for author in author_queries[:watch_limit]:
                    found.extend(
                        candidate
                        for candidate in adapter.search(
                            author,
                            from_date=source_from,
                            until_date=search_to,
                            limit=limit_per_lane,
                            field="query.author",
                            lane="crossref:authors",
                        )
                        if _author_watch_match(candidate, author)
                    )
            if "venues" in lanes:
                for venue in venue_queries[:watch_limit]:
                    found.extend(
                        candidate
                        for candidate in adapter.search(
                            venue,
                            from_date=source_from,
                            until_date=search_to,
                            limit=limit_per_lane,
                            field="query.container-title",
                            lane="crossref:venues",
                        )
                        if _venue_watch_match(candidate, venue)
                    )
            resolution_limit = max(0, int(config.get("max_seed_resolution", 12)))
            for index, seed in list(enumerate(effective_seeds)):
                if seed.doi or not seed.title or resolution_attempts >= resolution_limit:
                    continue
                resolution_attempts += 1
                resolved = adapter.resolve_seed(seed)
                if resolved and resolved.doi:
                    effective_seeds[index] = replace(seed, doi=resolved.doi)
                    resolved_count += 1
            statuses[adapter.name] = f"ok ({resolved_count} seed(s) resolved)"
        except Exception as exc:
            statuses[adapter.name] = "failed"
            errors.append(f"{adapter.name}: {exc}")

    if "openalex" in sources:
        adapter = OpenAlexAdapter(client)
        source_from = source_windows[adapter.name]["from"]
        resolved = 0
        openalex_failures = 0
        direct = [
            effective
            for original, effective in zip(active_seeds, effective_seeds)
            if original.doi and effective.doi
        ]
        enriched = [
            effective
            for original, effective in zip(active_seeds, effective_seeds)
            if not original.doi and effective.doi
        ]
        graph_limit = max(0, int(config.get("max_graph_seeds", 8)))
        graph_seeds = list(
            dict.fromkeys(seed.identity for seed in [*enriched, *direct])
        )[:graph_limit]
        graph_seed_by_identity = {
            seed.identity: seed for seed in [*enriched, *direct]
        }
        for identity in graph_seeds:
            seed = graph_seed_by_identity[identity]
            if not seed.doi:
                continue
            try:
                work = adapter.resolve_seed(seed)
                if not work:
                    continue
                resolved += 1
                work_id = str(work.get("id") or "")
                if work_id and "forward-citations" in lanes:
                    found.extend(
                        adapter.citing(
                            work_id,
                            from_date=source_from,
                            until_date=search_to,
                            limit=limit_per_lane,
                        )
                    )
                if "related" in lanes:
                    found.extend(adapter.related(work, limit=min(limit_per_lane, 10)))
            except Exception as exc:
                openalex_failures += 1
                errors.append(f"{adapter.name} seed {seed.citation_key}: {exc}")
        if "keywords" in lanes:
            for query in queries:
                try:
                    found.extend(adapter.search(query, from_date=source_from, until_date=search_to, limit=limit_per_lane))
                except Exception as exc:
                    openalex_failures += 1
                    errors.append(f"{adapter.name} query {query!r}: {exc}")
        if openalex_failures:
            statuses[adapter.name] = (
                f"partial ({resolved} seed(s) resolved; {openalex_failures} failure(s))"
            )
        else:
            statuses[adapter.name] = f"ok ({resolved} seed(s) resolved)"

    if "semanticscholar" in sources:
        adapter = SemanticScholarAdapter(client)
        source_from = source_windows[adapter.name]["from"]
        failures = 0
        queried = 0
        graph_limit = max(0, int(config.get("max_graph_seeds", 8)))
        graph_seeds = [
            seed for seed in effective_seeds if seed.doi or seed.preprint_id
        ][:graph_limit]
        for seed in graph_seeds:
            try:
                if "forward-citations" in lanes:
                    found.extend(
                        candidate
                        for candidate in adapter.citing(seed, limit=limit_per_lane)
                        if _published_in_window(
                            candidate,
                            from_date=source_from,
                            until_date=search_to,
                        )
                    )
                if "reference-neighborhood" in lanes:
                    found.extend(adapter.references(seed, limit=limit_per_lane))
                queried += 1
            except Exception as exc:
                failures += 1
                errors.append(f"{adapter.name} seed {seed.citation_key}: {exc}")
        if failures or adapter.coverage_notes:
            statuses[adapter.name] = (
                f"partial ({queried} seed(s) queried; {failures} failure(s); "
                f"{len(adapter.coverage_notes)} coverage gap(s))"
            )
        else:
            statuses[adapter.name] = f"ok ({queried} seed(s) queried)"

    seed_identities = {seed.identity for seed in snapshot.seeds} | {
        seed.identity for seed in effective_seeds
    }
    seed_titles = {
        normalize_title(seed.title) for seed in snapshot.seeds if seed.title
    }
    candidates = tuple(
        candidate
        for candidate in merge_candidates(found)
        if candidate.identity not in seed_identities
        and normalize_title(candidate.title) not in seed_titles
    )
    return DiscoveryOutcome(
        candidates=candidates,
        adapter_status=statuses,
        errors=tuple(errors),
        search_from=search_from,
        search_to=search_to,
        queries=queries,
        source_windows=source_windows,
    )

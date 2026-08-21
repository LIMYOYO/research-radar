"""Resolve a DOI to ranked access options without downloading in bulk."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote

from .access import doi_url, libkey_url, normalize_doi
from .discovery import CROSSREF_API, OPENALEX_API, HttpJsonClient


class JsonClient(Protocol):
    def get_json(self, url: str) -> dict[str, Any]: ...


@dataclass(frozen=True)
class AccessOption:
    route: str
    url: str
    access_type: str
    content_type: str | None
    version: str | None
    license: str | None
    source: str
    confidence: str


@dataclass(frozen=True)
class AccessResolution:
    schema_version: int
    doi: str
    recommended: AccessOption
    options: tuple[AccessOption, ...]
    adapter_status: dict[str, str]
    errors: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _url(value: object) -> str | None:
    return str(value).strip() if value and str(value).strip() else None


def _crossref_options(payload: dict[str, Any]) -> list[AccessOption]:
    message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
    options: list[AccessOption] = []
    for link in message.get("link", []) or []:
        if not isinstance(link, dict):
            continue
        url = _url(link.get("URL") or link.get("url"))
        if not url:
            continue
        content_type = _url(link.get("content-type"))
        looks_pdf = bool(
            (content_type and "pdf" in content_type.lower())
            or url.lower().split("?", 1)[0].endswith(".pdf")
            or "/doi/pdf/" in url.lower()
        )
        options.append(
            AccessOption(
                route="crossref-link",
                url=url,
                access_type="full-text-candidate" if looks_pdf else "publisher-resource",
                content_type=content_type,
                version=_url(link.get("content-version")),
                license=None,
                source="crossref",
                confidence="candidate",
            )
        )
    return options


def _openalex_options(payload: dict[str, Any]) -> list[AccessOption]:
    location = payload.get("best_oa_location")
    if not isinstance(location, dict) or not location.get("is_oa"):
        return []
    license_name = _url(location.get("license") or location.get("license_id"))
    version = _url(location.get("version"))
    options: list[AccessOption] = []
    pdf_url = _url(location.get("pdf_url"))
    landing_url = _url(location.get("landing_page_url"))
    if pdf_url:
        options.append(
            AccessOption(
                route="open-access-pdf",
                url=pdf_url,
                access_type="full-text",
                content_type="application/pdf",
                version=version,
                license=license_name,
                source="openalex",
                confidence="reported-open-access",
            )
        )
    if landing_url and landing_url != pdf_url:
        options.append(
            AccessOption(
                route="open-access-landing",
                url=landing_url,
                access_type="full-text-candidate",
                content_type="text/html",
                version=version,
                license=license_name,
                source="openalex",
                confidence="reported-open-access",
            )
        )
    return options


def _deduplicate(options: list[AccessOption]) -> tuple[AccessOption, ...]:
    unique: dict[str, AccessOption] = {}
    for option in options:
        unique.setdefault(option.url, option)
    priority = {
        "open-access-pdf": 0,
        "open-access-landing": 1,
        "crossref-link": 2,
        "libkey": 3,
        "doi": 4,
    }
    return tuple(sorted(unique.values(), key=lambda item: (priority.get(item.route, 9), item.url)))


def resolve_access(
    doi: str,
    *,
    client: JsonClient | None = None,
    cache_dir: str | Path | None = None,
) -> AccessResolution:
    normalized = normalize_doi(doi)
    if client is None:
        client = HttpJsonClient(
            cache_dir=Path(cache_dir).expanduser().resolve() if cache_dir else None
        )
    options: list[AccessOption] = []
    status: dict[str, str] = {}
    errors: list[str] = []

    try:
        identifier = quote(normalized, safe="/")
        options.extend(
            _crossref_options(client.get_json(f"{CROSSREF_API}/works/{identifier}"))
        )
        status["crossref"] = "ok"
    except Exception as exc:
        status["crossref"] = "failed"
        errors.append(f"crossref: {exc}")

    try:
        identifier = quote(f"https://doi.org/{normalized}", safe=":/")
        options.extend(
            _openalex_options(client.get_json(f"{OPENALEX_API}/works/{identifier}"))
        )
        status["openalex"] = "ok"
    except Exception as exc:
        status["openalex"] = "failed"
        errors.append(f"openalex: {exc}")

    options.extend(
        [
            AccessOption(
                route="libkey",
                url=libkey_url(normalized),
                access_type="institutional-handoff",
                content_type="text/html",
                version="version-of-record",
                license=None,
                source="libkey",
                confidence="authorized-user-handoff",
            ),
            AccessOption(
                route="doi",
                url=doi_url(normalized),
                access_type="publisher-landing",
                content_type="text/html",
                version="version-of-record",
                license=None,
                source="doi.org",
                confidence="canonical",
            ),
        ]
    )
    ranked = _deduplicate(options)
    return AccessResolution(
        schema_version=1,
        doi=normalized,
        recommended=ranked[0],
        options=ranked,
        adapter_status=status,
        errors=tuple(errors),
    )

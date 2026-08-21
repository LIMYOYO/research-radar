from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any

from research_radar.discovery import (
    DiscoveryError,
    candidate_from_crossref,
    candidate_from_openalex,
    discover,
    merge_candidates,
)
from research_radar.project import ingest_project


FIXTURE = Path(__file__).resolve().parents[1] / "examples" / "synthetic-project"


def crossref_item() -> dict[str, Any]:
    return {
        "DOI": "10.5555/FUTURE",
        "title": ["Strategic Reviews and Platform Learning"],
        "author": [{"given": "Ada", "family": "Lovelace"}],
        "published-online": {"date-parts": [[2026, 8, 20]]},
        "container-title": ["Management Science"],
        "abstract": "<jats:p>A platform learning abstract.</jats:p>",
        "URL": "https://doi.org/10.5555/future",
        "is-referenced-by-count": 3,
    }


def openalex_item() -> dict[str, Any]:
    return {
        "id": "https://openalex.org/WFUTURE",
        "doi": "https://doi.org/10.5555/future",
        "title": "Strategic Reviews and Platform Learning",
        "authorships": [{"author": {"display_name": "Ada Lovelace"}}],
        "publication_year": 2026,
        "publication_date": "2026-08-20",
        "primary_location": {"source": {"display_name": "Management Science"}},
        "abstract_inverted_index": {"A": [0], "richer": [1], "abstract": [2]},
        "has_fulltext": True,
        "best_oa_location": None,
        "cited_by_count": 4,
    }


class FakeClient:
    def __init__(self, fail_crossref: bool = False) -> None:
        self.fail_crossref = fail_crossref
        self.urls: list[str] = []

    def get_json(self, url: str) -> dict[str, Any]:
        self.urls.append(url)
        if "api.crossref.org/works?" in url:
            if self.fail_crossref:
                raise DiscoveryError("simulated Crossref outage")
            return {"message": {"items": [crossref_item()]}}
        if "api.openalex.org/works/https://doi.org/" in url:
            return {"id": "https://openalex.org/WSEED", "related_works": []}
        if "filter=cites%3AWSEED" in url:
            return {"results": [openalex_item()]}
        if "api.openalex.org/works?" in url:
            return {"results": []}
        raise AssertionError(f"Unexpected URL: {url}")


class DiscoveryTests(unittest.TestCase):
    def test_crossref_and_openalex_normalize_to_same_identity(self) -> None:
        crossref = candidate_from_crossref(crossref_item(), "crossref:keywords")
        openalex = candidate_from_openalex(openalex_item(), "openalex:forward-citations")
        self.assertIsNotNone(crossref)
        self.assertIsNotNone(openalex)
        merged = merge_candidates([crossref, openalex])  # type: ignore[list-item]

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].identity, "doi:10.5555/future")
        self.assertEqual(
            set(merged[0].discovered_by),
            {"crossref:keywords", "openalex:forward-citations"},
        )
        self.assertEqual(merged[0].cited_by_count, 4)
        self.assertEqual(merged[0].evidence_level, "abstract")
        self.assertEqual(openalex.evidence_level, "abstract")  # type: ignore[union-attr]
        self.assertEqual(openalex.access_status, "full-text")  # type: ignore[union-attr]

    def test_discovery_resolves_seeds_and_deduplicates_sources(self) -> None:
        snapshot = ingest_project(FIXTURE)
        client = FakeClient()
        outcome = discover(
            snapshot,
            search_from="2026-08-01",
            search_to="2026-08-21",
            client=client,
            limit_per_lane=5,
        )

        self.assertEqual(len(outcome.candidates), 1)
        self.assertEqual(outcome.candidates[0].doi, "10.5555/future")
        self.assertEqual(outcome.adapter_status["crossref"], "ok")
        self.assertIn("2 seed(s) resolved", outcome.adapter_status["openalex"])
        self.assertFalse(outcome.errors)
        self.assertGreater(len(client.urls), 4)

    def test_one_adapter_failure_is_nonfatal(self) -> None:
        snapshot = ingest_project(FIXTURE)
        outcome = discover(
            snapshot,
            search_from="2026-08-01",
            search_to="2026-08-21",
            client=FakeClient(fail_crossref=True),
            limit_per_lane=5,
        )

        self.assertEqual(outcome.adapter_status["crossref"], "failed")
        self.assertTrue(outcome.adapter_status["openalex"].startswith("ok"))
        self.assertEqual(len(outcome.candidates), 1)
        self.assertIn("simulated Crossref outage", outcome.errors[0])


if __name__ == "__main__":
    unittest.main()

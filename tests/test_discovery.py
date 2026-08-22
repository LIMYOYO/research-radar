from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path
from typing import Any

from research_radar.discovery import (
    CrossrefAdapter,
    DiscoveryError,
    candidate_from_crossref,
    candidate_from_openalex,
    candidate_from_semantic_scholar,
    discover,
    merge_candidates,
    profile_queries,
    profile_watch_items,
    SemanticScholarAdapter,
    _author_watch_match,
    _venue_watch_match,
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


def crossref_item_with_partial_date() -> dict[str, Any]:
    item = crossref_item()
    item["published-online"] = {"date-parts": [[2026, None, None]]}
    return item


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


def semantic_scholar_item() -> dict[str, Any]:
    return {
        "paperId": "S2FUTURE",
        "externalIds": {"DOI": "10.5555/FUTURE"},
        "title": "Strategic Reviews and Platform Learning",
        "authors": [{"name": "Ada Lovelace"}],
        "year": 2026,
        "publicationDate": "2026-08-20",
        "venue": "Management Science",
        "abstract": "An independent citation-graph abstract.",
        "url": "https://www.semanticscholar.org/paper/S2FUTURE",
        "citationCount": 5,
        "openAccessPdf": {"url": "https://example.test/future.pdf", "status": "GREEN"},
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
            item = crossref_item()
            if "query.author=Junyu+Cao" in url:
                item["author"] = [{"given": "Junyu", "family": "Cao"}]
            elif "query.author=Michael+Luca" in url:
                item["author"] = [{"given": "Michael", "family": "Luca"}]
            return {"message": {"items": [item]}}
        if "api.openalex.org/works/https://doi.org/" in url:
            return {"id": "https://openalex.org/WSEED", "related_works": []}
        if "filter=cites%3AWSEED" in url:
            return {"results": [openalex_item()]}
        if "api.openalex.org/works?" in url:
            return {"results": []}
        if "api.semanticscholar.org/graph/v1/paper/DOI:" in url and "/citations?" in url:
            return {"data": [{"citingPaper": semantic_scholar_item()}]}
        if "api.semanticscholar.org/graph/v1/paper/DOI:" in url and "/references?" in url:
            return {"data": []}
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

    def test_crossref_partial_date_is_tolerated(self) -> None:
        candidate = candidate_from_crossref(
            crossref_item_with_partial_date(), "crossref:keywords"
        )
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.publication_date, "2026")  # type: ignore[union-attr]
        self.assertEqual(candidate.year, 2026)  # type: ignore[union-attr]

    def test_title_fallback_identity_is_explicitly_marked_unresolved(self) -> None:
        item = crossref_item()
        item.pop("DOI")
        candidate = candidate_from_crossref(item, "crossref:keywords")
        self.assertIsNotNone(candidate)
        self.assertTrue(candidate.identity.startswith("title:"))  # type: ignore[union-attr]
        self.assertEqual(candidate.identity_status, "title-fallback")  # type: ignore[union-attr]

    def test_merge_never_downgrades_a_provider_identifier_to_title(self) -> None:
        openalex_data = openalex_item()
        openalex_data["doi"] = None
        openalex_data["ids"] = {}
        crossref_data = crossref_item()
        crossref_data.pop("DOI")
        openalex = candidate_from_openalex(openalex_data, "openalex:related")
        crossref = candidate_from_crossref(crossref_data, "crossref:keywords")

        self.assertIsNotNone(openalex)
        self.assertIsNotNone(crossref)
        for ordering in ([openalex, crossref], [crossref, openalex]):
            merged = merge_candidates(ordering)  # type: ignore[arg-type]
            self.assertEqual(len(merged), 1)
            self.assertEqual(merged[0].identity, "openalex:wfuture")
            self.assertEqual(merged[0].identity_status, "persistent")

    def test_semantic_scholar_candidate_preserves_independent_identity(self) -> None:
        candidate = candidate_from_semantic_scholar(
            semantic_scholar_item(), "semanticscholar:forward-citations"
        )
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.identity, "doi:10.5555/future")  # type: ignore[union-attr]
        self.assertEqual(candidate.semantic_scholar_id, "S2FUTURE")  # type: ignore[union-attr]
        self.assertEqual(candidate.access_status, "full-text")  # type: ignore[union-attr]
        self.assertEqual(candidate.evidence_level, "abstract")  # type: ignore[union-attr]

        nullable = semantic_scholar_item()
        nullable["authors"] = None
        nullable["openAccessPdf"] = None
        nullable_candidate = candidate_from_semantic_scholar(
            nullable, "semanticscholar:reference-neighborhood"
        )
        self.assertEqual(nullable_candidate.authors, ())  # type: ignore[union-attr]

    def test_semantic_scholar_reports_null_result_page_as_coverage_gap(self) -> None:
        class NullDataClient:
            def get_json(self, url: str) -> dict[str, Any]:
                return {"data": None}

        seed = ingest_project(FIXTURE).seeds[0]
        adapter = SemanticScholarAdapter(NullDataClient())
        self.assertEqual(adapter.citing(seed), [])
        self.assertEqual(adapter.references(seed), [])
        self.assertEqual(len(adapter.coverage_notes), 2)
        self.assertIn("publisher-elided", adapter.coverage_notes[0])

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
        self.assertTrue(outcome.adapter_status["crossref"].startswith("ok"))
        self.assertIn("2 seed(s) resolved", outcome.adapter_status["openalex"])
        self.assertIn("2 seed(s) queried", outcome.adapter_status["semanticscholar"])
        self.assertFalse(outcome.errors)
        self.assertGreater(len(client.urls), 4)
        self.assertIn("crossref:authors", outcome.candidates[0].discovered_by)
        self.assertIn("crossref:venues", outcome.candidates[0].discovered_by)
        self.assertIn(
            "semanticscholar:forward-citations",
            outcome.candidates[0].discovered_by,
        )

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

    def test_crossref_high_confidence_title_resolution(self) -> None:
        snapshot = ingest_project(FIXTURE)
        seed = replace(
            snapshot.seeds[0],
            doi=None,
            title="Strategic Reviews and Platform Learning",
        )
        resolved = CrossrefAdapter(FakeClient()).resolve_seed(seed)
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.doi, "10.5555/future")  # type: ignore[union-attr]

    def test_bibliography_seeds_are_active_before_first_citation(self) -> None:
        snapshot = ingest_project(FIXTURE)
        snapshot = replace(
            snapshot,
            seeds=tuple(replace(seed, cited_in_manuscript=False) for seed in snapshot.seeds),
            cited_keys=(),
        )
        outcome = discover(
            snapshot,
            search_from="2026-08-01",
            search_to="2026-08-21",
            client=FakeClient(),
            limit_per_lane=2,
        )
        self.assertIn("2 seed(s) resolved", outcome.adapter_status["openalex"])

    def test_wrapped_core_question_becomes_one_plain_query(self) -> None:
        snapshot = ingest_project(FIXTURE)
        profile = replace(
            snapshot.profile,
            raw_markdown=(
                "# Test\n\n**Core question**: How should a platform split *B* between\n"
                "pricing and recommendations?\n\n## Quick start\n"
            ),
            sections={"overview": "test"},
        )
        queries = profile_queries(replace(snapshot, profile=profile), {"watch": {"keywords": []}})
        self.assertEqual(
            queries,
            ("How should a platform split B between pricing and recommendations?",),
        )

    def test_wrapped_watch_fields_include_continuation_lines(self) -> None:
        snapshot = ingest_project(FIXTURE)
        sections = dict(snapshot.profile.sections)
        sections["watch"] = (
            "- Keywords: platform learning, dynamic pricing,\n"
            "  strategic review manipulation, response-time threshold\n"
            "- Authors: Ada Lovelace,\n"
            "  Grace Hopper\n"
            "- Venues or working-paper series: Management Science,\n"
            "  Operations Research\n"
        )
        snapshot = replace(
            snapshot,
            profile=replace(snapshot.profile, sections=sections),
        )

        queries = profile_queries(snapshot, {"watch": {"keywords": []}})
        authors = profile_watch_items(snapshot, {"watch": {"authors": []}}, "authors")
        venues = profile_watch_items(snapshot, {"watch": {"venues": []}}, "venues")

        self.assertIn("strategic review manipulation", queries)
        self.assertIn("response-time threshold", queries)
        self.assertIn("Grace Hopper", authors)
        self.assertIn("Operations Research", venues)

    def test_watch_results_are_locally_rechecked_after_fuzzy_provider_search(self) -> None:
        candidate = candidate_from_crossref(crossref_item(), "crossref:authors")
        self.assertTrue(_author_watch_match(candidate, "Ada Lovelace"))  # type: ignore[arg-type]
        self.assertFalse(_author_watch_match(candidate, "Michael Luca"))  # type: ignore[arg-type]
        self.assertTrue(_venue_watch_match(candidate, "Management Science"))  # type: ignore[arg-type]
        self.assertFalse(_venue_watch_match(candidate, "Marketing Science"))  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()

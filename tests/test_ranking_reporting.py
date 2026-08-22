from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from research_radar.cli import main
from research_radar.discovery import Candidate
from research_radar.project import ingest_project
from research_radar.ranking import rank_candidates
from research_radar.reporting import write_briefing, write_weekly
from research_radar.state import (
    last_successful_search_to,
    last_successful_search_to_by_adapter,
    latest_discovery_manifest,
    latest_feedback,
    load_candidate_records,
    save_discovery,
    save_feedback,
    save_snapshot,
)


FIXTURE = Path(__file__).resolve().parents[1] / "examples" / "synthetic-project"


def copy_fixture(root: Path) -> None:
    for source in FIXTURE.iterdir():
        if source.is_file():
            (root / source.name).write_bytes(source.read_bytes())


def candidate(
    identity: str,
    title: str,
    abstract: str,
    *,
    lane: str = "openalex:keywords",
) -> Candidate:
    return Candidate(
        schema_version=1,
        identity=identity,
        doi=identity.removeprefix("doi:") if identity.startswith("doi:") else None,
        openalex_id=None,
        title=title,
        authors=("A. Researcher",),
        year=2026,
        venue="Management Science",
        abstract=abstract,
        url="https://example.test/paper",
        discovered_by=(lane,),
        access_status="abstract",
        evidence_level="abstract",
        cited_by_count=2,
        publication_date="2026-08-20",
    )


class RankingAndReportingTests(unittest.TestCase):
    def test_provider_full_text_is_not_reported_as_a_local_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_fixture(root)
            snapshot = ingest_project(root)
            paper = candidate(
                "doi:10.5555/provider-only",
                "Strategic Review Manipulation in Platform Recommendation",
                "A platform learns while sellers manipulate review signals.",
            )
            paper = Candidate.from_dict(
                {**paper.to_dict(), "access_status": "full-text"}
            )

            ranked = rank_candidates(snapshot, [paper])

            self.assertEqual(ranked[0].candidate.local_access_status, "none")
            self.assertIn("metadata provider reports", ranked[0].evidence_note)
            self.assertNotIn("local full-text file", ranked[0].evidence_note)
            manifest = {
                "search_from": "2026-08-01",
                "search_to": "2026-08-21",
                "queries": ["platform learning"],
                "adapter_status": {"test": "ok"},
                "errors": [],
                "candidate_count": 1,
            }
            report = write_briefing(
                root,
                project_name=snapshot.profile.project_name,
                project_fingerprint=snapshot.fingerprint,
                ranked=ranked,
                manifest=manifest,
                top_n=5,
            )
            content = report.path.read_text(encoding="utf-8")
            self.assertIn(
                "`full-text` / `none` / `abstract`",
                content,
            )
            self.assertIn("research-radar access acquire", content)

    def test_hard_wrapped_exclusion_does_not_create_generic_mini_rules(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_fixture(root)
            profile = root / "RESEARCH_PROFILE.md"
            profile.write_text(
                profile.read_text(encoding="utf-8").replace(
                    "Pure sentiment-classification papers without platform decisions; "
                    "static review helpfulness prediction.",
                    "Suppress generic facility-location heuristics that do not model\n"
                    "responders or retrieval; static review helpfulness prediction.",
                ),
                encoding="utf-8",
            )
            snapshot = ingest_project(root)
            relevant = candidate(
                "doi:10.5555/responders",
                "Modeling Community First Responders",
                "We model responders and emergency availability in a spatial service system.",
                lane="openalex:forward-citations",
            )

            ranked = rank_candidates(snapshot, [relevant])

            self.assertFalse(ranked[0].suppressed)

    def test_exclusion_exception_terms_rescue_a_relevant_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_fixture(root)
            profile = root / "RESEARCH_PROFILE.md"
            profile.write_text(
                profile.read_text(encoding="utf-8").replace(
                    "Pure sentiment-classification papers without platform decisions;",
                    "Suppress generic facility-location heuristics that do not model "
                    "responders or retrieval;",
                ),
                encoding="utf-8",
            )
            snapshot = ingest_project(root)
            relevant = candidate(
                "doi:10.5555/retrieval",
                "Facility Location with Responders and Retrieval",
                "We model responder availability and two-leg retrieval for emergency delivery.",
                lane="openalex:forward-citations",
            )

            ranked = rank_candidates(snapshot, [relevant])

            self.assertFalse(ranked[0].suppressed)

    def test_structurally_relevant_candidate_ranks_above_lexical_noise(self) -> None:
        snapshot = ingest_project(FIXTURE)
        relevant = candidate(
            "doi:10.5555/relevant",
            "Strategic Review Manipulation in Platform Recommendation",
            "A platform uses Bayesian learning to choose recommendations while strategic sellers manipulate review signals at a convex effort cost.",
            lane="openalex:forward-citations",
        )
        noise = candidate(
            "doi:10.5555/noise",
            "Fake Review Detection with Sentiment Classification",
            "A machine learning classifier detects fake review text using sentiment features.",
        )

        ranked = rank_candidates(snapshot, [noise, relevant])

        self.assertEqual(ranked[0].candidate.identity, relevant.identity)
        self.assertGreater(ranked[0].score, ranked[1].score)
        self.assertEqual(ranked[0].relationship, "competes")
        self.assertIn("novelty", ranked[0].scores)
        self.assertIn("priority_risk", ranked[0].scores)
        self.assertTrue(ranked[1].suppressed)

    def test_bibliography_title_is_suppressed_even_when_provider_identity_differs(self) -> None:
        snapshot = ingest_project(FIXTURE)
        seed = snapshot.seeds[0]
        known = candidate(
            "doi:10.5555/provider-added-doi",
            seed.title or "missing title",
            "The provider resolved a DOI that was absent from the local bibliography.",
        )

        ranked = rank_candidates(snapshot, [known])

        self.assertTrue(ranked[0].suppressed)
        self.assertEqual(ranked[0].suppression_reason, "already-in-bibliography")

    def test_feedback_suppresses_candidate_and_report_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_fixture(root)
            snapshot = ingest_project(root)
            save_snapshot(snapshot)
            paper = candidate(
                "doi:10.5555/relevant",
                "Strategic Review Manipulation in Platform Recommendation",
                "A platform learns quality while sellers manipulate review signals.",
            )
            second_paper = candidate(
                "doi:10.5555/second",
                "Marketplace Learning with Strategic Signals",
                "A marketplace learns quality from strategic seller signals.",
            )
            manifest = {
                "search_from": "2026-08-01",
                "search_to": "2026-08-21",
                "queries": ["platform learning"],
                "adapter_status": {"openalex": "ok"},
                "errors": [],
                "candidate_count": 2,
            }
            save_discovery(
                root,
                candidates=[paper.to_dict(), second_paper.to_dict()],
                manifest=manifest,
                status="success",
            )
            self.assertEqual(last_successful_search_to(root), "2026-08-21")
            self.assertEqual(
                last_successful_search_to_by_adapter(root),
                {"openalex": "2026-08-21"},
            )
            save_discovery(
                root,
                candidates=[paper.to_dict(), second_paper.to_dict()],
                manifest={
                    "search_from": "2026-08-21",
                    "search_to": "2026-08-22",
                    "adapter_status": {
                        "crossref": "ok (0 seed(s) resolved)",
                        "openalex": "partial (1 failure)",
                    },
                },
                status="partial",
            )
            self.assertEqual(
                last_successful_search_to_by_adapter(root),
                {"crossref": "2026-08-22", "openalex": "2026-08-21"},
            )
            save_feedback(root, identity=paper.identity, label="known", note="Already cited")
            ranked = rank_candidates(snapshot, [paper], feedback=latest_feedback(root))
            self.assertTrue(ranked[0].suppressed)
            self.assertEqual(ranked[0].suppression_reason, "feedback:known")

            first = write_briefing(
                root,
                project_name=snapshot.profile.project_name,
                project_fingerprint=snapshot.fingerprint,
                ranked=ranked,
                manifest=manifest,
                top_n=5,
            )
            second = write_briefing(
                root,
                project_name=snapshot.profile.project_name,
                project_fingerprint=snapshot.fingerprint,
                ranked=ranked,
                manifest=manifest,
                top_n=5,
            )
            self.assertFalse(first.duplicate)
            self.assertTrue(second.duplicate)
            content = first.path.read_text(encoding="utf-8")
            self.assertIn("No unseen high-signal change", content)
            self.assertIn("feedback:known", content)

            save_feedback(root, identity=paper.identity, label="watch", note="Reconsider")
            reranked = rank_candidates(
                snapshot, [paper], feedback=latest_feedback(root)
            )
            changed = write_briefing(
                root,
                project_name=snapshot.profile.project_name,
                project_fingerprint=snapshot.fingerprint,
                ranked=reranked,
                manifest=manifest,
                top_n=5,
            )
            self.assertFalse(changed.duplicate)
            self.assertNotEqual(changed.path, first.path)
            self.assertEqual(changed.shown_count, 1)

            records = load_candidate_records(root, first_seen_since="2000-01-01T00:00:00+00:00")
            self.assertEqual(len(records), 2)
            self.assertEqual(
                {record["candidate"]["identity"] for record in records},
                {paper.identity, second_paper.identity},
            )
            weekly = write_weekly(
                root,
                project_name=snapshot.profile.project_name,
                project_fingerprint=snapshot.fingerprint,
                ranked=rank_candidates(snapshot, [second_paper]),
                feedback=latest_feedback(root),
                days=7,
                top_n=10,
            )
            weekly_content = weekly.path.read_text(encoding="utf-8")
            self.assertIn("Research Radar Weekly", weekly_content)
            self.assertIn("Pattern synthesis", weekly_content)
            self.assertIn("Full-text queue", weekly_content)
            self.assertIn("research-radar access acquire", weekly_content)

    def test_material_candidate_change_is_returned_for_incremental_reporting(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_fixture(root)
            snapshot = ingest_project(root)
            save_snapshot(snapshot)
            initial = candidate(
                "doi:10.5555/update",
                "Marketplace Learning Under Strategic Review Manipulation",
                "A platform learns product quality while strategic sellers manipulate review signals.",
            )
            manifest = {"search_from": "2026-08-01", "search_to": "2026-08-21"}
            _, new_count, updates = save_discovery(
                root,
                candidates=[initial.to_dict()],
                manifest=manifest,
                status="success",
            )
            enriched = Candidate.from_dict(
                {
                    **initial.to_dict(),
                    "abstract": "A platform learns product quality while strategic sellers manipulate review signals and disclosure.",
                    "access_status": "full-text",
                }
            )
            _, second_new_count, second_updates = save_discovery(
                root,
                candidates=[enriched.to_dict()],
                manifest=manifest,
                status="success",
            )

            self.assertEqual(new_count, 1)
            self.assertFalse(updates)
            self.assertEqual(second_new_count, 0)
            self.assertEqual(second_updates, (initial.identity,))
            stored_manifest = latest_discovery_manifest(root)
            self.assertIsNotNone(stored_manifest)
            assert stored_manifest is not None
            self.assertEqual(stored_manifest["new_candidate_count"], 1)
            self.assertEqual(stored_manifest["materially_updated_count"], 1)
            self.assertEqual(
                stored_manifest["changed_candidate_identities"],
                [initial.identity],
            )

            output = StringIO()
            with redirect_stdout(output):
                exit_code = main(["queue", "--project", str(root)])
            queued = json.loads(output.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(queued["items"][0]["identity"], initial.identity)
            self.assertEqual(queued["items"][0]["next_step"], "acquire")

            save_discovery(
                root,
                candidates=[enriched.to_dict()],
                manifest=manifest,
                status="success",
            )
            no_change_output = StringIO()
            with redirect_stdout(no_change_output):
                main(["queue", "--project", str(root)])
            self.assertEqual(json.loads(no_change_output.getvalue())["items"], [])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from research_radar.discovery import Candidate
from research_radar.distillation import (
    DistillationError,
    build_context,
    validate_for_project,
)
from research_radar.project import ingest_project
from research_radar.ranking import apply_distillations, rank_candidates
from research_radar.state import (
    latest_distillations,
    save_discovery,
    save_distillation,
    save_snapshot,
)


FIXTURE = Path(__file__).resolve().parents[1] / "examples" / "synthetic-project"


def candidate() -> Candidate:
    return Candidate(
        schema_version=1,
        identity="doi:10.5555/deep",
        doi="10.5555/deep",
        openalex_id=None,
        title="Strategic Review Manipulation in Platform Recommendation",
        authors=("A. Researcher",),
        year=2026,
        venue="Management Science",
        abstract="A platform learns quality while sellers manipulate review signals.",
        url="https://doi.org/10.5555/deep",
        discovered_by=("openalex:forward-citations",),
        access_status="abstract",
        evidence_level="abstract",
    )


def payload(identity: str = "doi:10.5555/deep") -> dict[str, object]:
    return {
        "schema_version": 1,
        "candidate_identity": identity,
        "research_question_and_setting": "A platform recommends sellers under uncertain quality.",
        "framework": "A dynamic Bayesian platform-seller model.",
        "mechanism_or_identification": "Sellers distort the signal used for learning.",
        "main_result": "Manipulation changes optimal exploration.",
        "boundary_conditions": ["The signal is endogenous."],
        "project_relationship": "competes",
        "contribution_delta": "It endogenizes the review signal but omits seller entry.",
        "project_consequence": "Clarify why entry changes the learning distortion.",
        "recommended_action": "read-now",
        "evidence_level": "abstract",
        "evidence_sources": ["https://doi.org/10.5555/deep"],
        "confidence": 0.8,
        "unresolved_questions": ["Does the result survive multiple sellers?"],
    }


class DistillationTests(unittest.TestCase):
    def test_validated_distillation_round_trips_and_hydrates_report_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for source in FIXTURE.iterdir():
                if source.is_file():
                    (root / source.name).write_bytes(source.read_bytes())
            snapshot = ingest_project(root)
            save_snapshot(snapshot)
            paper = candidate()
            save_discovery(
                root,
                candidates=[paper.to_dict()],
                manifest={"search_from": "2026-08-01", "search_to": "2026-08-21"},
                status="success",
            )

            normalized = validate_for_project(payload(), project=root, candidate=paper)
            row_id = save_distillation(
                root, identity=paper.identity, payload=normalized
            )
            stored = latest_distillations(root)
            hydrated = apply_distillations(
                rank_candidates(snapshot, [paper]), stored
            )[0]

            self.assertEqual(row_id, 1)
            self.assertEqual(stored[paper.identity]["project_relationship"], "competes")
            self.assertEqual(hydrated.relationship, "competes")
            self.assertEqual(hydrated.recommended_action, "read-now")
            self.assertIn("Contribution delta", hydrated.why_it_matters)
            self.assertEqual(hydrated.scores["distillation_confidence"], 0.8)
            context = build_context(snapshot, paper)
            self.assertEqual(context["available_evidence"]["levels"], ["metadata", "abstract"])

    def test_full_text_claim_requires_local_eligible_evidence(self) -> None:
        paper = candidate()
        full_text = payload()
        full_text["evidence_level"] = "full-text"
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(DistillationError, "unavailable"):
                validate_for_project(full_text, project=temporary, candidate=paper)

    def test_identity_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(DistillationError, "does not match"):
                validate_for_project(
                    payload("doi:10.5555/wrong"),
                    project=temporary,
                    candidate=candidate(),
                )


if __name__ == "__main__":
    unittest.main()

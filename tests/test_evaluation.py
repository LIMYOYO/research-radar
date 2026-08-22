from __future__ import annotations

import unittest
import json
import tempfile
from pathlib import Path

from research_radar.evaluation import evaluate_fixture
from research_radar.project import ingest_project
from research_radar.state import save_discovery, save_snapshot


ROOT = Path(__file__).resolve().parents[1]


class EvaluationTests(unittest.TestCase):
    def test_golden_ranking_baseline(self) -> None:
        result = evaluate_fixture(
            ROOT / "examples" / "synthetic-project",
            ROOT / "tests" / "fixtures" / "golden-candidates.json",
        )

        self.assertEqual(result.candidate_count, 20)
        self.assertEqual(result.relevant_count, 8)
        self.assertGreaterEqual(result.persistent_identifier_rate, 0.95)
        self.assertEqual(result.identity_contract_coverage, 1.0)
        self.assertLess(result.duplicate_identity_rate, 0.02)
        self.assertGreaterEqual(result.precision_at_5, 0.8)
        self.assertEqual(result.keyword_baseline_precision_at_5, 0.6)
        self.assertGreater(result.precision_at_5, result.keyword_baseline_precision_at_5)
        self.assertGreater(result.precision_lift_at_5, 0.0)
        self.assertGreaterEqual(result.reciprocal_rank, 1.0)
        self.assertGreaterEqual(result.recall_in_visible, 0.75)

    def test_project_state_can_be_evaluated_with_private_identity_judgments(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for source in (ROOT / "examples" / "synthetic-project").iterdir():
                if source.is_file():
                    (root / source.name).write_bytes(source.read_bytes())
            source_payload = json.loads(
                (ROOT / "tests" / "fixtures" / "golden-candidates.json").read_text(
                    encoding="utf-8"
                )
            )
            candidates = [case["candidate"] for case in source_payload["candidates"][:3]]
            snapshot = ingest_project(root)
            save_snapshot(snapshot)
            save_discovery(
                root,
                candidates=candidates,
                manifest={"search_from": "2026-08-01", "search_to": "2026-08-21"},
                status="success",
            )
            judgments = root / ".research-radar" / "judgments.json"
            judgments.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "judgments": [
                            {
                                "identity": candidate["identity"],
                                "judgment": "relevant",
                            }
                            for candidate in candidates
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = evaluate_fixture(root, judgments)

            self.assertEqual(result.candidate_count, 3)
            self.assertEqual(result.relevant_count, 3)


if __name__ == "__main__":
    unittest.main()

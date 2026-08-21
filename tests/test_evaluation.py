from __future__ import annotations

import unittest
from pathlib import Path

from research_radar.evaluation import evaluate_fixture


ROOT = Path(__file__).resolve().parents[1]


class EvaluationTests(unittest.TestCase):
    def test_golden_ranking_baseline(self) -> None:
        result = evaluate_fixture(
            ROOT / "examples" / "synthetic-project",
            ROOT / "tests" / "fixtures" / "golden-candidates.json",
        )

        self.assertEqual(result.candidate_count, 20)
        self.assertEqual(result.relevant_count, 8)
        self.assertGreaterEqual(result.precision_at_5, 0.8)
        self.assertGreaterEqual(result.reciprocal_rank, 1.0)
        self.assertGreaterEqual(result.recall_in_visible, 0.75)


if __name__ == "__main__":
    unittest.main()

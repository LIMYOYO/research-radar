from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from research_radar.cli import _doctor, _initialize_project
from research_radar.project import ingest_project, normalize_title, strip_tex_comments
from research_radar.state import save_snapshot, state_counts


FIXTURE = Path(__file__).resolve().parents[1] / "examples" / "synthetic-project"


class ProjectTests(unittest.TestCase):
    def test_ingests_profile_tex_and_bibtex(self) -> None:
        snapshot = ingest_project(FIXTURE)

        self.assertEqual(snapshot.schema_version, 1)
        self.assertEqual(snapshot.profile.project_name, "Marketplace Learning Under Strategic Reviews")
        self.assertEqual(len(snapshot.seeds), 2)
        self.assertEqual(set(snapshot.cited_keys), {"cao2026learning", "luca2016fake"})
        self.assertTrue(all(seed.cited_in_manuscript for seed in snapshot.seeds))
        self.assertEqual(snapshot.seeds[0].doi, "10.1287/mnsc.2023.00320")
        self.assertIn("jointly learns product quality", snapshot.manuscript_text)
        self.assertEqual(len(snapshot.fingerprint), 64)

    def test_comment_stripping_preserves_escaped_percent(self) -> None:
        text = "kept \\% value % removed\nnext"
        self.assertEqual(strip_tex_comments(text), "kept \\% value \nnext")

    def test_title_normalization_ignores_braces_and_punctuation(self) -> None:
        self.assertEqual(normalize_title("{A} Model: Pricing & Reviews"), "a model pricing reviews")

    def test_duplicate_doi_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "README.md").write_text("# Test\n\n## Question\nWhy?", encoding="utf-8")
            (root / "paper.tex").write_text("\\cite{one,two}", encoding="utf-8")
            (root / "refs.bib").write_text(
                """@article{one, title={First}, doi={10.1000/Test}}
@article{two, title={Published version}, doi={https://doi.org/10.1000/test}}
""",
                encoding="utf-8",
            )
            snapshot = ingest_project(root)
            self.assertEqual(
                snapshot.duplicate_identities,
                {"doi:10.1000/test": ("one", "two")},
            )

    def test_snapshot_persistence_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for source in FIXTURE.iterdir():
                if source.is_file():
                    (root / source.name).write_bytes(source.read_bytes())
            snapshot = ingest_project(root)
            path = save_snapshot(snapshot)
            save_snapshot(snapshot)

            self.assertTrue(path.is_file())
            self.assertEqual(state_counts(root)["projects"], 1)
            self.assertEqual(state_counts(root)["seed_papers"], 2)
            with sqlite3.connect(path) as connection:
                count = connection.execute("SELECT COUNT(*) FROM seed_papers").fetchone()[0]
            self.assertEqual(count, 2)

    def test_init_and_doctor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "new-project"
            result = _initialize_project(root)
            self.assertTrue((root / "RESEARCH_PROFILE.md").is_file())
            self.assertTrue((root / ".research-radar" / "config.yaml").is_file())
            self.assertTrue(result["profile_created"])

            diagnosis, exit_code = _doctor(root)
            self.assertEqual(exit_code, 2)
            self.assertFalse(diagnosis["ready"])


if __name__ == "__main__":
    unittest.main()

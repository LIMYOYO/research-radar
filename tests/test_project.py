from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from research_radar.cli import _doctor, _initialize_project
from research_radar.project import ingest_project, normalize_title, strip_tex_comments
from research_radar.state import ProfileChangePending, save_snapshot, state_counts


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
        self.assertIsNone(snapshot.seeds[0].preprint_id)
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

    def test_arxiv_identifier_is_normalized_and_used_for_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "README.md").write_text("# Preprint", encoding="utf-8")
            (root / "paper.tex").write_text(
                "\\cite{preprint}\\bibliography{refs}", encoding="utf-8"
            )
            (root / "refs.bib").write_text(
                """@article{preprint,
  title={A Working Paper},
  archivePrefix={arXiv},
  eprint={2608.12345v2},
  url={https://arxiv.org/abs/2608.12345v2}
}
""",
                encoding="utf-8",
            )
            seed = ingest_project(root).seeds[0]
            self.assertEqual(seed.preprint_id, "arxiv:2608.12345v2")
            self.assertEqual(seed.identity, "preprint:arxiv:2608.12345v2")

    def test_ingestion_follows_tex_and_bibliography_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "README.md").write_text("# Dependency test", encoding="utf-8")
            (root / "paper.tex").write_text(
                "\\input{sections/model}\n\\cite{real}\\bibliography{references}",
                encoding="utf-8",
            )
            (root / "sections").mkdir()
            (root / "sections" / "model.tex").write_text(
                "Included model text \\cite{included}", encoding="utf-8"
            )
            (root / "unused.tex").write_text(
                "Unused draft text \\cite{noise}", encoding="utf-8"
            )
            (root / "references.bib").write_text(
                "@article{real,title={Real}}\n@article{included,title={Included}}",
                encoding="utf-8",
            )
            (root / "sample.bib").write_text(
                "@article{noise,title={Template noise}}", encoding="utf-8"
            )

            snapshot = ingest_project(root)

            self.assertEqual(set(snapshot.cited_keys), {"real", "included"})
            self.assertEqual({seed.citation_key for seed in snapshot.seeds}, {"real", "included"})
            self.assertIn("Included model text", snapshot.manuscript_text)
            self.assertNotIn("Unused draft text", snapshot.manuscript_text)
            self.assertEqual(
                {source.path for source in snapshot.source_files if source.kind == "tex"},
                {"paper.tex", "sections/model.tex"},
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

    def test_profile_change_requires_explicit_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for source in FIXTURE.iterdir():
                if source.is_file():
                    (root / source.name).write_bytes(source.read_bytes())
            save_snapshot(ingest_project(root))
            profile = root / "RESEARCH_PROFILE.md"
            profile.write_text(
                profile.read_text(encoding="utf-8") + "\nApproved new exclusion.\n",
                encoding="utf-8",
            )
            changed = ingest_project(root)
            with self.assertRaisesRegex(ProfileChangePending, "--approve-change"):
                save_snapshot(changed)
            save_snapshot(changed, approve_profile_change=True)
            self.assertEqual(state_counts(root)["projects"], 1)


if __name__ == "__main__":
    unittest.main()

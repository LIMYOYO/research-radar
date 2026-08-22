from __future__ import annotations

import json
import sqlite3
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from research_radar import __version__
from research_radar.cli import _doctor, _initialize_project, main
from research_radar.project import (
    ProjectError,
    ResearchProfile,
    assess_profile,
    ingest_project,
    normalize_title,
    parse_markdown_sections,
    require_profile_ready,
    strip_tex_comments,
)
from research_radar.state import ProfileChangePending, save_snapshot, state_counts


FIXTURE = Path(__file__).resolve().parents[1] / "examples" / "synthetic-project"
ANONYMIZED_LAYOUT = (
    Path(__file__).resolve().parents[1] / "examples" / "anonymized-real-layout"
)


class ProjectTests(unittest.TestCase):
    def test_cli_reports_package_version(self) -> None:
        output = StringIO()
        with redirect_stdout(output), self.assertRaises(SystemExit) as raised:
            main(["--version"])

        self.assertEqual(raised.exception.code, 0)
        self.assertEqual(output.getvalue().strip(), f"research-radar {__version__}")

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

    def test_malformed_bibtex_reports_file_and_repair_hint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "README.md").write_text("# Broken bibliography", encoding="utf-8")
            (root / "paper.tex").write_text(
                "\\cite{broken}\\bibliography{refs}", encoding="utf-8"
            )
            (root / "refs.bib").write_text(
                "@article{broken, title={Unclosed}\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(
                Exception, r"refs\.bib.*unclosed.*delimiter"
            ):
                ingest_project(root)

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

    def test_anonymized_real_layout_ingests_nested_multifile_project(self) -> None:
        snapshot = ingest_project(ANONYMIZED_LAYOUT)

        self.assertEqual(snapshot.profile.project_name, "Capacity Sharing Under Uncertain Demand")
        self.assertEqual(
            set(snapshot.cited_keys),
            {"synthetic-pooling", "synthetic-signals", "synthetic-method"},
        )
        self.assertEqual(len(snapshot.seeds), 3)
        self.assertTrue(all(seed.cited_in_manuscript for seed in snapshot.seeds))
        self.assertEqual(
            {source.path for source in snapshot.source_files if source.kind == "tex"},
            {
                "paper/paper.tex",
                "paper/sections/appendix.tex",
                "paper/sections/introduction.tex",
                "paper/sections/model.tex",
            },
        )
        self.assertEqual(
            {source.path for source in snapshot.source_files if source.kind == "bib"},
            {"paper/appendix-references.bib", "paper/references.bib"},
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

    def test_init_locally_excludes_generated_state_without_editing_gitignore(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            gitignore = root / ".gitignore"
            gitignore.write_text("*.log\n", encoding="utf-8")

            first = _initialize_project(root)
            second = _initialize_project(root)

            self.assertEqual(first["git_exclude"]["status"], "added")
            self.assertEqual(second["git_exclude"]["status"], "already-present")
            exclude = Path(str(first["git_exclude"]["path"]))
            self.assertEqual(
                exclude.read_text(encoding="utf-8").splitlines().count(
                    ".research-radar/"
                ),
                1,
            )
            self.assertEqual(gitignore.read_text(encoding="utf-8"), "*.log\n")
            ignored = subprocess.run(
                ["git", "-C", str(root), "check-ignore", ".research-radar/config.yaml"],
                capture_output=True,
                check=False,
                text=True,
            )
            self.assertEqual(ignored.returncode, 0)

    def test_generic_readme_cannot_masquerade_as_research_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            readme = root / "README.md"
            readme.write_text(
                "# Software package\n\nInstallation instructions.", encoding="utf-8"
            )
            (root / "paper.tex").write_text(
                "\\cite{seed}\\bibliography{refs}", encoding="utf-8"
            )
            (root / "refs.bib").write_text(
                "@article{seed,title={Seed},doi={10.5555/seed}}", encoding="utf-8"
            )

            snapshot = ingest_project(root)
            readiness = assess_profile(snapshot.profile)
            self.assertFalse(readiness.ready)
            self.assertEqual(len(readiness.missing_sections), 10)
            with self.assertRaisesRegex(ProjectError, "Research profile.*incomplete"):
                require_profile_ready(snapshot.profile)

            diagnosis, exit_code = _doctor(root)
            self.assertEqual(exit_code, 2)
            self.assertFalse(diagnosis["ready"])
            profile_check = next(
                item
                for item in diagnosis["checks"]
                if item["check"] == "profile-structure"
            )
            self.assertFalse(profile_check["ok"])

            result = _initialize_project(root)
            self.assertTrue(result["profile_created"])
            self.assertTrue((root / "RESEARCH_PROFILE.md").is_file())
            self.assertEqual(
                readme.read_text(encoding="utf-8"),
                "# Software package\n\nInstallation instructions.",
            )

    def test_complete_profile_passes_doctor(self) -> None:
        snapshot = ingest_project(FIXTURE)
        self.assertTrue(assess_profile(snapshot.profile).ready)
        require_profile_ready(snapshot.profile)
        diagnosis, exit_code = _doctor(FIXTURE)
        self.assertEqual(exit_code, 0)
        self.assertTrue(diagnosis["ready"])

    def test_public_profile_examples_are_ready_but_template_is_not(self) -> None:
        root = Path(__file__).resolve().parents[1]
        paths = sorted((root / "examples" / "profiles").glob("*.md"))
        self.assertEqual(len(paths), 4)
        for path in paths:
            markdown = path.read_text(encoding="utf-8")
            project_name, sections = parse_markdown_sections(markdown)
            profile = ResearchProfile(path.name, project_name, markdown, sections)
            self.assertTrue(assess_profile(profile).ready, path.name)

        template = root / "src" / "research_radar" / "templates" / "RESEARCH_PROFILE.md"
        markdown = template.read_text(encoding="utf-8")
        project_name, sections = parse_markdown_sections(markdown)
        profile = ResearchProfile(template.name, project_name, markdown, sections)
        readiness = assess_profile(profile)
        self.assertFalse(readiness.ready)
        self.assertEqual(len(readiness.placeholder_sections), 10)

    def test_incomplete_profile_is_diagnostic_only_and_not_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = _initialize_project(root)
            self.assertTrue(result["profile_created"])
            (root / "paper.tex").write_text(
                "\\cite{seed}\\bibliography{refs}", encoding="utf-8"
            )
            (root / "refs.bib").write_text(
                "@article{seed,title={Seed},doi={10.5555/seed}}", encoding="utf-8"
            )

            output = StringIO()
            with redirect_stdout(output):
                exit_code = main(["profile", "--project", str(root)])
            payload = json.loads(output.getvalue())

            self.assertEqual(exit_code, 2)
            self.assertFalse(payload["profile_readiness"]["ready"])
            self.assertIsNone(payload["state_file"])
            self.assertFalse((root / ".research-radar" / "state.sqlite").exists())

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

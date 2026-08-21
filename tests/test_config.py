from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from research_radar.config import configured_watch, load_config
from research_radar.presets import INFORMS_JOURNALS, UTD24_JOURNALS
from research_radar.project import ProjectError


class ConfigTests(unittest.TestCase):
    def test_official_venue_presets_have_expected_sizes(self) -> None:
        self.assertEqual(len(INFORMS_JOURNALS), 17)
        self.assertEqual(len(UTD24_JOURNALS), 24)
        self.assertIn("Management Science", UTD24_JOURNALS)
        self.assertIn("Operations Research", INFORMS_JOURNALS)

    def test_presets_expand_without_duplicate_explicit_venues(self) -> None:
        config = {
            "watch": {"venues": ["Management Science"]},
            "venue_presets": ["informs-core"],
        }
        venues = configured_watch(config, "venues")
        self.assertEqual(venues.count("Management Science"), 1)
        self.assertIn("Manufacturing & Service Operations Management", venues)

    def test_unknown_preset_is_actionable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            radar = root / ".research-radar"
            radar.mkdir()
            (radar / "config.yaml").write_text(
                "schema_version: 1\nvenue_presets: [mystery]\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ProjectError, "Choose from"):
                load_config(root)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest
from typing import Any

from research_radar.resolution import resolve_access


class FakeClient:
    def get_json(self, url: str) -> dict[str, Any]:
        if "crossref" in url:
            return {
                "message": {
                    "link": [
                        {
                            "URL": "https://publisher.test/article.pdf",
                            "content-type": "application/pdf",
                            "content-version": "vor",
                        }
                    ]
                }
            }
        if "openalex" in url:
            return {
                "best_oa_location": {
                    "is_oa": True,
                    "pdf_url": "https://repository.test/manuscript.pdf",
                    "landing_page_url": "https://repository.test/item",
                    "license": "cc-by",
                    "version": "acceptedVersion",
                }
            }
        raise AssertionError(url)


class ResolutionTests(unittest.TestCase):
    def test_open_access_pdf_precedes_candidate_and_institutional_routes(self) -> None:
        result = resolve_access("https://doi.org/10.1287/MNSC.2023.00320", client=FakeClient())

        self.assertEqual(result.doi, "10.1287/mnsc.2023.00320")
        self.assertEqual(result.recommended.route, "open-access-pdf")
        self.assertEqual(result.recommended.license, "cc-by")
        self.assertEqual(
            [option.route for option in result.options],
            ["open-access-pdf", "open-access-landing", "crossref-link", "libkey", "doi"],
        )

    def test_provider_failure_keeps_fallback_routes(self) -> None:
        class FailingClient:
            def get_json(self, url: str) -> dict[str, Any]:
                raise RuntimeError("offline")

        result = resolve_access("10.1287/mnsc.2025.00819", client=FailingClient())

        self.assertEqual(result.recommended.route, "libkey")
        self.assertEqual(len(result.errors), 2)
        self.assertEqual({option.route for option in result.options}, {"libkey", "doi"})


if __name__ == "__main__":
    unittest.main()

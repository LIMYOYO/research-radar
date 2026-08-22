from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from research_radar.access import AccessError, import_pdf
from research_radar.acquisition import DownloadReceipt, acquire_pdf, download_candidate
from research_radar.resolution import AccessOption, AccessResolution


def readable_pdf() -> bytes:
    stream = io.BytesIO()
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {NameObject("/F1"): writer._add_object(font)}
            )
        }
    )
    content = DecodedStreamObject()
    content.set_data(b"BT /F1 12 Tf 72 720 Td (Automatically acquired paper) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(content)
    writer.write(stream)
    return stream.getvalue()


def option(
    route: str,
    url: str,
    access_type: str,
    *,
    license_name: str | None = None,
) -> AccessOption:
    return AccessOption(
        route=route,
        url=url,
        access_type=access_type,
        content_type="application/pdf" if "pdf" in route else "text/html",
        version="acceptedVersion",
        license=license_name,
        source="test",
        confidence="test",
    )


def resolution(*options: AccessOption) -> AccessResolution:
    return AccessResolution(
        schema_version=1,
        doi="10.5555/automatic",
        recommended=options[0],
        options=options,
        adapter_status={"test": "ok"},
        errors=(),
    )


class AcquisitionTests(unittest.TestCase):
    def test_downloader_rejects_html_and_declared_oversize_payloads(self) -> None:
        class Response:
            def __init__(self, payload: bytes, content_length: int | None = None) -> None:
                self.payload = payload
                self.sent = False
                self.headers = {
                    "Content-Type": "text/html",
                    **(
                        {"Content-Length": str(content_length)}
                        if content_length is not None
                        else {}
                    ),
                }

            def __enter__(self) -> "Response":
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def read(self, size: int) -> bytes:
                if self.sent:
                    return b""
                self.sent = True
                return self.payload

            def geturl(self) -> str:
                return "https://publisher.test/login"

        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "candidate.pdf"
            with patch(
                "research_radar.acquisition.urlopen",
                return_value=Response(b"<html>login</html>"),
            ):
                with self.assertRaisesRegex(AccessError, "non-PDF"):
                    download_candidate("https://publisher.test/paper", destination)
            with patch(
                "research_radar.acquisition.urlopen",
                return_value=Response(b"%PDF-test", content_length=101),
            ):
                with self.assertRaisesRegex(AccessError, "above"):
                    download_candidate(
                        "https://publisher.test/paper", destination, max_bytes=100
                    )

    def test_oa_candidate_is_validated_archived_and_exported_once(self) -> None:
        data = readable_pdf()
        calls: list[str] = []

        def downloader(url: str, destination: Path, max_bytes: int, timeout: float) -> DownloadReceipt:
            calls.append(url)
            destination.write_bytes(data)
            return DownloadReceipt(url, url, "application/pdf", len(data))

        resolved = resolution(
            option(
                "open-access-pdf",
                "https://repository.test/paper.pdf",
                "full-text",
                license_name="cc-by",
            ),
            option("libkey", "https://libkey.io/10.5555/automatic", "institutional-handoff"),
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = acquire_pdf(
                "10.5555/automatic",
                project=root,
                resolution=resolved,
                downloader=downloader,
            )
            second = acquire_pdf(
                "10.5555/automatic",
                project=root,
                resolution=resolved,
                downloader=lambda *_: (_ for _ in ()).throw(AssertionError("downloaded twice")),
            )

            self.assertEqual(first.status, "acquired")
            self.assertEqual(first.route, "open-access")
            self.assertEqual(first.license, "cc-by")
            self.assertEqual(len(str(first.sha256)), 64)
            self.assertEqual(first.pages, 1)
            self.assertGreater(first.text_characters or 0, 20)
            self.assertTrue(first.codex_eligible)
            self.assertEqual(len(calls), 1)
            self.assertTrue((root / str(first.pdf_file)).is_file())
            self.assertTrue((root / str(first.text_file)).is_file())
            self.assertEqual(second.status, "existing")
            self.assertEqual(second.pdf_file, first.pdf_file)
            ledger = root / ".research-radar" / "access-ledger.jsonl"
            self.assertEqual(len(ledger.read_text(encoding="utf-8").splitlines()), 1)

    def test_failed_public_candidate_returns_explicit_libkey_handoff(self) -> None:
        resolved = resolution(
            option(
                "crossref-link",
                "https://publisher.test/doi/pdf/10.5555/automatic",
                "full-text-candidate",
            ),
            option("libkey", "https://libkey.io/10.5555/automatic", "institutional-handoff"),
        )

        def failing_downloader(
            url: str, destination: Path, max_bytes: int, timeout: float
        ) -> DownloadReceipt:
            raise AccessError("HTML login page returned")

        with tempfile.TemporaryDirectory() as temporary:
            result = acquire_pdf(
                "10.5555/automatic",
                project=temporary,
                resolution=resolved,
                downloader=failing_downloader,
            )
            self.assertEqual(result.status, "authentication-required")
            self.assertFalse(result.codex_eligible)
            self.assertIsNone(result.sha256)
            self.assertEqual(result.handoff_url, "https://libkey.io/10.5555/automatic")
            self.assertEqual(result.attempts[0].status, "failed")
            self.assertIn("login page", result.attempts[0].detail)
            self.assertFalse((Path(temporary) / ".research-radar" / "access-ledger.jsonl").exists())

    def test_current_analysis_policy_controls_an_existing_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.pdf"
            source.write_bytes(readable_pdf())
            import_pdf(
                source,
                doi="10.5555/automatic",
                project=root,
                route="manual",
                ai_use_status="prohibited",
                analysis_policy="strict",
            )

            local = acquire_pdf(
                "10.5555/automatic",
                project=root,
                analysis_policy="local-test",
                downloader=lambda *_: (_ for _ in ()).throw(
                    AssertionError("existing local PDF should be reused")
                ),
            )
            strict = acquire_pdf(
                "10.5555/automatic",
                project=root,
                analysis_policy="strict",
                downloader=lambda *_: (_ for _ in ()).throw(
                    AssertionError("strict policy should stop before download")
                ),
            )

            self.assertEqual(local.status, "existing")
            self.assertTrue(local.codex_eligible)
            self.assertEqual(strict.status, "unavailable")
            self.assertFalse(strict.codex_eligible)
            self.assertIn("strict policy", strict.attempts[0].detail)
            ledger = root / ".research-radar" / "access-ledger.jsonl"
            self.assertEqual(len(ledger.read_text(encoding="utf-8").splitlines()), 2)


if __name__ == "__main__":
    unittest.main()

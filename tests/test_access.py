from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from research_radar.access import (
    AccessError,
    export_pdf_text,
    import_pdf,
    libkey_url,
    normalize_doi,
    paper_filename,
)


class AccessTests(unittest.TestCase):
    def test_normalize_doi_from_url(self) -> None:
        self.assertEqual(
            normalize_doi("https://doi.org/10.1287/MNSC.2025.00819."),
            "10.1287/mnsc.2025.00819",
        )

    def test_libkey_url_encodes_doi(self) -> None:
        self.assertEqual(
            libkey_url("10.1287/mnsc.2025.00819"),
            "https://libkey.io/10.1287/mnsc.2025.00819",
        )

    def test_paper_filename_is_local_filesystem_safe(self) -> None:
        self.assertEqual(
            paper_filename("10.1287/mnsc.2025.00819"),
            "10.1287_mnsc.2025.00819.pdf",
        )

    def test_invalid_doi_is_rejected(self) -> None:
        with self.assertRaises(AccessError):
            normalize_doi("not a DOI")

    def test_import_is_idempotent_and_writes_one_ledger_record(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "download.pdf"
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
            content.set_data(b"BT /F1 12 Tf 72 720 Td (Readable paper text) Tj ET")
            page[NameObject("/Contents")] = writer._add_object(content)
            with source.open("wb") as stream:
                writer.write(stream)

            first_path, first_record, first_duplicate = import_pdf(
                source,
                doi="10.1287/mnsc.2025.00819",
                project=root,
                route="uoft-ebsco",
                ai_use_status="allowed",
                license_name="CC BY 4.0",
            )
            second_path, _, second_duplicate = import_pdf(
                source,
                doi="10.1287/mnsc.2025.00819",
                project=root,
                route="uoft-ebsco",
                ai_use_status="allowed",
                license_name="CC BY 4.0",
            )

            self.assertEqual(first_path, second_path)
            self.assertFalse(first_duplicate)
            self.assertTrue(second_duplicate)
            self.assertEqual(first_record.doi, "10.1287/mnsc.2025.00819")
            self.assertTrue(first_record.codex_readable)
            self.assertTrue(first_record.text_extraction_performed)
            self.assertTrue(first_record.codex_eligible)
            self.assertEqual(first_record.ai_use_status, "allowed")
            ledger = root / ".research-radar" / "access-ledger.jsonl"
            records = [json.loads(line) for line in ledger.read_text().splitlines()]
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["sha256"], first_record.sha256)

    def test_unknown_ai_use_is_not_codex_eligible(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "download.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=612, height=792)
            with source.open("wb") as stream:
                writer.write(stream)

            _, record, _ = import_pdf(
                source,
                doi="10.1287/mnsc.2025.00819",
                project=root,
                route="uoft-ebsco",
                allow_image_only=True,
            )

            self.assertEqual(record.ai_use_status, "unknown")
            self.assertFalse(record.codex_eligible)

    def test_strict_policy_skips_prohibited_text_extraction(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "download.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=612, height=792)
            with source.open("wb") as stream:
                writer.write(stream)

            _, record, _ = import_pdf(
                source,
                doi="10.1287/mnsc.2025.00819",
                project=root,
                route="uoft-ebsco",
                ai_use_status="prohibited",
                analysis_policy="strict",
            )

            self.assertFalse(record.text_extraction_performed)
            self.assertFalse(record.codex_readable)
            self.assertFalse(record.codex_eligible)

    def test_local_test_policy_allows_local_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "download.pdf"
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
            content.set_data(b"BT /F1 12 Tf 72 720 Td (Local test text) Tj ET")
            page[NameObject("/Contents")] = writer._add_object(content)
            with source.open("wb") as stream:
                writer.write(stream)

            _, record, _ = import_pdf(
                source,
                doi="10.1287/mnsc.2025.00819",
                project=root,
                route="uoft-ebsco",
                ai_use_status="prohibited",
                analysis_policy="local-test",
            )

            self.assertTrue(record.text_extraction_performed)
            self.assertTrue(record.codex_readable)
            self.assertTrue(record.codex_eligible)
            self.assertEqual(record.analysis_policy, "local-test")

            destination, exported, duplicate = export_pdf_text(
                root,
                doi="10.1287/mnsc.2025.00819",
            )
            self.assertFalse(duplicate)
            self.assertTrue(destination.is_file())
            self.assertIn("--- Page 1 ---", destination.read_text(encoding="utf-8"))
            self.assertGreater(exported.text_characters, 10)

            _, second, duplicate = export_pdf_text(
                root,
                doi="10.1287/mnsc.2025.00819",
            )
            self.assertTrue(duplicate)
            self.assertEqual(second.sha256, exported.sha256)


if __name__ == "__main__":
    unittest.main()

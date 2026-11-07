import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.archiver import extract_design_attachments


class ArchiverAttachmentsTest(unittest.TestCase):
    def test_extracts_page_attachments_from_design_extension(self):
        design = {
            "designExtension": {
                "design_guide": [
                    {"name": "guide.pdf", "url": "https://example.com/files/guide.pdf"},
                ],
                "design_bom": [
                    {"name": "bom.xlsx", "url": "https://example.com/files/bom.xlsx"},
                ],
                "design_other": [
                    {"name": "readme.txt", "url": "https://example.com/files/readme.txt"},
                ],
            }
        }

        out = extract_design_attachments(design)

        self.assertEqual(len(out), 3)
        self.assertEqual(out[0]["category"], "guide")
        self.assertEqual(out[0]["name"], "guide.pdf")
        self.assertEqual(out[0]["url"], "https://example.com/files/guide.pdf")
        self.assertEqual(out[1]["category"], "bom")
        self.assertEqual(out[2]["category"], "other")

    def test_dedupes_local_names_when_multiple_attachments_share_filename(self):
        design = {
            "designExtension": {
                "design_guide": [
                    {"name": "manual.pdf", "url": "https://example.com/guide/manual.pdf"},
                ],
                "design_other": [
                    {"name": "manual.pdf", "url": "https://example.com/other/manual.pdf"},
                ],
            }
        }

        out = extract_design_attachments(design)

        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["localName"], "manual.pdf")
        self.assertEqual(out[1]["localName"], "manual_1.pdf")
        self.assertEqual(out[1]["relPath"], "file/manual_1.pdf")


if __name__ == "__main__":
    unittest.main()

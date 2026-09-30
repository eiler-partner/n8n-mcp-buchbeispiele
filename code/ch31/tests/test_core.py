from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ch31_lab.core import ContractError, character_error_rate, decide, normalize
from ch31_lab.mcp_stdio import handle, uri
from ch31_lab.pipeline import Store


class QualityTests(unittest.TestCase):
    def test_normalization(self):
        self.assertEqual(normalize("A\n  B\tC"), "A B C")

    def test_character_error_rate(self):
        self.assertEqual(character_error_rate("abc", "axc"), 1 / 3)
        self.assertEqual(character_error_rate("A B", "a   b"), 0)
        with self.assertRaises(ContractError):
            character_error_rate("", "x")

    def test_missing_critical_line_quarantined(self):
        report = decide("Dokument RICHTLINIE-31 mit Reisehinweisen und weiteren Angaben",
                        "Dokument RICHTLINIE-31 mit 15 Arbeitstage und Reisehinweisen",
                        ["RICHTLINIE-31", "15 Arbeitstage"], "ocr", 92)
        self.assertEqual(report["status"], "quarantined")
        self.assertIn("missing_required_phrase", report["reason_codes"])

    def test_good_text_accepted(self):
        text = "Richtlinie RICHTLINIE-31: 15 Arbeitstage. Belege binnen 30 Kalendertagen. Kontakt Team Prozesse."
        result = decide(text, text, ["15 Arbeitstage", "30 Kalendertagen"], "text", None)
        self.assertEqual(result["status"], "accepted")

    def test_low_confidence_quarantined(self):
        text = "Richtlinie RICHTLINIE-31: 15 Arbeitstage. Belege binnen 30 Kalendertagen. Kontakt Team Prozesse."
        result = decide(text, text, ["15 Arbeitstage"], "ocr", 45)
        self.assertIn("low_ocr_confidence", result["reason_codes"])


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(str(Path(self.temp.name) / "records.sqlite3"))

    def test_duplicate_and_resource_filter(self):
        accepted = {"source_sha256": "a" * 64, "case_id": "digital",
                    "document_id": "RICHTLINIE-31", "version": "2026-09",
                    "status": "accepted"}
        quarantined = accepted | {"source_sha256": "b" * 64,
                                  "case_id": "scan_cropped", "status": "quarantined"}
        with patch("ch31_lab.pipeline.inspect", side_effect=[
            (accepted, "Freigegebener Text"), (accepted, "Freigegebener Text"),
            (quarantined, "Ungeprüfter Text")]):
            self.assertFalse(self.store.ingest({"case_id": "digital"})["duplicate"])
            self.assertTrue(self.store.ingest({"case_id": "digital"})["duplicate"])
            self.assertEqual(self.store.ingest({"case_id": "scan_cropped"})["status"],
                             "quarantined")
        records = self.store.accepted()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["text"], "Freigegebener Text")
        meta = {"io.modelcontextprotocol/protocolVersion": "2026-07-28"}
        listing = handle({"id": 1, "method": "resources/list", "params": {"_meta": meta}},
                         self.store)
        self.assertEqual(len(listing["result"]["resources"]), 1)
        reading = handle({"id": 2, "method": "resources/read",
                          "params": {"_meta": meta, "uri": uri(records[0])}}, self.store)
        self.assertEqual(reading["result"]["contents"][0]["text"], "Freigegebener Text")
        denied = handle({"id": 3, "method": "resources/read",
                         "params": {"_meta": meta,
                                    "uri": "ingest://RICHTLINIE-31/2026-09/" + "b" * 16}},
                        self.store)
        self.assertEqual(denied["error"]["code"], -32602)


if __name__ == "__main__":
    unittest.main()

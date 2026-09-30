from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ch32_lab.core import (ContractError, MAX_CHARS, fixed_char_preview, load_policy,
                           normalize, paragraph_chunks, preview, structural_chunks)
from ch32_lab.mcp_stdio import handle, uri
from ch32_lab.store import Store


META = {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientInfo": {"name": "unit", "version": "0.1"},
        "io.modelcontextprotocol/clientCapabilities": {}}


class ChunkTests(unittest.TestCase):
    def test_normalization_and_stable_ids(self):
        self.assertEqual(normalize("A\u0308  B\n"), "Ä B")
        policy = load_policy("2026-09")
        first = structural_chunks(policy)
        self.assertEqual(first, structural_chunks(policy))
        self.assertEqual(len({row["chunk_id"] for row in first}), len(first))
        self.assertTrue(all(row["text_sha256"] and row["parent_id"] for row in first))

    def test_structure_and_table_atomicity(self):
        chunks = structural_chunks(load_policy("2026-09"))
        self.assertTrue(all(len(row["text"]) <= MAX_CHARS for row in chunks))
        self.assertTrue(all(row["parent_id"].endswith(row["section_id"]) for row in chunks))
        tables = [row for row in chunks if row["block_kind"] == "table"]
        self.assertEqual(len(tables), 1)
        self.assertIn("Inland | 30 Kalendertage", tables[0]["text"])
        self.assertIn("Ausland | 30 Kalendertage", tables[0]["text"])
        self.assertTrue(any("Krankenversicherungsnachweis" in row["text"] for row in chunks))
        self.assertTrue(all("Krankenversicherungsnachweis" not in row["text"]
                            or row["section_id"] == "travel" for row in chunks))

    def test_oversize_sentence_rejected_not_cut(self):
        with self.assertRaisesRegex(ContractError, "oversize_sentence"):
            paragraph_chunks("Kompositum" * 30, 80)

    def test_fixed_size_is_only_baseline(self):
        policy = load_policy("2026-09")
        result = fixed_char_preview(policy)
        self.assertGreater(result["chunk_count"], 1)
        self.assertEqual(result["size_unit"], "characters")
        self.assertGreater(preview("2026-09")["structural_chunk_count"], 3)


class VersionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(str(Path(self.temp.name) / "policy.sqlite3"))

    def tearDown(self):
        self.temp.cleanup()

    def test_version_switch_rights_and_history(self):
        with self.assertRaisesRegex(ContractError, "predecessor_required"):
            self.store.publish("2026-09")
        self.store.publish("2026-01")
        old = self.store.visible("2026-08-31", "employee")["chunks"]
        self.assertTrue(any("10 Arbeitstage" in row["text"] for row in old))
        self.assertFalse(any(row["audience"] == "hr" for row in old))
        self.store.publish("2026-09")
        current = self.store.visible("2026-09-29", "employee")["chunks"]
        self.assertTrue(any("15 Arbeitstage" in row["text"] for row in current))
        self.assertFalse(any("10 Arbeitstage" in row["text"] for row in current))
        self.assertFalse(any("45 Kalendertage" in row["text"] for row in current))
        self.assertFalse(any(row["audience"] == "hr" for row in current))
        hr = self.store.visible("2026-09-29", "hr")["chunks"]
        self.assertEqual(len(hr), len(current) + 1)
        self.assertEqual(self.store.history()["versions"][0]["valid_until"], "2026-09-01")

    def test_atomic_rollback_and_duplicate(self):
        self.store.publish("2026-01")
        with self.assertRaisesRegex(ContractError, "injected_failure"):
            self.store.publish("2026-09", fail_after_close=True)
        self.assertIsNone(self.store.history()["versions"][0]["valid_until"])
        self.assertEqual(len(self.store.history()["versions"]), 1)
        self.assertFalse(self.store.publish("2026-09")["duplicate"])
        self.assertTrue(self.store.publish("2026-09")["duplicate"])

    def test_withdrawal_is_visibility_not_physical_delete(self):
        self.store.publish("2026-01")
        self.store.publish("2026-09")
        self.store.withdraw("2026-10-01")
        self.assertEqual(self.store.visible("2026-10-02", "employee")["count"], 0)
        self.assertGreater(self.store.visible("2026-09-29", "employee")["count"], 0)
        self.assertEqual(len(self.store.history()["versions"]), 2)
        self.assertTrue(self.store.withdraw("2026-10-01")["duplicate"])

    def test_invalid_scope_date_and_mcp_read(self):
        self.store.publish("2026-01")
        self.store.publish("2026-09")
        with self.assertRaisesRegex(ContractError, "unknown_role"):
            self.store.visible("2026-09-29", "admin")
        with self.assertRaisesRegex(ContractError, "invalid_date"):
            self.store.visible("2026-02-30", "employee")
        employee = self.store.visible("2026-09-29", "employee")["chunks"]
        hr_only = next(row for row in self.store.visible("2026-09-29", "hr")["chunks"]
                       if row["audience"] == "hr")
        listed = handle({"id": 1, "method": "resources/list", "params": {"_meta": META}},
                        self.store, role="employee", as_of="2026-09-29")
        self.assertEqual(len(listed["result"]["resources"]), len(employee))
        denied = handle({"id": 2, "method": "resources/read",
                         "params": {"_meta": META, "uri": uri(hr_only)}},
                        self.store, role="employee", as_of="2026-09-29")
        self.assertEqual(denied["error"]["code"], -32602)
        spoof = handle({"id": 3, "method": "resources/list",
                        "params": {"_meta": META, "role": "hr"}},
                       self.store, role="employee", as_of="2026-09-29")
        self.assertEqual(spoof["error"]["code"], -32602)

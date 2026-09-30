import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

LAB = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, LAB / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


api = load("api")
init_env = load("init_env")


class ChapterSixTests(unittest.TestCase):
    def test_api_fixture_has_three_rows_and_explicit_offsets(self):
        status, orders = api.response_for("/orders")
        self.assertEqual(status, 200)
        self.assertEqual(len(orders), 3)
        self.assertEqual([row["order_id"] for row in orders], ["A-101", "A-102", "A-103"])
        self.assertEqual(orders[2]["amount"], "0")
        self.assertIsNone(orders[1]["customer_id"])
        self.assertTrue(all(row["created_at"].endswith(("Z", "+02:00")) for row in orders))

    def test_reference_table_has_two_keys(self):
        status, rows = api.response_for("/customers")
        self.assertEqual(status, 200)
        self.assertEqual({row["customer_id"] for row in rows}, {"C-10", "C-20"})
        self.assertEqual(api.response_for("/customers/C-10")[1]["name"], "Aster GmbH")
        self.assertEqual(api.response_for("/customers/missing")[0], 404)

    def test_unknown_endpoints_are_rejected(self):
        self.assertEqual(api.response_for("/admin")[0], 404)
        self.assertEqual(api.response_for("/customers/C-10/extra")[0], 404)

    def test_env_generation_is_private_and_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / ".env"
            self.assertTrue(init_env.create_env(target))
            original = target.read_text()
            self.assertFalse(init_env.create_env(target))
            self.assertEqual(original, target.read_text())
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)

    def test_broken_and_fixed_workflows_only_differ_in_link(self):
        broken = json.loads((LAB / "n8n/workflows/ch06-broken-link.json").read_text())
        fixed = json.loads((LAB / "n8n/workflows/ch06-fixed-link.json").read_text())
        self.assertNotEqual(broken["id"], fixed["id"])
        self.assertFalse(broken["active"])
        self.assertFalse(fixed["active"])
        for data in (broken, fixed):
            nodes = {node["name"]: node for node in data["nodes"]}
            self.assertEqual(len(nodes), 5)
            self.assertEqual(nodes["Fetch Orders"]["parameters"]["url"], "http://api:8066/orders")
            self.assertIn("customer_id", nodes["Lookup Customer"]["parameters"]["url"])
            self.assertIn("Fetch Orders", nodes["Join Result"]["parameters"]["assignments"]["assignments"][0]["value"])
            self.assertEqual(data["pinData"], {})
        broken_code = next(n for n in broken["nodes"] if n["name"] == "Normalize Orders")["parameters"]["jsCode"]
        fixed_code = next(n for n in fixed["nodes"] if n["name"] == "Normalize Orders")["parameters"]["jsCode"]
        self.assertNotIn("pairedItem:", broken_code)
        self.assertIn("pairedItem: { item: i }", fixed_code)
        self.assertEqual(broken_code.replace(" } });", " }, pairedItem: { item: i } });"), fixed_code)

    def test_compose_has_private_ports_and_no_default_password(self):
        compose = (LAB / "compose.yaml").read_text()
        self.assertIn("name: buch-ch06", compose)
        self.assertIn("127.0.0.1:${N8N_PORT:-15680}:5678", compose)
        self.assertIn("${POSTGRES_PASSWORD:?Run python3 init_env.py first}", compose)
        self.assertNotIn("chapter-24-local-db-password", compose)


if __name__ == "__main__":
    unittest.main()

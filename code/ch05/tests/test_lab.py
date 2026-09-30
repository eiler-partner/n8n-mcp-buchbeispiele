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


analyzer = load("analyzer")
init_env = load("init_env")


class AnalyzerTests(unittest.TestCase):
    def test_fixture_is_deterministic_and_flags_review(self):
        source = {"filename": "synthetic_notes.txt", "text": analyzer.FIXTURE.read_text()}
        result = analyzer.analyze(source)
        self.assertEqual(result["verdict"], "review")
        self.assertEqual(result["line_count"], 4)
        self.assertEqual(len(result["sha256"]), 64)
        self.assertEqual(result, analyzer.analyze(source))

    def test_ready_and_empty_document(self):
        self.assertEqual(analyzer.analyze({"filename": "a.txt", "text": "fertig"})["verdict"], "ready")
        self.assertEqual(analyzer.analyze({"filename": "a.txt", "text": ""})["line_count"], 0)

    def test_rejects_invalid_input(self):
        for document in ([], {}, {"filename": "../x", "text": "hi"}, {"filename": "x", "text": 4},
                         {"filename": "x", "text": "a" * (analyzer.MAX_BYTES + 1)}):
            with self.subTest(document=str(document)[:30]), self.assertRaises(ValueError):
                analyzer.analyze(document)

    def test_env_is_created_once_with_private_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / ".env"
            self.assertTrue(init_env.create_env(target))
            original = target.read_text()
            self.assertFalse(init_env.create_env(target))
            self.assertEqual(target.read_text(), original)
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            self.assertNotIn("GENERATE_LOCALLY", original)

    def test_workflow_has_two_triggers_and_no_pin(self):
        data = json.loads((LAB / "n8n/workflows/ch05-file-analysis.json").read_text())
        nodes = {node["name"]: node for node in data["nodes"]}
        self.assertFalse(data["active"])
        self.assertEqual(data["pinData"], {})
        self.assertEqual(nodes["File Intake"]["parameters"]["path"], "ch05-file-analysis")
        self.assertIn("Manual Start", data["connections"])
        self.assertIn("File Intake", data["connections"])
        self.assertEqual(nodes["Analyze Document"]["type"], "n8n-nodes-base.httpRequest")

    def test_compose_is_isolated_and_requires_secrets(self):
        compose = (LAB / "compose.yaml").read_text()
        self.assertIn("name: buch-ch05", compose)
        self.assertIn("127.0.0.1:${N8N_PORT:-15679}:5678", compose)
        self.assertIn("${POSTGRES_PASSWORD:?Run python3 init_env.py first}", compose)
        self.assertNotIn("chapter-24-local-db-password", compose)


if __name__ == "__main__":
    unittest.main()

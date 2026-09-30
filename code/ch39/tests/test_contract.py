"""Static Chapter 39 contracts; Docker daemon is not required."""
from __future__ import annotations

import json
import os
import secrets
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="buch-ch39-test-")
        folder = Path(cls.temp.name)
        cls.values = []
        for name in ("db_password", "n8n_key", "runner_token"):
            value = secrets.token_urlsafe(32)
            (folder / name).write_text(value, encoding="utf-8")
            cls.values.append(value)
        env = dict(os.environ, CH39_SECRET_DIR=str(folder))
        run = subprocess.run(["docker", "compose", "--profile", "scale", "config", "--format", "json"],
                             cwd=ROOT, env=env, text=True, capture_output=True, check=True)
        cls.raw = run.stdout
        cls.services = json.loads(run.stdout)["services"]
        cls.networks = json.loads(run.stdout)["networks"]

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_roles_and_versions(self):
        services = self.services
        self.assertEqual(services["main"]["image"], "n8nio/n8n:2.40.7")
        for name in ("bootstrap", "webhook", "worker1", "worker2"):
            self.assertEqual(services[name]["image"], services["main"]["image"])
            self.assertEqual(services[name]["environment"]["EXECUTIONS_MODE"], "queue")
        for name in ("runner1", "runner2"):
            self.assertEqual(services[name]["image"], "n8nio/runners:2.40.7")
        self.assertTrue(services["main"]["environment"]["N8N_DISABLE_PRODUCTION_MAIN_PROCESS"] == "true")
        self.assertEqual(services["worker2"]["profiles"], ["scale"])
        self.assertEqual(services["runner2"]["profiles"], ["scale"])

    def test_worker_limits_and_manual_offload(self):
        for name in ("worker1", "worker2"):
            self.assertIn("--concurrency=5", str(self.services[name]["command"]))
            env = self.services[name]["environment"]
            self.assertEqual(env["OFFLOAD_MANUAL_EXECUTIONS_TO_WORKERS"], "true")
            self.assertEqual(env["N8N_DEFAULT_BINARY_DATA_MODE"], "database")
            self.assertEqual(env["N8N_RUNNERS_MODE"], "external")
            self.assertNotIn("N8N_CONCURRENCY_PRODUCTION_LIMIT", env)

    def test_sidecar_pairing_and_isolation(self):
        for number in (1, 2):
            worker = self.services[f"worker{number}"]
            runner = self.services[f"runner{number}"]
            self.assertEqual(set(runner["networks"]), {f"broker{number}"})
            self.assertIn(f"broker{number}", worker["networks"])
            self.assertEqual(runner["environment"]["N8N_RUNNERS_TASK_BROKER_URI"],
                             f"http://worker{number}:5679")
            self.assertTrue(runner["read_only"])
            self.assertNotIn("ports", worker)
            self.assertNotIn("ports", runner)

    def test_queues_ports_and_storage(self):
        for name in ("data", "queue", "work", "broker1", "broker2"):
            self.assertTrue(self.networks[name]["internal"])
        self.assertEqual(str(self.services["webhook"]["ports"][0]["published"]), "15739")
        self.assertEqual(str(self.services["main"]["ports"][0]["published"]), "15740")
        for name in ("webhook", "main"):
            self.assertEqual(self.services[name]["ports"][0]["host_ip"], "127.0.0.1")
            self.assertIn("ingress", self.services[name]["networks"])
        for name in ("postgres", "redis", "workload"):
            self.assertNotIn("ports", self.services[name])
        self.assertEqual(set(self.services["redis"]["networks"]), {"queue"})
        self.assertEqual(set(self.services["postgres"]["networks"]), {"data"})

    def test_secrets_not_in_rendered_config(self):
        self.assertTrue(all(value not in self.raw for value in self.values))
        for name in ("runner1", "runner2"):
            self.assertEqual({entry["source"] for entry in self.services[name]["secrets"]},
                             {"runner_token"})
            self.assertNotIn("N8N_RUNNERS_AUTH_TOKEN", self.services[name]["environment"])
        self.assertEqual({entry["source"] for entry in self.services["postgres"]["secrets"]},
                         {"db_password"})

    def test_workflow_uses_real_python_runner(self):
        raw = (ROOT / "n8n/ch39-job.json").read_text(encoding="utf-8")
        workflow = json.loads(raw)
        self.assertTrue(all(value not in raw for value in self.values))
        self.assertNotIn("credentials", raw)
        kinds = [node["type"] for node in workflow["nodes"]]
        self.assertEqual(kinds, ["n8n-nodes-base.webhook", "n8n-nodes-base.httpRequest",
                                 "n8n-nodes-base.code"])
        self.assertEqual(workflow["nodes"][-1]["parameters"]["language"], "pythonNative")
        self.assertIn("http://workload:8139/work", raw)


if __name__ == "__main__":
    unittest.main()

"""Statische Sicherheits- und Kompositionsverträge, ohne Docker-Daemon."""
from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from verify_live import SPOOFED, forwarded_findings


class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="buch-ch38-test-")
        folder = Path(cls.temp.name)
        for name in ("db_password", "n8n_key", "runner_token"):
            (folder / name).write_text(secrets.token_urlsafe(24), encoding="utf-8")
        env = dict(os.environ, CH38_SECRET_DIR=str(folder))
        run = subprocess.run(["docker", "compose", "--profile", "probe", "config", "--format", "json"],
                             cwd=ROOT, env=env, text=True, capture_output=True, check=True)
        cls.config = json.loads(run.stdout)
        cls.config_text = run.stdout
        cls.secret_values = [(folder / name).read_text(encoding="utf-8")
                             for name in ("db_password", "n8n_key", "runner_token")]

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_only_caddy_publishes_loopback(self):
        services = self.config["services"]
        self.assertEqual(services["caddy"]["ports"][0]["host_ip"], "127.0.0.1")
        self.assertEqual(str(services["caddy"]["ports"][0]["published"]), "15738")
        for name in ("n8n", "postgres", "runners", "probe"):
            self.assertNotIn("ports", services[name])

    def test_networks_and_profile(self):
        nets = self.config["networks"]
        self.assertTrue(nets["data"]["internal"])
        self.assertTrue(nets["broker"]["internal"])
        services = self.config["services"]
        self.assertEqual(services["probe"]["profiles"], ["probe"])
        self.assertEqual(set(services["runners"]["networks"]), {"broker"})
        self.assertEqual(set(services["postgres"]["networks"]), {"data"})

    def test_secret_grants_and_no_values(self):
        services = self.config["services"]
        self.assertEqual({s["source"] for s in services["n8n"]["secrets"]},
                         {"db_password", "n8n_key", "runner_token"})
        self.assertEqual({s["source"] for s in services["runners"]["secrets"]}, {"runner_token"})
        self.assertEqual({s["source"] for s in services["postgres"]["secrets"]}, {"db_password"})
        self.assertTrue(all(value not in self.config_text for value in self.secret_values))
        self.assertNotIn("N8N_RUNNERS_AUTH_TOKEN", services["runners"]["environment"])

    def test_current_proxy_and_runner_settings(self):
        env = self.config["services"]["n8n"]["environment"]
        self.assertEqual(env["N8N_WEBHOOK_URL"], "https://localhost:15738/")
        self.assertEqual(env["N8N_PROXY_HOPS"], "1")
        self.assertEqual(env["N8N_RUNNERS_MODE"], "external")
        self.assertNotIn("WEBHOOK_URL", env)
        self.assertEqual(self.config["services"]["runners"]["image"], "n8nio/runners:2.40.7")
        self.assertTrue(self.config["services"]["runners"]["read_only"])

    def test_workflow_contains_no_credentials(self):
        workflow = json.loads((ROOT / "n8n/ch38-probe.json").read_text(encoding="utf-8"))
        self.assertNotIn("credentials", str(workflow))
        code = next(node for node in workflow["nodes"] if node["type"] == "n8n-nodes-base.code")
        self.assertEqual(code["parameters"]["language"], "pythonNative")
        self.assertTrue(all(value not in json.dumps(workflow) for value in self.secret_values))

    def test_caddy_tls_and_streaming(self):
        config = (ROOT / "Caddyfile").read_text(encoding="utf-8")
        self.assertIn("tls internal", config)
        self.assertIn("flush_interval -1", config)
        self.assertNotIn("tls off", config)


class ForwardedHeaderExpectation(unittest.TestCase):
    """Offline checks of the live probe's expectation; no Docker CLI needed."""

    HOST = "localhost:15738"
    SANITIZED = {"X-Forwarded-For": "192.168.65.1", "X-Forwarded-Host": HOST, "X-Forwarded-Proto": "https"}

    def test_caddyfile_trusts_no_proxy(self):
        # The expectation below holds only while Caddy trusts no upstream proxy.
        self.assertNotIn("trusted_proxies", (ROOT / "Caddyfile").read_text(encoding="utf-8"))

    def test_sanitized_headers_pass(self):
        self.assertEqual(forwarded_findings(self.SANITIZED, self.HOST), [])
        self.assertEqual(forwarded_findings(dict(self.SANITIZED, **{"X-Forwarded-For": "fd00::1"}), self.HOST), [])

    def test_each_forged_value_is_reported(self):
        for name, value in SPOOFED.items():
            with self.subTest(header=name):
                self.assertTrue(forwarded_findings(dict(self.SANITIZED, **{name: value}), self.HOST))
        # A trusting proxy would append instead of replace: "forged, peer".
        chained = dict(self.SANITIZED, **{"X-Forwarded-For": "203.0.113.66, 192.168.65.1"})
        self.assertIn("X-Forwarded-For contains the forged client address",
                      forwarded_findings(chained, self.HOST))
        self.assertTrue(forwarded_findings(dict(self.SANITIZED, **{"X-Forwarded-Host": None}), self.HOST))


if __name__ == "__main__":
    unittest.main()

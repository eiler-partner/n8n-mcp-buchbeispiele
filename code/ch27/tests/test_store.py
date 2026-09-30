from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from ch27_lab.store import LabError, RunStore, insert_effect_once


OLD_EFFECTS = """
    ALTER TABLE effects RENAME TO effects_new;
    CREATE TABLE effects (
      run_id TEXT PRIMARY KEY REFERENCES runs(run_id) ON DELETE CASCADE,
      tenant_id TEXT NOT NULL,
      effect_key TEXT NOT NULL UNIQUE,
      note_text TEXT NOT NULL,
      created_at TEXT NOT NULL
    );
    INSERT INTO effects SELECT * FROM effects_new;
    DROP TABLE effects_new;
"""


def effects_key(path):
    with closing(sqlite3.connect(path)) as db:
        columns = [row for row in db.execute("PRAGMA table_info(effects)") if row[5]]
    return [row[1] for row in sorted(columns, key=lambda row: row[5])]


def add_effect(path, effect_key, run_id="run-1", tenant="tenant-a"):
    with closing(sqlite3.connect(path)) as db, db:
        return insert_effect_once(db, run_id, tenant, effect_key,
                                  "Zweite synthetische Notiz",
                                  "2026-09-30T00:00:00+00:00")


def start_payload(run_id="run-1", tenant="tenant-a", session="session-a", budget=2):
    return {"run_id": run_id, "tenant_id": tenant, "session_id": session,
            "text": "Bitte eine synthetische Notiz vorbereiten.",
            "proposed_note": "Synthetischer Testeintrag", "max_steps": budget}


def resume_payload(run_id="run-1", tenant="tenant-a", key="resume-1",
                   revision=1, decision="continue"):
    return {"run_id": run_id, "tenant_id": tenant, "resume_key": key,
            "expected_revision": revision, "decision": decision}


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "state.sqlite"
        self.store = RunStore(self.db)

    def tearDown(self):
        self.temp.cleanup()

    def assert_code(self, code, fn, *args):
        with self.assertRaises(LabError) as caught:
            fn(*args)
        self.assertEqual(caught.exception.code, code)

    def test_start_does_not_write_effect(self):
        result = self.store.start(start_payload())
        self.assertEqual((result["state"], result["revision"], result["effect_count"]),
                         ("awaiting_resume", 1, 0))
        self.assertEqual(result["message_count"], 1)

    def test_start_replay_and_payload_conflict(self):
        self.store.start(start_payload())
        self.assertTrue(self.store.start(start_payload())["replay"])
        self.assert_code("run_id_conflict", self.store.start,
                         start_payload(session="session-other"))

    def test_restart_and_retry_have_one_effect(self):
        self.store.start(start_payload())
        restarted = RunStore(self.db)
        self.assertEqual(restarted.status("run-1", "tenant-a")["state"], "awaiting_resume")
        result = restarted.resume(resume_payload())
        self.assertEqual((result["state"], result["effect_count"], result["revision"]),
                         ("completed", 1, 2))
        after_second_restart = RunStore(self.db)
        retry = after_second_restart.resume(resume_payload())
        self.assertTrue(retry["replay"])
        self.assertEqual(retry["effect_count"], 1)
        self.assertEqual(retry["message_count"], 2)

    def test_effects_key_is_pair_of_run_and_action(self):
        self.assertEqual(effects_key(self.db), ["run_id", "effect_key"])

    def test_two_actions_same_run_one_effect_each(self):
        self.store.start(start_payload())
        self.assertEqual(self.store.resume(resume_payload())["effect_count"], 1)
        # Zweite Aktion desselben Laufs: eigener Eintrag.
        self.assertTrue(add_effect(self.db, "tenant-a:run-1:second_note"))
        self.assertEqual(self.store.status("run-1", "tenant-a")["effect_count"], 2)
        # Retry jeder der beiden Aktionen: kein weiterer Eintrag.
        self.assertFalse(add_effect(self.db, "tenant-a:run-1:second_note"))
        self.assertFalse(add_effect(self.db, "tenant-a:run-1:record_note"))
        self.assertEqual(self.store.status("run-1", "tenant-a")["effect_count"], 2)
        # Retry des Fortsetzungsauftrags bleibt ein Replay ohne Wirkung.
        retry = self.store.resume(resume_payload())
        self.assertTrue(retry["replay"])
        self.assertEqual(retry["effect_count"], 2)

    def test_old_effects_table_is_migrated(self):
        self.store.start(start_payload())
        self.store.resume(resume_payload())
        with closing(sqlite3.connect(self.db)) as db:
            db.executescript(OLD_EFFECTS)
        self.assertEqual(effects_key(self.db), ["run_id"])
        with self.assertRaises(sqlite3.IntegrityError):
            with closing(sqlite3.connect(self.db)) as db, db:
                db.execute("""INSERT INTO effects VALUES
                    ('run-1','tenant-a','tenant-a:run-1:second_note','x','t')""")
        migrated = RunStore(self.db)
        self.assertEqual(effects_key(self.db), ["run_id", "effect_key"])
        self.assertEqual(migrated.status("run-1", "tenant-a")["effect_count"], 1)
        self.assertTrue(add_effect(self.db, "tenant-a:run-1:second_note"))
        self.assertEqual(migrated.status("run-1", "tenant-a")["effect_count"], 2)

    def test_different_resume_key_cannot_repeat(self):
        self.store.start(start_payload())
        self.store.resume(resume_payload())
        self.assert_code("already_final", self.store.resume,
                         resume_payload(key="different"))

    def test_stale_revision_rejected(self):
        self.store.start(start_payload())
        self.assert_code("stale_revision", self.store.resume,
                         resume_payload(revision=2))
        self.assertEqual(self.store.status("run-1", "tenant-a")["effect_count"], 0)

    def test_cross_tenant_hidden(self):
        self.store.start(start_payload())
        self.assert_code("not_found", self.store.status, "run-1", "tenant-b")
        self.assert_code("not_found", self.store.start,
                         start_payload(tenant="tenant-b"))
        self.assert_code("not_found", self.store.resume,
                         resume_payload(tenant="tenant-b"))

    def test_stop_has_no_effect_and_is_replayable(self):
        self.store.start(start_payload())
        stopped = self.store.resume(resume_payload(decision="stop"))
        self.assertEqual((stopped["state"], stopped["effect_count"]), ("stopped", 0))
        self.assertTrue(self.store.resume(resume_payload(decision="stop"))["replay"])
        self.assert_code("already_final", self.store.resume, resume_payload())

    def test_budget_is_terminal(self):
        value = self.store.start(start_payload(budget=1))
        self.assertEqual(value["state"], "budget_exhausted")
        self.assert_code("not_resumable", self.store.resume, resume_payload())

    def test_forget_deletes_context_effect_and_blocks_reuse(self):
        self.store.start(start_payload())
        self.store.resume(resume_payload())
        self.store.start(start_payload("run-2", session="session-b"))
        result = self.store.forget_session(
            {"tenant_id": "tenant-a", "session_id": "session-a"})
        self.assertEqual(result["deleted_runs"], 1)
        self.assert_code("not_found", self.store.status, "run-1", "tenant-a")
        self.assert_code("deleted_run_id", self.store.start, start_payload())
        self.assertEqual(self.store.status("run-2", "tenant-a")["state"], "awaiting_resume")

    def test_invalid_input_and_bool_revision(self):
        self.assert_code("invalid_identifier", self.store.start, start_payload("bad/id"))
        self.assert_code("invalid_budget", self.store.start, start_payload(budget=True))
        self.store.start(start_payload())
        self.assert_code("invalid_revision", self.store.resume,
                         resume_payload(revision=True))
        self.assert_code("invalid_decision", self.store.resume,
                         resume_payload(decision="approve"))


if __name__ == "__main__":
    unittest.main()

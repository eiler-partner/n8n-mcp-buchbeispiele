import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backup_contract import BackupInvalid, goals, manifest, preflight


class BackupContractTest(unittest.TestCase):
    def setUp(self):
        self.archive = b"PGDMP synthetic example"
        self.key = b"test-key-never-for-production"
        self.now = datetime.now(timezone.utc)
        self.record = manifest(self.archive, self.key, source_image="n8nio/n8n:2.40.7",
                               snapshot_at=self.now.isoformat())

    def test_good_manifest(self):
        preflight(self.archive, self.key, self.record, target_image="n8nio/n8n:2.40.7")

    def test_wrong_or_missing_key(self):
        for key, reason in ((b"wrong", "instance_key_mismatch"), (b"", "instance_key_missing")):
            with self.subTest(reason=reason), self.assertRaisesRegex(BackupInvalid, reason):
                preflight(self.archive, key, self.record, target_image="n8nio/n8n:2.40.7")

    def test_corrupt_archive(self):
        with self.assertRaisesRegex(BackupInvalid, "archive_digest_mismatch"):
            preflight(self.archive[:-1], self.key, self.record, target_image="n8nio/n8n:2.40.7")

    def test_unreviewed_image_rejected(self):
        with self.assertRaisesRegex(BackupInvalid, "target_image_not_tested"):
            preflight(self.archive, self.key, self.record, target_image="n8nio/n8n:3.0")

    def test_rpo_rto_math(self):
        metrics = goals(self.now, self.now + timedelta(seconds=20), 35,
                        rpo_target_seconds=120, rto_target_seconds=180)
        self.assertEqual(metrics["observed_rpo_seconds"], 20)
        self.assertTrue(metrics["rpo_met"] and metrics["rto_met"])
        self.assertFalse(goals(self.now, self.now + timedelta(seconds=121), 181,
                               rpo_target_seconds=120, rto_target_seconds=180)["rpo_met"])


if __name__ == "__main__":
    unittest.main()

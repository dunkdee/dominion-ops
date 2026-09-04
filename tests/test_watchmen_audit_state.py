"""Watchmen/Saraqael audit state: machine-local, keyed, and honest about it.

Two properties are load-bearing here. First, audit state must never be written
inside the git checkout — runtime state in a repository gets committed by
accident, and this chain's entries name which secrets exist on the host.
Second, the signing key must not be recoverable from the source, because a key
that ships with the code makes the chain forgeable by anyone who can read it.

The emphasis is on the negative paths: a chain that reports "intact" when it
has been tampered with is worse than no chain at all.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "buddy_core"))

from watchmen import saraqael  # noqa: E402
from watchmen.saraqael import WatchmenStateError  # noqa: E402

POSIX = os.name == "posix"
SOURCE = Path(saraqael.__file__).read_text(encoding="utf-8")


class WatchmenStateTestCase(unittest.TestCase):
    """Every test runs against its own throwaway state directory."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.state = Path(self._tmp.name) / "watchmen"
        self._env(saraqael.ENV_STATE_DIR, str(self.state))
        self._env(saraqael.ENV_HMAC_KEY, None)
        self._env(saraqael.ENV_HMAC_FILE, None)

    def _env(self, name, value):
        previous = os.environ.get(name)
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value

        def restore():
            if previous is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = previous

        self.addCleanup(restore)

    def mode_of(self, path) -> int:
        return stat.S_IMODE(os.stat(path).st_mode)


class StateLocationTests(WatchmenStateTestCase):
    def test_default_state_dir_is_outside_the_repository(self):
        self._env(saraqael.ENV_STATE_DIR, None)
        default = saraqael.state_dir().resolve()
        self.assertEqual(default, (Path.home() / ".dominion" / "watchmen").resolve())
        self.assertNotIn(ROOT, default.parents)
        self.assertNotEqual(default, ROOT)

    def test_state_dir_override_is_honoured_for_every_state_file(self):
        self.assertEqual(saraqael.state_dir(), self.state)
        for path in (saraqael.audit_file(), saraqael.chain_file(), saraqael.key_file()):
            self.assertEqual(path.parent, self.state)

    def test_logging_writes_nothing_into_the_git_checkout(self):
        saraqael.log("test", "state_location_check", "ok")
        self.assertTrue(saraqael.audit_file().exists())
        for legacy in saraqael.LEGACY_ARTIFACTS:
            self.assertFalse(legacy.exists(), f"{legacy} was recreated inside the repository")

    def test_repository_working_tree_stays_clean_after_logging(self):
        saraqael.log("test", "worktree_cleanliness", "ok")
        saraqael.verify_chain()
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--", "buddy_core"],
            cwd=str(ROOT), capture_output=True, text=True, check=True).stdout
        self.assertEqual(dirty.strip().count("watchmen_audit.log"), 0)
        self.assertEqual(dirty.strip().count("watchmen_chain.json"), 0)


class SigningKeyTests(WatchmenStateTestCase):
    def test_no_static_signing_secret_remains_in_source(self):
        self.assertNotIn("_CHAIN_SECRET", SOURCE)
        self.assertNotIn("dominion_phi_1618_saraqael_eternal", SOURCE)
        self.assertNotIn('hmac.new(b"', SOURCE)
        self.assertNotIn("hmac.new(b'", SOURCE)

    def test_default_key_is_generated_and_is_high_entropy(self):
        key = saraqael._resolve_key()
        self.assertTrue(saraqael.key_file().exists())
        self.assertGreaterEqual(len(key), 32)
        self.assertEqual(len(set(key)), len(set(key)))
        self.assertNotIn(b"dominion", key.lower())

    def test_generated_key_persists_across_resolutions(self):
        first = saraqael._resolve_key()
        second = saraqael._resolve_key()
        self.assertEqual(first, second)

    def test_two_separate_state_dirs_get_different_keys(self):
        first = saraqael._resolve_key()
        other = Path(self._tmp.name) / "other"
        self._env(saraqael.ENV_STATE_DIR, str(other))
        self.assertNotEqual(first, saraqael._resolve_key())

    def test_environment_supplied_key_is_used_and_never_written_to_disk(self):
        self._env(saraqael.ENV_HMAC_KEY, "an-explicit-operator-key")
        self.assertEqual(saraqael._resolve_key(), b"an-explicit-operator-key")
        saraqael.log("test", "env_key", "ok")
        self.assertFalse(saraqael.key_file().exists(), "an in-memory key must never be persisted")

    def test_key_file_override_is_used(self):
        external = Path(self._tmp.name) / "external.key"
        external.write_bytes(b"key-from-an-external-file\n")
        if POSIX:
            external.chmod(0o600)
        self._env(saraqael.ENV_HMAC_FILE, str(external))
        self.assertEqual(saraqael._resolve_key(), b"key-from-an-external-file")

    def test_missing_explicit_key_file_fails_closed(self):
        self._env(saraqael.ENV_HMAC_FILE, str(Path(self._tmp.name) / "absent.key"))
        with self.assertRaises(WatchmenStateError):
            saraqael._resolve_key()
        with self.assertRaises(WatchmenStateError):
            saraqael.log("test", "should_not_be_written", "ok")
        self.assertFalse(saraqael.audit_file().exists())

    def test_blank_key_sources_fail_closed_rather_than_defaulting(self):
        self._env(saraqael.ENV_HMAC_KEY, "   ")
        with self.assertRaises(WatchmenStateError):
            saraqael._resolve_key()

    def test_blank_key_file_fails_closed(self):
        empty = Path(self._tmp.name) / "empty.key"
        empty.write_bytes(b"\n")
        if POSIX:
            empty.chmod(0o600)
        self._env(saraqael.ENV_HMAC_FILE, str(empty))
        with self.assertRaises(WatchmenStateError):
            saraqael._resolve_key()

    def test_key_material_never_appears_in_audit_entries_or_log(self):
        key = saraqael._resolve_key().decode()
        entry = saraqael.log("test", "key_leak_check", "ok", {"note": "routine"})
        self.assertNotIn(key, json.dumps(entry))
        self.assertNotIn(key, saraqael.audit_file().read_text(encoding="utf-8"))
        self.assertNotIn(key, json.dumps(saraqael.report()))
        self.assertNotIn(key, saraqael.chain_file().read_text(encoding="utf-8"))


@unittest.skipUnless(POSIX, "POSIX permission bits")
class PermissionTests(WatchmenStateTestCase):
    def test_state_files_are_owner_only(self):
        saraqael.log("test", "permission_check", "ok")
        self.assertEqual(self.mode_of(saraqael.state_dir()), 0o700)
        self.assertEqual(self.mode_of(saraqael.key_file()), 0o600)
        self.assertEqual(self.mode_of(saraqael.audit_file()), 0o600)
        self.assertEqual(self.mode_of(saraqael.chain_file()), 0o600)

    def test_chain_permissions_survive_rewrites(self):
        for _ in range(3):
            saraqael.log("test", "repeat_write", "ok")
        self.assertEqual(self.mode_of(saraqael.chain_file()), 0o600)


class ChainIntegrityTests(WatchmenStateTestCase):
    def write_entries(self, count=3):
        return [saraqael.log("test", f"event_{i}", "ok", {"i": i}) for i in range(count)]

    def rewrite(self, entries):
        saraqael.audit_file().write_text(
            "".join(json.dumps(e, ensure_ascii=True) + "\n" for e in entries),
            encoding="utf-8")

    def read_entries(self):
        return [json.loads(line) for line in saraqael.audit_file().read_text(encoding="utf-8").splitlines() if line]

    def test_empty_state_verifies_as_empty(self):
        result = saraqael.verify_chain()
        self.assertTrue(result["valid"])
        self.assertEqual(result["entries_checked"], 0)

    def test_valid_chain_verifies(self):
        self.write_entries(4)
        result = saraqael.verify_chain()
        self.assertTrue(result["valid"], result["message"])
        self.assertEqual(result["entries_checked"], 4)
        self.assertIsNone(result["first_break"])

    def test_sequence_and_linkage_are_continuous(self):
        entries = self.write_entries(3)
        self.assertEqual([e["seq"] for e in entries], [1, 2, 3])
        self.assertEqual(entries[0]["prev_hash"], "GENESIS")
        for earlier, later in zip(entries, entries[1:]):
            self.assertEqual(later["prev_hash"], earlier["hash"])

    def test_modified_entry_fails_verification(self):
        self.write_entries(3)
        entries = self.read_entries()
        entries[1]["details"] = {"i": "tampered"}
        self.rewrite(entries)
        result = saraqael.verify_chain()
        self.assertFalse(result["valid"])
        self.assertEqual(result["first_break"], 2)

    def test_deleted_entry_fails_verification(self):
        self.write_entries(3)
        entries = self.read_entries()
        del entries[1]
        self.rewrite(entries)
        self.assertFalse(saraqael.verify_chain()["valid"])

    def test_reordered_entries_fail_verification(self):
        self.write_entries(3)
        entries = self.read_entries()
        entries[0], entries[1] = entries[1], entries[0]
        self.rewrite(entries)
        self.assertFalse(saraqael.verify_chain()["valid"])

    def test_truncated_log_fails_against_recorded_chain_state(self):
        self.write_entries(3)
        entries = self.read_entries()
        self.rewrite(entries[:2])
        self.assertFalse(saraqael.verify_chain()["valid"])

    def test_wrong_key_fails_verification(self):
        self.write_entries(2)
        self.assertTrue(saraqael.verify_chain()["valid"])
        self._env(saraqael.ENV_HMAC_KEY, "a-different-key-entirely")
        self.assertFalse(saraqael.verify_chain()["valid"])

    def test_corrupt_log_line_is_not_silently_skipped(self):
        self.write_entries(2)
        with open(saraqael.audit_file(), "a", encoding="utf-8") as f:
            f.write("{ this is not json\n")
        result = saraqael.verify_chain()
        self.assertFalse(result["valid"])
        self.assertIn("JSON", result["message"])

    def test_corrupt_chain_state_is_not_trusted(self):
        self.write_entries(2)
        saraqael.chain_file().write_text("{ broken", encoding="utf-8")
        result = saraqael.verify_chain()
        self.assertFalse(result["valid"])
        self.assertIn("untrusted", result["message"].lower())

    def test_deleted_chain_state_will_not_fabricate_a_new_genesis(self):
        self.write_entries(2)
        saraqael.chain_file().unlink()
        with self.assertRaises(WatchmenStateError):
            saraqael.log("test", "after_state_deletion", "ok")
        self.assertFalse(saraqael.verify_chain()["valid"])

    def test_missing_log_with_populated_chain_state_reports_truthfully(self):
        self.write_entries(2)
        saraqael.audit_file().unlink()
        result = saraqael.verify_chain()
        self.assertFalse(result["valid"])
        self.assertIn("missing", result["message"].lower())

    def test_report_never_claims_validity_the_chain_cannot_prove(self):
        self.write_entries(2)
        entries = self.read_entries()
        entries[0]["status"] = "forged"
        self.rewrite(entries)
        self.assertFalse(saraqael.report()["chain_valid"])

    def test_chain_state_is_replaced_atomically(self):
        self.write_entries(2)
        leftovers = [p.name for p in saraqael.state_dir().iterdir() if p.name.endswith(".tmp")]
        self.assertEqual(leftovers, [])
        json.loads(saraqael.chain_file().read_text(encoding="utf-8"))


class LegacyArtifactTests(WatchmenStateTestCase):
    def test_legacy_repo_paths_are_git_ignored(self):
        for legacy in saraqael.LEGACY_ARTIFACTS:
            result = subprocess.run(["git", "check-ignore", "-q", str(legacy)], cwd=str(ROOT), capture_output=True)
            self.assertEqual(result.returncode, 0, f"{legacy} is not git-ignored")

    def test_legacy_files_are_never_read_as_authoritative(self):
        for legacy in saraqael.LEGACY_ARTIFACTS:
            legacy.parent.mkdir(parents=True, exist_ok=True)
        saraqael.LEGACY_ARTIFACTS[0].write_text(
            json.dumps({"seq": 1, "ts": "x", "source": "forged", "event": "forged",
                        "status": "ok", "threat_level": "none", "details": {},
                        "prev_hash": "GENESIS", "hash": "0" * 64}) + "\n",
            encoding="utf-8")
        saraqael.LEGACY_ARTIFACTS[1].write_text(
            json.dumps({"last_hash": "0" * 64, "count": 1}), encoding="utf-8")
        self.addCleanup(lambda: [p.unlink() for p in saraqael.LEGACY_ARTIFACTS if p.exists()])
        self.assertEqual(saraqael.verify_chain()["entries_checked"], 0)
        entry = saraqael.log("test", "legacy_isolation", "ok")
        self.assertEqual(entry["seq"], 1)
        self.assertEqual(entry["prev_hash"], "GENESIS")
        self.assertTrue(saraqael.verify_chain()["valid"])

    def test_legacy_artifacts_are_reported_without_claiming_continuity(self):
        self.assertEqual(saraqael.legacy_repo_artifacts(), [])
        saraqael.LEGACY_ARTIFACTS[0].write_text("legacy\n", encoding="utf-8")
        self.addCleanup(saraqael.LEGACY_ARTIFACTS[0].unlink)
        self.assertEqual(saraqael.legacy_repo_artifacts(), [str(saraqael.LEGACY_ARTIFACTS[0])])
        self.assertEqual(saraqael.verify_chain()["entries_checked"], 0)


class SecurityLanguageTests(unittest.TestCase):
    def test_module_claims_tamper_evidence_not_tamper_proofing(self):
        lowered = SOURCE.lower()
        self.assertIn("tamper-evident", lowered)
        start = 0
        while True:
            found = lowered.find("tamper-proof", start)
            if found == -1:
                break
            context = lowered[max(0, found - 40):found]
            self.assertIn("not", context, "'tamper-proof' is claimed rather than disclaimed")
            start = found + 1


class SentinelIntegrationTests(WatchmenStateTestCase):
    def test_sentinel_audit_helper_writes_to_the_machine_local_chain(self):
        from watchmen.saraqael import log as saraqael_log
        saraqael_log("sentinel", "env_key_sync", "ok", {"key": "EXAMPLE_KEY"})
        self.assertTrue(saraqael.verify_chain()["valid"])
        self.assertEqual(saraqael.verify_chain()["entries_checked"], 1)
        for legacy in saraqael.LEGACY_ARTIFACTS:
            self.assertFalse(legacy.exists())


if __name__ == "__main__":
    unittest.main()

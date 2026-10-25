"""Run against an isolated, temporary, in-memory SpacetimeDB server.

Usage: python3 spacetime/spacetimedb/tests/test_session_expiration.py
Requires the spacetime CLI and the module's installed npm dependencies.
"""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import unittest


MODULE = Path(__file__).resolve().parents[1]


class SessionExpirationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="shrimp-expiration-test-")
        cls.addClassCleanup(cls.temp.cleanup)
        root = Path(cls.temp.name)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        cls.server = f"http://127.0.0.1:{port}"
        cls.database = "session-expiration-test"
        log = (root / "server.log").open("w+")
        cls.server_log = log
        cls.addClassCleanup(log.close)
        process = subprocess.Popen(
            ["spacetime", "start", "--in-memory", "--non-interactive",
             "--listen-addr", f"127.0.0.1:{port}", "--data-dir", str(root / "data"),
             "--page_pool_max_size", "268435456"],
            stdout=log, stderr=subprocess.STDOUT,
        )

        def stop_server():
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

        cls.addClassCleanup(stop_server)
        for _ in range(100):
            if process.poll() is not None:
                log.seek(0)
                raise RuntimeError(log.read())
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=.1):
                    break
            except OSError:
                time.sleep(.05)
        else:
            raise RuntimeError("Temporary test database did not start.")

        # A test-only trigger exercises the real scheduler without waiting 20 minutes.
        project = root / "module"
        (project / "src").mkdir(parents=True)
        for name in ["package.json", "tsconfig.json"]:
            shutil.copyfile(MODULE / name, project / name)
        (project / "node_modules").symlink_to(MODULE / "node_modules", target_is_directory=True)
        source = (MODULE / "src/index.ts").read_text()
        source += """
export const scheduleExpirationTest = spacetimedb.reducer((ctx) => {
  ctx.db.sessionCleanupSchedule.insert({
    scheduledId: 2n,
    scheduledAt: ScheduleAt.time(ctx.timestamp.microsSinceUnixEpoch + 100_000n),
  });
});
"""
        (project / "src/index.ts").write_text(source)
        cls.cli("publish", cls.database, "--module-path", str(project), "--delete-data=never")

    @classmethod
    def cli(cls, command, *args, check=True):
        result = subprocess.run(
            ["spacetime", command, *args, "--server", cls.server, "--no-config", "--yes"],
            text=True, capture_output=True, timeout=45,
        )
        if check and result.returncode:
            cls.server_log.seek(0)
            raise AssertionError(result.stdout + result.stderr + cls.server_log.read()[-6000:])
        return result

    @classmethod
    def call(cls, reducer, *args, check=True):
        return cls.cli("call", cls.database, reducer, *(json.dumps(arg) for arg in args), check=check)

    @classmethod
    def rows(cls, table):
        result = cls.cli("sql", cls.database, f"SELECT * FROM {table}", "--format", "json")
        statement = json.loads(result.stdout)[0]
        names = [column["name"]["some"] for column in statement["schema"]["elements"]]
        return [dict(zip(names, row)) for row in statement["rows"]]

    def setUp(self):
        for row in self.rows("game_session"):
            self.call("delete_session", row["session_id"])

    def save(self, session_id, updated_at, *, expected="", messages=()):
        state = json.dumps({"created_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()})
        self.call("upsert_session_with_messages", session_id, state, updated_at, expected, list(messages))

    @staticmethod
    def message(session_id, pitch_index):
        return {
            "message_id": f"{session_id}-{pitch_index}", "session_id": session_id,
            "pitch_id": f"pitch-{pitch_index}", "pitch_index": pitch_index,
            "sequence": 0, "round_number": 1, "speaker": "Founder",
            "kind": "answer", "text": "Test conversation", "source": "offline",
        }

    def test_expired_sessions_and_all_pitch_messages_are_deleted(self):
        now = datetime.now(timezone.utc)
        stale = (now - timedelta(hours=2, minutes=1)).isoformat()
        recent = (now - timedelta(hours=1, minutes=59)).isoformat()
        self.save("expired", stale, messages=[self.message("expired", 1), self.message("expired", 2)])
        self.save("recent", recent, messages=[self.message("recent", 1)])
        self.call("cleanup_expired_sessions")
        self.assertEqual([row["session_id"] for row in self.rows("game_session")], ["recent"])
        self.assertEqual([row["message_id"] for row in self.rows("conversation_message")], ["recent-1"])

    def test_recently_updated_old_session_is_retained(self):
        old = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
        self.save("renewed", old)
        self.save("renewed", datetime.now(timezone.utc).isoformat(), expected=old)
        self.call("cleanup_expired_sessions")
        self.assertEqual([row["session_id"] for row in self.rows("game_session")], ["renewed"])

    def test_invalid_and_future_timestamps_are_preserved(self):
        self.save("invalid", "not-a-timestamp")
        self.save("future", (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat())
        self.call("cleanup_expired_sessions")
        self.assertEqual({row["session_id"] for row in self.rows("game_session")}, {"invalid", "future"})

    def test_cleanup_is_idempotent_and_keeps_one_twenty_minute_schedule(self):
        before = self.rows("session_cleanup_schedule")
        self.assertEqual(len(before), 1)
        for _ in range(2):
            self.call("cleanup_expired_sessions")
        self.assertEqual(self.rows("session_cleanup_schedule"), before)
        self.assertIn("1200000000", json.dumps(before))

    def test_expired_write_cannot_recreate_a_deleted_session(self):
        old = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
        self.save("deleted", old)
        self.call("cleanup_expired_sessions")
        result = self.call("upsert_session", "deleted", "{}", datetime.now(timezone.utc).isoformat(), old, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.rows("game_session"), [])

    def test_scheduler_runs_the_actual_sweep(self):
        self.save("scheduled-expiry", (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat())
        self.call("schedule_expiration_test")
        for _ in range(50):
            if not self.rows("game_session"):
                break
            time.sleep(.1)
        self.assertEqual(self.rows("game_session"), [])
        self.assertEqual(len(self.rows("session_cleanup_schedule")), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)

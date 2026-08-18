import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HEALER = ROOT / "scripts" / "buddy_bounded_self_heal.sh"
OBSERVER = ROOT / "scripts" / "runtime_observer.sh"


class LocalRuntimeAutomationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.mock_state = self.root / "mock-state"
        self.mock_log = self.root / "mock-log"
        self.runtime_state = self.root / "runtime-state"
        self._write_mocks()

    def tearDown(self):
        self.temp.cleanup()

    def _write(self, name: str, body: str) -> None:
        path = self.bin / name
        path.write_text(textwrap.dedent(body), encoding="utf-8")
        path.chmod(0o755)

    def _write_mocks(self) -> None:
        self._write(
            "systemctl",
            r"""#!/usr/bin/env bash
set -u
cmd="${1:-}"
shift || true
case "$cmd" in
  is-active)
    [[ "${1:-}" == --quiet ]] && shift
    unit="${1:-}"
    case "$unit" in
      dominion-nemotron.service|dominion-email-monitor.service|dominion-affiliate.timer|dominion-scout.timer|dominion-wholesale.timer)
        echo inactive; exit 3 ;;
      dominion-buddy-web.service)
        if [[ "${MOCK_MODE:-healthy}" == repair && ! -f "$MOCK_STATE/repaired" ]]; then
          echo inactive; exit 3
        fi
        if [[ "${MOCK_MODE:-healthy}" == fail ]]; then
          echo inactive; exit 3
        fi
        echo active; exit 0 ;;
      *) echo active; exit 0 ;;
    esac
    ;;
  is-enabled)
    unit="${1:-}"
    case "$unit" in
      dominion-nemotron.service|dominion-email-monitor.service|dominion-affiliate.timer|dominion-scout.timer|dominion-wholesale.timer)
        echo disabled; exit 1 ;;
      *) echo enabled; exit 0 ;;
    esac
    ;;
  restart)
    unit="${1:-}"
    printf 'restart %s\n' "$unit" >>"$MOCK_LOG"
    mkdir -p "$MOCK_STATE"
    touch "$MOCK_STATE/repaired"
    exit 0
    ;;
  show)
    echo 0
    exit 0
    ;;
  *) echo "unexpected systemctl command: $cmd" >&2; exit 90 ;;
esac
""",
        )
        self._write(
            "curl",
            r"""#!/usr/bin/env bash
set -u
url="${!#}"
case "$url" in
  *127.0.0.1:5070/buddy)
    if [[ "${MOCK_MODE:-healthy}" == repair && ! -f "$MOCK_STATE/repaired" ]]; then
      printf 500
    elif [[ "${MOCK_MODE:-healthy}" == fail ]]; then
      printf 500
    else
      printf 401
    fi
    ;;
  *127.0.0.1:5101/api/proposals) printf 200 ;;
  *) printf 200 ;;
esac
""",
        )
        self._write(
            "ss",
            r"""#!/usr/bin/env bash
set -u
if [[ "${MOCK_MODE:-healthy}" != repair || -f "$MOCK_STATE/repaired" ]]; then
  echo 'LISTEN 0 128 127.0.0.1:5070 0.0.0.0:*'
fi
if [[ "${MOCK_MODE:-healthy}" != fail ]]; then
  echo 'LISTEN 0 128 127.0.0.1:5101 0.0.0.0:*'
fi
""",
        )
        self._write(
            "journalctl",
            """#!/usr/bin/env bash
exit 0
""",
        )
        self._write(
            "gcloud",
            """#!/usr/bin/env bash
echo "ERROR: firewall rule was not found" >&2
exit 1
""",
        )

    def _run(self, script: Path, mode: str = "healthy") -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update({
            "PATH": f"{self.bin}:/usr/bin:/bin",
            "MOCK_MODE": mode,
            "MOCK_STATE": str(self.mock_state),
            "MOCK_LOG": str(self.mock_log),
            "DOMINION_STATE_DIR": str(self.runtime_state),
            "DOMINION_REPAIR_SETTLE_SECONDS": "0",
        })
        return subprocess.run(
            ["bash", str(script)],
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )

    def test_healthy_healer_makes_no_restart(self):
        result = self._run(HEALER)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("BUDDY_SELF_HEAL=NO_ACTION_HEALTHY", result.stdout)
        self.assertFalse(self.mock_log.exists())

    def test_healer_restarts_only_the_failed_allowlisted_service(self):
        result = self._run(HEALER, mode="repair")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("BUDDY_SELF_HEAL=RECOVERED attempt=1", result.stdout)
        self.assertEqual(
            self.mock_log.read_text(encoding="utf-8").splitlines(),
            ["restart dominion-buddy-web.service"],
        )

    def test_observer_passes_without_any_mutation_command(self):
        result = self._run(OBSERVER)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("RUNTIME_OBSERVER=PASS", result.stdout)
        self.assertNotIn("CHECK=FAIL", result.stdout)
        self.assertFalse(self.mock_log.exists())


if __name__ == "__main__":
    unittest.main()

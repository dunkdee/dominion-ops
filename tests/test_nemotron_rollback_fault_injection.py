from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACTIVATE = ROOT / "scripts" / "nemotron" / "activate_nemotron.sh"


def test_actual_rollback_function_restores_prior_state(tmp_path: Path) -> None:
    """Exercise the production rollback function with isolated command shims.

    No production path is touched. The test extracts the exact function definitions
    from the activation script, replaces systemctl/sudo/ss/curl with deterministic
    local shims, injects a failed post-mutation state, and requires restoration of
    the prior unit, integrity contract, and release pointer plus removal of the
    failed release.
    """
    source = ACTIVATE.read_text(encoding="utf-8")
    marker = '[[ "$DEPLOY_SHA" =~ ^[0-9a-fA-F]{40}$ ]]'
    assert marker in source
    library = tmp_path / "activation-functions.sh"
    library.write_text(source.split(marker, 1)[0], encoding="utf-8")

    runtime = tmp_path / "runtime-root"
    backup = runtime / "backups" / "before"
    prior = runtime / "releases" / "prior"
    failed = runtime / "releases" / ("f" * 40)
    live_contract = tmp_path / "system-integrity-agent.json"
    unit = tmp_path / "dominion-nemotron.service"
    staging = "/tmp/dominion-nemotron-stage.fault-test"

    backup.mkdir(parents=True)
    prior.mkdir(parents=True)
    failed.mkdir(parents=True)
    (runtime / "runtime").mkdir(parents=True)
    (backup / "unit").write_text("prior-unit\n", encoding="utf-8")
    (backup / "integrity-contract.json").write_text("prior-contract\n", encoding="utf-8")
    unit.write_text("candidate-unit\n", encoding="utf-8")
    live_contract.write_text("candidate-contract\n", encoding="utf-8")
    (runtime / "runtime" / "release").symlink_to(failed)

    bash = f'''
set -Eeuo pipefail
source {library!s}
trap - EXIT
SERVICE=dominion-nemotron.service
RUNTIME={runtime!s}
LIVE_CONTRACT={live_contract!s}
UNIT={unit!s}
backup={backup!s}
prior_release={prior!s}
new_release={failed!s}
staging={staging!s}
mkdir -p "$staging"
systemctl() {{ return 0; }}
sudo() {{ "$@"; }}
ss() {{ return 0; }}
curl() {{ printf '200'; }}
rollback
cmp -s "$UNIT" "$backup/unit"
cmp -s "$LIVE_CONTRACT" "$backup/integrity-contract.json"
[ "$(readlink -f "$RUNTIME/runtime/release")" = "$prior_release" ]
[ ! -e "$new_release" ]
[ ! -e "{staging}" ]
'''
    completed = subprocess.run(["bash", "-c", bash], text=True, capture_output=True)
    assert completed.returncode == 0, completed.stdout + "\n" + completed.stderr
    assert "NEMOTRON_ROLLBACK=BEGIN" in completed.stdout
    assert "NEMOTRON_ROLLBACK=COMPLETE" in completed.stdout

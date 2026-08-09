#!/usr/bin/env bash
set -euo pipefail

: "${DEPLOY_SHA:?DEPLOY_SHA is required}"
: "${OBSIDIAN_PASSWORD:?OBSIDIAN_PASSWORD is required}"
: "${RUN_ID:?RUN_ID is required}"

repo="$HOME/dominion-ops"
vault="${VAULT_PATH:-$HOME/vault}"
current="$vault/Dominion-Brain"
operator_notes="$vault/Dominion-Operator-Notes"
stage="$vault/.dominion-brain-stage-${DEPLOY_SHA:0:12}-${RUN_ID}"
backup="$vault/.dominion-brain-backup-${RUN_ID}"

[[ "$DEPLOY_SHA" =~ ^[0-9a-f]{40}$ ]] || { echo "BRAIN_DEPLOY=FAIL reason=invalid_sha"; exit 1; }
test -d "$repo/.git" || { echo "BRAIN_DEPLOY=FAIL reason=repo_missing"; exit 1; }
cd "$repo"
actual_sha="$(git rev-parse HEAD)"
test "$actual_sha" = "$DEPLOY_SHA" || {
  echo "BRAIN_DEPLOY=FAIL reason=vm_sha_mismatch expected=$DEPLOY_SHA actual=$actual_sha"
  exit 1
}

test -d "$vault" || { echo "BRAIN_DEPLOY=FAIL reason=vault_missing"; exit 1; }
test ! -e "$stage" || { echo "BRAIN_DEPLOY=FAIL reason=staging_collision"; exit 1; }
test ! -e "$backup" || { echo "BRAIN_DEPLOY=FAIL reason=backup_collision"; exit 1; }

python3 scripts/check_brain_inputs.py
python3 scripts/render_dominion_brain.py "$stage"

python3 - "$stage" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
manifest_path = root / "MANIFEST.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
assert manifest["schema"] == "dominion-brain-manifest-v2"
assert manifest["agent_count"] > 0
assert len(manifest["source_revision"]["sha256"]) == 64
for item in manifest["files"]:
    path = root / item["path"]
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == item["sha256"]
    assert len(raw) == item["bytes"]
print(f"BRAIN_STAGE_VERIFY=PASS agents={manifest['agent_count']} files={len(manifest['files'])} source_digest={manifest['source_revision']['sha256']}")
PY

# Create the preserved operator-note skeleton only when absent. Never overwrite it.
python3 - "$repo/agents/registry.json" "$operator_notes" <<'PY'
import json
import os
import re
import sys
from pathlib import Path

registry = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
root = Path(sys.argv[2])
root.mkdir(parents=True, exist_ok=True)
os.chmod(root, 0o700)
valid = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
files = (
    "08-Incidents-and-Lessons.md",
    "09-Current-State.md",
    "10-Change-Log.md",
)
for agent in registry["agents"]:
    aid = str(agent["id"])
    if not valid.fullmatch(aid):
        raise SystemExit("unsafe agent id")
    home = root / aid
    home.mkdir(mode=0o700, exist_ok=True)
    for name in files:
        path = home / name
        if path.exists():
            continue
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(f"# {aid} — {name[:-3]}\n\n")
            handle.write("Operator-owned sanitized runtime evidence. Do not store secrets or customer PII.\n")
            handle.flush()
            os.fsync(handle.fileno())
print(f"OPERATOR_NOTES=PASS agents={len(registry['agents'])}")
PY

old_present=0
if [ -e "$current" ]; then
  test -d "$current" && test ! -L "$current" || { echo "BRAIN_DEPLOY=FAIL reason=current_not_safe_directory"; rm -rf "$stage"; exit 1; }
  mv "$current" "$backup"
  old_present=1
fi

rollback() {
  rm -rf "$stage" || true
  if [ "$old_present" -eq 1 ] && [ -d "$backup" ] && [ ! -e "$current" ]; then
    mv "$backup" "$current" || true
  fi
}
trap rollback ERR
mv "$stage" "$current"

python3 - "$vault" <<'PY'
import os, sys
fd = os.open(sys.argv[1], os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
try:
    os.fsync(fd)
finally:
    os.close(fd)
PY

# Verify the published generation before touching the Obsidian container.
python3 - "$current" <<'PY'
import hashlib, json, sys
from pathlib import Path
root = Path(sys.argv[1])
manifest = json.loads((root / "MANIFEST.json").read_text(encoding="utf-8"))
for item in manifest["files"]:
    raw = (root / item["path"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == item["sha256"]
print(f"BRAIN_PUBLISH=PASS agents={manifest['agent_count']} files={len(manifest['files'])}")
PY

# Ensure Obsidian Remote is running from the exact checked-out repo. The password is process-only.
OBSIDIAN_PASSWORD="$OBSIDIAN_PASSWORD" docker compose up -d --no-deps obsidian-remote >/dev/null
ready=0
for _ in $(seq 1 40); do
  state="$(docker inspect --format '{{.State.Status}}' obsidian-remote 2>/dev/null || true)"
  if [ "$state" = "running" ] && curl -fsS --max-time 10 -u "dominion:$OBSIDIAN_PASSWORD" http://127.0.0.1:8083/ >/dev/null; then
    ready=1
    break
  fi
  sleep 3
done
test "$ready" -eq 1 || { echo "BRAIN_DEPLOY=FAIL reason=obsidian_local_unhealthy"; exit 1; }
unauth="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 http://127.0.0.1:8083/ || true)"
test "$unauth" = "401" || { echo "BRAIN_DEPLOY=FAIL reason=obsidian_auth_not_enforced status=$unauth"; exit 1; }

# Reuse the existing public route contract. Add it only if absent, with validation/rollback.
caddy=/etc/caddy/Caddyfile
if ! sudo grep -qF 'vault.dominionhealing.org {' "$caddy"; then
  caddy_backup="/etc/caddy/Caddyfile.brain-${RUN_ID}.bak"
  sudo cp -a "$caddy" "$caddy_backup"
  sudo tee -a "$caddy" >/dev/null <<'CADDY'

vault.dominionhealing.org {
    reverse_proxy 127.0.0.1:8083
}
CADDY
  if ! sudo caddy validate --config "$caddy" --adapter caddyfile >/dev/null; then
    sudo cp -a "$caddy_backup" "$caddy"
    echo "BRAIN_DEPLOY=FAIL reason=caddy_validation"
    exit 1
  fi
  sudo systemctl reload caddy
  sudo rm -f "$caddy_backup"
fi

getent ahostsv4 vault.dominionhealing.org >/dev/null 2>&1 || { echo "BRAIN_DEPLOY=FAIL reason=vault_dns_missing"; exit 1; }
public=0
for _ in $(seq 1 20); do
  if curl -fsS --max-time 15 -u "dominion:$OBSIDIAN_PASSWORD" https://vault.dominionhealing.org/ >/dev/null; then
    public=1
    break
  fi
  sleep 3
done
test "$public" -eq 1 || { echo "BRAIN_DEPLOY=FAIL reason=obsidian_public_unhealthy"; exit 1; }

# Successful publication: leave one exact rollback generation and report it; no note contents are emitted.
trap - ERR
if [ "$old_present" -eq 0 ]; then
  backup="none"
fi
printf 'BRAIN_DEPLOY=PASS sha=%s current=%s rollback=%s operator_notes=preserved obsidian=healthy public=healthy\n' "$DEPLOY_SHA" "$current" "$backup"

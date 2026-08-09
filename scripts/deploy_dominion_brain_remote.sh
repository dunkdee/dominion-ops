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
caddy=/etc/caddy/Caddyfile
caddy_backup="/etc/caddy/Caddyfile.brain-${RUN_ID}.bak"
old_present=0
published=0
route_added=0

[[ "$DEPLOY_SHA" =~ ^[0-9a-f]{40}$ ]] || { echo "BRAIN_DEPLOY=FAIL reason=invalid_sha"; exit 1; }
test -d "$repo/.git" || { echo "BRAIN_DEPLOY=FAIL reason=repo_missing"; exit 1; }
cd "$repo"
actual_sha="$(git rev-parse HEAD)"
test "$actual_sha" = "$DEPLOY_SHA" || { echo "BRAIN_DEPLOY=FAIL reason=vm_sha_mismatch expected=$DEPLOY_SHA actual=$actual_sha"; exit 1; }
test -d "$vault" || { echo "BRAIN_DEPLOY=FAIL reason=vault_missing"; exit 1; }
test ! -e "$stage" || { echo "BRAIN_DEPLOY=FAIL reason=staging_collision"; exit 1; }
test ! -e "$backup" || { echo "BRAIN_DEPLOY=FAIL reason=backup_collision"; exit 1; }

rollback() {
  set +e
  if [ "$route_added" -eq 1 ] && sudo test -f "$caddy_backup"; then
    sudo cp -a "$caddy_backup" "$caddy"
    sudo caddy validate --config "$caddy" --adapter caddyfile >/dev/null 2>&1 && sudo systemctl reload caddy >/dev/null 2>&1
  fi
  if [ "$published" -eq 1 ]; then
    rm -rf "$current"
    if [ "$old_present" -eq 1 ] && [ -d "$backup" ]; then mv "$backup" "$current"; fi
  fi
  rm -rf "$stage"
  echo "BRAIN_AUTO_ROLLBACK=PASS old_generation_restored=$old_present"
}
trap rollback ERR

python3 scripts/check_brain_inputs.py
python3 scripts/render_dominion_brain.py "$stage"
python3 - "$stage" <<'PY'
import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]); m=json.loads((root/'MANIFEST.json').read_text())
assert m['schema']=='dominion-brain-manifest-v2' and m['agent_count']>0
assert len(m['source_revision']['sha256'])==64
for item in m['files']:
    raw=(root/item['path']).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==item['sha256'] and len(raw)==item['bytes']
print(f"BRAIN_STAGE_VERIFY=PASS agents={m['agent_count']} files={len(m['files'])} source_digest={m['source_revision']['sha256']}")
PY

if [ -e "$current" ]; then
  test -d "$current" && test ! -L "$current" || { echo "BRAIN_DEPLOY=FAIL reason=current_not_safe_directory"; exit 1; }
  mv "$current" "$backup"
  old_present=1
fi
mv "$stage" "$current"
published=1
python3 - "$vault" <<'PY'
import os,sys
fd=os.open(sys.argv[1], os.O_RDONLY|getattr(os,'O_DIRECTORY',0))
try: os.fsync(fd)
finally: os.close(fd)
PY
python3 - "$current" <<'PY'
import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]); m=json.loads((root/'MANIFEST.json').read_text())
for item in m['files']:
    assert hashlib.sha256((root/item['path']).read_bytes()).hexdigest()==item['sha256']
print(f"BRAIN_PUBLISH=PASS agents={m['agent_count']} files={len(m['files'])}")
PY

OBSIDIAN_PASSWORD="$OBSIDIAN_PASSWORD" docker compose up -d --no-deps obsidian-remote >/dev/null
ready=0
for _ in $(seq 1 40); do
  state="$(docker inspect --format '{{.State.Status}}' obsidian-remote 2>/dev/null || true)"
  if [ "$state" = "running" ] && curl -fsS --max-time 10 -u "dominion:$OBSIDIAN_PASSWORD" http://127.0.0.1:8083/ >/dev/null; then ready=1; break; fi
  sleep 3
done
test "$ready" -eq 1 || { echo "BRAIN_DEPLOY=FAIL reason=obsidian_local_unhealthy"; false; }
unauth="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 http://127.0.0.1:8083/ || true)"
test "$unauth" = "401" || { echo "BRAIN_DEPLOY=FAIL reason=obsidian_auth_not_enforced status=$unauth"; false; }

if ! sudo grep -qF 'vault.dominionhealing.org {' "$caddy"; then
  sudo cp -a "$caddy" "$caddy_backup"
  route_added=1
  sudo tee -a "$caddy" >/dev/null <<'CADDY'

vault.dominionhealing.org {
    reverse_proxy 127.0.0.1:8083
}
CADDY
  sudo caddy validate --config "$caddy" --adapter caddyfile >/dev/null || { echo "BRAIN_DEPLOY=FAIL reason=caddy_validation"; false; }
  sudo systemctl reload caddy
fi

getent ahostsv4 vault.dominionhealing.org >/dev/null 2>&1 || { echo "BRAIN_DEPLOY=FAIL reason=vault_dns_missing"; false; }
public=0
for _ in $(seq 1 20); do
  if curl -fsS --max-time 15 -u "dominion:$OBSIDIAN_PASSWORD" https://vault.dominionhealing.org/ >/dev/null; then public=1; break; fi
  sleep 3
done
test "$public" -eq 1 || { echo "BRAIN_DEPLOY=FAIL reason=obsidian_public_unhealthy"; false; }

# Only after the generated mirror and access path are accepted, seed missing operator-owned note files. Never overwrite them.
python3 - "$repo/agents/registry.json" "$operator_notes" <<'PY'
import json,os,re,sys
from pathlib import Path
registry=json.loads(Path(sys.argv[1]).read_text()); root=Path(sys.argv[2]); root.mkdir(parents=True,exist_ok=True); os.chmod(root,0o700)
valid=re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')
files=('08-Incidents-and-Lessons.md','09-Current-State.md','10-Change-Log.md')
for agent in registry['agents']:
    aid=str(agent['id']); assert valid.fullmatch(aid)
    home=root/aid; home.mkdir(mode=0o700,exist_ok=True)
    for name in files:
        path=home/name
        if path.exists(): continue
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w',encoding='utf-8') as h:
            h.write(f'# {aid} — {name[:-3]}\n\nOperator-owned sanitized runtime evidence. Do not store secrets or customer PII.\n'); h.flush(); os.fsync(h.fileno())
print(f"OPERATOR_NOTES=PASS agents={len(registry['agents'])}")
PY

if [ "$route_added" -eq 1 ]; then sudo rm -f "$caddy_backup"; fi
trap - ERR
if [ "$old_present" -eq 0 ]; then backup="none"; fi
printf 'BRAIN_DEPLOY=PASS sha=%s current=%s rollback=%s operator_notes=preserved obsidian=healthy public=healthy\n' "$DEPLOY_SHA" "$current" "$backup"

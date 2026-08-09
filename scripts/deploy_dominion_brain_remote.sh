#!/usr/bin/env bash
set -Eeuo pipefail

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
caddy_changed=0

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
  if [ "$caddy_changed" -eq 1 ] && sudo test -f "$caddy_backup"; then
    sudo cp -a "$caddy_backup" "$caddy"
    sudo caddy validate --config "$caddy" --adapter caddyfile >/dev/null 2>&1 \
      && sudo systemctl reload caddy >/dev/null 2>&1
  fi
  if [ "$published" -eq 1 ]; then
    rm -rf "$current"
    if [ "$old_present" -eq 1 ] && [ -d "$backup" ]; then mv "$backup" "$current"; fi
  fi
  rm -rf "$stage"
  echo "BRAIN_AUTO_ROLLBACK=PASS old_generation_restored=$old_present caddy_restored=$caddy_changed"
}

on_error() {
  rc=$?
  trap - ERR
  rollback
  exit "$rc"
}
trap on_error ERR

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

# The Obsidian backend is loopback-only. It may render a login page with HTTP 200,
# so access control is enforced at Caddy rather than inferred from backend status.
OBSIDIAN_PASSWORD="$OBSIDIAN_PASSWORD" docker compose up -d --no-deps obsidian-remote >/dev/null
ready=0
for _ in $(seq 1 40); do
  state="$(docker inspect --format '{{.State.Status}}' obsidian-remote 2>/dev/null || true)"
  if [ "$state" = "running" ] && curl -fsS --max-time 10 http://127.0.0.1:8083/ >/dev/null; then ready=1; break; fi
  sleep 3
done
test "$ready" -eq 1 || { echo "BRAIN_DEPLOY=FAIL reason=obsidian_local_unhealthy"; false; }
ss -tln | grep -Eq '127\.0\.0\.1:8083[[:space:]]' || { echo "BRAIN_DEPLOY=FAIL reason=obsidian_not_loopback_bound"; false; }

# Always converge the public vault route to Caddy-enforced Basic Auth. The plaintext
# password is never written to Caddy; only the one-way hash is persisted.
sudo test -f "$caddy" || { echo "BRAIN_DEPLOY=FAIL reason=caddyfile_missing"; false; }
sudo test ! -L "$caddy" || { echo "BRAIN_DEPLOY=FAIL reason=caddyfile_symlink"; false; }
sudo cp -a "$caddy" "$caddy_backup"
caddy_changed=1
password_hash="$(sudo caddy hash-password --plaintext "$OBSIDIAN_PASSWORD")"
test -n "$password_hash" || { echo "BRAIN_DEPLOY=FAIL reason=caddy_password_hash_failed"; false; }
sudo env VAULT_PASSWORD_HASH="$password_hash" python3 - "$caddy" <<'PY'
import os,secrets,stat,sys
from pathlib import Path

path=Path(sys.argv[1]); password_hash=os.environ['VAULT_PASSWORD_HASH']
text=path.read_text(encoding='utf-8'); lines=text.splitlines(keepends=True)
starts=[i for i,line in enumerate(lines) if line.strip()=='vault.dominionhealing.org {']
if len(starts)>1:
    raise SystemExit('VAULT_CADDY_ROUTE_DUPLICATE')
block=(
    'vault.dominionhealing.org {\n'
    '    basic_auth {\n'
    f'        dominion {password_hash}\n'
    '    }\n'
    '    reverse_proxy 127.0.0.1:8083\n'
    '}\n'
)
if starts:
    start=starts[0]; depth=0; end=None
    for i in range(start,len(lines)):
        depth += lines[i].count('{') - lines[i].count('}')
        if depth==0:
            end=i+1; break
    if end is None:
        raise SystemExit('VAULT_CADDY_ROUTE_UNBALANCED')
    new=''.join(lines[:start])+block+''.join(lines[end:])
else:
    suffix='' if text.endswith('\n') or not text else '\n'
    new=text+suffix+'\n'+block
st=path.stat(); tmp=path.with_name(f'.{path.name}.vault-{os.getpid()}-{secrets.token_hex(8)}.tmp')
fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,stat.S_IMODE(st.st_mode))
try:
    with os.fdopen(fd,'w',encoding='utf-8',newline='\n') as h:
        h.write(new); h.flush(); os.fsync(h.fileno())
    os.chown(tmp,st.st_uid,st.st_gid); os.chmod(tmp,stat.S_IMODE(st.st_mode)); os.replace(tmp,path)
    dfd=os.open(path.parent,os.O_RDONLY|getattr(os,'O_DIRECTORY',0))
    try: os.fsync(dfd)
    finally: os.close(dfd)
finally:
    if tmp.exists(): tmp.unlink()
PY
unset password_hash
sudo caddy validate --config "$caddy" --adapter caddyfile >/dev/null || { echo "BRAIN_DEPLOY=FAIL reason=caddy_validation"; false; }
sudo systemctl reload caddy

getent ahostsv4 vault.dominionhealing.org >/dev/null 2>&1 || { echo "BRAIN_DEPLOY=FAIL reason=vault_dns_missing"; false; }
public=0
for _ in $(seq 1 20); do
  if curl -fsSL --max-time 15 -u "dominion:$OBSIDIAN_PASSWORD" https://vault.dominionhealing.org/ >/dev/null; then public=1; break; fi
  sleep 3
done
test "$public" -eq 1 || { echo "BRAIN_DEPLOY=FAIL reason=obsidian_public_authenticated_unhealthy"; false; }
unauth="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 https://vault.dominionhealing.org/ || true)"
test "$unauth" = "401" || { echo "BRAIN_DEPLOY=FAIL reason=public_auth_not_enforced status=$unauth"; false; }

# Only after the generated mirror and protected access path are accepted, seed
# missing operator-owned note files. Existing operator notes are never overwritten.
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

sudo rm -f "$caddy_backup"
caddy_changed=0
trap - ERR
if [ "$old_present" -eq 0 ]; then backup="none"; fi
printf 'BRAIN_DEPLOY=PASS sha=%s current=%s rollback=%s operator_notes=preserved obsidian_backend=loopback public_auth=basic_auth public=healthy\n' "$DEPLOY_SHA" "$current" "$backup"

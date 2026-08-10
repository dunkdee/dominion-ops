#!/usr/bin/env bash
set -euo pipefail
umask 077

: "${RUN_ID:?RUN_ID required}"
: "${RELEASE_SHA:?RELEASE_SHA required}"

[[ "$RELEASE_SHA" =~ ^[0-9a-f]{40}$ ]] || { echo 'BABY_API_GUMROAD_REPAIR=HOLD reason=bad_release_sha'; exit 1; }

repo="$HOME/dominion-ops"
repo_env="$repo/.env"
token_file="/tmp/baby-api-gumroad-${RUN_ID}.env"
env_backup="$repo/.env.baby-api-gumroad-${RUN_ID}.bak"
env_changed=0

cleanup() {
  rm -f "$token_file" /tmp/baby-vault-${RUN_ID}.json /tmp/baby-gumroad-${RUN_ID}.json
}

restore_env() {
  python3 - "$repo_env" "$env_backup" <<'PY'
import os, stat, sys
from pathlib import Path

dst=Path(sys.argv[1]); bak=Path(sys.argv[2]); parent=dst.parent
if not bak.is_file() or bak.is_symlink():
    raise SystemExit('rollback_backup_missing')
st=bak.stat(); data=bak.read_bytes()
tmp=parent/(f'.{dst.name}.restore.{os.getpid()}.tmp')
fd=os.open(tmp, os.O_WRONLY|os.O_CREAT|os.O_EXCL, stat.S_IMODE(st.st_mode))
try:
    view=memoryview(data)
    while view:
        n=os.write(fd,view); view=view[n:]
    os.fsync(fd); os.fchmod(fd,stat.S_IMODE(st.st_mode)); os.fchown(fd,st.st_uid,st.st_gid)
finally:
    os.close(fd)
os.replace(tmp,dst)
dfd=os.open(parent,os.O_RDONLY|os.O_DIRECTORY)
try: os.fsync(dfd)
finally: os.close(dfd)
bak.unlink()
PY
}

rollback() {
  rc=$?
  trap - ERR
  set +e
  if [ "$env_changed" -eq 1 ]; then
    restore_env
    WIX_AGENT_IMAGE="$(docker inspect wix-agent --format '{{.Config.Image}}' 2>/dev/null || true)" \
      docker compose -p dominion-ops -f "$repo/docker-compose.yml" --env-file "$repo_env" \
      up -d --no-deps --no-build --force-recreate baby-api >/dev/null 2>&1
  fi
  cleanup
  echo "BABY_API_GUMROAD_REPAIR=ROLLBACK original_rc=$rc"
  exit "$rc"
}
trap rollback ERR
trap cleanup EXIT

[ -d "$repo/.git" ] || { echo 'BABY_API_GUMROAD_REPAIR=HOLD reason=repo_missing'; exit 1; }
[ "$(git -C "$repo" rev-parse HEAD)" = "$RELEASE_SHA" ] || { echo 'BABY_API_GUMROAD_REPAIR=HOLD reason=vm_sha_mismatch'; exit 1; }
[ -f "$repo/docker-compose.yml" ] || { echo 'BABY_API_GUMROAD_REPAIR=HOLD reason=compose_missing'; exit 1; }
[ -f "$repo_env" ] && [ ! -L "$repo_env" ] || { echo 'BABY_API_GUMROAD_REPAIR=HOLD reason=repo_env_invalid'; exit 1; }
[ -s "$token_file" ] && [ ! -L "$token_file" ] || { echo 'BABY_API_GUMROAD_REPAIR=HOLD reason=token_stage_missing'; exit 1; }

docker inspect baby-api >/dev/null
[ "$(docker inspect baby-api --format '{{index .Config.Labels "com.docker.compose.project"}}')" = 'dominion-ops' ] || { echo 'BABY_API_GUMROAD_REPAIR=HOLD reason=compose_project_mismatch'; exit 1; }
[ "$(docker inspect baby-api --format '{{index .Config.Labels "com.docker.compose.service"}}')" = 'baby-api' ] || { echo 'BABY_API_GUMROAD_REPAIR=HOLD reason=compose_service_mismatch'; exit 1; }
[ "$(docker inspect baby-api --format '{{len .NetworkSettings.Networks}}')" = '1' ] || { echo 'BABY_API_GUMROAD_REPAIR=HOLD reason=network_count_mismatch'; exit 1; }
[ "$(docker inspect baby-api --format '{{range $name, $cfg := .NetworkSettings.Networks}}{{$name}}{{end}}')" = 'dominion-ops_default' ] || { echo 'BABY_API_GUMROAD_REPAIR=HOLD reason=network_mismatch'; exit 1; }

# Fail closed if a secret-bearing integration appeared since the read-only inventory.
# Recreating Baby API must never erase an integration that is live only in container memory.
python3 - <<'PY'
import json, subprocess
raw=subprocess.check_output(['docker','inspect','baby-api'],text=True)
d=json.loads(raw)[0]
env={}
for item in d.get('Config',{}).get('Env',[]):
    if '=' in item:
        k,v=item.split('=',1); env[k]=v.strip()
for key in (
    'ANTHROPIC_API_KEY','BINANCE_API_KEY','BINANCE_API_SECRET','BREVO_API_KEY',
    'GCP_PROJECT_ID','GEMINI_API_KEY','GOOGLE_SERVICE_ACCOUNT_JSON','OANDA_ACCOUNT_ID',
    'OANDA_API_KEY','TIKTOK_CLIENT_ID','TIKTOK_CLIENT_SECRET','YOUTUBE_API_KEY',
    'YOUTUBE_CLIENT_ID','YOUTUBE_CLIENT_SECRET'):
    if env.get(key):
        raise SystemExit('BABY_API_GUMROAD_REPAIR=HOLD reason=unexpected_live_secret key='+key)
if env.get('GUMROAD_TOKEN'):
    raise SystemExit('BABY_API_GUMROAD_REPAIR=HOLD reason=gumroad_already_present')
mounts={m.get('Destination'):m.get('Type') for m in d.get('Mounts',[])}
if mounts.get('/app')!='bind' or mounts.get('/vault')!='bind':
    raise SystemExit('BABY_API_GUMROAD_REPAIR=HOLD reason=mount_contract_changed')
print('BABY_API_PREMUTATION_CONTRACT=PASS')
PY

# Back up the exact env file and atomically change only GUMROAD_TOKEN.
python3 - "$repo_env" "$env_backup" "$token_file" <<'PY'
import os, shutil, stat, sys
from pathlib import Path

dst=Path(sys.argv[1]); bak=Path(sys.argv[2]); token_path=Path(sys.argv[3]); parent=dst.parent
if dst.is_symlink() or not dst.is_file(): raise SystemExit('repo_env_not_regular')
st=dst.stat(); mode=stat.S_IMODE(st.st_mode)
shutil.copy2(dst,bak)
with open(bak,'rb') as f: os.fsync(f.fileno())
dfd=os.open(parent,os.O_RDONLY|os.O_DIRECTORY)
try: os.fsync(dfd)
finally: os.close(dfd)

token=''
for raw in token_path.read_text(encoding='utf-8').splitlines():
    if raw.startswith('GUMROAD_TOKEN='):
        token=raw.split('=',1)[1].strip(); break
if not token: raise SystemExit('gumroad_token_empty')

existing=dst.read_text(encoding='utf-8',errors='strict').splitlines()
out=[]; replaced=False
for raw in existing:
    key=raw.split('=',1)[0].strip() if '=' in raw and not raw.lstrip().startswith('#') else None
    if key=='GUMROAD_TOKEN':
        if not replaced:
            out.append('GUMROAD_TOKEN='+token); replaced=True
        continue
    out.append(raw)
if not replaced: out.append('GUMROAD_TOKEN='+token)
payload=('\n'.join(out).rstrip('\n')+'\n').encode('utf-8')
tmp=parent/(f'.{dst.name}.gumroad.{os.getpid()}.tmp')
fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,mode)
try:
    view=memoryview(payload)
    while view:
        n=os.write(fd,view); view=view[n:]
    os.fsync(fd); os.fchmod(fd,mode); os.fchown(fd,st.st_uid,st.st_gid)
finally:
    os.close(fd)
os.replace(tmp,dst)
dfd=os.open(parent,os.O_RDONLY|os.O_DIRECTORY)
try: os.fsync(dfd)
finally: os.close(dfd)
PY
env_changed=1

# Recreate only Baby API from canonical Compose; no build and no dependency restart.
docker compose -p dominion-ops -f "$repo/docker-compose.yml" --env-file "$repo_env" \
  up -d --no-deps --no-build --force-recreate baby-api >/dev/null

ready=0
for _ in $(seq 1 30); do
  code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:8080/ || true)"
  if [ "$code" = '200' ]; then ready=1; break; fi
  sleep 2
done
[ "$ready" -eq 1 ] || { echo 'BABY_API_GUMROAD_REPAIR=HOLD reason=baby_api_not_ready'; false; }

vault_code="$(curl -sS -o "/tmp/baby-vault-${RUN_ID}.json" -w '%{http_code}' --max-time 10 http://127.0.0.1:8080/vault/health || true)"
[ "$vault_code" = '200' ] || { echo "BABY_API_GUMROAD_REPAIR=HOLD reason=vault_health status=$vault_code"; false; }

gumroad_code="$(curl -sS -o "/tmp/baby-gumroad-${RUN_ID}.json" -w '%{http_code}' --max-time 20 http://127.0.0.1:8080/gumroad || true)"
[ "$gumroad_code" = '200' ] || { echo "BABY_API_GUMROAD_REPAIR=HOLD reason=gumroad_health status=$gumroad_code"; false; }

read -r vault_notes product_count published_count <<EOF
$(python3 - "/tmp/baby-vault-${RUN_ID}.json" "/tmp/baby-gumroad-${RUN_ID}.json" <<'PY'
import json,sys
v=json.load(open(sys.argv[1],encoding='utf-8'))
g=json.load(open(sys.argv[2],encoding='utf-8'))
assert v.get('vault')=='mounted'
notes=int(v.get('total_notes',-1)); assert notes>=0
assert g.get('success') is True
products=g.get('products',[]); count=int(g.get('product_count',-1))
assert count==len(products) and count>=1
published=sum(1 for p in products if p.get('published') is True)
assert published>=1
print(notes,count,published)
PY
)
EOF

# Make the successful env state durable, then remove the rollback copy.
rm -f "$env_backup"
env_changed=0

echo "BABY_API_GUMROAD_REPAIR=PASS products=$product_count published=$published_count vault=mounted vault_notes=$vault_notes"

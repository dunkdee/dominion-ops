#!/usr/bin/env bash
set -euo pipefail
umask 077

: "${RELEASE_SHA:?RELEASE_SHA required}"
: "${WIX_SITE_ID:?WIX_SITE_ID required}"
: "${RUN_ID:?RUN_ID required}"

[[ "$RELEASE_SHA" =~ ^[0-9a-f]{40}$ ]] || { echo 'WIX_RUNTIME_REPAIR=HOLD reason=bad_release_sha'; exit 1; }
[ "$WIX_SITE_ID" = 'a790d430-a3a0-4b0e-9be6-4c874c229167' ] || { echo 'WIX_RUNTIME_REPAIR=HOLD reason=site_id_mismatch'; exit 1; }

release_tgz="/tmp/wix-agent-${RUN_ID}.tgz"
key_file="/tmp/wix-api-key-${RUN_ID}.env"
repo="$HOME/dominion-ops"
repo_env="$repo/.env"
work="$HOME/releases/wix-agent/${RELEASE_SHA}"
image="dominion/wix-agent:${RELEASE_SHA}"
rollback_image="dominion/wix-agent:rollback-${RUN_ID}"
candidate="wix-agent-preflight-${RUN_ID}"
candidate_data="${candidate}-data"
candidate_logs="${candidate}-logs"
legacy_backup="wix-agent-rollback-${RUN_ID}"
candidate_env="/tmp/wix-runtime-${RUN_ID}.env"
env_backup="$repo/.env.wix-repair-${RUN_ID}.bak"
env_changed=0
cutover_started=0
legacy_mode=0

cleanup_temp() {
  rm -f "$release_tgz" "$key_file" "$candidate_env" /tmp/wix-ready-${RUN_ID}.json /tmp/wix-prod-ready-${RUN_ID}.json
  docker rm -f "$candidate" >/dev/null 2>&1 || true
  docker volume rm "$candidate_data" "$candidate_logs" >/dev/null 2>&1 || true
}

restore_repo_env() {
  [ "$env_changed" -eq 1 ] || return 0
  python3 - "$repo_env" "$env_backup" <<'PY'
import os, shutil, stat, sys
from pathlib import Path

dst=Path(sys.argv[1]); bak=Path(sys.argv[2]); parent=dst.parent
if bak.exists():
    st=bak.stat(); mode=stat.S_IMODE(st.st_mode)
    tmp=parent/(f'.{dst.name}.restore.{os.getpid()}.tmp')
    fd=os.open(tmp, os.O_WRONLY|os.O_CREAT|os.O_EXCL, mode)
    try:
        with open(bak,'rb') as src:
            while True:
                chunk=src.read(1024*1024)
                if not chunk: break
                os.write(fd,chunk)
        os.fsync(fd); os.fchmod(fd,mode); os.fchown(fd,st.st_uid,st.st_gid)
    finally:
        os.close(fd)
    os.replace(tmp,dst)
    bak.unlink()
else:
    if dst.exists(): dst.unlink()
dfd=os.open(parent,os.O_RDONLY|os.O_DIRECTORY)
try: os.fsync(dfd)
finally: os.close(dfd)
PY
}

rollback() {
  rc=$?
  trap - ERR
  if [ "$cutover_started" -eq 1 ]; then
    restore_repo_env || true
    if [ "$legacy_mode" -eq 1 ]; then
      docker rm -f wix-agent >/dev/null 2>&1 || true
      if docker inspect "$legacy_backup" >/dev/null 2>&1; then
        docker rename "$legacy_backup" wix-agent >/dev/null 2>&1 || true
        docker start wix-agent >/dev/null 2>&1 || true
      fi
    else
      WIX_AGENT_IMAGE="$rollback_image" \
      WIX_AGENT_DATA_VOLUME="$data_source" \
      WIX_AGENT_LOGS_VOLUME="$logs_source" \
      docker compose -p "$compose_project" -f "$repo/docker-compose.yml" --env-file "$repo_env" \
        up -d --no-deps --no-build --force-recreate wix-agent >/dev/null 2>&1 || true
    fi
  else
    restore_repo_env || true
  fi
  docker image rm "$rollback_image" >/dev/null 2>&1 || true
  cleanup_temp
  echo "WIX_RUNTIME_REPAIR=ROLLBACK original_rc=$rc"
  exit "$rc"
}
trap rollback ERR
trap cleanup_temp EXIT

[ -d "$repo/.git" ] || { echo 'WIX_RUNTIME_REPAIR=HOLD reason=repo_missing'; exit 1; }
test -s "$release_tgz" && test -s "$key_file"
test -f "$repo/docker-compose.yml"
docker inspect wix-agent >/dev/null
if ss -ltnH | awk '{print $4}' | grep -Eq '(^|:)18082$'; then
  echo 'WIX_RUNTIME_REPAIR=HOLD reason=preflight_port_in_use'
  exit 1
fi

rm -rf "$work.tmp"
install -d -m 700 "$work.tmp"
# The release archive contains only version-controlled, non-secret Wix source.
# Keep the process umask restrictive for credentials, but extract source with
# normal code permissions so the non-root container user can read /app.
(umask 022; tar -xzf "$release_tgz" -C "$work.tmp")
rm -rf "$work"
mv "$work.tmp" "$work"
release_dir="$work/apps/wix-agent"
test -f "$release_dir/Dockerfile" && test -f "$release_dir/main.py"
find "$release_dir" -type d -exec chmod a+rx {} +
find "$release_dir" -type f -exec chmod a+r {} +
test -r "$release_dir/main.py"

api_key="$(sed -n 's/^WIX_API_KEY=//p' "$key_file" | tail -n1)"
test -n "$api_key"
operator_token=""
if [ -s "$repo_env" ]; then
  operator_token="$(sed -n 's/^WIX_AGENT_OPERATOR_TOKEN=//p' "$repo_env" | tail -n1 || true)"
fi
if [ -z "$operator_token" ]; then operator_token="$(openssl rand -hex 32)"; fi
{
  printf 'WIX_API_KEY=%s\n' "$api_key"
  printf 'WIX_SITE_ID=%s\n' "$WIX_SITE_ID"
  printf 'WIX_AGENT_OPERATOR_TOKEN=%s\n' "$operator_token"
  printf 'WIX_FULFILLMENT_MODE=record_only\n'
} > "$candidate_env"
chmod 600 "$candidate_env"

network_count="$(docker inspect wix-agent --format '{{len .NetworkSettings.Networks}}')"
[ "$network_count" = '1' ] || { echo "WIX_RUNTIME_REPAIR=HOLD reason=unexpected_network_count count=$network_count"; exit 1; }
network="$(docker inspect wix-agent --format '{{range $name, $config := .NetworkSettings.Networks}}{{$name}}{{end}}')"
data_mount="$(docker inspect wix-agent --format '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Type}}|{{if eq .Type "volume"}}{{.Name}}{{else}}{{.Source}}{{end}}{{end}}{{end}}')"
logs_mount="$(docker inspect wix-agent --format '{{range .Mounts}}{{if eq .Destination "/app/logs"}}{{.Type}}|{{if eq .Type "volume"}}{{.Name}}{{else}}{{.Source}}{{end}}{{end}}{{end}}')"
compose_project="$(docker inspect wix-agent --format '{{index .Config.Labels "com.docker.compose.project"}}' 2>/dev/null || true)"
compose_service="$(docker inspect wix-agent --format '{{index .Config.Labels "com.docker.compose.service"}}' 2>/dev/null || true)"
test -n "$network" && test -n "$data_mount" && test -n "$logs_mount"
IFS='|' read -r data_type data_source <<<"$data_mount"
IFS='|' read -r logs_type logs_source <<<"$logs_mount"
[ "$data_type" = 'volume' ] || { echo 'WIX_RUNTIME_REPAIR=HOLD reason=data_mount_not_volume'; exit 1; }
[ "$logs_type" = 'volume' ] || { echo 'WIX_RUNTIME_REPAIR=HOLD reason=logs_mount_not_volume'; exit 1; }
test -n "$data_source" && test -n "$logs_source"
if [ "$compose_service" = 'wix-agent' ] && [ -n "$compose_project" ]; then
  legacy_mode=0
else
  case "$network" in
    *_default) compose_project="${network%_default}"; legacy_mode=1 ;;
    *) echo "WIX_RUNTIME_REPAIR=HOLD reason=legacy_network_not_compose_default network=$network"; exit 1 ;;
  esac
fi

docker build --tag "$image" "$release_dir" >/dev/null
docker rm -f "$candidate" >/dev/null 2>&1 || true
docker volume rm "$candidate_data" "$candidate_logs" >/dev/null 2>&1 || true
docker volume create "$candidate_data" >/dev/null
docker volume create "$candidate_logs" >/dev/null
docker run -d --name "$candidate" \
  --network "$network" --publish 127.0.0.1:18082:8000 \
  --read-only --tmpfs /tmp:size=64m,noexec,nosuid,nodev \
  --cap-drop ALL --security-opt no-new-privileges \
  --pids-limit 256 --memory 512m --cpus 1.0 \
  --env-file "$candidate_env" --env WIX_AGENT_DB=/data/wix_agent.db \
  --env BABY_API_URL=http://baby-api:8080 \
  --volume "$candidate_data:/data" --volume "$candidate_logs:/app/logs" \
  "$image" >/dev/null
ok=0
for _ in $(seq 1 30); do
  if curl -fsS --max-time 5 http://127.0.0.1:18082/ready > "/tmp/wix-ready-${RUN_ID}.json"; then ok=1; break; fi
  sleep 2
done
[ "$ok" -eq 1 ] || { docker logs --tail 80 "$candidate"; echo 'WIX_RUNTIME_REPAIR=HOLD reason=isolated_not_ready'; exit 1; }
python3 - "/tmp/wix-ready-${RUN_ID}.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1]))
assert d['ready'] is True
assert d['catalog']['status']=='ok'
assert str(d['catalog']['version']).lower()=='v3'
assert d['fulfillment']['mode']=='record_only'
assert d['integrations']['wix_api_key'] is True
assert d['integrations']['wix_site_id'] is True
assert d['integrations']['operator_token'] is True
PY
test "$(curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:18082/fulfillments/status)" = '401'
curl -fsS -H "X-Operator-Token: $operator_token" http://127.0.0.1:18082/fulfillments/status >/dev/null
test "$(curl -sS -o /dev/null -w '%{http_code}' -X POST -H "X-Operator-Token: $operator_token" http://127.0.0.1:18082/fulfill)" = '409'
echo 'WIX_ISOLATED_PREFLIGHT=PASS catalog=v3 fulfillment=record_only auth=PASS'
docker rm -f "$candidate" >/dev/null
docker volume rm "$candidate_data" "$candidate_logs" >/dev/null

python3 - "$repo_env" "$env_backup" "$candidate_env" <<'PY'
import os, shutil, stat, sys
from pathlib import Path

dst=Path(sys.argv[1]); bak=Path(sys.argv[2]); src=Path(sys.argv[3]); parent=dst.parent
updates={}
for raw in src.read_text().splitlines():
    if '=' in raw:
        k,v=raw.split('=',1); updates[k]=v
existing=[]
if dst.exists():
    if dst.is_symlink(): raise SystemExit('repo_env_symlink')
    st=dst.stat()
    if not stat.S_ISREG(st.st_mode): raise SystemExit('repo_env_not_regular')
    existing=dst.read_text(errors='replace').splitlines()
    shutil.copy2(dst,bak)
    mode=stat.S_IMODE(st.st_mode); uid=st.st_uid; gid=st.st_gid
else:
    mode=0o600; uid=os.getuid(); gid=os.getgid()
seen=set(); out=[]
for raw in existing:
    key=raw.split('=',1)[0].strip() if '=' in raw and not raw.lstrip().startswith('#') else None
    if key in updates:
        if key not in seen: out.append(f'{key}={updates[key]}'); seen.add(key)
    else:
        out.append(raw)
for key in ('WIX_API_KEY','WIX_SITE_ID','WIX_AGENT_OPERATOR_TOKEN','WIX_FULFILLMENT_MODE'):
    if key not in seen: out.append(f'{key}={updates[key]}')
tmp=parent/(f'.{dst.name}.wix.{os.getpid()}.tmp')
fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,mode)
try:
    payload=('\n'.join(out).rstrip('\n')+'\n').encode()
    os.write(fd,payload); os.fsync(fd); os.fchmod(fd,mode); os.fchown(fd,uid,gid)
finally:
    os.close(fd)
os.replace(tmp,dst)
dfd=os.open(parent,os.O_RDONLY|os.O_DIRECTORY)
try: os.fsync(dfd)
finally: os.close(dfd)
PY
env_changed=1

current_image_id="$(docker inspect wix-agent --format '{{.Image}}')"
test -n "$current_image_id"
docker tag "$current_image_id" "$rollback_image"
cutover_started=1
if [ "$legacy_mode" -eq 1 ]; then
  docker rm -f "$legacy_backup" >/dev/null 2>&1 || true
  docker rename wix-agent "$legacy_backup"
  docker stop "$legacy_backup" >/dev/null
fi
WIX_AGENT_IMAGE="$image" \
WIX_AGENT_DATA_VOLUME="$data_source" \
WIX_AGENT_LOGS_VOLUME="$logs_source" \
docker compose -p "$compose_project" -f "$repo/docker-compose.yml" --env-file "$repo_env" \
  up -d --no-deps --no-build --force-recreate wix-agent >/dev/null

ok=0
for _ in $(seq 1 30); do
  if curl -fsS --max-time 5 http://127.0.0.1:8082/ready > "/tmp/wix-prod-ready-${RUN_ID}.json"; then ok=1; break; fi
  sleep 2
done
[ "$ok" -eq 1 ] || { docker logs --tail 80 wix-agent; echo 'WIX_RUNTIME_REPAIR=HOLD reason=production_not_ready'; false; }
python3 - "/tmp/wix-prod-ready-${RUN_ID}.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1]))
assert d['ready'] is True
assert d['catalog']['status']=='ok'
assert str(d['catalog']['version']).lower()=='v3'
assert d['fulfillment']['mode']=='record_only'
assert d['integrations']['wix_api_key'] is True
assert d['integrations']['wix_site_id'] is True
assert d['integrations']['operator_token'] is True
PY
test "$(curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:8082/fulfillments/status)" = '401'
curl -fsS -H "X-Operator-Token: $operator_token" http://127.0.0.1:8082/fulfillments/status >/dev/null
test "$(curl -sS -o /dev/null -w '%{http_code}' -X POST -H "X-Operator-Token: $operator_token" http://127.0.0.1:8082/fulfill)" = '409'
sleep 5
curl -fsS --max-time 5 http://127.0.0.1:8082/ready >/dev/null

if [ "$legacy_mode" -eq 1 ]; then docker rm "$legacy_backup" >/dev/null; fi
docker image rm "$rollback_image" >/dev/null 2>&1 || true
rm -f "$env_backup"
env_changed=0
cutover_started=0
echo "WIX_RUNTIME_REPAIR=PASS sha=$RELEASE_SHA site=voltedge catalog=v3 fulfillment=record_only"

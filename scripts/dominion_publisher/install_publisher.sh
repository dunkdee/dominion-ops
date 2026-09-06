#!/usr/bin/env bash
set -Eeuo pipefail

: "${RUN_SHA:?RUN_SHA is required}"
repo="${REPO_DIR:-$HOME/dominion-ops}"
state_root="$HOME/.dominion/publisher"
runtime_root="$state_root/runtime"
release_root="$runtime_root/release"
venv="$state_root/venv"
env_file="$state_root/runtime.env"
receipts="$state_root/receipts"
service_name="dominion-publisher.service"
unit="/etc/systemd/system/$service_name"
port="${DOMINION_PUBLISHER_PORT:-5112}"
user_name="$(id -un)"
group_name="$(id -gn)"

cd "$repo"
test "$(git rev-parse HEAD)" = "$RUN_SHA"
test -s apps/dominion_publisher/service.py
test -s apps/dominion_publisher/requirements.txt
python3 -m py_compile \
  apps/dominion_publisher/models.py \
  apps/dominion_publisher/core.py \
  apps/dominion_publisher/service.py \
  apps/dominion_publisher/adapters/meta.py

mkdir -p "$runtime_root" "$receipts"
chmod 700 "$state_root" "$runtime_root" "$receipts"
rm -rf "$release_root"
mkdir -p "$release_root/apps"
cp -a apps/dominion_publisher "$release_root/apps/"

if [ ! -x "$venv/bin/python" ]; then
  python3 -m venv "$venv"
fi
"$venv/bin/python" -m pip install --disable-pip-version-check --quiet --upgrade pip
"$venv/bin/python" -m pip install --disable-pip-version-check --quiet -r "$release_root/apps/dominion_publisher/requirements.txt"

if [ ! -s "$env_file" ]; then
  umask 077
  token="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
)"
  cat > "$env_file" <<EOF
DOMINION_PUBLISHER_OPERATOR_TOKEN=$token
DOMINION_PUBLISHER_DB=$state_root/dominion_publisher.db
EOF
  chmod 600 "$env_file"
fi

grep -q '^DOMINION_PUBLISHER_OPERATOR_TOKEN=.' "$env_file"
grep -q '^DOMINION_PUBLISHER_DB=.' "$env_file"

unit_tmp="$(mktemp)"
cat > "$unit_tmp" <<EOF
[Unit]
Description=Dominion Publisher governed social traffic control plane
After=network-online.target
Wants=network-online.target
ConditionPathExists=$release_root/apps/dominion_publisher/service.py
ConditionPathExists=$env_file

[Service]
Type=simple
User=$user_name
Group=$group_name
WorkingDirectory=$release_root
EnvironmentFile=$env_file
ExecStart=$venv/bin/python -m uvicorn apps.dominion_publisher.service:app --host 127.0.0.1 --port $port
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=read-only
ReadWritePaths=$state_root
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
UMask=0077

[Install]
WantedBy=multi-user.target
EOF
sudo install -m 644 "$unit_tmp" "$unit"
rm -f "$unit_tmp"

sudo systemctl daemon-reload
sudo systemctl reset-failed "$service_name" >/dev/null 2>&1 || true
sudo systemctl enable --now "$service_name" >/dev/null

health_tmp="$(mktemp)"
ready=0
for _ in $(seq 1 40); do
  if curl -fsS --max-time 4 "http://127.0.0.1:$port/health" >"$health_tmp" 2>/dev/null; then
    ready=1
    break
  fi
  sleep 1
done
if [ "$ready" -ne 1 ]; then
  sudo systemctl status "$service_name" --no-pager || true
  sudo journalctl -u "$service_name" -n 120 --no-pager || true
  echo 'DOMINION_PUBLISHER=FAIL reason=health_unavailable'
  exit 1
fi

python3 - "$health_tmp" "$port" <<'PY'
import json,sys
h=json.load(open(sys.argv[1],encoding='utf-8'))
assert h['status']=='ok'
assert h['service']=='dominion-publisher'
assert h['operator_gate_configured'] is True
assert set(h['platforms'])=={'instagram','facebook'}
print(f"DOMINION_PUBLISHER_HEALTH=PASS endpoint=127.0.0.1:{sys.argv[2]} operator_gate=configured meta_token={h['meta_token_configured']}")
PY
rm -f "$health_tmp"

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
receipt="$receipts/${stamp}-publisher-install-${RUN_SHA:0:12}.json"
RUN_SHA_VALUE="$RUN_SHA" PORT_VALUE="$port" python3 - "$receipt" <<'PY'
import json,os,sys
from datetime import datetime,timezone
from pathlib import Path
p=Path(sys.argv[1])
data={
  'schema':'dominion-publisher-install-receipt-v1',
  'status':'PASS',
  'release_sha':os.environ['RUN_SHA_VALUE'],
  'binding':f"127.0.0.1:{os.environ['PORT_VALUE']}",
  'operator_gate':'configured',
  'provider_credentials':'runtime_only',
  'observed_at':datetime.now(timezone.utc).isoformat(),
}
p.write_text(json.dumps(data,indent=2,sort_keys=True)+'\n',encoding='utf-8')
os.chmod(p,0o600)
PY

sudo systemctl is-active --quiet "$service_name"
sudo systemctl is-enabled --quiet "$service_name"
printf 'DOMINION_PUBLISHER=PASS release_sha=%s endpoint=http://127.0.0.1:%s service=%s state=%s\n' "$RUN_SHA" "$port" "$service_name" "$state_root"

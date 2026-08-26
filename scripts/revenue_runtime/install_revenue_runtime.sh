#!/usr/bin/env bash
set -Eeuo pipefail

: "${ASSET_ROOT:?ASSET_ROOT is required}"
: "${RUN_ID:?RUN_ID is required}"

asset_root="$(cd "$ASSET_ROOT" && pwd -P)"
user_name="$(id -un)"
user_group="$(id -gn)"
user_home="$HOME"
state_root="$user_home/.dominion/revenue-runtime"
runtime_root="$state_root/runtime"
new_runtime="$state_root/runtime.new.$RUN_ID"
backup_root="$state_root/backups/deploy-$RUN_ID"
signing_key="$state_root/signing.key"
service_name="dominion-revenue-runtime.service"
eval_service="dominion-revenue-evaluator.service"
eval_timer="dominion-revenue-evaluator.timer"
service_path="/etc/systemd/system/$service_name"
eval_service_path="/etc/systemd/system/$eval_service"
eval_timer_path="/etc/systemd/system/$eval_timer"
caddy_path="/etc/caddy/Caddyfile"
success=0

buddy_exec="$(systemctl show dominion-buddy-web.service -p ExecStart --value 2>/dev/null || true)"
buddy_python="$(printf '%s\n' "$buddy_exec" | sed -n 's/.*path=\([^ ;]*\).*/\1/p' | head -1)"
test -n "$buddy_python" || { echo 'REVENUE_RUNTIME=HOLD reason=buddy_python_unresolved'; exit 20; }
test -x "$buddy_python" || { echo 'REVENUE_RUNTIME=HOLD reason=buddy_python_not_executable'; exit 21; }

"$buddy_python" - <<'PY'
import importlib.util
mods=['fastapi','uvicorn','httpx','sqlite3']
missing=[m for m in mods if importlib.util.find_spec(m) is None]
assert not missing, missing
print('REVENUE_RUNTIME_IMPORTS=PASS modules=' + ','.join(mods))
PY

for key in WIX_API_KEY WIX_SITE_ID WIX_AGENT_OPERATOR_TOKEN; do
  grep -q "^${key}=." "$user_home/dominion-ops/.env" || { echo "REVENUE_RUNTIME=HOLD reason=config_missing_$key"; exit 22; }
done

if ss -ltn | awk '{print $4}' | grep -Eq '(^|:)8790$'; then
  if ! systemctl is-active --quiet "$service_name"; then
    echo 'REVENUE_RUNTIME=HOLD reason=port_8790_in_use'; exit 23
  fi
fi

mkdir -p "$state_root/backups"
chmod 700 "$state_root" "$state_root/backups"
rm -rf "$new_runtime"
mkdir -p "$new_runtime/apps/revenue_runtime" "$new_runtime/governance"
chmod 700 "$new_runtime"
install -m 600 "$asset_root/apps/revenue_runtime/"*.py "$new_runtime/apps/revenue_runtime/"
install -m 600 "$asset_root/governance/revenue_execution_policy.json" "$new_runtime/governance/revenue_execution_policy.json"
"$buddy_python" -m compileall -q "$new_runtime/apps/revenue_runtime"

if [ ! -s "$signing_key" ]; then
  umask 077
  "$buddy_python" - <<'PY' > "$signing_key.tmp"
import secrets
print(secrets.token_hex(48))
PY
  mv "$signing_key.tmp" "$signing_key"
  chmod 600 "$signing_key"
fi

mkdir -p "$backup_root"
chmod 700 "$backup_root"
[ -d "$runtime_root" ] && mv "$runtime_root" "$backup_root/runtime" || true
for spec in "$service_path:service.unit" "$eval_service_path:eval-service.unit" "$eval_timer_path:eval-timer.unit"; do
  path="${spec%%:*}"; name="${spec#*:}"
  if sudo test -f "$path"; then
    sudo cp -a "$path" "$backup_root/$name"
    sudo chown "$user_name:$user_group" "$backup_root/$name"
  fi
done
sudo cp -a "$caddy_path" "$backup_root/Caddyfile"
sudo chown "$user_name:$user_group" "$backup_root/Caddyfile"

rollback() {
  rc=$?
  [ "$success" -eq 1 ] && exit "$rc"
  trap - ERR INT TERM EXIT
  set +e
  echo "REVENUE_RUNTIME_ROLLBACK=BEGIN rc=$rc"
  sudo systemctl disable --now "$eval_timer" >/dev/null 2>&1 || true
  sudo systemctl stop "$service_name" "$eval_service" >/dev/null 2>&1 || true
  for spec in "$service_path:service.unit" "$eval_service_path:eval-service.unit" "$eval_timer_path:eval-timer.unit"; do
    path="${spec%%:*}"; name="${spec#*:}"
    if [ -f "$backup_root/$name" ]; then sudo install -m 644 "$backup_root/$name" "$path"; else sudo rm -f "$path"; fi
  done
  [ -f "$backup_root/Caddyfile" ] && sudo install -m 644 "$backup_root/Caddyfile" "$caddy_path"
  sudo systemctl daemon-reload >/dev/null 2>&1 || true
  sudo caddy validate --config "$caddy_path" >/dev/null 2>&1 && sudo systemctl reload caddy >/dev/null 2>&1 || true
  rm -rf "$runtime_root"
  [ -d "$backup_root/runtime" ] && mv "$backup_root/runtime" "$runtime_root"
  if sudo test -f "$service_path"; then sudo systemctl start "$service_name" >/dev/null 2>&1 || true; fi
  if sudo test -f "$eval_timer_path"; then sudo systemctl enable --now "$eval_timer" >/dev/null 2>&1 || true; fi
  rm -rf "$new_runtime"
  echo 'REVENUE_RUNTIME_ROLLBACK=COMPLETE'
  exit "$rc"
}
trap rollback ERR INT TERM EXIT

mv "$new_runtime" "$runtime_root"
mkdir -p "$state_root/receipts"
chmod 700 "$state_root/receipts"

service_tmp="$(mktemp)"; eval_service_tmp="$(mktemp)"; eval_timer_tmp="$(mktemp)"
cat > "$service_tmp" <<EOF
[Unit]
Description=Dominion Revenue Runtime — governed live CRO
After=network-online.target dominion-buddy-web.service
Wants=network-online.target
ConditionPathExists=$runtime_root/apps/revenue_runtime/service.py
ConditionPathExists=$buddy_python

[Service]
Type=simple
User=$user_name
WorkingDirectory=$runtime_root
Environment=DOMINION_REVENUE_RUNTIME_ENABLED=1
Environment=DOMINION_REVENUE_DB=$state_root/revenue.db
Environment=DOMINION_REVENUE_SIGNING_KEY_FILE=$signing_key
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=-$user_home/dominion-ops/.env
ExecStart=$buddy_python -m uvicorn apps.revenue_runtime.service:app --host 127.0.0.1 --port 8790 --workers 1
Restart=on-failure
RestartSec=5
TimeoutStartSec=60
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=read-only
ReadWritePaths=$state_root
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6

[Install]
WantedBy=multi-user.target
EOF

cat > "$eval_service_tmp" <<EOF
[Unit]
Description=Dominion Revenue Evaluator — attribution and winner gate
After=network-online.target $service_name
Wants=network-online.target

[Service]
Type=oneshot
User=$user_name
WorkingDirectory=$runtime_root
Environment=DOMINION_REVENUE_RUNTIME_ENABLED=1
Environment=DOMINION_REVENUE_DB=$state_root/revenue.db
Environment=DOMINION_REVENUE_SIGNING_KEY_FILE=$signing_key
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=-$user_home/dominion-ops/.env
ExecStart=$buddy_python -m apps.revenue_runtime.evaluator
TimeoutStartSec=10min
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=read-only
ReadWritePaths=$state_root
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
EOF

cat > "$eval_timer_tmp" <<EOF
[Unit]
Description=Evaluate Dominion revenue experiments every 10 minutes

[Timer]
OnBootSec=3min
OnUnitActiveSec=10min
RandomizedDelaySec=30
Persistent=true
Unit=$eval_service

[Install]
WantedBy=timers.target
EOF

sudo install -m 644 "$service_tmp" "$service_path"
sudo install -m 644 "$eval_service_tmp" "$eval_service_path"
sudo install -m 644 "$eval_timer_tmp" "$eval_timer_path"
rm -f "$service_tmp" "$eval_service_tmp" "$eval_timer_tmp"
sudo systemctl daemon-reload

# Add only the two public revenue paths to the existing Dominion origin.
sudo python3 - "$caddy_path" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
text=p.read_text()
marker='dominionhealing.org, www.dominionhealing.org {'
block='''\n\t@dominion_revenue_public path /r /r/* /revenue/events\n\treverse_proxy @dominion_revenue_public 127.0.0.1:8790\n'''
if '@dominion_revenue_public' not in text:
    if text.count(marker) != 1:
        raise SystemExit('dominion origin marker is not unique')
    text=text.replace(marker, marker + block, 1)
    p.write_text(text)
PY
sudo caddy validate --config "$caddy_path" >/dev/null
sudo systemctl reload caddy

sudo systemctl enable --now "$service_name" >/dev/null
for _ in $(seq 1 20); do
  code="$(curl -sS -o /tmp/revenue-health.$RUN_ID -w '%{http_code}' --max-time 4 http://127.0.0.1:8790/health || true)"
  [ "$code" = 200 ] && break
  sleep 1
done
[ "${code:-000}" = 200 ]
grep -q '"status":"ok"' /tmp/revenue-health.$RUN_ID
rm -f /tmp/revenue-health.$RUN_ID

unauth="$(curl -sS -o /dev/null -w '%{http_code}' -X POST --max-time 5 http://127.0.0.1:8790/control/evaluate || true)"
[ "$unauth" = 401 ]

# Caddy proof: public request must reach FastAPI and return its experiment 404.
probe="$(curl -sS --max-time 12 https://dominionhealing.org/r/__dominion_revenue_probe__ || true)"
printf '%s' "$probe" | grep -q 'Experiment not found'

# Evaluator must complete once before its recurring timer is armed.
sudo systemctl reset-failed "$eval_service" >/dev/null 2>&1 || true
sudo systemctl start "$eval_service"
[ "$(sudo systemctl show "$eval_service" -p Result --value)" = success ]
sudo systemctl enable --now "$eval_timer" >/dev/null
[ "$(sudo systemctl is-active "$eval_timer")" = active ]
[ "$(sudo systemctl is-enabled "$eval_timer")" = enabled ]

runtime_sha="$(sha256sum "$runtime_root/apps/revenue_runtime/service.py" | awk '{print $1}')"
policy_sha="$(sha256sum "$runtime_root/governance/revenue_execution_policy.json" | awk '{print $1}')"
echo 'DOMINION_REVENUE_RUNTIME=ACTIVE'
echo "REVENUE_RUNTIME_SHA256=$runtime_sha"
echo "REVENUE_POLICY_SHA256=$policy_sha"
echo 'REVENUE_INGRESS=PASS paths=/r,/revenue/events'
echo 'REVENUE_EVALUATOR_TIMER=PASS cadence=10m'
echo "REVENUE_BUDDY_RUNTIME=PASS interpreter=$buddy_python"
echo 'REVENUE_PRICE_AUTOMATION=DISABLED'
echo 'REVENUE_SPEND_AUTOMATION=DISABLED'

success=1
trap - ERR INT TERM EXIT
rm -rf "$backup_root"
echo 'DOMINION_REVENUE_DEPLOY=PASS'

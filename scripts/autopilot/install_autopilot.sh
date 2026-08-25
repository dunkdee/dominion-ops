#!/usr/bin/env bash
set -Eeuo pipefail

: "${ASSET_ROOT:?ASSET_ROOT is required}"
: "${RUN_ID:?RUN_ID is required}"

asset_root="$(cd "$ASSET_ROOT" && pwd -P)"
user_name="$(id -un)"
user_home="$HOME"
state_root="$user_home/.dominion/autopilot"
runtime_root="$state_root/runtime"
new_runtime="$state_root/runtime.new.$RUN_ID"
backup_root="$state_root/backups/deploy-$RUN_ID"
service_name="dominion-radah-autopilot.service"
timer_name="dominion-radah-autopilot.timer"
service_path="/etc/systemd/system/$service_name"
timer_path="/etc/systemd/system/$timer_name"
success=0

mkdir -p "$state_root" "$state_root/backups"
chmod 700 "$state_root" "$state_root/backups"
rm -rf "$new_runtime"
mkdir -p "$new_runtime/scripts/autopilot" "$new_runtime/governance"
chmod 700 "$new_runtime"

install -m 700 "$asset_root/scripts/autopilot/lane_supervisor.py" "$new_runtime/scripts/autopilot/lane_supervisor.py"
install -m 600 "$asset_root/governance/radah_memshalah_autopilot_policy.json" "$new_runtime/governance/radah_memshalah_autopilot_policy.json"
install -m 600 "$asset_root/governance/verticals.json" "$new_runtime/governance/verticals.json"

python3 -m py_compile "$new_runtime/scripts/autopilot/lane_supervisor.py"
plan_output="$(RADAH_AUTOPILOT_ENABLED=0 python3 "$new_runtime/scripts/autopilot/lane_supervisor.py" --plan-only --state-dir "$state_root/preflight")"
printf '%s\n' "$plan_output"
printf '%s' "$plan_output" | grep -q 'RADAH_AUTOPILOT=PLANNED'
test ! -e "$state_root/preflight/state.json"
rmdir "$state_root/preflight" 2>/dev/null || true

mkdir -p "$backup_root"
chmod 700 "$backup_root"
if [ -d "$runtime_root" ]; then
  mv "$runtime_root" "$backup_root/runtime"
fi
if sudo test -f "$service_path"; then
  sudo cp -a "$service_path" "$backup_root/service.unit"
  sudo chown "$user_name":"$(id -gn)" "$backup_root/service.unit"
fi
if sudo test -f "$timer_path"; then
  sudo cp -a "$timer_path" "$backup_root/timer.unit"
  sudo chown "$user_name":"$(id -gn)" "$backup_root/timer.unit"
fi

rollback() {
  rc=$?
  if [ "$success" -eq 1 ]; then
    exit "$rc"
  fi
  set +e
  echo "RADAH_AUTOPILOT_ROLLBACK=BEGIN rc=$rc"
  sudo systemctl disable --now "$timer_name" >/dev/null 2>&1 || true
  sudo systemctl stop "$service_name" >/dev/null 2>&1 || true
  if [ -f "$backup_root/service.unit" ]; then
    sudo install -m 644 "$backup_root/service.unit" "$service_path"
  else
    sudo rm -f "$service_path"
  fi
  if [ -f "$backup_root/timer.unit" ]; then
    sudo install -m 644 "$backup_root/timer.unit" "$timer_path"
  else
    sudo rm -f "$timer_path"
  fi
  sudo systemctl daemon-reload >/dev/null 2>&1 || true
  rm -rf "$runtime_root"
  if [ -d "$backup_root/runtime" ]; then
    mv "$backup_root/runtime" "$runtime_root"
  fi
  if sudo test -f "$timer_path"; then
    sudo systemctl enable --now "$timer_name" >/dev/null 2>&1 || true
  fi
  rm -rf "$new_runtime"
  echo "RADAH_AUTOPILOT_ROLLBACK=COMPLETE"
  exit "$rc"
}
trap rollback ERR INT TERM EXIT

mv "$new_runtime" "$runtime_root"
mkdir -p "$state_root/receipts" "$user_home/.dominion/buddy"
chmod 700 "$state_root/receipts" "$user_home/.dominion/buddy"

service_tmp="$(mktemp)"
timer_tmp="$(mktemp)"
trap 'rm -f "$service_tmp" "$timer_tmp"' RETURN
cat > "$service_tmp" <<EOF
[Unit]
Description=RADAH MEMSHALAH Dominion Production Lane Supervisor
After=network-online.target
Wants=network-online.target
ConditionPathExists=$runtime_root/scripts/autopilot/lane_supervisor.py

[Service]
Type=oneshot
User=$user_name
WorkingDirectory=$runtime_root
Environment=RADAH_AUTOPILOT_ENABLED=1
Environment=DOMINION_BUDDY_ROOT=$user_home/buddy_core
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=-$user_home/buddy_core/.env
EnvironmentFile=-$user_home/conductor/.env
ExecStart=/usr/bin/python3 $runtime_root/scripts/autopilot/lane_supervisor.py --execute --state-dir $state_root
TimeoutStartSec=20min
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=read-only
ReadWritePaths=$user_home/.dominion
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6

[Install]
WantedBy=multi-user.target
EOF

cat > "$timer_tmp" <<EOF
[Unit]
Description=Run RADAH MEMSHALAH production supervisor every 30 minutes

[Timer]
OnBootSec=5min
OnUnitActiveSec=30min
RandomizedDelaySec=60
Persistent=true
Unit=$service_name

[Install]
WantedBy=timers.target
EOF

sudo install -m 644 "$service_tmp" "$service_path"
sudo install -m 644 "$timer_tmp" "$timer_path"
rm -f "$service_tmp" "$timer_tmp"
sudo systemctl daemon-reload
sudo systemctl enable "$timer_name" >/dev/null

# Acceptance requires one real bounded internal mission before the timer is armed.
sudo systemctl start "$service_name"
result="$(sudo systemctl show "$service_name" -p Result --value)"
[ "$result" = "success" ] || { echo "RADAH_AUTOPILOT=HOLD service_result=$result"; exit 40; }

latest_receipt="$(find "$state_root/receipts" -maxdepth 1 -type f -name '*.json' -printf '%T@ %p\n' | sort -nr | head -1 | cut -d' ' -f2-)"
test -n "$latest_receipt" && test -s "$latest_receipt"
python3 - "$latest_receipt" <<'PY'
import json, sys
p = json.load(open(sys.argv[1], encoding='utf-8'))
assert p['status'] in {'COMPLETE', 'HELD'}
assert p['external_actions_authorized'] is False
assert p.get('lane')
print(f"AUTOPILOT_FIRST_MISSION=PASS lane={p['lane']} status={p['status']}")
PY

# Confirm the already-online core did not regress while activating the supervisor.
check200() {
  name="$1"; url="$2"
  code="$(curl -sS -o /dev/null -w '%{http_code}' --connect-timeout 3 --max-time 8 "$url" || true)"
  [ "$code" = 200 ] || { echo "RADAH_AUTOPILOT=HOLD health=$name status=$code"; exit 41; }
  echo "AUTOPILOT_HEALTH=PASS name=$name status=200"
}
check200 n8n http://127.0.0.1:5678/healthz
check200 conductor http://127.0.0.1:5060/health
check200 alpha_engine http://127.0.0.1:8787/health
check200 dominion_web http://127.0.0.1:8090/
check200 wix_agent http://127.0.0.1:8082/ready
[ "$(curl -sS -o /dev/null -w '%{http_code}' --max-time 8 http://127.0.0.1:5070/buddy || true)" = 401 ] || { echo 'RADAH_AUTOPILOT=HOLD buddy_auth_boundary'; exit 42; }

sudo systemctl enable --now "$timer_name" >/dev/null
[ "$(sudo systemctl is-active "$timer_name")" = "active" ]
[ "$(sudo systemctl is-enabled "$timer_name")" = "enabled" ]

runtime_sha="$(sha256sum "$runtime_root/scripts/autopilot/lane_supervisor.py" | awk '{print $1}')"
policy_sha="$(sha256sum "$runtime_root/governance/radah_memshalah_autopilot_policy.json" | awk '{print $1}')"
printf 'RADAH_AUTOPILOT=ACTIVE\n'
printf 'AUTOPILOT_RUNTIME_SHA256=%s\n' "$runtime_sha"
printf 'AUTOPILOT_POLICY_FILE_SHA256=%s\n' "$policy_sha"
printf 'AUTOPILOT_TIMER=PASS cadence=30m\n'

success=1
trap - ERR INT TERM EXIT
rm -rf "$backup_root"
echo 'RADAH_AUTOPILOT_DEPLOY=PASS'

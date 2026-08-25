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

# Reuse the exact Python entrypoint already proven by the healthy Buddy service.
# This avoids creating a second dependency universe for the same operator.
buddy_exec="$(systemctl show dominion-buddy-web.service -p ExecStart --value 2>/dev/null || true)"
buddy_python="$(printf '%s\n' "$buddy_exec" | sed -n 's/.*path=\([^ ;]*\).*/\1/p' | head -1)"
test -n "$buddy_python" || { echo 'RADAH_AUTOPILOT=HOLD reason=buddy_python_unresolved'; exit 20; }
case "$buddy_python" in
  *[[:space:]]*) echo 'RADAH_AUTOPILOT=HOLD reason=buddy_python_invalid'; exit 21 ;;
esac
test -x "$buddy_python" || { echo 'RADAH_AUTOPILOT=HOLD reason=buddy_python_not_executable'; exit 22; }

# Prove this interpreter can load the live Buddy operator before any unit change.
DOMINION_BUDDY_ROOT="$user_home/buddy_core" "$buddy_python" - <<'PY'
import os, sys
from pathlib import Path
root = Path(os.environ["DOMINION_BUDDY_ROOT"])
sys.path.insert(0, str(root))
from core.operator import get_operator
operator = get_operator()
assert operator.capabilities
print(f"BUDDY_RUNTIME_IMPORT=PASS capabilities={len(operator.capabilities)}")
PY

mkdir -p "$state_root" "$state_root/backups"
chmod 700 "$state_root" "$state_root/backups"
rm -rf "$new_runtime"
mkdir -p "$new_runtime/scripts/autopilot" "$new_runtime/governance"
chmod 700 "$new_runtime"

install -m 700 "$asset_root/scripts/autopilot/lane_supervisor.py" "$new_runtime/scripts/autopilot/lane_supervisor.py"
install -m 600 "$asset_root/governance/radah_memshalah_autopilot_policy.json" "$new_runtime/governance/radah_memshalah_autopilot_policy.json"
install -m 600 "$asset_root/governance/verticals.json" "$new_runtime/governance/verticals.json"

"$buddy_python" -m py_compile "$new_runtime/scripts/autopilot/lane_supervisor.py"
plan_output="$(RADAH_AUTOPILOT_ENABLED=0 "$buddy_python" "$new_runtime/scripts/autopilot/lane_supervisor.py" --plan-only --state-dir "$state_root/preflight")"
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
  trap - ERR INT TERM EXIT
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
cat > "$service_tmp" <<EOF
[Unit]
Description=RADAH MEMSHALAH Dominion Production Lane Supervisor
After=network-online.target dominion-buddy-web.service
Wants=network-online.target
ConditionPathExists=$runtime_root/scripts/autopilot/lane_supervisor.py
ConditionPathExists=$buddy_python

[Service]
Type=oneshot
User=$user_name
WorkingDirectory=$runtime_root
Environment=RADAH_AUTOPILOT_ENABLED=1
Environment=DOMINION_BUDDY_ROOT=$user_home/buddy_core
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=-$user_home/buddy_core/.env
EnvironmentFile=-$user_home/conductor/.env
ExecStart=$buddy_python $runtime_root/scripts/autopilot/lane_supervisor.py --execute --state-dir $state_root
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

cycles_before="$("$buddy_python" - "$state_root/state.json" <<'PY'
import json,sys
from pathlib import Path
p=Path(sys.argv[1])
if not p.is_file():
    print(0)
else:
    try:
        print(int(json.loads(p.read_text(encoding='utf-8')).get('cycles',0)))
    except Exception:
        raise SystemExit(2)
PY
)"

validate_latest_cycle() {
  expected_not_lane="${1:-}"
  latest_receipt="$(find "$state_root/receipts" -maxdepth 1 -type f -name '*.json' -printf '%T@ %p\n' | sort -nr | head -1 | cut -d' ' -f2-)"
  test -n "$latest_receipt" && test -s "$latest_receipt"
  "$buddy_python" - "$latest_receipt" "$expected_not_lane" <<'PY'
import json,sys
p=json.load(open(sys.argv[1],encoding='utf-8'))
not_lane=sys.argv[2]
status=str(p.get('status',''))
assert status in {'COMPLETE','HELD','BLOCKED'}
assert p.get('external_actions_authorized') is False
lane=str(p.get('lane',''))
assert lane
assert not not_lane or lane != not_lane
assert not p.get('supervisor_error')
if status == 'BLOCKED':
    assert p.get('mission_id')
    receipts=p.get('receipts')
    assert isinstance(receipts,list) and receipts
print(f"{lane}|{status}")
PY
}

# A governed evidence/policy blocker is a healthy bounded cycle. It must yield
# instead of crashing the scheduler. Supervisor exceptions still fail systemd.
sudo systemctl reset-failed "$service_name" >/dev/null 2>&1 || true
sudo systemctl start "$service_name"
result="$(sudo systemctl show "$service_name" -p Result --value)"
[ "$result" = "success" ] || { echo "RADAH_AUTOPILOT=HOLD service_result=$result"; exit 40; }
first_meta="$(validate_latest_cycle)"
first_lane="${first_meta%%|*}"
first_status="${first_meta#*|}"
echo "AUTOPILOT_FIRST_CYCLE=PASS lane=$first_lane status=$first_status"

cycles_after_first="$("$buddy_python" -c "import json; print(int(json.load(open('$state_root/state.json')).get('cycles',0)))")"
[ "$cycles_after_first" -ge "$((cycles_before + 1))" ]

# If the first lane is legitimately blocked, immediately prove rotation to a
# different lane before arming the recurring timer.
if [ "$first_status" = "BLOCKED" ]; then
  sudo systemctl start "$service_name"
  result="$(sudo systemctl show "$service_name" -p Result --value)"
  [ "$result" = "success" ] || { echo "RADAH_AUTOPILOT=HOLD rotation_service_result=$result"; exit 43; }
  second_meta="$(validate_latest_cycle "$first_lane")"
  second_lane="${second_meta%%|*}"
  second_status="${second_meta#*|}"
  echo "AUTOPILOT_BLOCKED_ROTATION=PASS from=$first_lane to=$second_lane status=$second_status"
  cycles_after_second="$("$buddy_python" -c "import json; print(int(json.load(open('$state_root/state.json')).get('cycles',0)))")"
  [ "$cycles_after_second" -ge "$((cycles_before + 2))" ]
fi

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
printf 'AUTOPILOT_BUDDY_RUNTIME=PASS interpreter=%s\n' "$buddy_python"

success=1
trap - ERR INT TERM EXIT
rm -rf "$backup_root"
echo 'RADAH_AUTOPILOT_DEPLOY=PASS'

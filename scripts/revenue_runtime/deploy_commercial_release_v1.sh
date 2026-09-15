#!/usr/bin/env bash
set -Eeuo pipefail

: "${ASSET_ROOT:?ASSET_ROOT is required}"
: "${RUN_ID:?RUN_ID is required}"
: "${EXPECTED_SOURCE_SHA:?EXPECTED_SOURCE_SHA is required}"

asset_root="$(cd "$ASSET_ROOT" && pwd -P)"
source_sha_file="$asset_root/SOURCE_SHA"
state_root="$HOME/.dominion/revenue-runtime"
runtime_root="$state_root/runtime"
rollback_root="$state_root/release-rollbacks/$RUN_ID"
service_name="dominion-revenue-runtime.service"
eval_service="dominion-revenue-evaluator.service"
eval_timer="dominion-revenue-evaluator.timer"
service_path="/etc/systemd/system/$service_name"
eval_service_path="/etc/systemd/system/$eval_service"
eval_timer_path="/etc/systemd/system/$eval_timer"
service_dropin="/etc/systemd/system/$service_name.d"
eval_dropin="/etc/systemd/system/$eval_service.d"
caddy_path="/etc/caddy/Caddyfile"
success=0

[[ "$EXPECTED_SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]] || { echo 'REVENUE_COMMERCIAL_DEPLOY=HOLD reason=invalid_expected_source_sha'; exit 20; }
test -s "$source_sha_file" || { echo 'REVENUE_COMMERCIAL_DEPLOY=HOLD reason=source_sha_file_missing'; exit 21; }
actual_source_sha="$(tr -d '[:space:]' < "$source_sha_file")"
test "$actual_source_sha" = "$EXPECTED_SOURCE_SHA" || { echo "REVENUE_COMMERCIAL_DEPLOY=HOLD reason=source_sha_mismatch expected=$EXPECTED_SOURCE_SHA actual=$actual_source_sha"; exit 22; }
test -x "$asset_root/scripts/revenue_runtime/install_revenue_runtime.sh" || chmod +x "$asset_root/scripts/revenue_runtime/install_revenue_runtime.sh"

buddy_exec="$(systemctl show dominion-buddy-web.service -p ExecStart --value 2>/dev/null || true)"
buddy_python="$(printf '%s\n' "$buddy_exec" | sed -n 's/.*path=\([^ ;]*\).*/\1/p' | head -1)"
test -n "$buddy_python" || { echo 'REVENUE_COMMERCIAL_DEPLOY=HOLD reason=buddy_python_unresolved'; exit 23; }
test -x "$buddy_python" || { echo 'REVENUE_COMMERCIAL_DEPLOY=HOLD reason=buddy_python_not_executable'; exit 24; }

mkdir -p "$state_root/release-rollbacks"
chmod 700 "$state_root" "$state_root/release-rollbacks"
test ! -e "$rollback_root" || { echo 'REVENUE_COMMERCIAL_DEPLOY=HOLD reason=rollback_reference_exists'; exit 25; }
mkdir -p "$rollback_root"
chmod 700 "$rollback_root"

service_active_before="$(systemctl is-active "$service_name" 2>/dev/null || true)"
service_enabled_before="$(systemctl is-enabled "$service_name" 2>/dev/null || true)"
timer_active_before="$(systemctl is-active "$eval_timer" 2>/dev/null || true)"
timer_enabled_before="$(systemctl is-enabled "$eval_timer" 2>/dev/null || true)"
printf '%s\n' "$service_active_before" > "$rollback_root/service.active.before"
printf '%s\n' "$service_enabled_before" > "$rollback_root/service.enabled.before"
printf '%s\n' "$timer_active_before" > "$rollback_root/timer.active.before"
printf '%s\n' "$timer_enabled_before" > "$rollback_root/timer.enabled.before"
printf '%s\n' "$EXPECTED_SOURCE_SHA" > "$rollback_root/target-source-sha"

backup_optional_path() {
  local src="$1" name="$2"
  if sudo test -e "$src"; then
    sudo cp -a "$src" "$rollback_root/$name"
    sudo chown -R "$(id -u):$(id -g)" "$rollback_root/$name"
  else
    : > "$rollback_root/$name.ABSENT"
  fi
}

backup_optional_path "$runtime_root" runtime
backup_optional_path "$service_path" service.unit
backup_optional_path "$eval_service_path" eval-service.unit
backup_optional_path "$eval_timer_path" eval-timer.unit
backup_optional_path "$service_dropin" service.dropin
backup_optional_path "$eval_dropin" eval.dropin
backup_optional_path "$caddy_path" Caddyfile

if [ -s "$state_root/revenue.db" ]; then
  "$buddy_python" - "$state_root/revenue.db" "$rollback_root/revenue.db" <<'PY'
import sqlite3, sys
src = sqlite3.connect(sys.argv[1], timeout=20)
dst = sqlite3.connect(sys.argv[2])
with dst:
    src.backup(dst)
check = dst.execute('PRAGMA integrity_check').fetchone()[0]
if check != 'ok':
    raise SystemExit(f'backup integrity failed: {check}')
src.close(); dst.close()
print('REVENUE_DB_BACKUP=PASS')
PY
  chmod 600 "$rollback_root/revenue.db"
else
  : > "$rollback_root/revenue.db.ABSENT"
fi

restore_optional_path() {
  local dst="$1" name="$2"
  sudo rm -rf "$dst"
  if [ -e "$rollback_root/$name" ]; then
    sudo cp -a "$rollback_root/$name" "$dst"
  fi
}

restore_states() {
  if [ "$service_enabled_before" = enabled ]; then sudo systemctl enable "$service_name" >/dev/null 2>&1 || true; else sudo systemctl disable "$service_name" >/dev/null 2>&1 || true; fi
  if [ "$service_active_before" = active ]; then sudo systemctl start "$service_name" >/dev/null 2>&1 || true; else sudo systemctl stop "$service_name" >/dev/null 2>&1 || true; fi
  if [ "$timer_enabled_before" = enabled ]; then sudo systemctl enable "$eval_timer" >/dev/null 2>&1 || true; else sudo systemctl disable "$eval_timer" >/dev/null 2>&1 || true; fi
  if [ "$timer_active_before" = active ]; then sudo systemctl start "$eval_timer" >/dev/null 2>&1 || true; else sudo systemctl stop "$eval_timer" >/dev/null 2>&1 || true; fi
}

rollback() {
  rc=$?
  [ "$success" -eq 1 ] && exit "$rc"
  trap - ERR INT TERM EXIT
  set +e
  echo "REVENUE_COMMERCIAL_ROLLBACK=BEGIN rc=$rc"
  sudo systemctl disable --now "$eval_timer" >/dev/null 2>&1 || true
  sudo systemctl stop "$service_name" "$eval_service" >/dev/null 2>&1 || true
  restore_optional_path "$runtime_root" runtime
  restore_optional_path "$service_path" service.unit
  restore_optional_path "$eval_service_path" eval-service.unit
  restore_optional_path "$eval_timer_path" eval-timer.unit
  restore_optional_path "$service_dropin" service.dropin
  restore_optional_path "$eval_dropin" eval.dropin
  restore_optional_path "$caddy_path" Caddyfile
  if [ -s "$rollback_root/revenue.db" ]; then cp -a "$rollback_root/revenue.db" "$state_root/revenue.db"; fi
  sudo systemctl daemon-reload >/dev/null 2>&1 || true
  sudo caddy validate --config "$caddy_path" >/dev/null 2>&1 && sudo systemctl reload caddy >/dev/null 2>&1 || true
  restore_states
  echo "REVENUE_COMMERCIAL_ROLLBACK=COMPLETE reference=$rollback_root"
  exit "$rc"
}
trap rollback ERR INT TERM EXIT

# Quiesce the recurring evaluator before changing runtime files.
sudo systemctl stop "$eval_timer" >/dev/null 2>&1 || true

# Fail closed: Commercial Release 1.0 certifies attribution/accounting, not automatic Wix mutation.
# The drop-ins are installed before the legacy installer can run its evaluator acceptance cycle.
sudo install -d -m 755 "$service_dropin" "$eval_dropin"
printf '%s\n' '[Service]' 'Environment=DOMINION_REVENUE_RUNTIME_ENABLED=0' | sudo tee "$service_dropin/90-commercial-release.conf" >/dev/null
printf '%s\n' '[Service]' 'Environment=DOMINION_REVENUE_RUNTIME_ENABLED=0' | sudo tee "$eval_dropin/90-commercial-release.conf" >/dev/null
sudo chmod 644 "$service_dropin/90-commercial-release.conf" "$eval_dropin/90-commercial-release.conf"
sudo systemctl daemon-reload

ASSET_ROOT="$asset_root" RUN_ID="commercial-$RUN_ID" bash "$asset_root/scripts/revenue_runtime/install_revenue_runtime.sh"

# The legacy installer uses enable --now, which does not restart an already-running service.
# Restart explicitly so acceptance proves the newly deployed files, not an old in-memory process.
sudo systemctl daemon-reload
sudo systemctl restart "$service_name"

# Commercial release does not expose generic server-event ingestion. Wix reconciliation is server-side.
sudo python3 - "$caddy_path" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
text = p.read_text(encoding='utf-8')
text = text.replace('@dominion_revenue_public path /r /r/* /revenue/events', '@dominion_revenue_public path /r /r/*')
p.write_text(text, encoding='utf-8')
PY
sudo caddy validate --config "$caddy_path" >/dev/null
sudo systemctl reload caddy
! sudo grep -Eq '@dominion_revenue_public[[:space:]]+path[^\n]*\/revenue\/events' "$caddy_path"
echo 'REVENUE_PUBLIC_EVENT_INGESTION=DISABLED'

# Prove exact deployed source for every Revenue Runtime Python module and policy.
for src in "$asset_root"/apps/revenue_runtime/*.py; do
  name="$(basename "$src")"
  cmp -s "$src" "$runtime_root/apps/revenue_runtime/$name" || { echo "REVENUE_RUNTIME_MANIFEST=FAIL file=$name"; exit 40; }
done
cmp -s "$asset_root/governance/revenue_execution_policy.json" "$runtime_root/governance/revenue_execution_policy.json" || { echo 'REVENUE_RUNTIME_MANIFEST=FAIL file=revenue_execution_policy.json'; exit 41; }
echo "REVENUE_RUNTIME_MANIFEST=PASS source_sha=$EXPECTED_SOURCE_SHA"

# Prove the live process is the restarted commercial-mode runtime.
health_file="$(mktemp)"
for _ in $(seq 1 20); do
  code="$(curl -sS -o "$health_file" -w '%{http_code}' --max-time 4 http://127.0.0.1:8790/health || true)"
  [ "$code" = 200 ] && break
  sleep 1
done
[ "${code:-000}" = 200 ]
"$buddy_python" - "$health_file" <<'PY'
import json, sys
payload = json.load(open(sys.argv[1], encoding='utf-8'))
assert payload.get('status') == 'ok', payload
assert payload.get('execution_enabled') is False, payload
print('REVENUE_AUTO_CRO=DISABLED')
PY
rm -f "$health_file"

unauth="$(curl -sS -o /dev/null -w '%{http_code}' -X POST --max-time 5 http://127.0.0.1:8790/control/evaluate || true)"
[ "$unauth" = 401 ]
echo 'REVENUE_CONTROL_NEGATIVE_AUTH=PASS'

probe="$(curl -sS --max-time 12 https://dominionhealing.org/r/__dominion_revenue_commercial_probe__ || true)"
printf '%s' "$probe" | grep -q 'Experiment not found'
echo 'REVENUE_PUBLIC_ROUTER=PASS'

# Run the reconciler once in fail-closed commercial mode, then restore its timer.
sudo systemctl reset-failed "$eval_service" >/dev/null 2>&1 || true
sudo systemctl start "$eval_service"
[ "$(sudo systemctl show "$eval_service" -p Result --value)" = success ]
sudo systemctl enable --now "$eval_timer" >/dev/null
[ "$(sudo systemctl is-active "$eval_timer")" = active ]
[ "$(sudo systemctl is-enabled "$eval_timer")" = enabled ]
echo 'REVENUE_EVALUATOR_TIMER=PASS cadence=10m'

if [ -s "$state_root/revenue.db" ]; then
  "$buddy_python" - "$state_root/revenue.db" <<'PY'
import sqlite3, sys
con = sqlite3.connect(sys.argv[1], timeout=20)
check = con.execute('PRAGMA integrity_check').fetchone()[0]
if check != 'ok':
    raise SystemExit(f'database integrity failed: {check}')
print('REVENUE_DB_INTEGRITY=PASS')
con.close()
PY
fi

cat > "$rollback_root/DEPLOYMENT_RECEIPT" <<EOF
source_sha=$EXPECTED_SOURCE_SHA
run_id=$RUN_ID
commercial_mode=attribution_accounting_only
auto_cro=disabled
public_event_ingestion=disabled
rollback_reference=$rollback_root
EOF
chmod 600 "$rollback_root/DEPLOYMENT_RECEIPT"

# Keep rollback evidence after success; prune only older completed rollback packages beyond the newest three.
find "$state_root/release-rollbacks" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' 2>/dev/null | sort -nr | awk 'NR>3 {sub(/^[^ ]+ /, ""); print}' | while IFS= read -r old; do rm -rf -- "$old"; done

success=1
trap - ERR INT TERM EXIT
echo "REVENUE_ROLLBACK_REFERENCE=PASS path=$rollback_root"
echo "REVENUE_RUNTIME_SOURCE_SHA=PASS sha=$EXPECTED_SOURCE_SHA"
echo 'REVENUE_COMMERCIAL_RUNTIME_DEPLOY=PASS'

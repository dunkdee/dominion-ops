#!/usr/bin/env bash
set -euo pipefail

MAX_ATTEMPTS=2
COOLDOWN_SECONDS=300
STATE_DIR="${DOMINION_STATE_DIR:-/var/lib/dominion/buddy-self-heal}"
SETTLE_SECONDS="${DOMINION_REPAIR_SETTLE_SECONDS:-6}"
STATE_FILE="$STATE_DIR/state"
LOCK_FILE="$STATE_DIR/lock"

install -d -m 0700 "$STATE_DIR"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo 'BUDDY_SELF_HEAL=BLOCKED reason=repair_already_running'
  exit 30
fi

read_number() {
  local key="$1" default="$2" value
  value="$(awk -F= -v key="$key" '$1 == key {print $2}' \
    "$STATE_FILE" 2>/dev/null | tail -1 || true)"
  case "$value" in
    ''|*[!0-9]*) printf '%s' "$default" ;;
    *) printf '%s' "$value" ;;
  esac
}

write_state() {
  local failures="$1" attempt_epoch="$2" result="$3" tmp
  tmp="$STATE_FILE.tmp.$$"
  umask 077
  {
    printf 'consecutive_failures=%s\n' "$failures"
    printf 'last_attempt_epoch=%s\n' "$attempt_epoch"
    printf 'last_result=%s\n' "$result"
  } >"$tmp"
  mv "$tmp" "$STATE_FILE"
}

failed_units=()

add_failed() {
  local candidate="$1" existing
  for existing in "${failed_units[@]:-}"; do
    [[ "$existing" == "$candidate" ]] && return 0
  done
  failed_units+=("$candidate")
}

check_unit() {
  local unit="$1"
  systemctl is-active --quiet "$unit" || add_failed "$unit"
}

check_runtime() {
  local buddy_code proposal_code
  failed_units=()
  check_unit dominion-buddy-web.service
  check_unit dominion-proposal-queue.service
  check_unit dominion-sentinel.service

  buddy_code="$(curl -sS -o /dev/null -w '%{http_code}' \
    --connect-timeout 2 --max-time 6 \
    http://127.0.0.1:5070/buddy 2>/dev/null || true)"
  [[ "$buddy_code" == 401 ]] || add_failed dominion-buddy-web.service

  proposal_code="$(curl -sS -o /dev/null -w '%{http_code}' \
    --connect-timeout 2 --max-time 6 \
    http://127.0.0.1:5101/api/proposals 2>/dev/null || true)"
  [[ "$proposal_code" == 200 ]] || add_failed dominion-proposal-queue.service

  ss -ltnH 2>/dev/null | awk '{print $4}' | grep -Eq '(^|:)5070$' || \
    add_failed dominion-buddy-web.service
  ss -ltnH 2>/dev/null | awk '{print $4}' | grep -Eq '(^|:)5101$' || \
    add_failed dominion-proposal-queue.service
}

echo '=== OBSERVE ==='
check_runtime
now="$(date +%s)"
consecutive_failures="$(read_number consecutive_failures 0)"
last_attempt_epoch="$(read_number last_attempt_epoch 0)"

if [[ "${#failed_units[@]}" -eq 0 ]]; then
  write_state 0 "$last_attempt_epoch" HEALTHY
  echo 'BUDDY_SELF_HEAL=NO_ACTION_HEALTHY'
  for unit in \
    dominion-buddy-web.service \
    dominion-proposal-queue.service \
    dominion-sentinel.service; do
    restarts="$(systemctl show "$unit" -p NRestarts --value 2>/dev/null || true)"
    echo "SERVICE=$unit active=active restarts=${restarts:-unknown}"
  done
  exit 0
fi

printf 'BUDDY_SELF_HEAL=UNHEALTHY services=%s\n' "${failed_units[*]}"

if [[ "$consecutive_failures" -ge "$MAX_ATTEMPTS" ]]; then
  echo "BUDDY_SELF_HEAL=BLOCKED_CIRCUIT_OPEN failures=$consecutive_failures"
  exit 31
fi

elapsed=$((now - last_attempt_epoch))
if [[ "$last_attempt_epoch" -gt 0 && "$elapsed" -lt "$COOLDOWN_SECONDS" ]]; then
  remaining=$((COOLDOWN_SECONDS - elapsed))
  echo "BUDDY_SELF_HEAL=BLOCKED cooldown_remaining_seconds=$remaining"
  exit 32
fi

echo '=== PRE-REPAIR EVIDENCE ==='
for unit in "${failed_units[@]}"; do
  systemctl show "$unit" -p ActiveState -p SubState -p NRestarts \
    -p ExecMainStatus --no-pager 2>/dev/null || true
done

attempt_number=$((consecutive_failures + 1))
# Persist the attempt before restarting anything so interruption cannot create
# an unbounded retry loop.
write_state "$attempt_number" "$now" ATTEMPTING

echo "=== BOUNDED RESTART attempt=$attempt_number/$MAX_ATTEMPTS ==="
for unit in "${failed_units[@]}"; do
  case "$unit" in
    dominion-buddy-web.service|dominion-proposal-queue.service|dominion-sentinel.service)
      systemctl restart "$unit"
      ;;
    *)
      echo "BUDDY_SELF_HEAL=BLOCKED reason=service_not_allowlisted unit=$unit"
      exit 33
      ;;
  esac
done

sleep "$SETTLE_SECONDS"
check_runtime
log_failure=0
since="$(date -u --date="@$now" '+%Y-%m-%d %H:%M:%S')"

echo '=== POST-REPAIR EVIDENCE ==='
for unit in \
  dominion-buddy-web.service \
  dominion-proposal-queue.service \
  dominion-sentinel.service; do
  systemctl show "$unit" -p ActiveState -p SubState -p NRestarts \
    -p ExecMainStatus --no-pager 2>/dev/null || true
  if journalctl -u "$unit" --since "$since" --no-pager 2>/dev/null | \
      grep -Eqi 'traceback|uncaught exception|failed with result|segmentation fault'; then
    echo "ERROR_LOG_CHECK=FAIL unit=$unit"
    log_failure=1
  else
    echo "ERROR_LOG_CHECK=PASS unit=$unit"
  fi
done

if [[ "${#failed_units[@]}" -eq 0 && "$log_failure" -eq 0 ]]; then
  write_state 0 "$now" RECOVERED
  echo "BUDDY_SELF_HEAL=RECOVERED attempt=$attempt_number"
  exit 0
fi

write_state "$attempt_number" "$now" FAILED
printf 'BUDDY_SELF_HEAL=FAILED attempt=%s remaining_services=%s\n' \
  "$attempt_number" "${failed_units[*]:-none}"
if [[ "$attempt_number" -ge "$MAX_ATTEMPTS" ]]; then
  echo "BUDDY_SELF_HEAL=BLOCKED_CIRCUIT_OPEN failures=$attempt_number"
fi
exit 34

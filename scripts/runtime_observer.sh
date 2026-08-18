#!/usr/bin/env bash
set -uo pipefail

# Local, read-only runtime observer. All output goes to journald through the
# systemd service; this script never mutates services, networking, or Git.

failures=0

fail() {
  printf 'CHECK=FAIL %s\n' "$*"
  failures=$((failures + 1))
}

pass() {
  printf 'CHECK=PASS %s\n' "$*"
}

check_http() {
  local name="$1" expected="$2" url="$3" code
  code="$(curl -sS -o /dev/null -w '%{http_code}' \
    --connect-timeout 3 --max-time 8 "$url" 2>/dev/null || true)"
  if [[ "$code" == "$expected" ]]; then
    pass "health=$name status=$code url=$url"
  else
    fail "health=$name expected=$expected actual=${code:-000} url=$url"
  fi
}

check_active() {
  local unit="$1" state
  state="$(systemctl is-active "$unit" 2>/dev/null || true)"
  if [[ "$state" == active ]]; then
    pass "unit=$unit active=$state"
  else
    fail "unit=$unit expected=active actual=${state:-unknown}"
  fi
}

check_held() {
  local unit="$1" active enabled
  active="$(systemctl is-active "$unit" 2>/dev/null || true)"
  enabled="$(systemctl is-enabled "$unit" 2>/dev/null || true)"
  if [[ "$active" == inactive && "$enabled" == disabled ]]; then
    pass "CONTAINMENT_HOLD=ENFORCED unit=$unit active=$active enabled=$enabled"
  else
    fail "CONTAINMENT_HOLD=BROKEN unit=$unit active=${active:-unknown} enabled=${enabled:-unknown}"
  fi
}

check_firewall_absent() {
  local rule="$1" output rc
  if ! command -v gcloud >/dev/null 2>&1; then
    fail "firewall=$rule state=UNKNOWN reason=gcloud_unavailable"
    return
  fi
  if output="$(gcloud compute firewall-rules describe "$rule" \
      --project=dominion-ascendant 2>&1)"; then
    rc=0
  else
    rc=$?
  fi
  if [[ "$rc" -eq 0 ]]; then
    fail "firewall=$rule state=PRESENT"
  elif grep -qiE 'was not found|not found' <<<"$output"; then
    pass "firewall=$rule state=ABSENT"
  else
    fail "firewall=$rule state=UNKNOWN reason=describe_failed"
  fi
}

echo '=== CORE RUNTIME ==='
check_http baby_api 200 http://127.0.0.1:8080/
check_http dominion_web 200 http://127.0.0.1:8090/
check_http wix_agent 200 http://127.0.0.1:8082/ready
check_http n8n 200 http://127.0.0.1:5678/healthz
check_http alpha_engine 200 http://127.0.0.1:8787/health
check_http conductor 200 http://127.0.0.1:5060/health

echo '=== BUDDY RUNTIME ==='
check_active dominion-buddy-web.service
check_active dominion-proposal-queue.service
check_active dominion-sentinel.service
check_http buddy_auth_boundary 401 http://127.0.0.1:5070/buddy
check_http proposal_queue 200 http://127.0.0.1:5101/api/proposals

echo '=== CONTAINMENT ==='
check_held dominion-nemotron.service
check_held dominion-email-monitor.service
check_held dominion-affiliate.timer
check_held dominion-scout.timer
check_held dominion-wholesale.timer

if ss -ltnH 2>/dev/null | awk '{print $4}' | grep -Eq '(^|:)11435$'; then
  fail 'CONTAINMENT_HOLD=BROKEN port=11435 listener=PRESENT'
else
  pass 'CONTAINMENT_HOLD=ENFORCED port=11435 listener=ABSENT'
fi

check_firewall_absent allow-ops-dashboard
check_firewall_absent allow-twilio-router

echo '=== GOVERNANCE STATE ==='
echo 'OBSIDIAN_CANONICAL=BLOCKED reason=four_store_reconciliation_not_accepted'
echo 'BUDDY_LIVE_CONFORMANCE=UNVERIFIED reason=vm_only_source_unreconciled'
echo 'EXTERNAL_ACTIONS_AUTHORIZED=false'

if [[ "$failures" -eq 0 ]]; then
  echo 'RUNTIME_OBSERVER=PASS system_online=VERIFIED_FOR_CHECKED_CONTRACTS'
  exit 0
fi

echo "RUNTIME_OBSERVER=FAIL failures=$failures"
exit 1

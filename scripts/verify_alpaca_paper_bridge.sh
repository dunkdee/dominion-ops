#!/usr/bin/env bash
#
# Verify the read-only Alpaca PAPER bridge on the Foundation VM.
#
# Safe to run before and after deployment: it only issues GET requests and
# never mutates the Command Center, the trading engine, or any broker account.
#
# Usage:
#   COMMAND_CENTER_API_KEY=... ./scripts/verify_alpaca_paper_bridge.sh [base_url]
#
# Exit status is 0 only when every governed assertion holds.

set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:8091}"
KEY="${COMMAND_CENTER_API_KEY:-}"
LEDGER="${TRADING_LEDGER_PATH:-/home/malachisingleton8/.dominion/ledger/alpaca-paper-observations.jsonl}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PASS=0
FAIL=0

ok()   { printf '  PASS  %s\n' "$1"; PASS=$((PASS + 1)); }
bad()  { printf '  FAIL  %s\n' "$1"; FAIL=$((FAIL + 1)); }
note() { printf '  ....  %s\n' "$1"; }

code_for() {
  local method="$1" path="$2"
  shift 2
  curl -s -o /dev/null -w '%{http_code}' -X "$method" "$@" "${BASE_URL}${path}" || echo "000"
}

echo "Dominion Alpaca paper bridge verification"
echo "base_url: ${BASE_URL}"
echo

echo "[1] Pre-existing Command Center surfaces (must be unaffected)"
for path in /health /api/status /api/revenue; do
  status="$(code_for GET "$path")"
  if [ "$status" = "200" ]; then ok "GET ${path} -> 200"; else bad "GET ${path} -> ${status}"; fi
done
echo

echo "[2] Bridge mount state (from the unauthenticated health probe)"
HEALTH="$(curl -fsS "${BASE_URL}/health" || echo '')"
if [ -z "$HEALTH" ]; then
  bad "could not read /health"
else
  python3 - "$HEALTH" <<'PY' && ok "bridge mounted, read-only, live trading disabled" || bad "bridge mount contract violated"
import json, sys
health = json.loads(sys.argv[1])
bridge = health.get("trading_bridge") or {}
assert bridge.get("mounted") is True, f"bridge not mounted: {bridge}"
assert bridge.get("read_only") is True
assert bridge.get("live_trading_enabled") is False
assert bridge.get("order_execution_enabled") is False
# The public probe must never carry account data.
blob = json.dumps(health)
for token in ("equity", "buying_power", "account_number"):
    assert token not in blob, f"public health leaked {token}"
PY
fi
echo

echo "[3] Authentication (fails closed)"
status="$(code_for GET /api/trading/paper/summary)"
if [ "$status" = "401" ]; then ok "unauthenticated request -> 401"
elif [ "$status" = "503" ]; then note "surface unconfigured (503): COMMAND_CENTER_API_KEY not set on the server"
else bad "unauthenticated request -> ${status} (expected 401)"; fi

status="$(code_for GET /api/trading/paper/summary -H 'X-Dominion-Key: definitely-not-the-real-key-000')"
if [ "$status" = "401" ] || [ "$status" = "503" ]; then ok "wrong key rejected (${status})"; else bad "wrong key -> ${status}"; fi
echo

echo "[4] Read-only surface (write verbs must not route)"
if [ -z "$KEY" ]; then
  note "COMMAND_CENTER_API_KEY not set in this shell; skipping authenticated checks"
else
  for method in POST PUT PATCH DELETE; do
    status="$(code_for "$method" /api/trading/paper/summary -H "X-Dominion-Key: ${KEY}")"
    if [ "$status" = "405" ]; then ok "${method} -> 405 Method Not Allowed"; else bad "${method} -> ${status} (expected 405)"; fi
  done
  echo

  echo "[5] Governed paper contract"
  BRIDGE="$(curl -fsS -H "X-Dominion-Key: ${KEY}" "${BASE_URL}/api/trading/paper/health" || echo '')"
  if [ -z "$BRIDGE" ]; then
    bad "could not read the authenticated bridge health endpoint"
  else
    python3 - "$BRIDGE" <<'PY' && ok "paper mode, read-only, paper host pinned" || bad "paper contract violated"
import json, sys
config = json.loads(sys.argv[1])["config"]
assert config["mode"] == "paper", config
assert config["read_only"] is True
assert config["live_trading_enabled"] is False
assert config["order_execution_enabled"] is False
if config["base_url"] is not None:
    assert "paper-api.alpaca.markets" in config["base_url"], config["base_url"]
assert "api.alpaca.markets/" not in (config["base_url"] or "") or "paper" in (config["base_url"] or "")
PY
    ACTIVATION="$(printf '%s' "$BRIDGE" | python3 -c 'import json,sys;print(json.load(sys.stdin)["activation_state"])')"
    note "activation_state: ${ACTIVATION}"
    if [ "$ACTIVATION" = "ready" ]; then
      ok "paper credentials present server-side"
    else
      note "remaining activation step: set ALPACA_PAPER_KEY_ID and ALPACA_PAPER_SECRET_KEY server-side, then redeploy"
    fi
  fi
  echo

  echo "[6] Observation payload truthfulness"
  SUMMARY="$(curl -fsS -H "X-Dominion-Key: ${KEY}" "${BASE_URL}/api/trading/paper/summary" || echo '')"
  if [ -z "$SUMMARY" ]; then
    bad "could not read the summary endpoint"
  else
    python3 - "$SUMMARY" <<'PY' && ok "summary is internally consistent and evidence-backed" || bad "summary contract violated"
import json, sys
body = json.loads(sys.argv[1])
assert body["live_trading_enabled"] is False
assert body["read_only"] is True
assert body["mode"] == "paper"
if body["connected"]:
    account = body["account"]
    assert account is not None and account["equity"] is not None
    assert body["pnl"] is not None
    print(f"    equity={account['equity']} buying_power={account['buying_power']} "
          f"realized={body['pnl']['realized']} unrealized={body['pnl']['unrealized']}")
else:
    # Not connected must mean nulls, never fabricated zeros.
    assert body["account"] is None and body["win_loss"] is None
    print(f"    not connected: {body['reason']}")
evidence = body.get("evidence") or {}
assert evidence.get("record_hash") or evidence.get("error"), "no evidence receipt"
PY
  fi
fi
echo

echo "[7] Evidence ledger integrity (canonical control-plane verification)"
if [ -f "$LEDGER" ]; then
  if (cd "$REPO_ROOT" && python3 -m control_plane.cli verify-ledger --ledger "$LEDGER" >/dev/null 2>&1); then
    COUNT="$(cd "$REPO_ROOT" && python3 -m control_plane.cli verify-ledger --ledger "$LEDGER" \
      | python3 -c 'import json,sys;print(json.load(sys.stdin)["record_count"])')"
    ok "ledger hash chain valid (${COUNT} records)"
  else
    bad "ledger hash chain FAILED verification: ${LEDGER}"
  fi
else
  note "no ledger yet at ${LEDGER} (written on first authenticated observation)"
fi
echo

echo "----------------------------------------"
echo "PASS=${PASS} FAIL=${FAIL}"
if [ "$FAIL" -gt 0 ]; then
  echo "RESULT: FAILED"
  exit 1
fi
echo "RESULT: OK — read-only paper bridge verified, live trading disabled"

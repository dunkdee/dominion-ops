#!/usr/bin/env bash
set -Eeuo pipefail

REPO_DIR="${REPO_DIR:-$HOME/dominion-ops}"
STATE_ROOT="$HOME/.dominion/system-integrity"
LIB_DIR="$HOME/.local/lib/dominion"
CONFIG_DIR="$HOME/.config/dominion"
SCRIPT_SRC="$REPO_DIR/scripts/system_integrity_agent.py"
CONTRACT_SRC="$REPO_DIR/governance/system_integrity_agent.json"
SERVICE_SRC="$REPO_DIR/deploy/systemd/dominion-system-integrity.service"
TIMER_SRC="$REPO_DIR/deploy/systemd/dominion-system-integrity.timer"

for path in "$SCRIPT_SRC" "$CONTRACT_SRC" "$SERVICE_SRC" "$TIMER_SRC"; do
  test -s "$path" || { echo "SYSTEM_INTEGRITY_INSTALL=FAIL missing=$path" >&2; exit 1; }
done

install -d -m 700 "$STATE_ROOT" "$STATE_ROOT/receipts" "$LIB_DIR" "$CONFIG_DIR"
install -m 700 "$SCRIPT_SRC" "$LIB_DIR/system_integrity_agent.py"
install -m 600 "$CONTRACT_SRC" "$CONFIG_DIR/system-integrity-agent.json"

python3 "$LIB_DIR/system_integrity_agent.py" \
  --contract "$CONFIG_DIR/system-integrity-agent.json" \
  --repo "$REPO_DIR" \
  --state-root "$STATE_ROOT" \
  --self-test

sudo install -m 644 "$SERVICE_SRC" /etc/systemd/system/dominion-system-integrity.service
sudo install -m 644 "$TIMER_SRC" /etc/systemd/system/dominion-system-integrity.timer
sudo systemctl daemon-reload
sudo systemctl enable --now dominion-system-integrity.timer

# First cycle is immediate and includes the end-to-end intelligence probe.
sudo systemctl reset-failed dominion-system-integrity.service >/dev/null 2>&1 || true
sudo systemctl start dominion-system-integrity.service

test "$(sudo systemctl show dominion-system-integrity.service -p Result --value)" = success
sudo systemctl is-active --quiet dominion-system-integrity.timer
sudo systemctl is-enabled --quiet dominion-system-integrity.timer

test -s "$STATE_ROOT/latest.json"
python3 - "$STATE_ROOT/latest.json" <<'PY'
import json,sys
state=json.load(open(sys.argv[1],encoding='utf-8'))
assert state['schema']=='dominion-system-integrity-state-v1'
assert state['agent']=='system-integrity-agent'
assert state['ok'] is True, state.get('defects')
assert state['status']=='PASS'
assert state['deep_probe_executed'] is True
assert state['authority']=='OBSERVE_VERIFY_REQUEST_RECOVERY'
assert state['self_mutation'] is False
print(f"SYSTEM_INTEGRITY_FIRST_CYCLE=PASS cycle={state['cycle']} checks={state['checks_total']} defects=0")
PY

echo "SYSTEM_INTEGRITY_INSTALL=PASS cadence=89s timer=active authority=observe_verify_request_recovery"

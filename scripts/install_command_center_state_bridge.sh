#!/usr/bin/env bash
set -Eeuo pipefail

: "${RUN_SHA:?RUN_SHA is required}"
repo="${REPO_DIR:-$HOME/dominion-ops}"
state_root="$HOME/.dominion/command-center"
runtime_root="$state_root/runtime"
receipts="$state_root/receipts"
bridge_v2_src="$repo/scripts/command_center_state_bridge_v2.py"
bridge_v3_src="$repo/scripts/command_center_state_bridge_v3.py"
bridge_v2="$runtime_root/command_center_state_bridge_v2.py"
bridge="$runtime_root/command_center_state_bridge.py"
service_name="dominion-command-center-state.service"
timer_name="dominion-command-center-state.timer"
service_path="/etc/systemd/system/$service_name"
timer_path="/etc/systemd/system/$timer_name"
user_name="$(id -un)"; group_name="$(id -gn)"

test -f "$bridge_v2_src"
test -f "$bridge_v3_src"
test "$(git -C "$repo" rev-parse HEAD)" = "$RUN_SHA"
vault="$(docker inspect obsidian-remote --format '{{range .Mounts}}{{if eq .Destination "/vaults/Dominion"}}{{.Source}}{{end}}{{end}}')"
test -n "$vault"; test -d "$vault/Dominion-Command-Center"
daily_state="$vault/Dominion-Command-Center/14-Daily-State.md"; test -f "$daily_state"

mkdir -p "$runtime_root" "$receipts"; chmod 700 "$state_root" "$runtime_root" "$receipts"
install -m 700 "$bridge_v2_src" "$bridge_v2"
install -m 700 "$bridge_v3_src" "$bridge"
python3 -m py_compile "$bridge_v2" "$bridge"
service_tmp="$(mktemp)"; timer_tmp="$(mktemp)"
cat > "$service_tmp" <<EOF
[Unit]
Description=Dominion Command Center Canonical Runtime State Bridge
After=network-online.target
Wants=network-online.target
ConditionPathExists=$bridge

[Service]
Type=oneshot
User=$user_name
Group=$group_name
WorkingDirectory=$repo
ExecStart=/usr/bin/python3 $bridge --repo $repo --dominion-root $HOME/.dominion --output $state_root/runtime-state.json --daily-state $daily_state
TimeoutStartSec=30
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=read-only
ReadWritePaths=$state_root $vault/Dominion-Command-Center
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
EOF
cat > "$timer_tmp" <<EOF
[Unit]
Description=Refresh Dominion Command Center system truth every minute

[Timer]
OnBootSec=30s
OnUnitActiveSec=60s
RandomizedDelaySec=10
Persistent=true
Unit=$service_name

[Install]
WantedBy=timers.target
EOF
sudo install -m 644 "$service_tmp" "$service_path"; sudo install -m 644 "$timer_tmp" "$timer_path"; rm -f "$service_tmp" "$timer_tmp"
sudo systemctl daemon-reload; sudo systemctl reset-failed "$service_name" >/dev/null 2>&1 || true; sudo systemctl start "$service_name"
test "$(sudo systemctl show "$service_name" -p Result --value)" = success
sudo systemctl enable --now "$timer_name" >/dev/null
test "$(sudo systemctl is-active "$timer_name")" = active; test "$(sudo systemctl is-enabled "$timer_name")" = enabled
test -s "$state_root/runtime-state.json"
python3 - "$state_root/runtime-state.json" "$RUN_SHA" <<'PY'
import json,sys
s=json.load(open(sys.argv[1],encoding='utf-8'))
assert s['schema']=='dominion-command-center-runtime-state-v2'
assert s['release_sha']==sys.argv[2]
assert s['lanes']['registered']==11 and s['lanes']['open']==11 and s['lanes']['all_open'] is True
assert s['founder_holds']
assert s['systems']['mcp_cli']['ok'] is True, s['systems']['mcp_cli']
assert s['systems']['dominion_publisher']['ok'] is True, s['systems']['dominion_publisher']
assert s['systems']['publisher_queue_ledger']['ok'] is True, s['systems']['publisher_queue_ledger']
p=s['publisher']
assert p['service']=='dominion-publisher'
assert isinstance(p['meta_bound_counts'],dict)
assert p['ledger']['connected'] is True
assert p['phase'] in {
    'AWAITING_META_APP_CONFIGURATION',
    'AWAITING_META_ACCOUNT_BINDING',
    'BOUND_LEDGER_UNVERIFIED',
    'BOUND_AWAITING_CONTROLLED_CANARY',
    'PUBLISHING_PROVEN',
}
print(
    f"COMMAND_CENTER_STATE_BRIDGE=PASS lanes=11/11 mcp_cli=online "
    f"publisher=online publisher_phase={p['phase']} cadence=60s receipts={len(s['latest_receipts'])}"
)
PY

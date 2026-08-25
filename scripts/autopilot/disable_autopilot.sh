#!/usr/bin/env bash
set -Eeuo pipefail

service_name="dominion-radah-autopilot.service"
timer_name="dominion-radah-autopilot.timer"
state_root="$HOME/.dominion/autopilot"
receipt_dir="$state_root/receipts"

mkdir -p "$receipt_dir"
chmod 700 "$state_root" "$receipt_dir"

sudo systemctl disable --now "$timer_name"
sudo systemctl stop "$service_name" >/dev/null 2>&1 || true

timer_active="$(sudo systemctl is-active "$timer_name" 2>/dev/null || true)"
timer_enabled="$(sudo systemctl is-enabled "$timer_name" 2>/dev/null || true)"
service_active="$(sudo systemctl is-active "$service_name" 2>/dev/null || true)"

[ "$timer_active" != "active" ]
[ "$timer_enabled" = "disabled" ]
[ "$service_active" != "active" ]

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
cat > "$receipt_dir/$stamp-founder-deactivation.json" <<EOF
{
  "schema": "radah-autopilot-control-receipt-v1",
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "action": "FOUNDER_DEACTIVATE_AUTOPILOT",
  "timer_active": "$timer_active",
  "timer_enabled": "$timer_enabled",
  "service_active": "$service_active",
  "external_actions_authorized": false,
  "result": "PASS"
}
EOF
chmod 600 "$receipt_dir/$stamp-founder-deactivation.json"

echo "RADAH_AUTOPILOT_DEACTIVATE=PASS timer_active=$timer_active timer_enabled=$timer_enabled service_active=$service_active"

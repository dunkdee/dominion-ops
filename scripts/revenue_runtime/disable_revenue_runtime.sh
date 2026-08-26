#!/usr/bin/env bash
set -euo pipefail

service_name="dominion-revenue-runtime.service"
eval_service="dominion-revenue-evaluator.service"
eval_timer="dominion-revenue-evaluator.timer"

sudo systemctl disable --now "$eval_timer" >/dev/null 2>&1 || true
sudo systemctl stop "$eval_service" >/dev/null 2>&1 || true
sudo systemctl stop "$service_name" >/dev/null 2>&1 || true

timer_state="$(systemctl is-active "$eval_timer" 2>/dev/null || true)"
service_state="$(systemctl is-active "$service_name" 2>/dev/null || true)"
[ "$timer_state" != "active" ]
[ "$service_state" != "active" ]
printf 'DOMINION_REVENUE_RUNTIME=DISABLED timer=%s service=%s\n' "$timer_state" "$service_state"

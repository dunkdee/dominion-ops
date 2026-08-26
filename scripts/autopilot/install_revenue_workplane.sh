#!/usr/bin/env bash
set -Eeuo pipefail

: "${ASSET_ROOT:?ASSET_ROOT is required}"
: "${RUN_ID:?RUN_ID is required}"

asset_root="$(cd "$ASSET_ROOT" && pwd -P)"
user_home="$HOME"
runtime_root="$user_home/.dominion/autopilot/runtime"
state_root="$user_home/.dominion/autopilot"
backup_root="$state_root/backups/revenue-workplane-$RUN_ID"
dropin_dir="/etc/systemd/system/dominion-radah-autopilot.service.d"
dropin_path="$dropin_dir/revenue-workplane.conf"
service="dominion-radah-autopilot.service"
timer="dominion-radah-autopilot.timer"
success=0

buddy_exec="$(systemctl show dominion-buddy-web.service -p ExecStart --value 2>/dev/null || true)"
buddy_python="$(printf '%s\n' "$buddy_exec" | sed -n 's/.*path=\([^ ;]*\).*/\1/p' | head -1)"
test -x "$buddy_python" || { echo 'REVENUE_WORKPLANE=HOLD reason=buddy_python_unavailable'; exit 20; }

test -f "$runtime_root/scripts/autopilot/lane_supervisor.py" || { echo 'REVENUE_WORKPLANE=HOLD reason=autopilot_runtime_missing'; exit 21; }
test "$(systemctl is-active "$timer")" = active || { echo 'REVENUE_WORKPLANE=HOLD reason=autopilot_timer_inactive'; exit 22; }
test "$(systemctl is-active dominion-revenue-runtime.service)" = active || { echo 'REVENUE_WORKPLANE=HOLD reason=revenue_runtime_inactive'; exit 23; }
test "$(systemctl is-active dominion-revenue-evaluator.timer)" = active || { echo 'REVENUE_WORKPLANE=HOLD reason=revenue_evaluator_inactive'; exit 24; }

mkdir -p "$backup_root"
chmod 700 "$backup_root"
for rel in \
  scripts/autopilot/revenue_workplane_supervisor.py \
  governance/radah_memshalah_autopilot_policy.json \
  governance/revenue_workplane.json \
  governance/lane_access_policy.json; do
  if [ -f "$runtime_root/$rel" ]; then
    mkdir -p "$backup_root/$(dirname "$rel")"
    cp -a "$runtime_root/$rel" "$backup_root/$rel"
  fi
done
if sudo test -f "$dropin_path"; then
  sudo cp -a "$dropin_path" "$backup_root/revenue-workplane.conf"
  sudo chown "$(id -un):$(id -gn)" "$backup_root/revenue-workplane.conf"
fi

rollback() {
  rc=$?
  [ "$success" -eq 1 ] && exit "$rc"
  trap - ERR INT TERM EXIT
  set +e
  echo "REVENUE_WORKPLANE_ROLLBACK=BEGIN rc=$rc"
  for rel in \
    scripts/autopilot/revenue_workplane_supervisor.py \
    governance/radah_memshalah_autopilot_policy.json \
    governance/revenue_workplane.json \
    governance/lane_access_policy.json; do
    if [ -f "$backup_root/$rel" ]; then
      mkdir -p "$runtime_root/$(dirname "$rel")"
      cp -a "$backup_root/$rel" "$runtime_root/$rel"
    else
      rm -f "$runtime_root/$rel"
    fi
  done
  if [ -f "$backup_root/revenue-workplane.conf" ]; then
    sudo install -m 644 "$backup_root/revenue-workplane.conf" "$dropin_path"
  else
    sudo rm -f "$dropin_path"
  fi
  sudo systemctl daemon-reload >/dev/null 2>&1 || true
  echo 'REVENUE_WORKPLANE_ROLLBACK=COMPLETE'
  exit "$rc"
}
trap rollback ERR INT TERM EXIT

install -m 700 "$asset_root/scripts/autopilot/revenue_workplane_supervisor.py" "$runtime_root/scripts/autopilot/revenue_workplane_supervisor.py"
install -m 600 "$asset_root/governance/radah_memshalah_autopilot_policy.json" "$runtime_root/governance/radah_memshalah_autopilot_policy.json"
install -m 600 "$asset_root/governance/revenue_workplane.json" "$runtime_root/governance/revenue_workplane.json"
install -m 600 "$asset_root/governance/lane_access_policy.json" "$runtime_root/governance/lane_access_policy.json"

"$buddy_python" -m py_compile "$runtime_root/scripts/autopilot/revenue_workplane_supervisor.py"

access="$(cd "$runtime_root/scripts/autopilot" && "$buddy_python" revenue_workplane_supervisor.py --inspect-lane-access)"
printf '%s\n' "$access"
printf '%s' "$access" | grep -q '"LANE_ACCESS": "PASS"'
printf '%s' "$access" | grep -q '"registered": 11'
printf '%s' "$access" | grep -q '"open": 11'
printf '%s' "$access" | grep -q '"all_registered_lanes_internal_open": true'

snapshot="$(cd "$runtime_root/scripts/autopilot" && "$buddy_python" revenue_workplane_supervisor.py --inspect-workplane)"
printf '%s\n' "$snapshot"
printf '%s' "$snapshot" | grep -q '"available": true'
printf '%s' "$snapshot" | grep -q '"experiment_id": "voltedge-speaker-offer-v1"'
printf '%s' "$snapshot" | grep -q '"constraint": "QUALIFIED_TRAFFIC"\|"constraint": "MESSAGE_MATCH_OR_CTA"\|"constraint": "PRODUCT_OR_CHECKOUT_FRICTION"\|"constraint": "STATISTICAL_EVIDENCE"'

tmp="$(mktemp)"
cat > "$tmp" <<EOF
[Service]
ExecStart=
ExecStart=$buddy_python $runtime_root/scripts/autopilot/revenue_workplane_supervisor.py --execute --state-dir $state_root
EOF
sudo install -d -m 755 "$dropin_dir"
sudo install -m 644 "$tmp" "$dropin_path"
rm -f "$tmp"
sudo systemctl daemon-reload

resolved="$(systemctl show "$service" -p ExecStart --value)"
printf '%s\n' "$resolved" | grep -q 'revenue_workplane_supervisor.py'

# Prove all 11 registered lanes remain schedulable for internal work.
for lane in \
  commerce_fulfillment kdp_publishing analytics_services digital_products \
  services_lead_generation content_traffic surplus trading \
  intelligence_orchestration governance_legal infrastructure; do
  plan="$(cd "$runtime_root/scripts/autopilot" && RADAH_AUTOPILOT_ENABLED=0 "$buddy_python" revenue_workplane_supervisor.py --plan-only --lane "$lane" --state-dir "$state_root")"
  printf '%s' "$plan" | grep -q "\"lane\": \"$lane\""
  printf '%s' "$plan" | grep -q '"lane_internal_open": true'
  printf '%s' "$plan" | grep -q '"all_registered_lanes_internal_open": true'
  printf '%s' "$plan" | grep -q "RADAH_AUTOPILOT=PLANNED lane=$lane bounded_cycle=true"
done

# Revenue-bound lane must also receive current runtime evidence.
commerce="$(cd "$runtime_root/scripts/autopilot" && RADAH_AUTOPILOT_ENABLED=0 "$buddy_python" revenue_workplane_supervisor.py --plan-only --lane commerce_fulfillment --state-dir "$state_root")"
printf '%s' "$commerce" | grep -q '"revenue_workplane"'
printf '%s' "$commerce" | grep -q '"experiment_id": "voltedge-speaker-offer-v1"'

# Existing recurring supervisor remains armed; no unrelated service restart.
test "$(systemctl is-active "$timer")" = active
test "$(systemctl is-enabled "$timer")" = enabled

echo 'RADAH_ALL_LANES=OPEN count=11 internal=true scheduler_eligible=true'
echo 'REVENUE_WORKPLANE=BOUND lane=commerce_fulfillment support=content_traffic,intelligence_orchestration,infrastructure'
echo 'REVENUE_WORKPLANE_RUNTIME=PASS service=dominion-revenue-runtime.service evaluator=10m'
echo 'REVENUE_WORKPLANE_AUTOPILOT=PASS cadence=30m'
echo 'REVENUE_WORKPLANE_EXPERIMENT=PASS id=voltedge-speaker-offer-v1'

success=1
trap - ERR INT TERM EXIT
rm -rf "$backup_root"
echo 'REVENUE_WORKPLANE_DEPLOY=PASS'

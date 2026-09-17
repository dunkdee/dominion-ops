#!/usr/bin/env bash
set -Eeuo pipefail

: "${RUN_ID:?RUN_ID is required}"
: "${PRODUCT_ID:?PRODUCT_ID is required}"
: "${TARGET_URL:?TARGET_URL is required}"

api="http://127.0.0.1:8790"
env_file="$HOME/dominion-ops/.env"
exp_id="gate-e-live-${RUN_ID}"
public_origin="https://dominionhealing.org"
work="$(mktemp -d)"
operator_token=""
activated=0
completed=0

cleanup() {
  rc=$?
  set +e
  if [ "$completed" -ne 1 ] && [ "$activated" -eq 1 ] && [ -n "$operator_token" ]; then
    curl -fsS -X POST -H "X-Operator-Token: $operator_token" \
      "$api/control/experiments/$exp_id/pause" >/dev/null 2>&1 || true
  fi
  rm -rf "$work"
  exit "$rc"
}
trap cleanup EXIT INT TERM

systemctl is-active --quiet dominion-revenue-runtime.service
systemctl is-active --quiet dominion-revenue-evaluator.timer
curl -fsS "$api/health" > "$work/health.json"
python3 - "$work/health.json" <<'PY'
import json,sys
obj=json.load(open(sys.argv[1], encoding='utf-8'))
assert obj.get('status') == 'ok', obj
assert obj.get('execution_enabled') is False, obj
assert obj.get('automatic_price_changes') is False, obj
assert obj.get('automatic_paid_spend') is False, obj
print('GATE_E_LIVE_RUNTIME_HEALTH=PASS execution_enabled=false automatic_price_changes=false automatic_paid_spend=false')
PY

python3 - "$TARGET_URL" <<'PY'
from urllib.parse import urlparse
import sys
u=urlparse(sys.argv[1])
assert u.scheme == 'https', u
assert u.hostname in {'voltedgegoods.com','www.voltedgegoods.com'}, u
assert u.path.startswith('/product-page/'), u
print('GATE_E_LIVE_TARGET_BOUNDARY=PASS host=www.voltedgegoods.com catalog_path=true')
PY

operator_token="$(python3 - "$env_file" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
if not p.is_file():
    raise SystemExit(2)
for raw in p.read_text(encoding='utf-8').splitlines():
    line=raw.strip()
    if not line or line.startswith('#') or '=' not in line:
        continue
    k,v=line.split('=',1)
    if k.strip() == 'WIX_AGENT_OPERATOR_TOKEN':
        v=v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in {'"', "'"}:
            v=v[1:-1]
        print(v)
        break
PY
)"
test -n "$operator_token"
auth=(-H "X-Operator-Token: $operator_token")

python3 - "$work/create.json" "$exp_id" "$PRODUCT_ID" "$TARGET_URL" <<'PY'
import json,sys
out,exp_id,product_id,target=sys.argv[1:]
payload={
  'id': exp_id,
  'name': 'Gate E one-time live attribution canary',
  'product_id': product_id,
  'target_url': target,
  'success_event': 'purchase',
  'wix_field': 'plainDescription',
  'treatment_pct': 0,
  'auto_promote': False,
  'control': {
    'headline': 'VoltEdge verification route',
    'body_text': 'One-time governed attribution canary.',
    'cta_text': 'Continue',
    'wix_value': '<p>One-time governed attribution canary.</p>'
  },
  'treatment': {
    'headline': 'VoltEdge verification route',
    'body_text': 'One-time governed attribution canary.',
    'cta_text': 'Continue',
    'wix_value': '<p>One-time governed attribution canary.</p>'
  }
}
with open(out,'w',encoding='utf-8') as f:
    json.dump(payload,f,separators=(',',':'))
PY

curl -fsS -X POST "${auth[@]}" -H 'Content-Type: application/json' \
  --data-binary "@$work/create.json" "$api/control/experiments" > "$work/created.json"
curl -fsS -X POST "${auth[@]}" "$api/control/experiments/$exp_id/activate" > "$work/activated.json"
activated=1

curl -fsS "${auth[@]}" "$api/control/experiments/$exp_id" > "$work/status.json"
python3 - "$work/status.json" "$exp_id" "$PRODUCT_ID" <<'PY'
import json,sys
obj=json.load(open(sys.argv[1], encoding='utf-8'))
exp_id,product_id=sys.argv[2:]
exp=obj['experiment']
assert exp['id'] == exp_id, obj
assert exp['product_id'] == product_id, obj
assert exp['status'] == 'active', obj
assert int(exp['treatment_pct']) == 0, obj
assert exp['auto_promote'] is False, obj
metrics=obj['metrics']
for variant in ('control','treatment'):
    assert int(metrics[variant].get('conversions',0)) == 0, metrics
    assert int(metrics[variant].get('gross_revenue_cents',0)) == 0, metrics
    assert int(metrics[variant].get('refund_cents',0)) == 0, metrics
print('GATE_E_LIVE_EXPERIMENT_ACTIVE=PASS treatment_pct=0 auto_promote=false preexisting_conversions=0')
PY

# Deliberately do not request /r/<experiment_id> here. The first public visit and
# click must come from the real checkout browser so the evaluator has one unique
# visitor candidate and cannot attribute a synthetic workflow click.
public_route="$public_origin/r/$exp_id"
echo "GATE_E_LIVE_CANARY_PREP=PASS experiment_id=$exp_id product_id=$PRODUCT_ID public_route=$public_route automated_spend=false price_mutation=false synthetic_click=false"

completed=1
trap - EXIT INT TERM
rm -rf "$work"

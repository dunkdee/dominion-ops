#!/usr/bin/env bash
set -Eeuo pipefail

: "${RUN_ID:?RUN_ID is required}"
: "${PRODUCT_ID:?PRODUCT_ID is required}"
: "${TARGET_URL:?TARGET_URL is required}"

api="http://127.0.0.1:8790"
state_root="$HOME/.dominion/revenue-runtime"
env_file="$HOME/dominion-ops/.env"
exp_id="gate-e-zero-spend-${RUN_ID}"
work="$(mktemp -d)"
paused=0
operator_token=""

cleanup() {
  rc=$?
  set +e
  if [ -n "$operator_token" ] && [ "$paused" -ne 1 ]; then
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
# Commercial Release 1.0 intentionally keeps automatic CRO disabled. This
# proof exercises only an owner-authorized, temporary manual experiment and
# must not turn the production kill switch on.
assert obj.get('execution_enabled') is False, obj
assert obj.get('automatic_price_changes') is False, obj
assert obj.get('automatic_paid_spend') is False, obj
print('REVENUE_RUNTIME_HEALTH_PROOF=PASS execution_enabled=false auto_cro=false price_automation=false paid_spend=false')
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
        if len(v) >= 2 and v[0] == v[-1] and v[0] in {'\"', "'"}:
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
  'name': 'Gate E zero-spend source/campaign proof',
  'product_id': product_id,
  'target_url': target,
  'success_event': 'purchase',
  'wix_field': 'plainDescription',
  'treatment_pct': 0,
  'auto_promote': False,
  'control': {
    'headline': 'VoltEdge verification route',
    'body_text': 'Governed zero-spend attribution verification.',
    'cta_text': 'Continue',
    'wix_value': '<p>Governed zero-spend attribution verification.</p>'
  },
  'treatment': {
    'headline': 'VoltEdge verification route',
    'body_text': 'Governed zero-spend attribution verification.',
    'cta_text': 'Continue',
    'wix_value': '<p>Governed zero-spend attribution verification.</p>'
  }
}
with open(out,'w',encoding='utf-8') as f:
    json.dump(payload,f,separators=(',',':'))
PY

curl -fsS -X POST "${auth[@]}" -H 'Content-Type: application/json' \
  --data-binary "@$work/create.json" "$api/control/experiments" > "$work/created.json"
curl -fsS -X POST "${auth[@]}" "$api/control/experiments/$exp_id/activate" > "$work/activated.json"

curl -fsS -D "$work/offer.headers" -c "$work/cookies.txt" \
  "$api/r/$exp_id" -o "$work/offer.html"

click_path="$(python3 - "$work/offer.html" "$exp_id" <<'PY'
import html,re,sys
text=open(sys.argv[1], encoding='utf-8').read()
exp=sys.argv[2]
m=re.search(r'href="([^"]+)"', text)
assert m, 'click href missing'
href=html.unescape(m.group(1))
assert href.startswith(f'/r/{exp}/click?'), href
print(href)
PY
)"

# Intentionally do not follow the 302: prove signed routing/UTM generation without creating an external storefront visit.
curl -sS -D "$work/click.headers" -o /dev/null -b "$work/cookies.txt" \
  "$api$click_path"

location="$(python3 - "$work/click.headers" <<'PY'
import sys
for raw in open(sys.argv[1], encoding='utf-8', errors='replace'):
    if raw.lower().startswith('location:'):
        print(raw.split(':',1)[1].strip())
        break
PY
)"
test -n "$location"

python3 - "$location" "$exp_id" "$TARGET_URL" <<'PY'
from urllib.parse import parse_qs,urlparse
import sys
location,exp_id,target=sys.argv[1:]
loc=urlparse(location)
tgt=urlparse(target)
assert loc.scheme == 'https', location
assert loc.hostname == tgt.hostname, (loc.hostname,tgt.hostname)
assert loc.path == tgt.path, (loc.path,tgt.path)
q=parse_qs(loc.query)
assert q.get('utm_source') == ['dominion_revenue'], q
assert q.get('utm_medium') == ['experiment'], q
assert q.get('utm_campaign') == [exp_id], q
assert q.get('utm_content') == ['control'], q
print(f'SOURCE_CAMPAIGN_ROUTER_PROOF=PASS experiment_id={exp_id} utm_source=dominion_revenue utm_medium=experiment utm_content=control')
PY

python3 - "$state_root/revenue.db" "$exp_id" <<'PY'
import sqlite3,sys
path,exp=sys.argv[1:]
db=sqlite3.connect(f'file:{path}?mode=ro', uri=True)
rows=dict(db.execute('SELECT event_type, COUNT(*) FROM events WHERE experiment_id=? GROUP BY event_type',(exp,)).fetchall())
imp=int(rows.get('impression',0)); clk=int(rows.get('click',0)); pur=int(rows.get('purchase',0)); ref=int(rows.get('refund',0))
assert imp >= 1, rows
assert clk >= 1, rows
assert pur == 0, rows
assert ref == 0, rows
print(f'GATE_E_EVENT_LEDGER_PROOF=PASS experiment_id={exp} impression_events={imp} click_events={clk} purchase_events=0 refund_events=0')
PY

curl -fsS -X POST "${auth[@]}" "$api/control/experiments/$exp_id/pause" > "$work/paused.json"
paused=1
curl -fsS "${auth[@]}" "$api/control/experiments/$exp_id" > "$work/status.json"
python3 - "$work/status.json" "$exp_id" <<'PY'
import json,sys
obj=json.load(open(sys.argv[1], encoding='utf-8'))
exp=sys.argv[2]
assert obj['experiment']['id'] == exp, obj
assert obj['experiment']['status'] == 'paused', obj
metrics=obj['metrics']
for variant in ('control','treatment'):
    assert int(metrics[variant].get('revenue_cents',0)) == 0, metrics
    assert int(metrics[variant].get('refund_cents',0)) == 0, metrics
print(f'GATE_E_ROLLBACK_PROOF=PASS experiment_id={exp} final_state=paused net_revenue_cents=0')
PY

echo "GATE_E_ZERO_SPEND_RUNTIME_PROOF=PASS experiment_id=$exp_id product_id=$PRODUCT_ID spend_cents=0 purchase_events=0 refund_events=0 external_redirect_followed=false auto_cro_enabled=false"
trap - EXIT INT TERM
rm -rf "$work"

#!/usr/bin/env bash
set -euo pipefail

: "${DEPLOY_SHA:?DEPLOY_SHA is required}"
: "${EXPECTED_CANDIDATE_COUNT:?EXPECTED_CANDIDATE_COUNT is required}"
: "${MAX_CANDIDATE_COUNT:?MAX_CANDIDATE_COUNT is required}"

repo="$HOME/dominion-ops"
target="$HOME/email_drip/email_drip.py"
service="dominion-email-drip.service"
env_file="$HOME/.env"
live_changed=0

[[ "$EXPECTED_CANDIDATE_COUNT" =~ ^[0-9]+$ ]] || { echo "EMAIL_DRIP_LIVE=FAIL reason=invalid_expected_count"; exit 1; }
[[ "$MAX_CANDIDATE_COUNT" =~ ^[0-9]+$ ]] || { echo "EMAIL_DRIP_LIVE=FAIL reason=invalid_max_count"; exit 1; }
[ "$EXPECTED_CANDIDATE_COUNT" -le "$MAX_CANDIDATE_COUNT" ] || { echo "EMAIL_DRIP_LIVE=FAIL reason=expected_exceeds_max"; exit 1; }
[ "$MAX_CANDIDATE_COUNT" -le 10 ] || { echo "EMAIL_DRIP_LIVE=FAIL reason=max_exceeds_safety_cap"; exit 1; }

cd "$repo"
test "$(git rev-parse HEAD)" = "$DEPLOY_SHA" || { echo "EMAIL_DRIP_LIVE=FAIL reason=vm_sha_mismatch"; exit 1; }
repo_sha="$(sha256sum services/email_drip/email_drip.py | awk '{print $1}')"
prod_sha="$(sha256sum "$target" | awk '{print $1}')"
test "$repo_sha" = "$prod_sha" || { echo "EMAIL_DRIP_LIVE=FAIL reason=production_source_drift"; exit 1; }

contain() {
  set +e
  sudo python3 scripts/set_email_drip_runtime.py hold --env-file "$env_file" --expect either >/dev/null 2>&1
  sudo systemctl restart "$service" >/dev/null 2>&1
  sudo systemctl is-active --quiet "$service"
  curl -fsS --max-time 10 http://127.0.0.1:8099/health | python3 -c 'import json,sys; j=json.load(sys.stdin); assert j["send_mode"]=="hold"' >/dev/null 2>&1
  echo "EMAIL_DRIP_AUTO_CONTAIN=PASS mode=hold"
}

on_error() {
  rc=$?
  if [ "$live_changed" -eq 1 ]; then contain || true; fi
  exit "$rc"
}
trap on_error ERR

sudo systemctl is-active --quiet "$service"
health="$(curl -fsS --max-time 10 http://127.0.0.1:8099/health)"
python3 - "$health" <<'PY'
import json,sys
j=json.loads(sys.argv[1])
assert j['send_mode']=='hold'
PY

main_pid="$(sudo systemctl show -p MainPID --value "$service")"
python_bin="$(sudo readlink -f "/proc/$main_pid/exe")"
owner="$(stat -c '%U' "$target")"

preflight="$({ sudo -u "$owner" env DRIP_SEND_MODE=hold DRIP_LIVE_PREFLIGHT_OK=false "$python_bin" - "$target" <<'PY'
import importlib.util,json,sys
from datetime import datetime,timezone
from pathlib import Path
path=Path(sys.argv[1])
spec=importlib.util.spec_from_file_location('dominion_email_drip_activation_preflight', path)
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
r=m._build_preflight_report(now=datetime.now(timezone.utc)); s=m.drip_status()
out={
 'candidate_count':r['candidate_count'],
 'free_audit_candidate_count':r['free_audit_candidate_count'],
 'status_counts':r['status_counts'],
 'smtp_configured':bool(s['smtp_configured']),
 'before_total_emails_sent':int(s['total_emails_sent']),
 'candidates':[{'book':x['book'],'step':x['step']} for x in r['candidates']],
}
print(json.dumps(out,separators=(',',':'),sort_keys=True))
PY
} )"
python3 - "$preflight" "$EXPECTED_CANDIDATE_COUNT" "$MAX_CANDIDATE_COUNT" <<'PY'
import json,sys
p=json.loads(sys.argv[1]); expected=int(sys.argv[2]); maximum=int(sys.argv[3])
assert p['candidate_count']==expected
assert p['candidate_count']<=maximum
assert p['free_audit_candidate_count']==0
assert p['smtp_configured'] is True
assert p['status_counts'].get('suppression_error',0)==0
assert p['status_counts'].get('send_reconciliation_required',0)==0
assert p['status_counts'].get('invalid_send_history',0)==0
print('EMAIL_DRIP_LIVE_PREFLIGHT=PASS '+json.dumps({k:p[k] for k in ('candidate_count','candidates','status_counts')},separators=(',',':'),sort_keys=True))
PY
before_total="$(python3 - "$preflight" -c '' 2>/dev/null || true)"
before_total="$(python3 - "$preflight" <<'PY'
import json,sys
print(json.loads(sys.argv[1])['before_total_emails_sent'])
PY
)"

sudo python3 scripts/set_email_drip_runtime.py live --env-file "$env_file" --expect hold
live_changed=1
sudo systemctl restart "$service"
sudo systemctl is-active --quiet "$service"
ss -tlnp | grep -q ':8099 '
health="$(curl -fsS --max-time 10 http://127.0.0.1:8099/health)"
python3 - "$health" <<'PY'
import json,sys
j=json.loads(sys.argv[1])
assert j['send_mode']=='live'
assert j['configured_send_mode']=='live'
assert j['live_start_authorized'] is True
assert j['live_preflight_ok'] is True
print('EMAIL_DRIP_LIVE_HEALTH=PASS')
PY

sleep 12
after_status="$(curl -fsS --max-time 10 http://127.0.0.1:8099/api/drip-status)"
python3 - "$after_status" "$before_total" "$EXPECTED_CANDIDATE_COUNT" <<'PY'
import json,sys
j=json.loads(sys.argv[1]); before=int(sys.argv[2]); expected=int(sys.argv[3])
after=int(j['total_emails_sent']); delta=after-before
assert delta==expected, f'expected_send_delta={expected} actual={delta}'
assert j['smtp_configured'] is True
print(f'EMAIL_DRIP_FIRST_CYCLE_ACCEPTANCE=PASS expected={expected} actual={delta} total={after}')
PY

# The next planner state must have no immediately due candidate after the accepted startup cycle.
postflight="$({ sudo -u "$owner" env DRIP_SEND_MODE=hold DRIP_LIVE_PREFLIGHT_OK=false "$python_bin" - "$target" <<'PY'
import importlib.util,json,sys
from datetime import datetime,timezone
from pathlib import Path
path=Path(sys.argv[1]); spec=importlib.util.spec_from_file_location('dominion_email_drip_postflight',path)
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
r=m._build_preflight_report(now=datetime.now(timezone.utc))
print(json.dumps({'candidate_count':r['candidate_count'],'status_counts':r['status_counts'],'free_audit_candidate_count':r['free_audit_candidate_count']},separators=(',',':'),sort_keys=True))
PY
} )"
python3 - "$postflight" <<'PY'
import json,sys
p=json.loads(sys.argv[1])
assert p['candidate_count']==0
assert p['free_audit_candidate_count']==0
print('EMAIL_DRIP_POSTFLIGHT=PASS '+json.dumps(p,separators=(',',':'),sort_keys=True))
PY

trap - ERR
printf 'EMAIL_DRIP_LIVE=PASS sha=%s expected_first_cycle=%s service=active port=8099 mode=live\n' "$DEPLOY_SHA" "$EXPECTED_CANDIDATE_COUNT"

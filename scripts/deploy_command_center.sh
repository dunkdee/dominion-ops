#!/usr/bin/env bash
set -Eeuo pipefail

REPO_DIR="${REPO_DIR:-$HOME/dominion-ops}"
DOMAIN="${COMMAND_CENTER_DOMAIN:-command.dominionhealing.org}"
ENV_FILE="${COMMAND_CENTER_ENV_FILE:-$HOME/.config/dominion/command-center.env}"
BRANCH="${COMMAND_CENTER_BRANCH:-main}"
EXPECTED_SHA="${EXPECTED_SHA:-}"
CADDYFILE="${CADDYFILE:-/etc/caddy/Caddyfile}"
ENV_EXAMPLE="$REPO_DIR/config/command-center.env.example"
STATE_ROOT="$HOME/.dominion/command-center"
STATE_FILE="$STATE_ROOT/runtime-state.json"
RECEIPTS="$STATE_ROOT/receipts"

cd "$REPO_DIR"
git fetch origin "$BRANCH"
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"
actual_sha="$(git rev-parse HEAD)"
if [[ -n "$EXPECTED_SHA" && "$actual_sha" != "$EXPECTED_SHA" ]]; then
  echo "Command Center release mismatch: expected=$EXPECTED_SHA actual=$actual_sha" >&2
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  test -f "$ENV_EXAMPLE"
  install -d -m 700 "$(dirname "$ENV_FILE")"
  install -m 600 "$ENV_EXAMPLE" "$ENV_FILE"
  echo "DOMINION_COMMAND_CENTER_ENV=CREATED baseline=$ENV_FILE"
fi
chmod 600 "$ENV_FILE"
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

vault="$(docker inspect obsidian-remote --format '{{range .Mounts}}{{if eq .Destination "/vaults/Dominion"}}{{.Source}}{{end}}{{end}}')"
test -n "$vault"
test -d "$vault/Dominion-Command-Center"
export VAULT_PATH="$vault"
export COMMAND_CENTER_RUNTIME_DIR="$STATE_ROOT"

# Install the canonical state bridge before the web surface. The first snapshot
# may truthfully show command_center offline; it is refreshed again after boot.
RUN_SHA="$actual_sha" REPO_DIR="$REPO_DIR" bash scripts/install_command_center_state_bridge.sh

test -s "$STATE_FILE"
python3 - "$STATE_FILE" "$actual_sha" <<'PY'
import json,sys
s=json.load(open(sys.argv[1],encoding='utf-8'))
assert s['schema']=='dominion-command-center-runtime-state-v2', s.get('schema')
assert s['release_sha']==sys.argv[2], (s.get('release_sha'),sys.argv[2])
assert s['lanes']['registered']==11 and s['lanes']['open']==11 and s['lanes']['all_open'] is True
assert s['revenue']['connected'] is True, s['revenue']
assert s['revenue']['active_experiment_count'] >= 1, s['revenue']
assert s['autopilot']['connected'] is True, s['autopilot']
assert s['autopilot']['timer']['active'] is True, s['autopilot']['timer']
assert s['founder_holds'], 'Founder holds unavailable'
print('COMMAND_CENTER_PREBOOT_TRUTH=PASS lanes=11/11 revenue=live autopilot=connected')
PY

# Docker build now contains an image-level import gate, so packaging drift fails
# during build rather than after the container enters production.
docker compose --env-file "$ENV_FILE" -f docker-compose.command-center.yml up -d --build

ready=0
for _ in $(seq 1 45); do
  if curl -fsS --max-time 5 http://127.0.0.1:8091/health >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 2
done
[[ "$ready" -eq 1 ]] || {
  docker logs --tail 160 dominion-command-center 2>&1 || true
  echo "Dominion Command Center failed local health gate" >&2
  exit 1
}

# Refresh after the container is healthy so web and Obsidian see the same
# post-boot service state.
sudo systemctl start dominion-command-center-state.service
test "$(sudo systemctl show dominion-command-center-state.service -p Result --value)" = success

daily_state="$vault/Dominion-Command-Center/14-Daily-State.md"
test -s "$daily_state"
grep -Fq '# Live Daily State' "$daily_state"
grep -Fq "$actual_sha" "$daily_state"
grep -Fq 'Current production state requires timestamped runtime receipts.' "$daily_state"

STATUS_JSON="$(curl -fsS http://127.0.0.1:8091/api/status)"
ACCEPTANCE="$(python3 - "$STATUS_JSON" "$actual_sha" <<'PY'
import json,sys
s=json.loads(sys.argv[1]); expected=sys.argv[2]
truth=s.get('truth',{})
assert truth.get('connected') is True, truth
assert truth.get('release_sha')==expected, (truth.get('release_sha'),expected)
summary=s.get('lane_summary',{})
assert summary=={'open':11,'registered':11,'all_open':True}, summary
r=s.get('revenue',{})
assert r.get('runtime_connected') is True, r
assert int(r.get('active_experiment_count',0)) >= 1, r
assert r.get('constraint') not in (None,'RUNTIME_STATE_UNAVAILABLE','NO_ACTIVE_EXPERIMENT'), r
ap=s.get('autopilot',{})
assert ap.get('connected') is True, ap
assert ap.get('timer',{}).get('active') is True, ap
systems=s.get('systems',{})
for key in ('revenue_runtime','revenue_evaluator','radah_autopilot','obsidian'):
    assert systems.get(key)=='online', (key,systems.get(key))
assert len(s.get('founder_holds',[])) >= 5, s.get('founder_holds')
assert s.get('latest_receipts'), 'runtime receipt index empty'
m=r.get('metrics',{})
print(' '.join([
    'truth=live','lanes=11/11',f"constraint={r.get('constraint')}",
    f"experiments={r.get('active_experiment_count')}",f"visitors={m.get('visitors')}",
    f"clicks={m.get('clicks')}",f"purchases={m.get('purchases')}",
    f"revenue_usd={m.get('revenue_usd')}",f"receipts={len(s.get('latest_receipts',[]))}"
]))
PY
)"
echo "DOMINION_COMMAND_CENTER_LIVE_STATE=$ACCEPTANCE"

if [[ ! -f "$CADDYFILE" ]]; then
  echo "Caddyfile not found: $CADDYFILE" >&2
  exit 1
fi
if ! sudo grep -Fq "$DOMAIN" "$CADDYFILE"; then
  cat <<EOF | sudo tee -a "$CADDYFILE" >/dev/null

$DOMAIN {
  encode gzip zstd
  reverse_proxy 127.0.0.1:8091
}
EOF
fi
sudo caddy validate --config "$CADDYFILE" >/dev/null
sudo systemctl reload caddy
sudo systemctl is-active --quiet caddy

if ! getent ahostsv4 "$DOMAIN" >/dev/null 2>&1; then
  echo "Command Center DNS does not resolve for $DOMAIN" >&2
  exit 1
fi
curl -fsS --max-time 20 "https://$DOMAIN/health" >/dev/null
PUBLIC_STATUS="$(curl -fsS --max-time 20 "https://$DOMAIN/api/status")"
python3 - "$PUBLIC_STATUS" "$actual_sha" <<'PY'
import json,sys
s=json.loads(sys.argv[1]); expected=sys.argv[2]
assert s['truth']['connected'] is True
assert s['truth']['release_sha']==expected
assert s['lane_summary']['all_open'] is True
assert s['revenue']['runtime_connected'] is True
print('COMMAND_CENTER_PUBLIC_TRUTH=PASS')
PY

# Record this successful build in the same governed receipt tree that the
# Command Center indexes. No secrets or raw receipt bodies are exposed by API.
mkdir -p "$RECEIPTS"
chmod 700 "$STATE_ROOT" "$RECEIPTS"
receipt_stamp="$(date -u +%Y%m%dT%H%M%SZ)"
receipt="$RECEIPTS/${receipt_stamp}-command-center-${actual_sha:0:12}.json"
RUN_ID_VALUE="${RUN_ID:-unknown}" DOMAIN_VALUE="$DOMAIN" ACCEPTANCE_VALUE="$ACCEPTANCE" python3 - "$receipt" "$actual_sha" <<'PY'
import json,os,sys,tempfile
from datetime import datetime,timezone
from pathlib import Path
path=Path(sys.argv[1]); path.parent.mkdir(parents=True,exist_ok=True)
data={
  'schema':'dominion-command-center-build-receipt-v1',
  'component':'dominion-command-center',
  'status':'PASS',
  'release_sha':sys.argv[2],
  'run_id':os.environ.get('RUN_ID_VALUE','unknown'),
  'public_endpoint':'https://'+os.environ['DOMAIN_VALUE'],
  'acceptance':os.environ.get('ACCEPTANCE_VALUE',''),
  'observed_at':datetime.now(timezone.utc).isoformat(),
}
fd,tmp=tempfile.mkstemp(prefix='.receipt.',dir=str(path.parent))
try:
  with os.fdopen(fd,'w',encoding='utf-8') as h:
    json.dump(data,h,indent=2,sort_keys=True); h.write('\n'); h.flush(); os.fsync(h.fileno())
  os.chmod(tmp,0o600); os.replace(tmp,path)
finally:
  if os.path.exists(tmp): os.unlink(tmp)
PY
chmod 600 "$receipt"

# Re-index after the build receipt lands and prove Obsidian + web both advance.
sudo systemctl start dominion-command-center-state.service
FINAL_STATUS="$(curl -fsS http://127.0.0.1:8091/api/status)"
python3 - "$FINAL_STATUS" "$(basename "$receipt")" <<'PY'
import json,sys
s=json.loads(sys.argv[1]); name=sys.argv[2]
assert any(x.get('name')==name for x in s.get('latest_receipts',[])), (name,s.get('latest_receipts'))
print('COMMAND_CENTER_BUILD_RECEIPT=PASS indexed=true')
PY
grep -Fq "$(basename "$receipt")" "$daily_state"

echo 'DOMINION_COMMAND_CENTER=PASS'
echo "release_sha=$actual_sha"
echo 'lanes=11/11'
echo "live_state=$ACCEPTANCE"
echo 'truth_bridge=active cadence=60s'
echo "obsidian_daily_state=$daily_state"
echo 'local_endpoint=http://127.0.0.1:8091'
echo "public_endpoint=https://$DOMAIN"
echo 'public_state=online'

#!/usr/bin/env bash
set -Eeuo pipefail

REPO_DIR="${REPO_DIR:-$HOME/dominion-ops}"
DOMAIN="${COMMAND_CENTER_DOMAIN:-command.dominionhealing.org}"
VAULT_HOST="${VAULT_HOST:-vault.dominionhealing.org}"
ENV_FILE="${COMMAND_CENTER_ENV_FILE:-$HOME/.config/dominion/command-center.env}"
BRANCH="${COMMAND_CENTER_BRANCH:-main}"
EXPECTED_SHA="${EXPECTED_SHA:-}"
CADDYFILE="${CADDYFILE:-/etc/caddy/Caddyfile}"
ENV_EXAMPLE="$REPO_DIR/config/command-center.env.example"
STATE_ROOT="$HOME/.dominion/command-center"
STATE_FILE="$STATE_ROOT/runtime-state.json"
RECEIPTS="$STATE_ROOT/receipts"

cd "$REPO_DIR"
git fetch origin "$BRANCH"; git checkout "$BRANCH"; git pull --ff-only origin "$BRANCH"
actual_sha="$(git rev-parse HEAD)"
if [[ -n "$EXPECTED_SHA" && "$actual_sha" != "$EXPECTED_SHA" ]]; then echo "Command Center release mismatch: expected=$EXPECTED_SHA actual=$actual_sha" >&2; exit 1; fi

if [[ ! -f "$ENV_FILE" ]]; then
  test -f "$ENV_EXAMPLE"; install -d -m 700 "$(dirname "$ENV_FILE")"; install -m 600 "$ENV_EXAMPLE" "$ENV_FILE"
  echo "DOMINION_COMMAND_CENTER_ENV=CREATED baseline=$ENV_FILE"
fi
chmod 600 "$ENV_FILE"; set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

vault="$(docker inspect obsidian-remote --format '{{range .Mounts}}{{if eq .Destination "/vaults/Dominion"}}{{.Source}}{{end}}{{end}}')"
test -n "$vault"; test -d "$vault/Dominion-Command-Center"
export VAULT_PATH="$vault" COMMAND_CENTER_RUNTIME_DIR="$STATE_ROOT"

# One canonical host snapshot feeds both the web cockpit and Obsidian.
RUN_SHA="$actual_sha" REPO_DIR="$REPO_DIR" bash scripts/install_command_center_state_bridge.sh
test -s "$STATE_FILE"
python3 - "$STATE_FILE" "$actual_sha" <<'PY'
import json,sys
s=json.load(open(sys.argv[1],encoding='utf-8'))
assert s['schema']=='dominion-command-center-runtime-state-v2'
assert s['release_sha']==sys.argv[2]
assert s['lanes']['registered']==11 and s['lanes']['open']==11 and s['lanes']['all_open'] is True
assert s['revenue']['connected'] is True and s['revenue']['active_experiment_count'] >= 1, s['revenue']
assert s['autopilot']['connected'] is True and s['autopilot']['timer']['active'] is True, s['autopilot']
assert len(s['founder_holds']) >= 5, s['founder_holds']
print('COMMAND_CENTER_PREBOOT_TRUTH=PASS lanes=11/11 revenue=live autopilot=connected')
PY

# The Dockerfile contains an image-level import test, so missing modules fail here.
docker compose --env-file "$ENV_FILE" -f docker-compose.command-center.yml up -d --build
ready=0
for _ in $(seq 1 45); do curl -fsS --max-time 5 http://127.0.0.1:8091/health >/dev/null 2>&1 && { ready=1; break; }; sleep 2; done
[[ "$ready" -eq 1 ]] || { docker logs --tail 160 dominion-command-center 2>&1 || true; echo "Dominion Command Center failed local health gate" >&2; exit 1; }

# Refresh after boot so both surfaces report the same post-boot service state.
sudo systemctl start dominion-command-center-state.service
test "$(sudo systemctl show dominion-command-center-state.service -p Result --value)" = success

daily_state="$vault/Dominion-Command-Center/14-Daily-State.md"
test -s "$daily_state"; grep -Fq '# Live Daily State' "$daily_state"; grep -Fq "$actual_sha" "$daily_state"; grep -Fq 'Current production state requires timestamped runtime receipts.' "$daily_state"

STATUS_JSON="$(curl -fsS http://127.0.0.1:8091/api/status)"
ACCEPTANCE="$(python3 - "$STATUS_JSON" "$actual_sha" <<'PY'
import json,sys
s=json.loads(sys.argv[1]); expected=sys.argv[2]
truth=s.get('truth',{}); assert truth.get('connected') is True and truth.get('release_sha')==expected, truth
summary=s.get('lane_summary',{}); assert summary=={'open':11,'registered':11,'all_open':True}, summary
r=s.get('revenue',{}); assert r.get('runtime_connected') is True and int(r.get('active_experiment_count',0))>=1, r
assert r.get('constraint') not in (None,'RUNTIME_STATE_UNAVAILABLE','NO_ACTIVE_EXPERIMENT'), r
ap=s.get('autopilot',{}); assert ap.get('connected') is True and ap.get('timer',{}).get('active') is True, ap
systems=s.get('systems',{})
for key in ('revenue_runtime','revenue_evaluator','radah_autopilot','obsidian'): assert systems.get(key)=='online', (key,systems.get(key))
assert len(s.get('founder_holds',[]))>=5
assert s.get('latest_receipts'), 'runtime receipt index empty'
m=r.get('metrics',{})
print(' '.join(['truth=live','lanes=11/11',f"constraint={r.get('constraint')}",f"experiments={r.get('active_experiment_count')}",f"visitors={m.get('visitors')}",f"clicks={m.get('clicks')}",f"purchases={m.get('purchases')}",f"revenue_usd={m.get('revenue_usd')}",f"receipts={len(s.get('latest_receipts',[]))}"]))
PY
)"
echo "DOMINION_COMMAND_CENTER_LIVE_STATE=$ACCEPTANCE"

[[ -f "$CADDYFILE" ]] || { echo "Caddyfile not found: $CADDYFILE" >&2; exit 1; }
[[ -n "${OBSIDIAN_PASSWORD:-}" ]] || { echo "OBSIDIAN_PASSWORD is required to protect public Command Center access" >&2; exit 1; }
password_hash="$(sudo caddy hash-password --plaintext "$OBSIDIAN_PASSWORD")"; test -n "$password_hash"
sudo env COMMAND_CENTER_PASSWORD_HASH="$password_hash" COMMAND_CENTER_DOMAIN="$DOMAIN" python3 - "$CADDYFILE" <<'PY'
import os
from pathlib import Path
import sys
path=Path(sys.argv[1]); host=os.environ['COMMAND_CENTER_DOMAIN']; password_hash=os.environ['COMMAND_CENTER_PASSWORD_HASH']; text=path.read_text(encoding='utf-8'); lines=text.splitlines(keepends=True)
starts=[i for i,line in enumerate(lines) if line.strip()==f'{host} {{']
if len(starts)>1: raise SystemExit('COMMAND_CENTER_CADDY_ROUTE_DUPLICATE')
block=(f'{host} {{\n'+'    basicauth {\n'+f'        dominion {password_hash}\n'+'    }\n'+'    encode gzip zstd\n'+'    reverse_proxy 127.0.0.1:8091\n'+'}\n')
if starts:
    start=starts[0]; depth=0; end=None
    for i in range(start,len(lines)):
        depth += lines[i].count('{')-lines[i].count('}')
        if depth==0: end=i+1; break
    if end is None: raise SystemExit('COMMAND_CENTER_CADDY_ROUTE_UNBALANCED')
    new=''.join(lines[:start])+block+''.join(lines[end:])
else:
    suffix='' if text.endswith('\n') or not text else '\n'; new=text+suffix+'\n'+block
path.write_text(new,encoding='utf-8',newline='\n')
PY
unset password_hash

# Preserve the already-resolving protected vault fallback across Brain publishes.
bash scripts/converge_command_center_vault_route.sh
sudo caddy validate --config "$CADDYFILE" --adapter caddyfile >/dev/null; sudo systemctl reload caddy; sudo systemctl is-active --quiet caddy

PUBLIC_ENDPOINT=""; PUBLIC_MODE=""
if getent ahostsv4 "$DOMAIN" >/dev/null 2>&1 && curl -fsS --max-time 20 -u "dominion:$OBSIDIAN_PASSWORD" "https://$DOMAIN/health" >/dev/null 2>&1; then
  PUBLIC_ENDPOINT="https://$DOMAIN"; PUBLIC_MODE="dedicated_host"
fi
if [[ -z "$PUBLIC_ENDPOINT" ]]; then
  getent ahostsv4 "$VAULT_HOST" >/dev/null 2>&1 || { echo "Neither $DOMAIN nor $VAULT_HOST resolves to a usable public route" >&2; exit 1; }
  PUBLIC_ENDPOINT="https://$VAULT_HOST/command-center"; PUBLIC_MODE="vault_protected_path"
  curl -fsS --max-time 20 -u "dominion:$OBSIDIAN_PASSWORD" "$PUBLIC_ENDPOINT/health" >/dev/null
fi
public_html="$(curl -fsS --max-time 20 -u "dominion:$OBSIDIAN_PASSWORD" "$PUBLIC_ENDPOINT/")"; grep -Fq 'All Dominion lanes' <<<"$public_html"
PUBLIC_STATUS="$(curl -fsS --max-time 20 -u "dominion:$OBSIDIAN_PASSWORD" "$PUBLIC_ENDPOINT/api/status")"
python3 - "$PUBLIC_STATUS" "$actual_sha" <<'PY'
import json,sys
s=json.loads(sys.argv[1]); expected=sys.argv[2]
assert s['truth']['connected'] is True and s['truth']['release_sha']==expected
assert s['lane_summary']=={'open':11,'registered':11,'all_open':True}
assert s['revenue']['runtime_connected'] is True and s['revenue']['active_experiment_count']>=1
print('COMMAND_CENTER_PUBLIC_TRUTH=PASS')
PY

# Successful builds become governed receipts and are immediately indexed.
mkdir -p "$RECEIPTS"; chmod 700 "$STATE_ROOT" "$RECEIPTS"
receipt_stamp="$(date -u +%Y%m%dT%H%M%SZ)"; receipt="$RECEIPTS/${receipt_stamp}-command-center-${actual_sha:0:12}.json"
RUN_ID_VALUE="${RUN_ID:-unknown}" PUBLIC_ENDPOINT_VALUE="$PUBLIC_ENDPOINT" PUBLIC_MODE_VALUE="$PUBLIC_MODE" ACCEPTANCE_VALUE="$ACCEPTANCE" python3 - "$receipt" "$actual_sha" <<'PY'
import json,os,sys,tempfile
from datetime import datetime,timezone
from pathlib import Path
path=Path(sys.argv[1]); data={'schema':'dominion-command-center-build-receipt-v1','component':'dominion-command-center','status':'PASS','release_sha':sys.argv[2],'run_id':os.environ.get('RUN_ID_VALUE','unknown'),'public_endpoint':os.environ['PUBLIC_ENDPOINT_VALUE'],'public_mode':os.environ['PUBLIC_MODE_VALUE'],'acceptance':os.environ.get('ACCEPTANCE_VALUE',''),'observed_at':datetime.now(timezone.utc).isoformat()}
fd,tmp=tempfile.mkstemp(prefix='.receipt.',dir=str(path.parent))
try:
  with os.fdopen(fd,'w',encoding='utf-8') as h: json.dump(data,h,indent=2,sort_keys=True); h.write('\n'); h.flush(); os.fsync(h.fileno())
  os.chmod(tmp,0o600); os.replace(tmp,path)
finally:
  if os.path.exists(tmp): os.unlink(tmp)
PY
chmod 600 "$receipt"; sudo systemctl start dominion-command-center-state.service
FINAL_STATUS="$(curl -fsS http://127.0.0.1:8091/api/status)"
python3 - "$FINAL_STATUS" "$(basename "$receipt")" <<'PY'
import json,sys
s=json.loads(sys.argv[1]); name=sys.argv[2]
assert any(x.get('name')==name for x in s.get('latest_receipts',[])), (name,s.get('latest_receipts'))
print('COMMAND_CENTER_BUILD_RECEIPT=PASS indexed=true')
PY
grep -Fq "$(basename "$receipt")" "$daily_state"

cat <<EOF
DOMINION_COMMAND_CENTER=PASS
release_sha=$actual_sha
lanes=11/11
live_state=$ACCEPTANCE
truth_bridge=active cadence=60s
obsidian_daily_state=$daily_state
local_endpoint=http://127.0.0.1:8091
public_endpoint=$PUBLIC_ENDPOINT
public_mode=$PUBLIC_MODE
public_state=online
EOF

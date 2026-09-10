#!/usr/bin/env bash
set -Eeuo pipefail

SERVICE=dominion-nemotron.service
MODEL=nemotron-3-nano:4b
REPO="${HOME}/dominion-ops"
RUNTIME="${HOME}/.dominion/nemotron"
LIVE_CONTRACT="${HOME}/.config/dominion/system-integrity-agent.json"
UNIT=/etc/systemd/system/dominion-nemotron.service
CC_ENV_FILE="${COMMAND_CENTER_ENV_FILE:-$HOME/.config/dominion/command-center.env}"
CC_COMPOSE="$REPO/docker-compose.command-center.yml"
CC_BUDDY_TOKEN_FILE="${COMMAND_CENTER_BUDDY_TOKEN_FILE:-$HOME/.dominion/command-center/buddy-web-token}"
CC_INTELLIGENCE_TIMEOUT_SECONDS=300
DEPLOY_SHA="${DEPLOY_SHA:-}"
REMOTE_BUNDLE="${REMOTE_BUNDLE:-}"

mutated=0
backup=''
prior_release=''
staging=''
new_release=''

say() { printf '%s\n' "$*"; }
fail() { say "NEMOTRON_ACTIVATION=BLOCKED reason=$*"; exit 1; }

cleanup_stage() {
  case "$staging" in /tmp/dominion-nemotron-stage.*) rm -rf "$staging" ;; esac
  staging=''
}

recreate_command_center() {
  (
    cd "$REPO"
    COMMAND_CENTER_BUDDY_TOKEN_FILE="$CC_BUDDY_TOKEN_FILE" \
      docker compose --env-file "$CC_ENV_FILE" -f "$CC_COMPOSE" \
      up -d --no-build --force-recreate --no-deps dominion-command-center
  ) || return 1

  local code=''
  for _ in $(seq 1 45); do
    code="$(curl -sS -o /dev/null -w '%{http_code}' --connect-timeout 3 --max-time 8 http://127.0.0.1:8091/health 2>/dev/null || true)"
    [ "$code" = 200 ] && return 0
    sleep 2
  done
  return 1
}

rollback() {
  set +e
  say 'NEMOTRON_ROLLBACK=BEGIN'
  sudo systemctl disable --now "$SERVICE" >/dev/null 2>&1 || true

  if [ -n "$backup" ] && [ -f "$backup/unit" ]; then
    sudo install -m 0644 "$backup/unit" "$UNIT" || true
  fi
  if [ -n "$backup" ] && [ -f "$backup/integrity-contract.json" ]; then
    install -m 600 "$backup/integrity-contract.json" "$LIVE_CONTRACT" || true
  fi
  if [ -n "$backup" ] && [ -f "$backup/command-center.env" ]; then
    install -m 600 "$backup/command-center.env" "$CC_ENV_FILE" || true
    recreate_command_center || true
  fi
  if [ -n "$prior_release" ]; then
    ln -sfn "$prior_release" "$RUNTIME/runtime/release" || true
  else
    rm -f "$RUNTIME/runtime/release" || true
  fi
  case "$new_release" in "$RUNTIME"/releases/*) rm -rf "$new_release" ;; esac

  sudo systemctl daemon-reload || true
  for _ in $(seq 1 30); do
    if ! ss -ltnH 2>/dev/null | awk '{print $4}' | grep -Eq '(^|:)11435$'; then break; fi
    sleep 1
  done

  code11434="$(curl -sS -o /dev/null -w '%{http_code}' --connect-timeout 3 --max-time 8 http://127.0.0.1:11434/api/tags 2>/dev/null || true)"
  codecc="$(curl -sS -o /dev/null -w '%{http_code}' --connect-timeout 3 --max-time 8 http://127.0.0.1:8091/health 2>/dev/null || true)"
  listener=absent
  ss -ltnH 2>/dev/null | awk '{print $4}' | grep -Eq '(^|:)11435$' && listener=present
  cleanup_stage
  say "NEMOTRON_ROLLBACK=COMPLETE listener_11435=$listener ollama_11434=${code11434:-000} command_center=${codecc:-000}"
}

on_exit() {
  rc=$?
  if [ "$rc" -ne 0 ] && [ "$mutated" -eq 1 ]; then rollback; else cleanup_stage; fi
  exit "$rc"
}
trap on_exit EXIT

[[ "$DEPLOY_SHA" =~ ^[0-9a-fA-F]{40}$ ]] || fail 'invalid_deploy_sha'
[ -n "$REMOTE_BUNDLE" ] && [ -f "$REMOTE_BUNDLE" ] || fail 'bundle_missing'
[ -d "$REPO/.git" ] || fail 'canonical_vm_repo_missing'
[ -z "$(git -C "$REPO" status --porcelain)" ] || fail 'canonical_vm_repo_dirty'
[ -f "$CC_ENV_FILE" ] || fail 'command_center_env_missing'
[ ! -L "$CC_ENV_FILE" ] || fail 'command_center_env_symlink_refused'
[ -f "$CC_COMPOSE" ] || fail 'command_center_compose_missing'
[ -s "$CC_BUDDY_TOKEN_FILE" ] || fail 'command_center_buddy_secret_missing'
vm_repo_sha="$(git -C "$REPO" rev-parse HEAD)"

service_active="$(systemctl is-active "$SERVICE" 2>/dev/null || true)"
service_enabled="$(systemctl is-enabled "$SERVICE" 2>/dev/null || true)"
[ "$service_active" != active ] || fail 'service_already_active_requires_reconciliation'
[ "$service_enabled" = disabled ] || fail "service_not_in_expected_disabled_state:$service_enabled"
if ss -ltnH 2>/dev/null | awk '{print $4}' | grep -Eq '(^|:)11435$'; then fail 'port_11435_not_free'; fi

code11434="$(curl -sS -o /dev/null -w '%{http_code}' --connect-timeout 3 --max-time 8 http://127.0.0.1:11434/api/tags 2>/dev/null || true)"
[ "$code11434" = 200 ] || fail "ollama_11434_unhealthy:$code11434"

tags_file="$(mktemp)"
curl -fsS --max-time 10 http://127.0.0.1:11434/api/tags -o "$tags_file" || { rm -f "$tags_file"; fail 'ollama_tags_unreadable'; }
python3 - "$MODEL" "$tags_file" <<'PY' || { rm -f "$tags_file"; fail 'required_model_missing'; }
import json, sys
model, path = sys.argv[1], sys.argv[2]
with open(path, encoding='utf-8') as handle:
    doc = json.load(handle)
names = {str(x.get('name')) for x in doc.get('models', []) if isinstance(x, dict)}
if model not in names:
    raise SystemExit(f'model_missing:{model}')
print('NEMOTRON_MODEL_PRESENT=PASS')
PY
rm -f "$tags_file"

codecc="$(curl -sS -o /dev/null -w '%{http_code}' --connect-timeout 3 --max-time 8 http://127.0.0.1:8091/health 2>/dev/null || true)"
[ "$codecc" = 200 ] || fail "command_center_preflight:$codecc"

integrity_state="$HOME/.dominion/system-integrity/latest.json"
[ -f "$integrity_state" ] || fail 'integrity_state_missing'
before_cycle="$(python3 - "$integrity_state" <<'PY'
import json, sys
with open(sys.argv[1], encoding='utf-8') as handle:
    d = json.load(handle)
assert d.get('ok') is True
assert d.get('status') == 'PASS'
assert int(d.get('defect_count', -1)) == 0
print(int(d.get('cycle', 0)))
PY
)" || fail 'integrity_preflight_not_pass'
say "NEMOTRON_PREFLIGHT=PASS integrity_cycle=$before_cycle vm_repo_sha=$vm_repo_sha"

# Resolve the reviewed exact SHA in an isolated staging repository. The canonical
# VM repo is deliberately not advanced here because Command Center truth binds
# to its currently deployed release SHA; moving that repo alone would create
# false drift. A later whole-foundation deployment reconciles repo parity.
staging="$(mktemp -d /tmp/dominion-nemotron-stage.XXXXXX)"
git -C "$staging" init -q
git -C "$staging" fetch -q "$REMOTE_BUNDLE" refs/heads/nemotron-release
git -C "$staging" checkout -q --detach FETCH_HEAD
[ "$(git -C "$staging" rev-parse HEAD)" = "$DEPLOY_SHA" ] || fail 'bundle_sha_mismatch'
[ -z "$(git -C "$staging" status --porcelain)" ] || fail 'isolated_stage_dirty'

backup="$RUNTIME/backups/$(date -u +%Y%m%dT%H%M%SZ)-${DEPLOY_SHA:0:12}"
install -d -m 700 "$backup" "$RUNTIME/releases" "$RUNTIME/runtime" "$RUNTIME/receipts" "$HOME/.config/dominion"
if [ -f "$UNIT" ]; then sudo cp -a "$UNIT" "$backup/unit"; fi
if [ -f "$LIVE_CONTRACT" ]; then cp -a "$LIVE_CONTRACT" "$backup/integrity-contract.json"; fi
cp -a "$CC_ENV_FILE" "$backup/command-center.env"
chmod 600 "$backup/command-center.env"
prior_release="$(readlink -f "$RUNTIME/runtime/release" 2>/dev/null || true)"
printf '%s\n' "$prior_release" > "$backup/prior-release.txt"
printf '%s\n' "$vm_repo_sha" > "$backup/canonical-vm-repo-sha.txt"

new_release="$RUNTIME/releases/$DEPLOY_SHA"
[ ! -e "$new_release" ] || fail 'release_path_already_exists'

# From this line onward every failure invokes the rollback trap.
mutated=1
install -d -m 755 "$new_release/apps/nemotron-worker"
install -m 0644 "$staging/apps/nemotron-worker/nemotron_worker.py" "$new_release/apps/nemotron-worker/nemotron_worker.py"
printf '%s\n' "$DEPLOY_SHA" > "$new_release/RELEASE_SHA"
ln -sfn "$new_release" "$RUNTIME/runtime/release"
install -m 600 "$staging/governance/system_integrity_agent.json" "$LIVE_CONTRACT"
sudo install -m 0644 "$staging/deploy/systemd/dominion-nemotron.service" "$UNIT"
sudo systemctl daemon-reload
sudo systemctl enable --now "$SERVICE"

health=''
for _ in $(seq 1 30); do
  health="$(curl -fsS --max-time 8 http://127.0.0.1:11435/health 2>/dev/null || true)"
  if python3 - "$health" "$MODEL" <<'PY' >/dev/null 2>&1
import json, sys
d = json.loads(sys.argv[1])
assert d.get('status') == 'ok'
assert d.get('model_available') is True
assert d.get('model') == sys.argv[2]
PY
  then break; fi
  sleep 2
done
python3 - "$health" "$MODEL" <<'PY' || fail 'health_acceptance_failed'
import json, sys
d = json.loads(sys.argv[1])
assert d.get('status') == 'ok'
assert d.get('model_available') is True
assert d.get('model') == sys.argv[2]
print('NEMOTRON_HEALTH=PASS')
PY

mainpid="$(systemctl show "$SERVICE" -p MainPID --value)"
[ -n "$mainpid" ] && [ "$mainpid" != 0 ] || fail 'missing_mainpid'
listener="$(sudo ss -lntp 2>/dev/null | grep ':11435' || true)"
printf '%s\n' "$listener" | grep -q '127.0.0.1:11435' || fail 'listener_not_loopback'
if printf '%s\n' "$listener" | grep -Eq '0\.0\.0\.0:11435|\[::\]:11435|\*:11435'; then fail 'listener_exposed'; fi
printf '%s\n' "$listener" | grep -q "pid=$mainpid," || fail 'listener_not_owned_by_service_mainpid'
[ "$(systemctl is-active "$SERVICE")" = active ] || fail 'service_not_active'
[ "$(systemctl is-enabled "$SERVICE")" = enabled ] || fail 'service_not_enabled'
say "NEMOTRON_LISTENER=PASS pid=$mainpid bind=127.0.0.1:11435"

# A cold Ollama model load can exceed the Command Center's historical 60-second
# intelligence timeout. Prove the worker can generate directly and warm the
# reviewed model before the Command Center routing acceptance test. This is a
# local no-side-effect probe only; failure still rolls the whole activation back.
warm_request="$(mktemp)"
warm_response="$(mktemp)"
python3 - "$warm_request" "$MODEL" <<'PY'
import json, sys
path, model = sys.argv[1:]
payload = {
    'model': model,
    'messages': [{'role': 'user', 'content': 'SYSTEM_INTEGRITY_WARMUP. Reply READY only.'}],
    'temperature': 0.0,
    'stream': False,
}
with open(path, 'w', encoding='utf-8') as handle:
    json.dump(payload, handle)
PY
warm_started="$(date +%s)"
curl -fsS --max-time "$CC_INTELLIGENCE_TIMEOUT_SECONDS" -H 'Content-Type: application/json' --data-binary "@$warm_request" http://127.0.0.1:11435/v1/chat/completions -o "$warm_response" || { rm -f "$warm_request" "$warm_response"; fail 'nemotron_cold_start_warmup_unavailable'; }
python3 - "$warm_response" <<'PY' || { rm -f "$warm_request" "$warm_response"; fail 'nemotron_cold_start_warmup_invalid'; }
import json, sys
with open(sys.argv[1], encoding='utf-8') as handle:
    d = json.load(handle)
choices = d.get('choices') or []
assert choices and isinstance(choices[0], dict)
answer = str(((choices[0].get('message') or {}).get('content')) or '').strip()
assert answer
print('NEMOTRON_WARMUP_RESPONSE=PASS')
PY
warm_elapsed="$(( $(date +%s) - warm_started ))"
rm -f "$warm_request" "$warm_response"
say "NEMOTRON_COLD_START_WARMUP=PASS elapsed_seconds=$warm_elapsed timeout_seconds=$CC_INTELLIGENCE_TIMEOUT_SECONDS"

# The recovery-hold baseline deliberately keeps NEMOTRON_BASE_URL empty until
# an exact-SHA activation is authorized. Converge the non-secret routing and
# timeout keys transactionally now that the governed worker is healthy and warm.
# The complete pre-change env is already backed up and rollback recreates Command
# Center from that backup if any later acceptance gate fails.
python3 - "$CC_ENV_FILE" "$MODEL" "$CC_INTELLIGENCE_TIMEOUT_SECONDS" <<'PY' || fail 'command_center_config_update_failed'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
model = sys.argv[2]
timeout_seconds = sys.argv[3]
updates = {
    'NEMOTRON_BASE_URL': 'http://127.0.0.1:11435',
    'NEMOTRON_MODEL': model,
    'INTELLIGENCE_TIMEOUT_SECONDS': timeout_seconds,
}
lines = path.read_text(encoding='utf-8').splitlines()
seen = set()
out = []
for line in lines:
    replaced = False
    for key, value in updates.items():
        if re.match(rf'^\s*(?:export\s+)?{re.escape(key)}=', line):
            out.append(f'{key}={value}')
            seen.add(key)
            replaced = True
            break
    if not replaced:
        out.append(line)
for key, value in updates.items():
    if key not in seen:
        out.append(f'{key}={value}')
path.write_text('\n'.join(out) + '\n', encoding='utf-8')
PY
chmod 600 "$CC_ENV_FILE"
recreate_command_center || fail 'command_center_reconfigure_failed'
cc_env_sha="$(sha256sum "$CC_ENV_FILE" | awk '{print $1}')"
say "NEMOTRON_COMMAND_CENTER_CONFIG=PASS base_url=127.0.0.1:11435 model=$MODEL timeout_seconds=$CC_INTELLIGENCE_TIMEOUT_SECONDS env_sha256=$cc_env_sha"

probe_request="$(mktemp)"
probe_response="$(mktemp)"
printf '%s' '{"message":"SYSTEM_INTEGRITY_HEALTH_PROBE. Return a short readiness acknowledgement. Do not perform any external action."}' > "$probe_request"
cc_route_max_time="$((CC_INTELLIGENCE_TIMEOUT_SECONDS + 30))"
curl -fsS --max-time "$cc_route_max_time" -H 'Content-Type: application/json' --data-binary "@$probe_request" http://127.0.0.1:8091/api/chat -o "$probe_response" || { rm -f "$probe_request" "$probe_response"; fail 'command_center_route_unavailable'; }
python3 - "$probe_response" <<'PY' || { rm -f "$probe_request" "$probe_response"; fail 'command_center_did_not_route_to_nemotron'; }
import json, sys
with open(sys.argv[1], encoding='utf-8') as handle:
    d = json.load(handle)
assert d.get('source') == 'nemotron', d.get('source')
assert str(d.get('answer') or '').strip()
print('NEMOTRON_COMMAND_CENTER_ROUTE=PASS')
PY
rm -f "$probe_request" "$probe_response"

cmp -s "$staging/governance/system_integrity_agent.json" "$LIVE_CONTRACT" || fail 'integrity_contract_drift'
worker_source_sha="$(sha256sum "$staging/apps/nemotron-worker/nemotron_worker.py" | awk '{print $1}')"
worker_live_sha="$(sha256sum "$new_release/apps/nemotron-worker/nemotron_worker.py" | awk '{print $1}')"
[ "$worker_source_sha" = "$worker_live_sha" ] || fail 'worker_hash_mismatch'
unit_source_sha="$(sha256sum "$staging/deploy/systemd/dominion-nemotron.service" | awk '{print $1}')"
unit_live_sha="$(sudo sha256sum "$UNIT" | awk '{print $1}')"
[ "$unit_source_sha" = "$unit_live_sha" ] || fail 'unit_hash_mismatch'

integrity_ok=0
for _ in $(seq 1 110); do
  if python3 - "$integrity_state" "$before_cycle" <<'PY' >/dev/null 2>&1
import json, sys
with open(sys.argv[1], encoding='utf-8') as handle:
    d = json.load(handle)
assert int(d.get('cycle', 0)) > int(sys.argv[2])
assert d.get('ok') is True
assert d.get('status') == 'PASS'
assert int(d.get('defect_count', -1)) == 0
PY
  then integrity_ok=1; break; fi
  sleep 2
done
[ "$integrity_ok" = 1 ] || fail 'integrity_post_activation_not_pass'
after_cycle="$(python3 - "$integrity_state" <<'PY'
import json, sys
with open(sys.argv[1], encoding='utf-8') as handle:
    print(int(json.load(handle).get('cycle', 0)))
PY
)"
say "NEMOTRON_INTEGRITY=PASS cycle=$after_cycle"

receipt="$RUNTIME/receipts/$(date -u +%Y%m%dT%H%M%SZ)-activation.json"
python3 - "$receipt" "$DEPLOY_SHA" "$worker_live_sha" "$unit_live_sha" "$mainpid" "$before_cycle" "$after_cycle" "$vm_repo_sha" "$cc_env_sha" "$CC_INTELLIGENCE_TIMEOUT_SECONDS" "$warm_elapsed" <<'PY'
import datetime, json, sys
path, sha, worker, unit, pid, before, after, vm_repo_sha, cc_env_sha, timeout_seconds, warm_elapsed = sys.argv[1:]
data = {
    'schema': 'dominion-nemotron-activation-receipt-v1',
    'governance': 'RADAH MEMSHALAH',
    'status': 'DONE',
    'release_sha': sha,
    'service': 'dominion-nemotron.service',
    'model': 'nemotron-3-nano:4b',
    'bind': '127.0.0.1:11435',
    'main_pid': int(pid),
    'worker_sha256': worker,
    'unit_sha256': unit,
    'command_center_source': 'nemotron',
    'command_center_base_url': 'http://127.0.0.1:11435',
    'command_center_model': 'nemotron-3-nano:4b',
    'command_center_timeout_seconds': int(timeout_seconds),
    'cold_start_warmup_seconds': int(warm_elapsed),
    'command_center_env_sha256': cc_env_sha,
    'integrity_cycle_before': int(before),
    'integrity_cycle_after': int(after),
    'integrity_status': 'PASS',
    'defect_count': 0,
    'external_ingress_opened': False,
    'canonical_vm_repo_sha_unchanged': vm_repo_sha,
    'deployment_source': 'isolated_exact_sha_bundle',
    'observed_at': datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00', 'Z'),
}
with open(path, 'w', encoding='utf-8') as handle:
    handle.write(json.dumps(data, indent=2, sort_keys=True) + '\n')
print(path)
PY
chmod 600 "$receipt"
ln -sfn "$receipt" "$RUNTIME/latest.json"
printf '%s\n' "$receipt" > /tmp/dominion-nemotron-activation-receipt.path
say "NEMOTRON_ACTIVATION=DONE release_sha=$DEPLOY_SHA receipt=$receipt"

mutated=0
trap - EXIT
cleanup_stage
rm -f "$REMOTE_BUNDLE"

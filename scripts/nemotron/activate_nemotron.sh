#!/usr/bin/env bash
set -Eeuo pipefail

SERVICE=dominion-nemotron.service
MODEL=nemotron-3-nano:4b
REPO="${HOME}/dominion-ops"
RUNTIME="${HOME}/.dominion/nemotron"
LIVE_CONTRACT="${HOME}/.config/dominion/system-integrity-agent.json"
UNIT=/etc/systemd/system/dominion-nemotron.service
DEPLOY_SHA="${DEPLOY_SHA:-}"
REMOTE_BUNDLE="${REMOTE_BUNDLE:-}"

mutated=0
backup=''
prior_release=''
prior_repo_sha=''

say() { printf '%s\n' "$*"; }
fail() { say "NEMOTRON_ACTIVATION=BLOCKED reason=$*"; exit 1; }

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
  if [ -n "$prior_release" ]; then
    ln -sfn "$prior_release" "$RUNTIME/runtime/release" || true
  else
    rm -f "$RUNTIME/runtime/release" || true
  fi

  if [ -n "$prior_repo_sha" ] && [ -d "$REPO/.git" ]; then
    current_sha="$(git -C "$REPO" rev-parse HEAD 2>/dev/null || true)"
    dirty="$(git -C "$REPO" status --porcelain 2>/dev/null || true)"
    if [ "$current_sha" = "$DEPLOY_SHA" ] && [ -z "$dirty" ]; then
      git -C "$REPO" reset --hard "$prior_repo_sha" >/dev/null 2>&1 || true
    else
      say "NEMOTRON_ROLLBACK_REPO=SKIPPED current=${current_sha:-unknown} dirty=$([ -n "$dirty" ] && echo yes || echo no)"
    fi
  fi

  sudo systemctl daemon-reload || true
  for _ in $(seq 1 30); do
    if ! ss -ltnH 2>/dev/null | awk '{print $4}' | grep -Eq '(^|:)11435$'; then break; fi
    sleep 1
  done

  code11434="$(curl -sS -o /dev/null -w '%{http_code}' --connect-timeout 3 --max-time 8 http://127.0.0.1:11434/api/tags 2>/dev/null || true)"
  codecc="$(curl -sS -o /dev/null -w '%{http_code}' --connect-timeout 3 --max-time 8 http://127.0.0.1:8091/health 2>/dev/null || true)"
  listener=absent
  ss -ltnH 2>/dev/null | awk '{print $4}' | grep -Eq '(^|:)11435$' && listener=present
  say "NEMOTRON_ROLLBACK=COMPLETE listener_11435=$listener ollama_11434=${code11434:-000} command_center=${codecc:-000}"
}

on_exit() {
  rc=$?
  if [ "$rc" -ne 0 ] && [ "$mutated" -eq 1 ]; then rollback; fi
  exit "$rc"
}
trap on_exit EXIT

[[ "$DEPLOY_SHA" =~ ^[0-9a-fA-F]{40}$ ]] || fail 'invalid_deploy_sha'
[ -n "$REMOTE_BUNDLE" ] && [ -f "$REMOTE_BUNDLE" ] || fail 'bundle_missing'
[ -d "$REPO/.git" ] || fail 'repo_missing'
[ -z "$(git -C "$REPO" status --porcelain)" ] || fail 'vm_repo_dirty'
[ "$(git -C "$REPO" branch --show-current)" = main ] || fail 'vm_repo_not_main'

service_active="$(systemctl is-active "$SERVICE" 2>/dev/null || true)"
service_enabled="$(systemctl is-enabled "$SERVICE" 2>/dev/null || true)"
[ "$service_active" != active ] || fail 'service_already_active_requires_reconciliation'
[ "$service_enabled" = disabled ] || fail "service_not_in_expected_disabled_state:$service_enabled"
if ss -ltnH 2>/dev/null | awk '{print $4}' | grep -Eq '(^|:)11435$'; then fail 'port_11435_not_free'; fi

code11434="$(curl -sS -o /dev/null -w '%{http_code}' --connect-timeout 3 --max-time 8 http://127.0.0.1:11434/api/tags 2>/dev/null || true)"
[ "$code11434" = 200 ] || fail "ollama_11434_unhealthy:$code11434"

tags_file="$(mktemp)"
trap 'rm -f "$tags_file"' RETURN
curl -fsS --max-time 10 http://127.0.0.1:11434/api/tags -o "$tags_file" || fail 'ollama_tags_unreadable'
python3 - "$MODEL" "$tags_file" <<'PY' || fail 'required_model_missing'
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
trap - RETURN

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
say "NEMOTRON_PREFLIGHT=PASS integrity_cycle=$before_cycle"

remote_ref=refs/remotes/nemotron/release
git -C "$REPO" fetch "$REMOTE_BUNDLE" "refs/heads/nemotron-release:$remote_ref"
fetched="$(git -C "$REPO" rev-parse "$remote_ref")"
[ "$fetched" = "$DEPLOY_SHA" ] || fail 'bundle_sha_mismatch'
prior_repo_sha="$(git -C "$REPO" rev-parse HEAD)"
git -C "$REPO" merge-base --is-ancestor "$prior_repo_sha" "$DEPLOY_SHA" || fail 'vm_repo_cannot_fast_forward'

backup="$RUNTIME/backups/$(date -u +%Y%m%dT%H%M%SZ)-${DEPLOY_SHA:0:12}"
install -d -m 700 "$backup" "$RUNTIME/releases" "$RUNTIME/runtime" "$RUNTIME/receipts" "$HOME/.config/dominion"
if [ -f "$UNIT" ]; then sudo cp -a "$UNIT" "$backup/unit"; fi
if [ -f "$LIVE_CONTRACT" ]; then cp -a "$LIVE_CONTRACT" "$backup/integrity-contract.json"; fi
prior_release="$(readlink -f "$RUNTIME/runtime/release" 2>/dev/null || true)"
printf '%s\n' "$prior_release" > "$backup/prior-release.txt"
printf '%s\n' "$prior_repo_sha" > "$backup/prior-repo-sha.txt"

# From this line onward every failure invokes the rollback trap.
mutated=1

git -C "$REPO" merge --ff-only "$DEPLOY_SHA"
[ "$(git -C "$REPO" rev-parse HEAD)" = "$DEPLOY_SHA" ] || fail 'vm_repo_sync_failed'

release="$RUNTIME/releases/$DEPLOY_SHA"
[ ! -e "$release" ] || fail 'release_path_already_exists'
install -d -m 755 "$release/apps/nemotron-worker"
install -m 0644 "$REPO/apps/nemotron-worker/nemotron_worker.py" "$release/apps/nemotron-worker/nemotron_worker.py"
printf '%s\n' "$DEPLOY_SHA" > "$release/RELEASE_SHA"
ln -sfn "$release" "$RUNTIME/runtime/release"

install -m 600 "$REPO/governance/system_integrity_agent.json" "$LIVE_CONTRACT"
sudo install -m 0644 "$REPO/deploy/systemd/dominion-nemotron.service" "$UNIT"
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

probe_file="$(mktemp)"
printf '%s' '{"message":"SYSTEM_INTEGRITY_HEALTH_PROBE. Return a short readiness acknowledgement. Do not perform any external action."}' > "$probe_file.request"
curl -fsS --max-time 90 -H 'Content-Type: application/json' --data-binary "@$probe_file.request" http://127.0.0.1:8091/api/chat -o "$probe_file" || fail 'command_center_route_unavailable'
python3 - "$probe_file" <<'PY' || fail 'command_center_did_not_route_to_nemotron'
import json, sys
with open(sys.argv[1], encoding='utf-8') as handle:
    d = json.load(handle)
assert d.get('source') == 'nemotron', d.get('source')
assert str(d.get('answer') or '').strip()
print('NEMOTRON_COMMAND_CENTER_ROUTE=PASS')
PY
rm -f "$probe_file" "$probe_file.request"

cmp -s "$REPO/governance/system_integrity_agent.json" "$LIVE_CONTRACT" || fail 'integrity_contract_drift'
worker_repo_sha="$(sha256sum "$REPO/apps/nemotron-worker/nemotron_worker.py" | awk '{print $1}')"
worker_live_sha="$(sha256sum "$release/apps/nemotron-worker/nemotron_worker.py" | awk '{print $1}')"
[ "$worker_repo_sha" = "$worker_live_sha" ] || fail 'worker_hash_mismatch'
unit_repo_sha="$(sha256sum "$REPO/deploy/systemd/dominion-nemotron.service" | awk '{print $1}')"
unit_live_sha="$(sudo sha256sum "$UNIT" | awk '{print $1}')"
[ "$unit_repo_sha" = "$unit_live_sha" ] || fail 'unit_hash_mismatch'

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
python3 - "$receipt" "$DEPLOY_SHA" "$worker_live_sha" "$unit_live_sha" "$mainpid" "$before_cycle" "$after_cycle" <<'PY'
import datetime, json, sys
path, sha, worker, unit, pid, before, after = sys.argv[1:]
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
    'integrity_cycle_before': int(before),
    'integrity_cycle_after': int(after),
    'integrity_status': 'PASS',
    'defect_count': 0,
    'external_ingress_opened': False,
    'observed_at': datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00', 'Z'),
}
with open(path, 'w', encoding='utf-8') as handle:
    handle.write(json.dumps(data, indent=2, sort_keys=True) + '\n')
print(path)
PY
chmod 600 "$receipt"
printf '%s\n' "$receipt" > /tmp/dominion-nemotron-activation-receipt.path
say "NEMOTRON_ACTIVATION=DONE release_sha=$DEPLOY_SHA receipt=$receipt"

mutated=0
trap - EXIT
rm -f "$REMOTE_BUNDLE"

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

cd "$REPO_DIR"
git fetch origin "$BRANCH"
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"

if [[ -n "$EXPECTED_SHA" ]]; then
  actual_sha="$(git rev-parse HEAD)"
  [[ "$actual_sha" == "$EXPECTED_SHA" ]] || {
    echo "Command Center release mismatch: expected=$EXPECTED_SHA actual=$actual_sha" >&2
    exit 1
  }
fi

# The control plane must boot even while individual offers are incomplete.
# Missing checkout/delivery values remain truthfully BLOCKED in /api/revenue.
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
  docker logs --tail 120 dominion-command-center 2>&1 || true
  echo "Dominion Command Center failed local health gate" >&2
  exit 1
}

STATUS_JSON="$(curl -fsS http://127.0.0.1:8091/api/status)"
python3 - "$STATUS_JSON" <<'PY'
import json
import sys
state = json.loads(sys.argv[1])
summary = state.get("lane_summary", {})
if summary.get("registered") != 11 or summary.get("open") != 11 or summary.get("all_open") is not True:
    raise SystemExit(f"11/11 lane gate failed: {summary}")
print("DOMINION_COMMAND_CENTER_LANES=PASS open=11 registered=11")
PY

REVENUE_JSON="$(curl -fsS http://127.0.0.1:8091/api/revenue)"
REVENUE_GATE_STATE="$(python3 - "$REVENUE_JSON" <<'PY'
import json
import sys
state = json.loads(sys.argv[1])
offers = state.get("offers", [])
ready = [o.get("slug") for o in offers if o.get("status") == "revenue_ready"]
blocked = [o.get("slug") for o in offers if o.get("status") != "revenue_ready"]
print(f"ready={len(ready)} blocked={len(blocked)} ready_offers={','.join(ready) or 'none'} blocked_offers={','.join(blocked) or 'none'}")
PY
)"
echo "DOMINION_COMMAND_CENTER_REVENUE_STATE=$REVENUE_GATE_STATE"

[[ -f "$CADDYFILE" ]] || { echo "Caddyfile not found: $CADDYFILE" >&2; exit 1; }
[[ -n "${OBSIDIAN_PASSWORD:-}" ]] || { echo "OBSIDIAN_PASSWORD is required to protect public Command Center access" >&2; exit 1; }

# Keep the dedicated hostname ready, but never expose the control surface without auth.
password_hash="$(sudo caddy hash-password --plaintext "$OBSIDIAN_PASSWORD")"
test -n "$password_hash"
sudo env COMMAND_CENTER_PASSWORD_HASH="$password_hash" COMMAND_CENTER_DOMAIN="$DOMAIN" python3 - "$CADDYFILE" <<'PY'
import os
from pathlib import Path

path = Path(__import__('sys').argv[1])
host = os.environ['COMMAND_CENTER_DOMAIN']
password_hash = os.environ['COMMAND_CENTER_PASSWORD_HASH']
text = path.read_text(encoding='utf-8')
lines = text.splitlines(keepends=True)
starts = [i for i, line in enumerate(lines) if line.strip() == f'{host} {{']
if len(starts) > 1:
    raise SystemExit('COMMAND_CENTER_CADDY_ROUTE_DUPLICATE')
block = (
    f'{host} {{\n'
    '    basicauth {\n'
    f'        dominion {password_hash}\n'
    '    }\n'
    '    encode gzip zstd\n'
    '    reverse_proxy 127.0.0.1:8091\n'
    '}\n'
)
if starts:
    start = starts[0]
    depth = 0
    end = None
    for i in range(start, len(lines)):
        depth += lines[i].count('{') - lines[i].count('}')
        if depth == 0:
            end = i + 1
            break
    if end is None:
        raise SystemExit('COMMAND_CENTER_CADDY_ROUTE_UNBALANCED')
    new = ''.join(lines[:start]) + block + ''.join(lines[end:])
else:
    suffix = '' if text.endswith('\n') or not text else '\n'
    new = text + suffix + '\n' + block
path.write_text(new, encoding='utf-8', newline='\n')
PY
unset password_hash

# Immediate protected fallback: the vault hostname already resolves to this VM.
bash scripts/converge_command_center_vault_route.sh

sudo caddy validate --config "$CADDYFILE" --adapter caddyfile >/dev/null
sudo systemctl reload caddy
sudo systemctl is-active --quiet caddy

PUBLIC_ENDPOINT=""
PUBLIC_MODE=""

# Prefer the dedicated hostname whenever its DNS exists and HTTPS proves healthy.
if getent ahostsv4 "$DOMAIN" >/dev/null 2>&1; then
  if curl -fsS --max-time 20 -u "dominion:$OBSIDIAN_PASSWORD" "https://$DOMAIN/health" >/dev/null 2>&1; then
    PUBLIC_ENDPOINT="https://$DOMAIN"
    PUBLIC_MODE="dedicated_host"
  fi
fi

# Otherwise use the already-live authenticated vault hostname under a protected path.
if [[ -z "$PUBLIC_ENDPOINT" ]]; then
  getent ahostsv4 "$VAULT_HOST" >/dev/null 2>&1 || {
    echo "Neither $DOMAIN nor $VAULT_HOST resolves to a usable public route" >&2
    exit 1
  }
  fallback="https://$VAULT_HOST/command-center"
  curl -fsS --max-time 20 -u "dominion:$OBSIDIAN_PASSWORD" "$fallback/health" >/dev/null
  html="$(curl -fsS --max-time 20 -u "dominion:$OBSIDIAN_PASSWORD" "$fallback/")"
  grep -Fq 'All Dominion lanes' <<<"$html"
  public_status="$(curl -fsS --max-time 20 -u "dominion:$OBSIDIAN_PASSWORD" "$fallback/api/status")"
  python3 - "$public_status" <<'PY'
import json,sys
state=json.loads(sys.argv[1])
summary=state.get('lane_summary',{})
assert summary.get('open') == 11
assert summary.get('registered') == 11
assert summary.get('all_open') is True
print('DOMINION_COMMAND_CENTER_PUBLIC_LANES=PASS open=11 registered=11')
PY
  PUBLIC_ENDPOINT="$fallback"
  PUBLIC_MODE="vault_protected_path"
fi

cat <<EOF
DOMINION_COMMAND_CENTER=PASS
release_sha=$(git rev-parse HEAD)
lanes=11/11
revenue_state=$REVENUE_GATE_STATE
local_endpoint=http://127.0.0.1:8091
public_endpoint=$PUBLIC_ENDPOINT
public_mode=$PUBLIC_MODE
public_state=online
EOF

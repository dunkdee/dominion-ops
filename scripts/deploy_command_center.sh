#!/usr/bin/env bash
set -Eeuo pipefail

REPO_DIR="${REPO_DIR:-$HOME/dominion-ops}"
DOMAIN="${COMMAND_CENTER_DOMAIN:-command.dominionhealing.org}"
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

# The control plane must be able to boot even when an individual revenue offer
# is not yet configured. Missing checkout/delivery values remain truthfully
# BLOCKED in /api/revenue; they must never take the whole Command Center down.
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

PUBLIC_STATE="pending"
if getent ahostsv4 "$DOMAIN" >/dev/null 2>&1; then
  if curl -fsS --max-time 20 "https://$DOMAIN/health" >/dev/null 2>&1; then
    PUBLIC_STATE="online"
  else
    echo "Command Center is healthy locally and Caddy is configured, but public HTTPS did not pass." >&2
    echo "Check DNS/TLS for $DOMAIN." >&2
    exit 1
  fi
else
  echo "Command Center is healthy locally and Caddy is configured, but DNS does not resolve for $DOMAIN." >&2
  exit 1
fi

cat <<EOF
DOMINION_COMMAND_CENTER=PASS
release_sha=$(git rev-parse HEAD)
lanes=11/11
revenue_state=$REVENUE_GATE_STATE
local_endpoint=http://127.0.0.1:8091
public_endpoint=https://$DOMAIN
public_state=$PUBLIC_STATE
EOF

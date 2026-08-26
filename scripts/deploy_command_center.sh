#!/usr/bin/env bash
set -Eeuo pipefail

REPO_DIR="${REPO_DIR:-$HOME/dominion-ops}"
DOMAIN="${COMMAND_CENTER_DOMAIN:-command.dominionhealing.org}"
ENV_FILE="${COMMAND_CENTER_ENV_FILE:-$HOME/.config/dominion/command-center.env}"
BRANCH="${COMMAND_CENTER_BRANCH:-main}"
EXPECTED_SHA="${EXPECTED_SHA:-}"
CADDYFILE="${CADDYFILE:-/etc/caddy/Caddyfile}"

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

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing runtime environment file: $ENV_FILE" >&2
  echo "Create it from config/command-center.env.example and keep permissions at 0600." >&2
  exit 1
fi

chmod 600 "$ENV_FILE"
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

required=(
  CHECKOUT_ART_OF_TRUE_HEALING
  DELIVERY_ART_OF_TRUE_HEALING
)
for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    echo "Required runtime value is missing: $name" >&2
    exit 1
  fi
done

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
python3 - "$REVENUE_JSON" <<'PY'
import json
import sys
state = json.loads(sys.argv[1])
ready = [offer for offer in state.get("offers", []) if offer.get("slug") == "art-of-true-healing" and offer.get("status") == "revenue_ready"]
if len(ready) != 1:
    raise SystemExit("Art of True Healing did not pass the revenue-ready gate")
print("DOMINION_COMMAND_CENTER_REVENUE_GATE=PASS offer=art-of-true-healing")
PY

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
revenue_gate=pass
local_endpoint=http://127.0.0.1:8091
public_endpoint=https://$DOMAIN
public_state=$PUBLIC_STATE
EOF

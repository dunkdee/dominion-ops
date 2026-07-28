#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${REPO_DIR:-$HOME/dominion-ops}"
DOMAIN="${COMMAND_CENTER_DOMAIN:-command.dominionhealing.org}"
ENV_FILE="${COMMAND_CENTER_ENV_FILE:-$HOME/.config/dominion/command-center.env}"
BRANCH="${COMMAND_CENTER_BRANCH:-main}"

cd "$REPO_DIR"
git fetch origin "$BRANCH"
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"

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

curl -fsS http://127.0.0.1:8091/health >/dev/null
REVENUE_JSON="$(curl -fsS http://127.0.0.1:8091/api/revenue)"
python3 - "$REVENUE_JSON" <<'PY'
import json
import sys
state = json.loads(sys.argv[1])
ready = [offer for offer in state.get("offers", []) if offer.get("slug") == "art-of-true-healing" and offer.get("status") == "revenue_ready"]
if len(ready) != 1:
    raise SystemExit("Art of True Healing did not pass the revenue-ready gate")
PY

cat <<EOF
Dominion Command Center is healthy locally.
Revenue gate passed for: The Art of True Healing
Local endpoint: http://127.0.0.1:8091
Public endpoint: https://$DOMAIN
EOF

#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${REPO_DIR:-$HOME/dominion-ops}"
DOMAIN="${COMMAND_CENTER_DOMAIN:-command.dominionhealing.org}"

cd "$REPO_DIR"
git fetch origin feat/prompt-os
git checkout feat/prompt-os
git pull --ff-only origin feat/prompt-os

docker compose -f docker-compose.command-center.yml up -d --build

curl -fsS http://127.0.0.1:8091/health >/dev/null

cat <<EOF
Dominion Command Center is healthy locally.
Local endpoint: http://127.0.0.1:8091
Recommended Caddy route:

$DOMAIN {
    reverse_proxy 127.0.0.1:8091
}

After adding the route, reload Caddy and open https://$DOMAIN from phone or laptop.
EOF

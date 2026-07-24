#!/usr/bin/env bash
set -euo pipefail

APP_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cd "$APP_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: Docker is required on the GCP VM." >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "ERROR: Docker Compose v2 is required on the GCP VM." >&2
  exit 1
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
fi

if ! grep -Eq '^VIDEO_STUDIO_WORKER_TOKEN=.{32,}$' .env; then
  token=$(openssl rand -hex 32)
  sed -i "s/^VIDEO_STUDIO_WORKER_TOKEN=.*/VIDEO_STUDIO_WORKER_TOKEN=${token}/" .env
  chmod 600 .env
fi

docker compose up -d --build
sleep 3
curl --fail --silent --show-error http://127.0.0.1:8094/ready
echo
echo "Dominion Video Studio is running on localhost:8094."
echo "Do not expose it publicly until the authenticated Caddy route is configured."

#!/usr/bin/env bash
set -Eeuo pipefail

umask 077

APP_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cd "$APP_DIR"

RELEASE_SHA=${RELEASE_SHA:-$(git rev-parse HEAD 2>/dev/null || true)}
SERVICE_NAME=${VIDEO_STUDIO_SERVICE_NAME:-dominion-video-studio}
IMAGE_REPO=${VIDEO_STUDIO_IMAGE_REPO:-dominion/video-studio}
PORT=${VIDEO_STUDIO_PORT:-8094}
DATA_VOLUME=${VIDEO_STUDIO_DATA_VOLUME:-dominion-video-studio-data}
ENV_FILE=${VIDEO_STUDIO_ENV_FILE:-$HOME/.config/dominion/video-studio.env}
HEALTH_ATTEMPTS=${VIDEO_STUDIO_HEALTH_ATTEMPTS:-30}
HEALTH_INTERVAL_SECONDS=${VIDEO_STUDIO_HEALTH_INTERVAL_SECONDS:-2}
HEALTH_URL="http://127.0.0.1:${PORT}/ready"
ROLLBACK_CONTAINER="${SERVICE_NAME}-rollback"

fail() {
  echo "ERROR: $*" >&2
  return 1
}

[[ "$RELEASE_SHA" =~ ^[0-9a-f]{40}$ ]] || fail "RELEASE_SHA must be a full 40-character commit SHA."
[[ "$HEALTH_ATTEMPTS" =~ ^[1-9][0-9]*$ ]] || fail "VIDEO_STUDIO_HEALTH_ATTEMPTS must be a positive integer."
[[ "$HEALTH_INTERVAL_SECONDS" =~ ^[1-9][0-9]*$ ]] || fail "VIDEO_STUDIO_HEALTH_INTERVAL_SECONDS must be a positive integer."
command -v docker >/dev/null 2>&1 || fail "Docker is required on the GCP VM."
command -v curl >/dev/null 2>&1 || fail "curl is required on the GCP VM."
command -v openssl >/dev/null 2>&1 || fail "openssl is required on the GCP VM."
[[ -f Dockerfile ]] || fail "Dockerfile not found in $APP_DIR."

mkdir -p "$(dirname "$ENV_FILE")"
if [[ ! -f "$ENV_FILE" ]]; then
  install -m 600 /dev/null "$ENV_FILE"
fi

set_env() {
  local key=$1
  local value=$2
  if grep -q "^${key}=" "$ENV_FILE"; then
    sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
  else
    printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
  fi
}

if ! grep -Eq '^VIDEO_STUDIO_WORKER_TOKEN=.{32,}$' "$ENV_FILE"; then
  set_env VIDEO_STUDIO_WORKER_TOKEN "$(openssl rand -hex 32)"
fi
set_env VIDEO_STUDIO_DATA_DIR /data
set_env VIDEO_STUDIO_MAX_UPLOAD_BYTES "${VIDEO_STUDIO_MAX_UPLOAD_BYTES:-104857600}"
chmod 600 "$ENV_FILE"

IMAGE_TAG="${IMAGE_REPO}:${RELEASE_SHA}"
PREVIOUS_IMAGE=""
PREVIOUS_EXISTS=false

if docker inspect "$SERVICE_NAME" >/dev/null 2>&1; then
  PREVIOUS_EXISTS=true
  PREVIOUS_IMAGE=$(docker inspect "$SERVICE_NAME" --format '{{.Config.Image}}')
fi

echo "Building immutable image $IMAGE_TAG"
docker build --pull --tag "$IMAGE_TAG" .

docker rm -f "$ROLLBACK_CONTAINER" >/dev/null 2>&1 || true
if [[ "$PREVIOUS_EXISTS" == true ]]; then
  docker stop "$SERVICE_NAME" >/dev/null
  docker rename "$SERVICE_NAME" "$ROLLBACK_CONTAINER"
fi

rollback() {
  local exit_code=$?
  trap - ERR
  set +e
  echo "Deployment failed; restoring previous container." >&2
  docker rm -f "$SERVICE_NAME" >/dev/null 2>&1 || true
  if docker inspect "$ROLLBACK_CONTAINER" >/dev/null 2>&1; then
    docker rename "$ROLLBACK_CONTAINER" "$SERVICE_NAME" >/dev/null 2>&1
    docker start "$SERVICE_NAME" >/dev/null 2>&1
    if ! docker inspect "$SERVICE_NAME" --format '{{.State.Running}}' 2>/dev/null | grep -qx true; then
      echo "ERROR: Previous container could not be restarted." >&2
    fi
  fi
  exit "$exit_code"
}
trap rollback ERR

docker volume create "$DATA_VOLUME" >/dev/null

docker run -d \
  --name "$SERVICE_NAME" \
  --restart unless-stopped \
  --publish "127.0.0.1:${PORT}:8000" \
  --read-only \
  --tmpfs /tmp:size=256m,noexec,nosuid,nodev \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --pids-limit 256 \
  --memory 2g \
  --cpus 2.0 \
  --env-file "$ENV_FILE" \
  --volume "${DATA_VOLUME}:/data" \
  --label "dominion.release.sha=${RELEASE_SHA}" \
  --label "dominion.release.service=video-studio" \
  "$IMAGE_TAG" >/dev/null

ready=false
for attempt in $(seq 1 "$HEALTH_ATTEMPTS"); do
  if curl --fail --silent --show-error "$HEALTH_URL" >/tmp/video-studio-ready.json; then
    python3 - <<'PY'
import json
from pathlib import Path
payload = json.loads(Path('/tmp/video-studio-ready.json').read_text())
assert payload.get('status') == 'ready', payload
PY
    ready=true
    break
  fi
  sleep "$HEALTH_INTERVAL_SECONDS"
done
if [[ "$ready" != true ]]; then
  docker logs --tail 200 "$SERVICE_NAME" >&2 || true
  fail "Readiness check failed after ${HEALTH_ATTEMPTS} attempts."
fi

CURRENT_IMAGE=$(docker inspect "$SERVICE_NAME" --format '{{.Config.Image}}')
CURRENT_SHA=$(docker inspect "$SERVICE_NAME" --format '{{index .Config.Labels "dominion.release.sha"}}')
[[ "$CURRENT_IMAGE" == "$IMAGE_TAG" ]] || fail "Running image mismatch."
[[ "$CURRENT_SHA" == "$RELEASE_SHA" ]] || fail "Running release label mismatch."

trap - ERR
docker rm -f "$ROLLBACK_CONTAINER" >/dev/null 2>&1 || true

printf 'release_sha=%s\nimage=%s\ncontainer=%s\nhealth_url=%s\nprevious_image=%s\n' \
  "$RELEASE_SHA" "$CURRENT_IMAGE" "$SERVICE_NAME" "$HEALTH_URL" "${PREVIOUS_IMAGE:-none}"
echo "Dominion Video Studio deployment passed on localhost:${PORT}."
echo "Public exposure remains prohibited until authenticated Caddy access is separately verified."

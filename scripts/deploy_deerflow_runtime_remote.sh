#!/usr/bin/env bash
set -euo pipefail

DEERFLOW_ROOT="${DEERFLOW_ROOT:-/opt/dominion/deer-flow}"
DOMINION_CONFIG_SOURCE="${DOMINION_CONFIG_SOURCE:?DOMINION_CONFIG_SOURCE is required}"
UPSTREAM_REPO="https://github.com/bytedance/deer-flow.git"
UPSTREAM_TAG="v2.0.0"
ENV_FILE="${DEERFLOW_ENV_FILE:-$HOME/.config/dominion/deerflow.env}"

command -v git >/dev/null
command -v docker >/dev/null
docker compose version >/dev/null

test -r "$DOMINION_CONFIG_SOURCE"

install -d -m 0755 "$(dirname "$DEERFLOW_ROOT")"

if [ ! -d "$DEERFLOW_ROOT/.git" ]; then
  git clone --depth 1 --branch "$UPSTREAM_TAG" "$UPSTREAM_REPO" "$DEERFLOW_ROOT"
else
  cd "$DEERFLOW_ROOT"
  current_remote="$(git remote get-url origin)"
  test "$current_remote" = "$UPSTREAM_REPO"
  git diff --quiet
  git diff --cached --quiet
  git fetch --tags --force origin "$UPSTREAM_TAG"
  git checkout --detach "$UPSTREAM_TAG"
fi

cd "$DEERFLOW_ROOT"
resolved_tag="$(git describe --tags --exact-match HEAD)"
test "$resolved_tag" = "$UPSTREAM_TAG"

install -m 0640 "$DOMINION_CONFIG_SOURCE" "$DEERFLOW_ROOT/config.yaml"

if [ ! -f "$ENV_FILE" ]; then
  install -d -m 0700 "$(dirname "$ENV_FILE")"
  umask 077
  cat > "$ENV_FILE" <<'EOF'
DOMINION_OLLAMA_BASE_URL=http://host.docker.internal:11434
UV_EXTRAS=browser,ollama
EOF
  chmod 0600 "$ENV_FILE"
fi

test -r "$ENV_FILE"

set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

: "${DOMINION_OLLAMA_BASE_URL:=http://host.docker.internal:11434}"
: "${UV_EXTRAS:=browser,ollama}"
export DOMINION_OLLAMA_BASE_URL UV_EXTRAS

cp "$ENV_FILE" "$DEERFLOW_ROOT/.env"
chmod 0600 "$DEERFLOW_ROOT/.env"

FRONTEND_ENV="$DEERFLOW_ROOT/frontend/.env"
if [ ! -f "$FRONTEND_ENV" ]; then
  test -r "$DEERFLOW_ROOT/frontend/.env.example"
  install -m 0600 "$DEERFLOW_ROOT/frontend/.env.example" "$FRONTEND_ENV"
fi
test -r "$FRONTEND_ENV"

grep -Fq 'browser_navigate' "$DEERFLOW_ROOT/config.yaml"
grep -Fq 'browser_click' "$DEERFLOW_ROOT/config.yaml"
grep -Fq 'browser_type' "$DEERFLOW_ROOT/config.yaml"
grep -Fq 'allow_host_bash: false' "$DEERFLOW_ROOT/config.yaml"

make up

for attempt in $(seq 1 30); do
  if curl --fail --silent --show-error http://127.0.0.1:2026/ >/dev/null; then
    echo "DEERFLOW_RUNTIME_HEALTH=PASS tag=$UPSTREAM_TAG url=http://127.0.0.1:2026/"
    exit 0
  fi
  sleep 4
done

echo "DEERFLOW_RUNTIME_HEALTH=FAIL tag=$UPSTREAM_TAG"
docker compose -p deer-flow -f docker/docker-compose.yaml ps || true
docker compose -p deer-flow -f docker/docker-compose.yaml logs --tail=120 gateway || true
exit 1

#!/usr/bin/env bash
set -euo pipefail

DEERFLOW_ROOT="${DEERFLOW_ROOT:-/opt/dominion/deer-flow}"
DOMINION_CONFIG_SOURCE="${DOMINION_CONFIG_SOURCE:?DOMINION_CONFIG_SOURCE is required}"
UPSTREAM_REPO="https://github.com/bytedance/deer-flow.git"
UPSTREAM_TAG="v2.0.0"
ENV_FILE="${DEERFLOW_ENV_FILE:-$HOME/.config/dominion/deerflow.env}"
APT_HTTPS_PATCHED=0
OLLAMA_DEP_PATCHED=0

restore_upstream_files() {
  if [ -d "$DEERFLOW_ROOT/.git" ]; then
    if [ "$APT_HTTPS_PATCHED" -eq 1 ]; then
      git -C "$DEERFLOW_ROOT" checkout -- backend/Dockerfile || true
    fi
    if [ "$OLLAMA_DEP_PATCHED" -eq 1 ]; then
      git -C "$DEERFLOW_ROOT" checkout -- backend/pyproject.toml || true
    fi
  fi
}
trap restore_upstream_files EXIT

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
EOF
  chmod 0600 "$ENV_FILE"
fi

test -r "$ENV_FILE"

# Remove only the obsolete value written by the first governed DeerFlow deploy.
# DeerFlow v2.0.0's root backend project does not define browser or ollama extras,
# so passing this as Docker's UV_EXTRAS build arg fails before the runtime starts.
if grep -Fqx 'UV_EXTRAS=browser,ollama' "$ENV_FILE"; then
  sed -i '/^UV_EXTRAS=browser,ollama$/d' "$ENV_FILE"
  chmod 0600 "$ENV_FILE"
fi

set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

: "${DOMINION_OLLAMA_BASE_URL:=http://host.docker.internal:11434}"
export DOMINION_OLLAMA_BASE_URL

cp "$ENV_FILE" "$DEERFLOW_ROOT/.env"
chmod 0600 "$DEERFLOW_ROOT/.env"

FRONTEND_ENV="$DEERFLOW_ROOT/frontend/.env"
if [ ! -f "$FRONTEND_ENV" ]; then
  test -r "$DEERFLOW_ROOT/frontend/.env.example"
  install -m 0600 "$DEERFLOW_ROOT/frontend/.env.example" "$FRONTEND_ENV"
fi
test -r "$FRONTEND_ENV"

# DeerFlow v2.0.0 documents Ollama through the harness optional dependency,
# while backend/pyproject.toml depends on plain deerflow-harness. Patch only the
# pinned checkout for the image build, then restore it automatically on exit.
UPSTREAM_PYPROJECT="$DEERFLOW_ROOT/backend/pyproject.toml"
test -r "$UPSTREAM_PYPROJECT"
grep -Fqx '    "deerflow-harness",' "$UPSTREAM_PYPROJECT"
sed -i 's|"deerflow-harness",|"deerflow-harness[ollama]",|' "$UPSTREAM_PYPROJECT"
OLLAMA_DEP_PATCHED=1
grep -Fqx '    "deerflow-harness[ollama]",' "$UPSTREAM_PYPROJECT"

UPSTREAM_DOCKERFILE="$DEERFLOW_ROOT/backend/Dockerfile"
test -r "$UPSTREAM_DOCKERFILE"
BUILDER_MARKER='FROM python:3.12-slim-bookworm AS builder'
grep -Fqx "$BUILDER_MARKER" "$UPSTREAM_DOCKERFILE"
if ! grep -Fq 'DOMINION_FORCE_APT_HTTPS' "$UPSTREAM_DOCKERFILE"; then
  sed -i "/^FROM python:3.12-slim-bookworm AS builder$/a\\
# DOMINION_FORCE_APT_HTTPS\\
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources /etc/apt/sources.list 2>/dev/null || true" "$UPSTREAM_DOCKERFILE"
  APT_HTTPS_PATCHED=1
fi
grep -Fq 'DOMINION_FORCE_APT_HTTPS' "$UPSTREAM_DOCKERFILE"
grep -Fq "s|http://deb.debian.org|https://deb.debian.org|g" "$UPSTREAM_DOCKERFILE"

# The pinned v2.0.0 tree does not contain deerflow.community.browser_automation.
# Keep the production contract honest: web/file tools stay enabled, browser
# automation remains disabled until Dominion moves to a separately reviewed pin.
grep -Fq 'web_search' "$DEERFLOW_ROOT/config.yaml"
! grep -Fq 'browser_automation' "$DEERFLOW_ROOT/config.yaml"
! grep -Fq 'browser_navigate' "$DEERFLOW_ROOT/config.yaml"
grep -Fq 'allow_host_bash: false' "$DEERFLOW_ROOT/config.yaml"

make up

for attempt in $(seq 1 30); do
  if curl --fail --silent --show-error http://127.0.0.1:2026/ >/dev/null; then
    echo "DEERFLOW_RUNTIME_HEALTH=PASS tag=$UPSTREAM_TAG url=http://127.0.0.1:2026/ ollama=harness-extra browser=disabled-v2.0.0"
    exit 0
  fi
  sleep 4
done

echo "DEERFLOW_RUNTIME_HEALTH=FAIL tag=$UPSTREAM_TAG"
docker compose -p deer-flow -f docker/docker-compose.yaml ps || true
docker compose -p deer-flow -f docker/docker-compose.yaml logs --tail=120 gateway || true
exit 1

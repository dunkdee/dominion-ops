#!/usr/bin/env bash
set -Eeuo pipefail

DEPLOY_SHA="${DEPLOY_SHA:-}"
REPO="${DOMINION_REPO:-$HOME/dominion-ops}"
PHASE="bootstrap"
PREVIOUS_SHA=""
ROLLBACK_REQUIRED=0
ROLLBACK_STATUS="not-required"

sanitize_command() {
  local command_text="${1:-unknown}"
  command_text="${command_text//$'\n'/ }"
  printf '%s' "${command_text:0:180}"
}

normalize_origin_target() {
  local origin_url="${1:-}"
  local normalized=""

  origin_url="${origin_url%/}"
  origin_url="${origin_url%.git}"

  case "$origin_url" in
    git@github.com:*)
      normalized="${origin_url#git@github.com:}"
      ;;
    ssh://git@github.com:22/*)
      normalized="${origin_url#ssh://git@github.com:22/}"
      ;;
    ssh://git@github.com/*)
      normalized="${origin_url#ssh://git@github.com/}"
      ;;
    https://github.com/*)
      normalized="${origin_url#https://github.com/}"
      ;;
    https://*@github.com/*)
      normalized="${origin_url#https://*@github.com/}"
      ;;
  esac

  printf '%s' "$normalized"
}

diagnostics() {
  echo "::group::Foundation VM deployment diagnostics"
  echo "phase=$PHASE"
  echo "host=$(hostname)"
  echo "repo=$REPO"
  echo "requested_sha=${DEPLOY_SHA:-unset}"
  echo "previous_sha=${PREVIOUS_SHA:-unset}"

  if [ -d "$REPO/.git" ]; then
    (
      cd "$REPO"
      echo "current_sha=$(git rev-parse HEAD 2>/dev/null || echo unknown)"
      echo "disk_free_kb=$(df -Pk . | awk 'NR==2 {print $4}')"
      docker compose ps || true
      echo "health_8080:"
      curl --max-time 5 --fail --silent --show-error http://127.0.0.1:8080/ >/dev/null && echo ok || echo failed
      echo "health_8090:"
      curl --max-time 5 --fail --silent --show-error http://127.0.0.1:8090/ >/dev/null && echo ok || echo failed
      docker compose logs --tail=40 || true
    )
  else
    echo "repository_state=missing"
  fi
  echo "::endgroup::"
}

on_error() {
  local rc=$?
  local failed_line="${BASH_LINENO[0]:-unknown}"
  local failed_command
  failed_command="$(sanitize_command "${BASH_COMMAND:-unknown}")"
  trap - ERR

  printf 'DEPLOY_FAILURE phase=%s line=%s rc=%s command=%q\n' \
    "$PHASE" "$failed_line" "$rc" "$failed_command"
  diagnostics

  if [ "$ROLLBACK_REQUIRED" -eq 1 ] && [ -n "$PREVIOUS_SHA" ]; then
    PHASE="rollback"
    echo "Deployment failed; restoring $PREVIOUS_SHA"
    if git checkout --detach "$PREVIOUS_SHA" \
      && docker compose up -d --build \
      && docker compose ps; then
      ROLLBACK_STATUS="success"
    else
      ROLLBACK_STATUS="failure"
    fi
    printf 'DEPLOY_ROLLBACK status=%s previous_sha=%s\n' "$ROLLBACK_STATUS" "$PREVIOUS_SHA"
  fi

  exit "$rc"
}
trap on_error ERR

PHASE="validate-input"
[[ "$DEPLOY_SHA" =~ ^[0-9a-fA-F]{40}$ ]] || {
  echo "A full 40-character deployment SHA is required"
  false
}

PHASE="repository-path"
[ -d "$REPO/.git" ] || {
  echo "Repository is missing at the governed path: $REPO"
  false
}
cd "$REPO"

PHASE="repository-origin"
origin_url="$(git remote get-url origin 2>/dev/null || true)"
origin_target="$(normalize_origin_target "$origin_url")"
[ "$origin_target" = "dunkdee/dominion-ops" ] || {
  echo "Repository origin does not resolve to the governed dunkdee/dominion-ops target"
  false
}

PHASE="docker-preflight"
command -v docker >/dev/null || {
  echo "Docker is not installed or not available to the deployment user"
  false
}
docker compose version >/dev/null || {
  echo "Docker Compose is not available to the deployment user"
  false
}

PHASE="disk-preflight"
free_kb="$(df -Pk . | awk 'NR==2 {print $4}')"
[ "$free_kb" -gt 1048576 ] || {
  echo "Foundation VM has less than 1 GiB of free repository filesystem space"
  false
}

PHASE="git-fetch"
git fetch --prune origin main

PHASE="commit-verification"
git cat-file -e "${DEPLOY_SHA}^{commit}"
git merge-base --is-ancestor "$DEPLOY_SHA" origin/main || {
  echo "Requested deployment SHA is not reachable from origin/main on the VM"
  false
}

PREVIOUS_SHA="$(git rev-parse HEAD)"
ROLLBACK_REQUIRED=1

PHASE="checkout"
git checkout --detach "$DEPLOY_SHA"

PHASE="governance-validation"
python3 scripts/validate_constitutional_kernel_v1.py
python3 scripts/validate_control_plane.py
python3 scripts/validate_control_plane_runtime.py

PHASE="compose-validation"
docker compose config --quiet

PHASE="compose-up"
docker compose up -d --build

PHASE="health-check"
healthy=0
for attempt in $(seq 1 18); do
  if curl --max-time 5 --fail --silent --show-error http://127.0.0.1:8080/ >/dev/null \
    && curl --max-time 5 --fail --silent --show-error http://127.0.0.1:8090/ >/dev/null; then
    healthy=1
    break
  fi
  echo "Health check attempt ${attempt}/18 failed; retrying in 5 seconds"
  sleep 5
done

[ "$healthy" -eq 1 ] || {
  echo "Deployment health checks failed after 18 attempts"
  false
}

docker compose ps
ROLLBACK_REQUIRED=0
trap - ERR
printf 'DEPLOY_SUCCESS requested_sha=%s previous_sha=%s\n' "$DEPLOY_SHA" "$PREVIOUS_SHA"

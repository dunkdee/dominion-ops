#!/usr/bin/env bash
set -Eeuo pipefail

DEPLOY_SHA="${DEPLOY_SHA:-}"
DEPLOY_BUNDLE_PATH="${DEPLOY_BUNDLE_PATH:-}"
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

  case "$origin_url" in
    *://*)
      normalized="${origin_url#*://}"
      normalized="${normalized#*@}"
      normalized="${normalized#*/}"
      ;;
    *@*:*|*:*)
      normalized="${origin_url#*:}"
      ;;
    *)
      normalized="$origin_url"
      ;;
  esac

  normalized="${normalized#/}"
  normalized="${normalized%/}"
  normalized="${normalized%.git}"
  normalized="${normalized,,}"
  printf '%s' "$normalized"
}

cleanup_bundle() {
  case "$DEPLOY_BUNDLE_PATH" in
    /tmp/dominion-deploy-[0-9]*-[0-9]*.bundle)
      rm -f -- "$DEPLOY_BUNDLE_PATH" || true
      ;;
  esac
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

  cleanup_bundle
  exit "$rc"
}
trap on_error ERR

PHASE="validate-input"
[[ "$DEPLOY_SHA" =~ ^[0-9a-fA-F]{40}$ ]] || {
  echo "A full 40-character deployment SHA is required"
  false
}
[[ "$DEPLOY_BUNDLE_PATH" =~ ^/tmp/dominion-deploy-[0-9]+-[0-9]+\.bundle$ ]] || {
  echo "The deployment bundle path is invalid"
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
echo "Repository origin target: ${origin_target:-unrecognized}"
[ "$origin_target" = "dunkdee/dominion-ops" ] || {
  echo "Repository origin path does not resolve to the governed dunkdee/dominion-ops target"
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

PHASE="bundle-preflight"
[ -f "$DEPLOY_BUNDLE_PATH" ] || {
  echo "Authorized deployment bundle is missing"
  false
}
[ ! -L "$DEPLOY_BUNDLE_PATH" ] || {
  echo "Authorized deployment bundle must not be a symbolic link"
  false
}
[ "$(stat -c '%U' "$DEPLOY_BUNDLE_PATH")" = "$(id -un)" ] || {
  echo "Authorized deployment bundle is not owned by the deployment user"
  false
}
git bundle verify "$DEPLOY_BUNDLE_PATH"

PHASE="git-import"
git fetch --force "$DEPLOY_BUNDLE_PATH" refs/heads/main:refs/remotes/origin/main

PHASE="commit-verification"
git cat-file -e "${DEPLOY_SHA}^{commit}"
git merge-base --is-ancestor "$DEPLOY_SHA" origin/main || {
  echo "Requested deployment SHA is not reachable from bundled main history"
  false
}
printf 'DEPLOY_ORIGIN target=%s source=bundle authorized_sha=%s\n' "$origin_target" "$DEPLOY_SHA"
cleanup_bundle

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
cleanup_bundle
printf 'DEPLOY_SUCCESS requested_sha=%s previous_sha=%s\n' "$DEPLOY_SHA" "$PREVIOUS_SHA"

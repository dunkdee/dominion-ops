#!/usr/bin/env bash
set -Eeuo pipefail

DEPLOY_SHA="${DEPLOY_SHA:-}"
DEPLOY_BUNDLE_PATH="${DEPLOY_BUNDLE_PATH:-}"
REPO="${DOMINION_REPO:-$HOME/dominion-ops}"
PHASE="bootstrap"
PREVIOUS_SHA=""
ROLLBACK_REQUIRED=0
ROLLBACK_STATUS="not-required"
FAILURE_DETAIL="none"
LOCAL_STATE_BACKUP=""
LOCAL_STATE_QUARANTINED=0
LOCAL_STATE_RESTORE_STATUS="not-required"

sanitize_command() {
  local command_text="${1:-unknown}"
  command_text="${command_text//$'\n'/ }"
  printf '%s' "${command_text:0:180}"
}

sanitize_failure_detail() {
  local detail="${1:-none}"
  detail="${detail//$'\r'/ }"
  detail="${detail//$'\n'/; }"
  printf '%s' "${detail:0:480}"
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

summarize_status_paths() {
  local status_line path lower_path
  local count=0
  local summary=""

  while IFS= read -r status_line; do
    [ -n "$status_line" ] || continue
    path="${status_line:3}"
    lower_path="${path,,}"

    case "$lower_path" in
      *".env"*|*secret*|*credential*|*private*|*token*|*key*)
        path="[sensitive-path]"
        ;;
    esac

    path="${path//$'\t'/ }"
    path="${path//$'\n'/ }"

    if [ "$count" -lt 6 ]; then
      [ -z "$summary" ] || summary+=","
      summary+="${path:0:80}"
    fi
    count=$((count + 1))
  done

  printf '%s' "${summary:-none}"
}

worktree_detail() {
  local status tracked_count untracked_count unmerged_count paths
  status="$(git status --porcelain=v1 --untracked-files=all 2>/dev/null || true)"

  if [ -z "$status" ]; then
    printf 'tracked=0,untracked=0,unmerged=0,paths=none'
    return
  fi

  tracked_count="$(printf '%s\n' "$status" | awk 'substr($0,1,2)!="??" {n++} END {print n+0}')"
  untracked_count="$(printf '%s\n' "$status" | awk 'substr($0,1,2)=="??" {n++} END {print n+0}')"
  unmerged_count="$(git ls-files -u 2>/dev/null | wc -l | tr -d ' ')"
  paths="$(printf '%s\n' "$status" | summarize_status_paths)"

  printf 'tracked=%s,untracked=%s,unmerged=%s,paths=%s' \
    "$tracked_count" "$untracked_count" "$unmerged_count" "$paths"
}

restore_local_state() {
  local rc=0
  local restore_output=""

  if [ "$LOCAL_STATE_QUARANTINED" -ne 1 ] || [ -z "$LOCAL_STATE_BACKUP" ]; then
    LOCAL_STATE_RESTORE_STATUS="not-required"
    return 0
  fi

  set +e
  # Move HEAD and worktree back to the previous release. `switch --detach`
  # without --force refuses on unexpected drift instead of destroying it,
  # which is the fail-closed behaviour governance requires.
  git switch --detach --quiet "$PREVIOUS_SHA"
  git clean -fdq

  if [ -s "$LOCAL_STATE_BACKUP/index.patch" ]; then
    git apply --index --binary --whitespace=nowarn "$LOCAL_STATE_BACKUP/index.patch"
    rc=$?
  fi

  if [ "$rc" -eq 0 ] && [ -s "$LOCAL_STATE_BACKUP/worktree.patch" ]; then
    git apply --binary --whitespace=nowarn "$LOCAL_STATE_BACKUP/worktree.patch"
    rc=$?
  fi

  if [ "$rc" -eq 0 ] && [ -s "$LOCAL_STATE_BACKUP/untracked.tar.gz" ]; then
    restore_output="$(tar --extract --gzip --file="$LOCAL_STATE_BACKUP/untracked.tar.gz" --directory="$REPO" 2>&1)"
    rc=$?
  fi
  set -e

  if [ "$rc" -eq 0 ]; then
    LOCAL_STATE_RESTORE_STATUS="success"
    return 0
  fi

  LOCAL_STATE_RESTORE_STATUS="failure"
  FAILURE_DETAIL="local_state_restore_rc=${rc};output=$(sanitize_failure_detail "$restore_output")"
  return 1
}

quarantine_local_state() {
  local status detail backup_id tracked_count untracked_count unmerged_count
  local tar_rc=0

  status="$(git status --porcelain=v1 --untracked-files=all 2>/dev/null || true)"
  [ -n "$status" ] || return 0

  detail="$(worktree_detail)"
  tracked_count="$(printf '%s' "$detail" | sed -n 's/^tracked=\([0-9][0-9]*\).*/\1/p')"
  untracked_count="$(printf '%s' "$detail" | sed -n 's/.*untracked=\([0-9][0-9]*\).*/\1/p')"
  unmerged_count="$(printf '%s' "$detail" | sed -n 's/.*unmerged=\([0-9][0-9]*\).*/\1/p')"

  if [ "${unmerged_count:-0}" -ne 0 ]; then
    FAILURE_DETAIL="$detail"
    echo "Governed deployment target contains unmerged paths: $(sanitize_failure_detail "$detail")"
    false
  fi

  PHASE="worktree-quarantine"
  backup_id="${DEPLOY_BUNDLE_PATH##*/}"
  backup_id="${backup_id#dominion-deploy-}"
  backup_id="${backup_id%.bundle}"
  LOCAL_STATE_BACKUP="$HOME/.local/state/dominion-deploy/backups/$backup_id"

  umask 077
  install -d -m 700 "$HOME/.local/state/dominion-deploy/backups"
  [ ! -e "$LOCAL_STATE_BACKUP" ] || {
    FAILURE_DETAIL="backup_path_already_exists"
    echo "A deployment-state backup already exists for this run"
    false
  }
  install -d -m 700 "$LOCAL_STATE_BACKUP"

  git diff --cached --binary HEAD > "$LOCAL_STATE_BACKUP/index.patch"
  git diff --binary > "$LOCAL_STATE_BACKUP/worktree.patch"

  if [ "${untracked_count:-0}" -gt 0 ]; then
    set +e
    git ls-files --others --exclude-standard -z \
      | tar --null --files-from=- --create --gzip --file="$LOCAL_STATE_BACKUP/untracked.tar.gz"
    tar_rc=${PIPESTATUS[1]}
    set -e
    [ "$tar_rc" -eq 0 ] || {
      FAILURE_DETAIL="untracked_archive_rc=${tar_rc};${detail}"
      echo "Unable to create the protected untracked-file archive"
      false
    }
  else
    : > "$LOCAL_STATE_BACKUP/untracked.tar.gz"
  fi

  {
    printf 'previous_sha=%s\n' "$PREVIOUS_SHA"
    printf 'requested_sha=%s\n' "$DEPLOY_SHA"
    printf 'tracked_count=%s\n' "${tracked_count:-0}"
    printf 'untracked_count=%s\n' "${untracked_count:-0}"
    printf 'unmerged_count=%s\n' "${unmerged_count:-0}"
    sha256sum \
      "$LOCAL_STATE_BACKUP/index.patch" \
      "$LOCAL_STATE_BACKUP/worktree.patch" \
      "$LOCAL_STATE_BACKUP/untracked.tar.gz"
  } > "$LOCAL_STATE_BACKUP/manifest.txt"
  chmod 600 "$LOCAL_STATE_BACKUP"/*

  LOCAL_STATE_QUARANTINED=1
  # Drift is already captured in $LOCAL_STATE_BACKUP above.
  git restore --source=HEAD --staged --worktree -- .
  git clean -fdq

  [ -z "$(git status --porcelain=v1 --untracked-files=all)" ] || {
    FAILURE_DETAIL="post_quarantine_state=$(worktree_detail)"
    echo "Deployment target remained dirty after protected quarantine"
    false
  }

  printf 'DEPLOY_LOCAL_STATE status=quarantined backup=%s detail=%s\n' \
    "$LOCAL_STATE_BACKUP" "$(sanitize_failure_detail "$detail")"
}

diagnostics() {
  echo "::group::Foundation VM deployment diagnostics"
  echo "phase=$PHASE"
  echo "host=$(hostname)"
  echo "repo=$REPO"
  echo "requested_sha=${DEPLOY_SHA:-unset}"
  echo "previous_sha=${PREVIOUS_SHA:-unset}"
  echo "local_state_backup=${LOCAL_STATE_BACKUP:-none}"
  echo "local_state_restore=${LOCAL_STATE_RESTORE_STATUS}"

  if [ -d "$REPO/.git" ]; then
    (
      cd "$REPO"
      echo "current_sha=$(git rev-parse HEAD 2>/dev/null || echo unknown)"
      echo "worktree=$(worktree_detail)"
      echo "disk_free_kb=$(df -Pk . | awk 'NR==2 {print $4}')"

      case "$PHASE" in
        compose-up|health-check|rollback)
          docker compose ps || true
          echo "health_8080:"
          curl --max-time 5 --fail --silent --show-error http://127.0.0.1:8080/ >/dev/null && echo ok || echo failed
          echo "health_8090:"
          curl --max-time 5 --fail --silent --show-error http://127.0.0.1:8090/ >/dev/null && echo ok || echo failed
          docker compose logs --tail=40 || true
          ;;
        *)
          echo "runtime_diagnostics=deferred-before-service-change"
          ;;
      esac
    )
  else
    echo "repository_state=missing"
  fi
  echo "::endgroup::"
}

on_error() {
  local rc=$?
  local failed_line="${BASH_LINENO[0]:-unknown}"
  local failed_command detail
  local checkout_ok=0
  local restore_ok=0
  local compose_ok=0

  failed_command="$(sanitize_command "${BASH_COMMAND:-unknown}")"
  detail="$(sanitize_failure_detail "${FAILURE_DETAIL:-none}")"
  trap - ERR

  printf 'DEPLOY_FAILURE phase=%s line=%s rc=%s command=%q detail=%q\n' \
    "$PHASE" "$failed_line" "$rc" "$failed_command" "$detail"
  diagnostics

  if [ -n "$PREVIOUS_SHA" ]; then
    PHASE="rollback"

    set +e
    git switch --detach --quiet "$PREVIOUS_SHA" >/dev/null 2>&1
    [ "$?" -eq 0 ] && checkout_ok=1

    if [ "$checkout_ok" -eq 1 ] && restore_local_state; then
      restore_ok=1
    fi

    if [ "$ROLLBACK_REQUIRED" -eq 1 ] && [ "$checkout_ok" -eq 1 ] && [ "$restore_ok" -eq 1 ]; then
      docker compose up -d --build >/dev/null 2>&1 \
        && docker compose ps >/dev/null 2>&1
      [ "$?" -eq 0 ] && compose_ok=1

      if [ "$compose_ok" -eq 1 ]; then
        ROLLBACK_STATUS="success"
      else
        ROLLBACK_STATUS="failure"
      fi
    elif [ "$ROLLBACK_REQUIRED" -eq 0 ] && [ "$checkout_ok" -eq 1 ] && [ "$restore_ok" -eq 1 ]; then
      ROLLBACK_STATUS="not-required"
    else
      ROLLBACK_STATUS="failure"
    fi
    set -e

    printf 'DEPLOY_ROLLBACK status=%s previous_sha=%s local_state_restore=%s\n' \
      "$ROLLBACK_STATUS" "$PREVIOUS_SHA" "$LOCAL_STATE_RESTORE_STATUS"
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
PHASE="working-tree-preflight"
quarantine_local_state

PHASE="checkout"
set +e
checkout_output="$(git checkout --detach "$DEPLOY_SHA" 2>&1)"
checkout_rc=$?
set -e

if [ "$checkout_rc" -ne 0 ]; then
  FAILURE_DETAIL="checkout_rc=${checkout_rc};output=$(sanitize_failure_detail "$checkout_output");$(worktree_detail)"
  false
fi

ROLLBACK_REQUIRED=1

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
printf 'DEPLOY_SUCCESS requested_sha=%s previous_sha=%s local_state_backup=%s\n' \
  "$DEPLOY_SHA" "$PREVIOUS_SHA" "${LOCAL_STATE_BACKUP:-none}"

#!/usr/bin/env bash
set -euo pipefail

: "${RUN_ID:?RUN_ID is required}"
repo="${DOMINION_REPO:-$HOME/dominion-ops}"
backup_root="$HOME/.local/state/dominion-deploy/backups"

ssh_alias_is_github() {
  local alias="${1:-}"
  local cfg host user port

  [[ "$alias" =~ ^[A-Za-z0-9._-]+$ ]] || return 1
  command -v ssh >/dev/null 2>&1 || return 1
  cfg="$(ssh -G "$alias" 2>/dev/null)" || return 1
  host="$(printf '%s\n' "$cfg" | awk 'tolower($1)=="hostname" {print tolower($2); exit}')"
  user="$(printf '%s\n' "$cfg" | awk 'tolower($1)=="user" {print tolower($2); exit}')"
  port="$(printf '%s\n' "$cfg" | awk 'tolower($1)=="port" {print $2; exit}')"

  [ "$user" = "git" ] || return 1
  if [ "$host" = "github.com" ] && [ "$port" = "22" ]; then
    return 0
  fi
  if [ "$host" = "ssh.github.com" ] && [ "$port" = "443" ]; then
    return 0
  fi
  return 1
}

normalize_origin_target() {
  local origin_url="${1:-}"
  local normalized="" authority="" origin_user="" alias=""

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
    ssh://git@ssh.github.com:443/*)
      normalized="${origin_url#ssh://git@ssh.github.com:443/}"
      ;;
    https://github.com/*)
      normalized="${origin_url#https://github.com/}"
      ;;
    https://*@github.com/*)
      normalized="${origin_url#https://*@github.com/}"
      ;;
    *@*:* )
      authority="${origin_url%%:*}"
      origin_user="${authority%@*}"
      alias="${authority##*@}"
      if [ "$origin_user" = "git" ] && ssh_alias_is_github "$alias"; then
        normalized="${origin_url#*:}"
      fi
      ;;
  esac

  normalized="${normalized#/}"
  normalized="${normalized%/}"
  normalized="${normalized%.git}"
  printf '%s' "${normalized,,}"
}

origin_fingerprint() {
  local origin_url="${1:-}"
  local lower kind="other" authority="" host="" path="" github_host=0 expected_path=0 userinfo=0 alias_verified=0 alias="" origin_user=""
  lower="${origin_url,,}"
  lower="${lower%/}"
  lower="${lower%.git}"

  case "$lower" in
    https://*|http://*)
      kind="http"
      authority="${lower#*://}"
      path="${authority#*/}"
      authority="${authority%%/*}"
      [[ "$authority" == *@* ]] && userinfo=1
      host="${authority##*@}"
      host="${host%%:*}"
      ;;
    ssh://*)
      kind="ssh-url"
      authority="${lower#ssh://}"
      path="${authority#*/}"
      authority="${authority%%/*}"
      [[ "$authority" == *@* ]] && userinfo=1
      host="${authority##*@}"
      host="${host%%:*}"
      ;;
    *@*:*|*:*)
      kind="ssh-scp"
      authority="${lower%%:*}"
      path="${lower#*:}"
      [[ "$authority" == *@* ]] && userinfo=1
      host="${authority##*@}"
      if [ "$userinfo" -eq 1 ]; then
        origin_user="${authority%@*}"
        alias="${authority##*@}"
        if [ "$origin_user" = "git" ] && ssh_alias_is_github "$alias"; then alias_verified=1; fi
      fi
      ;;
    file://*|/*)
      kind="file"
      path="$lower"
      ;;
  esac

  path="${path#/}"
  path="${path%/}"
  path="${path%.git}"
  [ "$host" = "github.com" ] && github_host=1
  [ "$path" = "dunkdee/dominion-ops" ] && expected_path=1
  printf 'kind=%s github_host=%s expected_path=%s userinfo=%s alias_verified=%s' "$kind" "$github_host" "$expected_path" "$userinfo" "$alias_verified"
}

test -d "$repo/.git" || { echo "VM_DRIFT_QUARANTINE=FAIL reason=repo_missing"; exit 1; }
cd "$repo"
origin="$(git remote get-url origin 2>/dev/null || true)"
origin_target="$(normalize_origin_target "$origin")"
if [ "$origin_target" != "dunkdee/dominion-ops" ]; then
  echo "VM_DRIFT_QUARANTINE=FAIL reason=origin_mismatch $(origin_fingerprint "$origin")"
  exit 1
fi

status="$(git status --porcelain=v1 --untracked-files=all 2>/dev/null || true)"
if [ -z "$status" ]; then
  echo "VM_DRIFT_QUARANTINE=PASS state=clean backup=none"
  exit 0
fi

unmerged_count="$(git ls-files -u | wc -l | tr -d ' ')"
tracked_count="$(printf '%s\n' "$status" | awk 'substr($0,1,2)!="??" {n++} END {print n+0}')"
untracked_count="$(printf '%s\n' "$status" | awk 'substr($0,1,2)=="??" {n++} END {print n+0}')"
if [ "$unmerged_count" -ne 0 ]; then
  echo "VM_DRIFT_QUARANTINE=FAIL reason=unmerged_paths tracked=$tracked_count untracked=$untracked_count unmerged=$unmerged_count"
  exit 1
fi

previous_sha="$(git rev-parse HEAD)"
backup="$backup_root/brain-${RUN_ID}-${previous_sha:0:12}"
umask 077
install -d -m 700 "$backup_root"
test ! -e "$backup" || { echo "VM_DRIFT_QUARANTINE=FAIL reason=backup_collision"; exit 1; }
install -d -m 700 "$backup"

git diff --cached --binary HEAD > "$backup/index.patch"
git diff --binary > "$backup/worktree.patch"
if [ "$untracked_count" -gt 0 ]; then
  set +e
  git ls-files --others --exclude-standard -z \
    | tar --null --files-from=- --create --gzip --file="$backup/untracked.tar.gz"
  tar_rc=${PIPESTATUS[1]}
  set -e
  test "$tar_rc" -eq 0 || { echo "VM_DRIFT_QUARANTINE=FAIL reason=untracked_archive"; exit 1; }
else
  : > "$backup/untracked.tar.gz"
fi

{
  printf 'previous_sha=%s\n' "$previous_sha"
  printf 'tracked_count=%s\n' "$tracked_count"
  printf 'untracked_count=%s\n' "$untracked_count"
  printf 'unmerged_count=%s\n' "$unmerged_count"
  sha256sum "$backup/index.patch" "$backup/worktree.patch" "$backup/untracked.tar.gz"
} > "$backup/manifest.txt"
chmod 600 "$backup"/*

# Quarantine only version-control-visible local drift. Ignored runtime secrets remain untouched.
git reset --hard --quiet HEAD
git clean -fdq
post="$(git status --porcelain=v1 --untracked-files=all 2>/dev/null || true)"
test -z "$post" || { echo "VM_DRIFT_QUARANTINE=FAIL reason=post_clean_still_dirty"; exit 1; }

printf 'VM_DRIFT_QUARANTINE=PASS state=quarantined tracked=%s untracked=%s unmerged=0 backup=%s previous_sha=%s\n' \
  "$tracked_count" "$untracked_count" "$backup" "$previous_sha"

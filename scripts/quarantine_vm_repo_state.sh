#!/usr/bin/env bash
set -euo pipefail

: "${RUN_ID:?RUN_ID is required}"
repo="${DOMINION_REPO:-$HOME/dominion-ops}"
backup_root="$HOME/.local/state/dominion-deploy/backups"

test -d "$repo/.git" || { echo "VM_DRIFT_QUARANTINE=FAIL reason=repo_missing"; exit 1; }
cd "$repo"
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

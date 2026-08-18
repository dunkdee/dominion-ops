#!/usr/bin/env bash
set -euo pipefail

INSTALL_CONFIRM='INSTALL LOCAL RUNTIME AUTOMATION'
ROLLBACK_CONFIRM='ROLLBACK LOCAL RUNTIME AUTOMATION'
BACKUP_ROOT=/var/backups/dominion-runtime-automation
LIB_DIR=/usr/local/lib/dominion
STATE_DIR=/var/lib/dominion/runtime-automation

expected_sha=''
confirmation=''
rollback_dir=''

while [[ $# -gt 0 ]]; do
  case "$1" in
    --expected-sha)
      expected_sha="${2:-}"
      shift 2
      ;;
    --confirm)
      confirmation="${2:-}"
      shift 2
      ;;
    --rollback)
      rollback_dir="${2:-}"
      shift 2
      ;;
    *)
      echo "INSTALL_LOCAL_AUTOMATION=BLOCKED reason=unknown_argument argument=$1" >&2
      exit 2
      ;;
  esac
done

[[ "$EUID" -eq 0 ]] || {
  echo 'INSTALL_LOCAL_AUTOMATION=BLOCKED reason=root_required' >&2
  exit 2
}

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(git -C "$script_dir/.." rev-parse --show-toplevel 2>/dev/null || true)"

targets=(
  /usr/local/lib/dominion/runtime_observer.sh
  /usr/local/lib/dominion/buddy_bounded_self_heal.sh
  /etc/systemd/system/dominion-runtime-observer.service
  /etc/systemd/system/dominion-runtime-observer.timer
  /etc/systemd/system/dominion-buddy-self-heal.service
  /etc/systemd/system/dominion-buddy-self-heal.timer
)
timers=(
  dominion-runtime-observer.timer
  dominion-buddy-self-heal.timer
)

backup_name() {
  printf '%s' "${1#/}" | tr '/' '_'
}

restore_backup() {
  local backup="$1" target name enabled active timer
  [[ -d "$backup" && "$backup" == "$BACKUP_ROOT"/* ]] || {
    echo 'LOCAL_AUTOMATION_ROLLBACK=BLOCKED reason=invalid_backup_directory' >&2
    return 2
  }

  for timer in "${timers[@]}"; do
    systemctl disable --now "$timer" >/dev/null 2>&1 || true
  done

  for target in "${targets[@]}"; do
    name="$(backup_name "$target")"
    if [[ -f "$backup/files/$name" ]]; then
      install -D -m "$(stat -c '%a' "$backup/files/$name")" \
        "$backup/files/$name" "$target"
    elif [[ -f "$backup/absent/$name" ]]; then
      rm -f -- "$target"
    else
      echo "LOCAL_AUTOMATION_ROLLBACK=BLOCKED reason=backup_incomplete target=$target" >&2
      return 2
    fi
  done

  systemctl daemon-reload
  while IFS='|' read -r timer enabled active; do
    [[ -n "$timer" ]] || continue
    if [[ "$enabled" == enabled ]]; then
      systemctl enable "$timer" >/dev/null
    fi
    if [[ "$active" == active ]]; then
      systemctl start "$timer"
    fi
  done <"$backup/timer-state"
  echo "LOCAL_AUTOMATION_ROLLBACK=PASS backup=$backup"
}

if [[ -n "$rollback_dir" ]]; then
  [[ "$confirmation" == "$ROLLBACK_CONFIRM" ]] || {
    echo 'LOCAL_AUTOMATION_ROLLBACK=BLOCKED reason=confirmation_mismatch' >&2
    exit 2
  }
  rollback_dir="$(realpath -e -- "$rollback_dir" 2>/dev/null || true)"
  restore_backup "$rollback_dir"
  exit 0
fi

[[ "$confirmation" == "$INSTALL_CONFIRM" ]] || {
  echo 'INSTALL_LOCAL_AUTOMATION=BLOCKED reason=confirmation_mismatch' >&2
  exit 2
}
[[ "$expected_sha" =~ ^[0-9a-f]{40}$ ]] || {
  echo 'INSTALL_LOCAL_AUTOMATION=BLOCKED reason=invalid_expected_sha' >&2
  exit 2
}
[[ -n "$repo_root" ]] || {
  echo 'INSTALL_LOCAL_AUTOMATION=BLOCKED reason=repository_not_found' >&2
  exit 2
}

actual_sha="$(git -C "$repo_root" rev-parse HEAD)"
branch="$(git -C "$repo_root" branch --show-current)"
[[ "$actual_sha" == "$expected_sha" ]] || {
  echo "INSTALL_LOCAL_AUTOMATION=BLOCKED reason=sha_mismatch expected=$expected_sha actual=$actual_sha" >&2
  exit 2
}
[[ "$branch" == main ]] || {
  echo "INSTALL_LOCAL_AUTOMATION=BLOCKED reason=main_branch_required actual=$branch" >&2
  exit 2
}
[[ -z "$(git -C "$repo_root" status --porcelain=v1 --untracked-files=no)" ]] || {
  echo 'INSTALL_LOCAL_AUTOMATION=BLOCKED reason=tracked_worktree_dirty' >&2
  exit 2
}

sources=(
  "$repo_root/scripts/runtime_observer.sh"
  "$repo_root/scripts/buddy_bounded_self_heal.sh"
  "$repo_root/operations/systemd/dominion-runtime-observer.service"
  "$repo_root/operations/systemd/dominion-runtime-observer.timer"
  "$repo_root/operations/systemd/dominion-buddy-self-heal.service"
  "$repo_root/operations/systemd/dominion-buddy-self-heal.timer"
)

for source in "${sources[@]}"; do
  [[ -f "$source" && ! -L "$source" ]] || {
    echo "INSTALL_LOCAL_AUTOMATION=BLOCKED reason=source_missing_or_symlink path=$source" >&2
    exit 2
  }
done
for target in "${targets[@]}"; do
  [[ ! -L "$target" ]] || {
    echo "INSTALL_LOCAL_AUTOMATION=BLOCKED reason=target_symlink path=$target" >&2
    exit 2
  }
done

bash -n "$repo_root/scripts/runtime_observer.sh"
bash -n "$repo_root/scripts/buddy_bounded_self_heal.sh"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup="$BACKUP_ROOT/$timestamp-$expected_sha"
install -d -m 0700 "$backup/files" "$backup/absent" "$LIB_DIR" "$STATE_DIR"

for timer in "${timers[@]}"; do
  printf '%s|%s|%s\n' "$timer" \
    "$(systemctl is-enabled "$timer" 2>/dev/null || true)" \
    "$(systemctl is-active "$timer" 2>/dev/null || true)" \
    >>"$backup/timer-state"
done

for target in "${targets[@]}"; do
  name="$(backup_name "$target")"
  if [[ -f "$target" ]]; then
    cp -a -- "$target" "$backup/files/$name"
  else
    : >"$backup/absent/$name"
  fi
done

committed=0
rollback_on_error() {
  rc=$?
  if [[ "$committed" -eq 0 ]]; then
    restore_backup "$backup" || true
  fi
  echo "INSTALL_LOCAL_AUTOMATION=FAIL rc=$rc backup=$backup" >&2
  exit "$rc"
}
trap rollback_on_error ERR

install -m 0755 "$repo_root/scripts/runtime_observer.sh" \
  "$LIB_DIR/runtime_observer.sh"
install -m 0755 "$repo_root/scripts/buddy_bounded_self_heal.sh" \
  "$LIB_DIR/buddy_bounded_self_heal.sh"
install -m 0644 "$repo_root/operations/systemd/dominion-runtime-observer.service" \
  /etc/systemd/system/dominion-runtime-observer.service
install -m 0644 "$repo_root/operations/systemd/dominion-runtime-observer.timer" \
  /etc/systemd/system/dominion-runtime-observer.timer
install -m 0644 "$repo_root/operations/systemd/dominion-buddy-self-heal.service" \
  /etc/systemd/system/dominion-buddy-self-heal.service
install -m 0644 "$repo_root/operations/systemd/dominion-buddy-self-heal.timer" \
  /etc/systemd/system/dominion-buddy-self-heal.timer

systemctl daemon-reload
systemd-analyze verify \
  /etc/systemd/system/dominion-runtime-observer.service \
  /etc/systemd/system/dominion-runtime-observer.timer \
  /etc/systemd/system/dominion-buddy-self-heal.service \
  /etc/systemd/system/dominion-buddy-self-heal.timer
systemctl enable --now "${timers[@]}"
for timer in "${timers[@]}"; do
  systemctl is-enabled --quiet "$timer"
  systemctl is-active --quiet "$timer"
done

heal_rc=0
systemctl start dominion-buddy-self-heal.service || heal_rc=$?
observer_rc=0
systemctl start dominion-runtime-observer.service || observer_rc=$?

if [[ "$observer_rc" -ne 0 || "$heal_rc" -ne 0 ]]; then
  printf 'observer_acceptance_exit=%s\nhealer_acceptance_exit=%s\n' \
    "$observer_rc" "$heal_rc" >"$backup/acceptance-failure"
  chmod 0600 "$backup/acceptance-failure"
  trap - ERR
  if ! restore_backup "$backup"; then
    echo "LOCAL_RUNTIME_ACCEPTANCE=ROLLBACK_FAILED backup=$backup" >&2
    exit 4
  fi
  echo "LOCAL_RUNTIME_ACCEPTANCE=ROLLED_BACK backup=$backup"
  echo "OBSERVER_ACCEPTANCE_EXIT=$observer_rc"
  echo "HEALER_ACCEPTANCE_EXIT=$heal_rc"
  exit 3
fi

observer_hash="$(sha256sum "$LIB_DIR/runtime_observer.sh" | awk '{print $1}')"
healer_hash="$(sha256sum "$LIB_DIR/buddy_bounded_self_heal.sh" | awk '{print $1}')"
receipt="$STATE_DIR/install-receipt.json"
python3 - "$receipt" "$expected_sha" "$backup" "$observer_hash" \
  "$healer_hash" "$observer_rc" "$heal_rc" <<'PY'
import json
import os
import sys
from datetime import datetime, timezone

path, sha, backup, observer_hash, healer_hash, observer_rc, healer_rc = sys.argv[1:]
record = {
    "schema": "dominion-local-runtime-automation-install-v1",
    "installed_at": datetime.now(timezone.utc).isoformat(),
    "source_commit": sha,
    "backup_directory": backup,
    "observer_sha256": observer_hash,
    "healer_sha256": healer_hash,
    "observer_acceptance_exit": int(observer_rc),
    "healer_acceptance_exit": int(healer_rc),
    "timers_enabled": True,
}
tmp = path + ".tmp"
with open(tmp, "w", encoding="utf-8") as handle:
    json.dump(record, handle, indent=2, sort_keys=True)
    handle.write("\n")
os.chmod(tmp, 0o600)
os.replace(tmp, path)
PY

committed=1
trap - ERR

echo "INSTALL_LOCAL_AUTOMATION=PASS sha=$expected_sha backup=$backup"
echo "OBSERVER_ACCEPTANCE_EXIT=$observer_rc"
echo "HEALER_ACCEPTANCE_EXIT=$heal_rc"
echo "RECEIPT=$receipt"
echo "ROLLBACK=sudo $repo_root/scripts/install_local_runtime_automation.sh --rollback $backup --confirm '$ROLLBACK_CONFIRM'"

echo 'LOCAL_RUNTIME_ACCEPTANCE=PASS'

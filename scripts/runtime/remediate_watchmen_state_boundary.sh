#!/usr/bin/env bash
set -Eeuo pipefail

legacy="${DOMINION_WATCHMEN_LEGACY_STATE_DIR:-$HOME/.dominion/watchmen}"
target="${DOMINION_WATCHMEN_MACHINE_STATE_DIR:-/var/lib/dominion/watchmen}"
run_user="$(id -un)"
run_group="$(id -gn)"

case "$target" in
  "$HOME"|"$HOME"/*)
    echo 'WATCHMEN_STATE_MIGRATION=FAIL target_inside_home'
    exit 2
    ;;
esac

# Tests and non-root installations may use an already-writable machine-local
# target. Production /var/lib requires the bounded sudo fallback.
if ! install -d -m 700 "$target" 2>/dev/null; then
  sudo install -d -m 700 -o "$run_user" -g "$run_group" "$target"
fi
chmod 700 "$target"
install -d -m 700 "$(dirname "$legacy")"

python3 - "$legacy" "$target" "$HOME" <<'PY'
from __future__ import annotations

import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path

legacy = Path(sys.argv[1]).expanduser()
target = Path(sys.argv[2]).expanduser().resolve(strict=False)
home = Path(sys.argv[3]).expanduser().resolve(strict=False)
repo = (home / "dominion-ops").resolve(strict=False)
buddy = (home / "buddy_core").resolve(strict=False)


def fail(reason: str, code: int = 3) -> None:
    print(f"WATCHMEN_STATE_MIGRATION=FAIL {reason}")
    raise SystemExit(code)


def within(path: Path, parent: Path) -> bool:
    p = path.resolve(strict=False)
    root = parent.resolve(strict=False)
    return p == root or root in p.parents


def enforce_private_tree(root: Path) -> None:
    if os.name != "posix":
        return
    os.chmod(root, 0o700)
    for p in root.rglob("*"):
        if p.is_symlink():
            continue
        os.chmod(p, 0o700 if p.is_dir() else 0o600)


def same_bytes(a: Path, b: Path) -> bool:
    try:
        return a.read_bytes() == b.read_bytes()
    except OSError:
        return False


if within(target, home) or within(target, repo) or within(target, buddy):
    fail("target_resolves_inside_home_or_source")
if not target.is_dir():
    fail("target_not_directory")

enforce_private_tree(target)

# Repeated deployment after a successful migration is intentionally idempotent.
if legacy.is_symlink():
    if legacy.resolve(strict=False) != target:
        fail("legacy_symlink_wrong_target")
    enforce_private_tree(target)
    print("WATCHMEN_STATE_MIGRATION=PASS already_external")
    raise SystemExit(0)

if legacy.exists() and not legacy.is_dir():
    fail("legacy_path_not_directory")

# Copy only durable audit state. The lock file is intentionally not migrated;
# Saraqael recreates it at the canonical target with the required mode.
durable = ("watchmen_hmac.key", "watchmen_audit.log", "watchmen_chain.json")
if legacy.is_dir():
    for name in durable:
        src = legacy / name
        dst = target / name
        if not src.exists():
            continue
        if not src.is_file():
            fail(f"legacy_{name}_not_file")
        if dst.exists():
            if not dst.is_file() or not same_bytes(src, dst):
                fail(f"conflicting_{name}")
            continue
        fd, tmp_name = tempfile.mkstemp(prefix=f".{name}.", dir=str(target))
        os.close(fd)
        tmp = Path(tmp_name)
        try:
            shutil.copyfile(src, tmp)
            os.chmod(tmp, 0o600)
            sync_fd = os.open(str(tmp), os.O_RDONLY)
            try:
                os.fsync(sync_fd)
            finally:
                os.close(sync_fd)
            tmp.replace(dst)
        finally:
            if tmp.exists():
                tmp.unlink()

# Validate that any copied durable state is byte-identical before changing the
# compatibility path. This preserves the existing signing key and audit chain.
if legacy.is_dir():
    for name in durable:
        src = legacy / name
        if src.exists() and not same_bytes(src, target / name):
            fail(f"verification_failed_{name}")

enforce_private_tree(target)

backup = legacy.parent / f".watchmen-boundary-backup-{os.getpid()}"
try:
    if backup.exists() or backup.is_symlink():
        fail("backup_path_already_exists")
    if legacy.is_dir():
        legacy.rename(backup)
    legacy.symlink_to(target, target_is_directory=True)
    if legacy.resolve(strict=False) != target:
        fail("symlink_resolution_mismatch", 4)
    # Once the canonical target and compatibility link are proven, remove the
    # temporary HOME-resident copy so private audit state is not duplicated.
    if backup.is_dir():
        shutil.rmtree(backup)
except BaseException:
    try:
        if legacy.is_symlink():
            legacy.unlink()
        if backup.is_dir() and not legacy.exists():
            backup.rename(legacy)
    except OSError:
        pass
    raise

if os.name == "posix":
    if stat.S_IMODE(target.stat().st_mode) != 0o700:
        fail("target_mode_not_0700", 4)
    for name in durable:
        p = target / name
        if p.exists() and stat.S_IMODE(p.stat().st_mode) != 0o600:
            fail(f"{name}_mode_not_0600", 4)

print("WATCHMEN_STATE_MIGRATION=PASS preserved_machine_local_state")
PY

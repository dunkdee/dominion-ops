#!/usr/bin/env bash
set -Eeuo pipefail

legacy="${DOMINION_AUTH_LEGACY_KEY:-$HOME/.dominion/authorization/ledger_hmac.key}"
target="${DOMINION_AUTH_MACHINE_KEY:-/var/lib/dominion/authorization/ledger_hmac.key}"
target_dir="$(dirname "$target")"
legacy_dir="$(dirname "$legacy")"
run_user="$(id -un)"
run_group="$(id -gn)"

case "$target" in
  "$HOME"|"$HOME"/*)
    echo 'AUTH_KEY_MIGRATION=FAIL target_inside_home'
    exit 2
    ;;
esac

sudo install -d -m 700 -o "$run_user" -g "$run_group" "$target_dir"
install -d -m 700 "$legacy_dir"

# Resolve the same authorization-key inputs Buddy can receive at runtime. The
# three dotenv files are loaded in this order with override=False, so the first
# file that defines a key wins; the last assignment inside that file wins.
# Secret values stay in process memory and are never printed.
python3 - "$legacy" "$target" "$HOME" <<'PY'
from __future__ import annotations

import os
import secrets
import stat
import sys
from pathlib import Path

DIRECT = "DOMINION_AUTHORIZATION_HMAC_KEY"
FILE = "DOMINION_AUTHORIZATION_HMAC_KEY_FILE"
legacy = Path(sys.argv[1]).expanduser()
target = Path(sys.argv[2]).expanduser()
home = Path(sys.argv[3]).expanduser().resolve(strict=False)
repo = (home / "dominion-ops").resolve(strict=False)
buddy_source = (home / "buddy_core").resolve(strict=False)


def fail(reason: str, code: int = 3) -> None:
    print(f"AUTH_KEY_MIGRATION=FAIL {reason}")
    raise SystemExit(code)


def within(path: Path, parent: Path) -> bool:
    p = path.resolve(strict=False)
    root = parent.resolve(strict=False)
    return p == root or root in p.parents


def parse_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    try:
        lines = path.read_text(encoding="utf-8", errors="strict").splitlines()
    except (OSError, UnicodeError):
        fail("runtime_env_unreadable")
    for line in lines:
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("export "):
            s = s[len("export "):].lstrip()
        if "=" not in s:
            continue
        key, _, raw = s.partition("=")
        key = key.strip()
        if key not in {DIRECT, FILE}:
            continue
        value = raw.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        values[key] = value
    return values


def effective(name: str) -> tuple[bool, str]:
    if name in os.environ:
        return True, os.environ[name]
    for path in (home / "buddy_core" / ".env", home / "conductor" / ".env", home / ".env"):
        values = parse_dotenv(path)
        if name in values:
            return True, values[name]
    return False, ""


def validate(raw: bytes, origin: str) -> bytes:
    key = raw.strip()
    if len(key) < 32:
        fail(f"{origin}_weaker_than_256_bits")
    return key


def read_private(path: Path, origin: str) -> bytes:
    try:
        resolved = path.expanduser().resolve(strict=True)
    except (OSError, RuntimeError):
        fail(f"{origin}_missing_or_unreadable")
    if not resolved.is_file():
        fail(f"{origin}_not_file")
    if os.name == "posix" and stat.S_IMODE(resolved.stat().st_mode) & 0o077:
        fail(f"{origin}_not_private")
    try:
        return validate(resolved.read_bytes(), origin)
    except OSError:
        fail(f"{origin}_unreadable")


def write_key(path: Path, key: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(key + b"\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.chmod(path, 0o600)


direct_present, direct_value = effective(DIRECT)
file_present, file_value = effective(FILE)
configured_path: Path | None = None
source_key: bytes | None = None
source_kind = "DEFAULT"

if direct_present:
    source_key = validate(direct_value.encode("utf-8"), "runtime_direct_key")
    source_kind = "DIRECT"
elif file_present:
    if not file_value.strip():
        fail("runtime_key_file_override_empty")
    configured_path = Path(file_value.strip()).expanduser().resolve(strict=False)
    if within(configured_path, repo) or within(configured_path, buddy_source):
        # Do not mutate a configured key inside source control/Buddy source.
        # The service configuration must first be corrected explicitly.
        fail("runtime_key_file_override_inside_source")
    source_key = read_private(configured_path, "runtime_key_file")
    source_kind = "FILE"
else:
    if legacy.exists() or legacy.is_symlink():
        source_key = read_private(legacy, "legacy_key")

resolved_target = target.resolve(strict=False)
if within(resolved_target, home):
    fail("target_resolves_inside_home")

if target.exists():
    target_key = read_private(target, "target_key")
    if source_key is not None and target_key != source_key:
        fail("conflicting_existing_keys")
else:
    key = source_key if source_key is not None else secrets.token_hex(32).encode("ascii")
    write_key(target, validate(key, "new_target_key"))
    target_key = read_private(target, "target_key")

# If Buddy is explicitly configured to a file inside HOME (but outside source),
# keep that configured path valid by replacing it with a link to the canonical
# external target. An already-external configured file may remain in place only
# after proving it carries the exact same key.
if configured_path is not None:
    configured_resolved = configured_path.resolve(strict=False)
    if configured_resolved != target.resolve(strict=False):
        configured_key = read_private(configured_path, "runtime_key_file")
        if configured_key != target_key:
            fail("configured_key_differs_from_target")
        if within(configured_path, home):
            try:
                configured_path.unlink()
                configured_path.symlink_to(target)
            except OSError:
                fail("configured_key_relink_failed")
            if configured_path.resolve(strict=False) != target.resolve(strict=False):
                fail("configured_key_relink_mismatch")

# Preserve the historical default location as a compatibility link. Because
# AuthorizationLedger resolves the path before boundary checks, the effective
# file is now outside HOME even when callers still reference the legacy path.
if legacy.exists() or legacy.is_symlink():
    try:
        if legacy.is_symlink() and legacy.resolve(strict=False) == target.resolve(strict=False):
            pass
        else:
            legacy_key = read_private(legacy, "legacy_key")
            if legacy_key != target_key:
                fail("legacy_key_differs_from_target")
            legacy.unlink()
    except OSError:
        fail("legacy_key_relink_failed")
if not legacy.is_symlink():
    try:
        legacy.symlink_to(target)
    except OSError:
        fail("legacy_key_relink_failed")

if legacy.resolve(strict=False) != target.resolve(strict=False):
    fail("symlink_resolution_mismatch", 4)
if os.name == "posix" and stat.S_IMODE(target.stat().st_mode) != 0o600:
    fail("target_mode_not_0600", 4)

# No secret values are emitted. This marker describes only which supported
# runtime source was reconciled to the canonical external key.
print(f"AUTH_KEY_EFFECTIVE_SOURCE={source_kind}")
print("AUTH_KEY_MIGRATION=PASS preserved_or_created_machine_local_key")
PY

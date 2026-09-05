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

legacy_source=""
if [ -L "$legacy" ]; then
  legacy_resolved="$(readlink -f "$legacy" 2>/dev/null || true)"
  if [ -n "$legacy_resolved" ] && [ -f "$legacy_resolved" ]; then
    legacy_source="$legacy_resolved"
  fi
elif [ -f "$legacy" ]; then
  legacy_source="$legacy"
fi

if [ -f "$target" ] && [ -n "$legacy_source" ] && [ "$(readlink -f "$legacy_source")" != "$(readlink -f "$target")" ]; then
  if ! cmp -s "$legacy_source" "$target"; then
    echo 'AUTH_KEY_MIGRATION=FAIL conflicting_existing_keys'
    exit 3
  fi
fi

if [ ! -f "$target" ]; then
  if [ -n "$legacy_source" ]; then
    sudo install -m 600 -o "$run_user" -g "$run_group" "$legacy_source" "$target"
  else
    umask 077
    python3 - "$target" <<'PY'
import os
import secrets
import sys
from pathlib import Path

path = Path(sys.argv[1])
fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "wb") as fh:
    fh.write(secrets.token_hex(32).encode("ascii") + b"\n")
    fh.flush()
    os.fsync(fh.fileno())
PY
  fi
fi

chmod 600 "$target"
python3 - "$target" <<'PY'
import os
import stat
import sys
from pathlib import Path

path = Path(sys.argv[1])
raw = path.read_bytes().strip()
if len(raw) < 32:
    raise SystemExit("authorization key is weaker than 256 bits")
if os.name == "posix" and stat.S_IMODE(path.stat().st_mode) != 0o600:
    raise SystemExit("authorization key mode is not 0600")
PY

if [ -e "$legacy" ] || [ -L "$legacy" ]; then
  rm -f "$legacy"
fi
ln -s "$target" "$legacy"

resolved_legacy="$(readlink -f "$legacy")"
resolved_target="$(readlink -f "$target")"
[ "$resolved_legacy" = "$resolved_target" ] || {
  echo 'AUTH_KEY_MIGRATION=FAIL symlink_resolution_mismatch'
  exit 4
}

echo 'AUTH_KEY_MIGRATION=PASS preserved_or_created_machine_local_key'

#!/usr/bin/env bash
set -Eeuo pipefail

TARGET="${BUDDY_EXTERNAL_MESSAGE_ENV_FILE:-$HOME/buddy_core/.env}"
PARENT="$(dirname "$TARGET")"

install -d -m 755 "$PARENT"
umask 077

python3 - "$TARGET" <<'PY'
from __future__ import annotations

import os
import stat
import sys
import tempfile
from pathlib import Path

path = Path(sys.argv[1]).expanduser()
key = "BUDDY_EXTERNAL_MESSAGE_MODE"
value = "live"

if path.exists() and not path.is_file():
    print("EXTERNAL_MESSAGE_MODE=FAIL target_not_file")
    raise SystemExit(2)

original = path.read_text(encoding="utf-8") if path.exists() else ""
lines = original.splitlines(keepends=True)
newline = "\r\n" if any(line.endswith("\r\n") for line in lines) else "\n"

out: list[str] = []
written = False
for line in lines:
    stripped = line.lstrip()
    if stripped.startswith(f"{key}=") or stripped.startswith(f"export {key}="):
        if not written:
            out.append(f"{key}={value}{newline}")
            written = True
        continue
    out.append(line)

if not written:
    if out and not out[-1].endswith(("\n", "\r\n")):
        out[-1] = out[-1] + newline
    out.append(f"{key}={value}{newline}")

rendered = "".join(out)
path.parent.mkdir(parents=True, exist_ok=True)
fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
try:
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
        fh.write(rendered)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp_name, path)
    os.chmod(path, 0o600)
finally:
    try:
        os.unlink(tmp_name)
    except FileNotFoundError:
        pass

# Verify without printing the file or any other environment values.
active = []
for raw in path.read_text(encoding="utf-8").splitlines():
    stripped = raw.strip()
    if not stripped or stripped.startswith("#"):
        continue
    if stripped.startswith("export "):
        stripped = stripped[7:].lstrip()
    if stripped.startswith(f"{key}="):
        active.append(stripped.split("=", 1)[1].strip().strip('"').strip("'"))

if active != [value]:
    print("EXTERNAL_MESSAGE_MODE=FAIL verification")
    raise SystemExit(3)
if os.name == "posix" and stat.S_IMODE(path.stat().st_mode) != 0o600:
    print("EXTERNAL_MESSAGE_MODE=FAIL mode_not_0600")
    raise SystemExit(4)

print("EXTERNAL_MESSAGE_MODE=LIVE")
PY

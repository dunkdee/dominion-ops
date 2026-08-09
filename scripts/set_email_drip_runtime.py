#!/usr/bin/env python3
"""Atomically set only Email Drip runtime control keys in the production env file.

Secrets are never printed. The utility is intentionally narrow and fail-closed.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import secrets
import shutil
import stat
from datetime import datetime, timezone
from pathlib import Path

KEYS = ("DRIP_SEND_MODE", "DRIP_LIVE_PREFLIGHT_OK", "DRIP_LIVE_AUTHORIZED_AT")
ASSIGNMENT = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def assignment_indexes(lines: list[str], key: str) -> list[int]:
    prefix = key + "="
    return [i for i, line in enumerate(lines) if line.startswith(prefix)]


def apply(path: Path, mode: str, expect: str) -> None:
    if mode not in {"hold", "live"}:
        raise SystemExit("MODE_INVALID")
    if expect not in {"hold", "live", "either"}:
        raise SystemExit("EXPECT_INVALID")
    if not path.is_file() or path.is_symlink():
        raise SystemExit("ENV_TARGET_INVALID")

    st = path.stat()
    before = path.read_text(encoding="utf-8")
    lines = before.splitlines()
    mode_indexes = assignment_indexes(lines, "DRIP_SEND_MODE")
    if len(mode_indexes) != 1:
        raise SystemExit(f"DRIP_SEND_MODE_ASSIGNMENTS_INVALID count={len(mode_indexes)}")
    current_mode = lines[mode_indexes[0]].split("=", 1)[1].strip().lower()
    if current_mode not in {"hold", "live"}:
        raise SystemExit("DRIP_SEND_MODE_CURRENT_INVALID")
    if expect != "either" and current_mode != expect:
        raise SystemExit(f"DRIP_SEND_MODE_PRECONDITION_FAIL expected={expect} actual={current_mode}")

    for key in ("DRIP_LIVE_PREFLIGHT_OK", "DRIP_LIVE_AUTHORIZED_AT"):
        if len(assignment_indexes(lines, key)) > 1:
            raise SystemExit(f"{key}_ASSIGNMENTS_INVALID")

    values = {
        "DRIP_SEND_MODE": mode,
        "DRIP_LIVE_PREFLIGHT_OK": "true" if mode == "live" else "false",
        "DRIP_LIVE_AUTHORIZED_AT": datetime.now(timezone.utc).isoformat() if mode == "live" else "",
    }
    changed_keys: list[str] = []
    output = list(lines)
    for key, value in values.items():
        indexes = assignment_indexes(output, key)
        new_line = f"{key}={value}"
        if indexes:
            idx = indexes[0]
            if output[idx] != new_line:
                output[idx] = new_line
                changed_keys.append(key)
        else:
            output.append(new_line)
            changed_keys.append(key)

    after = "\n".join(output) + "\n"
    if after == before:
        print(f"ENV_RUNTIME_SET=PASS mode={mode} idempotent=true pre_sha={sha256(path)} post_sha={sha256(path)} changed_keys=none")
        return

    backup = path.with_name(f"{path.name}.drip-{mode}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(4)}.bak")
    shutil.copy2(path, backup)
    os.chown(backup, st.st_uid, st.st_gid)
    os.chmod(backup, stat.S_IMODE(st.st_mode))
    with backup.open("rb") as handle:
        os.fsync(handle.fileno())

    tmp = path.with_name(f".{path.name}.drip-{os.getpid()}-{secrets.token_hex(8)}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, stat.S_IMODE(st.st_mode))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(after)
            handle.flush()
            os.fsync(handle.fileno())
        os.chown(tmp, st.st_uid, st.st_gid)
        os.chmod(tmp, stat.S_IMODE(st.st_mode))
        pre_sha = sha256(path)
        os.replace(tmp, path)
        fsync_dir(path.parent)
        post_sha = sha256(path)
    finally:
        if tmp.exists():
            tmp.unlink()

    final_st = path.stat()
    if (final_st.st_uid, final_st.st_gid, stat.S_IMODE(final_st.st_mode)) != (st.st_uid, st.st_gid, stat.S_IMODE(st.st_mode)):
        raise SystemExit("ENV_METADATA_VERIFY_FAIL")
    final_lines = path.read_text(encoding="utf-8").splitlines()
    for key in KEYS:
        if len(assignment_indexes(final_lines, key)) != 1:
            raise SystemExit(f"ENV_POST_ASSIGNMENT_VERIFY_FAIL key={key}")
    if final_lines[assignment_indexes(final_lines, "DRIP_SEND_MODE")[0]] != f"DRIP_SEND_MODE={mode}":
        raise SystemExit("ENV_POST_MODE_VERIFY_FAIL")
    print(
        "ENV_RUNTIME_SET=PASS "
        f"mode={mode} idempotent=false pre_sha={pre_sha} post_sha={post_sha} "
        f"changed_keys={','.join(changed_keys)} backup={backup} owner={st.st_uid}:{st.st_gid} mode={oct(stat.S_IMODE(st.st_mode))}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("hold", "live"))
    parser.add_argument("--env-file", type=Path, default=Path("/home/malachisingleton8/.env"))
    parser.add_argument("--expect", choices=("hold", "live", "either"), default="either")
    args = parser.parse_args()
    apply(args.env_file, args.mode, args.expect)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
#!/usr/bin/env bash
set -euo pipefail

# Work Order 001A — Approval Gate A v2
# Read-only source, capacity, production-container identity, and open-write-handle preflight.
# Evidence is written only inside a private per-run directory under /tmp.

SOURCE=/home/malachisingleton8/releases
EXPECTED=/home/malachisingleton8/releases

umask 077
EVIDENCE_DIR=$(mktemp -d /tmp/dominion-releases-gate-a.XXXXXX) || {
  echo 'BLOCKED: unable to create private evidence directory'
  exit 18
}
chmod 700 -- "$EVIDENCE_DIR"
LSOF_OUT="$EVIDENCE_DIR/lsof.out"
LSOF_ERR="$EVIDENCE_DIR/lsof.err"
BASELINE="$EVIDENCE_DIR/container-baseline.txt"
STATUS_BEFORE="$EVIDENCE_DIR/container-status-before.txt"

printf '%s\n' '=== WORK ORDER 001A PREFLIGHT V2 ==='
printf 'evidence_dir=%s\n' "$EVIDENCE_DIR"
resolved=$(readlink -f -- "$SOURCE")
printf 'resolved_source=%s\n' "$resolved"
[ "$resolved" = "$EXPECTED" ] || { echo 'BLOCKED: source path mismatch'; exit 10; }
[ -d "$SOURCE" ] || { echo 'BLOCKED: source is not a directory'; exit 11; }
[ ! -L "$SOURCE" ] || { echo 'BLOCKED: source is a symlink'; exit 12; }

source_bytes=$(du -x --apparent-size --bytes --summarize "$SOURCE" | awk '{print $1}')
required_bytes=$((source_bytes * 3 + 268435456))
root_available=$(df -B1 --output=avail / | tail -n 1 | tr -d ' ')
tmp_available=$(df -B1 --output=avail /tmp | tail -n 1 | tr -d ' ')

printf 'source_apparent_bytes=%s\n' "$source_bytes"
printf 'required_capacity_bytes=%s\n' "$required_bytes"
printf 'root_available_bytes=%s\n' "$root_available"
printf 'tmp_available_bytes=%s\n' "$tmp_available"
df -B1 / /tmp

[ "$root_available" -ge "$required_bytes" ] || {
  echo 'BLOCKED: insufficient root filesystem safety margin'
  exit 13
}
[ "$tmp_available" -ge "$required_bytes" ] || {
  echo 'BLOCKED: insufficient /tmp filesystem safety margin'
  exit 14
}

docker ps -q --no-trunc \
  | LC_ALL=C sort \
  | xargs -r docker inspect --format '{{.Id}}|{{.Name}}|{{.Image}}' \
  | LC_ALL=C sort \
  | tee "$BASELINE"

docker ps --no-trunc --format '{{.ID}}|{{.Names}}|{{.Image}}|{{.Status}}' \
  | LC_ALL=C sort \
  | tee "$STATUS_BEFORE"

if ! command -v lsof >/dev/null 2>&1; then
  echo 'open_write_handles=UNKNOWN (lsof unavailable)'
  echo 'BLOCKED: package installation is not authorized by this work order'
  exit 15
fi

: > "$LSOF_OUT"
: > "$LSOF_ERR"
set +e
LC_ALL=C lsof -w +D "$SOURCE" >"$LSOF_OUT" 2>"$LSOF_ERR"
lsof_rc=$?
set -e
printf 'lsof_exit_code=%s\n' "$lsof_rc"

# lsof documents exit 1 with empty output as the no-match result. -w suppresses
# unrelated filesystem warnings while preserving the exit status and match output.
if [ "$lsof_rc" -eq 1 ] && [ ! -s "$LSOF_OUT" ] && [ ! -s "$LSOF_ERR" ]; then
  : # safe no-match result
elif [ "$lsof_rc" -ne 0 ]; then
  echo "BLOCKED: lsof inspection failed rc=$lsof_rc"
  [ ! -s "$LSOF_ERR" ] || sed -n '1,20p' "$LSOF_ERR"
  exit 16
fi

# Count only numeric file descriptors opened write-only (w) or read/write (u).
# This deliberately excludes pseudo-FD labels such as cwd, rtd, txt, mem, and DEL.
write_handles=$(awk 'NR>1 && $4 ~ /^[0-9]+[wu]/ {count++} END {print count+0}' "$LSOF_OUT")
printf 'open_write_handles=%s\n' "$write_handles"
[ "$write_handles" -eq 0 ] || {
  echo 'BLOCKED: source has open write handles'
  exit 17
}

printf '%s\n' 'PREFLIGHT=PASS'

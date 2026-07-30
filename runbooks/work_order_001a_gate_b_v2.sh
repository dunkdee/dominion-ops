#!/usr/bin/env bash
set -euo pipefail

# Work Order 001A — Approval Gate B v3
# Creates a deterministic, one-filesystem source inventory and NUL-delimited
# SHA-256 manifest without modifying the releases source tree.
# Certification requires writer quiescence plus byte-identical canonical source
# state before and after inventory generation.

SOURCE=/home/malachisingleton8/releases
EXPECTED=/home/malachisingleton8/releases
INVENTORY_FINAL=/tmp/dominion-releases-source-inventory.txt
MANIFEST_FINAL=/tmp/dominion-releases-source-manifest.sha256
READY_FINAL=/tmp/dominion-releases-gate-b.ready

umask 077
EVIDENCE_DIR=$(mktemp -d /tmp/dominion-releases-gate-b.XXXXXX) || {
  echo 'BLOCKED: unable to create private Gate B evidence directory'
  exit 18
}
STATE_BEFORE="$EVIDENCE_DIR/source-state.before.bin"
STATE_AFTER="$EVIDENCE_DIR/source-state.after.bin"
METRICS_BEFORE="$EVIDENCE_DIR/source-metrics.before.txt"
METRICS_AFTER="$EVIDENCE_DIR/source-metrics.after.txt"
MANIFEST_BEFORE="$EVIDENCE_DIR/source-manifest.before.sha256"
MANIFEST_AFTER="$EVIDENCE_DIR/source-manifest.after.sha256"
INVENTORY_TMP="$EVIDENCE_DIR/source-inventory.txt"
PUBLISHING_TMP="$EVIDENCE_DIR/publishing.marker"
READY_TMP="$EVIDENCE_DIR/ready.marker"

printf '%s\n' '=== WORK ORDER 001A SOURCE INVENTORY V3 ==='
printf 'evidence_dir=%s\n' "$EVIDENCE_DIR"

resolved=$(readlink -f -- "$SOURCE")
printf 'resolved_source=%s\n' "$resolved"
[ "$resolved" = "$EXPECTED" ] || { echo 'BLOCKED: source path mismatch'; exit 20; }
[ -d "$SOURCE" ] || { echo 'BLOCKED: source is not a directory'; exit 21; }
[ ! -L "$SOURCE" ] || { echo 'BLOCKED: source is a symlink'; exit 22; }

for required_command in awk cmp file find lsof mktemp mv python3 sha256sum sort uniq xargs; do
  command -v "$required_command" >/dev/null 2>&1 || {
    echo "BLOCKED: required command unavailable: $required_command"
    exit 23
  }
done

check_writers() {
  phase=$1
  out="$EVIDENCE_DIR/lsof-$phase.out"
  err="$EVIDENCE_DIR/lsof-$phase.err"
  : > "$out"
  : > "$err"

  set +e
  LC_ALL=C lsof -w +D "$SOURCE" >"$out" 2>"$err"
  rc=$?
  set -e

  if [ "$rc" -eq 1 ] && [ ! -s "$out" ] && [ ! -s "$err" ]; then
    : # documented no-match result
  elif [ "$rc" -ne 0 ]; then
    echo "BLOCKED: lsof $phase inspection failed rc=$rc"
    [ ! -s "$err" ] || sed -n '1,20p' "$err"
    exit 24
  fi

  writers=$(awk 'NR>1 && $4 ~ /^[0-9]+[wu]/ {count++} END {print count+0}' "$out")
  printf 'open_write_handles_%s=%s\n' "$phase" "$writers"
  [ "$writers" -eq 0 ] || {
    echo "BLOCKED: source has open write handles during $phase"
    exit 25
  }
}

capture_state() {
  state_path=$1
  manifest_path=$2
  metrics_path=$3

  python3 - "$SOURCE" "$state_path" "$manifest_path" "$metrics_path" <<'PY'
import hashlib
import os
import stat
import sys

root_text, state_name, manifest_name, metrics_name = sys.argv[1:]
root = os.fsencode(root_text)
root_stat = os.lstat(root)
root_dev = root_stat.st_dev
entries = []


def visit(path: bytes, rel: bytes) -> None:
    st = os.lstat(path)
    entries.append((rel, path))
    if stat.S_ISDIR(st.st_mode) and st.st_dev == root_dev:
        with os.scandir(path) as scan:
            children = sorted(scan, key=lambda entry: entry.name)
        for entry in children:
            child_path = os.path.join(path, entry.name)
            child_rel = entry.name if rel == b"." else rel + b"/" + entry.name
            visit(child_path, child_rel)


def stable_fields(st):
    return (
        st.st_mode,
        st.st_uid,
        st.st_gid,
        st.st_size,
        st.st_mtime_ns,
        st.st_ctime_ns,
        st.st_dev,
        st.st_ino,
        st.st_nlink,
        st.st_rdev,
    )


def write_field(stream, value: bytes) -> None:
    stream.write(len(value).to_bytes(8, "big"))
    stream.write(value)


visit(root, b".")
entries.sort(key=lambda item: item[0])
counts = {"regular_files": 0, "directories": 0, "symlinks": 0, "special_members": 0}
regular_bytes = 0
inode_counts = {}
oldest_ns = None
newest_ns = None
symlink_hash = hashlib.sha256()

with open(state_name, "wb") as state_out, open(manifest_name, "wb") as manifest_out:
    for rel, path in entries:
        before = os.lstat(path)
        mode = before.st_mode
        target = b""
        digest = b""

        if stat.S_ISREG(mode):
            counts["regular_files"] += 1
            regular_bytes += before.st_size
            inode_counts[(before.st_dev, before.st_ino)] = inode_counts.get((before.st_dev, before.st_ino), 0) + 1
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(path, flags)
            try:
                opened_before = os.fstat(fd)
                if (opened_before.st_dev, opened_before.st_ino) != (before.st_dev, before.st_ino):
                    raise RuntimeError("file identity changed before hashing")
                h = hashlib.sha256()
                while True:
                    chunk = os.read(fd, 1024 * 1024)
                    if not chunk:
                        break
                    h.update(chunk)
                opened_after = os.fstat(fd)
            finally:
                os.close(fd)
            if stable_fields(opened_before) != stable_fields(opened_after):
                raise RuntimeError("file changed while hashing")
            digest = h.hexdigest().encode("ascii")
            manifest_rel = b"./" + rel if rel != b"." else b"."
            manifest_out.write(digest + b"  " + manifest_rel + b"\0")
        elif stat.S_ISDIR(mode):
            counts["directories"] += 1
        elif stat.S_ISLNK(mode):
            counts["symlinks"] += 1
            target = os.readlink(path)
            symlink_hash.update(len(rel).to_bytes(8, "big") + rel)
            symlink_hash.update(len(target).to_bytes(8, "big") + target)
        else:
            counts["special_members"] += 1

        after = os.lstat(path)
        if stable_fields(before) != stable_fields(after):
            raise RuntimeError("source entry changed during canonical scan")

        oldest_ns = before.st_mtime_ns if oldest_ns is None else min(oldest_ns, before.st_mtime_ns)
        newest_ns = before.st_mtime_ns if newest_ns is None else max(newest_ns, before.st_mtime_ns)

        kind = (
            b"f" if stat.S_ISREG(mode) else
            b"d" if stat.S_ISDIR(mode) else
            b"l" if stat.S_ISLNK(mode) else
            b"o"
        )
        fields = [
            rel,
            kind,
            str(before.st_mode).encode(),
            str(before.st_uid).encode(),
            str(before.st_gid).encode(),
            str(before.st_size).encode(),
            str(before.st_mtime_ns).encode(),
            str(before.st_ctime_ns).encode(),
            str(before.st_dev).encode(),
            str(before.st_ino).encode(),
            str(before.st_nlink).encode(),
            str(before.st_rdev).encode(),
            target,
            digest,
        ]
        for field in fields:
            write_field(state_out, field)

hardlink_members = sum(count - 1 for count in inode_counts.values() if count > 1)
with open(metrics_name, "w", encoding="utf-8") as metrics:
    metrics.write(f"source={root_text}\n")
    metrics.write("filesystem_policy=one-filesystem\n")
    metrics.write(f"regular_files={counts['regular_files']}\n")
    metrics.write(f"directories={counts['directories']}\n")
    metrics.write(f"symlinks={counts['symlinks']}\n")
    metrics.write(f"special_members={counts['special_members']}\n")
    metrics.write(f"hardlink_members_expected={hardlink_members}\n")
    metrics.write(f"regular_file_bytes={regular_bytes}\n")
    metrics.write(f"symlink_target_sha256={symlink_hash.hexdigest()}\n")
    metrics.write(f"oldest_mtime_epoch_ns={oldest_ns or 0}\n")
    metrics.write(f"newest_mtime_epoch_ns={newest_ns or 0}\n")
PY
}

check_writers before
capture_state "$STATE_BEFORE" "$MANIFEST_BEFORE" "$METRICS_BEFORE"

special_members=$(awk -F= '$1=="special_members"{print $2}' "$METRICS_BEFORE")
[ "$special_members" -eq 0 ] || {
  echo "BLOCKED: unsupported source special members=$special_members"
  exit 26
}

{
  cat "$METRICS_BEFORE"
  tree_apparent_bytes=$(du -x --apparent-size --bytes --summarize "$SOURCE" | awk '{print $1}')
  printf 'tree_apparent_bytes=%s\n' "$tree_apparent_bytes"
  echo 'file_type_summary:'
  (
    cd "$SOURCE"
    LC_ALL=C find . -xdev -type f -print0 \
      | LC_ALL=C sort -z \
      | xargs -0 -r file --brief --mime-type --
  ) | LC_ALL=C sort | uniq -c | LC_ALL=C sort -nr
} > "$INVENTORY_TMP"

capture_state "$STATE_AFTER" "$MANIFEST_AFTER" "$METRICS_AFTER"
check_writers after

cmp -s "$STATE_BEFORE" "$STATE_AFTER" || {
  echo 'BLOCKED: canonical source state changed during Gate B'
  exit 27
}
cmp -s "$MANIFEST_BEFORE" "$MANIFEST_AFTER" || {
  echo 'BLOCKED: source content manifest changed during Gate B'
  exit 28
}
cmp -s "$METRICS_BEFORE" "$METRICS_AFTER" || {
  echo 'BLOCKED: source metrics changed during Gate B'
  exit 29
}

regular_files=$(awk -F= '$1=="regular_files"{print $2}' "$METRICS_BEFORE")
manifest_records=$(tr -cd '\0' < "$MANIFEST_BEFORE" | wc -c)
[ "$manifest_records" -eq "$regular_files" ] || {
  echo "BLOCKED: manifest records $manifest_records != regular files $regular_files"
  exit 30
}

for handoff in "$INVENTORY_FINAL" "$MANIFEST_FINAL" "$READY_FINAL"; do
  [ ! -d "$handoff" ] || {
    echo "BLOCKED: handoff path is a directory: $handoff"
    exit 31
  }
done

generation=$(basename "$EVIDENCE_DIR")
printf 'status=PUBLISHING\ngeneration=%s\n' "$generation" > "$PUBLISHING_TMP"
mv -fT -- "$PUBLISHING_TMP" "$READY_FINAL"

mv -fT -- "$INVENTORY_TMP" "$INVENTORY_FINAL"
mv -fT -- "$MANIFEST_BEFORE" "$MANIFEST_FINAL"
chmod 600 -- "$INVENTORY_FINAL" "$MANIFEST_FINAL" "$READY_FINAL"

inventory_sha256=$(sha256sum "$INVENTORY_FINAL" | awk '{print $1}')
manifest_sha256=$(sha256sum "$MANIFEST_FINAL" | awk '{print $1}')
state_sha256=$(sha256sum "$STATE_AFTER" | awk '{print $1}')

cat > "$READY_TMP" <<EOF
status=READY
generation=$generation
inventory_path=$INVENTORY_FINAL
inventory_sha256=$inventory_sha256
manifest_path=$MANIFEST_FINAL
manifest_sha256=$manifest_sha256
canonical_state_sha256=$state_sha256
regular_files=$regular_files
manifest_records=$manifest_records
EOF
chmod 600 -- "$READY_TMP"
mv -fT -- "$READY_TMP" "$READY_FINAL"
chmod 600 -- "$READY_FINAL"

printf 'regular_files=%s\n' "$regular_files"
printf 'manifest_records=%s\n' "$manifest_records"
printf 'inventory_path=%s\n' "$INVENTORY_FINAL"
printf 'inventory_sha256=%s\n' "$inventory_sha256"
printf 'manifest_path=%s\n' "$MANIFEST_FINAL"
printf 'manifest_sha256=%s\n' "$manifest_sha256"
printf 'ready_path=%s\n' "$READY_FINAL"
printf 'canonical_state_sha256=%s\n' "$state_sha256"
printf '%s\n' 'SOURCE_INVENTORY=PASS'
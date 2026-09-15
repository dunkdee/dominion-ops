#!/usr/bin/env bash
set -euo pipefail

# Work Order 001A — Approval Gate D v1
# Revalidates the exact Gate B source generation and Gate C archive generation
# before any transfer. This script does not transfer, upload, delete source data,
# restart services, merge, deploy, install packages, or continue to Gate E.

SOURCE=/home/malachisingleton8/releases
EXPECTED=/home/malachisingleton8/releases
GATE_B_READY=/tmp/dominion-releases-gate-b.ready
GATE_C_READY=/tmp/dominion-releases-gate-c.ready
SOURCE_INV=/tmp/dominion-releases-source-inventory.txt
SOURCE_MANIFEST=/tmp/dominion-releases-source-manifest.sha256
ARCHIVE=/tmp/dominion-releases-20260730.tar.gz
ARCHIVE_SHA=/tmp/dominion-releases-20260730.tar.gz.sha256
ARCHIVE_INV=/tmp/dominion-releases-archive-inventory.txt
GATE_D_READY_FINAL=/tmp/dominion-releases-gate-d.ready

umask 077
EVIDENCE_DIR=$(mktemp -d /tmp/dominion-releases-gate-d.XXXXXX) || {
  echo 'BLOCKED: unable to create private Gate D evidence directory'
  exit 80
}
READY_B_BEFORE="$EVIDENCE_DIR/gate-b.ready.before"
READY_B_AFTER="$EVIDENCE_DIR/gate-b.ready.after"
READY_C_BEFORE="$EVIDENCE_DIR/gate-c.ready.before"
READY_C_AFTER="$EVIDENCE_DIR/gate-c.ready.after"
STATE_BEFORE="$EVIDENCE_DIR/source-state.before.bin"
STATE_AFTER="$EVIDENCE_DIR/source-state.after.bin"
MANIFEST_BEFORE="$EVIDENCE_DIR/source-manifest.before.sha256"
MANIFEST_AFTER="$EVIDENCE_DIR/source-manifest.after.sha256"
METRICS_BEFORE="$EVIDENCE_DIR/source-metrics.before.txt"
METRICS_AFTER="$EVIDENCE_DIR/source-metrics.after.txt"
READY_D_TMP="$EVIDENCE_DIR/gate-d.ready"

printf '%s\n' '=== WORK ORDER 001A SOURCE STABILITY V1 ==='
printf 'evidence_dir=%s\n' "$EVIDENCE_DIR"

resolved=$(readlink -f -- "$SOURCE")
printf 'resolved_source=%s\n' "$resolved"
[ "$resolved" = "$EXPECTED" ] || { echo 'BLOCKED: source path mismatch'; exit 81; }
[ -d "$SOURCE" ] || { echo 'BLOCKED: source is not a directory'; exit 82; }
[ ! -L "$SOURCE" ] || { echo 'BLOCKED: source is a symlink'; exit 83; }

for required_command in awk basename chmod cmp cp lsof mktemp mv python3 readlink sed sha256sum stat tar tr wc; do
  command -v "$required_command" >/dev/null 2>&1 || {
    echo "BLOCKED: required command unavailable: $required_command"
    exit 84
  }
done

for artifact in \
  "$GATE_B_READY" "$GATE_C_READY" "$SOURCE_INV" "$SOURCE_MANIFEST" \
  "$ARCHIVE" "$ARCHIVE_SHA" "$ARCHIVE_INV"; do
  [ -f "$artifact" ] && [ ! -L "$artifact" ] || {
    echo "BLOCKED: required artifact missing or unsafe: $artifact"
    exit 85
  }
done

ready_value() {
  key=$1
  file=$2
  awk -F= -v wanted="$key" '
    $1 == wanted { count++; value = substr($0, index($0, "=") + 1) }
    END { if (count == 1) print value; else exit 1 }
  ' "$file"
}

inventory_value() {
  key=$1
  awk -F= -v wanted="$key" '
    $1 == wanted { count++; value = substr($0, index($0, "=") + 1) }
    END { if (count == 1) print value; else exit 1 }
  ' "$SOURCE_INV"
}

cp -- "$GATE_B_READY" "$READY_B_BEFORE"
cp -- "$GATE_C_READY" "$READY_C_BEFORE"

[ "$(ready_value status "$READY_B_BEFORE")" = READY ] || {
  echo 'BLOCKED: Gate B handoff is not READY'
  exit 86
}
[ "$(ready_value status "$READY_C_BEFORE")" = READY ] || {
  echo 'BLOCKED: Gate C handoff is not READY'
  exit 87
}

[ "$(ready_value inventory_path "$READY_B_BEFORE")" = "$SOURCE_INV" ] || {
  echo 'BLOCKED: Gate B inventory path mismatch'
  exit 88
}
[ "$(ready_value manifest_path "$READY_B_BEFORE")" = "$SOURCE_MANIFEST" ] || {
  echo 'BLOCKED: Gate B manifest path mismatch'
  exit 89
}
[ "$(ready_value source_inventory_path "$READY_C_BEFORE")" = "$SOURCE_INV" ] || {
  echo 'BLOCKED: Gate C source inventory path mismatch'
  exit 90
}
[ "$(ready_value source_manifest_path "$READY_C_BEFORE")" = "$SOURCE_MANIFEST" ] || {
  echo 'BLOCKED: Gate C source manifest path mismatch'
  exit 91
}
[ "$(ready_value archive_path "$READY_C_BEFORE")" = "$ARCHIVE" ] || {
  echo 'BLOCKED: Gate C archive path mismatch'
  exit 92
}
[ "$(ready_value archive_checksum_path "$READY_C_BEFORE")" = "$ARCHIVE_SHA" ] || {
  echo 'BLOCKED: Gate C archive checksum path mismatch'
  exit 93
}
[ "$(ready_value archive_inventory_path "$READY_C_BEFORE")" = "$ARCHIVE_INV" ] || {
  echo 'BLOCKED: Gate C archive inventory path mismatch'
  exit 94
}

expected_gate_b_generation=$(ready_value generation "$READY_B_BEFORE")
expected_gate_c_generation=$(ready_value generation "$READY_C_BEFORE")
expected_state_sha=$(ready_value canonical_state_sha256 "$READY_B_BEFORE")
expected_inventory_sha=$(ready_value inventory_sha256 "$READY_B_BEFORE")
expected_manifest_sha=$(ready_value manifest_sha256 "$READY_B_BEFORE")
expected_regular_files=$(ready_value regular_files "$READY_B_BEFORE")
expected_manifest_records=$(ready_value manifest_records "$READY_B_BEFORE")
expected_archive_sha=$(ready_value archive_sha256 "$READY_C_BEFORE")
expected_archive_bytes=$(ready_value archive_bytes "$READY_C_BEFORE")
expected_archive_inventory_sha=$(ready_value archive_inventory_sha256 "$READY_C_BEFORE")

[ "$(ready_value gate_b_generation "$READY_C_BEFORE")" = "$expected_gate_b_generation" ] || {
  echo 'BLOCKED: Gate C references a different Gate B generation'
  exit 95
}
[ "$(ready_value gate_b_canonical_state_sha256 "$READY_C_BEFORE")" = "$expected_state_sha" ] || {
  echo 'BLOCKED: Gate C references a different Gate B canonical state'
  exit 96
}
[ "$(ready_value source_inventory_sha256 "$READY_C_BEFORE")" = "$expected_inventory_sha" ] || {
  echo 'BLOCKED: Gate C references a different source inventory digest'
  exit 97
}
[ "$(ready_value source_manifest_sha256 "$READY_C_BEFORE")" = "$expected_manifest_sha" ] || {
  echo 'BLOCKED: Gate C references a different source manifest digest'
  exit 98
}

actual_inventory_sha=$(sha256sum "$SOURCE_INV" | awk '{print $1}')
actual_manifest_sha=$(sha256sum "$SOURCE_MANIFEST" | awk '{print $1}')
actual_archive_sha=$(sha256sum "$ARCHIVE" | awk '{print $1}')
actual_archive_bytes=$(stat --format='%s' "$ARCHIVE")
actual_archive_inventory_sha=$(sha256sum "$ARCHIVE_INV" | awk '{print $1}')

[ "$actual_inventory_sha" = "$expected_inventory_sha" ] || {
  echo 'BLOCKED: source inventory digest mismatch'
  exit 99
}
[ "$actual_manifest_sha" = "$expected_manifest_sha" ] || {
  echo 'BLOCKED: source manifest digest mismatch'
  exit 100
}
[ "$actual_archive_sha" = "$expected_archive_sha" ] || {
  echo 'BLOCKED: archive digest mismatch'
  exit 101
}
[ "$actual_archive_bytes" = "$expected_archive_bytes" ] || {
  echo 'BLOCKED: archive byte count mismatch'
  exit 102
}
[ "$actual_archive_inventory_sha" = "$expected_archive_inventory_sha" ] || {
  echo 'BLOCKED: archive inventory digest mismatch'
  exit 103
}
[ "$expected_regular_files" -eq "$expected_manifest_records" ] || {
  echo 'BLOCKED: Gate B regular-file and manifest-record counts disagree'
  exit 104
}

manifest_records=$(tr -cd '\0' < "$SOURCE_MANIFEST" | wc -c)
[ "$manifest_records" -eq "$expected_regular_files" ] || {
  echo 'BLOCKED: source manifest record count mismatch'
  exit 105
}

(
  cd "$(dirname "$ARCHIVE")"
  sha256sum -c --status "$(basename "$ARCHIVE_SHA")"
) || {
  echo 'BLOCKED: archive checksum verification failed'
  exit 106
}
tar -tzf "$ARCHIVE" >/dev/null || {
  echo 'BLOCKED: archive listing validation failed'
  exit 107
}

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
    exit 108
  fi

  writers=$(awk 'NR>1 && $4 ~ /^[0-9]+[wu]/ {count++} END {print count+0}' "$out")
  printf 'open_write_handles_%s=%s\n' "$phase" "$writers"
  [ "$writers" -eq 0 ] || {
    echo "BLOCKED: source has open write handles during $phase"
    exit 109
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

validate_metrics() {
  metrics=$1
  for key in regular_files directories symlinks special_members hardlink_members_expected regular_file_bytes symlink_target_sha256; do
    expected=$(inventory_value "$key")
    actual=$(awk -F= -v wanted="$key" '
      $1 == wanted { count++; value = substr($0, index($0, "=") + 1) }
      END { if (count == 1) print value; else exit 1 }
    ' "$metrics")
    [ "$actual" = "$expected" ] || {
      echo "BLOCKED: source metric mismatch for $key"
      exit 110
    }
  done
}

check_writers before
capture_state "$STATE_BEFORE" "$MANIFEST_BEFORE" "$METRICS_BEFORE"
check_writers middle

state_before_sha=$(sha256sum "$STATE_BEFORE" | awk '{print $1}')
[ "$state_before_sha" = "$expected_state_sha" ] || {
  echo 'BLOCKED: source canonical state no longer matches Gate B'
  exit 111
}
cmp -s "$SOURCE_MANIFEST" "$MANIFEST_BEFORE" || {
  echo 'BLOCKED: source content no longer matches Gate B manifest'
  exit 112
}
validate_metrics "$METRICS_BEFORE"

capture_state "$STATE_AFTER" "$MANIFEST_AFTER" "$METRICS_AFTER"
check_writers after

cmp -s "$STATE_BEFORE" "$STATE_AFTER" || {
  echo 'BLOCKED: canonical source state changed during Gate D'
  exit 113
}
cmp -s "$MANIFEST_BEFORE" "$MANIFEST_AFTER" || {
  echo 'BLOCKED: source content manifest changed during Gate D'
  exit 114
}
cmp -s "$METRICS_BEFORE" "$METRICS_AFTER" || {
  echo 'BLOCKED: source metrics changed during Gate D'
  exit 115
}

cp -- "$GATE_B_READY" "$READY_B_AFTER"
cp -- "$GATE_C_READY" "$READY_C_AFTER"
cmp -s "$READY_B_BEFORE" "$READY_B_AFTER" || {
  echo 'BLOCKED: Gate B READY marker changed during Gate D'
  exit 116
}
cmp -s "$READY_C_BEFORE" "$READY_C_AFTER" || {
  echo 'BLOCKED: Gate C READY marker changed during Gate D'
  exit 117
}

final_archive_sha=$(sha256sum "$ARCHIVE" | awk '{print $1}')
final_archive_bytes=$(stat --format='%s' "$ARCHIVE")
final_archive_inventory_sha=$(sha256sum "$ARCHIVE_INV" | awk '{print $1}')
[ "$final_archive_sha" = "$expected_archive_sha" ] || {
  echo 'BLOCKED: archive changed during Gate D'
  exit 118
}
[ "$final_archive_bytes" = "$expected_archive_bytes" ] || {
  echo 'BLOCKED: archive size changed during Gate D'
  exit 119
}
[ "$final_archive_inventory_sha" = "$expected_archive_inventory_sha" ] || {
  echo 'BLOCKED: archive inventory changed during Gate D'
  exit 120
}
(
  cd "$(dirname "$ARCHIVE")"
  sha256sum -c --status "$(basename "$ARCHIVE_SHA")"
) || {
  echo 'BLOCKED: final archive checksum verification failed'
  exit 121
}

for handoff in "$GATE_D_READY_FINAL"; do
  [ ! -d "$handoff" ] || {
    echo "BLOCKED: handoff path is a directory: $handoff"
    exit 122
  }
done

gate_d_generation=$(basename "$EVIDENCE_DIR")
cat > "$READY_D_TMP" <<EOF
status=READY
generation=$gate_d_generation
gate_b_generation=$expected_gate_b_generation
gate_c_generation=$expected_gate_c_generation
canonical_state_sha256=$state_before_sha
source_inventory_path=$SOURCE_INV
source_inventory_sha256=$expected_inventory_sha
source_manifest_path=$SOURCE_MANIFEST
source_manifest_sha256=$expected_manifest_sha
archive_path=$ARCHIVE
archive_sha256=$expected_archive_sha
archive_bytes=$expected_archive_bytes
archive_checksum_path=$ARCHIVE_SHA
archive_inventory_path=$ARCHIVE_INV
archive_inventory_sha256=$expected_archive_inventory_sha
regular_files=$expected_regular_files
manifest_records=$manifest_records
EOF
chmod 600 -- "$READY_D_TMP"
mv -fT -- "$READY_D_TMP" "$GATE_D_READY_FINAL"
chmod 600 -- "$GATE_D_READY_FINAL"

printf 'gate_b_generation=%s\n' "$expected_gate_b_generation"
printf 'gate_c_generation=%s\n' "$expected_gate_c_generation"
printf 'gate_d_generation=%s\n' "$gate_d_generation"
printf 'canonical_state_sha256=%s\n' "$state_before_sha"
printf 'regular_files=%s\n' "$expected_regular_files"
printf 'manifest_records=%s\n' "$manifest_records"
printf 'archive_path=%s\n' "$ARCHIVE"
printf 'archive_sha256=%s\n' "$expected_archive_sha"
printf 'archive_bytes=%s\n' "$expected_archive_bytes"
printf 'archive_inventory_sha256=%s\n' "$expected_archive_inventory_sha"
printf 'gate_d_ready_path=%s\n' "$GATE_D_READY_FINAL"
printf '%s\n' 'SOURCE_STABILITY=PASS'

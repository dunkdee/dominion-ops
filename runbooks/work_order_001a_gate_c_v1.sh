#!/usr/bin/env bash
set -euo pipefail

# Work Order 001A — Approval Gate C v1
# Creates and validates one releases archive from the exact Gate B generation.
# This script does not transfer, upload, delete source data, restart services,
# merge, deploy, install packages, or continue to Gate D.

SOURCE=/home/malachisingleton8/releases
EXPECTED=/home/malachisingleton8/releases
GATE_B_READY=/tmp/dominion-releases-gate-b.ready
SOURCE_INV=/tmp/dominion-releases-source-inventory.txt
SOURCE_MANIFEST=/tmp/dominion-releases-source-manifest.sha256
ARCHIVE_FINAL=/tmp/dominion-releases-20260730.tar.gz
ARCHIVE_SHA_FINAL=/tmp/dominion-releases-20260730.tar.gz.sha256
ARCHIVE_INV_FINAL=/tmp/dominion-releases-archive-inventory.txt
GATE_C_READY_FINAL=/tmp/dominion-releases-gate-c.ready

umask 077
EVIDENCE_DIR=$(mktemp -d /tmp/dominion-releases-gate-c.XXXXXX) || {
  echo 'BLOCKED: unable to create private Gate C evidence directory'
  exit 40
}
ARCHIVE_TMP="$EVIDENCE_DIR/$(basename "$ARCHIVE_FINAL")"
ARCHIVE_SHA_TMP="$EVIDENCE_DIR/$(basename "$ARCHIVE_SHA_FINAL")"
ARCHIVE_INV_TMP="$EVIDENCE_DIR/$(basename "$ARCHIVE_INV_FINAL")"
READY_B_BEFORE="$EVIDENCE_DIR/gate-b.ready.before"
READY_B_AFTER="$EVIDENCE_DIR/gate-b.ready.after"
SOURCE_MANIFEST_BEFORE="$EVIDENCE_DIR/source-manifest.before.sha256"
SOURCE_MANIFEST_AFTER="$EVIDENCE_DIR/source-manifest.after.sha256"
SOURCE_METRICS_BEFORE="$EVIDENCE_DIR/source-metrics.before.txt"
SOURCE_METRICS_AFTER="$EVIDENCE_DIR/source-metrics.after.txt"
PUBLISHING_TMP="$EVIDENCE_DIR/gate-c.publishing"
READY_C_TMP="$EVIDENCE_DIR/gate-c.ready"

printf '%s\n' '=== WORK ORDER 001A ARCHIVE CREATION V1 ==='
printf 'evidence_dir=%s\n' "$EVIDENCE_DIR"

resolved=$(readlink -f -- "$SOURCE")
printf 'resolved_source=%s\n' "$resolved"
[ "$resolved" = "$EXPECTED" ] || { echo 'BLOCKED: source path mismatch'; exit 41; }
[ -d "$SOURCE" ] || { echo 'BLOCKED: source is not a directory'; exit 42; }
[ ! -L "$SOURCE" ] || { echo 'BLOCKED: source is a symlink'; exit 43; }

for required_command in awk basename chmod cmp cp find lsof mktemp mv python3 readlink sed sha256sum stat tar wc; do
  command -v "$required_command" >/dev/null 2>&1 || {
    echo "BLOCKED: required command unavailable: $required_command"
    exit 44
  }
done

for artifact in "$GATE_B_READY" "$SOURCE_INV" "$SOURCE_MANIFEST"; do
  [ -f "$artifact" ] && [ ! -L "$artifact" ] || {
    echo "BLOCKED: required Gate B artifact missing or unsafe: $artifact"
    exit 45
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

cp -- "$GATE_B_READY" "$READY_B_BEFORE"
[ "$(ready_value status "$READY_B_BEFORE")" = READY ] || {
  echo 'BLOCKED: Gate B handoff is not READY'
  exit 46
}
[ "$(ready_value inventory_path "$READY_B_BEFORE")" = "$SOURCE_INV" ] || {
  echo 'BLOCKED: Gate B inventory path mismatch'
  exit 47
}
[ "$(ready_value manifest_path "$READY_B_BEFORE")" = "$SOURCE_MANIFEST" ] || {
  echo 'BLOCKED: Gate B manifest path mismatch'
  exit 48
}

expected_inventory_sha=$(ready_value inventory_sha256 "$READY_B_BEFORE")
expected_manifest_sha=$(ready_value manifest_sha256 "$READY_B_BEFORE")
expected_regular_files=$(ready_value regular_files "$READY_B_BEFORE")
expected_manifest_records=$(ready_value manifest_records "$READY_B_BEFORE")
expected_gate_b_generation=$(ready_value generation "$READY_B_BEFORE")
expected_canonical_state_sha=$(ready_value canonical_state_sha256 "$READY_B_BEFORE")

actual_inventory_sha=$(sha256sum "$SOURCE_INV" | awk '{print $1}')
actual_manifest_sha=$(sha256sum "$SOURCE_MANIFEST" | awk '{print $1}')
[ "$actual_inventory_sha" = "$expected_inventory_sha" ] || {
  echo 'BLOCKED: Gate B inventory digest mismatch'
  exit 49
}
[ "$actual_manifest_sha" = "$expected_manifest_sha" ] || {
  echo 'BLOCKED: Gate B manifest digest mismatch'
  exit 50
}
[ "$expected_regular_files" -eq "$expected_manifest_records" ] || {
  echo 'BLOCKED: Gate B regular-file and manifest-record counts disagree'
  exit 51
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
    exit 52
  fi

  writers=$(awk 'NR>1 && $4 ~ /^[0-9]+[wu]/ {count++} END {print count+0}' "$out")
  printf 'open_write_handles_%s=%s\n' "$phase" "$writers"
  [ "$writers" -eq 0 ] || {
    echo "BLOCKED: source has open write handles during $phase"
    exit 53
  }
}

capture_source() {
  manifest_path=$1
  metrics_path=$2

  python3 - "$SOURCE" "$manifest_path" "$metrics_path" <<'PY'
import hashlib
import os
import stat
import sys

root_text, manifest_name, metrics_name = sys.argv[1:]
root = os.fsencode(root_text)
root_stat = os.lstat(root)
root_dev = root_stat.st_dev
entries = []


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


visit(root, b".")
entries.sort(key=lambda item: item[0])
counts = {"regular_files": 0, "directories": 0, "symlinks": 0, "special_members": 0}
regular_bytes = 0
inode_counts = {}
symlink_hash = hashlib.sha256()

with open(manifest_name, "wb") as manifest_out:
    for rel, path in entries:
        before = os.lstat(path)
        mode = before.st_mode

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
            manifest_rel = b"./" + rel if rel != b"." else b"."
            manifest_out.write(h.hexdigest().encode("ascii") + b"  " + manifest_rel + b"\0")
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

hardlink_members = sum(count - 1 for count in inode_counts.values() if count > 1)
with open(metrics_name, "w", encoding="utf-8") as metrics:
    metrics.write(f"regular_files={counts['regular_files']}\n")
    metrics.write(f"directories={counts['directories']}\n")
    metrics.write(f"symlinks={counts['symlinks']}\n")
    metrics.write(f"special_members={counts['special_members']}\n")
    metrics.write(f"hardlink_members_expected={hardlink_members}\n")
    metrics.write(f"regular_file_bytes={regular_bytes}\n")
    metrics.write(f"symlink_target_sha256={symlink_hash.hexdigest()}\n")
PY
}

inventory_value() {
  key=$1
  awk -F= -v wanted="$key" '$1 == wanted { count++; value=$2 } END { if (count == 1) print value; else exit 1 }' "$SOURCE_INV"
}

validate_source_metrics() {
  metrics=$1
  for key in regular_files directories symlinks special_members hardlink_members_expected regular_file_bytes symlink_target_sha256; do
    expected=$(inventory_value "$key")
    actual=$(awk -F= -v wanted="$key" '$1 == wanted { count++; value=$2 } END { if (count == 1) print value; else exit 1 }' "$metrics")
    [ "$actual" = "$expected" ] || {
      echo "BLOCKED: source metric mismatch for $key"
      exit 54
    }
  done
}

check_writers before
capture_source "$SOURCE_MANIFEST_BEFORE" "$SOURCE_METRICS_BEFORE"
cmp -s "$SOURCE_MANIFEST" "$SOURCE_MANIFEST_BEFORE" || {
  echo 'BLOCKED: source content no longer matches Gate B manifest before archive creation'
  exit 55
}
validate_source_metrics "$SOURCE_METRICS_BEFORE"

# Create the archive only inside the private evidence directory. The source tree
# is read, never modified. GNU tar exits nonzero if it detects a changing file.
tar --one-file-system -C /home/malachisingleton8 -czf "$ARCHIVE_TMP" -- releases
tar -tzf "$ARCHIVE_TMP" >/dev/null

(
  cd "$EVIDENCE_DIR"
  sha256sum "$(basename "$ARCHIVE_TMP")"
) > "$ARCHIVE_SHA_TMP"

python3 - "$ARCHIVE_TMP" "$ARCHIVE_INV_TMP" <<'PY'
import ntpath
import posixpath
import re
import sys
import tarfile
from pathlib import PurePosixPath

archive, output = sys.argv[1:]
regular = directories = symlinks = hardlinks = others = 0
unsafe_names = []
unsafe_links = []
duplicate_names = []
root_ok = True
normalized_names = set()
windows_drive = re.compile(r"^[A-Za-z]:")


def windows_unsafe(value: str) -> bool:
    return (
        "\\" in value
        or value.startswith("//")
        or value.startswith("\\\\")
        or windows_drive.match(value) is not None
        or ntpath.isabs(value)
    )


def member_name_unsafe(value: str) -> bool:
    return value.startswith("/") or ".." in PurePosixPath(value).parts


def link_syntax_unsafe(value: str) -> bool:
    return value.startswith("/")


with tarfile.open(archive, mode="r:gz") as tf:
    members = tf.getmembers()

    for member in members:
        raw_name = member.name
        normalized = posixpath.normpath(raw_name)
        if windows_unsafe(raw_name) or member_name_unsafe(raw_name):
            unsafe_names.append(raw_name)
        if not (normalized == "releases" or normalized.startswith("releases/")):
            root_ok = False
        if normalized in normalized_names:
            duplicate_names.append(raw_name)
        normalized_names.add(normalized)

    for member in members:
        name = posixpath.normpath(member.name)

        if member.isfile():
            regular += 1
        elif member.isdir():
            directories += 1
        elif member.issym():
            symlinks += 1
            link = member.linkname
            if windows_unsafe(link) or link_syntax_unsafe(link):
                unsafe_links.append(f"{member.name} -> {link}")
            else:
                target = posixpath.normpath(posixpath.join(posixpath.dirname(name), link))
                if not (target == "releases" or target.startswith("releases/")):
                    unsafe_links.append(f"{member.name} -> {link}")
        elif member.islnk():
            hardlinks += 1
            link = member.linkname
            if windows_unsafe(link) or link_syntax_unsafe(link):
                unsafe_links.append(f"{member.name} -> {link}")
            else:
                target = posixpath.normpath(link)
                if not (target == "releases" or target.startswith("releases/")):
                    unsafe_links.append(f"{member.name} -> {link}")
                elif target not in normalized_names:
                    unsafe_links.append(f"{member.name} -> missing:{link}")
        else:
            others += 1

with open(output, "w", encoding="utf-8") as fh:
    fh.write(f"regular_members={regular}\n")
    fh.write(f"directory_members={directories}\n")
    fh.write(f"symlink_members={symlinks}\n")
    fh.write(f"hardlink_members={hardlinks}\n")
    fh.write(f"other_members={others}\n")
    fh.write(f"root_ok={str(root_ok).lower()}\n")
    fh.write(f"unsafe_names={len(unsafe_names)}\n")
    fh.write(f"unsafe_links={len(unsafe_links)}\n")
    fh.write(f"duplicate_names={len(duplicate_names)}\n")

if unsafe_names or unsafe_links or duplicate_names or not root_ok or others:
    raise SystemExit(56)
PY

source_regular=$(inventory_value regular_files)
source_dirs=$(inventory_value directories)
source_links=$(inventory_value symlinks)
source_hardlinks=$(inventory_value hardlink_members_expected)
archive_regular=$(awk -F= '$1=="regular_members"{print $2}' "$ARCHIVE_INV_TMP")
archive_dirs=$(awk -F= '$1=="directory_members"{print $2}' "$ARCHIVE_INV_TMP")
archive_links=$(awk -F= '$1=="symlink_members"{print $2}' "$ARCHIVE_INV_TMP")
archive_hardlinks=$(awk -F= '$1=="hardlink_members"{print $2}' "$ARCHIVE_INV_TMP")
archive_others=$(awk -F= '$1=="other_members"{print $2}' "$ARCHIVE_INV_TMP")
unsafe_names=$(awk -F= '$1=="unsafe_names"{print $2}' "$ARCHIVE_INV_TMP")
unsafe_links=$(awk -F= '$1=="unsafe_links"{print $2}' "$ARCHIVE_INV_TMP")
duplicate_names=$(awk -F= '$1=="duplicate_names"{print $2}' "$ARCHIVE_INV_TMP")
root_ok=$(awk -F= '$1=="root_ok"{print $2}' "$ARCHIVE_INV_TMP")

[ "$source_regular" -eq $((archive_regular + archive_hardlinks)) ] || {
  echo 'BLOCKED: regular-path accounting mismatch'
  exit 57
}
[ "$source_dirs" -eq "$archive_dirs" ] || { echo 'BLOCKED: directory count mismatch'; exit 58; }
[ "$source_links" -eq "$archive_links" ] || { echo 'BLOCKED: symlink count mismatch'; exit 59; }
[ "$source_hardlinks" -eq "$archive_hardlinks" ] || { echo 'BLOCKED: hard-link count mismatch'; exit 60; }
[ "$archive_others" -eq 0 ] || { echo 'BLOCKED: unsupported archive member'; exit 61; }
[ "$unsafe_names" -eq 0 ] || { echo 'BLOCKED: unsafe archive path'; exit 62; }
[ "$unsafe_links" -eq 0 ] || { echo 'BLOCKED: unsafe archive link target'; exit 63; }
[ "$duplicate_names" -eq 0 ] || { echo 'BLOCKED: duplicate normalized archive path'; exit 64; }
[ "$root_ok" = true ] || { echo 'BLOCKED: unexpected archive root'; exit 65; }

capture_source "$SOURCE_MANIFEST_AFTER" "$SOURCE_METRICS_AFTER"
check_writers after
cmp -s "$SOURCE_MANIFEST" "$SOURCE_MANIFEST_AFTER" || {
  echo 'BLOCKED: source content changed during archive creation'
  exit 66
}
cmp -s "$SOURCE_METRICS_BEFORE" "$SOURCE_METRICS_AFTER" || {
  echo 'BLOCKED: source metrics changed during archive creation'
  exit 67
}

cp -- "$GATE_B_READY" "$READY_B_AFTER"
cmp -s "$READY_B_BEFORE" "$READY_B_AFTER" || {
  echo 'BLOCKED: Gate B generation changed during Gate C'
  exit 68
}
[ "$(sha256sum "$SOURCE_INV" | awk '{print $1}')" = "$expected_inventory_sha" ] || {
  echo 'BLOCKED: Gate B inventory changed during Gate C'
  exit 69
}
[ "$(sha256sum "$SOURCE_MANIFEST" | awk '{print $1}')" = "$expected_manifest_sha" ] || {
  echo 'BLOCKED: Gate B manifest changed during Gate C'
  exit 70
}

for handoff in "$ARCHIVE_FINAL" "$ARCHIVE_SHA_FINAL" "$ARCHIVE_INV_FINAL" "$GATE_C_READY_FINAL"; do
  [ ! -d "$handoff" ] || {
    echo "BLOCKED: handoff path is a directory: $handoff"
    exit 71
  }
done

archive_sha=$(sha256sum "$ARCHIVE_TMP" | awk '{print $1}')
archive_bytes=$(stat --format='%s' "$ARCHIVE_TMP")
archive_inventory_sha=$(sha256sum "$ARCHIVE_INV_TMP" | awk '{print $1}')
gate_c_generation=$(basename "$EVIDENCE_DIR")

printf 'status=PUBLISHING\ngeneration=%s\n' "$gate_c_generation" > "$PUBLISHING_TMP"
mv -fT -- "$PUBLISHING_TMP" "$GATE_C_READY_FINAL"

mv -fT -- "$ARCHIVE_TMP" "$ARCHIVE_FINAL"
mv -fT -- "$ARCHIVE_SHA_TMP" "$ARCHIVE_SHA_FINAL"
mv -fT -- "$ARCHIVE_INV_TMP" "$ARCHIVE_INV_FINAL"
chmod 600 -- "$ARCHIVE_FINAL" "$ARCHIVE_SHA_FINAL" "$ARCHIVE_INV_FINAL" "$GATE_C_READY_FINAL"

published_archive_sha=$(sha256sum "$ARCHIVE_FINAL" | awk '{print $1}')
published_archive_inventory_sha=$(sha256sum "$ARCHIVE_INV_FINAL" | awk '{print $1}')
[ "$published_archive_sha" = "$archive_sha" ] || {
  echo 'BLOCKED: published archive digest mismatch'
  exit 72
}
[ "$published_archive_inventory_sha" = "$archive_inventory_sha" ] || {
  echo 'BLOCKED: published archive inventory digest mismatch'
  exit 73
}
(
  cd "$(dirname "$ARCHIVE_FINAL")"
  sha256sum -c --status "$(basename "$ARCHIVE_SHA_FINAL")"
) || {
  echo 'BLOCKED: published archive checksum verification failed'
  exit 74
}

cat > "$READY_C_TMP" <<EOF
status=READY
generation=$gate_c_generation
gate_b_generation=$expected_gate_b_generation
gate_b_canonical_state_sha256=$expected_canonical_state_sha
source_inventory_path=$SOURCE_INV
source_inventory_sha256=$expected_inventory_sha
source_manifest_path=$SOURCE_MANIFEST
source_manifest_sha256=$expected_manifest_sha
archive_path=$ARCHIVE_FINAL
archive_sha256=$archive_sha
archive_bytes=$archive_bytes
archive_checksum_path=$ARCHIVE_SHA_FINAL
archive_inventory_path=$ARCHIVE_INV_FINAL
archive_inventory_sha256=$archive_inventory_sha
regular_files=$source_regular
directories=$source_dirs
symlinks=$source_links
hardlink_members=$source_hardlinks
EOF
chmod 600 -- "$READY_C_TMP"
mv -fT -- "$READY_C_TMP" "$GATE_C_READY_FINAL"
chmod 600 -- "$GATE_C_READY_FINAL"

printf 'gate_b_generation=%s\n' "$expected_gate_b_generation"
printf 'gate_c_generation=%s\n' "$gate_c_generation"
printf 'archive_path=%s\n' "$ARCHIVE_FINAL"
printf 'archive_sha256=%s\n' "$archive_sha"
printf 'archive_bytes=%s\n' "$archive_bytes"
printf 'archive_checksum_path=%s\n' "$ARCHIVE_SHA_FINAL"
printf 'archive_inventory_path=%s\n' "$ARCHIVE_INV_FINAL"
printf 'archive_inventory_sha256=%s\n' "$archive_inventory_sha"
printf 'gate_c_ready_path=%s\n' "$GATE_C_READY_FINAL"
printf 'regular_files=%s\n' "$source_regular"
printf 'directories=%s\n' "$source_dirs"
printf 'symlinks=%s\n' "$source_links"
printf 'hardlink_members=%s\n' "$source_hardlinks"
printf '%s\n' 'ARCHIVE_CREATION=PASS'

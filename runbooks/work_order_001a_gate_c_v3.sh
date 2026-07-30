#!/usr/bin/env bash
set -euo pipefail

# Work Order 001A — Approval Gate C v3
# Creates one archive from the exact Gate B-certified source state and validates
# topology, counts, hard links, every regular-file digest, and source stability.
# It does not modify the source tree, upload, transfer, extract, or delete data.

SOURCE=/home/malachisingleton8/releases
EXPECTED=/home/malachisingleton8/releases
GATE_B_READY=/tmp/dominion-releases-gate-b.ready
SOURCE_INVENTORY=/tmp/dominion-releases-source-inventory.txt
SOURCE_MANIFEST=/tmp/dominion-releases-source-manifest.sha256
ARCHIVE_FINAL=/tmp/dominion-releases-20260730.tar.gz
ARCHIVE_SHA_FINAL=/tmp/dominion-releases-20260730.tar.gz.sha256
ARCHIVE_INVENTORY_FINAL=/tmp/dominion-releases-archive-inventory.txt
GATE_C_READY_FINAL=/tmp/dominion-releases-gate-c.ready

umask 077
EVIDENCE_DIR=$(mktemp -d /tmp/dominion-releases-gate-c.XXXXXX) || {
  echo 'BLOCKED: unable to create private Gate C evidence directory'
  exit 38
}
GATE_B_READY_COPY="$EVIDENCE_DIR/gate-b.ready"
SOURCE_INVENTORY_COPY="$EVIDENCE_DIR/source-inventory.txt"
SOURCE_MANIFEST_COPY="$EVIDENCE_DIR/source-manifest.sha256"
STATE_BEFORE="$EVIDENCE_DIR/source-state.before.bin"
STATE_AFTER="$EVIDENCE_DIR/source-state.after.bin"
MANIFEST_BEFORE="$EVIDENCE_DIR/source-manifest.before.sha256"
MANIFEST_AFTER="$EVIDENCE_DIR/source-manifest.after.sha256"
METRICS_BEFORE="$EVIDENCE_DIR/source-metrics.before.txt"
METRICS_AFTER="$EVIDENCE_DIR/source-metrics.after.txt"
ARCHIVE_TMP="$EVIDENCE_DIR/dominion-releases-20260730.tar.gz"
ARCHIVE_SHA_TMP="$EVIDENCE_DIR/dominion-releases-20260730.tar.gz.sha256"
ARCHIVE_INVENTORY_TMP="$EVIDENCE_DIR/dominion-releases-archive-inventory.txt"
ARCHIVE_MANIFEST_TMP="$EVIDENCE_DIR/archive-manifest.sha256"
READY_TMP="$EVIDENCE_DIR/gate-c.ready"
PUBLISHING_TMP="$EVIDENCE_DIR/gate-c.publishing"

printf '%s\n' '=== WORK ORDER 001A ARCHIVE CREATION V3 ==='
printf 'evidence_dir=%s\n' "$EVIDENCE_DIR"

resolved=$(readlink -f -- "$SOURCE")
printf 'resolved_source=%s\n' "$resolved"
[ "$resolved" = "$EXPECTED" ] || { echo 'BLOCKED: source path mismatch'; exit 40; }
[ -d "$SOURCE" ] || { echo 'BLOCKED: source is not a directory'; exit 41; }
[ ! -L "$SOURCE" ] || { echo 'BLOCKED: source is a symlink'; exit 42; }

for required_command in awk chmod cmp cp lsof mktemp mv python3 readlink sha256sum stat tar; do
  command -v "$required_command" >/dev/null 2>&1 || {
    echo "BLOCKED: required command unavailable: $required_command"
    exit 43
  }
done

for required_file in "$GATE_B_READY" "$SOURCE_INVENTORY" "$SOURCE_MANIFEST"; do
  [ -f "$required_file" ] && [ ! -L "$required_file" ] || {
    echo "BLOCKED: required Gate B artifact missing or unsafe: $required_file"
    exit 44
  }
done

# Snapshot the three Gate B handoff files once. Every later read uses these
# private copies so a concurrent replacement cannot mix generations.
cp -- "$GATE_B_READY" "$GATE_B_READY_COPY"
cp -- "$SOURCE_INVENTORY" "$SOURCE_INVENTORY_COPY"
cp -- "$SOURCE_MANIFEST" "$SOURCE_MANIFEST_COPY"
chmod 600 -- "$GATE_B_READY_COPY" "$SOURCE_INVENTORY_COPY" "$SOURCE_MANIFEST_COPY"

read_ready_key() {
  key=$1
  value=$(awk -F= -v wanted="$key" '$1==wanted {count++; value=substr($0,index($0,"=")+1)} END {if(count==1) print value; else exit 1}' "$GATE_B_READY_COPY") || {
    echo "BLOCKED: Gate B READY key missing or duplicated: $key"
    exit 45
  }
  [ -n "$value" ] || {
    echo "BLOCKED: Gate B READY key is empty: $key"
    exit 46
  }
  printf '%s' "$value"
}

[ "$(read_ready_key status)" = READY ] || { echo 'BLOCKED: Gate B is not READY'; exit 47; }
[ "$(read_ready_key inventory_path)" = "$SOURCE_INVENTORY" ] || { echo 'BLOCKED: Gate B inventory path mismatch'; exit 48; }
[ "$(read_ready_key manifest_path)" = "$SOURCE_MANIFEST" ] || { echo 'BLOCKED: Gate B manifest path mismatch'; exit 49; }

GATE_B_GENERATION=$(read_ready_key generation)
GATE_B_INVENTORY_SHA=$(read_ready_key inventory_sha256)
GATE_B_MANIFEST_SHA=$(read_ready_key manifest_sha256)
GATE_B_STATE_SHA=$(read_ready_key canonical_state_sha256)
GATE_B_REGULAR_FILES=$(read_ready_key regular_files)
GATE_B_MANIFEST_RECORDS=$(read_ready_key manifest_records)

case "$GATE_B_GENERATION" in dominion-releases-gate-b.*) ;; *) echo 'BLOCKED: invalid Gate B generation'; exit 50 ;; esac
for digest in "$GATE_B_INVENTORY_SHA" "$GATE_B_MANIFEST_SHA" "$GATE_B_STATE_SHA"; do
  case "$digest" in *[!0-9a-f]*|'') echo 'BLOCKED: invalid Gate B digest format'; exit 51 ;; esac
  [ "${#digest}" -eq 64 ] || { echo 'BLOCKED: invalid Gate B digest length'; exit 52; }
done
for count in "$GATE_B_REGULAR_FILES" "$GATE_B_MANIFEST_RECORDS"; do
  case "$count" in *[!0-9]*|'') echo 'BLOCKED: invalid Gate B count format'; exit 53 ;; esac
done
[ "$GATE_B_REGULAR_FILES" -eq "$GATE_B_MANIFEST_RECORDS" ] || {
  echo 'BLOCKED: Gate B regular-file and manifest counts differ'
  exit 54
}

actual_inventory_sha=$(sha256sum "$SOURCE_INVENTORY_COPY" | awk '{print $1}')
actual_manifest_sha=$(sha256sum "$SOURCE_MANIFEST_COPY" | awk '{print $1}')
[ "$actual_inventory_sha" = "$GATE_B_INVENTORY_SHA" ] || { echo 'BLOCKED: Gate B inventory digest mismatch'; exit 55; }
[ "$actual_manifest_sha" = "$GATE_B_MANIFEST_SHA" ] || { echo 'BLOCKED: Gate B manifest digest mismatch'; exit 56; }

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
    :
  elif [ "$rc" -ne 0 ]; then
    echo "BLOCKED: lsof $phase inspection failed rc=$rc"
    [ ! -s "$err" ] || sed -n '1,20p' "$err"
    exit 57
  fi
  writers=$(awk 'NR>1 && $4 ~ /^[0-9]+[wu]/ {count++} END {print count+0}' "$out")
  printf 'open_write_handles_%s=%s\n' "$phase" "$writers"
  [ "$writers" -eq 0 ] || { echo "BLOCKED: source has open write handles during $phase"; exit 58; }
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
root_dev = os.lstat(root).st_dev
entries = []

def visit(path: bytes, rel: bytes) -> None:
    st = os.lstat(path)
    entries.append((rel, path))
    if stat.S_ISDIR(st.st_mode) and st.st_dev == root_dev:
        with os.scandir(path) as scan:
            children = sorted(scan, key=lambda entry: entry.name)
        for entry in children:
            child_rel = entry.name if rel == b'.' else rel + b'/' + entry.name
            visit(os.path.join(path, entry.name), child_rel)

def stable_fields(st):
    return (st.st_mode, st.st_uid, st.st_gid, st.st_size, st.st_mtime_ns,
            st.st_ctime_ns, st.st_dev, st.st_ino, st.st_nlink, st.st_rdev)

def write_field(stream, value: bytes) -> None:
    stream.write(len(value).to_bytes(8, 'big'))
    stream.write(value)

visit(root, b'.')
entries.sort(key=lambda item: item[0])
counts = {'regular_files': 0, 'directories': 0, 'symlinks': 0, 'special_members': 0}
regular_bytes = 0
inode_counts = {}
symlink_hash = hashlib.sha256()

with open(state_name, 'wb') as state_out, open(manifest_name, 'wb') as manifest_out:
    for rel, path in entries:
        before = os.lstat(path)
        mode = before.st_mode
        target = b''
        digest = b''
        if stat.S_ISREG(mode):
            counts['regular_files'] += 1
            regular_bytes += before.st_size
            inode_counts[(before.st_dev, before.st_ino)] = inode_counts.get((before.st_dev, before.st_ino), 0) + 1
            fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
            try:
                opened_before = os.fstat(fd)
                if (opened_before.st_dev, opened_before.st_ino) != (before.st_dev, before.st_ino):
                    raise RuntimeError('file identity changed before hashing')
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
                raise RuntimeError('file changed while hashing')
            digest = h.hexdigest().encode('ascii')
            manifest_out.write(digest + b'  ' + (b'./' + rel if rel != b'.' else b'.') + b'\0')
        elif stat.S_ISDIR(mode):
            counts['directories'] += 1
        elif stat.S_ISLNK(mode):
            counts['symlinks'] += 1
            target = os.readlink(path)
            symlink_hash.update(len(rel).to_bytes(8, 'big') + rel)
            symlink_hash.update(len(target).to_bytes(8, 'big') + target)
        else:
            counts['special_members'] += 1
        after = os.lstat(path)
        if stable_fields(before) != stable_fields(after):
            raise RuntimeError('source entry changed during canonical scan')
        kind = b'f' if stat.S_ISREG(mode) else b'd' if stat.S_ISDIR(mode) else b'l' if stat.S_ISLNK(mode) else b'o'
        fields = [rel, kind, str(before.st_mode).encode(), str(before.st_uid).encode(),
                  str(before.st_gid).encode(), str(before.st_size).encode(),
                  str(before.st_mtime_ns).encode(), str(before.st_ctime_ns).encode(),
                  str(before.st_dev).encode(), str(before.st_ino).encode(),
                  str(before.st_nlink).encode(), str(before.st_rdev).encode(), target, digest]
        for field in fields:
            write_field(state_out, field)

hardlinks = sum(count - 1 for count in inode_counts.values() if count > 1)
with open(metrics_name, 'w', encoding='utf-8') as metrics:
    metrics.write(f"regular_files={counts['regular_files']}\n")
    metrics.write(f"directories={counts['directories']}\n")
    metrics.write(f"symlinks={counts['symlinks']}\n")
    metrics.write(f"special_members={counts['special_members']}\n")
    metrics.write(f"hardlink_members_expected={hardlinks}\n")
    metrics.write(f"regular_file_bytes={regular_bytes}\n")
    metrics.write(f"symlink_target_sha256={symlink_hash.hexdigest()}\n")
PY
}

check_writers before
capture_state "$STATE_BEFORE" "$MANIFEST_BEFORE" "$METRICS_BEFORE"
state_before_sha=$(sha256sum "$STATE_BEFORE" | awk '{print $1}')
[ "$state_before_sha" = "$GATE_B_STATE_SHA" ] || { echo 'BLOCKED: source no longer matches Gate B certified state'; exit 59; }
cmp -s "$MANIFEST_BEFORE" "$SOURCE_MANIFEST_COPY" || { echo 'BLOCKED: current source manifest differs from Gate B manifest'; exit 60; }

special_members=$(awk -F= '$1=="special_members"{print $2}' "$METRICS_BEFORE")
regular_files=$(awk -F= '$1=="regular_files"{print $2}' "$METRICS_BEFORE")
directories=$(awk -F= '$1=="directories"{print $2}' "$METRICS_BEFORE")
symlinks=$(awk -F= '$1=="symlinks"{print $2}' "$METRICS_BEFORE")
hardlinks=$(awk -F= '$1=="hardlink_members_expected"{print $2}' "$METRICS_BEFORE")
[ "$special_members" -eq 0 ] || { echo "BLOCKED: unsupported source special members=$special_members"; exit 61; }
[ "$regular_files" -eq "$GATE_B_REGULAR_FILES" ] || { echo 'BLOCKED: Gate B regular-file count mismatch'; exit 62; }

for handoff in "$ARCHIVE_FINAL" "$ARCHIVE_SHA_FINAL" "$ARCHIVE_INVENTORY_FINAL" "$GATE_C_READY_FINAL"; do
  [ ! -d "$handoff" ] || { echo "BLOCKED: output path is a directory: $handoff"; exit 63; }
done

tar --one-file-system -C /home/malachisingleton8 -czf "$ARCHIVE_TMP" -- releases
tar -tzf "$ARCHIVE_TMP" >/dev/null

python3 - "$ARCHIVE_TMP" "$ARCHIVE_INVENTORY_TMP" "$ARCHIVE_MANIFEST_TMP" \
  "$regular_files" "$directories" "$symlinks" "$hardlinks" <<'PY'
import hashlib
import ntpath
import posixpath
import re
import sys
import tarfile

archive, inventory, manifest, er, ed, es, eh = sys.argv[1:]
expected_regular, expected_dirs, expected_symlinks, expected_hardlinks = map(int, (er, ed, es, eh))
regular = directories = symlinks = hardlinks = others = 0
unsafe_names, unsafe_links, duplicates = [], [], []
members_by_name, digests = {}, {}

def windows_unsafe(value: str) -> bool:
    return ('\\' in value or value.startswith('//') or value.startswith('\\\\')
            or bool(re.match(r'^[A-Za-z]:', value)) or bool(ntpath.splitdrive(value)[0]))

def normalize_member(raw: str):
    if not raw or windows_unsafe(raw) or raw.startswith('/') or '..' in raw.split('/'):
        return None
    name = posixpath.normpath(raw)
    return name if name == 'releases' or name.startswith('releases/') else None

with tarfile.open(archive, 'r:gz') as tf:
    for member in tf.getmembers():
        name = normalize_member(member.name)
        if name is None:
            unsafe_names.append(member.name)
            continue
        if name in members_by_name:
            duplicates.append(member.name)
        members_by_name[name] = member

    for name, member in members_by_name.items():
        if member.isfile():
            regular += 1
            stream = tf.extractfile(member)
            if stream is None:
                raise RuntimeError(f'unreadable regular member: {member.name}')
            h = hashlib.sha256()
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                h.update(chunk)
            digests[name] = h.hexdigest()
        elif member.isdir():
            directories += 1
        elif member.issym():
            symlinks += 1
            link = member.linkname
            if not link or windows_unsafe(link) or posixpath.isabs(link) or '..' in link.split('/'):
                unsafe_links.append(f'{member.name} -> {link}')
            else:
                target = posixpath.normpath(posixpath.join(posixpath.dirname(name), link))
                if target != 'releases' and not target.startswith('releases/'):
                    unsafe_links.append(f'{member.name} -> {link}')
        elif member.islnk():
            hardlinks += 1
            link = member.linkname
            if not link or windows_unsafe(link) or posixpath.isabs(link) or '..' in link.split('/'):
                unsafe_links.append(f'{member.name} -> {link}')
            elif posixpath.normpath(link) not in members_by_name:
                unsafe_links.append(f'{member.name} -> missing:{link}')
        else:
            others += 1

    def digest_for(name: str, trail=None):
        if name in digests:
            return digests[name]
        member = members_by_name.get(name)
        if member is None or not member.islnk():
            raise RuntimeError(f'missing hardlink target: {name}')
        trail = set() if trail is None else trail
        if name in trail:
            raise RuntimeError(f'hardlink cycle: {name}')
        trail.add(name)
        target = posixpath.normpath(member.linkname)
        digest = digest_for(target, trail)
        digests[name] = digest
        return digest

    records = []
    for name, member in members_by_name.items():
        if member.isfile() or member.islnk():
            rel = name[len('releases/'):] if name.startswith('releases/') else '.'
            records.append((rel.encode('utf-8', 'surrogateescape'), digest_for(name)))
    records.sort(key=lambda item: item[0])
    with open(manifest, 'wb') as output:
        for rel, digest in records:
            output.write(digest.encode('ascii') + b'  ' + (b'./' + rel if rel != b'.' else b'.') + b'\0')

with open(inventory, 'w', encoding='utf-8') as output:
    output.write(f'regular_members={regular}\n')
    output.write(f'directory_members={directories}\n')
    output.write(f'symlink_members={symlinks}\n')
    output.write(f'hardlink_members={hardlinks}\n')
    output.write(f'other_members={others}\n')
    output.write(f'unsafe_names={len(unsafe_names)}\n')
    output.write(f'unsafe_links={len(unsafe_links)}\n')
    output.write(f'duplicate_names={len(duplicates)}\n')

if unsafe_names or unsafe_links or duplicates or others:
    raise SystemExit('unsafe archive topology')
if regular + hardlinks != expected_regular:
    raise SystemExit(f'archive file-path count mismatch: {regular}+{hardlinks}!={expected_regular}')
if directories != expected_dirs or symlinks != expected_symlinks or hardlinks != expected_hardlinks:
    raise SystemExit('archive member-class count mismatch')
PY

cmp -s "$ARCHIVE_MANIFEST_TMP" "$SOURCE_MANIFEST_COPY" || { echo 'BLOCKED: archive manifest differs from Gate B source manifest'; exit 64; }

capture_state "$STATE_AFTER" "$MANIFEST_AFTER" "$METRICS_AFTER"
check_writers after
cmp -s "$STATE_BEFORE" "$STATE_AFTER" || { echo 'BLOCKED: canonical source state changed during archive creation'; exit 65; }
cmp -s "$MANIFEST_BEFORE" "$MANIFEST_AFTER" || { echo 'BLOCKED: source content changed during archive creation'; exit 66; }
cmp -s "$METRICS_BEFORE" "$METRICS_AFTER" || { echo 'BLOCKED: source metrics changed during archive creation'; exit 67; }

archive_bytes=$(stat --format='%s' "$ARCHIVE_TMP")
(
  cd "$EVIDENCE_DIR"
  sha256sum "$(basename "$ARCHIVE_TMP")"
) > "$ARCHIVE_SHA_TMP"
archive_sha=$(awk '{print $1}' "$ARCHIVE_SHA_TMP")
archive_manifest_sha=$(sha256sum "$ARCHIVE_MANIFEST_TMP" | awk '{print $1}')

{
  printf 'archive_bytes=%s\n' "$archive_bytes"
  printf 'archive_sha256=%s\n' "$archive_sha"
  printf 'archive_manifest_sha256=%s\n' "$archive_manifest_sha"
  cat "$ARCHIVE_INVENTORY_TMP"
} > "$EVIDENCE_DIR/archive-inventory.complete"
mv -fT -- "$EVIDENCE_DIR/archive-inventory.complete" "$ARCHIVE_INVENTORY_TMP"

printf 'status=PUBLISHING\ngate_b_generation=%s\n' "$GATE_B_GENERATION" > "$PUBLISHING_TMP"
mv -fT -- "$PUBLISHING_TMP" "$GATE_C_READY_FINAL"
mv -fT -- "$ARCHIVE_TMP" "$ARCHIVE_FINAL"
mv -fT -- "$ARCHIVE_SHA_TMP" "$ARCHIVE_SHA_FINAL"
mv -fT -- "$ARCHIVE_INVENTORY_TMP" "$ARCHIVE_INVENTORY_FINAL"
chmod 600 -- "$ARCHIVE_FINAL" "$ARCHIVE_SHA_FINAL" "$ARCHIVE_INVENTORY_FINAL" "$GATE_C_READY_FINAL"

published_archive_sha=$(sha256sum "$ARCHIVE_FINAL" | awk '{print $1}')
published_checksum_sha=$(sha256sum "$ARCHIVE_SHA_FINAL" | awk '{print $1}')
published_inventory_sha=$(sha256sum "$ARCHIVE_INVENTORY_FINAL" | awk '{print $1}')
[ "$published_archive_sha" = "$archive_sha" ] || { echo 'BLOCKED: published archive digest mismatch'; exit 68; }

generation=$(basename "$EVIDENCE_DIR")
cat > "$READY_TMP" <<EOF
status=READY
generation=$generation
gate_b_generation=$GATE_B_GENERATION
archive_path=$ARCHIVE_FINAL
archive_sha256=$published_archive_sha
archive_checksum_path=$ARCHIVE_SHA_FINAL
archive_checksum_sha256=$published_checksum_sha
archive_inventory_path=$ARCHIVE_INVENTORY_FINAL
archive_inventory_sha256=$published_inventory_sha
source_inventory_path=$SOURCE_INVENTORY
source_inventory_sha256=$actual_inventory_sha
source_manifest_path=$SOURCE_MANIFEST
source_manifest_sha256=$actual_manifest_sha
regular_files=$regular_files
archive_bytes=$archive_bytes
EOF
chmod 600 -- "$READY_TMP"
mv -fT -- "$READY_TMP" "$GATE_C_READY_FINAL"
chmod 600 -- "$GATE_C_READY_FINAL"

printf 'gate_b_generation=%s\n' "$GATE_B_GENERATION"
printf 'archive_path=%s\n' "$ARCHIVE_FINAL"
printf 'archive_bytes=%s\n' "$archive_bytes"
printf 'archive_sha256=%s\n' "$published_archive_sha"
printf 'archive_checksum_path=%s\n' "$ARCHIVE_SHA_FINAL"
printf 'archive_inventory_path=%s\n' "$ARCHIVE_INVENTORY_FINAL"
printf 'gate_c_ready_path=%s\n' "$GATE_C_READY_FINAL"
printf '%s\n' 'ARCHIVE_CREATION=PASS'

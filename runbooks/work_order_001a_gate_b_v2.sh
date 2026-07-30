#!/usr/bin/env bash
set -euo pipefail

# Work Order 001A — Approval Gate B v2
# Creates a deterministic, one-filesystem source inventory and NUL-delimited
# SHA-256 manifest without modifying the releases source tree.

SOURCE=/home/malachisingleton8/releases
EXPECTED=/home/malachisingleton8/releases
INVENTORY_FINAL=/tmp/dominion-releases-source-inventory.txt
MANIFEST_FINAL=/tmp/dominion-releases-source-manifest.sha256

umask 077
EVIDENCE_DIR=$(mktemp -d /tmp/dominion-releases-gate-b.XXXXXX) || {
  echo 'BLOCKED: unable to create private Gate B evidence directory'
  exit 18
}
INVENTORY_TMP="$EVIDENCE_DIR/source-inventory.txt"
MANIFEST_TMP="$EVIDENCE_DIR/source-manifest.sha256"

printf '%s\n' '=== WORK ORDER 001A SOURCE INVENTORY V2 ==='
printf 'evidence_dir=%s\n' "$EVIDENCE_DIR"

resolved=$(readlink -f -- "$SOURCE")
printf 'resolved_source=%s\n' "$resolved"
[ "$resolved" = "$EXPECTED" ] || { echo 'BLOCKED: source path mismatch'; exit 20; }
[ -d "$SOURCE" ] || { echo 'BLOCKED: source is not a directory'; exit 21; }
[ ! -L "$SOURCE" ] || { echo 'BLOCKED: source is a symlink'; exit 22; }

for required_command in find du awk sort uniq python3 sha256sum file xargs mv chmod tr wc; do
  command -v "$required_command" >/dev/null 2>&1 || {
    echo "BLOCKED: required command unavailable: $required_command"
    exit 23
  }
done

regular_files=$(find "$SOURCE" -xdev -type f -printf '.' | wc -c)
directories=$(find "$SOURCE" -xdev -type d -printf '.' | wc -c)
symlinks=$(find "$SOURCE" -xdev -type l -printf '.' | wc -c)
special_members=$(find "$SOURCE" -xdev ! -type f ! -type d ! -type l -printf '.' | wc -c)
regular_file_bytes=$(find "$SOURCE" -xdev -type f -printf '%s\n' \
  | awk '{sum += $1} END {printf "%.0f\n", sum+0}')
tree_apparent_bytes=$(du -x --apparent-size --bytes --summarize "$SOURCE" | awk '{print $1}')
hardlink_members_expected=$(find "$SOURCE" -xdev -type f -printf '%D:%i\n' \
  | LC_ALL=C sort \
  | uniq -c \
  | awk '$1 > 1 {sum += $1 - 1} END {print sum+0}')
oldest=$(find "$SOURCE" -xdev -printf '%T@\n' | LC_ALL=C sort -n | sed -n '1p')
newest=$(find "$SOURCE" -xdev -printf '%T@\n' | LC_ALL=C sort -n | tail -n 1)

symlink_target_sha256=$(find "$SOURCE" -xdev -type l -printf '%P\0%l\0' \
  | python3 -c 'import hashlib,sys; p=sys.stdin.buffer.read().split(b"\0"); pairs=list(zip(p[0::2],p[1::2])); h=hashlib.sha256(); [h.update(a+b"\0"+b+b"\0") for a,b in sorted(pairs) if a]; print(h.hexdigest())')

[ "$special_members" -eq 0 ] || {
  echo "BLOCKED: unsupported source special members=$special_members"
  exit 24
}

{
  echo 'source=/home/malachisingleton8/releases'
  echo 'filesystem_policy=one-filesystem'
  echo "regular_files=$regular_files"
  echo "directories=$directories"
  echo "symlinks=$symlinks"
  echo "special_members=$special_members"
  echo "hardlink_members_expected=$hardlink_members_expected"
  echo "regular_file_bytes=$regular_file_bytes"
  echo "tree_apparent_bytes=$tree_apparent_bytes"
  echo "symlink_target_sha256=$symlink_target_sha256"
  echo "oldest_mtime_epoch=$oldest"
  echo "newest_mtime_epoch=$newest"
  echo 'file_type_summary:'
  find "$SOURCE" -xdev -type f -print0 \
    | xargs -0 -r file --brief --mime-type -- \
    | LC_ALL=C sort \
    | uniq -c \
    | LC_ALL=C sort -nr
} > "$INVENTORY_TMP"

(
  cd "$SOURCE"
  LC_ALL=C find . -xdev -type f -print0 \
    | LC_ALL=C sort -z \
    | xargs -0 -r sha256sum -z --
) > "$MANIFEST_TMP"

manifest_records=$(tr -cd '\0' < "$MANIFEST_TMP" | wc -c)
[ "$manifest_records" -eq "$regular_files" ] || {
  echo "BLOCKED: manifest records $manifest_records != regular files $regular_files"
  exit 25
}

[ ! -d "$INVENTORY_FINAL" ] || { echo 'BLOCKED: inventory handoff path is a directory'; exit 26; }
[ ! -d "$MANIFEST_FINAL" ] || { echo 'BLOCKED: manifest handoff path is a directory'; exit 27; }

# Atomic, exact-path publication on the same /tmp filesystem. If an old file or
# symlink exists at either handoff path, the directory entry itself is replaced;
# no target outside these exact paths is followed or removed.
mv -fT -- "$INVENTORY_TMP" "$INVENTORY_FINAL"
mv -fT -- "$MANIFEST_TMP" "$MANIFEST_FINAL"
chmod 600 -- "$INVENTORY_FINAL" "$MANIFEST_FINAL"

inventory_sha256=$(sha256sum "$INVENTORY_FINAL" | awk '{print $1}')
manifest_sha256=$(sha256sum "$MANIFEST_FINAL" | awk '{print $1}')

printf 'regular_files=%s\n' "$regular_files"
printf 'directories=%s\n' "$directories"
printf 'symlinks=%s\n' "$symlinks"
printf 'special_members=%s\n' "$special_members"
printf 'hardlink_members_expected=%s\n' "$hardlink_members_expected"
printf 'regular_file_bytes=%s\n' "$regular_file_bytes"
printf 'tree_apparent_bytes=%s\n' "$tree_apparent_bytes"
printf 'manifest_records=%s\n' "$manifest_records"
printf 'inventory_path=%s\n' "$INVENTORY_FINAL"
printf 'inventory_sha256=%s\n' "$inventory_sha256"
printf 'manifest_path=%s\n' "$MANIFEST_FINAL"
printf 'manifest_sha256=%s\n' "$manifest_sha256"
printf '%s\n' 'SOURCE_INVENTORY=PASS'

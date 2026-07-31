#!/usr/bin/env bash
set -euo pipefail

# Work Order 001A — Approval Gate E v1
# Transfers exactly four verified Gate D artifacts from foundation-vm to one
# fresh laptop staging directory. This script does not extract archives, delete
# or overwrite files, upload to cloud storage, modify VM source data, restart
# services, merge, deploy, install packages, or continue to Gate F.

PROJECT=dominion-ascendant
ZONE=us-central1-a
VM=foundation-vm
VM_USER=malachisingleton8
REMOTE="${VM_USER}@${VM}"

GATE_D_READY=/tmp/dominion-releases-gate-d.ready
REMOTE_ARCHIVE=/tmp/dominion-releases-20260730.tar.gz
REMOTE_ARCHIVE_SHA=/tmp/dominion-releases-20260730.tar.gz.sha256
REMOTE_MANIFEST=/tmp/dominion-releases-source-manifest.sha256
REMOTE_INVENTORY=/tmp/dominion-releases-source-inventory.txt

ROOT='C:/Users/Dell/Dominion-Archive/foundation-vm/2026-07-30'

umask 077
LOCAL_EVIDENCE=$(mktemp -d "${TMPDIR:-/tmp}/dominion-releases-gate-e.XXXXXX") || {
  echo 'BLOCKED: unable to create private local Gate E evidence directory'
  exit 130
}
READY_BEFORE="$LOCAL_EVIDENCE/gate-d.ready.before"
READY_AFTER="$LOCAL_EVIDENCE/gate-d.ready.after"

cleanup() {
  rm -f -- "$READY_BEFORE" "$READY_AFTER"
  rmdir -- "$LOCAL_EVIDENCE" 2>/dev/null || true
}
trap cleanup EXIT

printf '%s\n' '=== WORK ORDER 001A EXACT LAPTOP TRANSFER V1 ==='
printf 'local_evidence_dir=%s\n' "$LOCAL_EVIDENCE"

for required_command in awk cmp cygpath find gcloud mktemp powershell.exe sha256sum stat tr wc; do
  command -v "$required_command" >/dev/null 2>&1 || {
    echo "BLOCKED: required local command unavailable: $required_command"
    exit 131
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

capture_remote_ready() {
  output=$1
  gcloud compute ssh "$REMOTE" \
    --zone="$ZONE" \
    --project="$PROJECT" \
    --quiet \
    --command="bash -s" >"$output" <<'REMOTE_CHECK'
set -euo pipefail
READY=/tmp/dominion-releases-gate-d.ready
ARCHIVE=/tmp/dominion-releases-20260730.tar.gz
ARCHIVE_SHA=/tmp/dominion-releases-20260730.tar.gz.sha256
MANIFEST=/tmp/dominion-releases-source-manifest.sha256
INVENTORY=/tmp/dominion-releases-source-inventory.txt

for artifact in "$READY" "$ARCHIVE" "$ARCHIVE_SHA" "$MANIFEST" "$INVENTORY"; do
  [ -f "$artifact" ] && [ ! -L "$artifact" ] || {
    echo "BLOCKED: required transfer artifact missing or unsafe: $artifact" >&2
    exit 132
  }
done

value() {
  key=$1
  awk -F= -v wanted="$key" '
    $1 == wanted { count++; value = substr($0, index($0, "=") + 1) }
    END { if (count == 1) print value; else exit 1 }
  ' "$READY"
}

[ "$(value status)" = READY ] || { echo 'BLOCKED: Gate D is not READY' >&2; exit 133; }
[ "$(value archive_path)" = "$ARCHIVE" ] || { echo 'BLOCKED: Gate D archive path mismatch' >&2; exit 134; }
[ "$(value archive_checksum_path)" = "$ARCHIVE_SHA" ] || { echo 'BLOCKED: Gate D archive checksum path mismatch' >&2; exit 135; }
[ "$(value source_manifest_path)" = "$MANIFEST" ] || { echo 'BLOCKED: Gate D manifest path mismatch' >&2; exit 136; }
[ "$(value source_inventory_path)" = "$INVENTORY" ] || { echo 'BLOCKED: Gate D inventory path mismatch' >&2; exit 137; }

archive_sha=$(sha256sum "$ARCHIVE" | awk '{print $1}')
manifest_sha=$(sha256sum "$MANIFEST" | awk '{print $1}')
inventory_sha=$(sha256sum "$INVENTORY" | awk '{print $1}')
archive_bytes=$(stat --format='%s' "$ARCHIVE")
manifest_records=$(tr -cd '\0' < "$MANIFEST" | wc -c)

[ "$archive_sha" = "$(value archive_sha256)" ] || { echo 'BLOCKED: remote archive digest mismatch' >&2; exit 138; }
[ "$manifest_sha" = "$(value source_manifest_sha256)" ] || { echo 'BLOCKED: remote manifest digest mismatch' >&2; exit 139; }
[ "$inventory_sha" = "$(value source_inventory_sha256)" ] || { echo 'BLOCKED: remote inventory digest mismatch' >&2; exit 140; }
[ "$archive_bytes" = "$(value archive_bytes)" ] || { echo 'BLOCKED: remote archive byte count mismatch' >&2; exit 141; }
[ "$manifest_records" = "$(value manifest_records)" ] || { echo 'BLOCKED: remote manifest record count mismatch' >&2; exit 142; }

(
  cd "$(dirname "$ARCHIVE")"
  sha256sum -c --status "$(basename "$ARCHIVE_SHA")"
) || { echo 'BLOCKED: remote archive checksum file failed verification' >&2; exit 143; }

cat "$READY"
REMOTE_CHECK
}

capture_remote_ready "$READY_BEFORE"

status=$(ready_value status "$READY_BEFORE")
generation=$(ready_value generation "$READY_BEFORE")
archive_sha=$(ready_value archive_sha256 "$READY_BEFORE")
archive_bytes=$(ready_value archive_bytes "$READY_BEFORE")
manifest_sha=$(ready_value source_manifest_sha256 "$READY_BEFORE")
inventory_sha=$(ready_value source_inventory_sha256 "$READY_BEFORE")
manifest_records_expected=$(ready_value manifest_records "$READY_BEFORE")

[ "$status" = READY ] || { echo 'BLOCKED: captured Gate D marker is not READY'; exit 144; }
case "$generation" in
  dominion-releases-gate-d.[A-Za-z0-9][A-Za-z0-9][A-Za-z0-9][A-Za-z0-9][A-Za-z0-9][A-Za-z0-9]) ;;
  *) echo 'BLOCKED: unexpected Gate D generation format'; exit 145 ;;
esac
case "$archive_sha$manifest_sha$inventory_sha" in
  *[!0-9a-f]*) echo 'BLOCKED: READY marker contains a non-hex digest'; exit 146 ;;
esac
[ "${#archive_sha}" -eq 64 ] && [ "${#manifest_sha}" -eq 64 ] && [ "${#inventory_sha}" -eq 64 ] || {
  echo 'BLOCKED: READY marker digest length mismatch'
  exit 147
}
case "$archive_bytes:$manifest_records_expected" in
  *[!0-9:]*) echo 'BLOCKED: READY marker contains a non-numeric count'; exit 148 ;;
esac

STAGING="$ROOT/releases-transfer-$generation"
export DOMINION_ROOT="$ROOT"
export DOMINION_STAGING="$STAGING"

powershell.exe -NoProfile -NonInteractive -Command '
$ErrorActionPreference = "Stop"
$root = [System.IO.Path]::GetFullPath($env:DOMINION_ROOT)
$staging = [System.IO.Path]::GetFullPath($env:DOMINION_STAGING)

function Assert-NoReparsePoint([string]$Path) {
  $full = [System.IO.Path]::GetFullPath($Path)
  $drive = [System.IO.Path]::GetPathRoot($full)
  $relative = $full.Substring($drive.Length)
  $current = $drive
  foreach ($part in ($relative -split "[\\/]" | Where-Object { $_ -ne "" })) {
    $current = Join-Path $current $part
    if (Test-Path -LiteralPath $current) {
      $item = Get-Item -LiteralPath $current -Force
      if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "BLOCKED: reparse-point path component: $current"
      }
    } else {
      break
    }
  }
}

Assert-NoReparsePoint $root
if (-not (Test-Path -LiteralPath $root)) {
  New-Item -ItemType Directory -Path $root | Out-Null
}
Assert-NoReparsePoint $root

$parent = [System.IO.Path]::GetDirectoryName($staging).TrimEnd("\\")
$expectedParent = $root.TrimEnd("\\")
if (-not $parent.Equals($expectedParent, [System.StringComparison]::OrdinalIgnoreCase)) {
  throw "BLOCKED: staging parent mismatch"
}
if (Test-Path -LiteralPath $staging) {
  throw "BLOCKED: fresh staging directory already exists: $staging"
}
New-Item -ItemType Directory -Path $staging | Out-Null
Assert-NoReparsePoint $staging
' || {
  echo 'BLOCKED: laptop staging path safety check failed'
  exit 149
}

LOCAL_ARCHIVE="$STAGING/$(basename "$REMOTE_ARCHIVE")"
LOCAL_ARCHIVE_SHA="$STAGING/$(basename "$REMOTE_ARCHIVE_SHA")"
LOCAL_MANIFEST="$STAGING/$(basename "$REMOTE_MANIFEST")"
LOCAL_INVENTORY="$STAGING/$(basename "$REMOTE_INVENTORY")"

for destination in "$LOCAL_ARCHIVE" "$LOCAL_ARCHIVE_SHA" "$LOCAL_MANIFEST" "$LOCAL_INVENTORY"; do
  [ ! -e "$destination" ] && [ ! -L "$destination" ] || {
    echo "BLOCKED: transfer destination already exists: $destination"
    exit 150
  }
done

gcloud compute scp "$REMOTE:$REMOTE_ARCHIVE" "$LOCAL_ARCHIVE" --zone="$ZONE" --project="$PROJECT" --quiet
gcloud compute scp "$REMOTE:$REMOTE_ARCHIVE_SHA" "$LOCAL_ARCHIVE_SHA" --zone="$ZONE" --project="$PROJECT" --quiet
gcloud compute scp "$REMOTE:$REMOTE_MANIFEST" "$LOCAL_MANIFEST" --zone="$ZONE" --project="$PROJECT" --quiet
gcloud compute scp "$REMOTE:$REMOTE_INVENTORY" "$LOCAL_INVENTORY" --zone="$ZONE" --project="$PROJECT" --quiet

for local_file in "$LOCAL_ARCHIVE" "$LOCAL_ARCHIVE_SHA" "$LOCAL_MANIFEST" "$LOCAL_INVENTORY"; do
  [ -f "$local_file" ] && [ ! -L "$local_file" ] || {
    echo "BLOCKED: transferred file missing or unsafe: $local_file"
    exit 151
  }
done

local_file_count=$(find "$STAGING" -mindepth 1 -maxdepth 1 -type f -printf '.' | wc -c)
local_dir_count=$(find "$STAGING" -mindepth 1 -maxdepth 1 -type d -printf '.' | wc -c)
local_link_count=$(find "$STAGING" -mindepth 1 -maxdepth 1 -type l -printf '.' | wc -c)
[ "$local_file_count" -eq 4 ] || { echo "BLOCKED: staging file count is $local_file_count, expected 4"; exit 152; }
[ "$local_dir_count" -eq 0 ] || { echo 'BLOCKED: unexpected subdirectory in staging'; exit 153; }
[ "$local_link_count" -eq 0 ] || { echo 'BLOCKED: unexpected symlink in staging'; exit 154; }

local_archive_sha=$(sha256sum "$LOCAL_ARCHIVE" | awk '{print $1}')
local_manifest_sha=$(sha256sum "$LOCAL_MANIFEST" | awk '{print $1}')
local_inventory_sha=$(sha256sum "$LOCAL_INVENTORY" | awk '{print $1}')
local_archive_bytes=$(stat --format='%s' "$LOCAL_ARCHIVE")
local_manifest_records=$(tr -cd '\0' < "$LOCAL_MANIFEST" | wc -c)

[ "$local_archive_sha" = "$archive_sha" ] || { echo 'BLOCKED: laptop archive digest mismatch'; exit 155; }
[ "$local_manifest_sha" = "$manifest_sha" ] || { echo 'BLOCKED: laptop manifest digest mismatch'; exit 156; }
[ "$local_inventory_sha" = "$inventory_sha" ] || { echo 'BLOCKED: laptop inventory digest mismatch'; exit 157; }
[ "$local_archive_bytes" = "$archive_bytes" ] || { echo 'BLOCKED: laptop archive byte count mismatch'; exit 158; }
[ "$local_manifest_records" = "$manifest_records_expected" ] || { echo 'BLOCKED: laptop manifest record count mismatch'; exit 159; }

(
  cd "$STAGING"
  sha256sum -c --status "$(basename "$LOCAL_ARCHIVE_SHA")"
) || { echo 'BLOCKED: laptop archive checksum file failed verification'; exit 160; }

capture_remote_ready "$READY_AFTER"
cmp -s "$READY_BEFORE" "$READY_AFTER" || {
  echo 'BLOCKED: Gate D READY marker changed during transfer'
  exit 161
}

printf 'gate_d_generation=%s\n' "$generation"
printf 'staging_path=%s\n' "$STAGING"
printf 'transferred_files=%s\n' "$local_file_count"
printf 'archive_sha256=%s\n' "$local_archive_sha"
printf 'archive_bytes=%s\n' "$local_archive_bytes"
printf 'source_manifest_sha256=%s\n' "$local_manifest_sha"
printf 'source_manifest_records=%s\n' "$local_manifest_records"
printf 'source_inventory_sha256=%s\n' "$local_inventory_sha"
printf '%s\n' 'EXACT_TRANSFER=PASS'

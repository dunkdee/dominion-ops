#!/usr/bin/env bash
set -euo pipefail

# Work Order 001A — Approval Gate F v1
# Re-validates and extracts the exact Gate E laptop archive into one fresh,
# reparse-safe Windows directory, verifies every extracted regular file against
# the NUL-delimited Gate B manifest, reconciles counts and bytes, writes one
# local READY marker, and stops.
#
# This script does not contact the VM, transfer files, upload to cloud storage,
# overwrite or delete archive/source data, use recursive deletion, install
# packages, merge, deploy, restart services, expose secrets, or continue to
# Gate G.

ROOT='C:/Users/Dell/Dominion-Archive/foundation-vm/2026-07-30'
GATE_D_GENERATION='dominion-releases-gate-d.mRjArx'
STAGING="$ROOT/releases-transfer-$GATE_D_GENERATION"

ARCHIVE="$STAGING/dominion-releases-20260730.tar.gz"
ARCHIVE_SHA_FILE="$STAGING/dominion-releases-20260730.tar.gz.sha256"
MANIFEST="$STAGING/dominion-releases-source-manifest.sha256"
INVENTORY="$STAGING/dominion-releases-source-inventory.txt"

EXPECTED_ARCHIVE_SHA='2e005d40c9aaabffa3c132dc012d7f67f514dd85ecf416375355733e9a9c8c42'
EXPECTED_ARCHIVE_BYTES='7878803'
EXPECTED_MANIFEST_SHA='fd28783668988cf27345f6c7cd6b6119a16d218db1c80fda1d26061827830859'
EXPECTED_INVENTORY_SHA='5a960ea80d0a3018030d55f213793e3b11eac4fa9c2c1e41cef62a4455439f79'
EXPECTED_REGULAR_FILES='4695'
EXPECTED_DIRECTORIES='1150'
EXPECTED_MANIFEST_RECORDS='4695'
MIN_FREE_BYTES='134217728'

umask 077
EVIDENCE_DIR=$(mktemp -d "${TMPDIR:-/tmp}/dominion-releases-gate-f.XXXXXX") || {
  echo 'BLOCKED: unable to create private local Gate F evidence directory'
  exit 170
}
VALIDATION_REPORT="$EVIDENCE_DIR/archive-validation.txt"
EXTRACTION_REPORT="$EVIDENCE_DIR/extraction-report.txt"

cleanup() {
  rm -f -- "$VALIDATION_REPORT" "$EXTRACTION_REPORT"
  rmdir -- "$EVIDENCE_DIR" 2>/dev/null || true
}
trap cleanup EXIT

printf '%s\n' '=== WORK ORDER 001A LAPTOP EXTRACTION AND MANIFEST VERIFICATION V1 ==='
printf 'local_evidence_dir=%s\n' "$EVIDENCE_DIR"
printf 'staging_path=%s\n' "$STAGING"

for required_command in awk basename chmod find mktemp powershell.exe sha256sum stat tr wc; do
  command -v "$required_command" >/dev/null 2>&1 || {
    echo "BLOCKED: required local command unavailable: $required_command"
    exit 171
  }
done

run_python() {
  if command -v python3 >/dev/null 2>&1; then
    python3 "$@"
  elif command -v python >/dev/null 2>&1; then
    python "$@"
  elif command -v py >/dev/null 2>&1; then
    py -3 "$@"
  else
    echo 'BLOCKED: Python 3 is unavailable'
    return 127
  fi
}

run_python -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 8) else 1)' || {
  echo 'BLOCKED: Python 3.8 or newer is required'
  exit 172
}

export DOMINION_ROOT="$ROOT"
export DOMINION_STAGING="$STAGING"
export DOMINION_MIN_FREE_BYTES="$MIN_FREE_BYTES"

powershell.exe -NoProfile -NonInteractive -Command '
$ErrorActionPreference = "Stop"
$root = [System.IO.Path]::GetFullPath($env:DOMINION_ROOT)
$staging = [System.IO.Path]::GetFullPath($env:DOMINION_STAGING)
$minimum = [Int64]$env:DOMINION_MIN_FREE_BYTES

function Assert-NoReparsePoint([string]$Path) {
  $full = [System.IO.Path]::GetFullPath($Path)
  $drive = [System.IO.Path]::GetPathRoot($full)
  $relative = $full.Substring($drive.Length)
  $current = $drive
  foreach ($part in ($relative -split "[\\/]" | Where-Object { $_ -ne "" })) {
    $current = Join-Path $current $part
    if (-not (Test-Path -LiteralPath $current)) {
      throw "BLOCKED: required path component does not exist: $current"
    }
    $item = Get-Item -LiteralPath $current -Force
    if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
      throw "BLOCKED: reparse-point path component: $current"
    }
  }
}

if (-not (Test-Path -LiteralPath $root -PathType Container)) {
  throw "BLOCKED: exact archive root is missing or not a directory"
}
Assert-NoReparsePoint $root

if (-not (Test-Path -LiteralPath $staging -PathType Container)) {
  throw "BLOCKED: exact Gate E staging directory is missing"
}
Assert-NoReparsePoint $staging

$stagingParent = [System.IO.Path]::GetDirectoryName($staging).TrimEnd("\\")
$expectedParent = $root.TrimEnd("\\")
if (-not $stagingParent.Equals($expectedParent, [System.StringComparison]::OrdinalIgnoreCase)) {
  throw "BLOCKED: staging parent mismatch"
}

$driveRoot = [System.IO.Path]::GetPathRoot($root)
$drive = [System.IO.DriveInfo]::new($driveRoot)
if ($drive.AvailableFreeSpace -lt $minimum) {
  throw "BLOCKED: insufficient laptop free space for guarded extraction"
}
Write-Output ("laptop_free_bytes=" + $drive.AvailableFreeSpace)
' || {
  echo 'BLOCKED: laptop root/staging safety or capacity check failed'
  exit 173
}

for artifact in "$ARCHIVE" "$ARCHIVE_SHA_FILE" "$MANIFEST" "$INVENTORY"; do
  [ -f "$artifact" ] && [ ! -L "$artifact" ] || {
    echo "BLOCKED: required Gate E artifact missing or unsafe: $artifact"
    exit 174
  }
done

staging_file_count=$(find "$STAGING" -mindepth 1 -maxdepth 1 -type f -printf '.' | wc -c)
staging_dir_count=$(find "$STAGING" -mindepth 1 -maxdepth 1 -type d -printf '.' | wc -c)
staging_link_count=$(find "$STAGING" -mindepth 1 -maxdepth 1 -type l -printf '.' | wc -c)
[ "$staging_file_count" -eq 4 ] || { echo "BLOCKED: Gate E staging file count is $staging_file_count, expected 4"; exit 175; }
[ "$staging_dir_count" -eq 0 ] || { echo 'BLOCKED: unexpected subdirectory in Gate E staging'; exit 176; }
[ "$staging_link_count" -eq 0 ] || { echo 'BLOCKED: unexpected symlink in Gate E staging'; exit 177; }

archive_sha=$(sha256sum "$ARCHIVE" | awk '{print $1}')
archive_bytes=$(stat --format='%s' "$ARCHIVE")
manifest_sha=$(sha256sum "$MANIFEST" | awk '{print $1}')
inventory_sha=$(sha256sum "$INVENTORY" | awk '{print $1}')
manifest_records=$(tr -cd '\0' < "$MANIFEST" | wc -c)

[ "$archive_sha" = "$EXPECTED_ARCHIVE_SHA" ] || { echo 'BLOCKED: archive digest no longer matches Gate E'; exit 178; }
[ "$archive_bytes" = "$EXPECTED_ARCHIVE_BYTES" ] || { echo 'BLOCKED: archive byte count no longer matches Gate E'; exit 179; }
[ "$manifest_sha" = "$EXPECTED_MANIFEST_SHA" ] || { echo 'BLOCKED: source manifest digest no longer matches Gate E'; exit 180; }
[ "$inventory_sha" = "$EXPECTED_INVENTORY_SHA" ] || { echo 'BLOCKED: source inventory digest no longer matches Gate E'; exit 181; }
[ "$manifest_records" = "$EXPECTED_MANIFEST_RECORDS" ] || { echo 'BLOCKED: source manifest record count mismatch'; exit 182; }

checksum_lines=$(awk 'END {print NR+0}' "$ARCHIVE_SHA_FILE")
[ "$checksum_lines" -eq 1 ] || { echo 'BLOCKED: archive checksum file must contain exactly one record'; exit 183; }
checksum_digest=$(awk 'NF == 2 {print $1}' "$ARCHIVE_SHA_FILE")
checksum_name=$(awk 'NF == 2 {print $2}' "$ARCHIVE_SHA_FILE")
[ "$checksum_digest" = "$EXPECTED_ARCHIVE_SHA" ] || { echo 'BLOCKED: archive checksum record digest mismatch'; exit 184; }
[ "$checksum_name" = "$(basename "$ARCHIVE")" ] || { echo 'BLOCKED: archive checksum record filename mismatch'; exit 185; }
(
  cd "$STAGING"
  sha256sum -c --status "$(basename "$ARCHIVE_SHA_FILE")"
) || { echo 'BLOCKED: archive checksum file failed verification'; exit 186; }

inventory_value() {
  key=$1
  awk -F= -v wanted="$key" '
    $1 == wanted { count++; value = substr($0, index($0, "=") + 1) }
    END { if (count == 1) print value; else exit 1 }
  ' "$INVENTORY"
}

source_regular=$(inventory_value regular_files) || { echo 'BLOCKED: inventory regular_files field invalid'; exit 187; }
source_directories=$(inventory_value directories) || { echo 'BLOCKED: inventory directories field invalid'; exit 188; }
source_symlinks=$(inventory_value symlinks) || { echo 'BLOCKED: inventory symlinks field invalid'; exit 189; }
source_special=$(inventory_value special_members) || { echo 'BLOCKED: inventory special_members field invalid'; exit 190; }
source_hardlinks=$(inventory_value hardlink_members_expected) || { echo 'BLOCKED: inventory hardlink_members_expected field invalid'; exit 191; }
source_regular_bytes=$(inventory_value regular_file_bytes) || { echo 'BLOCKED: inventory regular_file_bytes field invalid'; exit 192; }

for numeric_value in "$source_regular" "$source_directories" "$source_symlinks" "$source_special" "$source_hardlinks" "$source_regular_bytes"; do
  case "$numeric_value" in
    ''|*[!0-9]*) echo 'BLOCKED: source inventory contains a non-numeric count'; exit 193 ;;
  esac
done

[ "$source_regular" = "$EXPECTED_REGULAR_FILES" ] || { echo 'BLOCKED: source inventory regular-file count mismatch'; exit 194; }
[ "$source_directories" = "$EXPECTED_DIRECTORIES" ] || { echo 'BLOCKED: source inventory directory count mismatch'; exit 195; }
[ "$source_symlinks" -eq 0 ] || { echo 'BLOCKED: source inventory contains symlinks'; exit 196; }
[ "$source_special" -eq 0 ] || { echo 'BLOCKED: source inventory contains special members'; exit 197; }
[ "$source_hardlinks" -eq 0 ] || { echo 'BLOCKED: source inventory contains hard links'; exit 198; }

run_python - "$ARCHIVE" "$VALIDATION_REPORT" "$source_regular" "$source_directories" "$source_regular_bytes" <<'PY'
import ntpath
import os
import posixpath
import re
import sys
import tarfile
from pathlib import PurePosixPath

archive, report, expected_regular, expected_directories, expected_bytes = sys.argv[1:]
expected_regular = int(expected_regular)
expected_directories = int(expected_directories)
expected_bytes = int(expected_bytes)

windows_drive = re.compile(r"^[A-Za-z]:")
invalid_windows_chars = set('<>:"|?*')
reserved = {"con", "prn", "aux", "nul"}
reserved.update(f"com{i}" for i in range(1, 10))
reserved.update(f"lpt{i}" for i in range(1, 10))

regular = 0
directories = 0
regular_bytes = 0
seen_posix = set()
seen_windows = set()
unsafe = []
root_directory_seen = False


def validate_name(raw: str, is_dir: bool) -> str:
    global root_directory_seen
    if not raw or "\x00" in raw or "\\" in raw:
        raise ValueError(f"unsafe archive name: {raw!r}")
    if raw.startswith("/") or raw.startswith("//") or raw.startswith("\\\\"):
        raise ValueError(f"absolute archive name: {raw!r}")
    if windows_drive.match(raw) or ntpath.isabs(raw):
        raise ValueError(f"drive-qualified archive name: {raw!r}")
    if any(ord(ch) < 32 or ch in invalid_windows_chars for ch in raw):
        raise ValueError(f"Windows-unsafe character in archive name: {raw!r}")

    trimmed = raw[:-1] if is_dir and raw.endswith("/") else raw
    if not trimmed or "//" in trimmed:
        raise ValueError(f"non-canonical archive name: {raw!r}")

    parts = trimmed.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError(f"traversal or empty component in archive name: {raw!r}")
    if parts[0] != "releases":
        raise ValueError(f"unexpected archive root: {raw!r}")

    for part in parts:
        if part.endswith(" ") or part.endswith("."):
            raise ValueError(f"Windows-normalized archive component: {raw!r}")
        stem = part.split(".", 1)[0].casefold()
        if stem in reserved:
            raise ValueError(f"Windows reserved archive component: {raw!r}")

    normalized = posixpath.normpath(trimmed)
    if not (normalized == "releases" or normalized.startswith("releases/")):
        raise ValueError(f"archive path escapes releases root: {raw!r}")
    if normalized in seen_posix:
        raise ValueError(f"duplicate normalized archive path: {raw!r}")

    windows_key = "/".join(part.casefold() for part in parts)
    if windows_key in seen_windows:
        raise ValueError(f"case-insensitive Windows path collision: {raw!r}")

    seen_posix.add(normalized)
    seen_windows.add(windows_key)
    if normalized == "releases" and is_dir:
        root_directory_seen = True
    return normalized


with tarfile.open(archive, mode="r:gz") as tf:
    members = tf.getmembers()
    for member in members:
        if member.isdir():
            directories += 1
            validate_name(member.name, True)
        elif member.isfile():
            regular += 1
            regular_bytes += member.size
            validate_name(member.name, False)
        elif member.issym() or member.islnk():
            raise ValueError(f"archive link member rejected: {member.name!r}")
        else:
            raise ValueError(f"unsupported archive member rejected: {member.name!r}")

if not root_directory_seen:
    raise ValueError("archive is missing the releases root directory")
if regular != expected_regular:
    raise ValueError(f"regular member count {regular} != {expected_regular}")
if directories != expected_directories:
    raise ValueError(f"directory member count {directories} != {expected_directories}")
if regular_bytes != expected_bytes:
    raise ValueError(f"regular member bytes {regular_bytes} != {expected_bytes}")

with open(report, "w", encoding="utf-8", newline="\n") as fh:
    fh.write(f"regular_members={regular}\n")
    fh.write(f"directory_members={directories}\n")
    fh.write(f"regular_member_bytes={regular_bytes}\n")
    fh.write("symlink_members=0\n")
    fh.write("hardlink_members=0\n")
    fh.write("other_members=0\n")
    fh.write("unsafe_names=0\n")
    fh.write("windows_collisions=0\n")
    fh.write("archive_validation=PASS\n")
PY

export DOMINION_EXTRACTION_PREFIX="releases-verified-$GATE_D_GENERATION-"
EXTRACTED=$(powershell.exe -NoProfile -NonInteractive -Command '
$ErrorActionPreference = "Stop"
$root = [System.IO.Path]::GetFullPath($env:DOMINION_ROOT)
$prefix = $env:DOMINION_EXTRACTION_PREFIX

function Assert-NoReparsePoint([string]$Path) {
  $full = [System.IO.Path]::GetFullPath($Path)
  $drive = [System.IO.Path]::GetPathRoot($full)
  $relative = $full.Substring($drive.Length)
  $current = $drive
  foreach ($part in ($relative -split "[\\/]" | Where-Object { $_ -ne "" })) {
    $current = Join-Path $current $part
    if (-not (Test-Path -LiteralPath $current)) {
      throw "BLOCKED: required path component does not exist: $current"
    }
    $item = Get-Item -LiteralPath $current -Force
    if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
      throw "BLOCKED: reparse-point path component: $current"
    }
  }
}

Assert-NoReparsePoint $root
$leaf = $prefix + [Guid]::NewGuid().ToString("N").Substring(0, 8)
$target = Join-Path $root $leaf
if (Test-Path -LiteralPath $target) {
  throw "BLOCKED: fresh extraction target unexpectedly exists"
}
New-Item -ItemType Directory -Path $target | Out-Null
Assert-NoReparsePoint $target
(($target -replace "\\", "/").TrimEnd("/"))
' | tr -d '\r') || {
  echo 'BLOCKED: unable to create a fresh reparse-safe extraction directory'
  exit 199
}

case "$EXTRACTED" in
  "$ROOT"/releases-verified-"$GATE_D_GENERATION"-[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]) ;;
  *) echo 'BLOCKED: extraction path format mismatch'; exit 200 ;;
esac

export DOMINION_EXTRACTED="$EXTRACTED"

run_python - "$ARCHIVE" "$EXTRACTED" "$EXTRACTION_REPORT" "$source_regular" "$source_directories" "$source_regular_bytes" <<'PY'
import ntpath
import os
import posixpath
import re
import shutil
import sys
import tarfile

archive, destination, report, expected_regular, expected_directories, expected_bytes = sys.argv[1:]
expected_regular = int(expected_regular)
expected_directories = int(expected_directories)
expected_bytes = int(expected_bytes)

destination = os.path.abspath(destination)
windows_drive = re.compile(r"^[A-Za-z]:")
invalid_windows_chars = set('<>:"|?*')
reserved = {"con", "prn", "aux", "nul"}
reserved.update(f"com{i}" for i in range(1, 10))
reserved.update(f"lpt{i}" for i in range(1, 10))
seen_windows = set()
seen_posix = set()
regular = 0
directories = 0
written_bytes = 0


def safe_parts(raw: str, is_dir: bool):
    if not raw or "\x00" in raw or "\\" in raw:
        raise ValueError(f"unsafe archive name: {raw!r}")
    if raw.startswith("/") or raw.startswith("//") or raw.startswith("\\\\"):
        raise ValueError(f"absolute archive name: {raw!r}")
    if windows_drive.match(raw) or ntpath.isabs(raw):
        raise ValueError(f"drive-qualified archive name: {raw!r}")
    if any(ord(ch) < 32 or ch in invalid_windows_chars for ch in raw):
        raise ValueError(f"Windows-unsafe character in archive name: {raw!r}")

    trimmed = raw[:-1] if is_dir and raw.endswith("/") else raw
    if not trimmed or "//" in trimmed:
        raise ValueError(f"non-canonical archive name: {raw!r}")
    parts = trimmed.split("/")
    if any(part in ("", ".", "..") for part in parts) or parts[0] != "releases":
        raise ValueError(f"unsafe archive path: {raw!r}")

    for part in parts:
        if part.endswith(" ") or part.endswith("."):
            raise ValueError(f"Windows-normalized archive component: {raw!r}")
        if part.split(".", 1)[0].casefold() in reserved:
            raise ValueError(f"Windows reserved archive component: {raw!r}")

    normalized = posixpath.normpath(trimmed)
    if not (normalized == "releases" or normalized.startswith("releases/")):
        raise ValueError(f"archive path escapes releases root: {raw!r}")
    if normalized in seen_posix:
        raise ValueError(f"duplicate normalized archive path: {raw!r}")

    windows_key = "/".join(part.casefold() for part in parts)
    if windows_key in seen_windows:
        raise ValueError(f"case-insensitive Windows path collision: {raw!r}")
    seen_posix.add(normalized)
    seen_windows.add(windows_key)

    target = os.path.abspath(os.path.join(destination, *parts))
    if os.path.commonpath([destination, target]) != destination:
        raise ValueError(f"resolved extraction path escapes destination: {raw!r}")
    if len(target) > 240:
        raise ValueError(f"Windows path exceeds guarded length: {raw!r}")
    return target


with tarfile.open(archive, mode="r:gz") as tf:
    members = tf.getmembers()

    # Validate the entire archive before writing the first member.
    prepared = []
    for member in members:
        if member.isdir():
            target = safe_parts(member.name, True)
            directories += 1
        elif member.isfile():
            target = safe_parts(member.name, False)
            regular += 1
            written_bytes += member.size
        elif member.issym() or member.islnk():
            raise ValueError(f"archive link member rejected: {member.name!r}")
        else:
            raise ValueError(f"unsupported archive member rejected: {member.name!r}")
        prepared.append((member, target))

    if regular != expected_regular or directories != expected_directories or written_bytes != expected_bytes:
        raise ValueError("archive accounting changed between validation and extraction")

    # Create directories first, then regular files with exclusive creation.
    for member, target in prepared:
        if member.isdir():
            os.makedirs(target, exist_ok=False)

    actual_written = 0
    for member, target in prepared:
        if not member.isfile():
            continue
        parent = os.path.dirname(target)
        if not os.path.isdir(parent):
            raise ValueError(f"missing validated parent directory: {member.name!r}")
        source = tf.extractfile(member)
        if source is None:
            raise ValueError(f"unable to read archive member: {member.name!r}")
        with source, open(target, "xb") as output:
            copied = 0
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
                copied += len(chunk)
            output.flush()
        if copied != member.size:
            raise ValueError(f"extracted size mismatch: {member.name!r}")
        actual_written += copied

if actual_written != expected_bytes:
    raise ValueError(f"total extracted bytes {actual_written} != {expected_bytes}")

with open(report, "w", encoding="utf-8", newline="\n") as fh:
    fh.write(f"regular_files={regular}\n")
    fh.write(f"directories={directories}\n")
    fh.write(f"regular_file_bytes={actual_written}\n")
    fh.write("extraction=PASS\n")
PY

powershell.exe -NoProfile -NonInteractive -Command '
$ErrorActionPreference = "Stop"
$extracted = [System.IO.Path]::GetFullPath($env:DOMINION_EXTRACTED)
if (-not (Test-Path -LiteralPath $extracted -PathType Container)) {
  throw "BLOCKED: extraction directory is missing"
}
$item = Get-Item -LiteralPath $extracted -Force
if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
  throw "BLOCKED: extraction directory became a reparse point"
}
$reparse = Get-ChildItem -LiteralPath $extracted -Force -Recurse | Where-Object {
  ($_.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0
} | Select-Object -First 1
if ($null -ne $reparse) {
  throw "BLOCKED: extracted tree contains a reparse point: $($reparse.FullName)"
}
' || {
  echo 'BLOCKED: extracted tree reparse-point validation failed'
  exit 201
}

EXTRACTED_RELEASES="$EXTRACTED/releases"
[ -d "$EXTRACTED_RELEASES" ] && [ ! -L "$EXTRACTED_RELEASES" ] || {
  echo 'BLOCKED: extracted releases root is missing or unsafe'
  exit 202
}

extracted_regular=$(find "$EXTRACTED_RELEASES" -type f -printf '.' | wc -c)
extracted_directories=$(find "$EXTRACTED_RELEASES" -type d -printf '.' | wc -c)
extracted_symlinks=$(find "$EXTRACTED_RELEASES" -type l -printf '.' | wc -c)
extracted_other=$(find "$EXTRACTED_RELEASES" ! -type f ! -type d ! -type l -printf '.' | wc -c)

[ "$extracted_regular" = "$source_regular" ] || { echo 'BLOCKED: extracted regular-file count mismatch'; exit 203; }
[ "$extracted_directories" = "$source_directories" ] || { echo 'BLOCKED: extracted directory count mismatch'; exit 204; }
[ "$extracted_symlinks" -eq 0 ] || { echo 'BLOCKED: extracted tree contains symlinks'; exit 205; }
[ "$extracted_other" -eq 0 ] || { echo 'BLOCKED: extracted tree contains unsupported members'; exit 206; }

(
  cd "$EXTRACTED_RELEASES"
  sha256sum -c --zero --status "$MANIFEST"
) || {
  echo 'BLOCKED: extracted files do not match the NUL-delimited source manifest'
  exit 207
}

# Re-bind the extraction result to the exact Gate E artifacts after all reads.
[ "$(sha256sum "$ARCHIVE" | awk '{print $1}')" = "$EXPECTED_ARCHIVE_SHA" ] || { echo 'BLOCKED: archive changed during Gate F'; exit 208; }
[ "$(stat --format='%s' "$ARCHIVE")" = "$EXPECTED_ARCHIVE_BYTES" ] || { echo 'BLOCKED: archive byte count changed during Gate F'; exit 209; }
[ "$(sha256sum "$MANIFEST" | awk '{print $1}')" = "$EXPECTED_MANIFEST_SHA" ] || { echo 'BLOCKED: source manifest changed during Gate F'; exit 210; }
[ "$(sha256sum "$INVENTORY" | awk '{print $1}')" = "$EXPECTED_INVENTORY_SHA" ] || { echo 'BLOCKED: source inventory changed during Gate F'; exit 211; }

GATE_F_READY="$EXTRACTED/dominion-releases-gate-f.ready"
[ ! -e "$GATE_F_READY" ] && [ ! -L "$GATE_F_READY" ] || {
  echo 'BLOCKED: Gate F READY marker already exists'
  exit 212
}

cat > "$GATE_F_READY" <<EOF
status=READY
generation=dominion-releases-gate-f.$(basename "$EXTRACTED" | awk -F- '{print $NF}')
gate_d_generation=$GATE_D_GENERATION
staging_path=$STAGING
extraction_path=$EXTRACTED
archive_sha256=$EXPECTED_ARCHIVE_SHA
archive_bytes=$EXPECTED_ARCHIVE_BYTES
source_manifest_sha256=$EXPECTED_MANIFEST_SHA
source_manifest_records=$EXPECTED_MANIFEST_RECORDS
source_inventory_sha256=$EXPECTED_INVENTORY_SHA
regular_files=$extracted_regular
directories=$extracted_directories
symlinks=$extracted_symlinks
other_members=$extracted_other
manifest_verification=PASS
EOF
chmod 600 -- "$GATE_F_READY"

printf 'gate_d_generation=%s\n' "$GATE_D_GENERATION"
printf 'staging_path=%s\n' "$STAGING"
printf 'extraction_path=%s\n' "$EXTRACTED"
printf 'gate_f_ready_path=%s\n' "$GATE_F_READY"
printf 'archive_sha256=%s\n' "$EXPECTED_ARCHIVE_SHA"
printf 'archive_bytes=%s\n' "$EXPECTED_ARCHIVE_BYTES"
printf 'source_manifest_sha256=%s\n' "$EXPECTED_MANIFEST_SHA"
printf 'source_manifest_records=%s\n' "$EXPECTED_MANIFEST_RECORDS"
printf 'source_inventory_sha256=%s\n' "$EXPECTED_INVENTORY_SHA"
printf 'regular_files=%s\n' "$extracted_regular"
printf 'directories=%s\n' "$extracted_directories"
printf 'symlinks=%s\n' "$extracted_symlinks"
printf 'other_members=%s\n' "$extracted_other"
printf '%s\n' 'MANIFEST_VERIFICATION=PASS'
printf '%s\n' 'GATE_F=PASS'

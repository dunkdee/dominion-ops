# Work Order 001A — Releases Archive Repair and GCP Storage Inventory

**Parent control packet:** #92  
**Work order:** #93  
**Mode:** inspect, archive, copy, verify, report, stop  
**Production impact:** none authorized  
**Deletion authority:** not granted  
**Cloud creation or policy-change authority:** not granted

## 1. Objective

Create one complete, byte-verifiable archive of:

```text
/home/malachisingleton8/releases
```

Transfer it to a separate laptop staging location, verify every regular file against a deterministic NUL-delimited SHA-256 manifest, inventory existing Google Cloud storage resources read-only, and present exact cloud archive destinations for separate Founder approval.

The first recursive SCP remains classified as **FAILED / INCOMPLETE** because the observed source and laptop regular-file counts were 5,761 and 4,695 respectively.

## 2. Non-negotiable safety boundaries

This runbook does not authorize:

- deleting or modifying `/home/malachisingleton8/releases`;
- deleting the incomplete laptop SCP directory;
- deleting the snapshot or strategizer archive;
- creating or modifying a Cloud Storage bucket, disk, snapshot, machine image, backup plan, lifecycle rule, retention rule, versioning setting, or storage class;
- uploading to Google Cloud before an exact destination receives separate Founder approval;
- deleting or transferring the home-level `.git` directory;
- modifying Ollama models, CUDA libraries, Docker images, Docker volumes, databases, swap, Caddy, DNS, firewall, secrets, or production services;
- installing or registering a CI runner;
- merging a pull request, deploying, restarting services, moving money, or enabling live trading.

Stop immediately if a command expands beyond the exact paths in this runbook.

## 3. Exact environment

```text
GCP project: dominion-ascendant
VM: foundation-vm
Zone: us-central1-a
VM user: malachisingleton8
Source: /home/malachisingleton8/releases
Laptop root: C:/Users/Dell/Dominion-Archive/foundation-vm/2026-07-30
Verified staging: C:/Users/Dell/Dominion-Archive/foundation-vm/2026-07-30/releases-verified-staging
Incomplete first copy: C:/Users/Dell/Dominion-Archive/foundation-vm/2026-07-30/releases/releases
```

VM temporary outputs:

```text
/tmp/dominion-releases-20260730.tar.gz
/tmp/dominion-releases-20260730.tar.gz.sha256
/tmp/dominion-releases-source-manifest.sha256
/tmp/dominion-releases-source-manifest.after.sha256
/tmp/dominion-releases-source-inventory.txt
/tmp/dominion-releases-container-baseline.txt
/tmp/dominion-releases-container-after.txt
/tmp/dominion-releases-container-status-before.txt
/tmp/dominion-releases-container-status-after.txt
/tmp/dominion-releases-archive-inventory.txt
/tmp/dominion-releases-lsof.out
/tmp/dominion-releases-lsof.err
```

## 4. Approval Gate A — read-only preflight

Only the commands in this section may run before the source is classified safe for archiving.

The capacity budget is intentionally conservative:

```text
required bytes = (source apparent bytes × 3) + 256 MiB
```

Both `/` and `/tmp` must independently report at least that many available bytes. This covers one source-sized archive, temporary manifests and inventories, retry overhead, and a fixed safety reserve.

From the laptop:

```bash
gcloud compute ssh malachisingleton8@foundation-vm \
  --zone=us-central1-a \
  --project=dominion-ascendant \
  --command='bash -s' <<'REMOTE'
set -euo pipefail

SOURCE=/home/malachisingleton8/releases
EXPECTED=/home/malachisingleton8/releases
LSOF_OUT=/tmp/dominion-releases-lsof.out
LSOF_ERR=/tmp/dominion-releases-lsof.err
BASELINE=/tmp/dominion-releases-container-baseline.txt
STATUS_BEFORE=/tmp/dominion-releases-container-status-before.txt

printf '%s\n' '=== WORK ORDER 001A PREFLIGHT ==='
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
lsof +D "$SOURCE" >"$LSOF_OUT" 2>"$LSOF_ERR"
lsof_rc=$?
set -e

if [ "$lsof_rc" -eq 1 ] && [ ! -s "$LSOF_OUT" ] && [ ! -s "$LSOF_ERR" ]; then
  : # documented safe no-match result
elif [ "$lsof_rc" -ne 0 ]; then
  echo "BLOCKED: lsof inspection failed rc=$lsof_rc"
  [ ! -s "$LSOF_ERR" ] || sed -n '1,20p' "$LSOF_ERR"
  exit 16
fi

write_handles=$(awk 'NR>1 && $4 ~ /w/ {count++} END {print count+0}' "$LSOF_OUT")
printf 'open_write_handles=%s\n' "$write_handles"
[ "$write_handles" -eq 0 ] || {
  echo 'BLOCKED: source has open write handles'
  exit 17
}

printf '%s\n' 'PREFLIGHT=PASS'
REMOTE
```

Required result:

- resolved source equals the exact expected path;
- source is a real directory and not a symlink;
- both capacity comparisons pass;
- `open_write_handles=0`;
- stable production container identity baseline is preserved;
- volatile status is reported separately and is not used for the identity diff.

## 5. Approval Gate B — one-filesystem source inventory and manifest

Run only after Gate A passes.

The source inventory, `find`, `du`, manifest, and later archive all use the same one-filesystem boundary. Mounted filesystems beneath `releases/` are not descended into or archived.

```bash
gcloud compute ssh malachisingleton8@foundation-vm \
  --zone=us-central1-a \
  --project=dominion-ascendant \
  --command='bash -s' <<'REMOTE'
set -euo pipefail

SOURCE=/home/malachisingleton8/releases
INVENTORY=/tmp/dominion-releases-source-inventory.txt
MANIFEST=/tmp/dominion-releases-source-manifest.sha256

resolved=$(readlink -f -- "$SOURCE")
[ "$resolved" = "$SOURCE" ] || { echo 'BLOCKED: source path mismatch'; exit 20; }
[ -d "$SOURCE" ] && [ ! -L "$SOURCE" ] || { echo 'BLOCKED: invalid source type'; exit 21; }

regular_files=$(find "$SOURCE" -xdev -type f -printf '.' | wc -c)
directories=$(find "$SOURCE" -xdev -type d -printf '.' | wc -c)
symlinks=$(find "$SOURCE" -xdev -type l -printf '.' | wc -c)
special_members=$(find "$SOURCE" -xdev ! -type f ! -type d ! -type l -printf '.' | wc -c)
regular_file_bytes=$(find "$SOURCE" -xdev -type f -printf '%s\n' | awk '{sum += $1} END {printf "%.0f\n", sum+0}')
tree_apparent_bytes=$(du -x --apparent-size --bytes --summarize "$SOURCE" | awk '{print $1}')
hardlink_members_expected=$(find "$SOURCE" -xdev -type f -printf '%D:%i\n' \
  | LC_ALL=C sort \
  | uniq -c \
  | awk '$1 > 1 {sum += $1 - 1} END {print sum+0}')
oldest=$(find "$SOURCE" -xdev -printf '%T@\n' | LC_ALL=C sort -n | head -1)
newest=$(find "$SOURCE" -xdev -printf '%T@\n' | LC_ALL=C sort -n | tail -1)

symlink_target_sha256=$(find "$SOURCE" -xdev -type l -printf '%P\0%l\0' \
  | python3 -c 'import hashlib,sys; p=sys.stdin.buffer.read().split(b"\0"); pairs=list(zip(p[0::2],p[1::2])); h=hashlib.sha256(); [h.update(a+b"\0"+b+b"\0") for a,b in sorted(pairs) if a]; print(h.hexdigest())')

[ "$special_members" -eq 0 ] || {
  echo "BLOCKED: unsupported source special members=$special_members"
  exit 22
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
} > "$INVENTORY"

(
  cd "$SOURCE"
  LC_ALL=C find . -xdev -type f -print0 \
    | LC_ALL=C sort -z \
    | xargs -0 -r sha256sum -z --
) > "$MANIFEST"

manifest_records=$(tr -cd '\0' < "$MANIFEST" | wc -c)
[ "$manifest_records" -eq "$regular_files" ] || {
  echo "BLOCKED: manifest records $manifest_records != regular files $regular_files"
  exit 23
}

sha256sum "$INVENTORY" "$MANIFEST"
cat "$INVENTORY"
echo 'SOURCE_INVENTORY=PASS'
REMOTE
```

Expected historical source count is 5,761 regular files, but the current count is authoritative. Any unexplained change must be reported and investigated before continuing.

## 6. Approval Gate C — create and validate the archive

```bash
gcloud compute ssh malachisingleton8@foundation-vm \
  --zone=us-central1-a \
  --project=dominion-ascendant \
  --command='bash -s' <<'REMOTE'
set -euo pipefail

SOURCE=/home/malachisingleton8/releases
ARCHIVE=/tmp/dominion-releases-20260730.tar.gz
ARCHIVE_SHA=/tmp/dominion-releases-20260730.tar.gz.sha256
SOURCE_INV=/tmp/dominion-releases-source-inventory.txt
SOURCE_MANIFEST=/tmp/dominion-releases-source-manifest.sha256
ARCHIVE_INV=/tmp/dominion-releases-archive-inventory.txt

[ -f "$SOURCE_INV" ] || { echo 'BLOCKED: source inventory missing'; exit 30; }
[ -f "$SOURCE_MANIFEST" ] || { echo 'BLOCKED: source manifest missing'; exit 31; }

rm -f -- "$ARCHIVE" "$ARCHIVE_SHA" "$ARCHIVE_INV"
tar --one-file-system -C /home/malachisingleton8 -czf "$ARCHIVE" -- releases
tar -tzf "$ARCHIVE" >/dev/null
(
  cd "$(dirname "$ARCHIVE")"
  sha256sum "$(basename "$ARCHIVE")"
) > "$ARCHIVE_SHA"
archive_bytes=$(stat --format='%s' "$ARCHIVE")

python3 - "$ARCHIVE" "$ARCHIVE_INV" <<'PY'
import posixpath
import sys
import tarfile
from pathlib import PurePosixPath

archive, output = sys.argv[1:]
regular = directories = symlinks = hardlinks = others = 0
unsafe_names = []
unsafe_links = []
duplicate_names = []
root_ok = True

with tarfile.open(archive, mode="r:gz") as tf:
    members = tf.getmembers()
    normalized_names = set()

    for member in members:
        raw_name = member.name
        parts = PurePosixPath(raw_name).parts
        normalized = posixpath.normpath(raw_name)

        if raw_name.startswith("/") or ".." in parts:
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
            if posixpath.isabs(link):
                unsafe_links.append(f"{member.name} -> {link}")
            else:
                target = posixpath.normpath(posixpath.join(posixpath.dirname(name), link))
                if not (target == "releases" or target.startswith("releases/")):
                    unsafe_links.append(f"{member.name} -> {link}")
        elif member.islnk():
            hardlinks += 1
            link = member.linkname
            if posixpath.isabs(link):
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
    raise SystemExit(40)
PY

source_regular=$(awk -F= '$1=="regular_files"{print $2}' "$SOURCE_INV")
source_dirs=$(awk -F= '$1=="directories"{print $2}' "$SOURCE_INV")
source_links=$(awk -F= '$1=="symlinks"{print $2}' "$SOURCE_INV")
source_hardlinks=$(awk -F= '$1=="hardlink_members_expected"{print $2}' "$SOURCE_INV")
archive_regular=$(awk -F= '$1=="regular_members"{print $2}' "$ARCHIVE_INV")
archive_dirs=$(awk -F= '$1=="directory_members"{print $2}' "$ARCHIVE_INV")
archive_links=$(awk -F= '$1=="symlink_members"{print $2}' "$ARCHIVE_INV")
archive_hardlinks=$(awk -F= '$1=="hardlink_members"{print $2}' "$ARCHIVE_INV")
archive_others=$(awk -F= '$1=="other_members"{print $2}' "$ARCHIVE_INV")
unsafe_names=$(awk -F= '$1=="unsafe_names"{print $2}' "$ARCHIVE_INV")
unsafe_links=$(awk -F= '$1=="unsafe_links"{print $2}' "$ARCHIVE_INV")
duplicate_names=$(awk -F= '$1=="duplicate_names"{print $2}' "$ARCHIVE_INV")
root_ok=$(awk -F= '$1=="root_ok"{print $2}' "$ARCHIVE_INV")

[ "$source_regular" -eq $((archive_regular + archive_hardlinks)) ] || {
  echo 'BLOCKED: regular-path accounting mismatch'
  exit 32
}
[ "$source_dirs" -eq "$archive_dirs" ] || { echo 'BLOCKED: directory count mismatch'; exit 33; }
[ "$source_links" -eq "$archive_links" ] || { echo 'BLOCKED: symlink count mismatch'; exit 34; }
[ "$source_hardlinks" -eq "$archive_hardlinks" ] || { echo 'BLOCKED: hard-link count mismatch'; exit 35; }
[ "$archive_others" -eq 0 ] || { echo 'BLOCKED: unsupported archive member'; exit 36; }
[ "$unsafe_names" -eq 0 ] || { echo 'BLOCKED: unsafe archive path'; exit 37; }
[ "$unsafe_links" -eq 0 ] || { echo 'BLOCKED: unsafe archive link target'; exit 38; }
[ "$duplicate_names" -eq 0 ] || { echo 'BLOCKED: duplicate normalized archive path'; exit 39; }
[ "$root_ok" = true ] || { echo 'BLOCKED: unexpected archive root'; exit 41; }

printf 'archive_bytes=%s\n' "$archive_bytes"
cat "$ARCHIVE_SHA"
cat "$ARCHIVE_INV"
echo 'ARCHIVE_CREATION=PASS'
REMOTE
```

The `rm -f` command removes only the three exact `/tmp` archive-output candidates before recreating them. It does not touch source data.

## 7. Approval Gate D — complete source stability verification

Before transfer, recompute the full NUL-delimited regular-file manifest using the exact Gate B procedure and compare it byte-for-byte with the recorded source manifest. Aggregate counts are also rechecked, including hard links, special members, regular-file bytes, and symlink targets.

```bash
gcloud compute ssh malachisingleton8@foundation-vm \
  --zone=us-central1-a \
  --project=dominion-ascendant \
  --command='bash -s' <<'REMOTE'
set -euo pipefail

SOURCE=/home/malachisingleton8/releases
INV=/tmp/dominion-releases-source-inventory.txt
MANIFEST=/tmp/dominion-releases-source-manifest.sha256
AFTER=/tmp/dominion-releases-source-manifest.after.sha256

[ -f "$INV" ] || { echo 'BLOCKED: source inventory missing'; exit 50; }
[ -f "$MANIFEST" ] || { echo 'BLOCKED: source manifest missing'; exit 51; }

(
  cd "$SOURCE"
  LC_ALL=C find . -xdev -type f -print0 \
    | LC_ALL=C sort -z \
    | xargs -0 -r sha256sum -z --
) > "$AFTER"

cmp -s "$MANIFEST" "$AFTER" || {
  echo 'BLOCKED: complete source manifest changed after archive creation'
  exit 52
}

before_files=$(awk -F= '$1=="regular_files"{print $2}' "$INV")
before_dirs=$(awk -F= '$1=="directories"{print $2}' "$INV")
before_links=$(awk -F= '$1=="symlinks"{print $2}' "$INV")
before_special=$(awk -F= '$1=="special_members"{print $2}' "$INV")
before_hardlinks=$(awk -F= '$1=="hardlink_members_expected"{print $2}' "$INV")
before_regular_bytes=$(awk -F= '$1=="regular_file_bytes"{print $2}' "$INV")
before_link_digest=$(awk -F= '$1=="symlink_target_sha256"{print $2}' "$INV")

after_files=$(find "$SOURCE" -xdev -type f -printf '.' | wc -c)
after_dirs=$(find "$SOURCE" -xdev -type d -printf '.' | wc -c)
after_links=$(find "$SOURCE" -xdev -type l -printf '.' | wc -c)
after_special=$(find "$SOURCE" -xdev ! -type f ! -type d ! -type l -printf '.' | wc -c)
after_hardlinks=$(find "$SOURCE" -xdev -type f -printf '%D:%i\n' \
  | LC_ALL=C sort | uniq -c \
  | awk '$1 > 1 {sum += $1 - 1} END {print sum+0}')
after_regular_bytes=$(find "$SOURCE" -xdev -type f -printf '%s\n' \
  | awk '{sum += $1} END {printf "%.0f\n", sum+0}')
after_link_digest=$(find "$SOURCE" -xdev -type l -printf '%P\0%l\0' \
  | python3 -c 'import hashlib,sys; p=sys.stdin.buffer.read().split(b"\0"); pairs=list(zip(p[0::2],p[1::2])); h=hashlib.sha256(); [h.update(a+b"\0"+b+b"\0") for a,b in sorted(pairs) if a]; print(h.hexdigest())')

[ "$before_files" -eq "$after_files" ] || { echo 'BLOCKED: source regular-file count changed'; exit 53; }
[ "$before_dirs" -eq "$after_dirs" ] || { echo 'BLOCKED: source directory count changed'; exit 54; }
[ "$before_links" -eq "$after_links" ] || { echo 'BLOCKED: source symlink count changed'; exit 55; }
[ "$before_special" -eq "$after_special" ] || { echo 'BLOCKED: source special-member count changed'; exit 56; }
[ "$before_hardlinks" -eq "$after_hardlinks" ] || { echo 'BLOCKED: source hard-link topology changed'; exit 57; }
[ "$before_regular_bytes" -eq "$after_regular_bytes" ] || { echo 'BLOCKED: source regular-file bytes changed'; exit 58; }
[ "$before_link_digest" = "$after_link_digest" ] || { echo 'BLOCKED: source symlink targets changed'; exit 59; }

rm -f -- "$AFTER"
echo 'SOURCE_STABILITY=PASS'
REMOTE
```

## 8. Approval Gate E — transfer exact files to the laptop

Create the destination root only:

```bash
mkdir -p "C:/Users/Dell/Dominion-Archive/foundation-vm/2026-07-30"
```

Transfer exactly four files, one command per file:

```bash
gcloud compute scp \
  malachisingleton8@foundation-vm:/tmp/dominion-releases-20260730.tar.gz \
  "C:/Users/Dell/Dominion-Archive/foundation-vm/2026-07-30/dominion-releases-20260730.tar.gz" \
  --zone=us-central1-a \
  --project=dominion-ascendant

gcloud compute scp \
  malachisingleton8@foundation-vm:/tmp/dominion-releases-20260730.tar.gz.sha256 \
  "C:/Users/Dell/Dominion-Archive/foundation-vm/2026-07-30/dominion-releases-20260730.tar.gz.sha256" \
  --zone=us-central1-a \
  --project=dominion-ascendant

gcloud compute scp \
  malachisingleton8@foundation-vm:/tmp/dominion-releases-source-manifest.sha256 \
  "C:/Users/Dell/Dominion-Archive/foundation-vm/2026-07-30/dominion-releases-source-manifest.sha256" \
  --zone=us-central1-a \
  --project=dominion-ascendant

gcloud compute scp \
  malachisingleton8@foundation-vm:/tmp/dominion-releases-source-inventory.txt \
  "C:/Users/Dell/Dominion-Archive/foundation-vm/2026-07-30/dominion-releases-source-inventory.txt" \
  --zone=us-central1-a \
  --project=dominion-ascendant
```

No wildcard and no recursive transfer are permitted.

## 9. Approval Gate F — laptop integrity and full manifest verification

Run in Git Bash on the laptop:

```bash
set -euo pipefail

ROOT="C:/Users/Dell/Dominion-Archive/foundation-vm/2026-07-30"
ARCHIVE="$ROOT/dominion-releases-20260730.tar.gz"
ARCHIVE_SHA="$ROOT/dominion-releases-20260730.tar.gz.sha256"
MANIFEST="$ROOT/dominion-releases-source-manifest.sha256"
INVENTORY="$ROOT/dominion-releases-source-inventory.txt"
STAGING="$ROOT/releases-verified-staging"

[ -f "$ARCHIVE" ] || { echo 'BLOCKED: archive missing'; exit 60; }
[ -f "$ARCHIVE_SHA" ] || { echo 'BLOCKED: archive checksum missing'; exit 61; }
[ -f "$MANIFEST" ] || { echo 'BLOCKED: source manifest missing'; exit 62; }
[ -f "$INVENTORY" ] || { echo 'BLOCKED: source inventory missing'; exit 63; }

(
  cd "$ROOT"
  sha256sum -c --status "$(basename "$ARCHIVE_SHA")"
) || { echo 'BLOCKED: laptop archive checksum mismatch'; exit 64; }

tar -tzf "$ARCHIVE" >/dev/null || { echo 'BLOCKED: archive listing failed'; exit 65; }

case "$STAGING" in
  "$ROOT/releases-verified-staging") ;;
  *) echo 'BLOCKED: staging path guard failed'; exit 66 ;;
esac
[ -n "$STAGING" ] && [ "$STAGING" != "$ROOT" ] || { echo 'BLOCKED: unsafe staging path'; exit 67; }

rm -rf -- "$STAGING"
mkdir -p -- "$STAGING"
tar --no-same-owner --no-same-permissions -xzf "$ARCHIVE" -C "$STAGING"

EXTRACTED="$STAGING/releases"
[ -d "$EXTRACTED" ] || { echo 'BLOCKED: expected releases root missing'; exit 68; }

source_regular=$(awk -F= '$1=="regular_files"{print $2}' "$INVENTORY")
source_dirs=$(awk -F= '$1=="directories"{print $2}' "$INVENTORY")
source_links=$(awk -F= '$1=="symlinks"{print $2}' "$INVENTORY")
source_special=$(awk -F= '$1=="special_members"{print $2}' "$INVENTORY")
source_hardlinks=$(awk -F= '$1=="hardlink_members_expected"{print $2}' "$INVENTORY")
source_regular_bytes=$(awk -F= '$1=="regular_file_bytes"{print $2}' "$INVENTORY")
source_link_digest=$(awk -F= '$1=="symlink_target_sha256"{print $2}' "$INVENTORY")

extracted_regular=$(find "$EXTRACTED" -xdev -type f -printf '.' | wc -c)
extracted_dirs=$(find "$EXTRACTED" -xdev -type d -printf '.' | wc -c)
extracted_links=$(find "$EXTRACTED" -xdev -type l -printf '.' | wc -c)
extracted_special=$(find "$EXTRACTED" -xdev ! -type f ! -type d ! -type l -printf '.' | wc -c)
extracted_hardlinks=$(find "$EXTRACTED" -xdev -type f -printf '%D:%i\n' \
  | LC_ALL=C sort | uniq -c \
  | awk '$1 > 1 {sum += $1 - 1} END {print sum+0}')
extracted_regular_bytes=$(find "$EXTRACTED" -xdev -type f -printf '%s\n' \
  | awk '{sum += $1} END {printf "%.0f\n", sum+0}')
extracted_link_digest=$(find "$EXTRACTED" -xdev -type l -printf '%P\0%l\0' \
  | python3 -c 'import hashlib,sys; p=sys.stdin.buffer.read().split(b"\0"); pairs=list(zip(p[0::2],p[1::2])); h=hashlib.sha256(); [h.update(a+b"\0"+b+b"\0") for a,b in sorted(pairs) if a]; print(h.hexdigest())')

[ "$source_regular" -eq "$extracted_regular" ] || { echo 'BLOCKED: regular-file count mismatch'; exit 69; }
[ "$source_dirs" -eq "$extracted_dirs" ] || { echo 'BLOCKED: directory count mismatch'; exit 70; }
[ "$source_links" -eq "$extracted_links" ] || { echo 'BLOCKED: symlink count mismatch'; exit 71; }
[ "$source_special" -eq "$extracted_special" ] || { echo 'BLOCKED: special-member count mismatch'; exit 72; }
[ "$source_hardlinks" -eq "$extracted_hardlinks" ] || { echo 'BLOCKED: hard-link topology mismatch'; exit 73; }
[ "$source_regular_bytes" -eq "$extracted_regular_bytes" ] || { echo 'BLOCKED: regular-file byte mismatch'; exit 74; }
[ "$source_link_digest" = "$extracted_link_digest" ] || { echo 'BLOCKED: symlink target mismatch'; exit 75; }

(
  cd "$EXTRACTED"
  sha256sum -c --status "$MANIFEST"
) || { echo 'BLOCKED: extracted file manifest mismatch'; exit 76; }

echo 'LAPTOP_RELEASES_VERIFICATION=PASS'
```

The exact-path `rm -rf -- "$STAGING"` is permitted only after both staging-path guards pass. Never replace `$STAGING` with a parent directory, wildcard, empty variable, or the incomplete first-copy directory.

## 10. Approval Gate G — production identity comparison

After verification, compare only stable production container identity fields to the baseline. Report volatile status separately.

```bash
gcloud compute ssh malachisingleton8@foundation-vm \
  --zone=us-central1-a \
  --project=dominion-ascendant \
  --command='bash -s' <<'REMOTE'
set -euo pipefail

AFTER=/tmp/dominion-releases-container-after.txt
STATUS_AFTER=/tmp/dominion-releases-container-status-after.txt
BASELINE=/tmp/dominion-releases-container-baseline.txt

[ -f "$BASELINE" ] || { echo 'BLOCKED: production identity baseline missing'; exit 80; }

docker ps -q --no-trunc \
  | LC_ALL=C sort \
  | xargs -r docker inspect --format '{{.Id}}|{{.Name}}|{{.Image}}' \
  | LC_ALL=C sort \
  | tee "$AFTER"

docker ps --no-trunc --format '{{.ID}}|{{.Names}}|{{.Image}}|{{.Status}}' \
  | LC_ALL=C sort \
  | tee "$STATUS_AFTER"

diff -u "$BASELINE" "$AFTER" || {
  echo 'BLOCKED: production container identity changed'
  exit 81
}

echo 'PRODUCTION_IDENTITY=PASS'
REMOTE
```

Any stable identity difference blocks completion and requires incident review.

## 11. Read-only GCP inventory

No resource mutation is authorized. Run from the laptop:

```bash
set -euo pipefail
PROJECT=dominion-ascendant

echo '=== BUCKETS ==='
gcloud storage buckets list --project="$PROJECT"

echo '=== DISKS ==='
gcloud compute disks list --project="$PROJECT"

echo '=== SNAPSHOTS ==='
gcloud compute snapshots list --project="$PROJECT"

echo '=== MACHINE IMAGES ==='
gcloud compute machine-images list --project="$PROJECT"

echo '=== BACKUP VAULTS ==='
gcloud backup-dr backup-vaults list --project="$PROJECT" --location=- 2>&1 || echo 'BACKUP_VAULT_INVENTORY=PARTIAL_OR_UNSUPPORTED'

echo '=== BACKUP PLANS ==='
gcloud backup-dr backup-plans list --project="$PROJECT" --location=- 2>&1 || echo 'BACKUP_PLAN_INVENTORY=PARTIAL_OR_UNSUPPORTED'
```

For each existing bucket, run exact-name inspection only:

```bash
gcloud storage buckets describe gs://EXACT_BUCKET_NAME --project=dominion-ascendant

gcloud storage du --summarize --readable-sizes gs://EXACT_BUCKET_NAME

gcloud storage ls --long --recursive gs://EXACT_BUCKET_NAME 2>/dev/null | head -200
```

The object listing is metadata-only and capped. Do not print object contents. If recursive metadata listing is unsupported or permission-blocked, report `UNKNOWN` or `PARTIAL`; do not broaden access.

Record for each bucket:

- exact bucket URL;
- location and alignment with `us-central1`;
- storage class;
- versioning state;
- lifecycle rules;
- retention and lock state;
- soft-delete policy;
- total usage and object count where available;
- Dominion-related prefixes by metadata only;
- expected incremental storage, retrieval, and transfer implications.

Record for each disk, snapshot, machine image, backup vault, and backup plan:

- exact name;
- location;
- size or stored bytes;
- state;
- source resource;
- attachment or use relationship;
- labels;
- likely purpose;
- whether it can be used without creating a new paid resource.

## 12. Required report

Attach a report to #93 and #92 containing:

```text
snapshot laptop copy: PASS / FAIL / UNKNOWN
strategizer source archive laptop copy: PASS / FAIL / UNKNOWN
first recursive releases SCP: FAIL — observed 1,066-file deficit
releases source preflight: PASS / FAIL / BLOCKED
releases source manifest: PASS / FAIL / BLOCKED
releases archive creation: PASS / FAIL / BLOCKED
releases archive path/link safety: PASS / FAIL / BLOCKED
releases laptop archive hash: PASS / FAIL / BLOCKED
releases extracted counts and topology: PASS / FAIL / BLOCKED
releases full file manifest: PASS / FAIL / BLOCKED
production container identity: PASS / FAIL / BLOCKED
GCP inventory: PASS / PARTIAL / BLOCKED
cloud destination proposal: PRESENT / PENDING
VM deletion authority: NOT GRANTED
```

The report must include exact hashes, counts, byte sizes, artifact paths, timestamps, command exit states, and all unknowns. It must not include secrets or file contents.

## 13. Definition of done

Work Order 001A is complete only when:

1. the releases archive exists as one verified file on the laptop;
2. archive bytes and SHA-256 match the VM archive;
3. extracted regular-file, directory, symlink, hard-link, special-member, and regular-file-byte results match the source inventory;
4. every extracted regular file passes the NUL-delimited source SHA-256 manifest;
5. all archive paths and link targets remain inside the approved `releases/` root;
6. no unsupported special archive member exists;
7. production container identity remains unchanged;
8. existing GCP storage is inventoried read-only;
9. exact cloud object destinations are proposed with cost and retention boundaries;
10. the evidence is attached to #93 and summarized in #92;
11. no source deletion, cloud upload, resource creation, merge, deployment, restart, or live trading occurs.

**Final action:** report and stop for Founder review.

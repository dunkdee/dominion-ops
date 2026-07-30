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

Transfer it to a separate laptop staging location, verify every regular file against a source SHA-256 manifest, inventory existing Google Cloud storage resources read-only, and present exact cloud archive destinations for separate Founder approval.

The first recursive SCP is classified as **FAILED / INCOMPLETE** because the observed source and laptop regular-file counts were 5,761 and 4,695 respectively.

## 2. Non-negotiable safety boundaries

This runbook does not authorize:

- deleting or modifying `/home/malachisingleton8/releases`;
- deleting the incomplete laptop SCP directory;
- deleting the snapshot or strategizer archive;
- creating or modifying a Cloud Storage bucket, disk, snapshot, machine image, backup plan, lifecycle rule, retention rule, versioning setting, or storage class;
- uploading to Google Cloud before a destination receives separate Founder approval;
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
/tmp/dominion-releases-source-inventory.txt
/tmp/dominion-releases-container-baseline.txt
/tmp/dominion-releases-container-after.txt
/tmp/dominion-releases-archive-inventory.txt
```

## 4. Approval Gate A — read-only preflight

Only the commands in this section may run before the source is classified safe for archiving.

From the laptop:

```bash
gcloud compute ssh malachisingleton8@foundation-vm \
  --zone=us-central1-a \
  --project=dominion-ascendant \
  --command='bash -s' <<'REMOTE'
set -euo pipefail

SOURCE=/home/malachisingleton8/releases
EXPECTED=/home/malachisingleton8/releases

printf '%s\n' '=== WORK ORDER 001A PREFLIGHT ==='
resolved=$(readlink -f -- "$SOURCE")
printf 'resolved_source=%s\n' "$resolved"
[ "$resolved" = "$EXPECTED" ] || { echo 'BLOCKED: source path mismatch'; exit 10; }
[ -d "$SOURCE" ] || { echo 'BLOCKED: source is not a directory'; exit 11; }
[ ! -L "$SOURCE" ] || { echo 'BLOCKED: source is a symlink'; exit 12; }

df -B1 / /tmp

docker ps --no-trunc --format '{{.ID}}|{{.Names}}|{{.Image}}|{{.Status}}' \
  | LC_ALL=C sort \
  | tee /tmp/dominion-releases-container-baseline.txt

if command -v lsof >/dev/null 2>&1; then
  write_handles=$(lsof +D "$SOURCE" 2>/dev/null | awk 'NR>1 && $4 ~ /w/ {count++} END {print count+0}')
  printf 'open_write_handles=%s\n' "$write_handles"
  [ "$write_handles" -eq 0 ] || { echo 'BLOCKED: source has open write handles'; exit 13; }
else
  echo 'open_write_handles=UNKNOWN (lsof unavailable)'
  echo 'BLOCKED: install is not authorized; use the before/after stability comparison only after Founder review.'
  exit 14
fi

printf '%s\n' 'PREFLIGHT=PASS'
REMOTE
```

Required result:

- resolved source equals the exact expected path;
- source is a real directory and not a symlink;
- `open_write_handles=0`;
- sufficient `/tmp` and root capacity exists for a roughly 33 MB source plus archive and verification overhead;
- production container baseline is preserved.

Do not install `lsof` under this work order. If it is unavailable, stop and report `BLOCKED`.

## 5. Approval Gate B — source inventory and deterministic manifest

Run only after Gate A passes:

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
apparent_bytes=$(du --apparent-size --bytes --summarize "$SOURCE" | awk '{print $1}')
oldest=$(find "$SOURCE" -xdev -printf '%T@\n' | LC_ALL=C sort -n | head -1)
newest=$(find "$SOURCE" -xdev -printf '%T@\n' | LC_ALL=C sort -n | tail -1)

{
  echo 'source=/home/malachisingleton8/releases'
  echo "regular_files=$regular_files"
  echo "directories=$directories"
  echo "symlinks=$symlinks"
  echo "apparent_bytes=$apparent_bytes"
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
    | xargs -0 -r sha256sum --
) > "$MANIFEST"

manifest_lines=$(wc -l < "$MANIFEST")
[ "$manifest_lines" -eq "$regular_files" ] || {
  echo "BLOCKED: manifest lines $manifest_lines != regular files $regular_files"
  exit 22
}

sha256sum "$INVENTORY" "$MANIFEST"
cat "$INVENTORY"
echo 'SOURCE_INVENTORY=PASS'
REMOTE
```

Expected historical source count is 5,761 regular files, but the current count is authoritative. Any unexplained change must be reported and investigated before continuing.

## 6. Approval Gate C — create and inspect the archive

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
ARCHIVE_INV=/tmp/dominion-releases-archive-inventory.txt

[ -f "$SOURCE_INV" ] || { echo 'BLOCKED: source inventory missing'; exit 30; }
[ -f /tmp/dominion-releases-source-manifest.sha256 ] || { echo 'BLOCKED: source manifest missing'; exit 31; }

rm -f -- "$ARCHIVE" "$ARCHIVE_SHA" "$ARCHIVE_INV"
tar -C /home/malachisingleton8 -czf "$ARCHIVE" -- releases

tar -tzf "$ARCHIVE" >/dev/null
sha256sum "$ARCHIVE" | tee "$ARCHIVE_SHA"
archive_bytes=$(stat --format='%s' "$ARCHIVE")

python3 - "$ARCHIVE" "$ARCHIVE_INV" <<'PY'
import sys
import tarfile

archive, output = sys.argv[1:]
regular = directories = symlinks = others = 0
unsafe = []
root_ok = True
with tarfile.open(archive, mode='r:gz') as tf:
    for member in tf:
        name = member.name
        if name.startswith('/') or name == '..' or name.startswith('../') or '/..' in name.split('/'):
            unsafe.append(name)
        if not (name == 'releases' or name.startswith('releases/')):
            root_ok = False
        if member.isfile():
            regular += 1
        elif member.isdir():
            directories += 1
        elif member.issym() or member.islnk():
            symlinks += 1
        else:
            others += 1
with open(output, 'w', encoding='utf-8') as fh:
    fh.write(f'regular_files={regular}\n')
    fh.write(f'directories={directories}\n')
    fh.write(f'symlinks={symlinks}\n')
    fh.write(f'other_members={others}\n')
    fh.write(f'root_ok={str(root_ok).lower()}\n')
    fh.write(f'unsafe_paths={len(unsafe)}\n')
if unsafe or not root_ok:
    raise SystemExit(40)
PY

source_regular=$(awk -F= '$1=="regular_files"{print $2}' "$SOURCE_INV")
source_dirs=$(awk -F= '$1=="directories"{print $2}' "$SOURCE_INV")
source_links=$(awk -F= '$1=="symlinks"{print $2}' "$SOURCE_INV")
archive_regular=$(awk -F= '$1=="regular_files"{print $2}' "$ARCHIVE_INV")
archive_dirs=$(awk -F= '$1=="directories"{print $2}' "$ARCHIVE_INV")
archive_links=$(awk -F= '$1=="symlinks"{print $2}' "$ARCHIVE_INV")
unsafe=$(awk -F= '$1=="unsafe_paths"{print $2}' "$ARCHIVE_INV")
root_ok=$(awk -F= '$1=="root_ok"{print $2}' "$ARCHIVE_INV")

[ "$source_regular" -eq "$archive_regular" ] || { echo 'BLOCKED: regular-file count mismatch'; exit 32; }
[ "$source_dirs" -eq "$archive_dirs" ] || { echo 'BLOCKED: directory count mismatch'; exit 33; }
[ "$source_links" -eq "$archive_links" ] || { echo 'BLOCKED: symlink count mismatch'; exit 34; }
[ "$unsafe" -eq 0 ] || { echo 'BLOCKED: unsafe archive path'; exit 35; }
[ "$root_ok" = true ] || { echo 'BLOCKED: unexpected archive root'; exit 36; }

printf 'archive_bytes=%s\n' "$archive_bytes"
cat "$ARCHIVE_INV"
echo 'ARCHIVE_CREATION=PASS'
REMOTE
```

The `rm -f` command above removes only the four exact `/tmp` output candidates before recreating them. It does not touch source data.

## 7. Approval Gate D — source stability comparison

Before transfer, remeasure the source and require no change from the recorded inventory:

```bash
gcloud compute ssh malachisingleton8@foundation-vm \
  --zone=us-central1-a \
  --project=dominion-ascendant \
  --command='bash -s' <<'REMOTE'
set -euo pipefail

SOURCE=/home/malachisingleton8/releases
INV=/tmp/dominion-releases-source-inventory.txt

before_files=$(awk -F= '$1=="regular_files"{print $2}' "$INV")
before_dirs=$(awk -F= '$1=="directories"{print $2}' "$INV")
before_links=$(awk -F= '$1=="symlinks"{print $2}' "$INV")
before_bytes=$(awk -F= '$1=="apparent_bytes"{print $2}' "$INV")
before_newest=$(awk -F= '$1=="newest_mtime_epoch"{print $2}' "$INV")

after_files=$(find "$SOURCE" -xdev -type f -printf '.' | wc -c)
after_dirs=$(find "$SOURCE" -xdev -type d -printf '.' | wc -c)
after_links=$(find "$SOURCE" -xdev -type l -printf '.' | wc -c)
after_bytes=$(du --apparent-size --bytes --summarize "$SOURCE" | awk '{print $1}')
after_newest=$(find "$SOURCE" -xdev -printf '%T@\n' | LC_ALL=C sort -n | tail -1)

[ "$before_files" -eq "$after_files" ] || { echo 'BLOCKED: source regular-file count changed'; exit 50; }
[ "$before_dirs" -eq "$after_dirs" ] || { echo 'BLOCKED: source directory count changed'; exit 51; }
[ "$before_links" -eq "$after_links" ] || { echo 'BLOCKED: source symlink count changed'; exit 52; }
[ "$before_bytes" -eq "$after_bytes" ] || { echo 'BLOCKED: source apparent bytes changed'; exit 53; }
[ "$before_newest" = "$after_newest" ] || { echo 'BLOCKED: source newest mtime changed'; exit 54; }

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
  sha256sum -c "$(basename "$ARCHIVE_SHA")"
)

tar -tzf "$ARCHIVE" >/dev/null

rm -rf -- "$STAGING"
mkdir -p -- "$STAGING"
tar -xzf "$ARCHIVE" -C "$STAGING"

EXTRACTED="$STAGING/releases"
[ -d "$EXTRACTED" ] || { echo 'BLOCKED: expected releases root missing'; exit 64; }

source_regular=$(awk -F= '$1=="regular_files"{print $2}' "$INVENTORY")
source_dirs=$(awk -F= '$1=="directories"{print $2}' "$INVENTORY")
source_links=$(awk -F= '$1=="symlinks"{print $2}' "$INVENTORY")
source_bytes=$(awk -F= '$1=="apparent_bytes"{print $2}' "$INVENTORY")

extracted_regular=$(find "$EXTRACTED" -type f -printf '.' | wc -c)
extracted_dirs=$(find "$EXTRACTED" -type d -printf '.' | wc -c)
extracted_links=$(find "$EXTRACTED" -type l -printf '.' | wc -c)
extracted_bytes=$(du --apparent-size --bytes --summarize "$EXTRACTED" | awk '{print $1}')

[ "$source_regular" -eq "$extracted_regular" ] || { echo 'BLOCKED: regular-file count mismatch'; exit 65; }
[ "$source_dirs" -eq "$extracted_dirs" ] || { echo 'BLOCKED: directory count mismatch'; exit 66; }
[ "$source_links" -eq "$extracted_links" ] || { echo 'BLOCKED: symlink count mismatch'; exit 67; }
[ "$source_bytes" -eq "$extracted_bytes" ] || { echo 'BLOCKED: apparent-byte mismatch'; exit 68; }

(
  cd "$EXTRACTED"
  sha256sum -c "$MANIFEST"
)

echo 'LAPTOP_RELEASES_VERIFICATION=PASS'
```

The exact-path `rm -rf -- "$STAGING"` is permitted only for the dedicated verified staging path defined above. Never replace `$STAGING` with a parent directory, wildcard, empty variable, or the incomplete first-copy directory.

## 10. Approval Gate G — production identity comparison

After verification, compare production container identities to the baseline:

```bash
gcloud compute ssh malachisingleton8@foundation-vm \
  --zone=us-central1-a \
  --project=dominion-ascendant \
  --command='bash -s' <<'REMOTE'
set -euo pipefail

docker ps --no-trunc --format '{{.ID}}|{{.Names}}|{{.Image}}|{{.Status}}' \
  | LC_ALL=C sort \
  | tee /tmp/dominion-releases-container-after.txt

diff -u \
  /tmp/dominion-releases-container-baseline.txt \
  /tmp/dominion-releases-container-after.txt

echo 'PRODUCTION_IDENTITY=PASS'
REMOTE
```

Any unexpected difference blocks completion and requires incident review.

## 11. Read-only GCP inventory

No resource mutation is authorized. Run from the laptop:

```bash
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
gcloud backup-dr backup-vaults list --project="$PROJECT" --location=- 2>&1 || true

echo '=== BACKUP PLANS ==='
gcloud backup-dr backup-plans list --project="$PROJECT" --location=- 2>&1 || true
```

For each existing bucket, run exact-name inspection:

```bash
gcloud storage buckets describe gs://EXACT_BUCKET_NAME --project=dominion-ascendant

gcloud storage du --summarize --readable-sizes gs://EXACT_BUCKET_NAME

gcloud storage ls --long --recursive gs://EXACT_BUCKET_NAME/** 2>/dev/null | head -200
```

The object listing is metadata-only and capped. Do not print object contents. If shell wildcard behavior is uncertain, omit the recursive listing and report `UNKNOWN` rather than broadening access.

Record for each bucket:

- exact bucket URL;
- location and region alignment with `us-central1`;
- storage class;
- versioning state;
- lifecycle rules;
- retention and lock state;
- soft-delete policy;
- total usage and object count where available;
- Dominion-related prefixes by metadata only;
- expected incremental storage and retrieval implications.

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
releases tar archive creation: PASS / FAIL / BLOCKED
releases laptop archive hash: PASS / FAIL / BLOCKED
releases extracted counts: PASS / FAIL / BLOCKED
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
3. extracted regular-file, directory, symlink, and apparent-byte counts match the source inventory;
4. every extracted regular file passes the source SHA-256 manifest;
5. production container identity remains unchanged;
6. existing GCP storage is inventoried read-only;
7. exact cloud object destinations are proposed with cost and retention boundaries;
8. the evidence is attached to #93 and summarized in #92;
9. no source deletion, cloud upload, resource creation, merge, deployment, restart, or live trading occurs.

**Final action:** report and stop for Founder review.

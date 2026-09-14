#!/usr/bin/env bash
# Permanently expand the foundation-vm boot disk from ~50GB to 100GB.
#
# AUTHORIZED SCOPE: grow one persistent disk, grow the one root partition on
# it, and grow the filesystem on that partition. Nothing else.
#
# NEVER, in any mode: mkfs, any format, any shrink, any partition deletion,
# any volume/database/container/service change, any VM creation, any service
# migration, any change to the DeerFlow deployment workflow. The workflow
# gate greps this file for those before it is allowed to run.
#
# gcloud runs HERE, on the VM, under the instance's own attached service
# account -- the same pattern every other GCP operation in this repository
# uses. If that service account lacks a permission the step needs, the
# script stops and says so rather than working around it.
#
# Two modes:
#   inspect  (default, read-only) -- Phase 1 + Phase 4. Proves disk identity
#            and records the block layout. Creates nothing, changes nothing.
#   expand   -- Phases 2-8. Snapshot, resize, growpart, resize filesystem,
#            verify health against the recorded pre-resize baseline.
#
# Every phase gate fails CLOSED: a gate that cannot be proven stops the run
# before the next, more consequential, step.
set -uo pipefail

MODE="${1:-inspect}"

PROJECT="dominion-ascendant"
ZONE="us-central1-a"
INSTANCE="foundation-vm"
TARGET_SIZE_GB=100
MIN_EXPECTED_GB=40          # the disk we expect is ~50GB; refuse anything far off
MAX_EXPECTED_GB=60
REQUIRED_FREE_GB=20         # post-state must clear this comfortably

say()   { printf '%s\n' "$*"; }
head2() { printf '\n== %s ==\n' "$*"; }
die()   { say ""; say "RESULT=STOP reason=$*"; say "FOUNDATION_VM_DISK_EXPANSION_END"; exit 3; }

SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  sudo -n true 2>/dev/null && SUDO="sudo -n"
fi

say "FOUNDATION_VM_DISK_EXPANSION_BEGIN"
say "collected_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
say "hostname=$(hostname 2>/dev/null || echo UNKNOWN)"
say "mode=$MODE"

# ── the health baseline this operation must not regress ────────────────
# Recorded from the pre-resize cleanup run 34897600099. gatekeeper and
# revenue_runtime answered 404 BEFORE the resize; that is established
# behaviour and must not be reported as a new failure afterwards.
baseline_health() {
  cat <<'BASE'
  health ascendant_store -> 200
  health command_center -> 200
  health conductor -> 200
  health dominion_publisher -> 200
  health dominion_store -> 200
  health gatekeeper -> 404
  health n8n -> 200
  health revenue_runtime -> 404
BASE
}

health_check() {
  for label_url in \
    "gatekeeper:http://127.0.0.1:5000/" \
    "conductor:http://127.0.0.1:5060/health" \
    "n8n:http://127.0.0.1:5678/healthz" \
    "dominion_publisher:http://127.0.0.1:5112/health" \
    "revenue_runtime:http://127.0.0.1:8790/" \
    "command_center:http://127.0.0.1:8091/api/status" \
    "ascendant_store:http://127.0.0.1:5090/health" \
    "dominion_store:http://127.0.0.1:5080/"; do
    label="${label_url%%:*}"
    url="${label_url#*:}"
    code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$url" 2>/dev/null)"
    say "  health $label -> ${code:-NO_RESPONSE}"
  done
}

# ══ PHASE 1 — verify exact infrastructure ══════════════════════════════
head2 "PHASE 1: GCLOUD IDENTITY AND PROJECT"
command -v gcloud >/dev/null 2>&1 || die "gcloud is not available on this VM"
say "  gcloud=$(command -v gcloud)"
say "  active_account=$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null || echo UNKNOWN)"
current_project="$(gcloud config get-value project 2>/dev/null)"
say "  configured_project=${current_project:-<unset>}"
say "  target_project=$PROJECT"

head2 "PHASE 1: INSTANCE DESCRIBE"
instance_json="$(gcloud compute instances describe "$INSTANCE" \
  --zone="$ZONE" --project="$PROJECT" --format=json 2>&1)"
if ! printf '%s' "$instance_json" | head -c1 | grep -q '{'; then
  say "  describe_failed_output<<"
  printf '%s\n' "$instance_json" | head -20 | sed 's/^/    /'
  die "cannot describe instance $INSTANCE -- the VM service account may lack compute.instances.get"
fi

# Boot disk is the attached disk with boot=true. Never assumed by name.
BOOT_DISK="$(printf '%s' "$instance_json" | python3 -c '
import json,sys
d=json.load(sys.stdin)
for disk in d.get("disks",[]):
    if disk.get("boot"):
        src=disk.get("source","")
        print(src.rsplit("/",1)[-1])
        break
' 2>/dev/null)"
VM_STATUS="$(printf '%s' "$instance_json" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("status","UNKNOWN"))' 2>/dev/null)"
say "  vm_status=$VM_STATUS"
say "  boot_disk_name=${BOOT_DISK:-UNRESOLVED}"
[ -n "$BOOT_DISK" ] || die "could not resolve the boot disk from the instance description"

head2 "PHASE 1: DISK DESCRIBE (independent verification)"
disk_json="$(gcloud compute disks describe "$BOOT_DISK" \
  --zone="$ZONE" --project="$PROJECT" --format=json 2>&1)"
if ! printf '%s' "$disk_json" | head -c1 | grep -q '{'; then
  say "  describe_failed_output<<"
  printf '%s\n' "$disk_json" | head -20 | sed 's/^/    /'
  die "cannot describe disk $BOOT_DISK -- the VM service account may lack compute.disks.get"
fi
DISK_SIZE_GB="$(printf '%s' "$disk_json" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("sizeGb","0"))' 2>/dev/null)"
DISK_TYPE="$(printf '%s' "$disk_json" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("type","").rsplit("/",1)[-1])' 2>/dev/null)"
DISK_SOURCE_IMAGE="$(printf '%s' "$disk_json" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("sourceImage","<none>").rsplit("/",1)[-1])' 2>/dev/null)"
DISK_USERS="$(printf '%s' "$disk_json" | python3 -c '
import json,sys
print(",".join(u.rsplit("/",1)[-1] for u in json.load(sys.stdin).get("users",[])) or "<none>")' 2>/dev/null)"
say "  disk_name=$BOOT_DISK"
say "  disk_size_gb=$DISK_SIZE_GB"
say "  disk_type=$DISK_TYPE"
say "  disk_source_image=$DISK_SOURCE_IMAGE"
say "  disk_attached_to=$DISK_USERS"

# Identity gates. Any mismatch stops before anything is created or changed.
printf '%s' "$DISK_USERS" | grep -qw "$INSTANCE" \
  || die "disk $BOOT_DISK is not attached to $INSTANCE (users=$DISK_USERS)"
case "$DISK_SIZE_GB" in ''|*[!0-9]*) die "disk size '$DISK_SIZE_GB' is not numeric" ;; esac
if [ "$DISK_SIZE_GB" -ge "$TARGET_SIZE_GB" ]; then
  say "  NOTE: disk already reports ${DISK_SIZE_GB}GB (>= target ${TARGET_SIZE_GB}GB)"
  ALREADY_CLOUD_SIZED=1
else
  ALREADY_CLOUD_SIZED=0
  [ "$DISK_SIZE_GB" -ge "$MIN_EXPECTED_GB" ] && [ "$DISK_SIZE_GB" -le "$MAX_EXPECTED_GB" ] \
    || die "disk is ${DISK_SIZE_GB}GB, outside the expected ${MIN_EXPECTED_GB}-${MAX_EXPECTED_GB}GB range for the ~50GB root disk"
fi
say "  identity_gate=PASS"

# ══ PHASE 4 — Linux block layout (read-only, both modes) ═══════════════
head2 "PHASE 4: FILESYSTEM AND BLOCK LAYOUT BEFORE"
say "  -- df -hT / --"
df -hT / 2>&1 | sed 's/^/    /'
say "  -- df -i / --"
df -i / 2>&1 | sed 's/^/    /'
say "  -- findmnt / --"
findmnt / 2>&1 | sed 's/^/    /'
say "  -- lsblk --"
lsblk -o NAME,SIZE,FSTYPE,TYPE,MOUNTPOINTS 2>&1 | sed 's/^/    /'
say "  -- fdisk -l --"
$SUDO fdisk -l 2>/dev/null | sed 's/^/    /' | head -40

# Resolve the root device dynamically. Never assumes sda1 vs nvme naming.
ROOT_SRC="$(findmnt -n -o SOURCE / 2>/dev/null)"
ROOT_FSTYPE="$(findmnt -n -o FSTYPE / 2>/dev/null)"
say ""
say "  root_source=$ROOT_SRC"
say "  root_fstype=$ROOT_FSTYPE"
[ -n "$ROOT_SRC" ] || die "could not resolve the root device"

# Parent disk and partition number, derived from the kernel rather than parsed
# out of the device name, so nvme0n1p1 and sda1 both resolve correctly.
ROOT_BASE="$(basename "$ROOT_SRC")"
PARENT_DISK="$(lsblk -no PKNAME "/dev/$ROOT_BASE" 2>/dev/null | head -1)"
PART_NUM="$(cat "/sys/class/block/$ROOT_BASE/partition" 2>/dev/null)"
say "  root_parent_disk=${PARENT_DISK:-<none>}"
say "  root_partition_number=${PART_NUM:-<none>}"

BEFORE_SIZE="$(df -h --output=size / 2>/dev/null | tail -1 | tr -d ' ')"
BEFORE_AVAIL="$(df -h --output=avail / 2>/dev/null | tail -1 | tr -d ' ')"
BEFORE_PCT="$(df -h --output=pcent / 2>/dev/null | tail -1 | tr -d ' %')"
say "  root_fs_size_before=$BEFORE_SIZE"
say "  root_fs_avail_before=$BEFORE_AVAIL"
say "  root_fs_used_pct_before=${BEFORE_PCT}%"

say ""
say "  -- growpart availability --"
if command -v growpart >/dev/null 2>&1; then
  say "  growpart=$(command -v growpart) AVAILABLE"
  GROWPART_OK=1
else
  say "  growpart=NOT INSTALLED (provided by cloud-guest-utils)"
  GROWPART_OK=0
fi

head2 "PHASE 4: HEALTH BASELINE (this run)"
health_check

if [ "$MODE" != "expand" ]; then
  say ""
  say "RESULT=INSPECTED_NOT_EXPANDED"
  say "ACTION_TAKEN=NONE (inspect mode)"
  say "FOUNDATION_VM_DISK_EXPANSION_END"
  exit 0
fi

# ══════════════════════ EXPAND MODE FROM HERE ══════════════════════════

# Filesystem allowlist. Anything else stops rather than guessing at a
# growth procedure that might not be safe for it.
case "$ROOT_FSTYPE" in
  ext4|ext3|ext2) GROW_TOOL="resize2fs" ;;
  xfs)            GROW_TOOL="xfs_growfs" ;;
  *) die "root filesystem type '$ROOT_FSTYPE' is not ext* or xfs -- refusing to guess at an expansion procedure" ;;
esac
say ""
say "  filesystem_grow_tool=$GROW_TOOL"

[ -n "$PARENT_DISK" ] || die "could not resolve the parent disk of $ROOT_SRC"
[ -n "$PART_NUM" ]    || die "root device $ROOT_SRC is not a partition; refusing to run growpart"

# ══ PHASE 2 — recovery snapshot BEFORE any capacity change ═════════════
head2 "PHASE 2: PRE-RESIZE SNAPSHOT"
SNAPSHOT_NAME="foundation-vm-pre-resize-$(date -u +%Y%m%d-%H%M%S)"
say "  snapshot_name=$SNAPSHOT_NAME"
snap_out="$(gcloud compute snapshots create "$SNAPSHOT_NAME" \
  --source-disk="$BOOT_DISK" \
  --source-disk-zone="$ZONE" \
  --project="$PROJECT" 2>&1)"
snap_rc=$?
printf '%s\n' "$snap_out" | sed 's/^/    /' | head -20
[ "$snap_rc" -eq 0 ] || die "snapshot creation failed -- not resizing anything"

# Poll until READY. No resize happens on a snapshot stuck in CREATING.
snap_status=""
waited=0
while [ "$waited" -lt 600 ]; do
  snap_status="$(gcloud compute snapshots describe "$SNAPSHOT_NAME" \
    --project="$PROJECT" --format='value(status)' 2>/dev/null)"
  say "  snapshot_status=$snap_status waited=${waited}s"
  [ "$snap_status" = "READY" ] && break
  [ "$snap_status" = "FAILED" ] && die "snapshot $SNAPSHOT_NAME reported FAILED"
  sleep 10
  waited=$((waited + 10))
done
[ "$snap_status" = "READY" ] \
  || die "snapshot $SNAPSHOT_NAME did not reach READY within ${waited}s (status=$snap_status)"
say "  FOUNDATION_VM_PRE_RESIZE_SNAPSHOT=PASS"

# ══ PHASE 3 — increase the persistent disk ═════════════════════════════
head2 "PHASE 3: CLOUD DISK RESIZE TO ${TARGET_SIZE_GB}GB"
if [ "$ALREADY_CLOUD_SIZED" -eq 1 ]; then
  say "  disk already at ${DISK_SIZE_GB}GB; no cloud resize issued"
else
  resize_out="$(gcloud compute disks resize "$BOOT_DISK" \
    --size="${TARGET_SIZE_GB}GB" \
    --zone="$ZONE" --project="$PROJECT" --quiet 2>&1)"
  resize_rc=$?
  printf '%s\n' "$resize_out" | sed 's/^/    /' | head -20
  [ "$resize_rc" -eq 0 ] || die "cloud disk resize failed"
fi

NEW_SIZE_GB="$(gcloud compute disks describe "$BOOT_DISK" \
  --zone="$ZONE" --project="$PROJECT" --format='value(sizeGb)' 2>/dev/null)"
say "  disk_size_gb_after=$NEW_SIZE_GB"
[ "$NEW_SIZE_GB" = "$TARGET_SIZE_GB" ] \
  || die "cloud disk reports ${NEW_SIZE_GB}GB, expected ${TARGET_SIZE_GB}GB -- not touching the partition"
say "  FOUNDATION_VM_CLOUD_DISK_RESIZE=PASS"

# ══ PHASE 5 — grow partition, then filesystem ══════════════════════════
head2 "PHASE 5: RESCAN AND GROW PARTITION"
# Make the kernel notice the larger device before growpart reads it.
if [ -w "/sys/class/block/$PARENT_DISK/device/rescan" ]; then
  $SUDO sh -c "echo 1 > /sys/class/block/$PARENT_DISK/device/rescan" 2>/dev/null || true
  say "  issued device rescan for $PARENT_DISK"
fi
$SUDO partprobe "/dev/$PARENT_DISK" 2>/dev/null && say "  partprobe ok" || say "  partprobe unavailable or non-fatal"

if [ "$GROWPART_OK" -ne 1 ]; then
  die "growpart is not installed (package cloud-guest-utils); refusing to hand-edit the partition table of a live root disk"
fi

say "  running: growpart /dev/$PARENT_DISK $PART_NUM"
grow_out="$($SUDO growpart "/dev/$PARENT_DISK" "$PART_NUM" 2>&1)"
grow_rc=$?
printf '%s\n' "$grow_out" | sed 's/^/    /'
# growpart exits 1 with NOCHANGE when the partition is already at max, which
# is a success for our purpose, not a failure.
if [ "$grow_rc" -ne 0 ]; then
  if printf '%s' "$grow_out" | grep -qi 'NOCHANGE'; then
    say "  growpart reported NOCHANGE (partition already spans the disk)"
  else
    die "growpart failed (rc=$grow_rc)"
  fi
fi

say ""
say "  -- lsblk after growpart --"
lsblk -o NAME,SIZE,FSTYPE,TYPE,MOUNTPOINTS 2>&1 | sed 's/^/    /'

head2 "PHASE 5: GROW FILESYSTEM ($GROW_TOOL)"
if [ "$GROW_TOOL" = "resize2fs" ]; then
  fs_out="$($SUDO resize2fs "$ROOT_SRC" 2>&1)"; fs_rc=$?
else
  fs_out="$($SUDO xfs_growfs -d / 2>&1)"; fs_rc=$?
fi
printf '%s\n' "$fs_out" | sed 's/^/    /'
[ "$fs_rc" -eq 0 ] || die "$GROW_TOOL failed (rc=$fs_rc)"

# ══ PHASE 6 — verify capacity ══════════════════════════════════════════
head2 "PHASE 6: CAPACITY AFTER"
df -hT / 2>&1 | sed 's/^/    /'
lsblk -o NAME,SIZE,FSTYPE,TYPE,MOUNTPOINTS 2>&1 | sed 's/^/    /'

AFTER_SIZE="$(df -h --output=size / 2>/dev/null | tail -1 | tr -d ' ')"
AFTER_AVAIL="$(df -h --output=avail / 2>/dev/null | tail -1 | tr -d ' ')"
AFTER_PCT="$(df -h --output=pcent / 2>/dev/null | tail -1 | tr -d ' %')"
AVAIL_GB="$(df -BG --output=avail / 2>/dev/null | tail -1 | tr -d ' G')"
say ""
say "  root_fs_size_before=$BEFORE_SIZE  root_fs_size_after=$AFTER_SIZE"
say "  root_fs_avail_before=$BEFORE_AVAIL  root_fs_avail_after=$AFTER_AVAIL"
say "  root_fs_used_pct_before=${BEFORE_PCT}%  root_fs_used_pct_after=${AFTER_PCT}%"
say "  root_fs_avail_gb_after=$AVAIL_GB"

case "$AVAIL_GB" in ''|*[!0-9]*) die "could not read available GB after expansion" ;; esac
[ "$AVAIL_GB" -gt "$REQUIRED_FREE_GB" ] \
  || die "only ${AVAIL_GB}GB free after expansion; required more than ${REQUIRED_FREE_GB}GB of healthy reserve"
case "$AFTER_PCT" in ''|*[!0-9]*) die "could not read used percentage after expansion" ;; esac
[ "$AFTER_PCT" -lt 94 ] || die "root still at ${AFTER_PCT}% used; expansion did not relieve pressure"
say "  FOUNDATION_VM_FILESYSTEM_EXPANSION=PASS"

# ══ PHASE 7 — production health verification ═══════════════════════════
head2 "PHASE 7: CONTAINER RUNTIME"
$SUDO docker ps --format '  id={{.ID}} name={{.Names}} image={{.Image}} status={{.Status}}' 2>&1
say ""
say "  -- docker system df --"
$SUDO docker system df 2>&1 | sed 's/^/    /'

head2 "PHASE 7: DOCKER VOLUMES (must all still exist)"
$SUDO docker volume ls --format '  volume={{.Name}}' 2>&1

head2 "PHASE 7: ROLLBACK ASSETS (must still exist)"
$SUDO docker images --format '  image={{.Repository}}:{{.Tag}} id={{.ID}}' 2>/dev/null | grep -i rollback \
  || say "  WARNING: no rollback-tagged image found"

head2 "PHASE 7: HEALTH AFTER"
health_check

head2 "PHASE 7: KERNEL ERRORS"
$SUDO dmesg --level=err,crit,alert,emerg 2>/dev/null | tail -100 | sed 's/^/    /' \
  || say "  dmesg unavailable"

head2 "PHASE 7: RECORDED PRE-RESIZE BASELINE (run 34897600099)"
baseline_health

say ""
say "FOUNDATION_VM_DISK_EXPANSION_END"
say "MUTATIONS_KIND=snapshot_create,cloud_disk_resize,partition_grow,filesystem_grow"

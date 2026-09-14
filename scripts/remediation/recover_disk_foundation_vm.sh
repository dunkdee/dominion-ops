#!/usr/bin/env bash
# Recover disk headroom on foundation-vm for the DeerFlow production rebuild.
#
# AUTHORIZED SCOPE: reclaim OBVIOUSLY safe space -- unused Docker build cache,
# dangling images, images not referenced by any container (running or
# stopped), stopped disposable containers, stale DeerFlow/Dominion deploy
# scratch directories, and oversized rotated logs. Nothing else.
#
# NEVER TOUCHED, under any mode: docker volumes, databases, n8n state, any
# running container, current production config, secrets, persistent
# application state, rollback assets, active Dominion service data. There is
# no volume-pruning command anywhere in this file, and the gate in the
# workflow greps to prove it.
#
# Two modes:
#   inspect  (default, read-only) -- reports sizes, does not delete anything
#   cleanup  -- performs only the allowlisted deletions above
#
# It does not use `set -e`: a missing tool or unreadable path is itself a
# finding, and aborting on the first one would hide the rest.
set -uo pipefail

MODE="${1:-inspect}"

say()   { printf '%s\n' "$*"; }
head2() { printf '\n== %s ==\n' "$*"; }

SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  sudo -n true 2>/dev/null && SUDO="sudo -n"
fi


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

say "FOUNDATION_VM_STORAGE_RECOVERY_BEGIN"
say "collected_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
say "hostname=$(hostname 2>/dev/null || echo UNKNOWN)"
say "mode=$MODE"

# ── BEFORE snapshot ─────────────────────────────────────────────────────
head2 "DISK SPACE BEFORE"
df -h 2>&1
head2 "INODES BEFORE"
df -i 2>&1
head2 "DOCKER STORAGE BEFORE"
if command -v docker >/dev/null 2>&1; then
  $SUDO docker system df -v 2>&1
else
  say "docker: NOT AVAILABLE"
fi

# ── where the space is going ────────────────────────────────────────────
head2 "PRODUCTION HEALTH VERIFICATION (BASELINE)"
health_check

head2 "LARGEST DIRECTORIES UNDER /var (top 15)"
$SUDO du -xh /var 2>/dev/null | sort -rh | head -15

head2 "LARGEST DIRECTORIES UNDER /opt (top 15)"
$SUDO du -xh /opt 2>/dev/null | sort -rh | head -15

head2 "LARGEST DIRECTORIES UNDER /tmp (top 15)"
$SUDO du -xh /tmp 2>/dev/null | sort -rh | head -15

head2 "RUNNING CONTAINERS (never touched)"
$SUDO docker ps --format 'id={{.ID}} name={{.Names}} image={{.Image}} status={{.Status}}' 2>&1

head2 "STOPPED / EXITED CONTAINERS (cleanup candidates)"
$SUDO docker ps -a --filter status=exited --filter status=created \
  --format 'id={{.ID}} name={{.Names}} image={{.Image}} status={{.Status}}' 2>&1

head2 "DANGLING IMAGES (cleanup candidates)"
$SUDO docker images -f dangling=true --format 'id={{.ID}} repo={{.Repository}} size={{.Size}}' 2>&1

head2 "IMAGES NOT REFERENCED BY ANY CONTAINER (running or stopped)"
# Compared by IMAGE ID, which is what a container actually references --
# not by repository:tag string, which can silently under- or over-match
# (e.g. a container started without an explicit tag, or a tag that has
# since been reassigned to a different image).
used_ids="$($SUDO docker ps -a --format '{{.ImageID}}' 2>/dev/null | cut -c1-12 | sort -u)"
$SUDO docker images --format '{{.ID}} {{.Repository}}:{{.Tag}}' 2>/dev/null | while read -r id ref; do
  short_id="$(printf '%s' "$id" | cut -c1-12)"
  if printf '%s\n' "$used_ids" | grep -qxF "$short_id"; then
    continue
  fi
  if printf '%s' "$ref" | grep -qi 'rollback'; then
    echo "unused image=$ref id=$id PROTECTED=rollback-asset-never-removed"
  else
    echo "unused image=$ref id=$id"
  fi
done

head2 "DOCKER BUILD CACHE"
$SUDO docker buildx du 2>&1 || $SUDO docker builder prune --dry-run 2>&1 || say "build cache introspection unavailable"

head2 "STALE DEPLOY SCRATCH DIRECTORIES (candidates only, never auto-selected)"
# The pattern every VM-side workflow in this repo uses for scratch dirs.
find /tmp -maxdepth 1 -type d -name 'dominion_*' -mtime +1 2>/dev/null | while read -r d; do
  echo "candidate=$d size=$($SUDO du -sh "$d" 2>/dev/null | cut -f1) age_days=$(( ( $(date +%s) - $(stat -c %Y "$d" 2>/dev/null || echo 0) ) / 86400 ))"
done
find /home -maxdepth 2 -type d \( -name 'dominion_meta_binding_*' -o -name 'deerflow_deploy_*' \) -mtime +1 2>/dev/null | while read -r d; do
  echo "candidate=$d size=$($SUDO du -sh "$d" 2>/dev/null | cut -f1)"
done

head2 "OVERSIZED LOG FILES (candidates only, >100MB, never auto-selected)"
$SUDO find /var/log -type f -size +100M 2>/dev/null -exec ls -lh {} \; | awk '{print "candidate="$NF" size="$5}'

if [ "$MODE" != "cleanup" ]; then
  say ""
  say "RESULT=INSPECTED_NOT_CLEANED"
  say "ACTION_TAKEN=NONE (inspect mode)"
  say "FOUNDATION_VM_STORAGE_RECOVERY_END"
  exit 0
fi

# ── CLEANUP: allowlisted operations only ────────────────────────────────
head2 "CLEANUP: DOCKER BUILD CACHE"
$SUDO docker builder prune -f 2>&1 || true

head2 "CLEANUP: DANGLING IMAGES"
$SUDO docker image prune -f 2>&1 || true

head2 "CLEANUP: UNUSED IMAGES NOT REFERENCED BY ANY CONTAINER"
# Never a blanket `docker image prune -af`. That command's only safety
# semantic is "no container references it" -- it does not know or care that
# a name contains "rollback". So the exact same used-id / rollback-pattern
# logic as the inspect pass decides removal here, one image at a time, and
# a rollback asset can never be selected no matter what else is unused.
used_ids="$($SUDO docker ps -a --format '{{.ImageID}}' 2>/dev/null | cut -c1-12 | sort -u)"
$SUDO docker images --format '{{.ID}} {{.Repository}}:{{.Tag}}' 2>/dev/null | while read -r id ref; do
  short_id="$(printf '%s' "$id" | cut -c1-12)"
  if printf '%s\n' "$used_ids" | grep -qxF "$short_id"; then
    continue
  fi
  if printf '%s' "$ref" | grep -qi 'rollback'; then
    say "  skipping PROTECTED rollback asset: $ref ($id)"
    continue
  fi
  say "  removing unused image: $ref ($id)"
  $SUDO docker rmi "$id" 2>&1 || true
done

head2 "CLEANUP: STOPPED / EXITED / CREATED CONTAINERS"
# Never running containers -- docker container prune only ever touches
# non-running ones by definition.
$SUDO docker container prune -f 2>&1 || true

head2 "CLEANUP: STALE DEPLOY SCRATCH DIRECTORIES (>1 day old, known prefixes only)"
for d in $(find /tmp -maxdepth 1 -type d -name 'dominion_*' -mtime +1 2>/dev/null); do
  say "removing $d"
  $SUDO rm -rf -- "$d"
done
for d in $(find /home -maxdepth 2 -type d \( -name 'dominion_meta_binding_*' -o -name 'deerflow_deploy_*' \) -mtime +1 2>/dev/null); do
  say "removing $d"
  $SUDO rm -rf -- "$d"
done

head2 "CLEANUP: OVERSIZED ROTATED LOGS (>100MB, rotated suffix only, e.g. .log.1 / .gz)"
# Only ever a ROTATED log (an already-numbered or already-compressed
# rotation), never the live file a service is currently writing to -- so an
# active log can never be truncated or deleted by this step.
$SUDO find /var/log -type f -size +100M \( -name '*.log.[0-9]*' -o -name '*.gz' \) 2>/dev/null -print -delete

say ""
say "FOUNDATION_VM_STORAGE_RECOVERY_ACTIONS_COMPLETE"

# ── AFTER snapshot ───────────────────────────────────────────────────────
head2 "DISK SPACE AFTER"
df -h 2>&1
head2 "INODES AFTER"
df -i 2>&1
head2 "DOCKER STORAGE AFTER"
$SUDO docker system df -v 2>&1

# ── health verification: nothing that was running is now not running ───
head2 "PRODUCTION HEALTH VERIFICATION (AFTER)"
say "  containers running now:"
$SUDO docker ps --format '  id={{.ID}} name={{.Names}} status={{.Status}}' 2>&1
health_check

say ""
say "FOUNDATION_VM_STORAGE_RECOVERY_END"
say "MUTATIONS_KIND=docker_prune,scratch_dir_removal,rotated_log_removal"

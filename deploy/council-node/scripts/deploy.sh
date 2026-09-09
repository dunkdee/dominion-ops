#!/usr/bin/env bash
# Deploy the Council Node at an exact commit, recording what it replaced.
#
# Records the previous SHA before changing anything, so rollback.sh has a
# target that was captured rather than guessed.
set -Eeuo pipefail

INSTALL_ROOT="${INSTALL_ROOT:-/opt/dominion/council-node}"
STATE_DIR="${STATE_DIR:-/var/lib/dominion}"
TARGET_SHA="${1:-}"

log()  { printf '[deploy] %s\n' "$*"; }
fail() { printf '[deploy] FAILED: %s\n' "$*" >&2; exit 1; }

[ -n "$TARGET_SHA" ] || fail "usage: deploy.sh <40-char-commit-sha>"
[[ "$TARGET_SHA" =~ ^[0-9a-f]{40}$ ]] || fail "target must be a full 40-character SHA"
[ -d "$INSTALL_ROOT/.git" ] || fail "no repository at $INSTALL_ROOT"

cd "$INSTALL_ROOT"
PREVIOUS_SHA="$(git rev-parse HEAD)"
log "current: $PREVIOUS_SHA"
log "target:  $TARGET_SHA"

if [ "$PREVIOUS_SHA" = "$TARGET_SHA" ]; then
  log "already at target; nothing to do"
  exit 0
fi

git fetch --depth 50 origin || fail "fetch failed"
git cat-file -e "${TARGET_SHA}^{commit}" 2>/dev/null || fail "commit $TARGET_SHA not found"

# Capture the rollback target before mutating anything.
install -d -m 0700 "$STATE_DIR"
printf '%s\n' "$PREVIOUS_SHA" > "$STATE_DIR/council-node.previous-sha"
chmod 0600 "$STATE_DIR/council-node.previous-sha"

git checkout --quiet --detach "$TARGET_SHA" || fail "checkout failed"
log "checked out $TARGET_SHA"

cd "$INSTALL_ROOT/deploy/council-node"
docker compose build council-api || fail "image build failed"
docker compose up -d --remove-orphans || fail "compose up failed"

log "waiting for health"
for _ in $(seq 1 30); do
  if docker compose exec -T council-api python -c \
      "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8200/health',timeout=3).status==200 else 1)" \
      2>/dev/null; then
    log "healthy at $TARGET_SHA"
    log "previous SHA recorded at $STATE_DIR/council-node.previous-sha"
    exit 0
  fi
  sleep 2
done

fail "service did not become healthy; run rollback.sh"

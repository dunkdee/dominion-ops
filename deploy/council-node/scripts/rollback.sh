#!/usr/bin/env bash
# Roll back to the SHA deploy.sh recorded.
#
# Refuses to cross a destructive migration: if a migration marker exists for
# the current release, the operator must resolve it deliberately. Rolling a
# schema backwards silently is how data is lost.
set -Eeuo pipefail

INSTALL_ROOT="${INSTALL_ROOT:-/opt/dominion/council-node}"
STATE_DIR="${STATE_DIR:-/var/lib/dominion}"
PREVIOUS_FILE="$STATE_DIR/council-node.previous-sha"
DESTRUCTIVE_MARKER="$STATE_DIR/council-node.destructive-migration"

log()  { printf '[rollback] %s\n' "$*"; }
fail() { printf '[rollback] FAILED: %s\n' "$*" >&2; exit 1; }

[ -f "$PREVIOUS_FILE" ] || fail "no recorded previous SHA at $PREVIOUS_FILE"
TARGET="$(tr -d '[:space:]' < "$PREVIOUS_FILE")"
[[ "$TARGET" =~ ^[0-9a-f]{40}$ ]] || fail "recorded SHA is malformed"

if [ -f "$DESTRUCTIVE_MARKER" ]; then
  fail "a destructive migration is recorded; automatic rollback is refused. Resolve manually, then remove $DESTRUCTIVE_MARKER"
fi

cd "$INSTALL_ROOT"
CURRENT="$(git rev-parse HEAD)"
log "rolling back $CURRENT -> $TARGET"

git checkout --quiet --detach "$TARGET" || fail "checkout failed"
cd "$INSTALL_ROOT/deploy/council-node"
docker compose build council-api || fail "rebuild failed"
docker compose up -d --remove-orphans || fail "compose up failed"

log "rolled back to $TARGET"
log "record a rollback receipt before declaring this closed"

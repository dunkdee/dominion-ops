#!/usr/bin/env bash
# Install / update the Ascendant Digital storefront on the foundation VM.
#
# Idempotent. Safe to re-run: it rebuilds the venv only when requirements
# change, and every schema statement is IF NOT EXISTS.
#
# It never prints a secret and never writes one. Credentials are expected to
# already exist in the 0600 runtime env file; the installer verifies their
# presence by name and refuses to start the service without them.
set -Eeuo pipefail

STATE_ROOT="${ASCENDANT_STATE_ROOT:-$HOME/.dominion/ascendant-store}"
RELEASE_DIR="$STATE_ROOT/runtime/release"
VENV="$STATE_ROOT/venv"
ENV_FILE="$STATE_ROOT/runtime.env"
SOURCE_DIR="${1:-}"

log()  { printf '[store-install] %s\n' "$*"; }
fail() { printf '[store-install] FAILED: %s\n' "$*" >&2; exit 1; }

[ -n "$SOURCE_DIR" ] || fail "usage: ascendant_store_install.sh <staged-source-dir>"
[ -d "$SOURCE_DIR/ascendant_store" ] || fail "no ascendant_store/ in $SOURCE_DIR"

install -d -m 700 "$STATE_ROOT" "$STATE_ROOT/runtime"
install -d -m 700 "$HOME/logs"

# ── release ────────────────────────────────────────────────────────────
rm -rf "$RELEASE_DIR.new"
mkdir -p "$RELEASE_DIR.new"
cp -a "$SOURCE_DIR/ascendant_store" "$RELEASE_DIR.new/"
rm -rf "$RELEASE_DIR.previous"
[ -d "$RELEASE_DIR" ] && mv "$RELEASE_DIR" "$RELEASE_DIR.previous"
mv "$RELEASE_DIR.new" "$RELEASE_DIR"
log "release staged"

# ── venv ───────────────────────────────────────────────────────────────
if [ ! -x "$VENV/bin/python" ]; then
  log "creating venv"
  python3 -m venv "$VENV"
fi
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$RELEASE_DIR/ascendant_store/requirements.txt"
log "dependencies installed"

# ── required configuration (names only, values never echoed) ───────────
[ -s "$ENV_FILE" ] || fail "runtime env $ENV_FILE is missing; create it 0600 with the required names"
chmod 600 "$ENV_FILE"
missing=()
for name in STRIPE_SECRET_KEY STRIPE_PUBLISHABLE_KEY STRIPE_WEBHOOK_SECRET DB_PASSWORD ASCENDANT_DOMAIN; do
  grep -q "^${name}=." "$ENV_FILE" || missing+=("$name")
done
if [ "${#missing[@]}" -gt 0 ]; then
  fail "runtime env is missing required settings: ${missing[*]}"
fi
log "required configuration present"

# ── schema ─────────────────────────────────────────────────────────────
if command -v psql >/dev/null 2>&1; then
  log "applying schema (idempotent)"
  PGPASSWORD="$(sed -n 's/^DB_PASSWORD=//p' "$ENV_FILE" | head -1)" \
    psql -h 127.0.0.1 -U dominion -d dominion -q \
      -f "$RELEASE_DIR/ascendant_store/schema.sql" \
    || fail "schema apply failed"
  PGPASSWORD="$(sed -n 's/^DB_PASSWORD=//p' "$ENV_FILE" | head -1)" \
    psql -h 127.0.0.1 -U dominion -d dominion -q \
      -f "$RELEASE_DIR/ascendant_store/migration_001_orders_attribution.sql" \
    || fail "migration apply failed"
  log "schema and migration applied"
else
  fail "psql not found; PostgreSQL is required for orders and webhook idempotency"
fi

# ── service ────────────────────────────────────────────────────────────
UNIT_SRC="$RELEASE_DIR/../../deploy/systemd/dominion-ascendant-store.service"
if [ -f "$SOURCE_DIR/deploy/systemd/dominion-ascendant-store.service" ]; then
  sudo install -m 644 "$SOURCE_DIR/deploy/systemd/dominion-ascendant-store.service" \
    /etc/systemd/system/dominion-ascendant-store.service
  sudo systemctl daemon-reload
  sudo systemctl enable dominion-ascendant-store.service
  sudo systemctl restart dominion-ascendant-store.service
  log "service restarted"
else
  fail "systemd unit not found in staged source"
fi

# ── health ─────────────────────────────────────────────────────────────
for _ in $(seq 1 20); do
  if curl -fsS --max-time 3 http://127.0.0.1:5090/health >/dev/null 2>&1; then
    log "STORE_HEALTH=PASS"
    exit 0
  fi
  sleep 2
done
fail "service did not become healthy on 127.0.0.1:5090"

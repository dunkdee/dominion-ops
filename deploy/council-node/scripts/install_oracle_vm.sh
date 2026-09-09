#!/usr/bin/env bash
# Oracle Cloud VM bootstrap for the Dominion Council Node.
#
# Idempotent: safe to re-run. Every step checks before it changes anything, so
# a partial run can simply be repeated.
#
# It refuses rather than guesses. Running as the wrong user, on an unsupported
# OS, or without Docker available after install stops the script with a stated
# reason instead of leaving a half-configured host.
#
# It never prints a secret. It never writes one either -- secrets are placed in
# /etc/dominion/secrets afterwards, by hand or by Oracle Vault.
set -Eeuo pipefail

SERVICE_USER="${SERVICE_USER:-dominion}"
INSTALL_ROOT="${INSTALL_ROOT:-/opt/dominion}"
DATA_ROOT="${DATA_ROOT:-/var/lib/dominion}"
CONFIG_ROOT="${CONFIG_ROOT:-/etc/dominion}"
REPO_URL="${REPO_URL:-https://github.com/dunkdee/dominion-ops.git}"

log()  { printf '[install] %s\n' "$*"; }
fail() { printf '[install] FAILED: %s\n' "$*" >&2; exit 1; }

# ── preconditions ──────────────────────────────────────────────────────
[ "$(id -u)" -eq 0 ] || fail "must run as root (use sudo)"

[ -r /etc/os-release ] || fail "/etc/os-release is missing; unsupported OS"
# shellcheck disable=SC1091
. /etc/os-release
case "${ID:-}" in
  ubuntu|debian|ol|oracle|rhel|almalinux|rocky) log "detected ${PRETTY_NAME:-$ID}" ;;
  *) fail "unsupported OS '${ID:-unknown}'; expected Ubuntu 24.04 or Oracle Linux 9" ;;
esac

if [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" = "$SERVICE_USER" ]; then
  fail "refusing to install as the service user itself"
fi

command -v systemctl >/dev/null 2>&1 || fail "systemd is required"

# ── packages ───────────────────────────────────────────────────────────
if command -v apt-get >/dev/null 2>&1; then
  PKG=apt
elif command -v dnf >/dev/null 2>&1; then
  PKG=dnf
else
  fail "neither apt-get nor dnf is available"
fi

log "updating packages"
if [ "$PKG" = apt ]; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq ca-certificates curl git fail2ban ufw chrony
else
  dnf install -y -q ca-certificates curl git fail2ban firewalld chrony
fi

# ── docker ─────────────────────────────────────────────────────────────
if command -v docker >/dev/null 2>&1; then
  log "docker already installed: $(docker --version)"
else
  log "installing docker engine"
  curl -fsSL https://get.docker.com | sh
fi
docker compose version >/dev/null 2>&1 || fail "docker compose plugin is unavailable"
systemctl enable --now docker

# ── time sync ──────────────────────────────────────────────────────────
systemctl enable --now chronyd 2>/dev/null || systemctl enable --now chrony 2>/dev/null || \
  log "WARNING: could not enable time sync; receipts depend on accurate clocks"

# ── service user ───────────────────────────────────────────────────────
if id -u "$SERVICE_USER" >/dev/null 2>&1; then
  log "user $SERVICE_USER exists"
else
  log "creating system user $SERVICE_USER"
  useradd --system --create-home --shell /usr/sbin/nologin "$SERVICE_USER"
fi
usermod -aG docker "$SERVICE_USER"

# ── directories ────────────────────────────────────────────────────────
install -d -m 0755 -o "$SERVICE_USER" -g "$SERVICE_USER" "$INSTALL_ROOT"
install -d -m 0700 -o "$SERVICE_USER" -g "$SERVICE_USER" \
  "$DATA_ROOT" "$DATA_ROOT/postgres" "$DATA_ROOT/ollama" "$DATA_ROOT/receipts"
install -d -m 0750 -o root -g "$SERVICE_USER" "$CONFIG_ROOT" "$CONFIG_ROOT/council-node"
install -d -m 0700 -o root -g root "$CONFIG_ROOT/secrets"

# ── firewall: 22/80/443 only ───────────────────────────────────────────
if command -v ufw >/dev/null 2>&1; then
  log "configuring ufw"
  ufw --force default deny incoming
  ufw --force default allow outgoing
  for port in 22 80 443; do ufw allow "$port"/tcp >/dev/null; done
  ufw --force enable
elif command -v firewall-cmd >/dev/null 2>&1; then
  log "configuring firewalld"
  systemctl enable --now firewalld
  for svc in ssh http https; do firewall-cmd --permanent --add-service="$svc" >/dev/null; done
  firewall-cmd --reload >/dev/null
fi

systemctl enable --now fail2ban 2>/dev/null || log "WARNING: fail2ban not enabled"

# ── ssh hardening ──────────────────────────────────────────────────────
SSHD_DROPIN=/etc/ssh/sshd_config.d/50-dominion.conf
if [ -d /etc/ssh/sshd_config.d ]; then
  cat > "$SSHD_DROPIN" <<'SSHEOF'
PermitRootLogin no
PasswordAuthentication no
ChallengeResponseAuthentication no
SSHEOF
  chmod 0644 "$SSHD_DROPIN"
  sshd -t && systemctl reload sshd 2>/dev/null || log "WARNING: sshd reload skipped"
else
  log "WARNING: no sshd_config.d; harden SSH manually"
fi

# ── repository ─────────────────────────────────────────────────────────
if [ -d "$INSTALL_ROOT/council-node/.git" ]; then
  log "repository already present; not touching the working tree"
else
  log "cloning repository"
  sudo -u "$SERVICE_USER" git clone --depth 1 "$REPO_URL" "$INSTALL_ROOT/council-node"
fi

# ── env scaffold (names only, never values) ────────────────────────────
ENV_FILE="$CONFIG_ROOT/council-node/service.env"
if [ ! -f "$ENV_FILE" ]; then
  install -m 0600 -o root -g "$SERVICE_USER" \
    "$INSTALL_ROOT/council-node/deploy/council-node/.env.example" "$ENV_FILE"
  log "wrote env template to $ENV_FILE — populate it before starting the service"
fi

log "bootstrap complete"
log "next: populate $ENV_FILE, then 'systemctl enable --now dominion-council-node'"

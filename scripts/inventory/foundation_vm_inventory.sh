#!/usr/bin/env bash
# Read-only inventory of foundation-vm.
#
# AUTHORIZED SCOPE: discovery only. This script performs no restart, no
# mutation, no deployment, no package installation, and no configuration
# change. Every command below either reads state or probes a health endpoint.
#
# It never prints a secret. Env files are examined for KEY NAMES ONLY, using a
# substitution that discards everything after the '=' before the line is ever
# echoed. No value is read into a variable, logged, or returned.
#
# It does not use `set -e`: a missing tool or an unreadable path is itself an
# inventory finding, and aborting on the first one would hide the rest.
set -uo pipefail

say()  { printf '%s\n' "$*"; }
head2() { printf '\n== %s ==\n' "$*"; }

say "FOUNDATION_VM_INVENTORY_BEGIN"
say "collected_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
say "hostname=$(hostname 2>/dev/null || echo UNKNOWN)"
say "uptime=$(uptime -p 2>/dev/null || echo UNKNOWN)"

# ── systemd units ──────────────────────────────────────────────────────
head2 "SYSTEMD SERVICES (running)"
if command -v systemctl >/dev/null 2>&1; then
  systemctl list-units --type=service --state=running --no-pager --plain 2>/dev/null \
    | awk 'NR>1 && $1 ~ /\.service$/ {print "  unit=" $1 " active=" $3 " sub=" $4}' \
    | head -60
else
  say "  systemctl: NOT AVAILABLE"
fi

head2 "SYSTEMD UNITS (dominion-*, any state)"
if command -v systemctl >/dev/null 2>&1; then
  systemctl list-units --all --no-pager --plain 'dominion-*' 2>/dev/null \
    | awk 'NR>1 && $1 ~ /dominion/ {print "  unit=" $1 " load=" $2 " active=" $3 " sub=" $4}' \
    | head -40
  systemctl list-timers --all --no-pager 2>/dev/null \
    | awk '/dominion/ {print "  timer=" $NF}' | head -20
fi

# ── containers ─────────────────────────────────────────────────────────
head2 "CONTAINERS"
if command -v docker >/dev/null 2>&1; then
  docker ps --format '  container={{.Names}} image={{.Image}} status={{.Status}} ports={{.Ports}}' 2>/dev/null \
    | head -40 || say "  docker: present but not queryable by this user"
else
  say "  docker: NOT AVAILABLE"
fi

# ── listening sockets ──────────────────────────────────────────────────
# -p is omitted deliberately: process names need elevation, and this script
# does not elevate. Ports plus health probes are enough to identify services.
head2 "LISTENING TCP PORTS"
if command -v ss >/dev/null 2>&1; then
  ss -tlnH 2>/dev/null | awk '{print "  listen=" $4}' | sort -u | head -50
elif command -v netstat >/dev/null 2>&1; then
  netstat -tln 2>/dev/null | awk 'NR>2 {print "  listen=" $4}' | sort -u | head -50
else
  say "  ss/netstat: NOT AVAILABLE"
fi

# ── health probes ──────────────────────────────────────────────────────
# The question this whole inventory exists to answer: which of the declared
# services are real, and on which ports.
head2 "HEALTH PROBES (loopback only)"
probe() {
  local port="$1" label="$2" path="${3:-/health}"
  local code
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 \
          "http://127.0.0.1:${port}${path}" 2>/dev/null)"
  if [ "$code" = "000" ] || [ -z "$code" ]; then
    say "  port=${port} label=${label} result=NO_RESPONSE"
  else
    say "  port=${port} label=${label} http=${code}"
  fi
}
probe 5060 conductor
probe 5050 alchemist
probe 9380 auricedge
probe 5000 gatekeeper
probe 5052 buddy_bridge
probe 5090 ascendant_store
probe 5112 dominion_publisher
probe 8790 revenue_runtime
probe 5678 n8n /healthz
probe 3000 dominion_web /
probe 8001 baby_api
probe 8090 wix_agent

# ── deployed revisions ─────────────────────────────────────────────────
head2 "DEPLOYED REVISIONS"
for dir in \
  "$HOME/.dominion/publisher/runtime/release" \
  "$HOME/.dominion/ascendant-store/runtime/release" \
  "$HOME/.dominion/revenue-runtime/runtime/release" \
  "$HOME/dominion" \
  "$HOME/dominion-ops" ; do
  if [ -d "$dir/.git" ]; then
    say "  path=$dir sha=$(git -C "$dir" rev-parse HEAD 2>/dev/null || echo UNKNOWN)"
  elif [ -d "$dir" ]; then
    say "  path=$dir sha=NOT_A_GIT_CHECKOUT"
  else
    say "  path=$dir ABSENT"
  fi
done

# ── configuration presence (NAMES ONLY, never values) ──────────────────
head2 "RUNTIME ENV FILES (key names only, values never read)"
for env_file in \
  "$HOME/.dominion/publisher/runtime.env" \
  "$HOME/.dominion/ascendant-store/runtime.env" \
  "$HOME/.dominion/revenue-runtime/runtime.env" \
  "$HOME/.env" ; do
  if [ -f "$env_file" ]; then
    perms="$(stat -c '%a' "$env_file" 2>/dev/null || echo '?')"
    # Everything after '=' is discarded by sed before this line is printed.
    names="$(sed -n 's/^\([A-Z_][A-Z0-9_]*\)=.*/\1/p' "$env_file" 2>/dev/null | tr '\n' ',' | sed 's/,$//')"
    say "  file=$env_file mode=$perms keys=[${names}]"
  else
    say "  file=$env_file ABSENT"
  fi
done

# ── reverse proxy ──────────────────────────────────────────────────────
head2 "REVERSE PROXY"
for caddy in /etc/caddy/Caddyfile "$HOME/Caddyfile"; do
  if [ -f "$caddy" ]; then
    say "  caddyfile=$caddy"
    grep -oE '^[a-z0-9.-]+\.[a-z]{2,}' "$caddy" 2>/dev/null | sed 's/^/    site=/' | head -20
    grep -oE 'reverse_proxy[[:space:]]+[^ ]+' "$caddy" 2>/dev/null | sed 's/^/    /' | head -20
  fi
done
command -v nginx >/dev/null 2>&1 && say "  nginx: present"

# ── database ───────────────────────────────────────────────────────────
head2 "POSTGRESQL"
if command -v psql >/dev/null 2>&1; then
  say "  psql: present ($(psql --version 2>/dev/null | head -1))"
else
  say "  psql: NOT AVAILABLE — the storefront requires it for orders"
fi

say ""
say "FOUNDATION_VM_INVENTORY_END"
say "MUTATIONS_PERFORMED=0"

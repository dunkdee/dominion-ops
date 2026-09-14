#!/usr/bin/env bash
# Bounded local transport adapter: Docker host-gateway IP :11434 -> the
# existing governed Ollama at 127.0.0.1:11434.
#
# WHY: DeerFlow deploy job 104183334060 built and started everything, then
# failed its capability proof on
#   http://host.docker.internal:11434/api/tags
#   ConnectionRefusedError: [Errno 111] Connection refused
# The error is ECONNREFUSED, not a DNS failure, so host.docker.internal
# already resolves inside the gateway -- nothing is listening on that
# address. This adds the missing listener and nothing else.
#
# THIS IS A NETWORK ADAPTER, NOT A MODEL SERVICE. It runs
# systemd-socket-proxyd, which forwards bytes. It does not load a model,
# does not serve inference, and is not a second model authority.
#
# NEVER, in any mode: modify or restart ollama.service, bind 0.0.0.0, bind
# a public interface, install any package, move Ollama into Docker, touch
# DeerFlow's configuration, or delete anything other than the two adapter
# unit files this script itself creates. The workflow gate greps for those.
#
# Two modes:
#   inspect (default, read-only) -- Phase 1 only. Creates nothing.
#   install -- Phases 2-4, with automatic rollback if any post-check fails.
set -uo pipefail

MODE="${1:-inspect}"

GATEWAY_CONTAINER="deer-flow-gateway"
OLLAMA_PORT=11434
LOOPBACK="127.0.0.1:${OLLAMA_PORT}"
REQUIRED_MODEL_PREFIX="llama3.1:8b"
SOCKET_UNIT="/etc/systemd/system/dominion-ollama-docker.socket"
SERVICE_UNIT="/etc/systemd/system/dominion-ollama-docker.service"

say()   { printf '%s\n' "$*"; }
head2() { printf '\n== %s ==\n' "$*"; }
die()   { say ""; say "RESULT=STOP reason=$*"; say "OLLAMA_DOCKER_BRIDGE_END"; exit 3; }

SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  sudo -n true 2>/dev/null && SUDO="sudo -n"
fi

say "OLLAMA_DOCKER_BRIDGE_BEGIN"
say "collected_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
say "hostname=$(hostname 2>/dev/null || echo UNKNOWN)"
say "mode=$MODE"

# ══ PHASE 1 — inspect ══════════════════════════════════════════════════
head2 "PHASE 1: GOVERNED OLLAMA HEALTH"
OLLAMA_ACTIVE="$(systemctl is-active ollama.service 2>/dev/null)"
say "  ollama.service is-active=$OLLAMA_ACTIVE"
[ "$OLLAMA_ACTIVE" = "active" ] || die "ollama.service is '$OLLAMA_ACTIVE', not active"

say "  -- systemctl cat ollama.service (recorded, never modified) --"
systemctl cat ollama.service 2>/dev/null | sed 's/^/    /'
# Fingerprint so the receipt can prove the unit was not touched.
OLLAMA_FRAGMENT="$(systemctl show ollama.service -p FragmentPath --value 2>/dev/null)"
OLLAMA_SHA_BEFORE="$($SUDO sha256sum "$OLLAMA_FRAGMENT" 2>/dev/null | awk '{print $1}')"
say "  ollama_unit_path=$OLLAMA_FRAGMENT"
say "  ollama_unit_sha256_before=${OLLAMA_SHA_BEFORE:-UNREADABLE}"

head2 "PHASE 1: LISTENERS ON ${OLLAMA_PORT} BEFORE"
$SUDO ss -ltnp 2>/dev/null | grep ":${OLLAMA_PORT}" | sed 's/^/    /' || say "    <none>"

head2 "PHASE 1: HOST LOOPBACK API"
if curl -fsS --max-time 10 "http://${LOOPBACK}/api/tags" >/dev/null 2>&1; then
  say "  loopback_api=PASS"
else
  die "governed Ollama is not answering on ${LOOPBACK}"
fi

head2 "PHASE 1: RESOLVE host.docker.internal FROM THE GATEWAY"
command -v docker >/dev/null 2>&1 || die "docker is not available"
$SUDO docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$GATEWAY_CONTAINER" \
  || die "container $GATEWAY_CONTAINER is not running"

RESOLVE_RAW="$($SUDO docker exec "$GATEWAY_CONTAINER" getent ahostsv4 host.docker.internal 2>&1)"
say "  -- getent ahostsv4 host.docker.internal --"
printf '%s\n' "$RESOLVE_RAW" | sed 's/^/    /'
HOST_GATEWAY_IP="$(printf '%s\n' "$RESOLVE_RAW" \
  | awk '/^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+/ {print $1; exit}')"
say "  HOST_GATEWAY_IP=${HOST_GATEWAY_IP:-UNRESOLVED}"
[ -n "$HOST_GATEWAY_IP" ] || die "could not resolve host.docker.internal from the gateway"

# Refuse anything that is not a private address, and refuse the wildcard
# outright, so this adapter can never be pointed at a public interface.
case "$HOST_GATEWAY_IP" in
  0.0.0.0|"") die "refusing to bind wildcard address" ;;
  10.*|192.168.*|172.1[6-9].*|172.2[0-9].*|172.3[0-1].*) say "  address_scope=PRIVATE (RFC1918) OK" ;;
  127.*) die "host.docker.internal resolved to loopback ($HOST_GATEWAY_IP); the adapter would bind the address it proxies to" ;;
  *) die "host.docker.internal resolved to $HOST_GATEWAY_IP, which is not an RFC1918 private address; refusing to bind it" ;;
esac

head2 "PHASE 1: CROSS-CHECK AGAINST HOST INTERFACES"
say "  -- docker network inspect bridge (gateway only) --"
$SUDO docker network inspect bridge --format '    bridge_gateway={{range .IPAM.Config}}{{.Gateway}}{{end}} subnet={{range .IPAM.Config}}{{.Subnet}}{{end}}' 2>&1
say "  -- ip addr (addresses only) --"
ip -4 -o addr show 2>/dev/null | awk '{print "    "$2" "$4}'
if ip -4 -o addr show 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | grep -qx "$HOST_GATEWAY_IP"; then
  say "  check_ip_is_a_local_host_address=PASS"
else
  die "$HOST_GATEWAY_IP is not configured on any local interface; refusing to bind it"
fi

head2 "PHASE 1: CONFIRM NOTHING ALREADY OWNS ${HOST_GATEWAY_IP}:${OLLAMA_PORT}"
if $SUDO ss -ltnH "sport = :${OLLAMA_PORT}" 2>/dev/null | awk '{print $4}' | grep -qx "${HOST_GATEWAY_IP}:${OLLAMA_PORT}"; then
  say "  existing_listener=PRESENT"
  ALREADY_BOUND=1
else
  say "  existing_listener=NONE (as expected -- this is the missing listener)"
  ALREADY_BOUND=0
fi

head2 "PHASE 1: LOCATE systemd-socket-proxyd"
PROXYD=""
for cand in "$(command -v systemd-socket-proxyd 2>/dev/null)" \
            /usr/lib/systemd/systemd-socket-proxyd \
            /lib/systemd/systemd-socket-proxyd; do
  [ -n "$cand" ] && [ -x "$cand" ] && { PROXYD="$cand"; break; }
done
say "  systemd_socket_proxyd=${PROXYD:-NOT FOUND}"
[ -n "$PROXYD" ] || die "systemd-socket-proxyd is unavailable; refusing to install any other proxy software"

head2 "PHASE 1: EXISTING ADAPTER UNITS"
for u in "$SOCKET_UNIT" "$SERVICE_UNIT"; do
  [ -f "$u" ] && say "  $u PRESENT" || say "  $u ABSENT"
done

if [ "$MODE" != "install" ]; then
  say ""
  say "  planned_socket_ListenStream=${HOST_GATEWAY_IP}:${OLLAMA_PORT}"
  say "  planned_service_ExecStart=$PROXYD ${LOOPBACK}"
  say "RESULT=INSPECTED_NOT_INSTALLED"
  say "ACTION_TAKEN=NONE (inspect mode)"
  say "OLLAMA_DOCKER_BRIDGE_END"
  exit 0
fi

# ══════════════════════════ INSTALL MODE ═══════════════════════════════

# Rollback is defined before anything is created, so it is always available.
rollback() {
  say ""
  head2 "ROLLBACK"
  $SUDO systemctl disable --now dominion-ollama-docker.socket 2>&1 | sed 's/^/    /' || true
  $SUDO systemctl stop dominion-ollama-docker.service 2>&1 | sed 's/^/    /' || true
  # The only deletions this script may perform: the two unit files it wrote.
  $SUDO rm -f "$SOCKET_UNIT" "$SERVICE_UNIT"
  $SUDO systemctl daemon-reload 2>&1 | sed 's/^/    /' || true
  say "  adapter units removed"
  if curl -fsS --max-time 10 "http://${LOOPBACK}/api/tags" >/dev/null 2>&1; then
    say "  rollback_ollama_loopback=PASS (governed Ollama healthy)"
  else
    say "  rollback_ollama_loopback=FAIL"
  fi
  say "  -- listeners after rollback --"
  $SUDO ss -ltnp 2>/dev/null | grep ":${OLLAMA_PORT}" | sed 's/^/    /' || say "    <none>"
}

[ "$ALREADY_BOUND" -eq 0 ] \
  || die "something already listens on ${HOST_GATEWAY_IP}:${OLLAMA_PORT}; refusing to contend for it"

# ══ PHASE 2 — create the reversible adapter ════════════════════════════
head2 "PHASE 2: WRITE ADAPTER UNITS"
$SUDO tee "$SOCKET_UNIT" >/dev/null <<UNIT
[Unit]
Description=Dominion Docker-only Ollama bridge
Before=dominion-ollama-docker.service

[Socket]
ListenStream=${HOST_GATEWAY_IP}:${OLLAMA_PORT}
# The docker0 address only exists once dockerd has created the bridge, and
# sockets.target is reached long before docker.service. Ordering After=
# docker.service would form a cycle (socket -> sockets.target ->
# basic.target -> docker.service), so IP_FREEBIND is the correct fix: the
# bind succeeds at boot even before the address is configured. It widens
# nothing -- this still binds exactly one RFC1918 address, never a wildcard.
FreeBind=true
NoDelay=true

[Install]
WantedBy=sockets.target
UNIT

$SUDO tee "$SERVICE_UNIT" >/dev/null <<UNIT
[Unit]
Description=Dominion Docker-to-loopback Ollama proxy
Requires=ollama.service
After=ollama.service

[Service]
ExecStart=${PROXYD} ${LOOPBACK}
PrivateTmp=true
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
UNIT

say "  -- $SOCKET_UNIT --"
$SUDO cat "$SOCKET_UNIT" | sed 's/^/    /'
say "  -- $SERVICE_UNIT --"
$SUDO cat "$SERVICE_UNIT" | sed 's/^/    /'

head2 "PHASE 2: ENABLE"
$SUDO systemctl daemon-reload 2>&1 | sed 's/^/    /'
if ! $SUDO systemctl enable --now dominion-ollama-docker.socket 2>&1 | sed 's/^/    /'; then
  rollback; die "could not enable the adapter socket"
fi
$SUDO systemctl status dominion-ollama-docker.socket --no-pager 2>&1 | head -12 | sed 's/^/    /'

# ══ PHASE 3 — prove both access paths ══════════════════════════════════
prove_paths() {  # $1 = label
  local label="$1" ok=0
  head2 "PROOF ($label): HOST LOOPBACK"
  if curl -fsS --max-time 10 "http://${LOOPBACK}/api/tags" >/dev/null 2>&1; then
    say "  host_loopback_api=PASS"
  else
    say "  host_loopback_api=FAIL"; ok=1
  fi

  head2 "PROOF ($label): DEERFLOW GATEWAY"
  # Resolve the interpreter ONCE up front. Chaining `python3 || python`
  # would re-run on an assertion failure with stdin already consumed by the
  # first attempt, turning a real failure into a confusing second error.
  local pybin out
  pybin="$($SUDO docker exec "$GATEWAY_CONTAINER" sh -lc \
    'command -v python3 || command -v python' 2>/dev/null | head -1 | tr -d '\r')"
  say "  gateway_python=${pybin:-NOT FOUND}"
  if [ -z "$pybin" ]; then
    say "  deerflow_gateway_api=FAIL (no python interpreter in the gateway)"
    return 1
  fi
  # Redirection belongs on the command line, before the heredoc body.
  out="$($SUDO docker exec -i "$GATEWAY_CONTAINER" "$pybin" - 2>&1 <<'PROOFPY'
import json, urllib.request
with urllib.request.urlopen(
    "http://host.docker.internal:11434/api/tags", timeout=10
) as response:
    data = json.load(response)
names = [str(x.get("name", "")) for x in data.get("models", [])]
assert any(x.startswith("llama3.1:8b") for x in names), names
print("MODELS_VISIBLE=" + ",".join(names))
print("DEERFLOW_OLLAMA_CONNECTIVITY=PASS")
PROOFPY
)"
  printf '%s\n' "$out" | sed 's/^/    /'
  printf '%s' "$out" | grep -q 'DEERFLOW_OLLAMA_CONNECTIVITY=PASS' \
    && say "  deerflow_gateway_api=PASS" \
    || { say "  deerflow_gateway_api=FAIL"; ok=1; }

  head2 "PROOF ($label): LISTENING SCOPE"
  local listeners
  listeners="$($SUDO ss -ltnp 2>/dev/null | grep ":${OLLAMA_PORT}")"
  printf '%s\n' "$listeners" | sed 's/^/    /'
  printf '%s' "$listeners" | grep -qE "(^|[[:space:]])127\.0\.0\.1:${OLLAMA_PORT}[[:space:]]" \
    && say "  scope_loopback_present=PASS" \
    || { say "  scope_loopback_present=FAIL"; ok=1; }
  printf '%s' "$listeners" | grep -qE "(^|[[:space:]])${HOST_GATEWAY_IP}:${OLLAMA_PORT}[[:space:]]" \
    && say "  scope_gateway_present=PASS" \
    || { say "  scope_gateway_present=FAIL"; ok=1; }
  if printf '%s' "$listeners" | grep -qE "(^|[[:space:]])(0\.0\.0\.0|\*):${OLLAMA_PORT}[[:space:]]"; then
    say "  scope_no_wildcard=FAIL (0.0.0.0 listener present)"; ok=1
  else
    say "  scope_no_wildcard=PASS"
  fi
  return "$ok"
}

if ! prove_paths "initial"; then
  rollback; die "post-install proof failed"
fi

# ══ PHASE 4 — persistence proof ════════════════════════════════════════
head2 "PHASE 4: RESTART THE ADAPTER ONLY"
say "  (the governed Ollama unit is left untouched)"
$SUDO systemctl restart dominion-ollama-docker.socket 2>&1 | sed 's/^/    /'
$SUDO systemctl status dominion-ollama-docker.socket --no-pager 2>&1 | head -12 | sed 's/^/    /'
say "  socket_enabled=$(systemctl is-enabled dominion-ollama-docker.socket 2>/dev/null)"
say "  socket_active=$(systemctl is-active dominion-ollama-docker.socket 2>/dev/null)"

if ! prove_paths "after restart"; then
  rollback; die "persistence proof failed after adapter restart"
fi

# ══ ollama.service must be byte-identical and never restarted ══════════
head2 "GOVERNED OLLAMA UNCHANGED"
OLLAMA_SHA_AFTER="$($SUDO sha256sum "$OLLAMA_FRAGMENT" 2>/dev/null | awk '{print $1}')"
say "  ollama_unit_sha256_after=${OLLAMA_SHA_AFTER:-UNREADABLE}"
if [ "$OLLAMA_SHA_BEFORE" = "$OLLAMA_SHA_AFTER" ]; then
  say "  ollama_unit_unchanged=PASS"
else
  rollback; die "ollama.service unit file changed during this run"
fi
say "  ollama_active=$(systemctl is-active ollama.service 2>/dev/null)"
say "  ollama_main_pid=$(systemctl show ollama.service -p MainPID --value 2>/dev/null)"
say "  ollama_since=$(systemctl show ollama.service -p ActiveEnterTimestamp --value 2>/dev/null)"

say ""
say "OLLAMA_DOCKER_BRIDGE_ADAPTER=PASS"
say "OLLAMA_DOCKER_BRIDGE_END"
say "MUTATIONS_KIND=create_two_adapter_units,enable_adapter_socket"

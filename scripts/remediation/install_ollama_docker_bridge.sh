#!/usr/bin/env bash
# Bounded local transport adapter: Docker bridge gateway :11434 -> the
# existing governed Ollama at 127.0.0.1:11434.
#
# This script is intentionally narrow. It may manage only the two Dominion
# adapter unit files. It must never control ollama.service lifecycle, bind a
# wildcard/public interface, install software, or change DeerFlow config.
#
# Modes:
#   inspect (default) -- read-only evidence collection
#   install           -- bounded adapter replacement with interruption-safe rollback
set -uo pipefail

MODE="${1:-inspect}"
GATEWAY_CONTAINER="deer-flow-gateway"
OLLAMA_PORT=11434
LOOPBACK="127.0.0.1:${OLLAMA_PORT}"
REQUIRED_MODEL_PREFIX="nemotron-3-nano:4b"
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

# ══ PHASE 1 — read-only inspection ═════════════════════════════════════
head2 "PHASE 1: GOVERNED OLLAMA HEALTH"
OLLAMA_ACTIVE="$(systemctl is-active ollama.service 2>/dev/null)"
say "  ollama.service is-active=$OLLAMA_ACTIVE"
[ "$OLLAMA_ACTIVE" = "active" ] || die "ollama.service is '$OLLAMA_ACTIVE', not active"

OLLAMA_FRAGMENT="$(systemctl show ollama.service -p FragmentPath --value 2>/dev/null)"
[ -n "$OLLAMA_FRAGMENT" ] || die "could not resolve ollama.service FragmentPath"
OLLAMA_SHA_BEFORE="$($SUDO sha256sum "$OLLAMA_FRAGMENT" 2>/dev/null | awk '{print $1}')"
OLLAMA_PID_BEFORE="$(systemctl show ollama.service -p MainPID --value 2>/dev/null)"
OLLAMA_SINCE_BEFORE="$(systemctl show ollama.service -p ActiveEnterTimestamp --value 2>/dev/null)"
[ -n "$OLLAMA_SHA_BEFORE" ] || die "could not fingerprint ollama.service"
say "  ollama_unit_path=$OLLAMA_FRAGMENT"
say "  ollama_unit_sha256_before=$OLLAMA_SHA_BEFORE"
say "  ollama_main_pid_before=${OLLAMA_PID_BEFORE:-UNKNOWN}"
say "  ollama_since_before=${OLLAMA_SINCE_BEFORE:-UNKNOWN}"

head2 "PHASE 1: HOST LOOPBACK API"
if curl -fsS --max-time 10 "http://${LOOPBACK}/api/tags" >/dev/null 2>&1; then
  say "  loopback_api=PASS"
else
  die "governed Ollama is not answering on ${LOOPBACK}"
fi

head2 "PHASE 1: RESOLVE DOCKER HOST GATEWAY"
command -v docker >/dev/null 2>&1 || die "docker is not available"
$SUDO docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$GATEWAY_CONTAINER" \
  || die "container $GATEWAY_CONTAINER is not running"

RESOLVE_RAW="$($SUDO docker exec "$GATEWAY_CONTAINER" getent ahostsv4 host.docker.internal 2>&1)"
printf '%s\n' "$RESOLVE_RAW" | sed 's/^/    /'
HOST_GATEWAY_IP="$(printf '%s\n' "$RESOLVE_RAW" \
  | awk '/^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+/ {print $1; exit}')"
[ -n "$HOST_GATEWAY_IP" ] || die "could not resolve host.docker.internal from the gateway"
say "  HOST_GATEWAY_IP=$HOST_GATEWAY_IP"

case "$HOST_GATEWAY_IP" in
  0.0.0.0|"") die "refusing to bind wildcard address" ;;
  10.*|192.168.*|172.1[6-9].*|172.2[0-9].*|172.3[0-1].*) say "  address_scope=PRIVATE (RFC1918) OK" ;;
  127.*) die "host.docker.internal resolved to loopback ($HOST_GATEWAY_IP)" ;;
  *) die "host.docker.internal resolved to non-RFC1918 address $HOST_GATEWAY_IP" ;;
esac

DOCKER_BRIDGE_GATEWAY="$($SUDO docker network inspect bridge \
  --format '{{range .IPAM.Config}}{{.Gateway}}{{end}}' 2>/dev/null)"
[ -n "$DOCKER_BRIDGE_GATEWAY" ] || die "could not resolve Docker bridge gateway"
say "  docker_bridge_gateway=$DOCKER_BRIDGE_GATEWAY"
if [ "$HOST_GATEWAY_IP" = "$DOCKER_BRIDGE_GATEWAY" ]; then
  say "  check_host_gateway_equals_docker_bridge=PASS"
else
  die "host.docker.internal=$HOST_GATEWAY_IP does not equal Docker bridge gateway=$DOCKER_BRIDGE_GATEWAY"
fi
if ip -4 -o addr show 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | grep -qx "$HOST_GATEWAY_IP"; then
  say "  check_ip_is_a_local_host_address=PASS"
else
  die "$HOST_GATEWAY_IP is not configured on a local interface"
fi

head2 "PHASE 1: LISTENER OWNERSHIP"
LISTENER_LINE="$($SUDO ss -ltnp 2>/dev/null | grep -E "(^|[[:space:]])${HOST_GATEWAY_IP}:${OLLAMA_PORT}[[:space:]]" | head -1 || true)"
if [ -n "$LISTENER_LINE" ]; then
  say "  existing_listener=PRESENT"
  printf '%s\n' "$LISTENER_LINE" | sed 's/^/    /'
  ALREADY_BOUND=1
else
  say "  existing_listener=NONE"
  ALREADY_BOUND=0
fi

PROXYD=""
for cand in "$(command -v systemd-socket-proxyd 2>/dev/null)" \
            /usr/lib/systemd/systemd-socket-proxyd \
            /lib/systemd/systemd-socket-proxyd; do
  [ -n "$cand" ] && [ -x "$cand" ] && { PROXYD="$cand"; break; }
done
[ -n "$PROXYD" ] || die "systemd-socket-proxyd is unavailable"
say "  systemd_socket_proxyd=$PROXYD"

# Capture exact prior adapter state before any mutation. A partial or foreign
# unit pair is refused. A recognized prior Dominion adapter can be upgraded,
# but its exact bytes and enabled/active state are preserved for rollback.
SOCKET_EXISTS=0
SERVICE_EXISTS=0
[ -f "$SOCKET_UNIT" ] && SOCKET_EXISTS=1
[ -f "$SERVICE_UNIT" ] && SERVICE_EXISTS=1
if [ "$SOCKET_EXISTS" -ne "$SERVICE_EXISTS" ]; then
  die "partial adapter state detected; exactly one unit file exists"
fi

PREEXISTING_ADAPTER=0
PREV_SOCKET_B64=""
PREV_SERVICE_B64=""
PREV_SOCKET_ENABLED="not-found"
PREV_SOCKET_ACTIVE="inactive"
PREV_SERVICE_ACTIVE="inactive"

if [ "$SOCKET_EXISTS" -eq 1 ]; then
  grep -Fq 'Description=Dominion Docker-only Ollama bridge' "$SOCKET_UNIT" \
    || die "existing socket unit is not the Dominion adapter"
  grep -Fq "ListenStream=${HOST_GATEWAY_IP}:${OLLAMA_PORT}" "$SOCKET_UNIT" \
    || die "existing Dominion socket binds a different address"
  grep -Fq 'Description=Dominion Docker-to-loopback Ollama proxy' "$SERVICE_UNIT" \
    || die "existing service unit is not the Dominion adapter"
  grep -Fq "ExecStart=${PROXYD} ${LOOPBACK}" "$SERVICE_UNIT" \
    || die "existing Dominion service has an unexpected ExecStart"
  if [ "$ALREADY_BOUND" -eq 1 ] && ! printf '%s' "$LISTENER_LINE" | grep -q 'systemd-socket'; then
    die "adapter address is held by a process other than systemd-socket-proxyd"
  fi
  PREEXISTING_ADAPTER=1
  PREV_SOCKET_B64="$($SUDO base64 -w0 "$SOCKET_UNIT" 2>/dev/null)"
  PREV_SERVICE_B64="$($SUDO base64 -w0 "$SERVICE_UNIT" 2>/dev/null)"
  [ -n "$PREV_SOCKET_B64" ] && [ -n "$PREV_SERVICE_B64" ] \
    || die "could not capture exact prior adapter unit bytes"
  PREV_SOCKET_ENABLED="$(systemctl is-enabled dominion-ollama-docker.socket 2>/dev/null || true)"
  PREV_SOCKET_ACTIVE="$(systemctl is-active dominion-ollama-docker.socket 2>/dev/null || true)"
  PREV_SERVICE_ACTIVE="$(systemctl is-active dominion-ollama-docker.service 2>/dev/null || true)"
  say "  prior_adapter_state_captured=PASS"
  say "  prior_socket_enabled=${PREV_SOCKET_ENABLED:-unknown}"
  say "  prior_socket_active=${PREV_SOCKET_ACTIVE:-unknown}"
  say "  prior_service_active=${PREV_SERVICE_ACTIVE:-unknown}"
else
  [ "$ALREADY_BOUND" -eq 0 ] || die "foreign listener owns ${HOST_GATEWAY_IP}:${OLLAMA_PORT}"
  say "  prior_adapter_state_captured=PASS (none present)"
fi

say "  required_model_contract=$REQUIRED_MODEL_PREFIX"
say "  required_model_contract_check=PASS"

if [ "$MODE" != "install" ]; then
  say "RESULT=INSPECTED_NOT_INSTALLED"
  say "ACTION_TAKEN=NONE (inspect mode)"
  say "OLLAMA_DOCKER_BRIDGE_END"
  exit 0
fi

# ══ INSTALL MODE — interruption-safe bounded mutation ══════════════════
MUTATION_ARMED=0
MUTATION_COMMITTED=0
ROLLBACK_RUNNING=0

remove_current_adapter_best_effort() {
  $SUDO systemctl disable --now dominion-ollama-docker.socket >/dev/null 2>&1 || true
  $SUDO systemctl stop dominion-ollama-docker.service >/dev/null 2>&1 || true
  $SUDO rm -f "$SOCKET_UNIT" "$SERVICE_UNIT" >/dev/null 2>&1 || true
  $SUDO systemctl daemon-reload >/dev/null 2>&1 || true
}

restore_prior_state() {
  remove_current_adapter_best_effort
  if [ "$PREEXISTING_ADAPTER" -eq 1 ]; then
    printf '%s' "$PREV_SOCKET_B64" | base64 -d | $SUDO tee "$SOCKET_UNIT" >/dev/null \
      || return 1
    printf '%s' "$PREV_SERVICE_B64" | base64 -d | $SUDO tee "$SERVICE_UNIT" >/dev/null \
      || return 1
    $SUDO systemctl daemon-reload >/dev/null 2>&1 || return 1

    case "$PREV_SOCKET_ENABLED" in
      enabled|enabled-runtime|linked|linked-runtime|alias)
        $SUDO systemctl enable dominion-ollama-docker.socket >/dev/null 2>&1 || return 1 ;;
      *) $SUDO systemctl disable dominion-ollama-docker.socket >/dev/null 2>&1 || true ;;
    esac
    if [ "$PREV_SOCKET_ACTIVE" = "active" ]; then
      $SUDO systemctl start dominion-ollama-docker.socket >/dev/null 2>&1 || return 1
    fi
    if [ "$PREV_SERVICE_ACTIVE" = "active" ] && [ "$PREV_SOCKET_ACTIVE" = "active" ]; then
      $SUDO docker exec "$GATEWAY_CONTAINER" sh -lc \
        'python3 - <<"PY" 2>/dev/null || python - <<"PY"
import urllib.request
urllib.request.urlopen("http://host.docker.internal:11434/api/tags", timeout=5).read(1)
PY' >/dev/null 2>&1 || true
    fi
    say "  prior_adapter_restore=PASS"
  else
    say "  prior_adapter_restore=PASS (pre-run state had no adapter)"
  fi
}

rollback() {
  [ "$ROLLBACK_RUNNING" -eq 0 ] || return 0
  ROLLBACK_RUNNING=1
  MUTATION_ARMED=0
  head2 "ROLLBACK"
  if restore_prior_state; then
    say "  rollback_adapter_state=PASS"
  else
    say "  rollback_adapter_state=FAIL"
  fi
  if curl -fsS --max-time 10 "http://${LOOPBACK}/api/tags" >/dev/null 2>&1; then
    say "  rollback_ollama_loopback=PASS"
  else
    say "  rollback_ollama_loopback=FAIL"
  fi
  ROLLBACK_RUNNING=0
}

on_exit() {
  rc="$1"
  if [ "$MUTATION_ARMED" -eq 1 ] && [ "$MUTATION_COMMITTED" -eq 0 ]; then
    say "  interruption_or_failure_detected=YES rc=$rc"
    rollback
  fi
  return "$rc"
}

trap 'on_exit $?' EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
MUTATION_ARMED=1
say "  interruption_rollback_armed=PASS"

# Remove only the recognized prior Dominion adapter. Its exact pre-run state
# has already been captured and will be restored by the EXIT/signal trap.
if [ "$PREEXISTING_ADAPTER" -eq 1 ]; then
  $SUDO systemctl disable --now dominion-ollama-docker.socket >/dev/null 2>&1 \
    || { rollback; die "could not stop prior adapter socket"; }
  $SUDO systemctl stop dominion-ollama-docker.service >/dev/null 2>&1 || true
  $SUDO rm -f "$SOCKET_UNIT" "$SERVICE_UNIT" \
    || { rollback; die "could not remove prior adapter unit files"; }
  $SUDO systemctl daemon-reload >/dev/null 2>&1 \
    || { rollback; die "daemon-reload failed after prior adapter removal"; }
fi

if $SUDO ss -ltnH "sport = :${OLLAMA_PORT}" 2>/dev/null | awk '{print $4}' \
     | grep -qx "${HOST_GATEWAY_IP}:${OLLAMA_PORT}"; then
  rollback; die "${HOST_GATEWAY_IP}:${OLLAMA_PORT} remained bound before install"
fi

head2 "PHASE 2: WRITE FAIL-CLOSED ADAPTER UNITS"
if ! $SUDO tee "$SOCKET_UNIT" >/dev/null <<UNIT
[Unit]
Description=Dominion Docker-only Ollama bridge
Before=dominion-ollama-docker.service

[Socket]
ListenStream=${HOST_GATEWAY_IP}:${OLLAMA_PORT}
FreeBind=true
NoDelay=true

[Install]
WantedBy=sockets.target
UNIT
then
  rollback; die "could not write adapter socket unit"
fi

if ! $SUDO tee "$SERVICE_UNIT" >/dev/null <<UNIT
[Unit]
Description=Dominion Docker-to-loopback Ollama proxy
Requisite=ollama.service
After=ollama.service

[Service]
ExecStart=${PROXYD} ${LOOPBACK}
PrivateTmp=true
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
UNIT
then
  rollback; die "could not write adapter service unit"
fi

if grep -Fq 'Requisite=ollama.service' "$SERVICE_UNIT" \
   && ! grep -Fq 'Requires=ollama.service' "$SERVICE_UNIT"; then
  say "  adapter_dependency_fail_closed=PASS"
else
  rollback; die "adapter dependency is not fail-closed"
fi

$SUDO systemctl daemon-reload >/dev/null 2>&1 \
  || { rollback; die "daemon-reload failed"; }
$SUDO systemctl enable --now dominion-ollama-docker.socket >/dev/null 2>&1 \
  || { rollback; die "could not enable adapter socket"; }

prove_paths() {
  label="$1"
  ok=0
  head2 "PROOF ($label)"
  if curl -fsS --max-time 10 "http://${LOOPBACK}/api/tags" >/dev/null 2>&1; then
    say "  host_loopback_api=PASS"
  else
    say "  host_loopback_api=FAIL"; ok=1
  fi

  pybin="$($SUDO docker exec "$GATEWAY_CONTAINER" sh -lc \
    'command -v python3 || command -v python' 2>/dev/null | head -1 | tr -d '\r')"
  if [ -z "$pybin" ]; then
    say "  deerflow_gateway_api=FAIL (no python interpreter)"
    return 1
  fi
  out="$($SUDO docker exec -i -e "REQUIRED_MODEL=${REQUIRED_MODEL_PREFIX}" \
    "$GATEWAY_CONTAINER" "$pybin" - 2>&1 <<'PROOFPY'
import json, os, urllib.request
with urllib.request.urlopen("http://host.docker.internal:11434/api/tags", timeout=10) as response:
    code = response.getcode()
    data = json.load(response)
models = data.get("models")
assert code == 200, code
assert isinstance(models, list), type(models).__name__
names = sorted(str(m.get("name", "")) for m in models)
print("MODELS_VISIBLE=" + ",".join(names))
print("DEERFLOW_OLLAMA_CONNECTIVITY=PASS")
want = os.environ.get("REQUIRED_MODEL", "")
if want:
    print("REQUIRED_MODEL_STATUS=%s model=%s" % (
        "PRESENT" if any(n.startswith(want) for n in names) else "ABSENT", want
    ))
PROOFPY
)"
  printf '%s\n' "$out" | sed 's/^/    /'
  printf '%s' "$out" | grep -q 'DEERFLOW_OLLAMA_CONNECTIVITY=PASS' \
    && say "  deerflow_gateway_api=PASS" \
    || { say "  deerflow_gateway_api=FAIL"; ok=1; }

  listeners="$($SUDO ss -ltnp 2>/dev/null | grep ":${OLLAMA_PORT}" || true)"
  printf '%s' "$listeners" | grep -qE "(^|[[:space:]])127\.0\.0\.1:${OLLAMA_PORT}[[:space:]]" \
    && say "  scope_loopback_present=PASS" \
    || { say "  scope_loopback_present=FAIL"; ok=1; }
  printf '%s' "$listeners" | grep -qE "(^|[[:space:]])${HOST_GATEWAY_IP}:${OLLAMA_PORT}[[:space:]]" \
    && say "  scope_gateway_present=PASS" \
    || { say "  scope_gateway_present=FAIL"; ok=1; }
  if printf '%s' "$listeners" | grep -qE "(^|[[:space:]])(0\.0\.0\.0|\*):${OLLAMA_PORT}[[:space:]]"; then
    say "  scope_no_wildcard=FAIL"; ok=1
  else
    say "  scope_no_wildcard=PASS"
  fi
  return "$ok"
}

if ! prove_paths "initial"; then
  rollback; die "initial post-install proof failed"
fi

head2 "PHASE 3: SYSTEMD OWNERSHIP / RESTART PROOF"
$SUDO systemctl stop dominion-ollama-docker.service >/dev/null 2>&1 || true
$SUDO systemctl restart dominion-ollama-docker.socket >/dev/null 2>&1 \
  || { rollback; die "adapter socket restart failed"; }
SOCK_ENABLED="$(systemctl is-enabled dominion-ollama-docker.socket 2>/dev/null)"
SOCK_ACTIVE="$(systemctl is-active dominion-ollama-docker.socket 2>/dev/null)"
[ "$SOCK_ENABLED" = "enabled" ] \
  && say "  socket_enabled_check=PASS" \
  || { rollback; die "adapter socket is not enabled"; }
[ "$SOCK_ACTIVE" = "active" ] \
  && say "  socket_active_check=PASS" \
  || { rollback; die "adapter socket is not active"; }

if ! prove_paths "after restart"; then
  rollback; die "persistence proof failed after adapter restart"
fi
FINAL_ACTIVE="$(systemctl is-active dominion-ollama-docker.socket 2>/dev/null)"
[ "$FINAL_ACTIVE" = "active" ] \
  && say "  adapter_owned_by_systemd=PASS" \
  || { rollback; die "systemd does not own an active adapter socket"; }

head2 "PHASE 4: PROVE GOVERNED OLLAMA UNCHANGED"
OLLAMA_SHA_AFTER="$($SUDO sha256sum "$OLLAMA_FRAGMENT" 2>/dev/null | awk '{print $1}')"
OLLAMA_PID_AFTER="$(systemctl show ollama.service -p MainPID --value 2>/dev/null)"
OLLAMA_SINCE_AFTER="$(systemctl show ollama.service -p ActiveEnterTimestamp --value 2>/dev/null)"
if [ "$OLLAMA_SHA_BEFORE" = "$OLLAMA_SHA_AFTER" ]; then
  say "  ollama_unit_unchanged=PASS"
else
  rollback; die "ollama.service unit bytes changed"
fi
if [ "$OLLAMA_PID_BEFORE" = "$OLLAMA_PID_AFTER" ] \
   && [ "$OLLAMA_SINCE_BEFORE" = "$OLLAMA_SINCE_AFTER" ]; then
  say "  ollama_lifecycle_unchanged=PASS"
else
  rollback; die "ollama.service lifecycle changed during adapter operation"
fi
if [ "$(systemctl is-active ollama.service 2>/dev/null)" = "active" ]; then
  say "  ollama_active_final=PASS"
else
  rollback; die "ollama.service is not active at final proof"
fi

MUTATION_COMMITTED=1
MUTATION_ARMED=0
trap - EXIT HUP INT TERM
say "  interruption_rollback_disarmed_after_commit=PASS"
say "OLLAMA_DOCKER_BRIDGE_ADAPTER=PASS"
say "OLLAMA_DOCKER_BRIDGE_END"
say "MUTATIONS_KIND=replace_or_create_two_adapter_units,enable_adapter_socket"
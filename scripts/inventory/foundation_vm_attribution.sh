#!/usr/bin/env bash
# Read-only attribution pass over foundation-vm.
#
# AUTHORIZED SCOPE: identification only. This script answers "what owns this
# listener, and why did that unit fail". It performs no service lifecycle
# change, no mutation, no deployment, no package installation, no firewall
# change and no configuration change. Every command reads state.
#
# Written for the questions the 2026-09-10 inventory (run 34448533182) could
# not answer, because that run deliberately omitted process-to-port mapping.
#
# SECRET HANDLING
#   * Process environments are reduced to KEY NAMES ONLY before printing.
#   * Unit files, command lines and journal lines pass through redact(), which
#     blanks the value of any assignment whose name looks like a credential.
#   * No file is printed whole except unit definitions, post-redaction.
#
# It does not use `set -e`: an unreadable path is itself a finding, and
# aborting on the first one would hide the rest.
set -uo pipefail

say()   { printf '%s\n' "$*"; }
head2() { printf '\n== %s ==\n' "$*"; }

# Blank the value of anything that names itself a credential, and any bearer
# token, before the line is echoed.
redact() {
  sed -E \
    -e 's/([A-Za-z_][A-Za-z0-9_]*(SECRET|TOKEN|KEY|PASSWORD|PASSWD|PASS|AUTH|CREDENTIAL|WEBHOOK|SID)[A-Za-z0-9_]*)=[^[:space:]"'"'"']*/\1=<redacted>/gi' \
    -e 's/(--?(token|key|secret|password|auth)[= ])[^[:space:]]+/\1<redacted>/gi' \
    -e 's/(Bearer|Basic)[[:space:]]+[A-Za-z0-9._~+\/-]+=*/\1 <redacted>/gi'
}

# sudo without a prompt. Absent privilege is a finding, never a hang.
SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  if sudo -n true 2>/dev/null; then SUDO="sudo -n"; fi
fi

say "FOUNDATION_VM_ATTRIBUTION_BEGIN"
say "collected_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
say "hostname=$(hostname 2>/dev/null || echo UNKNOWN)"
if [ "$(id -u)" -eq 0 ] || [ -n "$SUDO" ]; then PRIV=YES; else PRIV=NO; fi
say "privileged=$PRIV"

# ── full listener attribution ──────────────────────────────────────────
# One pass maps every listening socket to its process. Without privilege the
# kernel hides other users' sockets, so the header records which it was.
head2 "LISTENER TO PROCESS MAP"
if command -v ss >/dev/null 2>&1; then
  $SUDO ss -tlnpH 2>/dev/null | redact | sed 's/^/  /'
else
  say "  ss: NOT AVAILABLE"
fi

# ── deep dive on the ports under question ──────────────────────────────
# 11435  contained Nemotron port, listener present, owner unproven
# 5090   storefront already serving with no governed release directory
# 8200   collides with the Council Node bind port
# 8091   the integrity agent's own canonical truth source
# 5050   Alchemist, no health contract
# 9380   AuricEdge, no health contract, binds all interfaces
for PORT in 11435 5090 8200 8091 5050 9380; do
  head2 "PORT $PORT"

  pids="$($SUDO ss -tlnpH "sport = :$PORT" 2>/dev/null \
          | grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u)"
  bind="$($SUDO ss -tlnH "sport = :$PORT" 2>/dev/null | awk '{print $4}' | sort -u | tr '\n' ' ')"
  say "  bind_addresses=${bind:-NONE}"

  if [ -z "$pids" ]; then
    say "  owner=UNRESOLVED (no pid returned; privileged=$PRIV)"
    continue
  fi

  for pid in $pids; do
    say "  pid=$pid"
    say "    user=$(ps -o user= -p "$pid" 2>/dev/null | tr -d ' ')"
    say "    ppid=$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ')"
    say "    started=$(ps -o lstart= -p "$pid" 2>/dev/null)"
    say "    elapsed=$(ps -o etime= -p "$pid" 2>/dev/null | tr -d ' ')"
    say "    cmdline=$($SUDO tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null | redact)"
    exe="$($SUDO readlink -f "/proc/$pid/exe" 2>/dev/null)"
    say "    exe=${exe:-UNREADABLE}"
    say "    cwd=$($SUDO readlink -f "/proc/$pid/cwd" 2>/dev/null || echo UNREADABLE)"
    if [ -n "$exe" ] && [ -r "$exe" ]; then
      say "    exe_sha256=$($SUDO sha256sum "$exe" 2>/dev/null | awk '{print $1}')"
    else
      say "    exe_sha256=UNREADABLE"
    fi
    # cgroup names the systemd unit or docker container that owns the process.
    say "    cgroup=$($SUDO cat "/proc/$pid/cgroup" 2>/dev/null | tr '\n' '|' || echo UNREADABLE)"
    # KEY NAMES ONLY. Values are discarded before anything is printed.
    say "    env_keys=$($SUDO tr '\0' '\n' < "/proc/$pid/environ" 2>/dev/null \
                        | sed -n 's/^\([A-Za-z_][A-Za-z0-9_]*\)=.*/\1/p' | sort | tr '\n' ',')"
    # Parent, which tells apart a systemd-supervised unit from a stray child.
    ppid="$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ')"
    if [ -n "$ppid" ] && [ "$ppid" != "0" ]; then
      say "    parent_cmd=$(ps -o args= -p "$ppid" 2>/dev/null | redact)"
    fi
  done
done

# ── Nemotron: does the unit that was contained still exist ─────────────
head2 "NEMOTRON UNIT STATE"
if command -v systemctl >/dev/null 2>&1; then
  systemctl list-unit-files --no-pager --plain 2>/dev/null \
    | grep -i nemotron | sed 's/^/  unit_file: /' || say "  unit_file: NONE MATCHING"
  for u in dominion-nemotron.service nemotron.service nemotron-worker.service; do
    say "  $u -> $(systemctl show "$u" -p LoadState --value 2>/dev/null || echo UNKNOWN)/$(systemctl show "$u" -p ActiveState --value 2>/dev/null)/$(systemctl show "$u" -p UnitFileState --value 2>/dev/null)"
  done
fi
say "  fragment_paths:"
ls -la /etc/systemd/system/*nemotron* /lib/systemd/system/*nemotron* 2>/dev/null | sed 's/^/    /' \
  || say "    none on disk"

# ── the integrity agent: why is it failed ──────────────────────────────
INTEG=dominion-system-integrity.service
head2 "INTEGRITY AGENT STATUS"
systemctl status "$INTEG" --no-pager -l 2>/dev/null | redact | sed 's/^/  /'

head2 "INTEGRITY AGENT PROPERTIES"
systemctl show "$INTEG" --no-pager 2>/dev/null \
  | grep -E '^(LoadState|ActiveState|SubState|UnitFileState|Result|ExecMainStatus|ExecMainCode|ExecMainStartTimestamp|ExecMainExitTimestamp|ActiveEnterTimestamp|ActiveExitTimestamp|InactiveEnterTimestamp|StateChangeTimestamp|NRestarts|Requires|Wants|After|FragmentPath|ConditionResult|AssertResult|TriggeredBy)=' \
  | redact | sed 's/^/  /'

head2 "INTEGRITY AGENT UNIT DEFINITION"
systemctl cat "$INTEG" 2>/dev/null | redact | sed 's/^/  /'
systemctl cat dominion-system-integrity.timer 2>/dev/null | redact | sed 's/^/  /'

head2 "INTEGRITY AGENT TIMER STATE"
systemctl list-timers --all --no-pager 2>/dev/null | grep -i integrity | sed 's/^/  /' \
  || say "  no timer row"

# Oldest first: the FIRST failure is what explains the rest.
head2 "INTEGRITY AGENT JOURNAL (oldest 120 lines held)"
$SUDO journalctl -u "$INTEG" --no-pager -o short-iso 2>/dev/null \
  | head -120 | redact | sed 's/^/  /' || say "  journal: UNREADABLE"

head2 "INTEGRITY AGENT JOURNAL (newest 120 lines)"
$SUDO journalctl -u "$INTEG" --no-pager -o short-iso 2>/dev/null \
  | tail -120 | redact | sed 's/^/  /' || say "  journal: UNREADABLE"

head2 "INTEGRITY AGENT FAILURE BOUNDARY"
# The last line that looks like success, and the first that looks like failure.
$SUDO journalctl -u "$INTEG" --no-pager -o short-iso 2>/dev/null \
  | grep -nEi 'pass|ok=|success|complete' | tail -5 | redact | sed 's/^/  last_success: /'
$SUDO journalctl -u "$INTEG" --no-pager -o short-iso 2>/dev/null \
  | grep -nEi 'fail|error|traceback|refused|timeout|denied|no such' | head -20 | redact | sed 's/^/  first_failure: /'

# ── receipts the agent writes, names and times only ────────────────────
head2 "INTEGRITY RECEIPTS (names and times only)"
for d in "$HOME/.dominion/system-integrity" "$HOME/.dominion/receipts" \
         /var/lib/dominion/system-integrity /var/log/dominion; do
  if [ -d "$d" ]; then
    say "  dir=$d"
    ls -lat "$d" 2>/dev/null | head -8 | sed 's/^/    /'
  else
    say "  dir=$d ABSENT"
  fi
done

# ── storefront on 5090: what is actually serving ───────────────────────
head2 "STOREFRONT UNIT DEFINITIONS"
for u in ascendant-store.service dominion-store.service; do
  say "  --- $u ---"
  systemctl show "$u" --no-pager 2>/dev/null \
    | grep -E '^(FragmentPath|ExecStart|WorkingDirectory|User|Group|EnvironmentFiles|ActiveState|SubState|ActiveEnterTimestamp)=' \
    | redact | sed 's/^/    /'
done

head2 "STOREFRONT SOURCE TREES"
for d in "$HOME/.dominion/ascendant-store/runtime/release" "$HOME/dominion-ops/ascendant_store" \
         "$HOME/dominion/ascendant_store" "$HOME/ascendant_store"; do
  if [ -d "$d" ]; then
    sha="$(git -C "$d" rev-parse HEAD 2>/dev/null || echo NOT_A_GIT_CHECKOUT)"
    say "  path=$d sha=$sha files=$(find "$d" -maxdepth 1 -type f 2>/dev/null | wc -l)"
  else
    say "  path=$d ABSENT"
  fi
done

head2 "STOREFRONT ROUTES"
for path in / /health /healthz /products /policies /success; do
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://127.0.0.1:5090$path" 2>/dev/null)"
  [ "$code" = "000" ] && code=NO_RESPONSE
  say "  GET $path -> ${code:-NO_RESPONSE}"
done

head2 "CADDY MAPPING FOR THE STOREFRONT PORTS"
# Site headers and numeric upstreams only. No directive bodies are printed.
$SUDO grep -nE '^[a-z0-9.]+\.dominionhealing\.org|reverse_proxy[[:space:]]+127\.0\.0\.1:(5080|5090|5120|8200|8091)' \
  /etc/caddy/Caddyfile 2>/dev/null | sed 's/^/  /' || say "  Caddyfile: UNREADABLE"

# ── command centre truth source on 8091 ────────────────────────────────
head2 "COMMAND CENTER CONTAINER PORTS"
if command -v docker >/dev/null 2>&1; then
  docker inspect dominion-command-center \
    --format '  network_mode={{.HostConfig.NetworkMode}} ports={{.NetworkSettings.Ports}}' 2>/dev/null \
    || say "  docker inspect: UNAVAILABLE"
fi
cc_code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:8091/api/status 2>/dev/null)"
say "  probe 8091/api/status -> ${cc_code:-NO_RESPONSE}"

say ""
say "FOUNDATION_VM_ATTRIBUTION_END"
say "MUTATIONS_PERFORMED=0"

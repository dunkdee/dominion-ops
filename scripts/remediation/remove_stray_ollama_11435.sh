#!/usr/bin/env bash
# Remove the unmanaged second `ollama serve` occupying TCP 11435.
#
# AUTHORIZED SCOPE: terminate exactly one process, and only if it still matches
# the full fingerprint recorded in evidence/foundation-vm/attribution-20260910.md.
# Nothing else on the VM is touched. No package, no unit, no config, no data.
#
# IDENTITY FIRST, NEVER PID FIRST. A pid is not an identity -- pids are
# recycled, and acting on a stale one would kill an innocent process. So the
# target is discovered FROM the listener, then five independent properties must
# agree before a signal is sent:
#
#   1. the pid actually owns the 11435 listener, per `ss -tlnp`
#   2. its executable resolves to /usr/local/bin/ollama
#   3. that executable's SHA-256 equals the recorded hash
#   4. its command line is `ollama serve`
#   5. its cgroup is a USER SESSION scope, never system.slice
#
# Property 5 is the structural safety guarantee: a systemd-managed service can
# never match, so this script cannot terminate a governed unit even if every
# other check were somehow satisfied.
#
# The governed ollama on 11434 must also be present, healthy, distinct, and
# under system.slice before anything happens. If it is not, this is not the
# situation the evidence describes and the script refuses.
#
# Any mismatch exits non-zero WITHOUT acting and reports UNKNOWN.
#
# Termination is SIGTERM only. If the process survives the grace period the
# script reports BLOCKED rather than escalating: SIGKILL is a separate, more
# forceful action and is not authorized here.
set -uo pipefail

MODE="${1:-verify}"           # verify (read-only, default) | remediate
GRACE_SECONDS=10

EXPECTED_EXE="/usr/local/bin/ollama"
EXPECTED_SHA="c05cece87b2e85a525ccf9548d329197b938e58daa46d4fad59e8dab54e8d57d"
EXPECTED_CMD_RE="ollama[[:space:]]+serve"
STRAY_PORT=11435
GOVERNED_PORT=11434

say()   { printf '%s\n' "$*"; }
head2() { printf '\n== %s ==\n' "$*"; }
fail()  { say "RESULT=UNKNOWN reason=$*"; say "ACTION_TAKEN=NONE"; exit 3; }

SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  sudo -n true 2>/dev/null && SUDO="sudo -n"
fi

say "STRAY_OLLAMA_REMEDIATION_BEGIN"
say "collected_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
say "hostname=$(hostname 2>/dev/null || echo UNKNOWN)"
say "mode=$MODE"

# ── discover the target FROM the listener, not from a remembered pid ───
head2 "REVALIDATE TARGET IDENTITY"
listener_pids="$($SUDO ss -tlnpH "sport = :$STRAY_PORT" 2>/dev/null \
                 | grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u)"
count="$(printf '%s\n' "$listener_pids" | grep -c '[0-9]' || true)"
say "  listener_pids=${listener_pids:-NONE} count=$count"

[ "$count" -eq 0 ] && { say "RESULT=ALREADY_ABSENT reason=nothing is listening on $STRAY_PORT"; say "ACTION_TAKEN=NONE"; exit 0; }
[ "$count" -eq 1 ] || fail "expected exactly one listener on $STRAY_PORT, found $count"

TARGET="$listener_pids"
say "  target_pid=$TARGET"

exe="$($SUDO readlink -f "/proc/$TARGET/exe" 2>/dev/null)"
cmd="$($SUDO tr '\0' ' ' < "/proc/$TARGET/cmdline" 2>/dev/null | sed 's/[[:space:]]*$//')"
cgroup="$($SUDO cat "/proc/$TARGET/cgroup" 2>/dev/null | tr -d '\n')"
sha="$($SUDO sha256sum "$exe" 2>/dev/null | awk '{print $1}')"
say "  exe=${exe:-UNREADABLE}"
say "  cmdline=${cmd:-UNREADABLE}"
say "  cgroup=${cgroup:-UNREADABLE}"
say "  exe_sha256=${sha:-UNREADABLE}"

[ "$exe" = "$EXPECTED_EXE" ]         || fail "executable is '${exe:-unreadable}', expected $EXPECTED_EXE"
[ "$sha" = "$EXPECTED_SHA" ]         || fail "executable SHA-256 is '${sha:-unreadable}', expected $EXPECTED_SHA"
printf '%s' "$cmd" | grep -qE "$EXPECTED_CMD_RE" || fail "command line '${cmd:-unreadable}' is not an 'ollama serve'"
say "  check_listener_owner=PASS"
say "  check_executable_path=PASS"
say "  check_executable_hash=PASS"
say "  check_command_line=PASS"

# The structural guarantee: a governed unit lives under system.slice and can
# never satisfy this, so a service cannot be terminated by this script.
case "$cgroup" in
  *system.slice*) fail "target is under system.slice -- it is a systemd-managed service, refusing" ;;
  *user.slice*|*session-*.scope*) say "  check_cgroup_is_user_session=PASS" ;;
  *) fail "cgroup '${cgroup:-unreadable}' is neither a user session scope nor recognised" ;;
esac

# ── the governed instance must be present, healthy and distinct ────────
head2 "GOVERNED OLLAMA ON $GOVERNED_PORT"
gov_pids="$($SUDO ss -tlnpH "sport = :$GOVERNED_PORT" 2>/dev/null \
            | grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u)"
gov_pid="$(printf '%s\n' "$gov_pids" | head -1)"
say "  governed_pid=${gov_pid:-NONE}"
[ -n "$gov_pid" ] || fail "nothing is listening on $GOVERNED_PORT; the governed instance is not up"
[ "$gov_pid" != "$TARGET" ] || fail "the same pid holds both ports; this is not the recorded situation"

gov_cgroup="$($SUDO cat "/proc/$gov_pid/cgroup" 2>/dev/null | tr -d '\n')"
say "  governed_cgroup=${gov_cgroup:-UNREADABLE}"
case "$gov_cgroup" in
  *ollama.service*) say "  check_governed_is_ollama_service=PASS" ;;
  *) fail "governed pid $gov_pid is not under ollama.service (cgroup '${gov_cgroup:-unreadable}')" ;;
esac

gov_http="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://127.0.0.1:$GOVERNED_PORT/api/version" 2>/dev/null)"
say "  governed_http_api_version=${gov_http:-NO_RESPONSE}"
[ "$gov_http" = "200" ] || fail "governed ollama on $GOVERNED_PORT answered '${gov_http:-nothing}', not 200"
say "  check_governed_healthy=PASS"

# ── containment must still be intact before we touch anything ──────────
head2 "NEMOTRON CONTAINMENT PRECHECK"
nem_active="$(systemctl show dominion-nemotron.service -p ActiveState --value 2>/dev/null)"
nem_file="$(systemctl show dominion-nemotron.service -p UnitFileState --value 2>/dev/null)"
say "  dominion-nemotron.service active=$nem_active unit_file=$nem_file"
[ "$nem_active" != "active" ] || fail "dominion-nemotron.service is ACTIVE; this is a different situation than the evidence describes"
say "  check_nemotron_contained=PASS"

say ""
say "IDENTITY_REVALIDATED=PASS target_pid=$TARGET"

if [ "$MODE" != "remediate" ]; then
  say "RESULT=VERIFIED_NOT_REMEDIATED"
  say "ACTION_TAKEN=NONE (verify mode)"
  exit 0
fi

# ── least-forceful termination ─────────────────────────────────────────
head2 "TERMINATE"
say "  sending SIGTERM to $TARGET"
$SUDO kill -TERM "$TARGET" 2>/dev/null || fail "SIGTERM could not be delivered to $TARGET"
say "  signal_delivered=YES"

waited=0
while [ "$waited" -lt "$GRACE_SECONDS" ]; do
  if ! $SUDO kill -0 "$TARGET" 2>/dev/null; then break; fi
  sleep 1
  waited=$((waited + 1))
done
say "  waited_seconds=$waited"

if $SUDO kill -0 "$TARGET" 2>/dev/null; then
  say "RESULT=BLOCKED reason=process survived SIGTERM after ${GRACE_SECONDS}s"
  say "ACTION_TAKEN=SIGTERM_SENT_PROCESS_STILL_RUNNING"
  say "NOTE=escalation to SIGKILL is a separate, more forceful action and is not authorized by this lane"
  exit 4
fi
say "  process_gone=YES"

# ── prove the outcome ──────────────────────────────────────────────────
head2 "POST-STATE PROOF"
still="$($SUDO ss -tlnH "sport = :$STRAY_PORT" 2>/dev/null | wc -l)"
say "  port_${STRAY_PORT}_listeners=$still"
[ "$still" -eq 0 ] && say "  proof_11435_absent=PASS" || say "  proof_11435_absent=FAIL"

gov_after="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://127.0.0.1:$GOVERNED_PORT/api/version" 2>/dev/null)"
say "  governed_http_after=${gov_after:-NO_RESPONSE}"
[ "$gov_after" = "200" ] && say "  proof_11434_healthy=PASS" || say "  proof_11434_healthy=FAIL"

nem_after="$(systemctl show dominion-nemotron.service -p ActiveState --value 2>/dev/null)"
nem_file_after="$(systemctl show dominion-nemotron.service -p UnitFileState --value 2>/dev/null)"
say "  nemotron_after active=$nem_after unit_file=$nem_file_after"
[ "$nem_after" != "active" ] && say "  proof_nemotron_still_contained=PASS" || say "  proof_nemotron_still_contained=FAIL"

cc="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:8091/api/status 2>/dev/null)"
say "  command_center_api_status=${cc:-NO_RESPONSE}"
[ "$cc" = "200" ] && say "  proof_command_center_green=PASS" || say "  proof_command_center_green=FAIL"

# The integrity agent runs on an 89s timer. Wait for it to produce a fresh
# verdict of its own accord rather than invoking it, so the proof is the
# system's own scheduled evidence and not something this lane manufactured.
head2 "INTEGRITY AGENT VERDICT (awaiting its own next cycle)"
LATEST="$HOME/.dominion/system-integrity/latest.json"
before_cycle="$(python3 -c "import json;print(json.load(open('$LATEST'))['cycle'])" 2>/dev/null || echo 0)"
say "  cycle_before=$before_cycle"
waited=0
while [ "$waited" -lt 200 ]; do
  now_cycle="$(python3 -c "import json;print(json.load(open('$LATEST'))['cycle'])" 2>/dev/null || echo 0)"
  [ "$now_cycle" -gt "$before_cycle" ] && break
  sleep 5
  waited=$((waited + 5))
done
say "  waited_seconds=$waited"
python3 - "$LATEST" <<'PYV' 2>/dev/null | sed 's/^/  /' || say "  latest.json UNREADABLE"
import json, sys
d = json.load(open(sys.argv[1]))
print(f"cycle_after={d.get('cycle')} status={d.get('status')} ok={d.get('ok')} "
      f"checks={d.get('checks_total')} defects={d.get('defect_count')}")
for x in d.get("defects") or []:
    print(f"  remaining_defect: {x}")
print("proof_integrity_pass=" + ("PASS" if d.get("ok") else "FAIL"))
PYV

say ""
say "STRAY_OLLAMA_REMEDIATION_END"
say "PROCESSES_TERMINATED=1"

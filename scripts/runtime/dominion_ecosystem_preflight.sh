#!/usr/bin/env bash
# =============================================================================
# scripts/runtime/dominion_ecosystem_preflight.sh
# Read-only runtime preflight check — Dominion Ecosystem
# Does NOT modify any state, start/stop services, or deploy anything.
# =============================================================================
set -uo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENV_FILE="${DOMINION_ENV_FILE:-${REPO_ROOT}/.env}"
EXPECTED_SHA="${1:-${EXPECTED_SHA:-}}"
DISK_WARN_PCT="${DISK_WARN_PCT:-80}"
DISK_FAIL_PCT="${DISK_FAIL_PCT:-}"

# ---------------------------------------------------------------------------
# Startup: validate threshold configuration before running any checks
# ---------------------------------------------------------------------------
_validate_threshold() {
    local val="$1" name="$2"
    if [[ ! "${val}" =~ ^[0-9]+$ ]] || [[ "${val}" -lt 1 ]] || [[ "${val}" -gt 100 ]]; then
        echo "CONFIG ERROR: ${name}=${val} must be an integer from 1 to 100" >&2
        exit 2
    fi
}

_validate_threshold "${DISK_WARN_PCT}" "DISK_WARN_PCT"
if [[ -n "${DISK_FAIL_PCT}" ]]; then
    _validate_threshold "${DISK_FAIL_PCT}" "DISK_FAIL_PCT"
    if [[ "${DISK_FAIL_PCT}" -lt "${DISK_WARN_PCT}" ]]; then
        echo "CONFIG ERROR: DISK_FAIL_PCT (${DISK_FAIL_PCT}) must be >= DISK_WARN_PCT (${DISK_WARN_PCT})" >&2
        exit 2
    fi
fi

# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------
PASS=0
WARN=0
FAIL=0

_pass()    { PASS=$((PASS + 1));  echo "  [PASS] $*"; }
_warn()    { WARN=$((WARN + 1));  echo "  [WARN] $*"; }
_fail()    { FAIL=$((FAIL + 1));  echo "  [FAIL] $*"; }
_info()    { echo "  [INFO] $*"; }
_section() { echo; echo "=== $* ==="; }

# ---------------------------------------------------------------------------
# 1. Git SHA reconciliation — always run
# ---------------------------------------------------------------------------
_section "Git SHA reconciliation"

_validate_sha() {
    [[ "${1}" =~ ^[0-9a-fA-F]{40}$ ]]
}

ACTUAL_SHA=""
GIT_REPO_OK=0

if ! command -v git &>/dev/null; then
    _fail "git is not installed — cannot inspect repository SHA"
else
    if git -C "${REPO_ROOT}" rev-parse --is-inside-work-tree &>/dev/null; then
        GIT_REPO_OK=1
    fi

    if [[ "${GIT_REPO_OK}" -eq 0 ]]; then
        _fail "REPO_ROOT (${REPO_ROOT}) is not a Git repository"
    else
        RAW_SHA=""
        GIT_SHA_RC=0
        RAW_SHA="$(git -C "${REPO_ROOT}" rev-parse HEAD 2>/dev/null)" || GIT_SHA_RC=$?
        if [[ "${GIT_SHA_RC}" -ne 0 ]] || [[ -z "${RAW_SHA}" ]]; then
            _fail "Could not read HEAD SHA from repository (exit ${GIT_SHA_RC})"
        elif ! _validate_sha "${RAW_SHA}"; then
            _fail "HEAD SHA '${RAW_SHA}' is not a valid 40-character hex string"
        else
            ACTUAL_SHA="${RAW_SHA}"
            _info "HEAD SHA: ${ACTUAL_SHA}"
        fi
    fi
fi

if [[ -z "${EXPECTED_SHA}" ]]; then
    _warn "EXPECTED_SHA not set — SHA comparison skipped"
elif [[ -z "${ACTUAL_SHA}" ]]; then
    : # already failed above
elif ! _validate_sha "${EXPECTED_SHA}"; then
    _fail "EXPECTED_SHA '${EXPECTED_SHA}' is not a valid 40-character hex SHA — cannot compare"
elif [[ "${ACTUAL_SHA}" == "${EXPECTED_SHA}" ]]; then
    _pass "HEAD SHA matches expected: ${ACTUAL_SHA}"
else
    _fail "SHA mismatch — expected ${EXPECTED_SHA}, got ${ACTUAL_SHA}"
fi

# ---------------------------------------------------------------------------
# 2. Environment file — safe non-evaluating parser
# ---------------------------------------------------------------------------
_section "Environment file variable presence"

declare -A ENV_VARS=()
ENV_PARSE_FAILED=0

_parse_env_file() {
    local env_file="$1"
    if [[ ! -f "${env_file}" ]]; then
        _warn "Env file not found at ${env_file} — skipping variable checks"
        ENV_PARSE_FAILED=1
        return
    fi

    local raw_output awk_rc
    raw_output=""
    awk_rc=0
    raw_output="$(awk '
        {
            line = $0
            # Strip leading whitespace
            sub(/^[[:space:]]+/, "", line)
            # Skip blank lines and comment-only lines
            if (line == "" || substr(line, 1, 1) == "#") next
            # Strip optional export prefix — accepts tabs and multiple spaces
            if (line ~ /^export[[:space:]]+/) {
                sub(/^export[[:space:]]+/, "", line)
            }
            # Must contain = to be an assignment
            eq = index(line, "=")
            if (eq == 0) next
            name = substr(line, 1, eq - 1)
            sub(/[[:space:]]+$/, "", name)
            sub(/^[[:space:]]+/, "", name)
            # Name must be a valid shell identifier
            if (name !~ /^[A-Za-z_][A-Za-z0-9_]*$/) next
            val = substr(line, eq + 1)
            # Strip leading whitespace from value
            sub(/^[[:space:]]+/, "", val)
            # Handle double-quoted value
            if (substr(val, 1, 1) == "\"") {
                val = substr(val, 2)
                q = index(val, "\"")
                if (q > 0) val = substr(val, 1, q - 1)
                else val = ""
            }
            # Handle single-quoted value
            else if (substr(val, 1, 1) == "'"'"'") {
                val = substr(val, 2)
                q = index(val, "'"'"'")
                if (q > 0) val = substr(val, 1, q - 1)
                else val = ""
            }
            # Unquoted value — strip inline comment (space(s) + #)
            else {
                n = split(val, parts, /[[:space:]]+#/)
                if (n >= 1) val = parts[1]
                sub(/[[:space:]]+$/, "", val)
            }
            # Report only when value is non-empty after all stripping
            if (val != "") print name
        }
    ' "${env_file}" 2>/dev/null)" || awk_rc=$?

    if [[ "${awk_rc}" -ne 0 ]]; then
        _warn "Env file parser failed on ${env_file} (exit ${awk_rc}) — skipping variable checks"
        ENV_PARSE_FAILED=1
        return
    fi

    while IFS= read -r varname; do
        [[ -n "${varname}" ]] && ENV_VARS["${varname}"]=1
    done <<< "${raw_output}"
}

_parse_env_file "${ENV_FILE}"

# severity argument: WARN (default) or FAIL
_check_var() {
    local varname="$1"
    local label="${2:-${varname}}"
    local severity="${3:-WARN}"
    if [[ "${ENV_PARSE_FAILED}" -eq 1 ]]; then
        return   # single WARN already emitted by parser; suppress per-variable noise
    fi
    if [[ -n "${ENV_VARS[${varname}]+_}" ]]; then
        _pass "${label} present in env file"
    else
        if [[ "${severity}" == "FAIL" ]]; then
            _fail "${label} absent or empty in env file"
        else
            _warn "${label} absent or empty in env file"
        fi
    fi
}

# Wix variables — WARN until governed activation gate confirms mandatory
_check_var "WIX_API_KEY"               "wix_api_key"               "WARN"
_check_var "WIX_SITE_ID"               "wix_site_id"               "WARN"
_check_var "WIX_AGENT_OPERATOR_TOKEN"  "wix_agent_operator_token"  "WARN"

# Provider, payment, trading, social, and video variables — WARN
_check_var "ANTHROPIC_API_KEY"   "anthropic_api_key"   "WARN"
_check_var "GEMINI_API_KEY"      "gemini_api_key"      "WARN"
_check_var "STRIPE_SECRET_KEY"   "stripe_secret_key"   "WARN"
_check_var "YOUTUBE_CLIENT_ID"   "youtube_client_id"   "WARN"
_check_var "OANDA_API_KEY"       "oanda_api_key"       "WARN"
_check_var "TIKTOK_CLIENT_ID"    "tiktok_client_id"    "WARN"
_check_var "BREVO_API_KEY"       "brevo_api_key"       "WARN"
_check_var "N8N_WEBHOOK_URL"     "n8n_webhook_url"     "WARN"

# ---------------------------------------------------------------------------
# 3. Disk usage
# ---------------------------------------------------------------------------
_section "Disk usage"

if command -v df &>/dev/null; then
    DF_RC=0
    DF_OUTPUT=""
    DF_OUTPUT="$(df -P / 2>/dev/null)" || DF_RC=$?
    if [[ "${DF_RC}" -ne 0 ]] || [[ -z "${DF_OUTPUT}" ]]; then
        _fail "df -P / failed (exit ${DF_RC})"
    else
        USED_PCT="$(echo "${DF_OUTPUT}" | awk 'NR==2 { gsub(/%/, "", $5); print $5 }')"
        FREE_BLOCKS="$(echo "${DF_OUTPUT}" | awk 'NR==2 { print $4 }')"
        if [[ ! "${USED_PCT}" =~ ^[0-9]+$ ]]; then
            _fail "Could not parse disk usage percentage from df output: '${USED_PCT}'"
        elif [[ ! "${FREE_BLOCKS}" =~ ^[0-9]+$ ]]; then
            _fail "Could not parse free blocks from df output: '${FREE_BLOCKS}'"
        else
            _info "Disk usage: ${USED_PCT}%, free blocks: ${FREE_BLOCKS}"
            if [[ "${FREE_BLOCKS}" -eq 0 ]]; then
                _fail "Disk is FULL (0 blocks free)"
            elif [[ -n "${DISK_FAIL_PCT}" ]] && [[ "${USED_PCT}" -ge "${DISK_FAIL_PCT}" ]]; then
                _fail "Disk at ${USED_PCT}% — exceeds DISK_FAIL_PCT=${DISK_FAIL_PCT}%"
            elif [[ "${USED_PCT}" -ge "${DISK_WARN_PCT}" ]]; then
                _warn "Disk at ${USED_PCT}% — exceeds warn threshold of ${DISK_WARN_PCT}%"
            else
                _pass "Disk at ${USED_PCT}% — within threshold"
            fi
        fi
    fi
else
    _warn "df not available — skipping disk check"
fi

# ---------------------------------------------------------------------------
# 4. Port listener classification
# ---------------------------------------------------------------------------
_section "Port listener classification"

SS_OUTPUT=""
SS_AVAILABLE=0
if command -v ss &>/dev/null; then
    SS_RC=0
    SS_OUTPUT="$(ss -H -ltn 2>/dev/null)" || SS_RC=$?
    if [[ "${SS_RC}" -eq 0 ]]; then
        SS_AVAILABLE=1
    else
        _warn "ss -H -ltn failed (exit ${SS_RC}) — skipping all port checks"
    fi
else
    _warn "ss not available — skipping all port checks"
fi

# Extract all Local-Address:Port entries for an exact port number from the
# captured ss snapshot.  Matches only when the address field ends with :PORT.
_get_port_listeners() {
    local port="$1"
    if [[ "${SS_AVAILABLE}" -eq 0 ]]; then return; fi
    echo "${SS_OUTPUT}" | awk -v port="${port}" '
    {
        addr = $4
        suffix = ":" port
        slen = length(suffix)
        alen = length(addr)
        if (alen >= slen && substr(addr, alen - slen + 1) == suffix) print addr
    }'
}

# Returns 0 (true) when the address is an approved loopback address.
# Approved loopback: 127.0.0.1 (IPv4 only), ::1 (IPv6), [::1] (bracket form).
# Any other address — including other 127.x.x.x variants — is non-loopback.
_is_loopback() {
    local addr_port="$1"
    # Remove port suffix (bash %: shortest match from right)
    local addr="${addr_port%:*}"
    # Remove IPv6 bracket notation
    addr="${addr//[\[\]]/}"
    [[ "${addr}" == "127.0.0.1" ]] && return 0
    [[ "${addr}" == "::1" ]]       && return 0
    return 1
}

# Loopback-only port: FAIL when any listener is not an approved loopback address.
_check_loopback_port() {
    local port="$1"
    local label="${2:-port ${port}}"
    if [[ "${SS_AVAILABLE}" -eq 0 ]]; then return; fi

    local listeners non_loopback_found
    listeners="$(_get_port_listeners "${port}")"
    if [[ -z "${listeners}" ]]; then
        _info "${label} (${port}): no listener found"
        return
    fi

    non_loopback_found=0
    while IFS= read -r listener; do
        [[ -z "${listener}" ]] && continue
        if ! _is_loopback "${listener}"; then
            _fail "${label} (${port}): loopback-only port has non-loopback listener: ${listener}"
            non_loopback_found=1
        fi
    done <<< "${listeners}"

    if [[ "${non_loopback_found}" -eq 0 ]]; then
        _pass "${label} (${port}): all listeners are loopback-only"
    fi
}

# Inspect a governed service port for non-loopback binding.
# WARN when any non-loopback listener is found — firewall and reverse-proxy
# exposure require verification.
# PASS when only loopback listeners are found.
# INFO when no listener is found.
_check_service_port() {
    local port="$1"
    local label="${2:-port ${port}}"
    if [[ "${SS_AVAILABLE}" -eq 0 ]]; then return; fi

    local listeners non_loopback_found
    listeners="$(_get_port_listeners "${port}")"
    if [[ -z "${listeners}" ]]; then
        _info "${label} (${port}): no listener found"
        return
    fi

    non_loopback_found=0
    while IFS= read -r listener; do
        [[ -z "${listener}" ]] && continue
        if ! _is_loopback "${listener}"; then
            non_loopback_found=1
        fi
    done <<< "${listeners}"

    if [[ "${non_loopback_found}" -eq 1 ]]; then
        _warn "${label} (${port}): non-loopback listener present — firewall and reverse-proxy exposure require verification"
    else
        _pass "${label} (${port}): listener found (loopback only)"
    fi
}

# Loopback-only governed ports — FAIL on any non-loopback binding
_check_loopback_port 5432 "dominion-db (postgres)"
_check_loopback_port 8082 "wix-agent"
_check_loopback_port 8083 "obsidian-remote"

# Governed service ports — WARN on non-loopback binding
_check_service_port  8080 "baby-api"
_check_service_port  8081 "browser-agents"
_check_service_port  8090 "dominion-web"
_check_service_port  8001 "movie-generator"
_check_service_port  5678 "dominion-n8n"
_check_service_port  5000 "dominion-gatekeeper"
_check_service_port  5051 "conductor-api"
_check_service_port  5052 "buddy-bridge"
_check_service_port  5055 "dominion-juris"
_check_service_port  5080 "dominion-store"
_check_service_port  5090 "ascendant-store"
_check_service_port  5095 "dominion-report"
_check_service_port  5100 "dominion-ops-dashboard"
_check_service_port  5110 "dominion-command-deck"
_check_service_port  5120 "dominion-tiktok"
_check_service_port  3000 "dominion-dashboard"

# ---------------------------------------------------------------------------
# 5. Docker Compose file validation (read-only)
# ---------------------------------------------------------------------------
_section "Docker Compose file validation"

COMPOSE_FILE="${REPO_ROOT}/docker-compose.yml"
if [[ ! -f "${COMPOSE_FILE}" ]]; then
    _warn "docker-compose.yml not found at ${COMPOSE_FILE}"
elif ! command -v docker &>/dev/null; then
    _warn "docker not available — skipping compose validation"
else
    COMPOSE_RC=0
    docker compose -f "${COMPOSE_FILE}" config --quiet 2>/dev/null || COMPOSE_RC=$?
    if [[ "${COMPOSE_RC}" -eq 0 ]]; then
        _pass "docker compose config validates successfully"
    else
        _fail "docker compose config failed (exit ${COMPOSE_RC})"
    fi
fi

# ---------------------------------------------------------------------------
# 6. Docker container health
# ---------------------------------------------------------------------------
_section "Docker container health"

DOCKER_PS_OUT=""
DOCKER_AVAILABLE=0

if ! command -v docker &>/dev/null; then
    _warn "docker not available — skipping container checks"
else
    DOCKER_INFO_RC=0
    docker info &>/dev/null || DOCKER_INFO_RC=$?
    if [[ "${DOCKER_INFO_RC}" -ne 0 ]]; then
        _fail "Docker daemon is not accessible (docker info exit ${DOCKER_INFO_RC}) — skipping container checks"
    else
        DOCKER_PS_RC=0
        DOCKER_PS_OUT="$(docker ps -a --format '{{.Names}}' 2>/dev/null)" || DOCKER_PS_RC=$?
        if [[ "${DOCKER_PS_RC}" -eq 0 ]]; then
            DOCKER_AVAILABLE=1
        else
            _fail "docker ps -a failed (exit ${DOCKER_PS_RC}) — skipping container checks"
        fi
    fi
fi

_check_container() {
    local ct="$1"
    if [[ "${DOCKER_AVAILABLE}" -eq 0 ]]; then return; fi

    # Only inspect containers confirmed present in the ps snapshot
    if ! echo "${DOCKER_PS_OUT}" | grep -qx "${ct}"; then
        _warn "${ct}: not found in docker ps -a output"
        return
    fi

    local status inspect_status_rc
    status=""
    inspect_status_rc=0
    status="$(docker inspect --format '{{.State.Status}}' "${ct}" 2>/dev/null)" || inspect_status_rc=$?
    if [[ "${inspect_status_rc}" -ne 0 ]] || [[ -z "${status}" ]]; then
        _fail "${ct}: docker inspect State.Status failed (exit ${inspect_status_rc})"
        return
    fi

    local health inspect_health_rc
    health=""
    inspect_health_rc=0
    health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}no_healthcheck{{end}}' "${ct}" 2>/dev/null)" || inspect_health_rc=$?
    if [[ "${inspect_health_rc}" -ne 0 ]] || [[ -z "${health}" ]]; then
        _fail "${ct}: docker inspect Health.Status failed (exit ${inspect_health_rc})"
        return
    fi

    if [[ "${status}" != "running" ]]; then
        _fail "${ct}: status=${status}"
    elif [[ "${health}" == "unhealthy" ]]; then
        _fail "${ct}: running but health=${health}"
    elif [[ "${health}" == "starting" ]]; then
        _warn "${ct}: running, health=${health} (still initializing)"
    else
        _pass "${ct}: status=${status}, health=${health}"
    fi
}

EXPECTED_CONTAINERS=(
    "baby-api"
    "baby-logger"
    "browser-agents"
    "dominion-web"
    "wix-agent"
    "obsidian-remote"
    "movie-generator"
    "dominion-seo"
    "dominion-n8n"
    "dominion-db"
)

for ct in "${EXPECTED_CONTAINERS[@]}"; do
    _check_container "${ct}"
done

# ---------------------------------------------------------------------------
# 7. Systemd service presence
# ---------------------------------------------------------------------------
_section "Systemd service presence"

SYSTEMCTL_AVAILABLE=0
if command -v systemctl &>/dev/null; then
    SYSTEMCTL_AVAILABLE=1
else
    _warn "systemctl not available — skipping systemd checks"
fi

_check_service() {
    local svc="$1"
    if [[ "${SYSTEMCTL_AVAILABLE}" -eq 0 ]]; then return; fi

    local state svc_rc
    state=""
    svc_rc=0
    state="$(systemctl is-active "${svc}" 2>/dev/null)" || svc_rc=$?

    # Empty output indicates systemctl itself failed to run (e.g. dbus unavailable)
    if [[ -z "${state}" ]]; then
        _warn "${svc}: systemctl is-active returned no output (exit ${svc_rc})"
        return
    fi

    case "${state}" in
        active)     _pass "${svc}: active" ;;
        activating) _warn "${svc}: activating" ;;
        *)          _fail "${svc}: ${state}" ;;
    esac
}

if [[ "${SYSTEMCTL_AVAILABLE}" -eq 1 ]]; then
    SYSTEMD_SERVICES=(
        "caddy"
        "dominion-gatekeeper"
        "conductor-api"
        "conductor-worker"
        "conductor-scheduler"
        "buddy-bridge"
        "dominion-juris"
        "auric-edge"
        "dominion-buddy-web"
        "dominion-store"
        "ascendant-store"
        "dominion-report"
        "dominion-dashboard"
        "dominion-sentinel"
        "dominion-guardian"
        "dominion-monitor"
        "dominion-n8n-watchdog"
        "dominion-ops-dashboard"
        "dominion-command-deck"
        "dominion-tiktok"
        "dominion-twilio-router"
        "dominion-email-monitor"
        "dominion-email-drip"
        "dominion-alpha"
        "dominion-alchemist"
        "dominion-3d-dashboard"
        "dominion-conductor"
        "dominion-review-queue"
        "dominion-surplus-dashboard"
        "covenant-watchdog"
        "gemini-server"
        "ollama"
    )

    for svc in "${SYSTEMD_SERVICES[@]}"; do
        _check_service "${svc}"
    done

    # Report failed units only when the query itself succeeds
    FAILED_UNITS=""
    FAILED_UNITS_RC=0
    FAILED_UNITS="$(systemctl list-units --state=failed --no-legend --no-pager 2>/dev/null)" || FAILED_UNITS_RC=$?

    if [[ "${FAILED_UNITS_RC}" -ne 0 ]]; then
        _warn "systemctl list-units --state=failed failed (exit ${FAILED_UNITS_RC}) — failed unit count is unknown"
    elif [[ -z "${FAILED_UNITS}" ]]; then
        _pass "No failed systemd units"
    else
        FAILED_UNIT_NAMES="$(echo "${FAILED_UNITS}" | awk '{ print $1 }' | tr '\n' ' ')"
        _fail "Failed systemd units: ${FAILED_UNIT_NAMES}"
    fi
fi

# ---------------------------------------------------------------------------
# 8. logrotate
# ---------------------------------------------------------------------------
_section "logrotate"

if [[ "${SYSTEMCTL_AVAILABLE}" -eq 1 ]]; then
    LOGROTATE_STATE=""
    LOGROTATE_RC=0
    # is-failed exits 0 when the service is in failed state; non-zero otherwise.
    # The state string is always printed when systemctl can reach dbus.
    LOGROTATE_STATE="$(systemctl is-failed logrotate.service 2>/dev/null)" || LOGROTATE_RC=$?

    if [[ -z "${LOGROTATE_STATE}" ]]; then
        _warn "logrotate.service: systemctl is-failed returned no output (exit ${LOGROTATE_RC})"
    elif [[ "${LOGROTATE_STATE}" == "failed" ]]; then
        _fail "logrotate.service is in failed state — inspect with: journalctl -u logrotate -n 50"
    else
        # Non-failed state (active, inactive, etc.) — non-zero exit from is-failed is expected
        _info "logrotate.service state=${LOGROTATE_STATE} (timer-driven unit may show inactive between runs)"
    fi
else
    _warn "systemctl not available — skipping logrotate check"
fi

# ---------------------------------------------------------------------------
# 9. Summary
# ---------------------------------------------------------------------------
_section "Preflight summary"
echo "  PASS: ${PASS}  WARN: ${WARN}  FAIL: ${FAIL}"
echo

if [[ "${FAIL}" -gt 0 ]]; then
    echo "  PREFLIGHT STATUS: FAIL — ${FAIL} failure(s) require attention before deployment"
    exit 1
elif [[ "${WARN}" -gt 0 ]]; then
    echo "  PREFLIGHT STATUS: WARN — ${WARN} warning(s) require review"
    exit 0
else
    echo "  PREFLIGHT STATUS: PASS"
    exit 0
fi

#!/usr/bin/env bash
# Post-deploy verification. Read-only. Exits non-zero on any failed gate.
#
# Gate 8 is the reason this exists: it asserts that Postgres, Redis and Ollama
# are NOT reachable from outside the container network. A passing deploy that
# published those ports would be a breach, not a success.
set -uo pipefail

PUBLIC_HOST="${PUBLIC_HOST:-127.0.0.1}"
FAILED=0

pass() { printf '  PASS  %s\n' "$*"; }
fail() { printf '  FAIL  %s\n' "$*"; FAILED=1; }

printf '== Council Node verification ==\n'

printf '\n[service]\n'
if curl -fsS --max-time 5 "http://127.0.0.1:8200/health" >/dev/null 2>&1; then
  pass "council-api /health responds on loopback"
else
  fail "council-api /health did not respond"
fi

if curl -fsS --max-time 5 "http://127.0.0.1:8200/ready" 2>/dev/null | grep -q '"ready": *true'; then
  pass "governance loaded (/ready reports ready)"
else
  fail "/ready did not report ready — governance may not have loaded"
fi

printf '\n[network exposure — must NOT be reachable]\n'
check_closed() {
  local name="$1" port="$2"
  if timeout 3 bash -c "</dev/tcp/${PUBLIC_HOST}/${port}" 2>/dev/null; then
    fail "$name is reachable on ${PUBLIC_HOST}:${port}"
  else
    pass "$name is not publicly reachable (${port})"
  fi
}
check_closed postgres 5432
check_closed redis 6379
check_closed ollama 11434

printf '\n[containers]\n'
if docker compose ps --format '{{.Service}} {{.State}}' 2>/dev/null | grep -q 'running'; then
  docker compose ps --format '  {{.Service}}: {{.State}}' 2>/dev/null
  pass "compose services are running"
else
  fail "no running compose services found"
fi

printf '\n'
if [ "$FAILED" -eq 0 ]; then
  printf 'VERIFICATION PASSED\n'
else
  printf 'VERIFICATION FAILED — do not record this deployment as DONE\n'
fi
exit "$FAILED"

#!/usr/bin/env bash
set -Eeuo pipefail

state_root="${DOMINION_PUBLISHER_STATE_ROOT:-$HOME/.dominion/publisher}"
env_file="$state_root/runtime.env"
release_root="$state_root/runtime/release"
venv="$state_root/venv"
base_url="${DOMINION_PUBLISHER_LOCAL_URL:-http://127.0.0.1:5112}"

usage() {
  cat <<'EOF'
Usage:
  meta_control.sh configure
  meta_control.sh start
  meta_control.sh candidates
  meta_control.sh bind <facebook_page_id> <approved_by>
  meta_control.sh accounts

Provider secrets and the Publisher operator token are never printed.
EOF
}

require_runtime() {
  test -s "$env_file" || { echo 'META_CONTROL=FAIL reason=runtime_env_missing'; exit 20; }
  test -x "$venv/bin/python" || { echo 'META_CONTROL=FAIL reason=publisher_python_missing'; exit 21; }
  operator_token="$(sed -n 's/^DOMINION_PUBLISHER_OPERATOR_TOKEN=//p' "$env_file" | head -1)"
  test -n "$operator_token" || { echo 'META_CONTROL=FAIL reason=operator_token_missing'; exit 22; }
}

pretty_json() {
  python3 -m json.tool
}

# curl -f discards the response body on HTTP errors, which hid the server's own
# explanation (for example the 503 "Meta app configuration is not present in
# the encrypted vault") behind a bare "curl: (22) ... error: 503". Capture the
# body and the status separately so the operator sees the reason. Exit 22 is
# preserved so callers that keyed off curl's failure code still behave the same.
api_call() {
  local method="$1" url="$2" body_file status
  shift 2
  body_file="$(mktemp)"
  status="$(curl -sS -o "$body_file" -w '%{http_code}' --max-time 30 \
    -X "$method" -H "X-Operator-Token: $operator_token" "$@" "$url")" || {
      echo "META_CONTROL=FAIL reason=transport_error url=$url" >&2
      rm -f "$body_file"
      return 22
    }
  if [ "$status" -ge 400 ]; then
    echo "META_CONTROL=FAIL http_status=$status" >&2
    echo "META_CONTROL_ERROR_BODY<<EOF" >&2
    cat "$body_file" >&2
    echo >&2
    echo "EOF" >&2
    rm -f "$body_file"
    return 22
  fi
  cat "$body_file"
  rm -f "$body_file"
}

command_name="${1:-}"
case "$command_name" in
  configure)
    require_runtime
    cd "$release_root"
    set -a
    # runtime.env is mode 0600 and contains only Publisher-local configuration.
    # shellcheck disable=SC1090
    source "$env_file"
    set +a
    exec "$venv/bin/python" -m apps.dominion_publisher.configure_meta
    ;;

  start)
    require_runtime
    response="$(api_call POST "$base_url/oauth/meta/start")"
    python3 - "$response" <<'PY'
import json,sys
payload=json.loads(sys.argv[1])
url=payload['authorization_url']
print('META_BINDING_START=PASS')
print('AUTHORIZATION_URL=' + url)
print('EXPIRES_IN_SECONDS=' + str(payload['expires_in_seconds']))
PY
    ;;

  candidates)
    require_runtime
    body="$(api_call GET "$base_url/oauth/meta/candidates")" || exit 22
    printf '%s' "$body" | pretty_json
    ;;

  bind)
    require_runtime
    page_id="${2:-}"
    approved_by="${3:-}"
    test -n "$page_id" || { usage; exit 2; }
    test -n "$approved_by" || { usage; exit 2; }
    payload="$(python3 - "$page_id" "$approved_by" <<'PY'
import json,sys
print(json.dumps({'page_id':sys.argv[1],'approved_by':sys.argv[2]}))
PY
)"
    body="$(api_call POST "$base_url/oauth/meta/bind" \
      -H 'X-Human-Approval: APPROVED' \
      -H 'Content-Type: application/json' \
      --data "$payload")" || exit 22
    printf '%s' "$body" | pretty_json
    ;;

  accounts)
    require_runtime
    body="$(api_call GET "$base_url/accounts")" || exit 22
    printf '%s' "$body" | pretty_json
    ;;

  *)
    usage
    exit 2
    ;;
esac

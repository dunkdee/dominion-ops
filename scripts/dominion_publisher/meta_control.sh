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
    response="$(curl -fsS -X POST \
      -H "X-Operator-Token: $operator_token" \
      "$base_url/oauth/meta/start")"
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
    curl -fsS \
      -H "X-Operator-Token: $operator_token" \
      "$base_url/oauth/meta/candidates" | pretty_json
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
    curl -fsS -X POST \
      -H "X-Operator-Token: $operator_token" \
      -H 'X-Human-Approval: APPROVED' \
      -H 'Content-Type: application/json' \
      --data "$payload" \
      "$base_url/oauth/meta/bind" | pretty_json
    ;;

  accounts)
    require_runtime
    curl -fsS \
      -H "X-Operator-Token: $operator_token" \
      "$base_url/accounts" | pretty_json
    ;;

  *)
    usage
    exit 2
    ;;
esac

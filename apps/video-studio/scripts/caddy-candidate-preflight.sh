#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

: "${RELEASE_SHA:?RELEASE_SHA is required}"
[[ "$RELEASE_SHA" =~ ^[0-9a-f]{40}$ ]]

report_dir="$HOME/releases/video-studio-caddy-candidate/$RELEASE_SHA"
report="$report_dir/caddy-candidate-report.txt"
live_copy="$report_dir/.live-Caddyfile.private"
merged_template="$report_dir/.merged-Caddyfile.template.private"
merged_candidate="$report_dir/.merged-Caddyfile.private"
canary_config="$report_dir/.canary-Caddyfile.private"
marker_dir="$report_dir/upstream"
caddy_log="$report_dir/.caddy-canary.log"
upstream_log="$report_dir/.upstream-canary.log"
caddy_pid=""
upstream_pid=""
password=""
live_before="unknown"
auth_directive="unknown"
stage=initialize

cleanup() {
  set +e
  [ -z "$caddy_pid" ] || kill "$caddy_pid" >/dev/null 2>&1 || true
  [ -z "$upstream_pid" ] || kill "$upstream_pid" >/dev/null 2>&1 || true
  [ -z "$caddy_pid" ] || wait "$caddy_pid" >/dev/null 2>&1 || true
  [ -z "$upstream_pid" ] || wait "$upstream_pid" >/dev/null 2>&1 || true
  rm -f "$live_copy" "$merged_template" "$merged_candidate" "$canary_config" "$caddy_log" "$upstream_log"
  rm -rf "$marker_dir" "$report_dir/caddy-data" "$report_dir/caddy-config"
  password=""
}

current_live_hash() {
  if [ -r /etc/caddy/Caddyfile ]; then
    sha256sum /etc/caddy/Caddyfile | awk '{print $1}'
  else
    sudo -n sha256sum /etc/caddy/Caddyfile | awk '{print $1}'
  fi
}

redact_caddy_output() {
  sed -E \
    -e 's/\$2[aby]\$[0-9]{2}\$[A-Za-z0-9.\/]+/[REDACTED_HASH]/g' \
    -e 's/operator[[:space:]]+[^[:space:]]+/operator [REDACTED]/g'
}

write_failure() {
  local exit_code=$?
  trap - ERR
  set +e
  live_after=$(current_live_hash 2>/dev/null || echo unavailable)
  live_unchanged=false
  if [ "$live_before" != unknown ] && [ "$live_before" = "$live_after" ]; then
    live_unchanged=true
  fi
  {
    echo "release_sha=$RELEASE_SHA"
    echo "result=failed"
    echo "failed_stage=$stage"
    echo "exit_code=$exit_code"
    echo "auth_directive_candidate=$auth_directive"
    echo "live_config_hash_unchanged=$live_unchanged"
    echo "live_caddy_active_after=$(systemctl is-active caddy 2>/dev/null || echo unknown)"
    echo "plaintext_credential_exported=false"
    echo "password_hash_exported=false"
    echo "live_config_modified=false"
    echo "public_route_activated=false"
    if [ -f "$caddy_log" ]; then
      echo "--- caddy_canary_log_tail ---"
      tail -n 60 "$caddy_log" | redact_caddy_output
    fi
    if [ -f "$upstream_log" ]; then
      echo "--- upstream_canary_log_tail ---"
      tail -n 20 "$upstream_log"
    fi
  } > "$report"
  chmod 600 "$report"
  cat "$report" >&2
  exit "$exit_code"
}

trap cleanup EXIT
trap write_failure ERR

stage=verify_prerequisites
mkdir -p "$report_dir" "$marker_dir" "$report_dir/caddy-data" "$report_dir/caddy-config"
chmod 700 "$report_dir" "$marker_dir" "$report_dir/caddy-data" "$report_dir/caddy-config"
command -v caddy >/dev/null
command -v curl >/dev/null
command -v openssl >/dev/null
command -v python3 >/dev/null
systemctl is-active --quiet caddy

stage=copy_live_config
if [ -r /etc/caddy/Caddyfile ]; then
  cp /etc/caddy/Caddyfile "$live_copy"
else
  sudo -n cat /etc/caddy/Caddyfile > "$live_copy"
fi
chmod 600 "$live_copy"
live_before=$(sha256sum "$live_copy" | awk '{print $1}')

stage=generate_ephemeral_credential
password=$(openssl rand -hex 24)
test "${#password}" = 48
password_hash=$(caddy hash-password --plaintext "$password")
test -n "$password_hash"

stage=insert_candidate_route
python3 - "$live_copy" "$merged_template" "$password_hash" <<'PY'
import sys
from pathlib import Path

source = Path(sys.argv[1])
destination = Path(sys.argv[2])
password_hash = sys.argv[3]
lines = source.read_text(encoding="utf-8").splitlines()
target = "tools.dominionhealing.org"
start = None
for index, raw in enumerate(lines):
    code = raw.split("#", 1)[0].strip()
    if code == f"{target} {{":
        start = index
        break
if start is None:
    raise SystemExit("tools_site_block_not_found")

depth = 0
end = None
for index in range(start, len(lines)):
    code = lines[index].split("#", 1)[0]
    depth += code.count("{")
    depth -= code.count("}")
    if index > start and depth == 0:
        end = index
        break
if end is None:
    raise SystemExit("tools_site_block_unclosed")
block = "\n".join(lines[start : end + 1])
if "/video-studio" in block or "127.0.0.1:8094" in block:
    raise SystemExit("video_studio_route_already_present")

indent = "    "
route = [
    f"{indent}handle_path /video-studio/* {{",
    f"{indent}{indent}DOMINION_AUTH_DIRECTIVE {{",
    f"{indent}{indent}{indent}operator {password_hash}",
    f"{indent}{indent}}}",
    f"{indent}{indent}reverse_proxy 127.0.0.1:8094",
    f"{indent}}}",
    "",
]
updated = lines[: start + 1] + route + lines[start + 1 :]
destination.write_text("\n".join(updated) + "\n", encoding="utf-8")
PY
chmod 600 "$merged_template"
route_count=$(grep -c 'handle_path /video-studio/\*' "$merged_template")
test "$route_count" = 1

stage=detect_auth_directive
cp "$merged_template" "$merged_candidate"
sed -i 's/DOMINION_AUTH_DIRECTIVE/basic_auth/' "$merged_candidate"
auth_directive=basic_auth
if ! caddy validate --config "$merged_candidate" --adapter caddyfile >"$caddy_log" 2>&1; then
  cp "$merged_template" "$merged_candidate"
  sed -i 's/DOMINION_AUTH_DIRECTIVE/basicauth/' "$merged_candidate"
  auth_directive=basicauth
  caddy validate --config "$merged_candidate" --adapter caddyfile >"$caddy_log" 2>&1
fi

stage=prepare_isolated_canary
cat > "$marker_dir/index.html" <<'HTML'
DOMINION_VIDEO_STUDIO_AUTH_CANARY_OK
HTML
chmod 600 "$marker_dir/index.html"
python3 -m http.server 18099 --bind 127.0.0.1 --directory "$marker_dir" >"$upstream_log" 2>&1 &
upstream_pid=$!

cat > "$canary_config" <<EOF
{
    admin off
    auto_https off
}

http://127.0.0.1:18098 {
    handle_path /video-studio/* {
        $auth_directive {
            operator $password_hash
        }
        reverse_proxy 127.0.0.1:18099
    }
    respond 404
}
EOF
chmod 600 "$canary_config"
caddy validate --config "$canary_config" --adapter caddyfile >"$caddy_log" 2>&1

stage=launch_isolated_canary
XDG_DATA_HOME="$report_dir/caddy-data" XDG_CONFIG_HOME="$report_dir/caddy-config" \
  caddy run --config "$canary_config" --adapter caddyfile >"$caddy_log" 2>&1 &
caddy_pid=$!

stage=wait_for_canary
upstream_ready=false
for attempt in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:18099/ >/dev/null 2>&1; then
    upstream_ready=true
    break
  fi
  sleep 1
done
[ "$upstream_ready" = true ]

caddy_ready=false
for attempt in $(seq 1 30); do
  status=$(curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:18098/video-studio/ || true)
  if [ "$status" = 401 ]; then
    caddy_ready=true
    break
  fi
  sleep 1
done
[ "$caddy_ready" = true ]

stage=verify_authentication_behavior
unauthorized_status=$(curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:18098/video-studio/)
wrong_status=$(curl -sS -o /dev/null -w '%{http_code}' -u 'operator:wrong-password' http://127.0.0.1:18098/video-studio/)
authorized_body=$(curl -fsS -u "operator:$password" http://127.0.0.1:18098/video-studio/)
authorized_status=$(curl -sS -o /dev/null -w '%{http_code}' -u "operator:$password" http://127.0.0.1:18098/video-studio/)
test "$unauthorized_status" = 401
test "$wrong_status" = 401
test "$authorized_status" = 200
grep -q 'DOMINION_VIDEO_STUDIO_AUTH_CANARY_OK' <<<"$authorized_body"

stage=verify_live_runtime_unchanged
live_after=$(current_live_hash)
test "$live_after" = "$live_before"
systemctl is-active --quiet caddy

stage=write_success_evidence
{
  echo "release_sha=$RELEASE_SHA"
  echo "result=passed"
  echo "candidate_only=true"
  echo "placement=tools.dominionhealing.org/video-studio/"
  echo "auth_directive=$auth_directive"
  echo "live_config_hash_unchanged=true"
  echo "route_insertion_count=$route_count"
  echo "merged_live_config_validation=passed"
  echo "isolated_canary_config_validation=passed"
  echo "unauthorized_status=$unauthorized_status"
  echo "wrong_password_status=$wrong_status"
  echo "authorized_status=$authorized_status"
  echo "authorized_upstream_marker=passed"
  echo "live_caddy_active_after=true"
  echo "plaintext_credential_exported=false"
  echo "password_hash_exported=false"
  echo "live_config_modified=false"
  echo "public_route_activated=false"
} > "$report"
chmod 600 "$report"
cat "$report"

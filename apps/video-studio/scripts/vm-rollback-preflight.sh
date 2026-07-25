#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

: "${RELEASE_SHA:?RELEASE_SHA is required}"
: "${SHORT_SHA:?SHORT_SHA is required}"
[[ "$RELEASE_SHA" =~ ^[0-9a-f]{40}$ ]]
[[ "$SHORT_SHA" =~ ^[0-9a-f]{12}$ ]]

root="$HOME/releases/video-studio-rollback/$RELEASE_SHA"
good_dir="$root/apps/video-studio"
broken_dir="$root/broken/apps/video-studio"
report="$root/rollback-preflight-report.txt"
good_log="$root/.good-deploy.log"
broken_log="$root/.broken-deploy.log"
service="dominion-video-studio-rollback-$SHORT_SHA"
rollback_name="${service}-rollback"
image_repo="dominion/video-studio-rollback-$SHORT_SHA"
volume="${service}-data"
env_file="$root/rollback-test.env"
port=18096
broken_sha=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
production_before=absent
stage=initialize

cleanup() {
  set +e
  docker rm -f "$service" "$rollback_name" >/dev/null 2>&1 || true
  docker volume rm "$volume" >/dev/null 2>&1 || true
  docker images "$image_repo" --format '{{.Repository}}:{{.Tag}}' \
    | xargs -r docker image rm >/dev/null 2>&1 || true
  rm -f "$env_file" "$good_log" "$broken_log"
  rm -rf "$root/broken"
}

production_identity() {
  if docker inspect dominion-video-studio >/dev/null 2>&1; then
    docker inspect dominion-video-studio --format '{{.Id}}'
  else
    printf 'absent\n'
  fi
}

redact_log() {
  sed -E \
    -e 's/(VIDEO_STUDIO_WORKER_TOKEN=)[^[:space:]]+/\1[REDACTED]/g' \
    -e 's/[0-9a-f]{64}/[REDACTED_TOKEN_OR_HASH]/g'
}

write_failure() {
  local exit_code=$?
  trap - ERR
  set +e
  production_after=$(production_identity 2>/dev/null || echo unavailable)
  production_unchanged=false
  [ "$production_after" = "$production_before" ] && production_unchanged=true
  service_present=false
  service_running=false
  rollback_present=false
  restored_sha=none
  restored_image=none
  if docker inspect "$service" >/dev/null 2>&1; then
    service_present=true
    service_running=$(docker inspect "$service" --format '{{.State.Running}}' 2>/dev/null || echo false)
    restored_sha=$(docker inspect "$service" --format '{{index .Config.Labels "dominion.release.sha"}}' 2>/dev/null || echo none)
    restored_image=$(docker inspect "$service" --format '{{.Config.Image}}' 2>/dev/null || echo none)
  fi
  docker inspect "$rollback_name" >/dev/null 2>&1 && rollback_present=true
  {
    echo "release_sha=$RELEASE_SHA"
    echo "result=failed"
    echo "failed_stage=$stage"
    echo "exit_code=$exit_code"
    echo "test_service_present=$service_present"
    echo "test_service_running=$service_running"
    echo "rollback_container_present=$rollback_present"
    echo "observed_service_release_sha=$restored_sha"
    echo "observed_service_image=$restored_image"
    echo "production_container_unchanged=$production_unchanged"
    echo "personal_media_used=false"
    echo "public_exposure=not_performed"
    if [ -f "$good_log" ]; then
      echo "--- good_deploy_log_tail ---"
      tail -n 80 "$good_log" | redact_log
    fi
    if [ -f "$broken_log" ]; then
      echo "--- broken_deploy_log_tail ---"
      tail -n 120 "$broken_log" | redact_log
    fi
  } > "$report"
  chmod 600 "$report"
  cat "$report" >&2
  exit "$exit_code"
}

trap cleanup EXIT
trap write_failure ERR

stage=verify_prerequisites
command -v docker >/dev/null
command -v curl >/dev/null
command -v openssl >/dev/null
command -v python3 >/dev/null
docker info >/dev/null
test -d "$good_dir"
test -f "$good_dir/deploy-gcp-vm.sh"
production_before=$(production_identity)
cleanup
mkdir -p "$root"

stage=deploy_known_good_candidate
good_started=$(date +%s)
(
  cd "$good_dir"
  chmod 700 deploy-gcp-vm.sh
  RELEASE_SHA="$RELEASE_SHA" \
  VIDEO_STUDIO_SERVICE_NAME="$service" \
  VIDEO_STUDIO_IMAGE_REPO="$image_repo" \
  VIDEO_STUDIO_PORT="$port" \
  VIDEO_STUDIO_DATA_VOLUME="$volume" \
  VIDEO_STUDIO_ENV_FILE="$env_file" \
  VIDEO_STUDIO_HEALTH_ATTEMPTS=20 \
  VIDEO_STUDIO_HEALTH_INTERVAL_SECONDS=1 \
  ./deploy-gcp-vm.sh
) >"$good_log" 2>&1
good_seconds=$(( $(date +%s) - good_started ))

stage=verify_known_good_candidate
good_id=$(docker inspect "$service" --format '{{.Id}}')
good_image=$(docker inspect "$service" --format '{{.Config.Image}}')
good_release_sha=$(docker inspect "$service" --format '{{index .Config.Labels "dominion.release.sha"}}')
test "$good_release_sha" = "$RELEASE_SHA"
test "$(docker inspect "$service" --format '{{.State.Running}}')" = true
curl -fsS "http://127.0.0.1:${port}/ready" > "$root/good-ready.json"
python3 - "$root/good-ready.json" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
assert payload.get("status") == "ready", payload
PY
test "$(stat -c '%a' "$env_file")" = 600

stage=prepare_deliberately_broken_candidate
mkdir -p "$(dirname "$broken_dir")"
cp -a "$good_dir" "$broken_dir"
cat > "$broken_dir/fail-fast.sh" <<'SH'
#!/bin/sh
exit 42
SH
chmod 755 "$broken_dir/fail-fast.sh"
cat >> "$broken_dir/Dockerfile" <<'DOCKER'
COPY fail-fast.sh /app/fail-fast.sh
CMD ["/app/fail-fast.sh"]
DOCKER

grep -q 'CMD \["/app/fail-fast.sh"\]' "$broken_dir/Dockerfile"

stage=attempt_broken_replacement
broken_started=$(date +%s)
set +e
(
  cd "$broken_dir"
  chmod 700 deploy-gcp-vm.sh
  RELEASE_SHA="$broken_sha" \
  VIDEO_STUDIO_SERVICE_NAME="$service" \
  VIDEO_STUDIO_IMAGE_REPO="$image_repo" \
  VIDEO_STUDIO_PORT="$port" \
  VIDEO_STUDIO_DATA_VOLUME="$volume" \
  VIDEO_STUDIO_ENV_FILE="$env_file" \
  VIDEO_STUDIO_HEALTH_ATTEMPTS=5 \
  VIDEO_STUDIO_HEALTH_INTERVAL_SECONDS=1 \
  ./deploy-gcp-vm.sh
) >"$broken_log" 2>&1
broken_exit=$?
set -e
broken_seconds=$(( $(date +%s) - broken_started ))
test "$broken_exit" -ne 0

stage=verify_automatic_restore
restored_id=$(docker inspect "$service" --format '{{.Id}}')
restored_image=$(docker inspect "$service" --format '{{.Config.Image}}')
restored_release_sha=$(docker inspect "$service" --format '{{index .Config.Labels "dominion.release.sha"}}')
test "$restored_id" = "$good_id"
test "$restored_image" = "$good_image"
test "$restored_release_sha" = "$RELEASE_SHA"
test "$(docker inspect "$service" --format '{{.State.Running}}')" = true
if docker inspect "$rollback_name" >/dev/null 2>&1; then
  echo "ERROR: rollback container still exists after restoration" >&2
  false
fi
curl -fsS "http://127.0.0.1:${port}/ready" > "$root/restored-ready.json"
python3 - "$root/restored-ready.json" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
assert payload.get("status") == "ready", payload
PY

stage=verify_production_noninterference
production_after=$(production_identity)
test "$production_after" = "$production_before"

stage=write_success_evidence
{
  echo "release_sha=$RELEASE_SHA"
  echo "result=passed"
  echo "isolated_good_deploy=passed"
  echo "deliberately_broken_replacement_failed=true"
  echo "automatic_previous_container_restore=passed"
  echo "restored_container_identity_match=passed"
  echo "restored_image_match=passed"
  echo "restored_release_sha_match=passed"
  echo "restored_readiness=passed"
  echo "good_deploy_seconds=$good_seconds"
  echo "failed_replacement_and_restore_seconds=$broken_seconds"
  echo "localhost_test_binding=127.0.0.1:18096"
  echo "production_container_unchanged=passed"
  echo "personal_media_used=false"
  echo "public_exposure=not_performed"
} > "$report"
chmod 600 "$report"
cat "$report"

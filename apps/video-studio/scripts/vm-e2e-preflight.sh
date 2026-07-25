#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

: "${RELEASE_SHA:?RELEASE_SHA is required}"
: "${SHORT_SHA:?SHORT_SHA is required}"
[[ "$RELEASE_SHA" =~ ^[0-9a-f]{40}$ ]]
[[ "$SHORT_SHA" =~ ^[0-9a-f]{12}$ ]]

release_root="$HOME/releases/video-studio-e2e/$RELEASE_SHA"
release_dir="$release_root/apps/video-studio"
report="$release_root/e2e-worker-preflight-report.txt"
work_dir="$release_root/synthetic-e2e"
control_image="dominion/video-studio:e2e-$RELEASE_SHA"
worker_image="dominion/video-studio-lite:e2e-$RELEASE_SHA"
control_container="dominion-video-studio-e2e-$SHORT_SHA"
worker_container="dominion-lite-worker-e2e-$SHORT_SHA"
network="dominion-video-studio-e2e-$SHORT_SHA"
volume="dominion-video-studio-e2e-$SHORT_SHA-data"
port=18097
token=""
worker_id="dominion-lite-e2e-$SHORT_SHA"
production_before=absent
stage=initialize

cleanup() {
  set +e
  docker rm -f "$worker_container" "$control_container" >/dev/null 2>&1 || true
  docker network rm "$network" >/dev/null 2>&1 || true
  docker volume rm "$volume" >/dev/null 2>&1 || true
  docker image rm "$worker_image" "$control_image" >/dev/null 2>&1 || true
  rm -rf "$work_dir"
}

write_failure() {
  local exit_code=$?
  trap - ERR
  set +e
  {
    echo "release_sha=$RELEASE_SHA"
    echo "result=failed"
    echo "failed_stage=$stage"
    echo "exit_code=$exit_code"
    echo "production_container_touched=false_or_verified_by_cleanup_boundary"
    echo "personal_media_used=false"
    echo "public_exposure=not_performed"
    echo "--- control_plane_logs ---"
    docker logs --tail 60 "$control_container" 2>&1 | sed "s/${token:-__NO_TOKEN__}/[REDACTED]/g" || true
    echo "--- worker_logs ---"
    docker logs --tail 60 "$worker_container" 2>&1 | sed "s/${token:-__NO_TOKEN__}/[REDACTED]/g" || true
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
test -d "$release_dir"
if docker inspect dominion-video-studio >/dev/null 2>&1; then
  production_before=$(docker inspect dominion-video-studio --format '{{.Id}}')
fi
cleanup
mkdir -p "$work_dir"
chmod 777 "$work_dir"
token=$(openssl rand -hex 32)

stage=build_control_plane_image
docker build --progress=plain --pull --tag "$control_image" "$release_dir"

stage=build_cpu_worker_image
docker build --progress=plain --pull \
  --file "$release_dir/worker/Dockerfile.lite" \
  --tag "$worker_image" "$release_dir"

stage=generate_synthetic_inputs
python3 - "$work_dir" <<'PY'
import binascii
import math
import struct
import sys
import wave
import zlib
from pathlib import Path


def png_chunk(kind: bytes, data: bytes) -> bytes:
    checksum = binascii.crc32(kind + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", checksum)


target = Path(sys.argv[1])
width, height = 480, 640
rows: list[bytes] = []
for y in range(height):
    row = bytearray()
    for x in range(width):
        row.extend(
            (
                45 + x * 110 // width,
                60 + y * 95 // height,
                100 + (x + y) * 70 // (width + height),
            )
        )
    rows.append(b"\x00" + bytes(row))
raw = b"".join(rows)
png = (
    b"\x89PNG\r\n\x1a\n"
    + png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    + png_chunk(b"IDAT", zlib.compress(raw, 9))
    + png_chunk(b"IEND", b"")
)
(target / "portrait.png").write_bytes(png)

sample_rate = 16_000
duration = 1.35
with wave.open(str(target / "voice.wav"), "wb") as output:
    output.setnchannels(1)
    output.setsampwidth(2)
    output.setframerate(sample_rate)
    for index in range(int(sample_rate * duration)):
        envelope = 0.2 + 0.7 * abs(math.sin(index / sample_rate * math.pi * 3.5))
        value = int(32767 * 0.20 * envelope * math.sin(2 * math.pi * 205 * index / sample_rate))
        output.writeframesraw(struct.pack("<h", value))
PY
chmod 644 "$work_dir/portrait.png" "$work_dir/voice.wav"

stage=create_internal_runtime
docker network create --internal "$network" >/dev/null
docker volume create "$volume" >/dev/null

stage=launch_control_plane
docker run -d --name "$control_container" \
  --network "$network" --network-alias video-studio \
  --publish "127.0.0.1:${port}:8000" \
  --read-only --tmpfs /tmp:size=256m,noexec,nosuid,nodev \
  --cap-drop ALL --security-opt no-new-privileges \
  --pids-limit 256 --memory 2g --cpus 2.0 \
  --env VIDEO_STUDIO_DATA_DIR=/data \
  --env VIDEO_STUDIO_MAX_UPLOAD_BYTES=104857600 \
  --env "VIDEO_STUDIO_WORKER_TOKEN=$token" \
  --volume "$volume:/data" \
  "$control_image" >/dev/null

stage=wait_for_control_plane
ready=false
for attempt in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:${port}/ready" >/tmp/e2e-ready.json; then
    ready=true
    break
  fi
  sleep 2
done
[ "$ready" = true ]
python3 -c 'import json; d=json.load(open("/tmp/e2e-ready.json")); assert d.get("status") == "ready", d; assert d.get("external_worker_configured") is True, d'

stage=create_consent_and_project
consent=$(curl -fsS -X POST "http://127.0.0.1:${port}/api/consents" \
  -H 'Content-Type: application/json' \
  --data '{"subject_name":"Synthetic E2E Subject","likeness_confirmed":true,"voice_confirmed":true,"rights_confirmed":true}')
consent_id=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])' <<<"$consent")
project=$(curl -fsS -X POST "http://127.0.0.1:${port}/api/projects" \
  -H 'Content-Type: application/json' \
  --data "{\"title\":\"Synthetic E2E\",\"script\":\"Dominion end to end worker canary.\",\"output_format\":\"vertical\",\"consent_id\":\"$consent_id\"}")
project_id=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])' <<<"$project")

stage=upload_synthetic_assets
curl -fsS -X POST "http://127.0.0.1:${port}/api/projects/${project_id}/assets" \
  -F kind=portrait -F "file=@$work_dir/portrait.png;type=image/png" >/dev/null
curl -fsS -X POST "http://127.0.0.1:${port}/api/projects/${project_id}/assets" \
  -F kind=voice -F "file=@$work_dir/voice.wav;type=audio/wav" >/dev/null

stage=queue_external_job
queued=$(curl -fsS -X POST "http://127.0.0.1:${port}/api/projects/${project_id}/jobs" \
  -H 'Content-Type: application/json' --data '{"engine":"external_clone"}')
job_id=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])' <<<"$queued")

stage=launch_detachable_worker
render_started=$(date +%s)
docker run -d --name "$worker_container" \
  --network "$network" \
  --read-only --tmpfs /tmp:size=512m,noexec,nosuid,nodev \
  --cap-drop ALL --security-opt no-new-privileges \
  --pids-limit 256 --memory 2g --cpus 2.0 \
  --env VIDEO_STUDIO_URL=http://video-studio:8000 \
  --env "VIDEO_STUDIO_WORKER_TOKEN=$token" \
  --env "VIDEO_STUDIO_WORKER_ID=$worker_id" \
  --env VIDEO_STUDIO_POLL_SECONDS=1 \
  --env 'VIDEO_CLONE_COMMAND=python /worker/dominion_lite_canary_renderer.py --portrait {portrait} --voice {voice} --script-file {script_file} --output {output} --format {output_format} --fps 24' \
  "$worker_image" >/dev/null

stage=wait_for_external_job
status=queued
job='{}'
for attempt in $(seq 1 120); do
  job=$(curl -fsS "http://127.0.0.1:${port}/api/jobs/${job_id}")
  status=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])' <<<"$job")
  if [ "$status" = completed ]; then
    break
  fi
  if [ "$status" = failed ]; then
    false
  fi
  sleep 1
done
[ "$status" = completed ]
render_seconds=$(( $(date +%s) - render_started ))
python3 -c 'import json,sys; d=json.load(sys.stdin); assert "claim_token_hash" not in d; assert d["download_url"]' <<<"$job"

stage=download_and_validate_output
curl -fsS "http://127.0.0.1:${port}/api/jobs/${job_id}/download" -o "$work_dir/output.mp4"
test -s "$work_dir/output.mp4"
docker run --rm --network none --read-only \
  --volume "$work_dir:/work:ro" --entrypoint ffprobe "$worker_image" \
  -v error -show_entries stream=codec_name,width,height -show_entries format=duration \
  -of json /work/output.mp4 > "$release_root/e2e-ffprobe.json"
python3 - "$release_root/e2e-ffprobe.json" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
streams = payload.get("streams", [])
video = next(stream for stream in streams if "width" in stream)
audio = next(stream for stream in streams if stream.get("codec_name") == "aac")
assert video["codec_name"] == "h264", payload
assert (video["width"], video["height"]) == (720, 1280), payload
assert audio["codec_name"] == "aac", payload
assert 1.0 <= float(payload["format"]["duration"]) <= 2.1, payload
PY

stage=verify_review_and_isolation
project_state=$(curl -fsS "http://127.0.0.1:${port}/api/projects/${project_id}")
python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["status"] == "review_ready", d' <<<"$project_state"
test "$(docker inspect "$control_container" --format '{{.HostConfig.ReadonlyRootfs}}')" = true
test "$(docker inspect "$worker_container" --format '{{.HostConfig.ReadonlyRootfs}}')" = true
test "$(docker network inspect "$network" --format '{{.Internal}}')" = true
production_after=absent
if docker inspect dominion-video-studio >/dev/null 2>&1; then
  production_after=$(docker inspect dominion-video-studio --format '{{.Id}}')
fi
test "$production_after" = "$production_before"

stage=write_success_evidence
output_bytes=$(stat -c '%s' "$work_dir/output.mp4")
output_sha=$(sha256sum "$work_dir/output.mp4" | awk '{print $1}')
{
  echo "release_sha=$RELEASE_SHA"
  echo "result=passed"
  echo "control_plane_ready=passed"
  echo "consent_project_asset_job_flow=passed"
  echo "worker_claim_lease_download=passed"
  echo "cpu_render=passed"
  echo "validated_output_upload=passed"
  echo "project_review_ready=passed"
  echo "output_format=720x1280_h264_aac"
  echo "output_bytes=$output_bytes"
  echo "output_sha256=$output_sha"
  echo "render_seconds=$render_seconds"
  echo "docker_network_internal=true"
  echo "localhost_binding=127.0.0.1:18097"
  echo "production_container_unchanged=passed"
  echo "personal_media_used=false"
  echo "public_exposure=not_performed"
  echo "claim=cpu_preview_not_neural_clone"
} > "$report"
chmod 600 "$report" "$release_root/e2e-ffprobe.json"
cat "$report"

# Prepended to the governed remote deployment payload.
# It wraps only `docker compose up` so stale, verified Dominion containers
# cannot block either deployment or automatic rollback.

reconcile_governed_wix_container() {
  local ids container_id full_id container_name image service_label working_dir config_files mount_names
  local authorized_legacy_id="f0319cf37704efcd92de809994673620c77e3850ec0106551340f3ad2e2859b5"
  local identity_source=""
  local count=0
  local owned=0

  ids="$(command docker container ls --all --quiet --filter 'name=^/wix-agent$' 2>/dev/null || true)"
  [ -n "$ids" ] || return 0

  count="$(printf '%s\n' "$ids" | sed '/^$/d' | wc -l | tr -d ' ')"
  if [ "$count" -ne 1 ]; then
    FAILURE_DETAIL="wix_agent_container_count=${count}"
    echo "Governed Wix container reconciliation found an ambiguous exact-name match"
    return 1
  fi

  container_id="$(printf '%s\n' "$ids" | sed -n '1p')"
  full_id="$(command docker inspect --format '{{.Id}}' "$container_id" 2>/dev/null || true)"
  container_name="$(command docker inspect --format '{{.Name}}' "$container_id" 2>/dev/null || true)"
  image="$(command docker inspect --format '{{.Config.Image}}' "$container_id" 2>/dev/null || true)"
  service_label="$(command docker inspect --format '{{index .Config.Labels "com.docker.compose.service"}}' "$container_id" 2>/dev/null || true)"
  working_dir="$(command docker inspect --format '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' "$container_id" 2>/dev/null || true)"
  config_files="$(command docker inspect --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}' "$container_id" 2>/dev/null || true)"
  mount_names="$(command docker inspect --format '{{range .Mounts}}{{println .Name}}{{end}}' "$container_id" 2>/dev/null || true)"

  if [ "$container_name" != "/wix-agent" ]; then
    FAILURE_DETAIL="wix_agent_container_name=unexpected"
    echo "Exact-name Wix reconciliation resolved an unexpected container identity"
    return 1
  fi

  # One-time authorization for the exact legacy container observed in governed
  # workflow run 30221186607. The full immutable Docker ID and exact name must
  # both match; no prefix or image-only match is accepted by this path.
  if [ "$full_id" = "$authorized_legacy_id" ]; then
    owned=1
    identity_source="authorized-observed-legacy-id"
  fi

  if [ "$owned" -ne 1 ] && [ "$service_label" = "wix-agent" ]; then
    case "$image" in
      dominion/wix-agent:*)
        owned=1
        identity_source="compose-service-image"
        ;;
    esac
    case "${working_dir}|${config_files}" in
      *"/dominion-ops"*)
        owned=1
        identity_source="compose-project-path"
        ;;
    esac
  fi

  if [ "$owned" -ne 1 ]; then
    case "$image" in
      dominion/wix-agent:*)
        case "$mount_names" in
          *"dominion-ops_wix_agent_data"*"dominion-ops_wix_agent_logs"*|*"dominion-ops_wix_agent_logs"*"dominion-ops_wix_agent_data"*)
            owned=1
            identity_source="governed-image-volumes"
            ;;
        esac
        ;;
    esac
  fi

  if [ "$owned" -ne 1 ]; then
    FAILURE_DETAIL="wix_agent_container_identity=unverified"
    echo "Existing /wix-agent container is not verified as Dominion-managed; refusing removal"
    return 1
  fi

  command docker rm --force "$container_id" >/dev/null
  printf 'DEPLOY_CONTAINER_RECONCILE name=wix-agent status=removed identity=%s volumes=preserved\n' "$identity_source"
}

reconcile_governed_dominion_web_container() {
  local ids container_id full_id container_name image service_label working_dir config_files
  local authorized_legacy_id="cf8294541b1ab3c7ea29896950f6e87e38683ac32b400afb8a1850a0be6f61c5"
  local identity_source=""
  local count=0
  local owned=0

  ids="$(command docker container ls --all --quiet --filter 'name=^/dominion-web$' 2>/dev/null || true)"
  [ -n "$ids" ] || return 0

  count="$(printf '%s\n' "$ids" | sed '/^$/d' | wc -l | tr -d ' ')"
  if [ "$count" -ne 1 ]; then
    FAILURE_DETAIL="dominion_web_container_count=${count}"
    echo "Governed Dominion web reconciliation found an ambiguous exact-name match"
    return 1
  fi

  container_id="$(printf '%s\n' "$ids" | sed -n '1p')"
  full_id="$(command docker inspect --format '{{.Id}}' "$container_id" 2>/dev/null || true)"
  container_name="$(command docker inspect --format '{{.Name}}' "$container_id" 2>/dev/null || true)"
  image="$(command docker inspect --format '{{.Config.Image}}' "$container_id" 2>/dev/null || true)"
  service_label="$(command docker inspect --format '{{index .Config.Labels "com.docker.compose.service"}}' "$container_id" 2>/dev/null || true)"
  working_dir="$(command docker inspect --format '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' "$container_id" 2>/dev/null || true)"
  config_files="$(command docker inspect --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}' "$container_id" 2>/dev/null || true)"

  if [ "$container_name" != "/dominion-web" ]; then
    FAILURE_DETAIL="dominion_web_container_name=unexpected"
    echo "Exact-name Dominion web reconciliation resolved an unexpected container identity"
    return 1
  fi

  # One-time authorization for the exact immutable container observed in
  # governed workflow run 30228680159. Exact full ID and exact name are both
  # required; no prefix, short-ID, or name-only authorization is accepted.
  if [ "$full_id" = "$authorized_legacy_id" ]; then
    owned=1
    identity_source="authorized-observed-legacy-id"
  fi

  if [ "$owned" -ne 1 ] && [ "$service_label" = "dominion-web" ]; then
    case "$image" in
      dominion-ops-dominion-web*|dominion-web*)
        owned=1
        identity_source="compose-service-image"
        ;;
    esac
    case "${working_dir}|${config_files}" in
      *"/dominion-ops"*)
        owned=1
        identity_source="compose-project-path"
        ;;
    esac
  fi

  if [ "$owned" -ne 1 ]; then
    FAILURE_DETAIL="dominion_web_container_identity=unverified"
    echo "Existing /dominion-web container is not verified as Dominion-managed; refusing removal"
    return 1
  fi

  command docker rm --force "$container_id" >/dev/null
  printf 'DEPLOY_CONTAINER_RECONCILE name=dominion-web status=removed identity=%s volumes=preserved\n' "$identity_source"
}

reconcile_governed_baby_logger_container() {
  local ids container_id full_id container_name image service_label working_dir config_files
  local authorized_legacy_id="c3d390494b902672bd7ef1aabc0fcc4a0fe770368439933fd1a47c5b70813161"
  local identity_source=""
  local count=0
  local owned=0

  ids="$(command docker container ls --all --quiet --filter 'name=^/baby-logger$' 2>/dev/null || true)"
  [ -n "$ids" ] || return 0

  count="$(printf '%s\n' "$ids" | sed '/^$/d' | wc -l | tr -d ' ')"
  if [ "$count" -ne 1 ]; then
    FAILURE_DETAIL="baby_logger_container_count=${count}"
    echo "Governed baby logger reconciliation found an ambiguous exact-name match"
    return 1
  fi

  container_id="$(printf '%s\n' "$ids" | sed -n '1p')"
  full_id="$(command docker inspect --format '{{.Id}}' "$container_id" 2>/dev/null || true)"
  container_name="$(command docker inspect --format '{{.Name}}' "$container_id" 2>/dev/null || true)"
  image="$(command docker inspect --format '{{.Config.Image}}' "$container_id" 2>/dev/null || true)"
  service_label="$(command docker inspect --format '{{index .Config.Labels "com.docker.compose.service"}}' "$container_id" 2>/dev/null || true)"
  working_dir="$(command docker inspect --format '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' "$container_id" 2>/dev/null || true)"
  config_files="$(command docker inspect --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}' "$container_id" 2>/dev/null || true)"

  if [ "$container_name" != "/baby-logger" ]; then
    FAILURE_DETAIL="baby_logger_container_name=unexpected"
    echo "Exact-name baby logger reconciliation resolved an unexpected container identity"
    return 1
  fi

  # One-time authorization for the exact immutable container observed in
  # governed workflow run 30229386173. Exact full ID and exact name are both
  # required; no prefix, short-ID, or name-only authorization is accepted.
  if [ "$full_id" = "$authorized_legacy_id" ]; then
    owned=1
    identity_source="authorized-observed-legacy-id"
  fi

  if [ "$owned" -ne 1 ] && [ "$service_label" = "baby-logger" ]; then
    case "$image" in
      alpine:*)
        owned=1
        identity_source="compose-service-image"
        ;;
    esac
    case "${working_dir}|${config_files}" in
      *"/dominion-ops"*)
        owned=1
        identity_source="compose-project-path"
        ;;
    esac
  fi

  if [ "$owned" -ne 1 ]; then
    FAILURE_DETAIL="baby_logger_container_identity=unverified"
    echo "Existing /baby-logger container is not verified as Dominion-managed; refusing removal"
    return 1
  fi

  command docker rm --force "$container_id" >/dev/null
  printf 'DEPLOY_CONTAINER_RECONCILE name=baby-logger status=removed identity=%s volumes=none\n' "$identity_source"
}

reconcile_governed_baby_api_container() {
  local ids container_id container_name image service_label working_dir config_files bind_sources
  local expected_repo="$HOME/dominion-ops"
  local expected_config="$HOME/dominion-ops/docker-compose.yml"
  local expected_bind="$HOME/dominion-ops/api"
  local expected_image="dominion-ops-baby-api"
  local identity_source=""
  local count=0
  local bind_count=0
  local service_ok=0
  local image_ok=0
  local working_dir_ok=0
  local config_file_ok=0
  local bind_source_ok=0
  local owned=0

  ids="$(command docker container ls --all --quiet --filter 'name=^/baby-api$' 2>/dev/null || true)"
  [ -n "$ids" ] || return 0

  count="$(printf '%s\n' "$ids" | sed '/^$/d' | wc -l | tr -d ' ')"
  if [ "$count" -ne 1 ]; then
    FAILURE_DETAIL="baby_api_container_count=${count}"
    echo "Governed Baby API reconciliation found an ambiguous exact-name match"
    return 1
  fi

  container_id="$(printf '%s\n' "$ids" | sed -n '1p')"
  container_name="$(command docker inspect --format '{{.Name}}' "$container_id" 2>/dev/null || true)"
  image="$(command docker inspect --format '{{.Config.Image}}' "$container_id" 2>/dev/null || true)"
  service_label="$(command docker inspect --format '{{index .Config.Labels "com.docker.compose.service"}}' "$container_id" 2>/dev/null || true)"
  working_dir="$(command docker inspect --format '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' "$container_id" 2>/dev/null || true)"
  config_files="$(command docker inspect --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}' "$container_id" 2>/dev/null || true)"
  bind_sources="$(command docker inspect --format '{{range .Mounts}}{{if eq .Type "bind"}}{{println .Source}}{{end}}{{end}}' "$container_id" 2>/dev/null || true)"

  if [ "$container_name" != "/baby-api" ]; then
    FAILURE_DETAIL="baby_api_container_name=unexpected"
    echo "Exact-name Baby API reconciliation resolved an unexpected container identity"
    return 1
  fi

  # Track checks independently and require exact matches
  [ "$service_label" = "baby-api" ] && service_ok=1
  [ "$image" = "$expected_image" ] && image_ok=1
  [ "$working_dir" = "$expected_repo" ] && working_dir_ok=1
  [ "$config_files" = "$expected_config" ] && config_file_ok=1

  # Compose ownership requires ALL compose-managed checks
  if [ "$service_ok" -eq 1 ] && [ "$image_ok" -eq 1 ] && [ "$working_dir_ok" -eq 1 ] && [ "$config_file_ok" -eq 1 ]; then
    owned=1
    identity_source="compose-exact-identity"
  fi

  # Fallback: accept bind-managed container only when image matches AND at least one bind source equals expected_bind exactly
  if [ "$owned" -ne 1 ] && [ "$image_ok" -eq 1 ]; then
    bind_count="$(printf '%s\n' "$bind_sources" | sed '/^$/d' | wc -l | tr -d ' ')"
    if [ "$bind_count" -gt 0 ]; then
      # normalize and check if any bind source matches expected_bind exactly
      while IFS= read -r src; do
        [ -z "$src" ] && continue
        if [ "$src" = "$expected_bind" ]; then
          bind_source_ok=1
          break
        fi
      done <<EOF
$(printf '%s\n' "$bind_sources" | sed '/^$/d')
EOF
    fi

    if [ "$image_ok" -eq 1 ] && [ "$bind_source_ok" -eq 1 ]; then
      owned=1
      identity_source="governed-image-exact-api-bind"
    fi
  fi

  if [ "$owned" -ne 1 ]; then
    FAILURE_DETAIL="baby_api_container_identity=unverified"
    echo "Existing /baby-api container is not verified as Dominion-managed; refusing removal"
    return 1
  fi

  command docker rm --force "$container_id" >/dev/null
  printf 'DEPLOY_CONTAINER_RECONCILE name=baby-api status=removed identity=%s bind_data=preserved\n' "$identity_source"
}

docker() {
  local prior_phase="${PHASE:-compose-up}"

  if [ "$#" -ge 2 ] && [ "$1" = "compose" ] && [ "$2" = "up" ]; then
    PHASE="container-reconcile"
    reconcile_governed_wix_container || return $?
    reconcile_governed_dominion_web_container || return $?
    reconcile_governed_baby_logger_container || return $?
    reconcile_governed_baby_api_container || return $?
    PHASE="$prior_phase"
  fi

  command docker "$@"
}

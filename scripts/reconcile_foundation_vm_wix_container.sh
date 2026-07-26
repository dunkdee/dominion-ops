# Prepended to the governed remote deployment payload.
# It wraps only `docker compose up` so stale, verified Dominion Wix containers
# cannot block either deployment or automatic rollback.

reconcile_governed_wix_container() {
  local ids container_id image service_label working_dir config_files mount_names
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
  image="$(command docker inspect --format '{{.Config.Image}}' "$container_id" 2>/dev/null || true)"
  service_label="$(command docker inspect --format '{{index .Config.Labels "com.docker.compose.service"}}' "$container_id" 2>/dev/null || true)"
  working_dir="$(command docker inspect --format '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' "$container_id" 2>/dev/null || true)"
  config_files="$(command docker inspect --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}' "$container_id" 2>/dev/null || true)"
  mount_names="$(command docker inspect --format '{{range .Mounts}}{{println .Name}}{{end}}' "$container_id" 2>/dev/null || true)"

  if [ "$service_label" = "wix-agent" ]; then
    case "$image" in
      dominion/wix-agent:*) owned=1 ;;
    esac
    case "${working_dir}|${config_files}" in
      *"/dominion-ops"*) owned=1 ;;
    esac
  fi

  if [ "$owned" -ne 1 ]; then
    case "$image" in
      dominion/wix-agent:*)
        case "$mount_names" in
          *"dominion-ops_wix_agent_data"*"dominion-ops_wix_agent_logs"*|*"dominion-ops_wix_agent_logs"*"dominion-ops_wix_agent_data"*)
            owned=1
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
  printf 'DEPLOY_CONTAINER_RECONCILE name=wix-agent status=removed identity=verified volumes=preserved\n'
}

docker() {
  local prior_phase="${PHASE:-compose-up}"

  if [ "$#" -ge 2 ] && [ "$1" = "compose" ] && [ "$2" = "up" ]; then
    PHASE="container-reconcile"
    reconcile_governed_wix_container || return $?
    PHASE="$prior_phase"
  fi

  command docker "$@"
}

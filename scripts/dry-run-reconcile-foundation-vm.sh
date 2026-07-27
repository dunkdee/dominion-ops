#!/usr/bin/env bash
# Non-destructive strict dry-run wrapper for scripts/reconcile_foundation_vm_wix_container.sh
# Simulates the reconciliation that runs on the "foundation-vm" target.
# Prints observed vs expected identity signals with PASS/FAIL for each signal.
# Never removes or modifies anything; prints the exact removal command it would run.

set -uo pipefail

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker is not installed or not in PATH." >&2
  exit 127
fi

if ! docker info >/dev/null 2>&1; then
  echo "ERROR: Docker daemon is unavailable or this user lacks Docker permission." >&2
  exit 1
fi

dry_print_inspect() {
  local id="$1"
  local fmt="$2"
  docker inspect --format "$fmt" "$id" 2>/dev/null || true
}

dry_reconcile_governed_wix_container() {
  local ids container_id full_id container_name image service_label working_dir config_files mount_names
  local authorized_legacy_id="f0319cf37704efcd92de809994673620c77e3850ec0106551340f3ad2e2859b5"
  local identity_source=""
  local count=0
  local owned=0

  ids="$(docker container ls --all --quiet --filter 'name=^/wix-agent$' 2>/dev/null || true)"
  if [ -z "$ids" ]; then
    echo "[wix-agent] no container found; skipping."
    return 0
  fi

  count="$(printf '%s\n' "$ids" | sed '/^$/d' | wc -l | tr -d ' ')"
  if [ "$count" -ne 1 ]; then
    echo "[wix-agent] FAILURE_DETAIL=wix_agent_container_count=${count}"
    echo "[wix-agent] Governed Wix container reconciliation found an ambiguous exact-name match"
    return 1
  fi

  container_id="$(printf '%s\n' "$ids" | sed -n '1p')"
  full_id="$(dry_print_inspect "$container_id" '{{.Id}}')"
  container_name="$(dry_print_inspect "$container_id" '{{.Name}}')"
  image="$(dry_print_inspect "$container_id" '{{.Config.Image}}')"
  service_label="$(dry_print_inspect "$container_id" '{{index .Config.Labels "com.docker.compose.service"}}')"
  working_dir="$(dry_print_inspect "$container_id" '{{index .Config.Labels "com.docker.compose.project.working_dir"}}')"
  config_files="$(dry_print_inspect "$container_id" '{{index .Config.Labels "com.docker.compose.project.config_files"}}')"
  mount_names="$(dry_print_inspect "$container_id" '{{range .Mounts}}{{println .Name}}{{end}}')"

  echo "---- wix-agent identity signals ----"
  printf "container_id: %s\n" "$container_id"
  printf "full_id: %s\n" "${full_id:-<missing>}"
  printf "container_name: %s\n" "${container_name:-<missing>}"
  printf "image: %s\n" "${image:-<missing>}"
  printf "service_label: %s\n" "${service_label:-<missing>}"
  printf "working_dir: %s\n" "${working_dir:-<missing>}"
  printf "config_files: %s\n" "${config_files:-<missing>}"
  printf "mount_names:\n%s\n" "${mount_names:-<none>}"
  echo "------------------------------------"

  if [ "$container_name" != "/wix-agent" ]; then
    echo "[wix-agent] FAILURE_DETAIL=wix_agent_container_name=unexpected"
    echo "[wix-agent] Exact-name Wix reconciliation resolved an unexpected container identity"
    return 1
  fi

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
    echo "[wix-agent] FAILURE_DETAIL=wix_agent_container_identity=unverified"
    echo "[wix-agent] Existing /wix-agent container is not verified as Dominion-managed; refusing removal"
    return 1
  fi

  echo "[wix-agent] Ownership verified: yes"
  echo "[wix-agent] identity_source=${identity_source}"
  echo "[wix-agent] Would run: docker rm --force ${container_id}"
  return 0
}

dry_reconcile_governed_dominion_web_container() {
  local ids container_id full_id container_name image service_label working_dir config_files
  local authorized_legacy_id="cf8294541b1ab3c7ea29896950f6e87e38683ac32b400afb8a1850a0be6f61c5"
  local identity_source=""
  local count=0
  local owned=0

  ids="$(docker container ls --all --quiet --filter 'name=^/dominion-web$' 2>/dev/null || true)"
  if [ -z "$ids" ]; then
    echo "[dominion-web] no container found; skipping."
    return 0
  fi

  count="$(printf '%s\n' "$ids" | sed '/^$/d' | wc -l | tr -d ' ')"
  if [ "$count" -ne 1 ]; then
    echo "[dominion-web] FAILURE_DETAIL=dominion_web_container_count=${count}"
    echo "[dominion-web] Governed Dominion web reconciliation found an ambiguous exact-name match"
    return 1
  fi

  container_id="$(printf '%s\n' "$ids" | sed -n '1p')"
  full_id="$(dry_print_inspect "$container_id" '{{.Id}}')"
  container_name="$(dry_print_inspect "$container_id" '{{.Name}}')"
  image="$(dry_print_inspect "$container_id" '{{.Config.Image}}')"
  service_label="$(dry_print_inspect "$container_id" '{{index .Config.Labels "com.docker.compose.service"}}')"
  working_dir="$(dry_print_inspect "$container_id" '{{index .Config.Labels "com.docker.compose.project.working_dir"}}')"
  config_files="$(dry_print_inspect "$container_id" '{{index .Config.Labels "com.docker.compose.project.config_files"}}')"

  echo "---- dominion-web identity signals ----"
  printf "container_id: %s\n" "$container_id"
  printf "full_id: %s\n" "${full_id:-<missing>}"
  printf "container_name: %s\n" "${container_name:-<missing>}"
  printf "image: %s\n" "${image:-<missing>}"
  printf "service_label: %s\n" "${service_label:-<missing>}"
  printf "working_dir: %s\n" "${working_dir:-<missing>}"
  printf "config_files: %s\n" "${config_files:-<missing>}"
  echo "----------------------------------------"

  if [ "$container_name" != "/dominion-web" ]; then
    echo "[dominion-web] FAILURE_DETAIL=dominion_web_container_name=unexpected"
    echo "[dominion-web] Exact-name Dominion web reconciliation resolved an unexpected container identity"
    return 1
  fi

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
    echo "[dominion-web] FAILURE_DETAIL=dominion_web_container_identity=unverified"
    echo "[dominion-web] Existing /dominion-web container is not verified as Dominion-managed; refusing removal"
    return 1
  fi

  echo "[dominion-web] Ownership verified: yes"
  echo "[dominion-web] identity_source=${identity_source}"
  echo "[dominion-web] Would run: docker rm --force ${container_id}"
  return 0
}

dry_reconcile_governed_baby_logger_container() {
  local ids container_id full_id container_name image service_label working_dir config_files
  local authorized_legacy_id="c3d390494b902672bd7ef1aabc0fcc4a0fe770368439933fd1a47c5b70813161"
  local identity_source=""
  local count=0
  local owned=0

  ids="$(docker container ls --all --quiet --filter 'name=^/baby-logger$' 2>/dev/null || true)"
  if [ -z "$ids" ]; then
    echo "[baby-logger] no container found; skipping."
    return 0
  fi

  count="$(printf '%s\n' "$ids" | sed '/^$/d' | wc -l | tr -d ' ')"
  if [ "$count" -ne 1 ]; then
    echo "[baby-logger] FAILURE_DETAIL=baby_logger_container_count=${count}"
    echo "[baby-logger] Governed baby logger reconciliation found an ambiguous exact-name match"
    return 1
  fi

  container_id="$(printf '%s\n' "$ids" | sed -n '1p')"
  full_id="$(dry_print_inspect "$container_id" '{{.Id}}')"
  container_name="$(dry_print_inspect "$container_id" '{{.Name}}')"
  image="$(dry_print_inspect "$container_id" '{{.Config.Image}}')"
  service_label="$(dry_print_inspect "$container_id" '{{index .Config.Labels "com.docker.compose.service"}}')"
  working_dir="$(dry_print_inspect "$container_id" '{{index .Config.Labels "com.docker.compose.project.working_dir"}}')"
  config_files="$(dry_print_inspect "$container_id" '{{index .Config.Labels "com.docker.compose.project.config_files"}}')"

  echo "---- baby-logger identity signals ----"
  printf "container_id: %s\n" "$container_id"
  printf "full_id: %s\n" "${full_id:-<missing>}"
  printf "container_name: %s\n" "${container_name:-<missing>}"
  printf "image: %s\n" "${image:-<missing>}"
  printf "service_label: %s\n" "${service_label:-<missing>}"
  printf "working_dir: %s\n" "${working_dir:-<missing>}"
  printf "config_files: %s\n" "${config_files:-<missing>}"
  echo "--------------------------------------"

  if [ "$container_name" != "/baby-logger" ]; then
    echo "[baby-logger] FAILURE_DETAIL=baby_logger_container_name=unexpected"
    echo "[baby-logger] Exact-name baby logger reconciliation resolved an unexpected container identity"
    return 1
  fi

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
    echo "[baby-logger] FAILURE_DETAIL=baby_logger_container_identity=unverified"
    echo "[baby-logger] Existing /baby-logger container is not verified as Dominion-managed; refusing removal"
    return 1
  fi

  echo "[baby-logger] Ownership verified: yes"
  echo "[baby-logger] identity_source=${identity_source}"
  echo "[baby-logger] Would run: docker rm --force ${container_id}"
  return 0
}

dry_reconcile_governed_baby_api_container() {
  local ids container_id container_name image service_label working_dir config_files bind_sources
  local identity_source=""
  local count=0
  local owned=0

  local expected_repo expected_config expected_bind expected_image
  expected_repo="${HOME%/}/dominion-ops"
  expected_config="${expected_repo}/docker-compose.yml"
  expected_bind="${expected_repo}/api"
  expected_image="dominion-ops-baby-api"

  ids="$(docker container ls --all --quiet --filter 'name=^/baby-api$' 2>/dev/null || true)"
  if [ -z "$ids" ]; then
    echo "[baby-api] no container found; skipping."
    return 0
  fi

  count="$(printf '%s\n' "$ids" | sed '/^$/d' | wc -l | tr -d ' ')"
  if [ "$count" -ne 1 ]; then
    echo "[baby-api] FAILURE_DETAIL=baby_api_container_count=${count}"
    echo "[baby-api] Governed Baby API reconciliation found an ambiguous exact-name match"
    return 1
  fi

  container_id="$(printf '%s\n' "$ids" | sed -n '1p')"
  container_name="$(dry_print_inspect "$container_id" '{{.Name}}')"
  image="$(dry_print_inspect "$container_id" '{{.Config.Image}}')"
  service_label="$(dry_print_inspect "$container_id" '{{index .Config.Labels "com.docker.compose.service"}}')"
  working_dir="$(dry_print_inspect "$container_id" '{{index .Config.Labels "com.docker.compose.project.working_dir"}}')"
  config_files="$(dry_print_inspect "$container_id" '{{index .Config.Labels "com.docker.compose.project.config_files"}}')"
  bind_sources="$(dry_print_inspect "$container_id" '{{range .Mounts}}{{if eq .Type "bind"}}{{println .Source}}{{end}}{{end}}')"

  container_name="${container_name:-<missing>}"
  image="${image:-<missing>}"
  service_label="${service_label:-<missing>}"
  working_dir="${working_dir:-<missing>}"
  config_files="${config_files:-<missing>}"
  bind_sources="${bind_sources:-<none>}"

  echo "---- baby-api identity signals ----"
  printf "container_id: %s\n" "$container_id"
  printf "container_name: observed='%s' | expected='/baby-api' => %s\n" "$container_name" "$( [ "$container_name" = "/baby-api" ] && echo PASS || echo FAIL )"
  printf "service_label: observed='%s' | expected='baby-api' => %s\n" "$service_label" "$( [ "$service_label" = "baby-api" ] && echo PASS || echo FAIL )"
  printf "image: observed='%s' | expected='%s' => %s\n" "$image" "$expected_image" "$( [ "$image" = "$expected_image" ] && echo PASS || echo FAIL )"
  printf "working_dir: observed='%s' | expected='%s' => %s\n" "$working_dir" "$expected_repo" "$( [ "$working_dir" = "$expected_repo" ] && echo PASS || echo FAIL )"
  printf "config_files: observed='%s' | expected='%s' => %s\n" "$config_files" "$expected_config" "$( [ "$config_files" = "$expected_config" ] && echo PASS || echo FAIL )"
  printf "bind_sources (observed lines):\n%s\n" "$bind_sources"
  echo "-----------------------------------"

  if [ "$container_name" != "/baby-api" ]; then
    echo "[baby-api] FAILURE_DETAIL=baby_api_container_name=unexpected"
    echo "[baby-api] Exact-name Baby API reconciliation resolved an unexpected container identity"
    return 1
  fi

  local compose_service_ok=0
  local compose_image_ok=0
  local compose_working_ok=0
  local compose_config_ok=0

  [ "$service_label" = "baby-api" ] && compose_service_ok=1
  [ "$image" = "$expected_image" ] && compose_image_ok=1
  [ "$working_dir" = "$expected_repo" ] && compose_working_ok=1
  [ "$config_files" = "$expected_config" ] && compose_config_ok=1

  if [ "$compose_service_ok" -eq 1 ] && [ "$compose_image_ok" -eq 1 ] && [ "$compose_working_ok" -eq 1 ] && [ "$compose_config_ok" -eq 1 ]; then
    owned=1
    identity_source="compose-exact-identity"
    echo "[baby-api] Compose identity check: PASS (all four signals matched exactly)"
  else
    echo "[baby-api] Compose identity check: FAIL"
    printf "  signals: service_label=%s image=%s working_dir=%s config_files=%s\n" \
      "$( [ "$compose_service_ok" -eq 1 ] && echo PASS || echo FAIL )" \
      "$( [ "$compose_image_ok" -eq 1 ] && echo PASS || echo FAIL )" \
      "$( [ "$compose_working_ok" -eq 1 ] && echo PASS || echo FAIL )" \
      "$( [ "$compose_config_ok" -eq 1 ] && echo PASS || echo FAIL )"
  fi

  if [ "$owned" -ne 1 ]; then
    local bind_total=0
    local bind_match_count=0
    local line

    while IFS= read -r line; do
      [ -z "$line" ] && continue
      [ "$line" = "<none>" ] && continue
      bind_total=$((bind_total + 1))
      if [ "$line" = "$expected_bind" ]; then
        bind_match_count=$((bind_match_count + 1))
      fi
    done <<EOF
$bind_sources
EOF

    printf "[baby-api] Fallback image: observed='%s' | expected='%s' => %s\n" "$image" "$expected_image" "$( [ "$image" = "$expected_image" ] && echo PASS || echo FAIL )"
    printf "[baby-api] Fallback total bind sources: observed=%d | expected=1 => %s\n" "$bind_total" "$( [ "$bind_total" -eq 1 ] && echo PASS || echo FAIL )"
    printf "[baby-api] Fallback expected bind: observed exact matches=%d | expected path='%s' => %s\n" "$bind_match_count" "$expected_bind" "$( [ "$bind_match_count" -eq 1 ] && echo PASS || echo FAIL )"

    if [ "$image" = "$expected_image" ] && [ "$bind_total" -eq 1 ] && [ "$bind_match_count" -eq 1 ]; then
      owned=1
      identity_source="image-single-bind-exact-identity"
      echo "[baby-api] Fallback identity check: PASS"
    else
      echo "[baby-api] Fallback identity check: FAIL"
    fi
  fi

  if [ "$owned" -ne 1 ]; then
    echo "[baby-api] FAILURE_DETAIL=baby_api_container_identity=unverified"
    echo "[baby-api] Existing /baby-api container is not verified as Dominion-managed; refusing removal"
    return 1
  fi

  echo "[baby-api] Ownership verified: yes"
  echo "[baby-api] identity_source=${identity_source}"
  echo "[baby-api] Would run: docker rm --force ${container_id}"
  return 0
}

main() {
  local failures=0

  echo "DRY RUN (strict): foundation-vm reconcile phase (non-destructive)"

  dry_reconcile_governed_wix_container || {
    echo "[wix-agent] reconcile returned non-zero"
    failures=$((failures + 1))
  }

  dry_reconcile_governed_dominion_web_container || {
    echo "[dominion-web] reconcile returned non-zero"
    failures=$((failures + 1))
  }

  dry_reconcile_governed_baby_logger_container || {
    echo "[baby-logger] reconcile returned non-zero"
    failures=$((failures + 1))
  }

  dry_reconcile_governed_baby_api_container || {
    echo "[baby-api] reconcile returned non-zero"
    failures=$((failures + 1))
  }

  echo "DRY RUN complete. failures=${failures}"

  if [ "$failures" -ne 0 ]; then
    return 1
  fi

  return 0
}

main "$@"

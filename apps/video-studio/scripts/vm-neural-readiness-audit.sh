#!/usr/bin/env bash
set -euo pipefail

OUT="${1:-$HOME/neural-worker-readiness-report.txt}"
umask 077

have() { command -v "$1" >/dev/null 2>&1; }

{
  echo "audit=dominion_video_studio_neural_worker_readiness"
  echo "timestamp_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "hostname=$(hostname)"
  echo "kernel=$(uname -srmo)"
  echo "arch=$(uname -m)"
  echo "cpu_threads=$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo unknown)"
  echo "memory_kib=$(awk '/MemTotal/ {print $2}' /proc/meminfo 2>/dev/null || echo unknown)"
  echo "disk_root=$(df -Pk / | awk 'NR==2 {print $2":"$3":"$4}')"

  if have nvidia-smi; then
    echo "nvidia_smi=present"
    nvidia-smi --query-gpu=name,driver_version,memory.total,compute_cap --format=csv,noheader,nounits 2>/dev/null \
      | sed 's/^/gpu=/' || echo "gpu=query_failed"
  else
    echo "nvidia_smi=absent"
  fi

  if have lspci; then
    gpu_lines=$(lspci 2>/dev/null | grep -Ei 'vga|3d|display' || true)
    if [[ -n "$gpu_lines" ]]; then
      while IFS= read -r line; do echo "display_controller=$line"; done <<< "$gpu_lines"
    else
      echo "display_controller=none_detected"
    fi
  else
    echo "lspci=absent"
  fi

  if have docker; then
    echo "docker=present"
    docker version --format 'docker_server={{.Server.Version}}' 2>/dev/null || echo "docker_server=unavailable"
    docker info --format 'docker_runtimes={{json .Runtimes}}' 2>/dev/null || echo "docker_runtimes=unavailable"
  else
    echo "docker=absent"
  fi

  if [[ -e /dev/nvidia0 ]]; then
    echo "nvidia_device=present"
  else
    echo "nvidia_device=absent"
  fi

  echo "paid_gpu_authorized=false"
  echo "installation_performed=false"
  echo "media_processed=false"
  echo "public_exposure=false"
} > "$OUT"

chmod 600 "$OUT"
cat "$OUT"

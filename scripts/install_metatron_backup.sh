#!/usr/bin/env bash
set -euo pipefail

# Dominion pinned backup intelligence layer.
# Upstream: https://github.com/kerbelp/metatron
# License: MIT
# Pinned release: v0.12.0

METATRON_VERSION="v0.12.0"
METATRON_REPO="https://github.com/kerbelp/metatron.git"
INSTALL_ROOT="${INSTALL_ROOT:-$HOME/dominion-tools}"
TARGET_DIR="$INSTALL_ROOT/metatron"

command -v git >/dev/null 2>&1 || { echo "git is required"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "python3 is required"; exit 1; }

mkdir -p "$INSTALL_ROOT"

if [ -d "$TARGET_DIR/.git" ]; then
  git -C "$TARGET_DIR" fetch --tags --prune origin
else
  git clone --filter=blob:none "$METATRON_REPO" "$TARGET_DIR"
fi

git -C "$TARGET_DIR" checkout --detach "$METATRON_VERSION"

if command -v uv >/dev/null 2>&1; then
  (
    cd "$TARGET_DIR"
    uv sync --frozen
  )
else
  python3 -m venv "$TARGET_DIR/.venv"
  "$TARGET_DIR/.venv/bin/python" -m pip install --upgrade pip
  "$TARGET_DIR/.venv/bin/python" -m pip install "getmetatron==0.12.0"
fi

cat <<EOF
METATRON_BACKUP_READY
version=$METATRON_VERSION
path=$TARGET_DIR
upstream=$METATRON_REPO
EOF

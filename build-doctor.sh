#!/usr/bin/env bash
set -euo pipefail
echo "Dominion Ark: Doctor setup"

# Ensure we are in the repo. This script is diagnostic/setup only; it must not
# mutate Git history or push production branches.
if [ ! -d "$HOME/ai/.git" ]; then
  echo "Repo not found in current context; switching to ~/ai..."
  cd ~/ai || { echo "Repo not found at ~/ai"; exit 1; }
fi

# Empire Doctor command
sudo tee /usr/local/bin/empire-doctor >/dev/null <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
echo "=== Dominion Empire Doctor ==="
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo
for svc in daily-content.service shopify-sync.service; do
  if systemctl list-unit-files | grep -q "$svc"; then
    echo "== $svc =="
    systemctl status "$svc" --no-pager -l | head -n 15 || true
    journalctl -u "$svc" -n 20 --no-pager || true
    echo
  fi
done
EOF
sudo chmod +x /usr/local/bin/empire-doctor

# Provenance is reported, never changed here. Backups/commits/pushes must use a
# separately governed workflow with explicit authority and review.
echo "REPO_HEAD=$(git rev-parse HEAD)"
echo "REPO_BRANCH=$(git branch --show-current)"
if [ -n "$(git status --porcelain)" ]; then
  echo "REPO_WORKTREE=DIRTY"
else
  echo "REPO_WORKTREE=CLEAN"
fi

echo "Doctor setup complete."
echo "Use: empire-doctor   # check containers + logs"
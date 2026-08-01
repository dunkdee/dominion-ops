#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Run as root: sudo bash scripts/ready_now.sh" >&2
  exit 2
fi

SRC=$(cd "$(dirname "$0")/.." && pwd)
DEST=/opt/orion-extreme

echo "[1/6] Installing ORION with backup and hardened systemd service..."
bash "$SRC/scripts/install.sh"

echo "[2/6] Pairing the owner Telegram account..."
python3 "$DEST/scripts/configure_telegram.py" --env "$DEST/.env"
chown orion:orion "$DEST/.env"
chmod 0600 "$DEST/.env"

echo "[3/6] Enabling live public crypto scanning (signals only; no broker clicks)..."
systemctl enable --now orion-extreme-v3-scanner.service

echo "[4/6] Restarting services with Telegram configuration..."
systemctl restart orion-extreme-v3.service
systemctl restart orion-extreme-v3-scanner.service
sleep 3

echo "[5/6] Running readiness checks..."
runuser -u orion -- env $(grep -v '^#' "$DEST/.env" | xargs) "$DEST/.venv/bin/python" "$DEST/orion_production.py" --doctor
curl -fsS http://127.0.0.1:5070/health >/dev/null
systemctl is-active --quiet orion-extreme-v3.service
systemctl is-active --quiet orion-extreme-v3-scanner.service

echo "[6/6] Ready. Open Telegram and send:"
echo "  /status"
echo "  /mode paper"
echo "  /capital 1000"
echo "  /payout 85"
echo "  /arm"
echo ""
echo "ORION is now listening to live public crypto data and sending qualified alerts."
echo "Execution remains manual, as required by the qualification standard."

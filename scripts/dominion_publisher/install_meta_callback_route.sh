#!/usr/bin/env bash
set -Eeuo pipefail

: "${RUN_SHA:?RUN_SHA is required}"

state_root="$HOME/.dominion/publisher"
receipts="$state_root/receipts"
backup_root="$state_root/backups/meta-callback-${RUN_SHA:0:12}-$(date -u +%Y%m%dT%H%M%SZ)"
caddy_path="/etc/caddy/Caddyfile"
origin_marker='dominionhealing.org, www.dominionhealing.org {'
matcher='@dominion_publisher_meta_callback'
public_url='https://dominionhealing.org/oauth/meta/callback'
upstream='127.0.0.1:5112'
success=0

mkdir -p "$receipts" "$backup_root"
chmod 700 "$state_root" "$receipts" "$backup_root"
sudo test -f "$caddy_path"
sudo systemctl is-active --quiet dominion-publisher.service
local_code="$(curl -sS -o /tmp/dominion-publisher-callback-local.$$ -w '%{http_code}' --max-time 5 \
  http://127.0.0.1:5112/oauth/meta/callback || true)"
[ "$local_code" = 400 ]
grep -q 'Missing code or state' /tmp/dominion-publisher-callback-local.$$
rm -f /tmp/dominion-publisher-callback-local.$$

sudo cp -a "$caddy_path" "$backup_root/Caddyfile"
sudo chown "$(id -un):$(id -gn)" "$backup_root/Caddyfile"

rollback() {
  rc=$?
  [ "$success" -eq 1 ] && exit "$rc"
  trap - ERR INT TERM EXIT
  set +e
  if [ -f "$backup_root/Caddyfile" ]; then
    sudo install -m 644 "$backup_root/Caddyfile" "$caddy_path"
    sudo caddy validate --config "$caddy_path" --adapter caddyfile >/dev/null 2>&1 \
      && sudo systemctl reload caddy >/dev/null 2>&1 || true
  fi
  rm -f /tmp/dominion-publisher-callback-public.$$
  echo "DOMINION_PUBLISHER_META_CALLBACK_ROLLBACK=COMPLETE rc=$rc"
  exit "$rc"
}
trap rollback ERR INT TERM EXIT

sudo python3 - "$caddy_path" "$origin_marker" "$matcher" "$upstream" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
marker = sys.argv[2]
matcher = sys.argv[3]
upstream = sys.argv[4]
text = path.read_text(encoding="utf-8")
route = (
    "\n\t@dominion_publisher_meta_callback path /oauth/meta/callback\n"
    "\treverse_proxy @dominion_publisher_meta_callback 127.0.0.1:5112\n"
)

if matcher in text:
    if text.count(matcher) != 2:
        raise SystemExit("publisher Meta callback matcher is duplicated or malformed")
    if "reverse_proxy @dominion_publisher_meta_callback 127.0.0.1:5112" not in text:
        raise SystemExit("publisher Meta callback upstream drift detected")
else:
    if text.count(marker) != 1:
        raise SystemExit("Dominion origin marker is not unique")
    text = text.replace(marker, marker + route, 1)
    path.write_text(text, encoding="utf-8")
PY

sudo caddy validate --config "$caddy_path" --adapter caddyfile >/dev/null
sudo systemctl reload caddy

public_code="$(curl -sS -o /tmp/dominion-publisher-callback-public.$$ -w '%{http_code}' --max-time 12 \
  "$public_url" || true)"
[ "$public_code" = 400 ]
grep -q 'Missing code or state' /tmp/dominion-publisher-callback-public.$$
rm -f /tmp/dominion-publisher-callback-public.$$

receipt="$receipts/$(date -u +%Y%m%dT%H%M%SZ)-meta-callback-${RUN_SHA:0:12}.json"
RUN_SHA_VALUE="$RUN_SHA" PUBLIC_URL_VALUE="$public_url" UPSTREAM_VALUE="$upstream" python3 - "$receipt" <<'PY'
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

p = Path(sys.argv[1])
data = {
    "schema": "dominion-publisher-meta-callback-route-v1",
    "status": "PASS",
    "release_sha": os.environ["RUN_SHA_VALUE"],
    "public_url": os.environ["PUBLIC_URL_VALUE"],
    "upstream": os.environ["UPSTREAM_VALUE"],
    "public_probe": "HTTP_400_EXPECTED_MISSING_STATE",
    "observed_at": datetime.now(timezone.utc).isoformat(),
}
p.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
os.chmod(p, 0o600)
PY

success=1
trap - ERR INT TERM EXIT
printf 'DOMINION_PUBLISHER_META_CALLBACK=PASS release_sha=%s public_url=%s upstream=%s\n' \
  "$RUN_SHA" "$public_url" "$upstream"

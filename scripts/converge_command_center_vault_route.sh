#!/usr/bin/env bash
set -Eeuo pipefail

CADDYFILE="${CADDYFILE:-/etc/caddy/Caddyfile}"
VAULT_HOST="${VAULT_HOST:-vault.dominionhealing.org}"
COMMAND_CENTER_UPSTREAM="${COMMAND_CENTER_UPSTREAM:-127.0.0.1:8091}"

sudo test -f "$CADDYFILE" || { echo "COMMAND_CENTER_VAULT_ROUTE=FAIL reason=caddyfile_missing"; exit 1; }
sudo test ! -L "$CADDYFILE" || { echo "COMMAND_CENTER_VAULT_ROUTE=FAIL reason=caddyfile_symlink"; exit 1; }

sudo python3 - "$CADDYFILE" "$VAULT_HOST" "$COMMAND_CENTER_UPSTREAM" <<'PY'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
host = sys.argv[2]
upstream = sys.argv[3]
text = path.read_text(encoding="utf-8")
lines = text.splitlines(keepends=True)
starts = [i for i, line in enumerate(lines) if line.strip() == f"{host} {{"]
if len(starts) != 1:
    raise SystemExit(f"VAULT_ROUTE_EXPECTED_ONE_BLOCK found={len(starts)}")
start = starts[0]
depth = 0
end = None
for i in range(start, len(lines)):
    depth += lines[i].count("{") - lines[i].count("}")
    if depth == 0:
        end = i + 1
        break
if end is None:
    raise SystemExit("VAULT_ROUTE_UNBALANCED")
block = "".join(lines[start:end])
match = re.search(r"(?ms)^\s*basicauth\s*\{\s*\n\s*dominion\s+(\S+)\s*\n\s*\}\s*", block)
if not match:
    match = re.search(r"(?ms)^\s*basic_auth\s*\{\s*\n\s*dominion\s+(\S+)\s*\n\s*\}\s*", block)
if not match:
    raise SystemExit("VAULT_ROUTE_BASIC_AUTH_NOT_FOUND")
password_hash = match.group(1)
new_block = (
    f"{host} {{\n"
    "    basicauth {\n"
    f"        dominion {password_hash}\n"
    "    }\n"
    "    redir /command-center /command-center/ 308\n"
    "    handle_path /command-center/* {\n"
    f"        reverse_proxy {upstream} {{\n"
    "            header_up X-Forwarded-Prefix /command-center\n"
    "        }\n"
    "    }\n"
    "    handle {\n"
    "        reverse_proxy 127.0.0.1:8083\n"
    "    }\n"
    "}\n"
)
new = "".join(lines[:start]) + new_block + "".join(lines[end:])
path.write_text(new, encoding="utf-8", newline="\n")
PY

sudo caddy validate --config "$CADDYFILE" --adapter caddyfile >/dev/null
sudo systemctl reload caddy
sudo systemctl is-active --quiet caddy

echo "COMMAND_CENTER_VAULT_ROUTE=PASS host=$VAULT_HOST path=/command-center/ upstream=$COMMAND_CENTER_UPSTREAM"

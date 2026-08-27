#!/usr/bin/env bash
set -Eeuo pipefail

: "${RUN_SHA:?RUN_SHA is required}"
repo="${REPO_DIR:-$HOME/dominion-ops}"
server_src="$repo/apps/mcp-cli-server/server.py"
registry_src="$repo/governance/mcp_connector_registry.json"
state_root="$HOME/.dominion/mcp-cli"
runtime_root="$state_root/runtime"
receipts="$state_root/receipts"
server="$runtime_root/server.py"
registry="$runtime_root/connector_registry.json"
wrapper="$HOME/.local/bin/dominion-mcp"
service_name="dominion-mcp-cli.service"
unit="/etc/systemd/system/$service_name"
user_name="$(id -un)"
group_name="$(id -gn)"

cd "$repo"
test "$(git rev-parse HEAD)" = "$RUN_SHA"
test -s "$server_src"
test -s "$registry_src"
python3 -m py_compile "$server_src"
python3 - "$registry_src" <<'PY'
import json,sys
p=json.load(open(sys.argv[1],encoding='utf-8'))
assert p['schema']=='dominion-mcp-connector-registry-v1'
assert p['default_mode']=='deny'
assert p['external_mutation_enabled'] is False
assert len(p['connectors']) >= 8
for name,spec in p['connectors'].items():
    assert spec['effect']=='read_only', name
    assert spec['adapter'] in {'http_get','exec','file_read'}, name
print(f"MCP_REGISTRY=PASS connectors={len(p['connectors'])} mutation=disabled")
PY

mkdir -p "$runtime_root" "$receipts" "$HOME/.local/bin"
chmod 700 "$state_root" "$runtime_root" "$receipts" "$HOME/.local/bin"
install -m 700 "$server_src" "$server"
install -m 600 "$registry_src" "$registry"

cat > "$wrapper" <<EOF
#!/usr/bin/env bash
set -Eeuo pipefail
export DOMINION_MCP_REGISTRY='$registry'
export DOMINION_MCP_STATE_DIR='$state_root'
exec /usr/bin/python3 '$server' --stdio
EOF
chmod 700 "$wrapper"

unit_tmp="$(mktemp)"
cat > "$unit_tmp" <<EOF
[Unit]
Description=Dominion governed MCP CLI connector server
After=network-online.target
Wants=network-online.target
ConditionPathExists=$server
ConditionPathExists=$registry

[Service]
Type=simple
User=$user_name
Group=$group_name
Environment=DOMINION_MCP_REGISTRY=$registry
Environment=DOMINION_MCP_STATE_DIR=$state_root
ExecStart=/usr/bin/python3 $server --http --host 127.0.0.1 --port 8390
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=read-only
ReadWritePaths=$state_root
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
UMask=0077

[Install]
WantedBy=multi-user.target
EOF
sudo install -m 644 "$unit_tmp" "$unit"
rm -f "$unit_tmp"

sudo systemctl daemon-reload
sudo systemctl reset-failed "$service_name" >/dev/null 2>&1 || true
sudo systemctl enable --now "$service_name" >/dev/null

ready=0
for _ in $(seq 1 30); do
  if curl -fsS --max-time 4 http://127.0.0.1:8390/health >/tmp/dominion-mcp-health.$$ 2>/dev/null; then ready=1; break; fi
  sleep 1
done
test "$ready" -eq 1 || { sudo systemctl status "$service_name" --no-pager || true; sudo journalctl -u "$service_name" -n 120 --no-pager || true; echo 'MCP_CLI=FAIL reason=health_unavailable'; exit 1; }
python3 - /tmp/dominion-mcp-health.$$ <<'PY'
import json,sys
h=json.load(open(sys.argv[1],encoding='utf-8'))
assert h['status']=='ok'
assert h['protocol']=='2026-07-28'
assert h['connector_count'] >= 8
assert h['external_mutation_enabled'] is False
assert h['binding']=='loopback-only'
print(f"MCP_HEALTH=PASS protocol={h['protocol']} connectors={h['connector_count']} binding={h['binding']}")
PY
rm -f /tmp/dominion-mcp-health.$$

DISCOVER="$(printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"server/discover","params":{"_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28","io.modelcontextprotocol/clientInfo":{"name":"dominion-install","version":"1"}}}}' | "$wrapper")"
python3 - "$DISCOVER" <<'PY'
import json,sys
r=json.loads(sys.argv[1])
assert r['result']['supportedVersions'][0]=='2026-07-28'
assert 'tools' in r['result']['capabilities']
assert r['result']['_meta']['io.modelcontextprotocol/serverInfo']['name']=='dominion-mcp-cli'
print('MCP_STDIO_DISCOVERY=PASS')
PY

LIST="$(printf '%s\n' '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{"_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28"}}}' | "$wrapper")"
python3 - "$LIST" <<'PY'
import json,sys
r=json.loads(sys.argv[1])
names=[x['name'] for x in r['result']['tools']]
assert names==['dominion_connectors_list','dominion_connector_invoke']
print('MCP_TOOLS_LIST=PASS')
PY

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
receipt="$receipts/${stamp}-mcp-cli-install-${RUN_SHA:0:12}.json"
RUN_SHA_VALUE="$RUN_SHA" python3 - "$receipt" <<'PY'
import json,os,sys
from datetime import datetime,timezone
from pathlib import Path
p=Path(sys.argv[1])
data={
  'schema':'dominion-mcp-cli-install-receipt-v1',
  'status':'PASS',
  'release_sha':os.environ['RUN_SHA_VALUE'],
  'protocol':'2026-07-28',
  'binding':'127.0.0.1:8390',
  'external_mutation_enabled':False,
  'observed_at':datetime.now(timezone.utc).isoformat(),
}
p.write_text(json.dumps(data,indent=2,sort_keys=True)+'\n',encoding='utf-8')
os.chmod(p,0o600)
PY

sudo systemctl is-active --quiet "$service_name"
sudo systemctl is-enabled --quiet "$service_name"
printf 'DOMINION_MCP_CLI=PASS release_sha=%s protocol=2026-07-28 endpoint=http://127.0.0.1:8390 cli=%s registry=%s service=%s\n' "$RUN_SHA" "$wrapper" "$registry" "$service_name"

#!/usr/bin/env bash
set -Eeuo pipefail

: "${ASSET_ROOT:?ASSET_ROOT is required}"
: "${RUN_ID:?RUN_ID is required}"
: "${OBSIDIAN_PASSWORD:?OBSIDIAN_PASSWORD is required}"

asset_root="$(cd "$ASSET_ROOT" && pwd)"
test -f "$asset_root/obsidian/00-DOMINION-COMMAND-CENTER.md"
test -d "$asset_root/obsidian/command-center"
test -f "$asset_root/obsidian/dominion.css"
test -f "$asset_root/obsidian/dominion-motion.css"
test -f "$asset_root/obsidian/dominion-golden-ratio.css"

mount_sources="$(docker inspect obsidian-remote --format '{{range .Mounts}}{{if eq .Destination "/vaults/Dominion"}}{{println .Source}}{{end}}{{end}}')"
mount_count="$(printf '%s\n' "$mount_sources" | sed '/^[[:space:]]*$/d' | wc -l | tr -d ' ')"
test "$mount_count" = 1 || { echo "DOMINION_UI=FAIL reason=canonical_vault_mount_count count=$mount_count"; exit 1; }
vault="$(printf '%s\n' "$mount_sources" | sed '/^[[:space:]]*$/d' | head -n1)"
test -n "$vault"
test -d "$vault"
test ! -L "$vault"
test -d "$vault/Dominion-Brain"
test ! -L "$vault/Dominion-Brain"

canonical_vault="$(cd "$vault" && pwd -P)"
brain_root="$(cd "$vault/Dominion-Brain" && pwd -P)"
case "$brain_root" in "$canonical_vault"/*) ;; *) echo "DOMINION_UI=FAIL reason=brain_outside_canonical_vault"; exit 1;; esac

target="$vault/Dominion-Command-Center"
root_note="$vault/00-DOMINION-COMMAND-CENTER.md"
obsidian_dir="$vault/.obsidian"
snippet_dir="$obsidian_dir/snippets"
snippet="$snippet_dir/dominion.css"
appearance="$obsidian_dir/appearance.json"
stage="$vault/.dominion-command-center-stage-$RUN_ID"
backup="$vault/.dominion-command-center-backup-$RUN_ID"

hash_brain() {
  python3 - "$vault/Dominion-Brain" <<'PY'
import hashlib,sys
from pathlib import Path
root=Path(sys.argv[1])
h=hashlib.sha256()
for p in sorted(x for x in root.rglob('*') if x.is_file() and not x.is_symlink()):
    rel=p.relative_to(root).as_posix().encode()
    h.update(rel); h.update(b'\0'); h.update(hashlib.sha256(p.read_bytes()).digest()); h.update(b'\n')
print(h.hexdigest())
PY
}

brain_before="$(hash_brain)"
test -n "$brain_before"

test ! -e "$stage"
test ! -e "$backup"
mkdir -m 700 "$stage" "$backup"

old_target=0
old_root=0
old_snippet=0
old_appearance=0
published=0

if [ -e "$target" ]; then
  test -d "$target" && test ! -L "$target"
  cp -a "$target" "$backup/command-center"
  old_target=1
fi
if [ -f "$root_note" ]; then cp -a "$root_note" "$backup/root-note.md"; old_root=1; fi
if [ -f "$snippet" ]; then mkdir -p "$backup/snippets"; cp -a "$snippet" "$backup/snippets/dominion.css"; old_snippet=1; fi
if [ -f "$appearance" ]; then cp -a "$appearance" "$backup/appearance.json"; old_appearance=1; fi

rollback() {
  set +e
  if [ "$published" -eq 1 ]; then
    rm -rf "$target"
    rm -f "$root_note" "$snippet"
    if [ "$old_target" -eq 1 ]; then mv "$backup/command-center" "$target"; fi
    if [ "$old_root" -eq 1 ]; then cp -a "$backup/root-note.md" "$root_note"; fi
    if [ "$old_snippet" -eq 1 ]; then mkdir -p "$snippet_dir"; cp -a "$backup/snippets/dominion.css" "$snippet"; fi
    if [ "$old_appearance" -eq 1 ]; then cp -a "$backup/appearance.json" "$appearance"; else rm -f "$appearance"; fi
    docker restart obsidian-remote >/dev/null 2>&1 || true
  fi
  rm -rf "$stage" "$backup"
  echo "DOMINION_UI_ROLLBACK=PASS"
}

on_error() {
  rc=$?
  trap - ERR
  rollback
  exit "$rc"
}
trap on_error ERR

cp -a "$asset_root/obsidian/command-center/." "$stage/"
for required in 00-HOME.md 03-Control-Plane.md 04-Agents.md 06-Operations.md 07-Incidents.md 08-Evidence.md 09-Revenue.md 10-Architecture.md 11-SOPs.md 12-Decisions.md 13-Learning.md 14-Daily-State.md 15-Founder-Oversight.md 16-Production-Matrix.md 17-MCP-CLI-Connector.md 99-System-Map.md; do
  test -s "$stage/$required"
done

if [ -e "$target" ]; then rm -rf "$target"; fi
mv "$stage" "$target"
cp -a "$asset_root/obsidian/00-DOMINION-COMMAND-CENTER.md" "$root_note"
mkdir -p "$snippet_dir"
cat "$asset_root/obsidian/dominion.css" "$asset_root/obsidian/dominion-motion.css" "$asset_root/obsidian/dominion-golden-ratio.css" > "$snippet"
chmod 600 "$root_note" "$snippet"

target_root="$(cd "$target" && pwd -P)"
case "$target_root" in "$canonical_vault"/*) ;; *) echo "DOMINION_UI=FAIL reason=command_center_outside_canonical_vault"; false;; esac

python3 - "$appearance" <<'PY'
import json,os,sys,tempfile
from pathlib import Path
path=Path(sys.argv[1])
path.parent.mkdir(parents=True,exist_ok=True)
data={}
if path.is_file():
    try:
        loaded=json.loads(path.read_text(encoding='utf-8'))
        if isinstance(loaded,dict): data=loaded
    except Exception:
        data={}
snips=data.get('enabledCssSnippets',[])
if not isinstance(snips,list): snips=[]
snips=[str(x) for x in snips if str(x).strip()]
if 'dominion' not in snips: snips.append('dominion')
data['enabledCssSnippets']=snips
fd,tmp=tempfile.mkstemp(prefix='.appearance.',suffix='.tmp',dir=str(path.parent))
try:
    with os.fdopen(fd,'w',encoding='utf-8',newline='\n') as h:
        json.dump(data,h,indent=2,sort_keys=True); h.write('\n'); h.flush(); os.fsync(h.fileno())
    os.chmod(tmp,0o600)
    os.replace(tmp,path)
finally:
    if os.path.exists(tmp): os.unlink(tmp)
PY

published=1

test -s "$root_note"
test -s "$target/00-HOME.md"
test -s "$target/14-Daily-State.md"
test -s "$target/09-Revenue.md"
test -s "$target/16-Production-Matrix.md"
test -s "$target/17-MCP-CLI-Connector.md"
test -s "$snippet"
grep -Fq 'dominion-command-center-root' "$root_note"
grep -Fq 'class="dominion-shell"' "$target/00-HOME.md"
grep -Fq '16-Production-Matrix' "$target/00-HOME.md"
grep -Fq '17-MCP-CLI-Connector' "$target/00-HOME.md"
grep -Fq 'class="dominion-card-grid' "$target/16-Production-Matrix.md"
grep -Fq 'MCP 2026-07-28' "$target/17-MCP-CLI-Connector.md"
grep -Fq '@media (max-width: 720px)' "$snippet"
grep -Fq '.dominion-mobile-dock' "$snippet"
grep -Fq '@keyframes dominion-ambient-drift' "$snippet"
grep -Fq '@keyframes dominion-orbit' "$snippet"
grep -Fq '@keyframes dominion-production-sweep' "$snippet"
grep -Fq '@media (prefers-reduced-motion: reduce)' "$snippet"
grep -Fq -- '--dominion-phi: 1.61803398875' "$snippet"
grep -Fq -- '--dominion-s9: 377px' "$snippet"
python3 - "$appearance" <<'PY'
import json,sys
from pathlib import Path
data=json.loads(Path(sys.argv[1]).read_text())
assert 'dominion' in data.get('enabledCssSnippets',[])
print('DOMINION_CSS_ENABLE=PASS golden_ratio=locked')
PY

brain_after="$(hash_brain)"
test "$brain_after" = "$brain_before" || { echo "DOMINION_UI=FAIL reason=governed_brain_changed before=$brain_before after=$brain_after"; false; }
echo "DOMINION_VAULT_CANONICAL=PASS root=$canonical_vault brain=$brain_root command_center=$target_root"

docker restart obsidian-remote >/dev/null
ready=0
for _ in $(seq 1 60); do
  state="$(docker inspect --format '{{.State.Status}}' obsidian-remote 2>/dev/null || true)"
  code="$(curl -sS -u "dominion:$OBSIDIAN_PASSWORD" -o /dev/null -w '%{http_code}' --max-time 10 http://127.0.0.1:8083/ || true)"
  if [ "$state" = running ] && [[ "$code" =~ ^(200|302)$ ]]; then ready=1; break; fi
  sleep 2
done
test "$ready" -eq 1 || { echo 'DOMINION_UI=FAIL reason=obsidian_local_health'; false; }

legacy="$(docker exec obsidian-remote sh -lc "ps -ef 2>/dev/null | grep -E '[x]rdp|[g]uacd' || true" 2>/dev/null || true)"
test -z "$legacy" || { echo 'DOMINION_UI=FAIL reason=legacy_rdp_returned'; false; }

public=0
for _ in $(seq 1 20); do
  code="$(curl -sS -u "dominion:$OBSIDIAN_PASSWORD" -o /dev/null -w '%{http_code}' --max-time 15 https://vault.dominionhealing.org/ || true)"
  if [[ "$code" =~ ^(200|302)$ ]]; then public=1; break; fi
  sleep 2
done
test "$public" -eq 1 || { echo 'DOMINION_UI=FAIL reason=public_authenticated_route'; false; }
unauth="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 https://vault.dominionhealing.org/ || true)"
test "$unauth" = 401 || { echo "DOMINION_UI=FAIL reason=public_auth_not_enforced status=$unauth"; false; }

rm -rf "$backup"
trap - ERR
printf 'DOMINION_UI=PASS vault=%s command_center=installed mcp_canopy=installed production_matrix=installed css=enabled motion=natural_restrained golden_ratio=locked brain_hash=%s public_auth=pass legacy_rdp=absent\n' "$vault" "$brain_after"

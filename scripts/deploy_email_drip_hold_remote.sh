#!/usr/bin/env bash
set -euo pipefail

: "${DEPLOY_SHA:?DEPLOY_SHA is required}"
: "${RUN_ID:?RUN_ID is required}"

repo="$HOME/dominion-ops"
target="$HOME/email_drip/email_drip.py"
lock_target="$HOME/email_drip/filelock.py"
service="dominion-email-drip.service"
env_file="$HOME/.env"
source_backup="$HOME/email_drip/email_drip.py.github-rollback-${RUN_ID}.bak"
lock_backup="$HOME/email_drip/filelock.py.github-rollback-${RUN_ID}.bak"
source_published=0
lock_published=0
lock_preexisting=0

[[ "$DEPLOY_SHA" =~ ^[0-9a-f]{40}$ ]] || { echo "EMAIL_DRIP_DEPLOY=FAIL reason=invalid_sha"; exit 1; }
test -d "$repo/.git" || { echo "EMAIL_DRIP_DEPLOY=FAIL reason=repo_missing"; exit 1; }
cd "$repo"
test "$(git rev-parse HEAD)" = "$DEPLOY_SHA" || { echo "EMAIL_DRIP_DEPLOY=FAIL reason=vm_sha_mismatch"; exit 1; }
test -f "$target" && test ! -L "$target" || { echo "EMAIL_DRIP_DEPLOY=FAIL reason=production_target_invalid"; exit 1; }
test ! -e "$source_backup" || { echo "EMAIL_DRIP_DEPLOY=FAIL reason=rollback_collision"; exit 1; }
test -f services/email_drip/filelock.py && test ! -L services/email_drip/filelock.py || { echo "EMAIL_DRIP_DEPLOY=FAIL reason=lock_shim_missing"; exit 1; }

if sudo test -e "$lock_target"; then
  sudo test -f "$lock_target" && sudo test ! -L "$lock_target" || { echo "EMAIL_DRIP_DEPLOY=FAIL reason=production_lock_target_invalid"; exit 1; }
  test ! -e "$lock_backup" || { echo "EMAIL_DRIP_DEPLOY=FAIL reason=lock_rollback_collision"; exit 1; }
  sudo cp -a "$lock_target" "$lock_backup"
  lock_preexisting=1
fi

sudo cp -a "$target" "$source_backup"
sudo python3 - "$source_backup" <<'PY'
import os,sys
with open(sys.argv[1],'rb') as f: os.fsync(f.fileno())
PY

wait_health() {
  local expected="$1" health
  for _ in $(seq 1 30); do
    if health="$(curl -fsS --max-time 2 http://127.0.0.1:8099/health 2>/dev/null)" \
      && python3 - "$health" "$expected" <<'PY' >/dev/null 2>&1
import json,sys
j=json.loads(sys.argv[1])
assert j['status']=='ok'
assert j['send_mode']==sys.argv[2]
PY
    then
      printf '%s' "$health"
      return 0
    fi
    sleep 0.5
  done
  return 1
}

service_python() {
  local pid="$1"
  sudo python3 - "$pid" <<'PY'
import pathlib,sys
raw=pathlib.Path(f'/proc/{sys.argv[1]}/cmdline').read_bytes().split(b'\0')
if not raw or not raw[0]: raise SystemExit(1)
print(raw[0].decode())
PY
}

restore_atomic() {
  local backup="$1" destination="$2"
  sudo python3 - "$backup" "$destination" <<'PY'
import os,secrets,shutil,stat,sys
from pathlib import Path
backup=Path(sys.argv[1]); target=Path(sys.argv[2]); st=backup.stat()
tmp=target.with_name(f'.{target.name}.rollback-{os.getpid()}-{secrets.token_hex(8)}.tmp')
fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,stat.S_IMODE(st.st_mode))
try:
    with os.fdopen(fd,'wb') as out, backup.open('rb') as src:
        shutil.copyfileobj(src,out); out.flush(); os.fsync(out.fileno())
    os.chown(tmp,st.st_uid,st.st_gid); os.chmod(tmp,stat.S_IMODE(st.st_mode)); os.replace(tmp,target)
    dfd=os.open(target.parent,os.O_RDONLY|getattr(os,'O_DIRECTORY',0))
    try: os.fsync(dfd)
    finally: os.close(dfd)
finally:
    if tmp.exists(): tmp.unlink()
PY
}

rollback() {
  set +e
  sudo python3 scripts/set_email_drip_runtime.py hold --env-file "$env_file" --expect either >/dev/null 2>&1
  if [ "$source_published" -eq 1 ] && sudo test -f "$source_backup"; then
    restore_atomic "$source_backup" "$target"
  fi
  if [ "$lock_published" -eq 1 ]; then
    if [ "$lock_preexisting" -eq 1 ] && sudo test -f "$lock_backup"; then
      restore_atomic "$lock_backup" "$lock_target"
    else
      sudo rm -f "$lock_target"
    fi
  fi
  sudo systemctl restart "$service" >/dev/null 2>&1
  sudo systemctl is-active --quiet "$service"
  wait_health hold >/dev/null 2>&1
  echo "EMAIL_DRIP_AUTO_ROLLBACK=PASS source_restored=$source_published lock_restored=$lock_published mode=hold"
}

on_error() {
  local rc=$?
  trap - ERR
  rollback || true
  exit "$rc"
}
trap on_error ERR

PYTHONPATH=services/email_drip python3 -m py_compile services/email_drip/filelock.py services/email_drip/email_drip.py scripts/set_email_drip_runtime.py
PYTHONPATH=services/email_drip python3 - <<'PY'
from filelock import FileLock, Timeout
assert FileLock and Timeout
PY
sudo python3 scripts/set_email_drip_runtime.py hold --env-file "$env_file" --expect either

# Publish the local lock shim first so the new service source has no external filelock dependency.
lock_published=1
sudo python3 - "$repo/services/email_drip/filelock.py" "$lock_target" "$target" <<'PY'
import os,secrets,shutil,stat,sys
from pathlib import Path
source=Path(sys.argv[1]); dest=Path(sys.argv[2]); reference=Path(sys.argv[3]); ref=reference.stat()
if not source.is_file() or source.is_symlink(): raise SystemExit('LOCK_SOURCE_INVALID')
if dest.exists() and (not dest.is_file() or dest.is_symlink()): raise SystemExit('LOCK_TARGET_INVALID')
if dest.exists():
    st=dest.stat(); uid,gid,mode=st.st_uid,st.st_gid,stat.S_IMODE(st.st_mode)
else:
    uid,gid,mode=ref.st_uid,ref.st_gid,0o644
tmp=dest.with_name(f'.{dest.name}.github-{os.getpid()}-{secrets.token_hex(8)}.tmp')
fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,mode)
try:
    with os.fdopen(fd,'wb') as out, source.open('rb') as src:
        shutil.copyfileobj(src,out); out.flush(); os.fsync(out.fileno())
    os.chown(tmp,uid,gid); os.chmod(tmp,mode); os.replace(tmp,dest)
    dfd=os.open(dest.parent,os.O_RDONLY|getattr(os,'O_DIRECTORY',0))
    try: os.fsync(dfd)
    finally: os.close(dfd)
finally:
    if tmp.exists(): tmp.unlink()
PY

source_published=1
sudo python3 - "$repo/services/email_drip/email_drip.py" "$target" "$RUN_ID" <<'PY'
import hashlib,os,secrets,shutil,stat,sys
from datetime import datetime, timezone
from pathlib import Path
source=Path(sys.argv[1]); target=Path(sys.argv[2]); run_id=sys.argv[3]
if not source.is_file() or source.is_symlink(): raise SystemExit('SOURCE_INVALID')
if not target.is_file() or target.is_symlink(): raise SystemExit('TARGET_INVALID')
st=target.stat()
def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()
pre_sha=digest(target); source_sha=digest(source)
backup=target.with_name(f"{target.name}.github-{run_id}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.bak")
shutil.copy2(target,backup); os.chown(backup,st.st_uid,st.st_gid); os.chmod(backup,stat.S_IMODE(st.st_mode))
with backup.open('rb') as f: os.fsync(f.fileno())
tmp=target.with_name(f'.{target.name}.github-{os.getpid()}-{secrets.token_hex(8)}.tmp')
fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,stat.S_IMODE(st.st_mode))
try:
    with os.fdopen(fd,'wb') as out, source.open('rb') as src:
        shutil.copyfileobj(src,out); out.flush(); os.fsync(out.fileno())
    os.chown(tmp,st.st_uid,st.st_gid); os.chmod(tmp,stat.S_IMODE(st.st_mode)); os.replace(tmp,target)
    dfd=os.open(target.parent,os.O_RDONLY|getattr(os,'O_DIRECTORY',0))
    try: os.fsync(dfd)
    finally: os.close(dfd)
finally:
    if tmp.exists(): tmp.unlink()
post_sha=digest(target)
if post_sha!=source_sha: raise SystemExit('SOURCE_HASH_VERIFY_FAIL')
final=target.stat()
if (final.st_uid,final.st_gid,stat.S_IMODE(final.st_mode))!=(st.st_uid,st.st_gid,stat.S_IMODE(st.st_mode)): raise SystemExit('TARGET_METADATA_VERIFY_FAIL')
print(f'EMAIL_DRIP_SOURCE_PUBLISH=PASS pre_sha={pre_sha} source_sha={source_sha} post_sha={post_sha} backup={backup} mode={oct(stat.S_IMODE(st.st_mode))}')
PY

sudo systemctl restart "$service"
sudo systemctl is-active --quiet "$service"
health="$(wait_health hold)"
main_pid="$(sudo systemctl show -p MainPID --value "$service")"
test "$main_pid" -gt 0
python_bin="$(service_python "$main_pid")"
test -x "$python_bin"
ss -tlnp | grep -q ':8099 '
runtime_status="$(curl -fsS --max-time 10 http://127.0.0.1:8099/api/drip-status)"
python3 - "$health" "$runtime_status" <<'PY'
import json,sys
h=json.loads(sys.argv[1]); s=json.loads(sys.argv[2])
assert h['status']=='ok' and h['send_mode']=='hold' and h['live_preflight_ok'] is False
assert s['smtp_configured'] is True and s['transport']=='smtp'
print('EMAIL_DRIP_HEALTH=PASS mode=hold smtp_configured=true')
PY

owner="$(stat -c '%U' "$target")"
target_dir="$(dirname "$target")"
planner="$(sudo -u "$owner" env PYTHONPATH="$target_dir" DRIP_SEND_MODE=hold DRIP_LIVE_PREFLIGHT_OK=false "$python_bin" - "$target" <<'PY'
import importlib.util,json,sys
from datetime import datetime,timezone
from pathlib import Path
path=Path(sys.argv[1]); spec=importlib.util.spec_from_file_location('dominion_email_drip_preflight',path)
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); r=m._build_preflight_report(now=datetime.now(timezone.utc))
print(json.dumps({'candidate_count':r['candidate_count'],'candidates':[{'book':x['book'],'step':x['step']} for x in r['candidates']],'status_counts':r['status_counts'],'free_audit_candidate_count':r['free_audit_candidate_count'],'transport_invoked':r['transport_invoked'],'state_mutated':r['state_mutated'],'total_leads':r['total_leads']},separators=(',',':'),sort_keys=True))
PY
)"
python3 - "$planner" <<'PY'
import json,sys
p=json.loads(sys.argv[1]); assert p['transport_invoked'] is False and p['state_mutated'] is False and p['free_audit_candidate_count']==0
assert p['status_counts'].get('suppression_error',0)==0
assert p['status_counts'].get('send_reconciliation_required',0)==0
assert p['status_counts'].get('invalid_send_history',0)==0
print('EMAIL_DRIP_PREFLIGHT_JSON='+json.dumps(p,separators=(',',':'),sort_keys=True))
PY

unsubscribe_status="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 https://dominionhealing.org/api/unsubscribe || true)"
case "$unsubscribe_status" in 400|401|403|405|422) ;; *) echo "EMAIL_DRIP_DEPLOY=FAIL reason=unsubscribe_route_unverified status=$unsubscribe_status"; false ;; esac

trap - ERR
rm -f "$lock_backup" 2>/dev/null || true
printf 'EMAIL_DRIP_DEPLOY=PASS sha=%s service=active pid=%s port=8099 send_mode=hold smtp_configured=true unsubscribe_status=%s rollback=%s\n' "$DEPLOY_SHA" "$main_pid" "$unsubscribe_status" "$source_backup"

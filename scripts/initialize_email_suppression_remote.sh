#!/usr/bin/env bash
set -euo pipefail

home="$HOME"
target="$home/buddy_core/email_suppression.json"

sudo python3 - "$home" "$target" <<'PY'
import hashlib
import json
import os
import secrets
import stat
import sys
from pathlib import Path

home=Path(sys.argv[1]).resolve()
target=Path(sys.argv[2])
parent=target.parent

if not parent.is_dir() or parent.is_symlink():
    raise SystemExit('EMAIL_DRIP_SUPPRESSION_INIT=FAIL reason=parent_invalid')
try:
    target.resolve().relative_to(home)
except ValueError:
    raise SystemExit('EMAIL_DRIP_SUPPRESSION_INIT=FAIL reason=target_outside_home')


def validate(path: Path):
    if not path.is_file() or path.is_symlink():
        raise SystemExit('EMAIL_DRIP_SUPPRESSION_INIT=FAIL reason=target_invalid')
    try:
        data=json.loads(path.read_text(encoding='utf-8'))
    except Exception as exc:
        raise SystemExit(f'EMAIL_DRIP_SUPPRESSION_INIT=FAIL reason=json_invalid error_type={type(exc).__name__}')
    emails=data.get('emails') if isinstance(data,dict) else None
    if not isinstance(emails,list) or any(not isinstance(item,str) for item in emails):
        raise SystemExit('EMAIL_DRIP_SUPPRESSION_INIT=FAIL reason=schema_invalid')
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    print(f'EMAIL_DRIP_SUPPRESSION_INIT=PASS state=existing count={len(emails)} sha256={digest}')


if target.exists() or target.is_symlink():
    validate(target)
    raise SystemExit(0)

# Inventory before initialization. Never silently create an empty store if an
# alternate canonical-looking suppression file already exists in runtime roots.
roots=[home/'buddy_core',home/'email_drip',home/'.local'/'state']
alternates=[]
for root in roots:
    if not root.exists():
        continue
    for base,dirs,files in os.walk(root):
        dirs[:]=[d for d in dirs if d not in {'.git','venv','.venv','__pycache__','node_modules'}]
        for name in files:
            if name != 'email_suppression.json':
                continue
            candidate=Path(base)/name
            try:
                resolved=candidate.resolve()
            except OSError:
                continue
            if resolved != target.resolve():
                alternates.append(str(resolved.relative_to(home)) if resolved.is_relative_to(home) else str(resolved))
if alternates:
    print('EMAIL_DRIP_SUPPRESSION_INIT=HOLD reason=alternate_store_found count='+str(len(alternates)))
    raise SystemExit(2)

pst=parent.stat()
tmp=parent/f'.{target.name}.init-{os.getpid()}-{secrets.token_hex(8)}.tmp'
fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
try:
    with os.fdopen(fd,'w',encoding='utf-8') as handle:
        json.dump({'emails':[]},handle,separators=(',',':'),sort_keys=True)
        handle.write('\n')
        handle.flush()
        os.fsync(handle.fileno())
    os.chown(tmp,pst.st_uid,pst.st_gid)
    os.chmod(tmp,0o600)
    os.replace(tmp,target)
    dfd=os.open(parent,os.O_RDONLY|getattr(os,'O_DIRECTORY',0))
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)
finally:
    if tmp.exists():
        tmp.unlink()

validate(target)
PY

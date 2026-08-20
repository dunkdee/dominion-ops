#!/usr/bin/env python3
"""One-purpose source patch for Buddy web -> BuddyOperator integration.

Fails if canonical source markers are not exact. This avoids hand-rewriting the
large embedded HTML/JS surface and prevents broad/ambiguous source mutation.
"""
from pathlib import Path

PATH = Path("buddy_core/buddy_web.py")
text = PATH.read_text(encoding="utf-8")

replacements = [
    (
        'from core.brain import ask, status as brain_status, BUDDY_SYSTEM\n',
        'from core.brain import status as brain_status\nfrom core.operator import get_operator\n',
    ),
    (
        'BUDDY_WEB_TOKEN = os.getenv("BUDDY_WEB_TOKEN", "")\n',
        'BUDDY_WEB_TOKEN = os.getenv("BUDDY_WEB_TOKEN", "").strip()\n'
        'BUDDY_ALLOW_OPEN_DEV = os.getenv("BUDDY_ALLOW_OPEN_DEV", "0").strip().lower() in {"1", "true", "yes"}\n',
    ),
    (
        '    if not BUDDY_WEB_TOKEN:\n        return  # No token configured = open (dev mode)\n',
        '    if not BUDDY_WEB_TOKEN:\n'
        '        # Fail closed by default. Explicit open-dev is loopback only.\n'
        '        host = request.client.host if request.client else ""\n'
        '        if BUDDY_ALLOW_OPEN_DEV and host in {"127.0.0.1", "::1", "localhost"}:\n'
        '            return\n'
        '        raise HTTPException(status_code=503, detail="Buddy authentication is not configured")\n',
    ),
    (
        '    try:\n        response = ask(full_prompt)\n    except Exception as e:\n        response = f"Brain error: {e}"\n',
        '    try:\n'
        '        operator_result = get_operator().handle(message, session_id=session_id)\n'
        '        response = operator_result.get("response") or "Buddy completed the request without a text summary."\n'
        '    except Exception as e:\n'
        '        operator_result = {"status": "BLOCKED", "error": type(e).__name__}\n'
        '        response = f"Operator blocked: {type(e).__name__}"\n',
    ),
    (
        '    return JSONResponse({"response": response, "session_id": session_id})\n',
        '    payload = {"response": response, "session_id": session_id}\n'
        '    for key in ("status", "mission_id", "held", "receipts", "evidence"):\n'
        '        if key in operator_result:\n'
        '            payload[key] = operator_result[key]\n'
        '    return JSONResponse(payload)\n',
    ),
    (
        '@app.get("/buddy/api/status")\ndef buddy_status():\n    return JSONResponse(brain_status())\n',
        '@app.get("/buddy/api/status")\ndef buddy_status(request: Request):\n'
        '    verify_token(request)\n'
        '    data = brain_status()\n'
        '    data["operator"] = "v2"\n'
        '    data["capability_count"] = len(get_operator().capabilities)\n'
        '    return JSONResponse(data)\n',
    ),
]

for old, new in replacements:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected exactly one canonical marker, found {count}: {old[:80]!r}")
    text = text.replace(old, new, 1)

# Structural assertions: old raw-chat dispatch must be gone, operator path present.
required = [
    "from core.operator import get_operator",
    "get_operator().handle(message, session_id=session_id)",
    'data["operator"] = "v2"',
    "Buddy authentication is not configured",
]
for marker in required:
    if marker not in text:
        raise SystemExit(f"required marker missing after patch: {marker}")
if "response = ask(full_prompt)" in text:
    raise SystemExit("raw chat ask() dispatch still present")

PATH.write_text(text, encoding="utf-8")
print("BUDDY_WEB_OPERATOR_WIRING=STAGED")

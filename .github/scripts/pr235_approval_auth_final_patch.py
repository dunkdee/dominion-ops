from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    src = p.read_text(encoding="utf-8")
    count = src.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one match, found {count}: {old[:100]!r}")
    p.write_text(src.replace(old, new, 1), encoding="utf-8")


# Founder approval/resume must never inherit the loopback open-dev bypass.
replace_once(
    "buddy_core/buddy_web.py",
    '''def verify_token(request: Request):
    """Fail-closed auth for every Buddy surface.

    Accepts, in order: a signed phone session cookie, a bearer token, an
    X-Buddy-Token header, ?token=, or the legacy buddy_token cookie.
    """
    if not BUDDY_WEB_TOKEN:
        # Fail closed by default. Explicit open-dev is loopback only.
        host = request.client.host if request.client else ""
        if BUDDY_ALLOW_OPEN_DEV and host in {"127.0.0.1", "::1", "localhost"}:
            return
        raise HTTPException(status_code=503, detail="Buddy authentication is not configured")
    if is_authenticated(request):
        return
    raise HTTPException(status_code=401, detail="Unauthorized")
''',
    '''def verify_token(request: Request):
    """Fail-closed auth for ordinary Buddy surfaces.

    Accepts, in order: a signed phone session cookie, a bearer token, an
    X-Buddy-Token header, ?token=, or the legacy buddy_token cookie. The
    loopback open-dev exception is intentionally limited to non-authority
    operations; Founder approval/resume uses verify_founder_authority().
    """
    if not BUDDY_WEB_TOKEN:
        # Fail closed by default. Explicit open-dev is loopback only.
        host = request.client.host if request.client else ""
        if BUDDY_ALLOW_OPEN_DEV and host in {"127.0.0.1", "::1", "localhost"}:
            return
        raise HTTPException(status_code=503, detail="Buddy authentication is not configured")
    if is_authenticated(request):
        return
    raise HTTPException(status_code=401, detail="Unauthorized")


def verify_founder_authority(request: Request):
    """Require configured, real authentication for authority-changing calls.

    BUDDY_ALLOW_OPEN_DEV must never grant or resume Founder authority, even
    from loopback. A valid signed session or master token is required.
    """
    if not BUDDY_WEB_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="Founder approval authentication is not configured",
        )
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Founder approval requires authentication")
''',
)

replace_once(
    "buddy_core/buddy_web.py",
    '''    if body.get("approve") is True and approval_id:
        result = get_operator().grant_and_resume(
''',
    '''    if body.get("approve") is True and approval_id:
        verify_founder_authority(request)
        result = get_operator().grant_and_resume(
''',
)

# Remove confusing standalone line-continuation markers from regression modules.
for test_path in (
    "tests/test_pr235_final_authority_closure.py",
    "tests/test_watchmen_review_closure.py",
):
    p = Path(test_path)
    src = p.read_text(encoding="utf-8")
    if src.startswith("\\\n"):
        p.write_text(src[2:], encoding="utf-8")
    elif src.startswith('"""'):
        pass
    else:
        raise SystemExit(f"{test_path}: unexpected file prefix")

# Add a focused authority-boundary regression without relying on network state.
Path("tests/test_pr235_approval_auth_boundary.py").write_text(
    '''"""Final regression for Founder approval authentication on PR #235."""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest import mock

from fastapi import HTTPException

from buddy_core import buddy_web


class FounderApprovalAuthBoundaryTests(unittest.TestCase):
    def _request(self):
        return SimpleNamespace(
            client=SimpleNamespace(host="127.0.0.1"),
            headers={},
            query_params={},
            cookies={},
        )

    def test_open_dev_cannot_substitute_for_founder_authentication(self):
        request = self._request()
        with mock.patch.object(buddy_web, "BUDDY_WEB_TOKEN", ""), \\
             mock.patch.object(buddy_web, "BUDDY_ALLOW_OPEN_DEV", True):
            # Ordinary dev access may pass on loopback...
            self.assertIsNone(buddy_web.verify_token(request))
            # ...but authority mutation must still fail closed.
            with self.assertRaises(HTTPException) as ctx:
                buddy_web.verify_founder_authority(request)
            self.assertEqual(ctx.exception.status_code, 503)

    def test_configured_token_still_requires_authenticated_request(self):
        request = self._request()
        with mock.patch.object(buddy_web, "BUDDY_WEB_TOKEN", "configured-secret"), \\
             mock.patch.object(buddy_web, "is_authenticated", return_value=False):
            with self.assertRaises(HTTPException) as ctx:
                buddy_web.verify_founder_authority(request)
            self.assertEqual(ctx.exception.status_code, 401)

    def test_authenticated_request_is_allowed_to_reach_authority_layer(self):
        request = self._request()
        with mock.patch.object(buddy_web, "BUDDY_WEB_TOKEN", "configured-secret"), \\
             mock.patch.object(buddy_web, "is_authenticated", return_value=True):
            self.assertIsNone(buddy_web.verify_founder_authority(request))


if __name__ == "__main__":
    unittest.main()
''',
    encoding="utf-8",
)

print("PR235_APPROVAL_AUTH_FINAL_PATCH=APPLIED")

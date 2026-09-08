"""Provision the Meta app credentials into the encrypted vault.

Two entry paths, one destination:

  interactive (default)  a terminal prompt, secret masked by getpass
  --stdin                a JSON payload on standard input

The stdin path exists so the governed workflow can provision from GitHub
Secrets when the Founder is nowhere near the VM. The payload arrives on stdin
and never on the command line, so it is not visible in `ps` on the VM, and it
is never written to a file or echoed. Both paths write through the same shared
vault_root(), so the service reads exactly what was written.
"""

from __future__ import annotations

import getpass
import json
import sys
from pathlib import Path

from .paths import vault_root

DEFAULT_REDIRECT_URI = "https://dominionhealing.org/oauth/meta/callback"
DEFAULT_GRAPH_VERSION = "v25.0"


class PayloadError(ValueError):
    """The supplied credential payload is unusable. Never carries the secret."""


def _prompt(label: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{label}{suffix}: ").strip()
    return value or (default or "")


def read_stdin_payload(stream) -> dict:
    """Parse a credential payload from a stream.

    Returns the four settings. Raises PayloadError with a message that never
    quotes the payload, so a malformed secret cannot leak through the error.
    """
    raw = stream.read()
    if not raw or not raw.strip():
        raise PayloadError("no credential payload was supplied on stdin")
    try:
        parsed = json.loads(raw)
    except ValueError:
        raise PayloadError("credential payload on stdin is not valid JSON") from None
    if not isinstance(parsed, dict):
        raise PayloadError("credential payload must be a JSON object")

    app_id = str(parsed.get("app_id") or "").strip()
    app_secret = str(parsed.get("app_secret") or "").strip()
    redirect_uri = str(parsed.get("redirect_uri") or DEFAULT_REDIRECT_URI).strip()
    graph_version = str(parsed.get("graph_version") or DEFAULT_GRAPH_VERSION).strip()
    # Optional: only Facebook Login for Business apps have one.
    config_id = str(parsed.get("config_id") or "").strip()

    missing = [
        name for name, value in (("app_id", app_id), ("app_secret", app_secret))
        if not value
    ]
    if missing:
        raise PayloadError(f"credential payload is missing: {', '.join(missing)}")

    return {
        "app_id": app_id,
        "app_secret": app_secret,
        "redirect_uri": redirect_uri,
        "graph_version": graph_version,
        "config_id": config_id,
    }


def _interactive_payload() -> dict:
    return {
        "app_id": _prompt("Meta App ID"),
        "app_secret": getpass.getpass("Meta App Secret (hidden): ").strip(),
        "redirect_uri": _prompt("Meta OAuth redirect URI", DEFAULT_REDIRECT_URI),
        "graph_version": _prompt("Meta Graph API version", DEFAULT_GRAPH_VERSION),
        "config_id": _prompt("Facebook Login for Business configuration id (blank for classic login)"),
    }


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    # Imported here rather than at module scope so this module stays importable
    # -- and its payload handling stays testable -- without the cryptography
    # extension being loadable.
    from .vault import CredentialVault

    if "--stdin" in args:
        try:
            payload = read_stdin_payload(sys.stdin)
        except PayloadError as exc:
            print(f"META_APP_CONFIGURED=FAIL reason={exc}", file=sys.stderr)
            return 2
    else:
        payload = _interactive_payload()

    # Same helper the service uses, so credentials are always written where
    # the service reads them.
    vault_dir: Path = vault_root()
    vault = CredentialVault(vault_dir)
    try:
        vault.configure_meta_app(
            app_id=payload["app_id"],
            app_secret=payload["app_secret"],
            redirect_uri=payload["redirect_uri"],
            graph_version=payload["graph_version"],
            config_id=payload["config_id"],
        )
    except ValueError as exc:
        print(f"META_APP_CONFIGURED=FAIL reason={exc}", file=sys.stderr)
        return 2

    app_id = payload["app_id"]
    print(
        "META_APP_CONFIGURED=PASS "
        f"app_id_suffix={app_id[-4:] if len(app_id) >= 4 else app_id} "
        f"redirect_uri={payload['redirect_uri']} graph_version={vault.graph_version()} "
        f"login_flow={'business' if payload['config_id'] else 'classic'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

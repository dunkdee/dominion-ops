from __future__ import annotations

import getpass
import os
from pathlib import Path

from .vault import CredentialVault


def _prompt(label: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{label}{suffix}: ").strip()
    return value or (default or "")


def main() -> int:
    vault_root = Path(
        os.getenv("DOMINION_PUBLISHER_VAULT", "~/.dominion/publisher/credential-vault")
    ).expanduser()
    app_id = _prompt("Meta App ID")
    app_secret = getpass.getpass("Meta App Secret (hidden): ").strip()
    redirect_uri = _prompt(
        "Meta OAuth redirect URI",
        "https://dominionhealing.org/oauth/meta/callback",
    )
    graph_version = _prompt("Meta Graph API version", "v25.0")

    vault = CredentialVault(vault_root)
    vault.configure_meta_app(
        app_id=app_id,
        app_secret=app_secret,
        redirect_uri=redirect_uri,
        graph_version=graph_version,
    )
    print(
        "META_APP_CONFIGURED=PASS "
        f"app_id_suffix={app_id[-4:] if len(app_id) >= 4 else app_id} "
        f"redirect_uri={redirect_uri} graph_version={vault.graph_version()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

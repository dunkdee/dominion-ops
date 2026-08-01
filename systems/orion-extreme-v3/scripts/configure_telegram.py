#!/usr/bin/env python3
"""Pair ORION with the owner's Telegram account without exposing the token."""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path


def api(token: str, method: str, data: dict | None = None, timeout: int = 30) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    encoded = urllib.parse.urlencode(data or {}).encode()
    req = urllib.request.Request(url, data=encoded, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if not payload.get("ok"):
        raise RuntimeError(payload.get("description", "Telegram API error"))
    return payload


def set_env(path: Path, values: dict[str, str]) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    found: set[str] = set()
    out: list[str] = []
    for line in lines:
        if "=" in line and not line.lstrip().startswith("#"):
            key = line.split("=", 1)[0].strip()
            if key in values:
                out.append(f"{key}={values[key]}")
                found.add(key)
                continue
        out.append(line)
    for key, value in values.items():
        if key not in found:
            out.append(f"{key}={value}")
    path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
    path.chmod(0o600)


def main() -> int:
    p = argparse.ArgumentParser(description="Pair ORION with Telegram")
    p.add_argument("--env", default="/opt/orion-extreme/.env")
    p.add_argument("--wait", type=int, default=180)
    args = p.parse_args()
    env_path = Path(args.env)

    token = os.environ.get("TELEGRAM_BOT_TOKEN_INPUT", "").strip()
    if not token:
        token = getpass.getpass("Paste BotFather token (hidden): ").strip()
    if not token:
        print("No token supplied.", file=sys.stderr)
        return 2

    me = api(token, "getMe")["result"]
    username = me.get("username", "")
    print(f"Validated bot: @{username}")
    print(f"Open Telegram, send /start to @{username}, then return here.")
    input("Press Enter after sending /start... ")

    deadline = time.time() + max(30, args.wait)
    chosen = None
    offset = 0
    while time.time() < deadline and chosen is None:
        updates = api(token, "getUpdates", {"offset": offset, "timeout": 20}, timeout=25).get("result", [])
        for update in updates:
            offset = max(offset, int(update.get("update_id", 0)) + 1)
            msg = update.get("message") or {}
            sender = msg.get("from") or {}
            chat = msg.get("chat") or {}
            if chat.get("type") == "private" and sender.get("id") and chat.get("id"):
                chosen = (str(chat["id"]), str(sender["id"]), sender.get("username") or sender.get("first_name") or "owner")
        if chosen is None:
            print("Waiting for your Telegram message...")

    if chosen is None:
        print("No private Telegram message was found before timeout.", file=sys.stderr)
        return 3

    chat_id, owner_id, display = chosen
    set_env(env_path, {
        "TELEGRAM_BOT_TOKEN": token,
        "TELEGRAM_CHAT_ID": chat_id,
        "TELEGRAM_OWNER_USER_ID": owner_id,
    })
    print(f"Paired owner {display}; chat_id={chat_id}; owner_user_id={owner_id}")
    print(f"Updated {env_path} with mode 0600. Token was not printed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

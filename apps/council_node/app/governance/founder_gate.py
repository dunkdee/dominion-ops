"""Founder authority gate.

Rule 11: human-Founder gates override automation. This gate does two things:

  authenticate  a Founder mutation must carry the Founder token, compared in
                constant time so the check cannot be timed
  hold          the Founder can HOLD a lane, and a HOLD blocks execution in
                that lane regardless of what any policy or council says

An unconfigured gate denies everything. A deployment that forgot to set the
Founder token gets a service nobody can drive, which is the safe failure.
"""

from __future__ import annotations

import hmac
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


class FounderGateError(RuntimeError):
    """Founder authority was required and not established."""


class FounderGate:
    def __init__(self, token: str, state_path: Path | str) -> None:
        self._token = token or ""
        self.state_path = Path(state_path).expanduser()
        self.state_path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def configured(self) -> bool:
        return bool(self._token)

    def authenticate(self, presented: str | None) -> bool:
        if not self.configured:
            # Fail closed: no configured Founder means no Founder actions.
            return False
        if not presented:
            return False
        return hmac.compare_digest(self._token, presented)

    def require(self, presented: str | None) -> None:
        if not self.authenticate(presented):
            raise FounderGateError("Founder authorization is required and was not established")

    # ── holds ───────────────────────────────────────────────────────────

    def _load(self) -> dict:
        if not self.state_path.is_file():
            return {}
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            # An unreadable hold file must not be read as "nothing is held".
            raise FounderGateError("Founder hold state is unreadable; treating all lanes as held")

    def _save(self, data: dict) -> None:
        fd, tmp = tempfile.mkstemp(dir=str(self.state_path.parent), prefix=".holds-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, sort_keys=True, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.state_path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def hold(self, lane_id: str, reason: str) -> dict:
        data = self._load()
        entry = {
            "lane_id": lane_id,
            "reason": reason,
            "held_at": datetime.now(timezone.utc).isoformat(),
        }
        data[lane_id] = entry
        self._save(data)
        return entry

    def release(self, lane_id: str) -> bool:
        data = self._load()
        if lane_id not in data:
            return False
        data.pop(lane_id)
        self._save(data)
        return True

    def is_held(self, lane_id: str) -> bool:
        return lane_id in self._load()

    def held_lanes(self) -> dict:
        return self._load()

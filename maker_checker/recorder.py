"""Role 4: the Recorder (the auditor).

An append-only log. Each entry includes the hash of the previous one, so
editing or deleting any past entry breaks the chain and `verify()` catches it.
The Planner never gets a reference to the Recorder.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

GENESIS = "0" * 64


def _hash(entry: dict) -> str:
    return hashlib.sha256(json.dumps(entry, sort_keys=True).encode()).hexdigest()


class Recorder:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch()

    def _last_hash(self) -> str:
        lines = self.path.read_text().splitlines()
        return json.loads(lines[-1])["hash"] if lines else GENESIS

    def record(self, event: str, **data) -> None:
        entry = {
            "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "event": event,
            "data": data,
            "prev": self._last_hash(),
        }
        entry["hash"] = _hash(entry)
        with self.path.open("a") as f:
            f.write(json.dumps(entry) + "\n")

    def verify(self) -> bool:
        prev = GENESIS
        for line in self.path.read_text().splitlines():
            entry = json.loads(line)
            claimed = entry.pop("hash")
            if entry["prev"] != prev or _hash(entry) != claimed:
                return False
            prev = claimed
        return True

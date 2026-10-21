"""Role 4: the Recorder (the auditor).

An append-only JSONL log. Each entry includes the hash of the previous one, so
editing or deleting any past entry breaks the chain and `verify()` catches it.
Safe to share between threads and between processes (e.g. one hook process
per tool call).
"""

from __future__ import annotations

import hashlib
import json
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

try:
    import fcntl
except ImportError:  # Windows: thread-safe only
    fcntl = None

GENESIS = "0" * 64


def _hash(entry: dict) -> str:
    return hashlib.sha256(json.dumps(entry, sort_keys=True, default=str).encode()).hexdigest()


def _last_hash(f) -> str:
    f.seek(0)
    last = None
    for line in f:
        if line.strip():
            last = line
    return json.loads(last)["hash"] if last else GENESIS


class Recorder:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch()
        self._lock = threading.Lock()

    @contextmanager
    def _exclusive(self):
        with self._lock, self.path.open("a+") as f:
            if fcntl:
                fcntl.flock(f, fcntl.LOCK_EX)
            try:
                yield f
            finally:
                if fcntl:
                    fcntl.flock(f, fcntl.LOCK_UN)

    def record(self, event: str, **data) -> None:
        with self._exclusive() as f:
            entry = {
                "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "event": event,
                "data": data,
                "prev": _last_hash(f),
            }
            entry["hash"] = _hash(entry)
            f.seek(0, 2)
            f.write(json.dumps(entry, default=str) + "\n")

    def verify(self) -> bool:
        return verify_log(self.path)


def verify_log(path: str | Path) -> bool:
    prev = GENESIS
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        claimed = entry.pop("hash", None)
        if entry.get("prev") != prev or _hash(entry) != claimed:
            return False
        prev = claimed
    return True

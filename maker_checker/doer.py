"""Role 3: the Doer (the executor).

No reasoning. It runs an action only with a valid, unused token for exactly
that action.
"""

from __future__ import annotations

import hmac
import threading
from typing import Any, Callable

from .gatekeeper import sign
from .intents import Intent


class NotApproved(Exception):
    pass


class Doer:
    def __init__(self, secret: bytes):
        self._secret = secret
        self._used_nonces: set[str] = set()
        self._lock = threading.Lock()

    def redeem(self, intent: Intent, token: str | None) -> None:
        """Check the token and burn it. Raises NotApproved if it isn't valid."""
        if not token or "." not in token:
            raise NotApproved("no approval token")

        nonce, signature = token.split(".", 1)
        if not hmac.compare_digest(signature, sign(self._secret, nonce, intent)):
            raise NotApproved("token doesn't match this exact action")
        with self._lock:
            if nonce in self._used_nonces:
                raise NotApproved("token was already used")
            self._used_nonces.add(nonce)

    def run(self, intent: Intent, token: str | None, call: Callable[[], Any]) -> Any:
        self.redeem(intent, token)
        return call()

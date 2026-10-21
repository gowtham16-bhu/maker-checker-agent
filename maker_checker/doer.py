"""Role 3: the Doer (the executor).

No reasoning. It runs an action only if it carries a valid, unused token
for exactly that action, and the tools only touch a sandbox folder.
"""

from __future__ import annotations

import hmac
from typing import Callable

from .gatekeeper import sign
from .intents import Intent


class NotApproved(Exception):
    pass


class Doer:
    def __init__(self, secret: bytes, tools: dict[str, Callable[..., str]]):
        self._secret = secret
        self._tools = tools
        self._used_nonces: set[str] = set()

    def run(self, intent: Intent, token: str | None) -> str:
        if not token or "." not in token:
            raise NotApproved("no approval token")

        nonce, signature = token.split(".", 1)
        if not hmac.compare_digest(signature, sign(self._secret, nonce, intent)):
            raise NotApproved("token doesn't match this exact action")
        if nonce in self._used_nonces:
            raise NotApproved("token was already used")
        self._used_nonces.add(nonce)

        return self._tools[intent.tool](**intent.args)

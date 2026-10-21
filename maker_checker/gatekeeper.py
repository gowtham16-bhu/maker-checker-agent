"""Role 2: the Gatekeeper (the "checker").

Plain code, no LLM. It checks each proposed action against the policy and,
if the action is allowed, issues a one-time token bound to its exact bytes.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from . import policy
from .intents import Decision, Intent


def sign(secret: bytes, nonce: str, intent: Intent) -> str:
    return hmac.new(secret, nonce.encode() + intent.canonical_bytes(), hashlib.sha256).hexdigest()


class Gatekeeper:
    def __init__(self, secret: bytes):
        # Shared with the Doer so it can verify tokens. A production system
        # would sign with a private key and give the Doer only the public key.
        self._secret = secret

    def review(self, intent: Intent, context: dict) -> Decision:
        problem = policy.check(intent, context)
        if problem:
            return Decision(allowed=False, reason=problem)

        nonce = secrets.token_hex(8)
        token = f"{nonce}.{sign(self._secret, nonce, intent)}"
        return Decision(allowed=True, reason="matches policy", token=token)

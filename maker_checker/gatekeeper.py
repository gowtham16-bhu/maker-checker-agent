"""Role 2: the Gatekeeper (the "checker").

Plain code, no LLM. It asks the policy about each proposed action, brings in a
human when the policy says "ask", and for allowed actions issues a one-time
token bound to the action's exact bytes.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Callable

from .intents import Decision, Intent
from .policy import Policy

# Shown an intent and the policy's reason; returns True to approve.
Approver = Callable[[Intent, str], bool]


def sign(secret: bytes, nonce: str, intent: Intent) -> str:
    return hmac.new(secret, nonce.encode() + intent.canonical_bytes(), hashlib.sha256).hexdigest()


class Gatekeeper:
    def __init__(self, policy: Policy, secret: bytes, approver: Approver | None = None):
        self.policy = policy
        # Shared with the Doer so it can verify tokens. To run the roles as
        # separate services, sign with a private key and give the Doer the
        # public key instead.
        self._secret = secret
        self.approver = approver

    def review(self, intent: Intent, context: dict | None = None) -> Decision:
        try:
            verdict = self.policy.evaluate(intent, context)
        except Exception as error:  # a broken rule must fail closed
            return Decision(allowed=False, reason=f"policy error: {error}")

        if verdict.effect == "deny":
            return Decision(allowed=False, reason=verdict.reason)

        by = "policy"
        if verdict.effect == "ask":
            by = "human"
            if self.approver is None:
                return Decision(False, f"needs a human, but no approver is set ({verdict.reason})", by=by)
            if not self.approver(intent, verdict.reason):
                return Decision(False, f"a human declined ({verdict.reason})", by=by)

        nonce = secrets.token_hex(8)
        token = f"{nonce}.{sign(self._secret, nonce, intent)}"
        return Decision(allowed=True, reason=verdict.reason, token=token, by=by)

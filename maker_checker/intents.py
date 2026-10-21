"""The data that flows between the roles."""

from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Email:
    """An incoming email. `sender` comes from the mail server, so it's trusted.
    `body` comes from the outside world, so it's not."""

    sender: str
    subject: str
    body: str


@dataclass(frozen=True)
class Intent:
    """An action the Planner *proposes*. It's only data: it can't run anything."""

    tool: str
    args: dict = field(default_factory=dict)
    reason: str = ""

    def canonical_bytes(self) -> bytes:
        """The exact bytes an approval is bound to. Change one character and
        the approval no longer matches."""
        return json.dumps(
            {"tool": self.tool, "args": self.args},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()

    def __str__(self) -> str:
        args = ", ".join(f"{k}={v!r}" for k, v in self.args.items())
        return f"{self.tool}({args})"


@dataclass(frozen=True)
class Decision:
    """The Gatekeeper's verdict. `token` is set only when the action is allowed."""

    allowed: bool
    reason: str
    token: str | None = None

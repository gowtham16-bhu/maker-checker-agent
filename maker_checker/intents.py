"""The data that flows between the roles."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Literal

Effect = Literal["allow", "deny", "ask"]


@dataclass(frozen=True)
class Intent:
    """An action an agent *proposes*. It's only data: it can't run anything."""

    tool: str
    args: dict = field(default_factory=dict)

    def canonical_bytes(self) -> bytes:
        """The exact bytes an approval is bound to. Change one character and
        the approval no longer matches."""
        return json.dumps(
            {"tool": self.tool, "args": self.args},
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()

    def __str__(self) -> str:
        args = ", ".join(f"{k}={v!r}" for k, v in self.args.items())
        return f"{self.tool}({args})"


@dataclass(frozen=True)
class Verdict:
    """What the policy says about an intent, before any human is involved."""

    effect: Effect
    reason: str


@dataclass(frozen=True)
class Decision:
    """The Gatekeeper's final answer. `token` is set only when the action is allowed."""

    allowed: bool
    reason: str
    token: str | None = None
    by: Literal["policy", "human"] = "policy"

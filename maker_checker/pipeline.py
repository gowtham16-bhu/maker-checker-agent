"""Wires the four roles together: Planner -> Gatekeeper -> Doer, with the
Recorder logging every step. Also includes the usual one-agent design for
comparison."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from pathlib import Path

from .doer import Doer
from .gatekeeper import Gatekeeper
from .intents import Email, Intent
from .recorder import Recorder
from .tools import make_tools


@dataclass
class Outcome:
    intent: Intent
    allowed: bool
    reason: str
    result: str | None = None


class MakerCheckerAgent:
    def __init__(self, planner, gatekeeper: Gatekeeper, doer: Doer, recorder: Recorder):
        self.planner = planner
        self.gatekeeper = gatekeeper
        self.doer = doer
        self.recorder = recorder

    def handle(self, email: Email) -> list[Outcome]:
        self.recorder.record("email_received", sender=email.sender, subject=email.subject)
        outcomes = []

        for intent in self.planner.plan(email):
            self.recorder.record("proposed", tool=intent.tool, args=intent.args)

            # Trusted facts come from the mail server, never from the LLM.
            decision = self.gatekeeper.review(intent, context={"sender": email.sender})
            self.recorder.record("decision", tool=intent.tool, allowed=decision.allowed, reason=decision.reason)

            result = None
            if decision.allowed:
                result = self.doer.run(intent, decision.token)
                self.recorder.record("executed", tool=intent.tool, result=result)

            outcomes.append(Outcome(intent, decision.allowed, decision.reason, result))

        return outcomes


def build_agent(planner, workdir: Path) -> MakerCheckerAgent:
    workdir = Path(workdir)
    secret = secrets.token_bytes(32)
    return MakerCheckerAgent(
        planner=planner,
        gatekeeper=Gatekeeper(secret),
        doer=Doer(secret, make_tools(workdir / "sandbox")),
        recorder=Recorder(workdir / "audit.jsonl"),
    )


class NaiveAgent:
    """The usual design: whatever the LLM proposes, runs. For comparison only."""

    def __init__(self, planner, workdir: Path):
        self.planner = planner
        self.tools = make_tools(Path(workdir) / "sandbox")

    def handle(self, email: Email) -> list[Outcome]:
        return [
            Outcome(intent, True, "no checks", self.tools[intent.tool](**intent.args))
            for intent in self.planner.plan(email)
        ]

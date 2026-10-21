"""The Checker: the one object you add to any agent framework.

Wrap your tool functions with `checker.guard`. Every agent framework that
takes plain Python functions as tools (LangChain, OpenAI Agents SDK, Claude,
CrewAI, LlamaIndex, your own loop...) then sends each call through the
policy, a human when needed, and the audit log, before the function runs.

    checker = Checker("policy.toml")

    @checker.guard
    def send_email(to: str, subject: str, body: str) -> str:
        ...

    with checker.context(sender=email.sender):   # trusted facts for this request
        agent.run(email.body)
"""

from __future__ import annotations

import functools
import inspect
import secrets
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Callable, Iterable, Literal

from .doer import Doer
from .gatekeeper import Approver, Gatekeeper
from .intents import Decision, Intent
from .policy import Policy
from .recorder import Recorder

_request_context: ContextVar[dict] = ContextVar("maker_checker_context", default={})


class Blocked(Exception):
    """Raised by a guarded tool when `on_block="raise"`."""

    def __init__(self, intent: Intent, reason: str):
        super().__init__(f"{intent.tool} was blocked: {reason}")
        self.intent = intent
        self.reason = reason


def _short(value: Any, limit: int = 500) -> str:
    text = value if isinstance(value, str) else repr(value)
    return text if len(text) <= limit else text[:limit] + "…"


class Checker:
    def __init__(
        self,
        policy: Policy | dict | str | Path,
        *,
        audit_log: str | Path | None = "maker-checker-audit.jsonl",
        approver: Approver | None = None,
        context: dict | None = None,
        on_block: Literal["return", "raise"] = "return",
    ):
        """
        policy     a Policy, a dict, or a path to a .toml policy file
        audit_log  where the Recorder writes; None turns logging off
        approver   called for "ask" decisions; without one, "ask" means no
        context    trusted facts available to every call ($context.<key>)
        on_block   "return" a message the LLM can read (works with every
                   framework), or "raise" a Blocked exception
        """
        if on_block not in ("return", "raise"):
            raise ValueError('on_block must be "return" or "raise"')
        self.policy = Policy.load(policy)
        secret = secrets.token_bytes(32)
        self.gatekeeper = Gatekeeper(self.policy, secret, approver)
        self.doer = Doer(secret)
        self.recorder = Recorder(audit_log) if audit_log else None
        self.base_context = dict(context or {})
        self.on_block = on_block

    @contextmanager
    def context(self, **values):
        """Add trusted facts for the calls made inside this block. Works with
        threads and asyncio, so concurrent requests don't mix."""
        token = _request_context.set({**_request_context.get(), **values})
        try:
            yield self
        finally:
            _request_context.reset(token)

    def current_context(self, extra: dict | None = None) -> dict:
        return {**self.base_context, **_request_context.get(), **(extra or {})}

    def check(self, tool: str, args: dict | None = None, context: dict | None = None) -> Decision:
        """Review one proposed call without running anything. Use this when
        your framework gives you a hook or middleware instead of functions."""
        return self._review(Intent(tool, dict(args or {})), self.current_context(context))

    def guard(
        self,
        fn: Callable | None = None,
        *,
        name: str | None = None,
        exclude: Iterable[str] = (),
    ):
        """Decorator. `name` is the tool name your policy uses (defaults to the
        function name). `exclude` lists parameters a framework injects (like a
        run context) that shouldn't be part of the policy check."""
        excluded = set(exclude)

        def decorate(f: Callable) -> Callable:
            tool_name = name or f.__name__
            signature = inspect.signature(f)

            def prepare(args, kwargs):
                bound = signature.bind(*args, **kwargs)
                bound.apply_defaults()
                visible = {k: v for k, v in bound.arguments.items() if k not in excluded}
                return bound, Intent(tool_name, visible)

            if inspect.iscoroutinefunction(f):

                @functools.wraps(f)
                async def wrapper(*args, **kwargs):
                    bound, intent = prepare(args, kwargs)
                    decision = self._review(intent, self.current_context())
                    if not decision.allowed:
                        return self._blocked(intent, decision)
                    self.doer.redeem(intent, decision.token)
                    try:
                        result = await f(*bound.args, **bound.kwargs)
                    except Exception as error:
                        self._record("failed", tool=tool_name, error=repr(error))
                        raise
                    self._record("executed", tool=tool_name, result=_short(result))
                    return result

            else:

                @functools.wraps(f)
                def wrapper(*args, **kwargs):
                    bound, intent = prepare(args, kwargs)
                    decision = self._review(intent, self.current_context())
                    if not decision.allowed:
                        return self._blocked(intent, decision)
                    try:
                        result = self.doer.run(intent, decision.token, lambda: f(*bound.args, **bound.kwargs))
                    except Exception as error:
                        self._record("failed", tool=tool_name, error=repr(error))
                        raise
                    self._record("executed", tool=tool_name, result=_short(result))
                    return result

            wrapper.__maker_checker_tool__ = tool_name
            return wrapper

        return decorate(fn) if fn is not None else decorate

    def _record(self, event: str, **data) -> None:
        if self.recorder:
            self.recorder.record(event, **data)

    def _review(self, intent: Intent, context: dict) -> Decision:
        self._record("proposed", tool=intent.tool, args=intent.args)
        decision = self.gatekeeper.review(intent, context)
        self._record("decision", tool=intent.tool, allowed=decision.allowed, by=decision.by, reason=decision.reason)
        return decision

    def _blocked(self, intent: Intent, decision: Decision) -> str:
        if self.on_block == "raise":
            raise Blocked(intent, decision.reason)
        return f"BLOCKED by policy: {decision.reason}. This action was not performed."

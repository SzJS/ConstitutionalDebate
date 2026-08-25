"""The fake client every offline test runs against.

Two things about it are load-bearing.

**It instruments concurrency.** ``max_in_flight`` records the high-water mark of
overlapping calls, so "this stage is a serial await loop" is caught by an assertion
rather than by review. exp1 shipped two such loops — their semaphores could never be
contended — and this is what stops that recurring here.

**Its default replies are well-formed.** A judge that replies "Verdict: FLAWED" by
default means a test exercises the thing under test rather than the repair path. Tests
that want the repair path ask for it through ``fail_on``.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from helpers import make_config, make_item, make_sides  # noqa: F401  (re-exported)

from exp2.client import Completion, FatalError, RetryableError

# Roles whose calls are keyed on the role alone — there is at most one per run.
SINGLETON_ROLES = {"judge", "recourse_judge", "challenger", "comprehension",
                   "recourse_solo"}
# Roles where the same role is called several times for different purposes.
STAGED_ROLES = {"grader", "solo", "critic"}

DEFAULT_REPLIES: dict[str, str] = {
    "judge": "The flawed side quoted the text; the sound side did not.\nVerdict: FLAWED",
    "recourse_judge": "The objection identifies a real error.\nRuling: OVERTURN",
    "challenger": ("Thinking: I read the record.\n"
                   "Argument: Objection: RAISED\nStep 2 divides by zero."),
    "comprehension": "I followed most of it.\nComprehension: 4",
    "recourse_solo": "Thinking: reconsidering.\nReasoning: I was wrong.\nVerdict: SOUND",
    "grader": ("It points at the right step and says what is wrong.\n"
               "Identified the flaw: YES\nCharacterised the flaw: YES"),
}


# A distinctive needle, so a leak assertion cannot pass because the word happens to
# appear in some role's own system prompt.
SOLO_THINKING = "SECRET-SOLO-THINKING-never-published"


def _solo_reply(purpose: str) -> str:
    if purpose == "critique":
        return f"Thinking: {SOLO_THINKING}\nReasoning: my draft took step 2 on trust."
    return (f"Thinking: {SOLO_THINKING}\n"
            f"Reasoning: my {purpose} assessment.\nVerdict: FLAWED")


class FakeClient:
    """A ``ChatClient`` that answers from a script instead of the network."""

    def __init__(self, *, replies: dict[Any, str] | None = None,
                 fail_on: dict[Any, str] | None = None, sink=None):
        self.replies = dict(replies or {})
        self.fail_on = dict(fail_on or {})
        self.sink = sink
        self.calls: list[dict[str, Any]] = []
        self.in_flight = 0
        self.max_in_flight = 0

    @staticmethod
    def key(meta: dict[str, Any]) -> Any:
        role = meta.get("role")
        if role in SINGLETON_ROLES:
            return role
        if role in STAGED_ROLES:
            return (role, meta.get("purpose"))
        return (meta.get("round"), meta.get("speaker"))

    def reply_for(self, meta: dict[str, Any]) -> str:
        key = self.key(meta)
        if key in self.replies:
            return self.replies[key]
        role = meta.get("role")
        if role in DEFAULT_REPLIES:
            return DEFAULT_REPLIES[role]
        if role in ("solo", "critic"):
            return _solo_reply(meta.get("purpose") or "answer")
        speaker, round_number = meta.get("speaker"), meta.get("round")
        return (f"Thinking: private plan for {speaker} in round {round_number}.\n"
                f"Argument: {speaker} argues in round {round_number}.")

    async def complete(self, *, model: str, messages: list[dict[str, str]],
                       temperature: float, max_tokens: int, reasoning_effort: str,
                       meta: dict[str, Any], frequency_penalty: float = 0.0):
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            await asyncio.sleep(0)  # let a sibling coroutine actually overlap
            self.calls.append({"model": model, "messages": messages, "meta": dict(meta)})
            key = self.key(meta)
            failure = self.fail_on.get(key)
            # A repair must be able to succeed, or the repair path cannot be tested.
            if failure and meta.get("purpose") != "repair":
                if failure == "http_error":
                    raise RetryableError("injected", status=500)
                if failure == "fatal":
                    raise FatalError("injected", status=400)
                if failure == "truncated":
                    return self._completion("cut off mid-sen", finish_reason="length")
                if failure == "malformed":
                    return self._completion("no labels here at all")
            completion = self._completion(self.reply_for(meta))
            if self.sink is not None:
                await self.sink({"call_id": completion.call_id, "attempt": 1,
                                 "status": 200, "request_body": {"model": model},
                                 "response_body": {}, "usage": {"cost": 0.0},
                                 **meta})
            return completion
        finally:
            self.in_flight -= 1

    def _completion(self, content: str, *, finish_reason: str = "stop") -> Completion:
        return Completion(
            call_id=f"call-{len(self.calls)}", content=content,
            finish_reason=finish_reason, model="fake/model", provider="fake",
            reasoning="", usage={"cost": 0.0},
        )

    # --- assertions tests reach for -------------------------------------------------

    def roles(self) -> list[str]:
        return [c["meta"].get("role") for c in self.calls]

    def purposes(self, role: str) -> list[str]:
        return [c["meta"].get("purpose") for c in self.calls
                if c["meta"].get("role") == role]

    def sent_to(self, role: str) -> list[dict[str, str]]:
        """The message list of the first call made as this role."""
        for call in self.calls:
            if call["meta"].get("role") == role:
                return call["messages"]
        raise AssertionError(f"no call was made as {role!r}; roles seen: {self.roles()}")


@pytest.fixture
def client() -> FakeClient:
    return FakeClient()


@pytest.fixture
def config():
    return make_config()


@pytest.fixture
def item():
    return make_item()


@pytest.fixture
def sides():
    return make_sides()

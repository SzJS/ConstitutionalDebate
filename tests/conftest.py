"""Shared fixtures.

``FakeClient`` instruments concurrency. Asserting on message contents alone
would only prove that the visibility predicate is right while *trusting* that
``asyncio.gather`` was used; counting in-flight calls is what actually
distinguishes the two turn styles, and it catches a serial ``for`` loop with an
``await`` inside — the failure mode the project's own rules forbid.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest

from constitutional_debate.client import Completion
from constitutional_debate.config import DebateConfig, load_config
from constitutional_debate.types import Seating, Task


class FakeClient:
    """In-memory ``ChatClient`` that records calls and tracks concurrency."""

    def __init__(
        self,
        *,
        scripted: dict[Any, str] | None = None,
        fail_on: dict[Any, str] | None = None,
        delay: float = 0.01,
        sink: Any = None,
    ) -> None:
        self.scripted = scripted or {}
        self.fail_on = fail_on or {}
        self.delay = delay
        self.sink = sink
        self.calls: list[dict[str, Any]] = []
        self.in_flight = 0
        self.max_in_flight = 0

    # Roles that have exactly one call per run, so a script can key on the role
    # alone. Debaters need (round, speaker).
    SINGLETON_ROLES = frozenset({"judge", "recourse_judge", "challenger"})
    # Roles that occur several times per run but carry no round or speaker — a
    # grader runs once per objection, a validator once per case and again per
    # ruling. They would all collide on ``(None, None)``, so they key on
    # ``(role, purpose)`` instead. Existing keys are untouched.
    STAGED_ROLES = frozenset({"grader", "validator", "solo", "critic", "injector"})

    @staticmethod
    def key(meta: dict[str, Any]) -> Any:
        role = meta.get("role")
        if role in FakeClient.SINGLETON_ROLES:
            return role
        if role in FakeClient.STAGED_ROLES:
            return (role, meta.get("purpose"))
        return (meta.get("round"), meta.get("speaker"))

    async def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        reasoning_effort: str,
        meta: dict[str, Any],
        frequency_penalty: float = 0.0,
    ) -> Completion:
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            await asyncio.sleep(self.delay)
            self.calls.append(
                {"model": model, "messages": messages, "meta": dict(meta)}
            )

            key = self.key(meta)
            mode = self.fail_on.get(key)
            if mode == "http_error" and meta.get("purpose") != "repair":
                raise RuntimeError(f"simulated transport failure for {key}")

            finish_reason = "stop"
            if mode == "truncated":
                finish_reason = "length"

            if mode == "malformed" and meta.get("purpose") != "repair":
                content = "I forgot the labels entirely."
            elif key in self.scripted:
                content = self.scripted[key]
            elif meta.get("role") == "judge":
                content = "Answer: 1"
            elif meta.get("role") == "recourse_judge":
                content = (
                    "The challenge restates the losing case rather than "
                    "identifying an error in the decision's reasoning.\n\n"
                    "Ruling: UPHOLD"
                )
            elif meta.get("role") == "critic":
                # No format contract: a critique produces no decision, so there
                # is nothing to parse and nothing a malformed reply could break.
                content = "Step 2 asserts the bound without establishing it."
            elif meta.get("role") == "solo":
                content = (
                    "Thinking: private working, published only afterwards\n\n"
                    "Reasoning: The first choice follows from the constraint.\n"
                    "Answer: 1"
                )
            elif meta.get("role") == "grader":
                content = (
                    "The objection names the divisor and says the answer flips.\n\n"
                    "Localisation: 2\n"
                    "Changes the decision: YES"
                )
            elif meta.get("role") == "validator":
                content = (
                    "The intended flaw is present and drove the decision.\n\n"
                    "Fidelity: YES\nSurvived: YES\nCross-arm match: YES\n"
                    "Re-derived: NO"
                )
            elif meta.get("role") == "challenger":
                # Carries the "Challenge: YES" decision line, because the
                # challenger may decline by default and the parser refuses a
                # response without it. A scripted reply that omitted it would
                # test the repair path rather than the thing under test.
                content = (
                    "Thinking: private plan for the challenge — this scratchpad "
                    "is not part of the challenge and must not reach the judge "
                    "or either debater.\n\n"
                    "Argument: Challenge: YES\n"
                    "The decision rests on a figure neither debater supported."
                )
            else:
                # Thinking is deliberately long, distinctive and *multi-line*:
                # real ones are all three — the prompts ask for a numbered plan —
                # and the leak tests would be weak against a single-line
                # fixture: anything interpolating a turn into a prompt indents
                # continuation lines, so a leak would not contain the raw
                # needle anywhere.
                content = (
                    f"Thinking: private plan for {meta['speaker']} in round "
                    f"{meta['round']} — the judge must not see this reasoning.\n"
                    f"1. Open on the strongest point available to me.\n"
                    f"2. Concede nothing, and set out my strategy in detail "
                    f"before I argue.\n\n"
                    f"Argument: {meta['speaker']} argument round {meta['round']}"
                )

            completion = Completion(
                call_id=uuid.uuid4().hex[:12],
                content=content,
                finish_reason=finish_reason,
                model=model,
                provider="fake",
                reasoning=None,
                usage={"prompt_tokens": 100, "completion_tokens": 20},
            )
            if self.sink is not None:
                # Mirrors the shape OpenRouterClient records, so tests that read
                # calls.jsonl are reading the real artifact's shape.
                await self.sink(
                    {
                        "call_id": completion.call_id,
                        "attempt": 1,
                        "status": 200,
                        "request_body": {
                            "model": model,
                            "messages": messages,
                            "temperature": temperature,
                            "max_tokens": max_tokens,
                        },
                        "response_body": {"choices": [{"message": {"content": content}}]},
                        "provider": "fake",
                        "response_model": model,
                        "finish_reason": finish_reason,
                        "has_native_reasoning": False,
                        "usage": completion.usage,
                        **meta,
                    }
                )
            return completion
        finally:
            self.in_flight -= 1


@pytest.fixture
def task() -> Task:
    return Task(
        task_id="fixture-task",
        question="Is it OK to use tax havens?",
        answers=("It is OK to use tax havens.", "It is NOT OK to use tax havens."),
        gold_index=None,
    )


@pytest.fixture
def seating() -> Seating:
    """Alice defends answer 0, but the judge is shown answer 1 as choice 1.

    A non-identity choice_order by default means every end-to-end test exercises
    the mapping that would silently invert verdicts if it were wrong.
    """
    return Seating(
        alice_answer=0, bob_answer=1, choice_order=(1, 0), seed_material="fixture"
    )


@pytest.fixture
def config() -> DebateConfig:
    debate, _ = load_config()
    return debate


@pytest.fixture
def make_config():
    def _make(**kwargs) -> DebateConfig:
        debate, _ = load_config()
        return DebateConfig(**{**debate.to_dict(), **kwargs})

    return _make

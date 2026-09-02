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
import itertools
from typing import Any

import pytest
from helpers import make_config, make_item, make_sides  # noqa: F401  (re-exported)

from exp2.client import Completion, FatalError, RetryableError

# Roles whose calls are keyed on the role alone — there is at most one per run.
SINGLETON_ROLES = {"judge", "recourse_judge", "challenger", "comprehension",
                   "recourse_solo", "agreement", "ruling_reader",
                   "ruling_reader_materiality", "judgment_grader", "gatekeeper",
                   "findings_grader"}
# Roles where the same role is called several times for different purposes.
STAGED_ROLES = {"grader", "solo", "critic"}

DEFAULT_REPLIES: dict[str, str] = {
    "judge": "The flawed side quoted the text; the sound side did not.\nVerdict: FLAWED",
    # The judge states an absolute conclusion and never a relative word; UPHOLD or
    # OVERTURN is derived from it by comparison with the decision. Against the default
    # judge's FLAWED verdict this SOUND conclusion derives OVERTURN, which is what the
    # old "Ruling: OVERTURN" default gave, so the recourse tests keep the outcome they
    # were written against while exercising the new line.
    "recourse_judge": ("The objection identifies a real error.\n"
                       "Conclusion: the original text in <solution> does not contain a "
                       "flaw"),
    # Contests: one line, REVERSE, which against the default judge's FLAWED verdict
    # derives a claimed SOUND. A reply with no parsable line is the `unclear` stance,
    # which seeks no ruling — so every recourse test would silently stop exercising the
    # ruling path if this default lost its line.
    "challenger": ("Thinking: I read the record.\n"
                   "Argument: Step 2 does not divide by zero; the decision misread "
                   "it.\nDecision: REVERSE"),
    "comprehension": "I followed most of it.\nComprehension: 4",
    "recourse_solo": "Thinking: reconsidering.\nReasoning: I was wrong.\nVerdict: SOUND",
    "grader": ("It points at the right step and says what is wrong.\n"
               "Identified the flaw: YES\nCharacterised the flaw: YES"),
    # The judgment variant's grader: one line per alleged defect, then the summary. VALID
    # matches the summary line, so the default run measures a consistent grade and tests
    # that want the disagreement ask for it.
    "judgment_grader": ("The judgment quote is accurate and the record does not say "
                        "it.\nDefect 1: VALID — the record says the opposite.\n"
                        "Valid objection: YES"),
    # The M4 admissibility gate. ADMITTED matches its own per-defect finding, so the
    # default run measures a consistent admission and `line_mismatch` reads False; a test
    # that wants the disagreement, or a refusal, asks for it. Without a default here the
    # fake would fall through to the catch-all and every gate call in the offline harness
    # would die malformed after its one repair — which is exactly what the materiality
    # reader was silently doing until 2026-08-28.
    "gatekeeper": ("The judgment quote is verbatim and the record does not say it.\n"
                   "Defect 1: REAL — the record says the opposite.\n"
                   "Admissibility: ADMITTED"),
    # The line-vs-prose probe. WRONG matches the default challenger's REVERSE line, so
    # the default run measures agreement rather than a phantom contest; tests that want
    # the mismatch ask for it.
    "agreement": "It argues the verdict got it wrong.\nProse: WRONG",
    # The ruling's line-vs-prose probe. SOUND matches the default recourse judge's
    # conclusion above, so the default run measures agreement rather than a mismatch;
    # tests that want the mismatch ask for it.
    "ruling_reader": "The reasoning concludes the text is fine.\nReading: SOUND",
    # The SAME instrument keyed on the materiality prompt, which is what rules every
    # judgment-family objection (`prompts.RULING_READER_ROLES`). It answers in the
    # materiality vocabulary — STANDS / CHANGED / NEITHER, mapped onto a verdict in code
    # — not in the object-level reader's FLAWED / SOUND, so it needs its own default.
    # Without one the fake fell through to the catch-all and every materiality reading in
    # the offline harness died malformed after its one repair, which is exactly what
    # `scripts/e2e_offline.py` was silently doing to the judgment pass. CHANGED is the
    # consistent answer to the default judge above: it concludes SOUND against a FLAWED
    # parent, so the decision changed, and `ruling_line_mismatch` is False.
    "ruling_reader_materiality": ("The judge finds the defect real and material.\n"
                                  "Reading: CHANGED"),
    # --- the findings family, campaign `fd1` (2026-09-02) --------------------------
    #
    # Three of these are answered under a wire role that ALREADY has a default —
    # `judge`, `recourse_judge`, `ruling_reader` — because the wire role is what
    # accounting reads and a findings judgment is the same decision-path call a verdict
    # judgment is. A fixture keyed on the role alone would therefore answer the findings
    # judge with "Verdict: FLAWED", its parser would refuse it, and the cell would die
    # after its one repair. That is exactly what this file was doing to every materiality
    # reading until 2026-08-28, in a stage that reports nothing. So the fake sniffs the
    # prompt for a mark from the closing it was actually sent (`FINDINGS_MARKS` below)
    # and answers the question it was asked.
    #
    # The judgment derives FLAWED — one FLAW finding — which is what the plain `judge`
    # default gives, so a test that swaps the judge form keeps the outcome it was written
    # against while exercising the new parser.
    "judge_findings": ("The flawed side raised one purported flaw.\n"
                       "Finding 1\n"
                       'Passage: "step 2 divides by zero"\n'
                       "Claim: step 2 can divide by zero\n"
                       "Defence: none given\n"
                       "Reason: the divisor is not bounded away from zero\n"
                       "Ruling: FLAW"),
    # One line per contest. `parse_findings_ruling_output` is bound to the objection's
    # own contest count, so a default that names contest 1 is enough for a one-contest
    # objection and is harmlessly dropped when there are none.
    "recourse_judge_findings": ("The quotation is in the text and the claim holds.\n"
                                "Contest 1 (Finding 1): NOT A FLAW"),
    # CONSISTENT is the consistent answer: the ruling above reaches a definite ruling and
    # gives its reason, so `ruling_line_mismatch` reads False.
    "ruling_reader_findings": ("The reasoning settles the contest it discusses.\n"
                               "Reading: CONSISTENT"),
    # The findings grader: one line per contest, then the summary. VALID matches the
    # summary line, so the default run measures a consistent grade and tests that want
    # the disagreement ask for it.
    "findings_grader": ("The contest quotes the text accurately and the finding is "
                        "about the annotated flaw.\n"
                        "Contest 1: VALID — it points at the recorded flaw.\n"
                        "Valid objection: YES"),
}


# A distinctive needle, so a leak assertion cannot pass because the word happens to
# appear in some role's own system prompt.
SOLO_THINKING = "SECRET-SOLO-THINKING-never-published"


def _solo_reply(purpose: str) -> str:
    if purpose == "critique":
        return f"Thinking: {SOLO_THINKING}\nReasoning: my draft took step 2 on trust."
    return (f"Thinking: {SOLO_THINKING}\n"
            f"Reasoning: my {purpose} assessment.\nVerdict: FLAWED")


# Call ids are unique across every fake client in a process, as a provider's generation
# ids are across every run. They were `call-{len(self.calls)}` and so restarted at zero
# for each client — which is fine while one directory holds one client's calls, and wrong
# the moment a directory holds a wire log copied from ANOTHER run beside its own: a
# re-judged decision keeps the debate's prompts in `calls.source.jsonl` and its own judge
# call in `calls.jsonl`, and two calls sharing an id would render one under the other's
# heading.
_CALL_IDS = itertools.count()


class FakeClient:
    """A ``ChatClient`` that answers from a script instead of the network."""

    # Failure modes that keep firing on the repair attempt too. Everything else stops
    # after the first call, so that the repair path can actually be tested.
    ALWAYS = {"truncated_twice"}

    def __init__(self, *, replies: dict[Any, str] | None = None,
                 fail_on: dict[Any, str] | None = None, sink=None,
                 native_reasoning: str = "",
                 truncated_content: str = "cut off mid-sen",
                 malformed_content: str = "no labels here at all"):
        self.replies = dict(replies or {})
        self.fail_on = dict(fail_on or {})
        self.sink = sink
        self.native_reasoning = native_reasoning
        # What a truncated reply contains. The budget route reads it — whether the
        # public label was reached decides whether the truncation cut anything — so a
        # test has to be able to say what the model got as far as writing.
        self.truncated_content = truncated_content
        # What a malformed reply contains. The repair route now reads it — the SHAPE of
        # the refusal picks which correction is sent — so a test has to be able to say
        # which of pilot-2's measured shapes the model produced.
        self.malformed_content = malformed_content
        self.calls: list[dict[str, Any]] = []
        self.in_flight = 0
        self.max_in_flight = 0

    # The one place the fake has to look at the MESSAGES and not only at the meta.
    # `recourse.judge_ruling_prose` deliberately logs both readings under one wire role
    # — `ruling_reader`, because accounting reads `meta` and the two readings are one
    # probe — while asking two different questions in two different vocabularies:
    # FLAWED/SOUND for an object-level ruling, STANDS/CHANGED/NEITHER for a materiality
    # one. A fixture keyed on the role alone therefore answers the materiality reader in
    # the object-level vocabulary, its parser rejects it, and the reading dies after its
    # one repair — silently, since `ruling_agreement` is off the decision path. That is
    # exactly what `scripts/e2e_offline.py` was doing to every judgment-arm ruling until
    # 2026-08-28, and it is the arm the whole next phase re-rules. So the fake answers
    # the question it was actually asked.
    MATERIALITY_READER_MARK = "`Reading: STANDS`, `Reading: CHANGED`, or `Reading: NEITHER`"

    # The same trick for the findings family, and for the same reason one layer wider:
    # three wire roles now serve two questions each. The mark is a distinctive phrase
    # from the closing the findings form actually sends, so the fake answers what it was
    # asked rather than what its role is usually asked. `{wire role: (reply key, mark)}`.
    FINDINGS_MARKS = {
        "judge": ("judge_findings",
                  "raised no identifiable purported flaw at all"),
        "recourse_judge": ("recourse_judge_findings",
                           "Rule only on the contests, one at a time"),
        "ruling_reader": ("ruling_reader_findings",
                          "`Reading: CONSISTENT`, `Reading: INCONSISTENT`, or "
                          "`Reading: NEITHER`"),
    }

    @staticmethod
    def asked_for_findings(role, messages: list[dict[str, str]] | None) -> str | None:
        """The findings reply key for these messages, or None if this is the other
        question this wire role serves."""
        entry = FakeClient.FINDINGS_MARKS.get(role)
        if entry is None or not messages:
            return None
        key, mark = entry
        blob = "".join(m.get("content", "") for m in messages)
        return key if mark in blob else None

    @staticmethod
    def key(meta: dict[str, Any]) -> Any:
        role = meta.get("role")
        if role in SINGLETON_ROLES:
            return role
        if role in STAGED_ROLES:
            return (role, meta.get("purpose"))
        return (meta.get("round"), meta.get("speaker"))

    @staticmethod
    def asked_for_materiality(messages: list[dict[str, str]] | None) -> bool:
        """Whether these messages are the MATERIALITY ruling reader's, not the
        object-level one's — decided by the answer line the prompt asks for."""
        if not messages:
            return False
        return FakeClient.MATERIALITY_READER_MARK in "".join(
            m.get("content", "") for m in messages)

    def reply_for(self, meta: dict[str, Any],
                  messages: list[dict[str, str]] | None = None) -> str:
        key = self.key(meta)
        # An explicit `ruling_reader_materiality` script wins over a generic
        # `ruling_reader` one, so a pass that answers both readers can say so; a test
        # that scripts only `ruling_reader` keeps meaning exactly what it meant.
        if key == "ruling_reader" and self.asked_for_materiality(messages):
            if "ruling_reader_materiality" in self.replies:
                return self.replies["ruling_reader_materiality"]
            if key not in self.replies:
                return DEFAULT_REPLIES["ruling_reader_materiality"]
        # Same rule for the findings family: an explicit `judge_findings` /
        # `recourse_judge_findings` / `ruling_reader_findings` script wins over a generic
        # one on the wire role, and a test that scripts only the wire role keeps meaning
        # exactly what it meant.
        findings_key = self.asked_for_findings(meta.get("role"), messages)
        if findings_key is not None:
            if findings_key in self.replies:
                return self.replies[findings_key]
            if key not in self.replies:
                return DEFAULT_REPLIES[findings_key]
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
                       meta: dict[str, Any], frequency_penalty: float = 0.0,
                       provider: dict[str, Any] | None = None):
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            await asyncio.sleep(0)  # let a sibling coroutine actually overlap
            self.calls.append({"model": model, "messages": messages,
                               "meta": dict(meta), "temperature": temperature,
                               "max_tokens": max_tokens, "provider": provider})
            key = self.key(meta)
            # Keyed on the call's own key, falling back to the bare role name. A repair
            # carries purpose="repair", so a staged role's repair has a different key
            # from the call it is repairing; keying on the role is how a test asks for a
            # failure that covers both.
            failure = self.fail_on.get(key, self.fail_on.get(meta.get("role")))
            request = self._request_body(
                model=model, messages=messages, temperature=temperature,
                max_tokens=max_tokens, reasoning_effort=reasoning_effort,
                frequency_penalty=frequency_penalty, provider=provider,
            )
            # A repair must be able to succeed, or the repair path cannot be tested —
            # unless the test asked for a failure that keeps firing.
            if failure and (failure in self.ALWAYS
                            or meta.get("purpose") != "repair"):
                if failure == "http_error":
                    raise RetryableError("injected", status=500)
                if failure == "fatal":
                    raise FatalError("injected", status=400)
                if failure in ("truncated", "truncated_twice"):
                    return await self._deliver(self.truncated_content, request, meta,
                                               finish_reason="length")
                if failure == "malformed":
                    return await self._deliver(self.malformed_content, request, meta)
            return await self._deliver(self.reply_for(meta, messages),
                                       request, meta)
        finally:
            self.in_flight -= 1

    @staticmethod
    def _request_body(*, model: str, messages: list[dict[str, str]],
                      temperature: float, max_tokens: int, reasoning_effort: str,
                      frequency_penalty: float,
                      provider: dict[str, Any] | None = None) -> dict[str, Any]:
        """The body ``OpenRouterClient._build_body`` would have put on the wire.

        A renderer that reads ``calls.jsonl`` reads the request, so the fake's log
        has to carry the same fields — including the zero ``frequency_penalty``
        that the real client deliberately omits.
        """
        body: dict[str, Any] = {
            "model": model, "messages": messages, "temperature": temperature,
            "max_tokens": max_tokens, "usage": {"include": True},
        }
        if frequency_penalty:
            body["frequency_penalty"] = frequency_penalty
        body["reasoning"] = ({"enabled": False} if reasoning_effort == "off"
                             else {"effort": reasoning_effort})
        if provider:
            body["provider"] = provider
        return body

    async def _deliver(self, content: str, request: dict[str, Any],
                       meta: dict[str, Any], *,
                       finish_reason: str = "stop") -> Completion:
        """Return a completion, logging it as the real client logs an attempt.

        Malformed and truncated replies are logged too: they are generations that
        a run paid for, and the wire log is where they have to be findable.
        """
        completion = self._completion(content, finish_reason=finish_reason)
        if self.sink is not None:
            await self.sink({
                "call_id": completion.call_id, "attempt": 1, "status": 200,
                "request_body": request,
                "latency_ms": 0,
                "response_body": {
                    "model": completion.model, "provider": completion.provider,
                    "choices": [{
                        "finish_reason": finish_reason,
                        "message": {"role": "assistant", "content": content,
                                    "reasoning": completion.reasoning or None},
                    }],
                },
                "finish_reason": finish_reason,
                "has_native_reasoning": completion.has_native_reasoning,
                "usage": {"cost": 0.0},
                **meta,
            })
        return completion

    def _completion(self, content: str, *, finish_reason: str = "stop") -> Completion:
        return Completion(
            call_id=f"call-{next(_CALL_IDS)}", content=content,
            finish_reason=finish_reason, model="fake/model", provider="fake",
            reasoning=self.native_reasoning, usage={"cost": 0.0},
        )

    # --- assertions tests reach for -------------------------------------------------

    def roles(self) -> list[str]:
        return [c["meta"].get("role") for c in self.calls]

    def purposes(self, role: str) -> list[str]:
        return [c["meta"].get("purpose") for c in self.calls
                if c["meta"].get("role") == role]

    def temperature_for(self, role: str) -> float:
        """The temperature the first call as this role was made at."""
        return self._first(role)["temperature"]

    def max_tokens_for(self, role: str, purpose: str | None = None) -> int:
        """The cap the first call as this role (and purpose, if given) was made at."""
        return self._first(role, purpose)["max_tokens"]

    def _first(self, role: str, purpose: str | None = None) -> dict[str, Any]:
        for call in self.calls:
            if call["meta"].get("role") != role:
                continue
            if purpose is not None and call["meta"].get("purpose") != purpose:
                continue
            return call
        raise AssertionError(f"no call was made as {role!r}; roles seen: {self.roles()}")

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

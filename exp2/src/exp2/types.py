"""Core protocol types.

The task is a yes/no verdict over one solution: given a problem and a proposed
solution, does the solution contain a flaw?  That is the difference from exp1, which
asked which of two *answers* was correct, and it removes an entire layer of
indirection — there is no answer pair, no choice ordering, and no index to resolve.

What remains, and what this module exists to keep apart, is two orderings:

1. ``Sides.alice_side``    -- which debater argues that the solution is flawed;
2. ``Sides.verdict_order`` -- which verdict the judge's template lists first.

Alice always speaks first in the transcript (per the protocol), while
``verdict_order`` is drawn independently.  If those two correlate, "the first-listed
verdict" silently becomes "the side that spoke first", and the randomisation that
exists to neutralise position bias stops doing anything.

The ground truth is ``Item.gold_flawed``, a bool.  exp1 could enforce "gold never
reaches a prompt" structurally, because an index would have to be matched against
answer text to leak.  A bool cannot be grepped for, so the invariant is enforced by a
property test instead: every prompt built for an item with ``gold_flawed`` flipped must
be byte-identical.  That is a stronger check than the one it replaces.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from dataclasses import asdict, dataclass, field, fields
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable, Sequence

from .config import TurnStyle

EMPTY_TRANSCRIPT = "[This is the first round; no arguments have been made yet.]"

# The two verdicts, and the two sides a debater can be assigned. One vocabulary for
# both, because they are the same proposition: a debater argues for a verdict.
#
# The words are FLAWED/SOUND rather than YES/NO deliberately. The challenger's decision
# line is "Decision: STANDS|REVERSE" and a transcript quotes both; if the judge's line
# were "Verdict: YES|NO" a reader scanning the document would meet two unrelated
# yes/no decisions, and a mis-parse of one would look exactly like the other. The same
# reasoning is why the challenger's line shares no word with the verdict's: it did until
# 2026-08-25, and the challenger used SOUND for both propositions (LLM_NOTES §3n).
FLAWED = "FLAWED"
SOUND = "SOUND"
VERDICTS: tuple[str, ...] = (FLAWED, SOUND)


def complement(verdict: str) -> str:
    """The other verdict.  Named, because writing it inline invites an inversion."""
    if verdict not in VERDICTS:
        raise ValueError(f"verdict must be one of {VERDICTS}, got {verdict!r}")
    return SOUND if verdict == FLAWED else FLAWED


def verdict_for(gold_flawed: bool) -> str:
    """The verdict that is correct for an item with this label."""
    return FLAWED if gold_flawed else SOUND


class Speaker(StrEnum):
    """A debater.  ``ORDER`` is the fixed transcript order, Alice first."""

    ALICE = "Alice"
    BOB = "Bob"

    @property
    def position(self) -> int:
        return ORDER.index(self)

    @property
    def opponent(self) -> "Speaker":
        return ORDER[1 - self.position]


ORDER: tuple[Speaker, ...] = (Speaker.ALICE, Speaker.BOB)


# How an item's ground truth was derived. Recorded per item because the three answers
# mean genuinely different things, and a rate pooled across them means little:
#
#   injected_pair    a planted reasoning error, against an expert-verified sound sibling
#                    (the modified_* subsets). The cleanest label here.
#   sentence_labels  two reviewers concurring that this one sentence is illogical,
#                    untrue or misleading (the CELS subsets). Sentences they disagreed
#                    about are dropped, not labelled.
#   final_answer     annotators agreed with the model's final answer (medqa). The weak
#                    one: a solution that reasons badly and lands on the right answer is
#                    labelled sound, so a challenger objecting to it is *correct* rather
#                    than raising a false alarm. Kept deliberately, reported apart.
#
# The analysis stratifies on this and never pools across it by default.
LABEL_BASES: tuple[str, ...] = ("injected_pair", "sentence_labels", "final_answer")


@dataclass(frozen=True)
class Item:
    """One problem, one solution, and the hidden answer to "is it flawed?".

    An *item* is the unit that gets decided.  Upstream rows do not map to it one to
    one: a FindTheFlaws row carrying both a correct and a flawed solution yields two
    items, and a row carrying one naturally-occurring solution yields one.  That
    expansion happens in ``datasets`` and nothing downstream knows about it — except
    through ``row_id``, which is the only trace of it that survives.

    ``row_id`` is the clustering unit for the bootstrap.  Two items from one row share
    a problem statement, and for the injected-flaw subsets their solutions differ by a
    single edit, so treating them as independent draws would understate every interval.

    ``gold_flawed`` never reaches a prompt.  See the module docstring for how that is
    enforced now that it is a bool rather than an index.
    """

    item_id: str
    row_id: str
    subset: str
    problem: str
    solution: str
    gold_flawed: bool
    label_basis: str = "injected_pair"
    # False where the upstream data flags the *sound* side as unreliable — python800
    # marks 323 of 648 correct explanations this way. Such an item is kept and
    # stratified rather than dropped, because dropping half the largest subset over a
    # disagreement about the control side is a worse trade than reporting it.
    label_reliable: bool = True
    source: str | None = None

    def __post_init__(self) -> None:
        if not self.item_id:
            raise ValueError("item_id must be non-empty")
        if not self.solution.strip():
            raise ValueError(f"{self.item_id}: solution is empty")
        if self.label_basis not in LABEL_BASES:
            raise ValueError(
                f"{self.item_id}: label_basis must be one of {LABEL_BASES}, "
                f"got {self.label_basis!r}"
            )

    @property
    def gold_verdict(self) -> str:
        return verdict_for(self.gold_flawed)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Item":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    @classmethod
    def from_json(cls, path: Path) -> "Item":
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# What the flaw annotation is good for.  Not cosmetic: FindTheFlaws' GPQA subset
# annotates every flaw as "The first error occurs in Step N" — 9 distinct strings
# across 198 rows — which pins down *where* the error is and says nothing about *what*
# it is.  Grading whether an objection characterised the flaw against a string that
# characterises nothing would measure the grader's imagination, so the tier is recorded
# per subset and the valid-objection metric is computed only where it is "explanation".
ANNOTATION_QUALITIES: tuple[str, ...] = ("explanation", "location_only", "none")


@dataclass(frozen=True)
class FlawAnnotation:
    """What the dataset says is wrong with a flawed solution.

    Reaches exactly one place: the grader.  ``load_run_record`` does not read it, and
    no prompt on the decision or contest path interpolates it — an objection graded
    against an annotation the challenger was shown would measure nothing.
    """

    annotation_id: str
    flaw_location: str = ""  # a step pointer, where upstream gives one
    annotation: str = ""  # the natural-language account of what is wrong
    annotation_quality: str = "none"
    # "injected" for the modified_* subsets, "natural" for the CELS/medqa ones where
    # the flaw is a real model error rather than a planted edit. Worth keeping apart:
    # an injected flaw is a single localisable edit and a natural one need not be.
    origin: str = "injected"
    source: str | None = None

    def __post_init__(self) -> None:
        if self.annotation_quality not in ANNOTATION_QUALITIES:
            raise ValueError(
                f"annotation_quality must be one of {ANNOTATION_QUALITIES}, "
                f"got {self.annotation_quality!r}"
            )

    @property
    def grades_characterisation(self) -> bool:
        """Whether this annotation can support the valid-objection metric."""
        return self.annotation_quality == "explanation"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FlawAnnotation":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Case:
    """An item plus, when the item is flawed, what is wrong with it.

    The invariant below is the type-level statement of the design's rule that *no
    objection can be valid when the solution is sound*.  It matters because the CELS
    and medqa subsets carry a non-empty ``comments_on_llm_solution`` on **every** row,
    sound ones included — those comments are the annotators' review, not a flaw — and
    attaching them to a sound item would create a gradable "flaw" that does not exist
    and inflate the valid-objection rate on exactly the cell where it is undefined.
    """

    item: Item
    flaw: FlawAnnotation | None = None

    def __post_init__(self) -> None:
        if self.item.gold_flawed and self.flaw is None:
            raise ValueError(
                f"{self.item.item_id}: a flawed item must carry a FlawAnnotation "
                "(use annotation_quality='none' if the subset has no usable one)"
            )
        if not self.item.gold_flawed and self.flaw is not None:
            raise ValueError(
                f"{self.item.item_id}: a sound item must not carry a FlawAnnotation. "
                "No objection can be valid when the solution is sound, so there is "
                "nothing for a grader to grade against."
            )

    @property
    def gradable(self) -> bool:
        """Whether this case can support the valid-objection metric."""
        return self.flaw is not None and self.flaw.grades_characterisation

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Case":
        flaw = data.get("flaw")
        return cls(
            item=Item.from_dict(data["item"]),
            flaw=FlawAnnotation.from_dict(flaw) if flaw else None,
        )

    @classmethod
    def from_json(cls, path: Path) -> "Case":
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def to_dict(self) -> dict[str, Any]:
        return {
            "item": self.item.to_dict(),
            "flaw": self.flaw.to_dict() if self.flaw else None,
        }


def load_cases(path: Path) -> list[Case]:
    """Load one case from ``.json`` or many from ``.jsonl``."""
    if path.suffix == ".jsonl":
        return [
            Case.from_dict(json.loads(line))
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    return [Case.from_json(path)]


@dataclass(frozen=True)
class Sides:
    """Who argues what, and how the judge's two verdicts are ordered."""

    alice_side: str  # FLAWED or SOUND
    bob_side: str  # the complement
    verdict_order: tuple[str, str]  # the order the judge's template lists them in
    seed_material: str
    # Which of the two debater models speaks first, when the run uses two.
    # ``False`` — the default and the only value for a same-model debate — means
    # Alice takes ``debater_model``.
    #
    # A third independent draw, for the same reason as the other two: Alice always
    # speaks first, so "Alice is always DeepSeek" would make model identity a proxy for
    # speaking order, and a capability gap between the two would then read as a
    # first-mover effect. Drawn even when only one model is configured, so the sides
    # are identical whether or not the variant is used.
    swap_debater_models: bool = False

    def __post_init__(self) -> None:
        if self.alice_side not in VERDICTS:
            raise ValueError(f"alice_side must be one of {VERDICTS}")
        if self.bob_side != complement(self.alice_side):
            raise ValueError("bob_side must be the complement of alice_side")
        if tuple(sorted(self.verdict_order)) != tuple(sorted(VERDICTS)):
            raise ValueError(f"verdict_order must be a permutation of {VERDICTS}")

    def side_for(self, speaker: Speaker) -> str:
        return self.alice_side if speaker is Speaker.ALICE else self.bob_side

    def speaker_for_side(self, side: str) -> Speaker:
        if side not in VERDICTS:
            raise ValueError(f"side must be one of {VERDICTS}, got {side!r}")
        return Speaker.ALICE if self.alice_side == side else Speaker.BOB

    def model_for(self, speaker: Speaker, primary: str, secondary: str | None) -> str:
        """Which model speaks as this debater.

        ``secondary is None`` is the same-model variant: both sides get the primary,
        and the swap draw has no effect.
        """
        if secondary is None:
            return primary
        first, second = (
            (secondary, primary) if self.swap_debater_models else (primary, secondary)
        )
        return first if speaker is Speaker.ALICE else second

    def to_dict(self) -> dict[str, Any]:
        return {
            "alice_side": self.alice_side,
            "bob_side": self.bob_side,
            "verdict_order": list(self.verdict_order),
            "seed_material": self.seed_material,
            "swap_debater_models": self.swap_debater_models,
        }


def make_sides(item: Item, seed: int) -> Sides:
    """Draw sides deterministically, before any API call.

    Seeded on ``"{seed}:{item_id}"`` rather than the bare integer so the draw is stable
    per item regardless of iteration order — which matters as soon as a harness shards
    a dataset across workers, and again when a run is resumed.

    The three draws are independent: which side Alice argues says nothing about which
    verdict the judge's template lists first, nor about which model speaks first.
    """
    seed_material = f"{seed}:{item.item_id}"
    rng = random.Random(seed_material)
    alice_side = FLAWED if rng.randint(0, 1) == 0 else SOUND
    first_verdict = FLAWED if rng.randint(0, 1) == 0 else SOUND
    swap_models = bool(rng.randint(0, 1))
    return Sides(
        alice_side=alice_side,
        bob_side=complement(alice_side),
        verdict_order=(first_verdict, complement(first_verdict)),
        seed_material=seed_material,
        swap_debater_models=swap_models,
    )


@dataclass
class Turn:
    """One debater's contribution to one round."""

    round: int  # 1-based
    speaker: Speaker
    side: str  # FLAWED or SOUND, the position this speaker was assigned
    thinking: str
    argument: str
    word_count: int
    parse_mode: str
    repair_attempts: int
    finish_reason: str | None
    has_native_reasoning: bool
    call_id: str
    raw: str
    # The provider's own reasoning channel, when the model has one. Recorded as
    # text rather than as a bare flag because the project's claim is that every
    # channel which moved the outcome is *published* — and the newest models
    # refuse to disable this one, so suppressing it is no longer an option that
    # keeps the claim true. Empty when reasoning was off or none was returned.
    native_reasoning: str = ""
    # True when the provider billed reasoning tokens but returned no text for
    # them. That is a genuinely invisible channel and the one case the claim
    # cannot cover, so it is recorded per turn rather than averaged away.
    reasoning_withheld: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["speaker"] = str(self.speaker)
        return data


def count_words(argument: str) -> int:
    """Whitespace word count.  Recorded so overruns are visible, never enforced."""
    return len(argument.split())


@dataclass
class Transcript:
    turns: list[Turn] = field(default_factory=list)

    def add(self, turn: Turn) -> None:
        self.turns.append(turn)

    def all_turns(self) -> list[Turn]:
        """Every turn in protocol order: by round, Alice before Bob."""
        return sorted(self.turns, key=lambda t: (t.round, t.speaker.position))

    def visible_to(
        self, speaker: Speaker, round: int, turn_style: TurnStyle
    ) -> list[Turn]:
        """Turns this speaker may condition on when writing ``round``.

        Note this is only half of the turn-style mechanism.  The other half is
        the scheduler in ``debate.run_debate``: under ``asyncio.gather`` both
        debaters' calls are issued before either turn exists, so the sequential
        clause below can only ever be satisfied if the caller also awaits the
        two turns in order.
        """
        visible = [t for t in self.all_turns() if t.round < round]
        if turn_style == "sequential" and speaker is Speaker.BOB:
            visible += [
                t
                for t in self.all_turns()
                if t.round == round and t.speaker is Speaker.ALICE
            ]
        return visible

    def split_at(self, round: int) -> tuple["Transcript", "Transcript"]:
        """Split into the turns up to ``round`` and the turns after it.

        The one definition of "which of these turns are the recourse's own".
        The orchestrator, the writer and both renderers all need that split, and
        four hand-rolled ``round > parent_rounds`` comprehensions would be four
        chances to write ``>=``.
        """
        turns = self.all_turns()
        return (
            Transcript(turns=[t for t in turns if t.round <= round]),
            Transcript(turns=[t for t in turns if t.round > round]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"turns": [t.to_dict() for t in self.all_turns()]}


def compose_transcript(parent: Transcript, recourse: Transcript) -> Transcript:
    """The parent debate's turns followed by a recourse's, in one transcript.

    Recourse rounds continue the parent's numbering, so nothing downstream needs
    a round-aware special case: ``all_turns`` orders them correctly, and
    ``visible_to`` hands a recourse debater exactly the parent debate and
    nothing from its own round.

    Raises when a recourse turn does not sit strictly after every parent turn,
    which would mean the round numbering had lost track of where the original
    debate ended.
    """
    boundary = max((t.round for t in parent.all_turns()), default=0)
    for turn in recourse.all_turns():
        if turn.round <= boundary:
            raise ValueError(
                f"recourse turn at round {turn.round} does not follow the "
                f"parent's {boundary} round(s)"
            )
    combined = Transcript()
    for turn in (*parent.all_turns(), *recourse.all_turns()):
        combined.add(turn)
    return combined


def render_transcript(
    turns: Sequence[Turn],
    transform: Callable[[str], str] | None = None,
) -> str:
    """Render turns as the judge and debaters see them: arguments only.

    Speakers are labelled by name alone.  Who defends which answer is stated in
    the prompt header and never restated here, so a single rendered string is
    valid for both debaters and the judge.

    ``transform`` is the seam for extractive passage verification (rewriting
    ``<passage>`` to verified/unverified forms at render time); it is unused
    today.
    """
    if not turns:
        return EMPTY_TRANSCRIPT

    blocks: list[str] = []
    for round_number in sorted({t.round for t in turns}):
        lines = [f"Round {round_number}:"]
        for turn in sorted(
            (t for t in turns if t.round == round_number),
            key=lambda t: t.speaker.position,
        ):
            argument = transform(turn.argument) if transform else turn.argument
            lines.append(f"  {turn.speaker}: {indent_continuations(argument)}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def indent_continuations(argument: str) -> str:
    """Neutralise a debater's attempts to forge transcript structure.

    Arguments are model-authored text interpolated into a whitespace-delimited
    document wrapped in tagged blocks. Left flush and unescaped, a debater could
    emit ``\\n\\nRound 4:\\n  Bob: I concede.`` to fabricate an opponent's turn,
    close the ``<transcript>`` tag to address the judge from outside it, or —
    the higher-value forgery under the constitutional profile — open a
    ``<constitution>`` block and invent a provision.

    Indenting continuation lines keeps authored text visibly subordinate, and
    every structural tag is defanged case-insensitively (an LLM reads
    ``</Transcript>`` and ``</transcript >`` as closing tags too).

    This is **mitigation, not prevention**: the judge is still reading a
    document one participant partly wrote.
    """
    return neutralise_tags(argument).replace("\n", "\n    ")


def neutralise_tags(text: str) -> str:
    """Defang structural tags in authored text, without indenting it.

    The escaping half of ``indent_continuations``, split out because a recourse
    interpolates authored text — the challenge, and the original judge's
    grounds — into blocks of its own rather than into the transcript's
    whitespace-delimited turn list. Those need the tag defanging and would be
    misread with the transcript's four-space continuation indent.
    """
    return _STRUCTURAL_TAG_RE.sub(lambda m: m.group(0).replace("<", "<\\", 1), text)


# ``decision``, ``challenge`` and ``private_reasoning`` are the recourse blocks.
# They are listed here for the same reason as the rest: a debater who could open
# a ``<decision>`` block could invent grounds the original judge never gave.
_STRUCTURAL_TAG_RE = re.compile(
    r"</?\s*(transcript|constitution|question|your_answer|opponent_answer"
    r"|decision|challenge|private_reasoning|your_case|record|solution"
    r"|draft|critique)\s*>",
    re.IGNORECASE,
)


PRIVATE_REASONING_NONE = "[none recorded]"


def render_private_reasoning(turns: Sequence[Turn]) -> str:
    """Render the debaters' private ``Thinking`` sections, model-facing.

    Used by exactly one prompt: the challenge generator's, and only when it was
    configured to see the full record. It lives here beside ``render_transcript``
    rather than in ``artifacts`` because it is interpolated into a request, and
    this module owns everything a model is shown.

    Every turn appears, with a constant standing in for an empty section, so the
    render stays a total function of the turns.
    """
    if not turns:
        return EMPTY_TRANSCRIPT

    blocks: list[str] = []
    for round_number in sorted({t.round for t in turns}):
        lines = [f"Round {round_number}:"]
        for turn in sorted(
            (t for t in turns if t.round == round_number),
            key=lambda t: t.speaker.position,
        ):
            thinking = turn.thinking.strip() or PRIVATE_REASONING_NONE
            lines.append(f"  {turn.speaker}: {indent_continuations(thinking)}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


SOLO_STAGES: tuple[str, ...] = ("draft", "critique", "revision", "answer")


@dataclass
class Step:
    """One model contribution to a non-debate decision procedure.

    The sibling of ``Turn``, not a subclass. A ``Turn`` carries an
    ``side`` because a debater was *assigned* a position before it wrote
    a word; a step is written by an agent that was assigned nothing.

    Reusing ``Transcript`` with a solo ``Speaker.ALICE`` would have saved this
    class and made every renderer apply unchanged — but ``artifacts.positions()``
    would then state that Bob argues for ``answers[1]`` in a run where Bob never
    spoke. The whole claim under test is that the published record is readable
    *and true*, so the false statement is not worth the saving.
    """

    index: int  # 1-based, production order
    stage: str  # one of SOLO_STAGES
    thinking: str
    text: str
    word_count: int
    parse_mode: str
    repair_attempts: int
    finish_reason: str | None
    has_native_reasoning: bool
    call_id: str
    raw: str
    native_reasoning: str = ""
    reasoning_withheld: bool = False

    def __post_init__(self) -> None:
        if self.stage not in SOLO_STAGES:
            raise ValueError(f"stage must be one of {SOLO_STAGES}, got {self.stage!r}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Trace:
    """The steps of a non-debate decision, in production order."""

    steps: list[Step] = field(default_factory=list)

    def add(self, step: Step) -> None:
        self.steps.append(step)

    def all_steps(self) -> list[Step]:
        return sorted(self.steps, key=lambda s: s.index)

    def visible_to(self, index: int) -> list[Step]:
        """Steps this one may condition on: everything strictly before it."""
        return [s for s in self.all_steps() if s.index < index]

    def to_dict(self) -> dict[str, Any]:
        return {"steps": [s.to_dict() for s in self.all_steps()]}


def render_trace(steps: Sequence[Step]) -> str:
    """Render steps as the agent sees them on its next pass.

    Model-facing, and here rather than in ``artifacts`` for the same reason as
    ``render_transcript``: this module owns everything a model is shown.
    """
    if not steps:
        return EMPTY_TRACE
    return "\n\n".join(
        f"{s.stage.capitalize()}:\n{indent_continuations(s.text)}"
        for s in sorted(steps, key=lambda s: s.index)
    )


EMPTY_TRACE = "[Nothing has been written yet.]"


def render_trace_private_reasoning(steps: Sequence[Step]) -> str:
    """Render a solo agent's private ``Thinking`` sections, model-facing.

    The ``Trace`` analogue of ``render_private_reasoning``, and here for the same
    reason: it is interpolated into a request, and this module owns everything a
    model is shown.

    Every step appears, with a constant standing in for an empty section, so the
    render stays a total function of the steps. A constructed step has no
    thinking at all, and that is what this must then say — rather than omitting
    the step and leaving a reader to infer the record is shorter than it is.
    """
    if not steps:
        return EMPTY_TRACE
    return "\n\n".join(
        f"{s.stage.capitalize()}:\n"
        f"{indent_continuations(s.thinking.strip() or PRIVATE_REASONING_NONE)}"
        for s in sorted(steps, key=lambda s: s.index)
    )


@dataclass(frozen=True)
class DecisionRecord:
    """What a challenger is shown of a completed decision, in either shape.

    A decision reached by debate has a ``Transcript`` of ``Turn``s; one reached
    by a solo arm has a ``Trace`` of ``Step``s. Both are records of how a
    decision was made, and a challenger must be able to read either — but the
    two are different types with different renderers, and the recourse path used
    to reach for ``transcript`` unconditionally. A solo decision therefore
    presented as an empty debate: the challenger was shown
    ``EMPTY_TRANSCRIPT`` and told two debaters had argued.

    Normalising both to one type is what stops that being expressible. ``kind``
    is carried rather than inferred downstream so the prompt can say something
    true about which shape it is holding.

    Deliberately carries no ``Sides`` and no ``Verdict``: who argued for what
    is a claim only the debate shape can make, and the decision's grounds are
    ``RunRecord.decision_grounds``.
    """

    body: str
    private_reasoning: str
    kind: str  # "debate" | "solo"

    @classmethod
    def for_debate(cls, transcript: "Transcript") -> "DecisionRecord":
        turns = transcript.all_turns()
        return cls(
            body=render_transcript(turns),
            private_reasoning=render_private_reasoning(turns),
            kind="debate",
        )

    @classmethod
    def for_solo_body(
        cls, body: str, private_reasoning: str = PRIVATE_REASONING_NONE
    ) -> "DecisionRecord":
        """A solo record whose body is already rendered.

        The solo conditions now hold a real conversation rather than a ``Trace``, so the
        published record is assembled from that conversation's assistant turns. Kept
        beside ``for_solo`` rather than replacing it so both shapes normalise to the one
        type the challenger and the recourse judge accept.
        """
        return cls(body=body, private_reasoning=private_reasoning, kind="solo")

    @classmethod
    def for_solo(cls, trace: "Trace") -> "DecisionRecord":
        steps = trace.all_steps()
        return cls(
            body=render_trace(steps),
            private_reasoning=render_trace_private_reasoning(steps),
            kind="solo",
        )



@dataclass
class Verdict:
    """The decision, and enough context to account for it.

    Produced by all three conditions: the debate judge reaches it from a transcript,
    the solo conditions from their own reasoning. One type, because everything
    downstream — the contest, the index, the analysis — must treat them alike or the
    comparison is not a comparison.

    There is deliberately no confidence field. Judge confidence is listed in DESIGN.md
    as an ablation, and adding it here would put it in the record of every run that did
    not ask for it.
    """

    verdict: str  # FLAWED or SOUND
    parse_mode: str
    raw: str
    call_id: str
    finish_reason: str | None
    correct: bool | None  # None when the item carries no label
    # Published, because how a decision was obtained is part of it: a verdict that came
    # from a format-repair reply says so in the readable document.
    repair_attempts: int = 0
    # The stated grounds, parsed out of ``raw``: everything preceding the decisive
    # "Verdict:" line.  Distinct from ``Completion.reasoning``, which is the provider's
    # *native* reasoning channel — a second private channel outside the protocol that
    # ``reasoning_effort = "off"`` suppresses.  Empty when the model decided before
    # explaining; ``raw`` is always the complete record, and the markdown artifact
    # renders that instead.
    reasoning: str = ""
    # The provider's own reasoning channel, distinct from ``reasoning`` above.
    # Published for the same reason a debater's is: the claim is that every channel
    # which moved the decision is in the record, and a judge's hidden deliberation
    # moves it more directly than anyone's.
    native_reasoning: str = ""
    reasoning_withheld: bool = False

    def __post_init__(self) -> None:
        if self.verdict not in VERDICTS:
            raise ValueError(f"verdict must be one of {VERDICTS}, got {self.verdict!r}")

    @property
    def says_flawed(self) -> bool:
        return self.verdict == FLAWED

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        # A derived property, serialised explicitly for the same reason as
        # ``Ruling.changed_the_decision``: ``asdict`` omits properties, and the index
        # reads this straight out of verdict.json.
        data["says_flawed"] = self.says_flawed
        return data


@dataclass
class DebateResult:
    run_id: str
    item: Item
    sides: Sides
    transcript: Transcript
    verdict: Verdict


# --------------------------------------------------------------------------- #
# recourse
# --------------------------------------------------------------------------- #
#
# What a challenger did, in three kinds. ``Challenge.raised`` keeps its literal
# meaning — the model asked for the decision to be reversed — and every *gate* in the
# pipeline reads ``stance``, because two earlier instructions proved that a word alone
# does not say which way the challenger went.
#
#   contests   `Decision: REVERSE`. The challenger says the verdict is wrong. The only
#              stance that seeks a ruling.
#   declined   `Decision: STANDS`. A recorded judgement that the decision looks sound.
#   unclear    no parsable line, after the one repair. Its own column: excluded from the
#              rates, counted in coverage. It is NOT malformed — making it so would let
#              the experiment's own subject role lose an entire contest to a
#              DebateFailure, and the challenger's measured repair rate is 0%.
#
# ``agrees`` is kept in the vocabulary and is now **unreachable**. It was the fourth
# kind under the two-line instruction — RAISED beside a claimed verdict equal to the one
# already given — and the single relative line cannot express it: a reply cannot both
# ask for a reversal and name the verdict it is reversing to. The name survives so that
# `challenge_agreed` stays a column that reads 0 rather than disappearing, which is a
# different claim from a column that was never written. What replaced the detection is
# the `agreement` stage, which reads the prose independently of the line.
CHALLENGE_STANCES: tuple[str, ...] = ("contests", "agrees", "declined", "unclear")

# The challenger's two words, stated relative to the decision.
STANDS = "STANDS"
REVERSE = "REVERSE"
DECISION_WORDS: tuple[str, ...] = (STANDS, REVERSE)


def challenge_stance(word: str | None) -> str:
    """The stance, from the one decision line.

    ``None`` — no parsable line after the repair — is ``unclear``, which seeks no ruling
    and is excluded from the rates rather than counted either way.
    """
    if word is None:
        return "unclear"
    if word not in DECISION_WORDS:
        raise ValueError(f"decision word must be one of {DECISION_WORDS}, got {word!r}")
    return "contests" if word == REVERSE else "declined"


def claimed_verdict_for(word: str | None, decision_verdict: str) -> str | None:
    """The verdict the challenger is asking for, derived rather than stated.

    Under the two-line instruction the challenger named this verdict itself, and named
    it wrongly often enough to be the reason the instruction changed: SOUND meant "the
    text is sound" and "the verdict is sound" in the same reply. REVERSE means the
    complement of what was decided and STANDS means what was decided, with no word in
    common between the two vocabularies and nothing for the challenger to translate.

    ``None`` for ``unclear``: a reply whose direction could not be read is not asking
    for either verdict, and defaulting it to one would manufacture a claim.
    """
    if word is None:
        return None
    if decision_verdict not in VERDICTS:
        raise ValueError(
            f"decision_verdict must be one of {VERDICTS}, got {decision_verdict!r}"
        )
    return complement(decision_verdict) if word == REVERSE else decision_verdict


@dataclass(frozen=True)
class Challenge:
    """An argument that a completed decision was mistaken.

    ``text`` is the document itself; everything else is provenance. A challenge
    is an *input* to a recourse in the way a constitution is an input to a
    debate, so it is recorded beside the run rather than folded into its config.

    ``arm`` and ``visibility`` are hidden variables in the same sense as
    ``Item.gold_flawed``: they determine what the challenge is, and must leave no
    trace in any prompt downstream of the generator, or a judge would be scoring
    the label instead of the argument.
    """

    text: str
    origin: str  # "file" | "generated"
    # False when the challenger reviewed the decision and found nothing to
    # contest. Not the same as an empty challenge: a decline is a recorded
    # judgement that the decision looks sound, and it is what separates "did
    # not detect the error" from "detected it and argued badly". Defaulted so
    # that a challenge written before this existed, and every supplied one,
    # loads as raised.
    raised: bool = True
    # The verdict the challenger is asking for, DERIVED from its decision line and the
    # verdict under review (``claimed_verdict_for``) rather than stated by the model.
    # ``raised`` is the direction it asked for; ``stance`` is what the pipeline gates on.
    # Empty means "derive from ``raised``", which is what a challenge written before this
    # existed — or supplied from a file — loads as.
    claimed_verdict: str | None = None
    stance: str = ""
    # A reply that declined and yet named the contrary verdict. Unreachable since
    # 2026-08-25: there is one line and it cannot disagree with itself. The field stays
    # so that the column reads 0 rather than vanishing, and so that pilot-2's records
    # remain loadable.
    contradictory: bool = False
    source: str | None = None  # the path, when origin == "file"
    arm: str | None = None  # "grounded" | "specious" | "neutral" | "stakeholder"
    visibility: str | None = None  # "public" | "full" — what the generator saw
    model: str | None = None
    call_id: str | None = None
    finish_reason: str | None = None
    parse_mode: str | None = None
    repair_attempts: int = 0
    # The generator's own scratchpad, recorded for the same reason a debater's
    # is. It is not part of the challenge: what goes to the judge is the
    # argument, and this is the working behind it.
    thinking: str = ""
    raw: str = ""
    # As on ``Verdict``: the provider's channel, beside the generator's own
    # ``thinking``. A challenge written partly in a channel nobody can read is
    # exactly what the transparency claim rules out.
    native_reasoning: str = ""
    reasoning_withheld: bool = False

    def __post_init__(self) -> None:
        if not self.stance:
            object.__setattr__(
                self, "stance", "contests" if self.raised else "declined"
            )
        if self.stance not in CHALLENGE_STANCES:
            raise ValueError(
                f"stance must be one of {CHALLENGE_STANCES}, got {self.stance!r}"
            )
        # ``raised`` means exactly ``contests`` now. Under the two-line instruction it
        # meant "the model wrote RAISED", which was also true of ``agrees`` and of
        # ``unclear``; with one relative line there is no such reply — a challenge that
        # could not be read is not a request for anything, so ``unclear`` carries
        # raised=False. The consequence to know about: a challenge.json written before
        # 2026-08-25 with stance "agrees" or "unclear" no longer loads, which is correct
        # — those stances were recorded under an instrument this one does not implement.
        if self.raised != (self.stance == "contests"):
            raise ValueError(
                f"stance {self.stance!r} disagrees with raised={self.raised}"
            )

    @property
    def shown_private_reasoning(self) -> bool:
        """Whether the generator was shown reasoning the deciding judge lacked.

        Not a secrecy question — the record publishes the ``Thinking`` sections
        anyway. What it marks is an asymmetry between the two decisions: a
        challenge written from this material can put to the recourse judge
        something the judge who decided the question never had. Only a
        *generated* challenge can have been shown anything; a supplied one was
        written by whoever wrote it, and the field says nothing about it.
        """
        return self.origin == "generated" and self.visibility == "full"

    def sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Challenge":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})




# How a re-decision was obtained. The two conditions ask genuinely different
# questions, and the record has to say which was asked rather than leaving a reader to
# infer it from the model name.
#
#   uphold_overturn   the debate condition. A recourse judge is asked whether the
#                     objection shows the decision to be mistaken. The burden is on the
#                     challenger; the verdict is *derived* from UPHOLD/OVERTURN.
#   restated_verdict  the solo conditions. The model that decided is handed the
#                     objection in its own conversation and asked for its verdict
#                     again. The verdict is parsed, not derived.
#
# Worth naming because the second form asks a model to contradict itself, which is the
# axis on which models are most sycophantic. A revision rate under that form is not
# directly comparable to one under the first, and the analysis says so.
RULING_FORMS: tuple[str, ...] = ("uphold_overturn", "restated_verdict")


@dataclass
class Ruling:
    """The re-decision after a contest, and enough context to account for it.

    For the ``uphold_overturn`` form, ``verdict`` is *derived*, never parsed: unchanged
    if the decision is upheld, flipped if it is overturned. That asymmetry is the whole
    point of recourse — the decision stands unless the objection moves it — so the
    record states both halves, the ruling given and the verdict that follows from it,
    so a reader can check the implication rather than taking it on trust.

    For the ``restated_verdict`` form there is no ruling word; the model simply says
    what it now thinks, and ``ruling`` is None.
    """

    form: str  # one of RULING_FORMS
    ruling: str | None  # "UPHOLD" | "OVERTURN" for uphold_overturn, else None
    protocol: str  # "judge_only" | "in_conversation", named rather than inferred
    parent_verdict: str
    verdict: str
    parse_mode: str
    raw: str
    call_id: str
    finish_reason: str | None
    correct: bool | None  # None when the item carries no label
    repair_attempts: int = 0
    # As on ``Verdict``: the text preceding the decisive match.
    reasoning: str = ""
    native_reasoning: str = ""
    reasoning_withheld: bool = False

    def __post_init__(self) -> None:
        if self.form not in RULING_FORMS:
            raise ValueError(f"form must be one of {RULING_FORMS}, got {self.form!r}")
        if self.verdict not in VERDICTS:
            raise ValueError(f"verdict must be one of {VERDICTS}, got {self.verdict!r}")
        if self.parent_verdict not in VERDICTS:
            raise ValueError(f"parent_verdict must be one of {VERDICTS}")
        if self.form == "uphold_overturn":
            if self.ruling not in RULINGS:
                raise ValueError(
                    f"the uphold_overturn form needs a ruling in {RULINGS}, "
                    f"got {self.ruling!r}"
                )
            expected = resolve_ruling(self.ruling, self.parent_verdict)
            if self.verdict != expected:
                raise ValueError(
                    f"{self.ruling} on a {self.parent_verdict} decision implies "
                    f"{expected}, but verdict is {self.verdict}"
                )
        elif self.ruling is not None:
            raise ValueError("the restated_verdict form must not carry a ruling word")

    @property
    def upheld(self) -> bool:
        return self.verdict == self.parent_verdict

    @property
    def changed_the_decision(self) -> bool:
        return self.verdict != self.parent_verdict

    def to_dict(self) -> dict[str, Any]:
        # The properties must be serialised explicitly: ``asdict`` omits them, and the
        # index reads ``changed_the_decision`` straight out of ruling.json. Left out,
        # every headline revision rate reads 0/N with a confident interval — a wrong
        # number that never crashes.
        data = asdict(self)
        data["upheld"] = self.upheld
        data["changed_the_decision"] = self.changed_the_decision
        return data


RULINGS: tuple[str, ...] = ("UPHOLD", "OVERTURN")


def resolve_ruling(ruling: str, parent_verdict: str) -> str:
    """The verdict a ruling leaves standing.

    One line, but it is *the* decision rule of the judge-only recourse protocol, so it
    has a name rather than being written out inline, where it would be one
    ``complement`` away from silently inverting every contested decision.
    """
    if ruling not in RULINGS:
        raise ValueError(f"ruling must be UPHOLD or OVERTURN, got {ruling!r}")
    return parent_verdict if ruling == "UPHOLD" else complement(parent_verdict)


@dataclass
class RecourseResult:
    run_id: str
    parent_run_id: str
    item: Item
    sides: Sides
    challenge: Challenge
    transcript: Transcript  # the recourse turns only; empty under judge-only recourse
    # ``None`` when the challenger declined: there was nothing to rule on, so no ruling
    # was sought and none is written. A reader — and the analysis — distinguishes "the
    # decision survived an objection" from "the decision was never objected to" by
    # which of the two is absent.
    ruling: Ruling | None
    # Asked even on a decline: it is a question about the record's readability, not
    # about the objection.
    comprehension: "Comprehension | None" = None


# --------------------------------------------------------------------------- #
# the line-vs-prose instrument
# --------------------------------------------------------------------------- #
#
# What a reader of the objection's PROSE says it argues, independently of the label the
# challenger put at the top of it. The three values are the grader's, not the
# challenger's: RIGHT / WRONG / NEITHER about the verdict under review.
PROSE_STANCES: tuple[str, ...] = ("RIGHT", "WRONG", "NEITHER")

# Which prose stance each decision word implies, so the agreement test is a table rather
# than an inline comparison that can be inverted by a typo.
_IMPLIED_PROSE = {REVERSE: "WRONG", STANDS: "RIGHT"}


def line_prose_agree(word: str | None, prose_stance: str) -> bool | None:
    """Whether the challenger's line and its own prose point the same way.

    ``None`` when there is nothing to compare — an unreadable line, or prose that takes
    no side. NEITHER is deliberately not folded into "disagrees": a response that raises
    a doubt without arguing either way has not contradicted its label, it has failed to
    support it, and those are different findings.
    """
    if word is None or prose_stance == "NEITHER":
        return None
    return _IMPLIED_PROSE[word] == prose_stance


@dataclass(frozen=True)
class Agreement:
    """One grader reading of one objection's prose. Off the decision path, always.

    Its whole reason for existing is that the challenger's line is a single relative
    token and nothing mechanical can check it against what the challenger then wrote.
    ``phantom_contest`` is the failure it was built to count: REVERSE at the top of a
    response that goes on to argue the verdict was right.
    """

    prose_stance: str  # one of PROSE_STANCES
    line_word: str | None  # the challenger's own word, copied for the cross-tab
    reasoning: str
    model: str
    parse_mode: str
    raw: str
    call_id: str
    finish_reason: str | None
    repair_attempts: int = 0
    native_reasoning: str = ""
    reasoning_withheld: bool = False

    def __post_init__(self) -> None:
        if self.prose_stance not in PROSE_STANCES:
            raise ValueError(
                f"prose_stance must be one of {PROSE_STANCES}, "
                f"got {self.prose_stance!r}"
            )
        if self.line_word is not None and self.line_word not in DECISION_WORDS:
            raise ValueError(
                f"line_word must be one of {DECISION_WORDS} or None, "
                f"got {self.line_word!r}"
            )

    @property
    def agrees(self) -> bool | None:
        return line_prose_agree(self.line_word, self.prose_stance)

    @property
    def phantom_contest(self) -> bool:
        """A contest in the label and an endorsement in the prose."""
        return self.line_word == REVERSE and self.prose_stance == "RIGHT"

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "agrees": self.agrees,
                "phantom_contest": self.phantom_contest}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Agreement":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})


# Identifies the anchor text a score was given against, so a rating recorded today is
# still interpretable if the wording is ever changed. Bump it when the scale changes.
COMPREHENSION_SCALE_ID = "followability-1to5-v1"


@dataclass(frozen=True)
class Comprehension:
    """The challenger's self-reported ability to follow the decision's reasoning.

    A proxy for transparency, and a weak one: a model's self-report measures its
    willingness to claim comprehension as much as its comprehension. Recorded with the
    anchor text verbatim so the record says what a 4 meant, and reported as a
    distribution rather than a mean, because a flat 4-5 with no variance is the
    expected outcome and a mean would hide it.
    """

    score: int  # 1..5
    scale: str  # the anchor text as shown, verbatim
    justification: str
    asked_after_decline: bool
    model: str
    parse_mode: str
    raw: str
    call_id: str
    finish_reason: str | None
    repair_attempts: int = 0
    native_reasoning: str = ""
    reasoning_withheld: bool = False

    def __post_init__(self) -> None:
        if not 1 <= self.score <= 5:
            raise ValueError(f"comprehension score must be 1..5, got {self.score}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

"""Core protocol types.

The central concern of this module is keeping three orderings apart:

1. ``Task.answers``          -- the task's intrinsic answer list;
2. ``Seating.alice_answer``  -- which debater defends which answer;
3. ``Seating.choice_order``  -- which answer the judge is shown as choice 1 vs 2.

Alice always speaks first in the transcript (per the protocol), while
``choice_order`` is drawn independently.  If those two correlate, "choice 1"
silently becomes "the debater who spoke first" and the randomisation that exists
to neutralise position bias stops doing anything.
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


@dataclass(frozen=True)
class Context:
    """Run-level context supplied alongside a task, e.g. a constitution.

    Deliberately *not* a ``Task`` field: a task is exactly what came off disk,
    and ``task.json`` in the record is that file. Folding a runtime
    ``--constitution`` into it would mean the recorded task no longer matched
    the fixture it names, and a reader could not tell which parts of it were
    supplied at the command line.
    """

    kind: str  # currently only "constitution"
    text: str
    source: str | None = None

    def sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Task:
    """A binary-choice question.

    ``gold_index`` is an index rather than an answer string so that "the gold
    answer never reaches a prompt" is a checkable invariant: a string would have
    to be matched against answer text somewhere, and that match would drift.
    """

    task_id: str
    question: str
    answers: tuple[str, str]
    gold_index: int | None = None
    source: str | None = None

    def __post_init__(self) -> None:
        if len(self.answers) != 2:
            raise ValueError(f"a task needs exactly 2 answers, got {len(self.answers)}")
        if self.gold_index is not None and self.gold_index not in (0, 1):
            raise ValueError(f"gold_index must be 0, 1 or None, got {self.gold_index}")

    @property
    def verifiable(self) -> bool:
        return self.gold_index is not None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        return cls(
            task_id=data["task_id"],
            question=data["question"],
            answers=(data["answers"][0], data["answers"][1]),
            gold_index=data.get("gold_index"),
            source=data.get("source"),
        )

    @classmethod
    def from_json(cls, path: Path) -> "Task":
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "question": self.question,
            "answers": list(self.answers),
            "gold_index": self.gold_index,
            "source": self.source,
        }


ERROR_TYPES: tuple[str, ...] = (
    "unspecified",
    "factual",
    "inference",
    "omission",
    "misinterpretation",
    "aggregation",
    "logical",
)

# What the annotation is good for. Not cosmetic: FindTheFlaws' GPQA subset
# annotates every flaw as "The first error occurs in Step N" -- 9 distinct
# strings across 198 rows -- which pins down *where* the error is and says
# nothing about *what* it is. Grading whether a challenge characterised the
# error needs the second thing. Carrying the distinction on the data means the
# grader and the analysis can skip what they cannot measure, instead of a
# subset name being hardcoded somewhere downstream.
ANNOTATION_QUALITIES: tuple[str, ...] = ("explanation", "location_only", "none")


@dataclass(frozen=True)
class ErrorSpec:
    """A known error in a case, and how it got there.

    Two halves that must never be confused.

    ``seed`` and ``sound_seed`` are inputs to the *decision procedure*: they
    reach the prompts of the roles named in ``seed_targets`` and no others.

    ``flaw_location`` and ``annotation`` are inputs to the *grader*: where the
    error is and what it is. They reach no prompt anywhere on the decision path.
    That is enforced structurally rather than by convention -- ``load_run_record``
    does not read ``error.json``, so nothing downstream of a decision can reach
    them even by accident.

    ``mechanism`` is written *after* the decision, by the runner: an error case
    is ``genuine`` when the procedure fell for the seeded flaw unaided, and
    ``manufactured`` when the adjudicator had to be steered to reach it. Both
    are usable; only the first is evidence about what the system does on its own.
    """

    error_id: str
    error_type: str = "unspecified"
    origin: str = "dataset"  # "dataset" | "injected" | "natural"
    mechanism: str = ""  # "genuine" | "manufactured", set post hoc
    seed: str = ""  # the flawed reasoning, given to the wrong-side role
    sound_seed: str = ""  # the correct reasoning, given to the right-side role
    # False where upstream annotators disagreed about whether the *sound* seed
    # is itself sound — 323 of Python650's 648 rows. Such a case is still fine
    # for detection (the flawed side is annotated either way) and shaky as a
    # control, so it is stratified in the analysis rather than dropped, and the
    # reason is carried here rather than being re-derived from a subset name.
    sound_seed_reliable: bool = True
    seed_targets: tuple[str, ...] = ()
    flaw_location: str = ""  # ground truth for "where"
    annotation: str = ""  # ground truth for "what"
    annotation_quality: str = "none"
    corrected_answer_index: int | None = None
    source: str | None = None

    def __post_init__(self) -> None:
        if self.error_type not in ERROR_TYPES:
            raise ValueError(
                f"error_type must be one of {ERROR_TYPES}, got {self.error_type!r}"
            )
        if self.annotation_quality not in ANNOTATION_QUALITIES:
            raise ValueError(
                f"annotation_quality must be one of {ANNOTATION_QUALITIES}, "
                f"got {self.annotation_quality!r}"
            )

    @property
    def grades_characterisation(self) -> bool:
        """Whether this case can support the strict valid-objection metric.

        False for a location-only annotation: there is nothing to check a
        challenge's characterisation of the error *against*, so scoring one
        would be scoring the grader's imagination.
        """
        return self.annotation_quality == "explanation"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["seed_targets"] = list(self.seed_targets)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ErrorSpec":
        known = {f.name for f in fields(cls)}
        kwargs = {k: v for k, v in data.items() if k in known}
        if "seed_targets" in kwargs:
            kwargs["seed_targets"] = tuple(kwargs["seed_targets"])
        return cls(**kwargs)


@dataclass(frozen=True)
class Case:
    """A task and the error it is known to contain, as one file on disk.

    A case is the unit the experiment iterates. The task half is exactly what a
    ``--task`` file would have held, so a case can always be run as a plain
    task by ignoring its error half -- which is what the correct-condition arm
    does.
    """

    task: Task
    error: ErrorSpec | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Case":
        # A bare task file is a valid case with no known error, so the same
        # loader serves both and --case never has to guess at the shape.
        if "task" not in data:
            return cls(task=Task.from_dict(data), error=None)
        error = data.get("error")
        return cls(
            task=Task.from_dict(data["task"]),
            error=ErrorSpec.from_dict(error) if error else None,
        )

    @classmethod
    def from_json(cls, path: Path) -> "Case":
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task.to_dict(),
            "error": self.error.to_dict() if self.error else None,
        }


def seeded_case_for(
    *, speaker: "Speaker", seating: "Seating", task: Task, error: ErrorSpec | None
) -> str:
    """The reasoning handed to this debater as the case for its answer.

    The correct solution goes to whoever defends the gold answer and the flawed
    one to whoever defends the other — which is what makes the constructed error
    the *same bytes* in every arm rather than merely the same specification.

    Keyed on ``task.gold_index``, never on literal index 0. ``gold_index`` is
    drawn per task precisely so that "correct" is not confounded with "first in
    ``Task.answers``", and written as ``answers[0]`` this would hand the flawed
    solution to the debater defending the *right* answer on half the dataset.
    Every run would still complete, the transcripts would still read plausibly,
    and the error condition would be silently inverted on half the corpus.
    """
    if error is None or task.gold_index is None:
        return ""
    defending = seating.answer_for(speaker)
    return error.sound_seed if defending == task.gold_index else error.seed


def seeded_case_for_solo(*, task: Task, error: ErrorSpec | None) -> str:
    """The reasoning handed to a solo agent as its own.

    A solo arm has no sides, so there is nothing to key on the way
    ``seeded_case_for`` keys on which answer a debater defends. It gets the
    flawed reasoning in the error condition and the correct reasoning otherwise
    — which is what makes the constructed error the *same bytes* here as in the
    debate arm's flawed side.

    ``ErrorSpec.seed`` is the flawed text by construction, so "the error
    condition" is simply "an error spec was supplied".
    """
    if error is None or task.gold_index is None:
        return ""
    return error.seed


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
class Seating:
    """Who defends what, and how the judge's two choices are ordered."""

    alice_answer: int
    bob_answer: int
    choice_order: tuple[int, int]  # choice N shows task.answers[choice_order[N-1]]
    seed_material: str
    # Which of the two debater models speaks first, when the run uses two.
    # ``False`` — the default and the only value for a same-model debate — means
    # Alice takes ``debater_model``.
    #
    # A fourth independent draw, for the same reason as the other three: Alice
    # always speaks first, so "Alice is always DeepSeek" would make model
    # identity a proxy for speaking order, and a capability gap between the two
    # would then read as a first-mover effect. Drawn even when only one model is
    # configured, so the seating is identical whether or not the variant is used.
    swap_debater_models: bool = False

    def answer_for(self, speaker: Speaker) -> int:
        return self.alice_answer if speaker is Speaker.ALICE else self.bob_answer

    def answer_index_for_choice(self, choice: int) -> int:
        """Map a judge choice (1 or 2) back to an index into ``Task.answers``."""
        if choice not in (1, 2):
            raise ValueError(f"choice must be 1 or 2, got {choice}")
        return self.choice_order[choice - 1]

    def choice_for_answer(self, answer_index: int) -> int:
        """The inverse: the judge choice (1 or 2) that showed this answer.

        Lives here rather than only in ``artifacts`` because a recourse prompt
        has to name the decided answer by the number the judge saw, and
        ``prompts`` cannot import ``artifacts`` — nothing in that module may
        reach a prompt.
        """
        return self.choice_order.index(answer_index) + 1

    def speaker_for_choice(self, choice: int) -> Speaker:
        answer_index = self.answer_index_for_choice(choice)
        return Speaker.ALICE if answer_index == self.alice_answer else Speaker.BOB

    def model_for(self, speaker: "Speaker", primary: str, secondary: str | None) -> str:
        """Which model speaks as this debater.

        ``secondary is None`` is the same-model variant: both sides get the
        primary, and the swap draw has no effect.
        """
        if secondary is None:
            return primary
        first, second = (
            (secondary, primary) if self.swap_debater_models else (primary, secondary)
        )
        return first if speaker is Speaker.ALICE else second

    def to_dict(self) -> dict[str, Any]:
        return {
            "alice_answer": self.alice_answer,
            "bob_answer": self.bob_answer,
            "choice_order": list(self.choice_order),
            "seed_material": self.seed_material,
            "swap_debater_models": self.swap_debater_models,
        }


def make_seating(task: Task, seed: int) -> Seating:
    """Draw seating deterministically, before any API call.

    Seeded on ``"{seed}:{task_id}"`` rather than the bare integer so seating is
    stable per task regardless of iteration order — which matters as soon as a
    harness shards a dataset across workers.

    The two draws are independent: which answer Alice defends says nothing about
    which answer the judge sees first.
    """
    seed_material = f"{seed}:{task.task_id}"
    rng = random.Random(seed_material)
    alice_answer = rng.randint(0, 1)
    first_choice = rng.randint(0, 1)
    swap_models = bool(rng.randint(0, 1))
    return Seating(
        alice_answer=alice_answer,
        bob_answer=1 - alice_answer,
        choice_order=(first_choice, 1 - first_choice),
        seed_material=seed_material,
        swap_debater_models=swap_models,
    )


@dataclass
class Turn:
    """One debater's contribution to one round."""

    round: int  # 1-based
    speaker: Speaker
    answer_index: int
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
    ``answer_index`` because a debater was *assigned* an answer before it wrote
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


@dataclass
class Verdict:
    """The judge's decision, and enough context to account for it."""

    choice: int  # 1 or 2, as presented to the judge
    answer_index: int  # resolved index into Task.answers
    parse_mode: str
    raw: str
    call_id: str
    finish_reason: str | None
    correct: bool | None  # None when the task has no gold answer
    # Published, because how a decision was obtained is part of it: a verdict
    # that came from a format-repair reply says so in the readable document.
    repair_attempts: int = 0
    # The judge's stated grounds, parsed out of ``raw``: everything preceding
    # the decisive "Answer:" line.  Distinct from ``Completion.reasoning``,
    # which is the provider's *native* reasoning channel — a second private
    # channel outside the protocol that ``reasoning_effort = "off"`` suppresses.
    # Empty when the judge decided before explaining; ``raw`` is always the
    # complete record, and the markdown artifact renders that instead.
    reasoning: str = ""
    # The provider's own reasoning channel, distinct from ``reasoning`` above,
    # which is the judge's stated grounds parsed out of ``raw``. Published for
    # the same reason a debater's is: the claim is that every channel which
    # moved the decision is in the record, and a judge's hidden deliberation
    # moves it more directly than anyone's.
    native_reasoning: str = ""
    reasoning_withheld: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DebateResult:
    run_id: str
    task: Task
    seating: Seating
    transcript: Transcript
    verdict: Verdict


# --------------------------------------------------------------------------- #
# recourse
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Challenge:
    """An argument that a completed decision was mistaken.

    ``text`` is the document itself; everything else is provenance. A challenge
    is an *input* to a recourse in the way a constitution is an input to a
    debate, so it is recorded beside the run rather than folded into its config.

    ``arm`` and ``visibility`` are hidden variables in the same sense as
    ``Task.gold_index``: they determine what the challenge is, and must leave no
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


@dataclass
class Ruling:
    """The recourse judge's decision, and enough context to account for it.

    ``answer_index`` is *derived*, never parsed: unchanged if the decision is
    upheld, flipped if it is overturned. That asymmetry is the whole point of
    recourse — the decision stands unless the challenge moves it — so the record
    states both halves, the ruling the judge gave and the index that follows
    from it, so a reader can check the implication rather than taking it on
    trust.
    """

    ruling: str  # "UPHOLD" | "OVERTURN"
    upheld: bool
    protocol: str  # "judge_only" | "debate", named rather than inferred
    parent_answer_index: int
    parent_choice: int
    answer_index: int  # derived from the two above
    choice: int  # the same answer in the inherited seating's numbering
    parse_mode: str
    raw: str
    call_id: str
    finish_reason: str | None
    correct: bool | None  # None when the task has no gold answer
    repair_attempts: int = 0
    # As on ``Verdict``: the text preceding the decisive "Ruling:" match.
    reasoning: str = ""
    native_reasoning: str = ""
    reasoning_withheld: bool = False

    @property
    def changed_the_decision(self) -> bool:
        return self.answer_index != self.parent_answer_index

    def to_dict(self) -> dict[str, Any]:
        # The property must be serialised explicitly: ``asdict`` omits it, and
        # the index reads ``changed_the_decision`` straight out of ruling.json.
        # Left out, every headline revision rate reads 0/N with a confident
        # interval — a wrong number that never crashes.
        data = asdict(self)
        data["changed_the_decision"] = self.changed_the_decision
        return data


def resolve_ruling(ruling: str, parent_answer_index: int) -> int:
    """The answer a ruling leaves standing.

    One line, but it is *the* decision rule of the recourse protocol, so it has
    a name rather than being written out inline, where it would be one
    ``1 -`` away from silently inverting every contested decision.
    """
    if ruling not in ("UPHOLD", "OVERTURN"):
        raise ValueError(f"ruling must be UPHOLD or OVERTURN, got {ruling!r}")
    return parent_answer_index if ruling == "UPHOLD" else 1 - parent_answer_index


@dataclass
class RecourseResult:
    run_id: str
    parent_run_id: str
    task: Task
    seating: Seating
    challenge: Challenge
    transcript: Transcript  # the recourse turns only
    # ``None`` when the challenger declined to challenge: there was nothing to
    # rule on, so no ruling was sought and none is written. A reader — and the
    # analysis — distinguishes "the decision survived a challenge" from "the
    # decision was never challenged" by which of the two is absent.
    ruling: Ruling | None

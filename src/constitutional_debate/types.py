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
from dataclasses import asdict, dataclass, field
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

    Deliberately *not* a ``Task`` field: a task is exactly what came off disk and
    ``task_sha256`` hashes that file.  Folding a runtime ``--constitution`` into
    the task would mean the recorded hash no longer matched the fixture, breaking
    the provenance chain the audit depends on.
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


@dataclass(frozen=True)
class Seating:
    """Who defends what, and how the judge's two choices are ordered."""

    alice_answer: int
    bob_answer: int
    choice_order: tuple[int, int]  # choice N shows task.answers[choice_order[N-1]]
    seed_material: str

    def answer_for(self, speaker: Speaker) -> int:
        return self.alice_answer if speaker is Speaker.ALICE else self.bob_answer

    def answer_index_for_choice(self, choice: int) -> int:
        """Map a judge choice (1 or 2) back to an index into ``Task.answers``."""
        if choice not in (1, 2):
            raise ValueError(f"choice must be 1 or 2, got {choice}")
        return self.choice_order[choice - 1]

    def speaker_for_choice(self, choice: int) -> Speaker:
        answer_index = self.answer_index_for_choice(choice)
        return Speaker.ALICE if answer_index == self.alice_answer else Speaker.BOB

    def to_dict(self) -> dict[str, Any]:
        return {
            "alice_answer": self.alice_answer,
            "bob_answer": self.bob_answer,
            "choice_order": list(self.choice_order),
            "seed_material": self.seed_material,
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
    return Seating(
        alice_answer=alice_answer,
        bob_answer=1 - alice_answer,
        choice_order=(first_choice, 1 - first_choice),
        seed_material=seed_material,
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

    def to_dict(self) -> dict[str, Any]:
        return {"turns": [t.to_dict() for t in self.all_turns()]}


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
    neutralised = _STRUCTURAL_TAG_RE.sub(
        lambda m: m.group(0).replace("<", "<\\", 1), argument
    )
    return neutralised.replace("\n", "\n    ")


_STRUCTURAL_TAG_RE = re.compile(
    r"</?\s*(transcript|constitution|question|your_answer|opponent_answer)\s*>",
    re.IGNORECASE,
)


@dataclass
class Verdict:
    """The judge's decision, and enough context to re-derive it."""

    choice: int  # 1 or 2, as presented to the judge
    answer_index: int  # resolved index into Task.answers
    parse_mode: str
    raw: str
    call_id: str
    finish_reason: str | None
    correct: bool | None  # None when the task has no gold answer
    # Recorded so the audit knows whether the judge's request should match the
    # re-derived prompt exactly or carry a repair suffix.
    repair_attempts: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DebateResult:
    run_id: str
    task: Task
    seating: Seating
    transcript: Transcript
    verdict: Verdict

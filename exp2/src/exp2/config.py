"""Configuration schema and loader.

This module holds no default *values* — those live in ``configs/default.toml`` so the
settings that determine a decision are data rather than code.

``DebateConfig`` and ``ClientConfig`` are kept apart deliberately.  Everything in
``DebateConfig`` can change the decision and is persisted to ``config.json`` as part of
the public record; everything in ``ClientConfig`` is operational and is recorded in
``run.json`` instead.  Merging them would mean two runs that produced identical
decisions looked different because a timeout was tuned.

Ported from exp1, with the profile system removed.  exp1 carried three task profiles
(paper / opinion / constitutional) because it ran over both verifiable and
unverifiable domains; exp2 v1 has one framing and one domain, so every profile slot
would hold a constant.  The cost of that decision is that re-adding a constitution
later is a real diff rather than filling a slot.
"""

from __future__ import annotations

import tomllib
from dataclasses import MISSING, dataclass, fields
from pathlib import Path
from typing import Any, Literal

TurnStyle = Literal["simultaneous", "sequential"]

TURN_STYLES: tuple[str, ...] = ("simultaneous", "sequential")
REASONING_EFFORTS: tuple[str, ...] = ("off", "low", "medium", "high")

# Settings that describe how a decision is *contested*, not how it was made. A
# decision run records them because config.json records every field, but it had no
# opinion about them, so a contest must not inherit them — it would pick up a stale
# default and silently run a different protocol. One list, so the inheritance rule and
# the exemption cannot disagree.
RECOURSE_ONLY_KEYS: frozenset[str] = frozenset(
    {
        "recourse_rounds",
        "recourse_judge_model",
        "challenger_model",
        "challenge_word_limit",
        "comprehension_model",
        "challenger_temperature",
    }
)


def _default_config_path() -> Path:
    """Locate ``default.toml``.

    Prefer the repo ``configs/`` copy, which is the one a user edits. Fall back to the
    copy shipped inside the package, so an installed wheel still has defaults.
    """
    repo_copy = Path(__file__).resolve().parents[2] / "configs" / "default.toml"
    if repo_copy.is_file():
        return repo_copy
    return Path(__file__).resolve().parent / "default.toml"


DEFAULT_CONFIG_PATH = _default_config_path()


class ConfigError(ValueError):
    """Raised when a config file is missing keys, or carries unusable values."""


@dataclass(frozen=True)
class DebateConfig:
    """Decision-relevant settings.  Persisted verbatim as ``config.json``."""

    debater_model: str
    judge_model: str

    n_rounds: int
    turn_style: TurnStyle

    # Prompt-only cap: the prompt states it, the turn records the realised
    # word_count, and the CLI warns on overrun. Arguments are never truncated —
    # cutting the text would inject an edit the model did not author.
    word_limit: int

    debater_temperature: float
    judge_temperature: float

    max_tokens: int
    reasoning_effort: str
    judge_cot: bool
    seed: int

    frequency_penalty: float = 0.0
    max_decision_attempts: int = 2

    # The cap for the roles that produce *record text* — debaters, the solo stages, the
    # critic. Separate from ``max_tokens`` (which the judge, challenger, recourse judge
    # and comprehension probe keep) because the two are bounding different risks: those
    # roles emit a short decision line, while a debater's private Thinking block is
    # where the runaway lives. Defaulted rather than required so that a config.json
    # written before this field loads.
    generation_max_tokens: int = 8192

    # Matched to n_rounds, and validated as such. A self_critique run of
    # draft + (critique, revision) * n gives 1 + 2n calls against debate's 2n + 1, so
    # equality here is what makes the two conditions the same number of generations.
    # Set it apart from n_rounds and the "debate only wins because it generates more
    # text" confound comes back silently.
    n_critique_rounds: int = 3

    # Second debater model, for the different-families ablation. None means self-play.
    debater_model_b: str | None = None
    # None means the debater model.
    critic_model: str | None = None

    # --- contest settings -------------------------------------------------------
    # 0, and validated as such: the settled protocol is judge-only recourse. Adding
    # rounds here would assign advocates to a solo decision that never had any, and
    # the contest step has to be the constant across conditions.
    recourse_rounds: int = 0
    # None means the judge model. Only the debate condition uses it; single and
    # self_critique are re-decided in-conversation by the model that decided.
    recourse_judge_model: str | None = None
    # None means the debater model; in practice this is set to the weak model.
    challenger_model: str | None = None
    # None means the run's word_limit. An objection has to quote the record back.
    challenge_word_limit: int | None = None
    # None means the run's reasoning_effort.
    challenger_reasoning_effort: str | None = None
    # The challenger's own sampling temperature. Until 2026-08-25 there was no field:
    # the challenger ran at ``debater_temperature`` by inheritance, so config.json could
    # not show that a measured role was borrowing another role's setting, and WHY had no
    # line for it. Placed among the contest settings, with a default, because the fields
    # above it are required and a defaulted field cannot precede them.
    challenger_temperature: float = 0.7
    # None means the challenger model — the probe asks the challenger about the
    # record it just read, so it must be the same reader.
    comprehension_model: str | None = None
    # Validated True. Without a decline option there is no way to tell a challenger
    # that missed the error from one that found it and argued badly, and the
    # false-alarm rate on sound decisions cannot be estimated at all — which is half
    # of what this experiment measures. It is a field rather than a constant only so
    # that config.json states it.
    challenger_may_decline: bool = True

    def __post_init__(self) -> None:
        if self.turn_style not in TURN_STYLES:
            raise ConfigError(
                f"turn_style must be one of {TURN_STYLES}, got {self.turn_style!r}"
            )
        if self.reasoning_effort not in REASONING_EFFORTS:
            raise ConfigError(
                f"reasoning_effort must be one of {REASONING_EFFORTS}, "
                f"got {self.reasoning_effort!r}"
            )
        if self.n_rounds < 1:
            raise ConfigError(f"n_rounds must be >= 1, got {self.n_rounds}")
        if self.word_limit < 0:
            raise ConfigError(f"word_limit must be >= 0, got {self.word_limit}")
        if not -2.0 <= self.frequency_penalty <= 2.0:
            raise ConfigError(
                f"frequency_penalty must be in [-2, 2], got {self.frequency_penalty}"
            )
        if self.max_decision_attempts < 1:
            raise ConfigError(
                f"max_decision_attempts must be >= 1, got {self.max_decision_attempts}"
            )
        if self.max_tokens < 1:
            raise ConfigError(f"max_tokens must be >= 1, got {self.max_tokens}")
        if self.generation_max_tokens < 1:
            raise ConfigError(
                f"generation_max_tokens must be >= 1, got {self.generation_max_tokens}"
            )
        if self.n_critique_rounds != self.n_rounds:
            raise ConfigError(
                f"n_critique_rounds ({self.n_critique_rounds}) must equal n_rounds "
                f"({self.n_rounds}). They are matched so that self_critique and debate "
                "make the same number of generations; setting them apart reintroduces "
                "the token-count confound the design warns about. Change both, or "
                "state the imbalance deliberately in the experiment spec."
            )
        if self.recourse_rounds != 0:
            raise ConfigError(
                f"recourse_rounds must be 0, got {self.recourse_rounds}. The settled "
                "protocol is judge-only recourse; rounds here would give the debate "
                "condition an exchange the baselines have no counterpart for. "
                "Re-enabling them is the 'contestability debate round' ablation and "
                "needs the recourse debater path, which is not implemented."
            )
        if not self.challenger_may_decline:
            raise ConfigError(
                "challenger_may_decline must be True. Without a decline option "
                "P(revised | initially correct) cannot be estimated, and that is half "
                "the result."
            )
        if self.challenge_word_limit is not None and self.challenge_word_limit < 0:
            raise ConfigError(
                f"challenge_word_limit must be >= 0 or unset, "
                f"got {self.challenge_word_limit}"
            )
        if self.challenger_reasoning_effort is not None and (
            self.challenger_reasoning_effort not in REASONING_EFFORTS
        ):
            raise ConfigError(
                f"challenger_reasoning_effort must be one of {REASONING_EFFORTS} or "
                f"unset, got {self.challenger_reasoning_effort!r}"
            )
        if not 0.0 <= self.challenger_temperature <= 2.0:
            raise ConfigError(
                f"challenger_temperature must be in [0, 2], got "
                f"{self.challenger_temperature}"
            )

    # --- resolvers --------------------------------------------------------------

    def critic_model_for(self) -> str:
        return self.critic_model or self.debater_model

    def challenger_model_for(self) -> str:
        return self.challenger_model or self.debater_model

    def comprehension_model_for(self) -> str:
        return self.comprehension_model or self.challenger_model_for()

    def recourse_judge_model_for(self) -> str:
        return self.recourse_judge_model or self.judge_model

    def challenge_word_limit_for(self) -> int:
        return (
            self.word_limit
            if self.challenge_word_limit is None
            else self.challenge_word_limit
        )

    @property
    def recourse_protocol(self) -> str:
        return "judge_only" if self.recourse_rounds == 0 else "debate"

    def to_dict(self) -> dict[str, Any]:
        return {f.name: getattr(self, f.name) for f in fields(self)}


# One line per decision-relevant field, saying why it is what it is.
#
# The repo's practice rule is that every hyperparameter is shown with a reason before a
# run. Keeping the reasons here rather than retyping them into chat each time means the
# tool satisfies the rule and the reasons cannot drift from the fields. ``--dry-run``
# prints this table beside the resolved values; a test asserts it covers every field.
WHY: dict[str, str] = {
    "debater_model": "strong, per the debate literature: weak debaters give the judge nothing to weigh.",
    "judge_model": "weak, per the debate literature: a strong judge verifies for itself and needs no transcript.",
    "n_rounds": "3 — opening, attack, counter; the smallest number that lets a claim be rebutted and defended.",
    "turn_style": "simultaneous, so neither debater conditions on the other's current-round argument.",
    "word_limit": "400 words per argument; long enough to quote the solution, short enough to keep the record readable.",
    "debater_temperature": "above zero, because two debaters on the same model at 0 would write the same argument.",
    "judge_temperature": "0 — the verdict should not vary between identical readings of one transcript.",
    "max_tokens": "a ceiling, not a spend; must leave room for the private Thinking block. Truncation is fatal and unretryable.",
    "generation_max_tokens": "8192 — the cap for roles that produce record text (debaters, solo stages, critic). It covers every successful generation in the pilot (max 7,888 completion tokens; p99 5,794) and halves a runaway's cost against 16,384; anything lower truncated successful turns, four of them mid-argument.",
    "reasoning_effort": "off, so the private channel is the published Thinking block rather than a provider channel no reader can see.",
    "judge_cot": "on: a decision that states no grounds can be neither read nor contested, and both are the claim under test.",
    "seed": "seeds side assignment and template order per item, so the draws are stable across re-runs.",
    "frequency_penalty": "0 unless a model loops; a nonzero value changes the text and so belongs in the record.",
    "max_decision_attempts": "2 — one retry for a transient failure, without selecting for compliant outputs.",
    "n_critique_rounds": "equal to n_rounds, so self_critique and debate make the same number of generations.",
    "debater_model_b": "unset means self-play; setting it is the different-model-families ablation.",
    "critic_model": "unset means the debater model; a different critic would confound capability with procedure.",
    "recourse_rounds": "0 — judge-only recourse, so the contest step is identical across all three conditions.",
    "recourse_judge_model": "unset means the judge model: debate's recourse is ruled by the same weak judge that decided.",
    "challenger_model": "the weak model — a stakeholder standing in for a human reader, not a second expert.",
    "challenge_word_limit": "unset means the run's word limit; an objection has to quote the record back.",
    "challenger_reasoning_effort": "unset means the run's setting; challenger deliberation is an experimental axis.",
    "challenger_temperature": "0.7 — a generative role like a debater, not a verdict like the judge: at 0 every stakeholder would write the same objection, and variance across objections is part of what is measured.",
    "comprehension_model": "unset means the challenger model — the probe asks the reader about what it just read.",
    "challenger_may_decline": "True, and validated: without it the false-alarm rate on sound decisions cannot be estimated.",
}


# The same rule for the operational table. None of it can change a decision, but the
# repo's practice rule is a reason per hyperparameter and "it cannot change the outcome"
# is not the same as "it does not matter": `max_concurrency` and `max_runs_in_flight`
# decide whether a sweep fits in a day, and `run_timeout_s` is what a cell dies against.
CLIENT_WHY: dict[str, str] = {
    "base_url": "OpenRouter, so one key reaches every provider and the model id is the only thing that changes.",
    "max_concurrency": "requests in flight across the whole fleet; the lever that decides the sweep's wall-clock.",
    "max_attempts": "4 tries for a transport failure — distinct from the one format repair, which is a modelling decision.",
    "backoff_base_s": "1s, doubling: enough to clear a rate-limit burst without idling on a transient 500.",
    "backoff_cap_s": "30s, so one slow provider cannot stall a run past its own timeout.",
    "connect_timeout_s": "15s — a connection that has not opened by then is not going to.",
    "read_timeout_s": "300s: a long generation at a high token cap legitimately takes minutes.",
    "run_timeout_s": "1800s per cell, the bound a whole debate must finish inside; raising concurrency eats into it.",
    "max_runs_in_flight": "open run directories at once; a second bound because it limits file handles rather than requests.",
    "copy_parent": "True — a contest record that does not contain the decision it contests is not self-contained.",
}

GRADING_WHY: dict[str, str] = {
    "grader_model": "Haiku on the batch tier: grading is an offline pass over finished directories, so latency costs nothing and halves the price.",
    "grader_temperature": "0 — a grade is a measurement, and the same objection against the same annotation should not vary.",
    "max_tokens": "4096; a grade is two lines and a short explanation, and it reads an annotation rather than a transcript.",
}


@dataclass(frozen=True)
class ClientConfig:
    """Operational settings.  Cannot change a decision."""

    base_url: str
    max_concurrency: int
    max_attempts: int
    backoff_base_s: float
    backoff_cap_s: float
    connect_timeout_s: float
    read_timeout_s: float
    run_timeout_s: float
    # How many cells the batch harness keeps open at once. A second bound alongside
    # max_concurrency because they limit different things: that one caps requests in
    # flight across the fleet, this one caps open run directories and file handles.
    max_runs_in_flight: int = 4
    # Whether a contest copies its parent run directory wholesale. True keeps each
    # contest record self-contained, which is the project's whole value proposition;
    # False writes a pointer plus a hash instead, for corpora where the parent records
    # are large enough that duplicating them dominates disk.
    copy_parent: bool = True

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ConfigError(f"max_attempts must be >= 1, got {self.max_attempts}")
        if self.max_concurrency < 1:
            raise ConfigError(
                f"max_concurrency must be >= 1, got {self.max_concurrency}"
            )
        if self.max_runs_in_flight < 1:
            raise ConfigError(
                f"max_runs_in_flight must be >= 1, got {self.max_runs_in_flight}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {f.name: getattr(self, f.name) for f in fields(self)}


@dataclass(frozen=True)
class GradingConfig:
    """Settings for the off-path passes: objection grading, and the comprehension probe.

    A third table rather than fields on ``DebateConfig``, because ``config.json``
    promises that everything in it can change the decision — and none of this can.
    These passes run after every decision is final, over completed run directories, and
    are re-runnable without re-spending anything.  Recorded in ``run.json`` instead.
    """

    # Grading is an offline pass over finished directories, so batch latency costs
    # nothing and halves the price.
    grader_model: str = "anthropic/claude-haiku-4.5:batch"
    grader_temperature: float = 0.0
    max_tokens: int = 4096

    def to_dict(self) -> dict[str, Any]:
        return {f.name: getattr(self, f.name) for f in fields(self)}


def _build(cls: type, table: dict[str, Any], table_name: str) -> Any:
    """Construct a config dataclass, reporting missing/unknown keys precisely."""
    unknown = sorted(set(table) - {f.name for f in fields(cls)})
    if unknown:
        raise ConfigError(f"[{table_name}] has unknown keys: {unknown}")
    required = {
        f.name
        for f in fields(cls)
        if f.default is MISSING and f.default_factory is MISSING
    }
    missing = sorted(required - set(table))
    if missing:
        raise ConfigError(f"[{table_name}] is missing keys: {missing}")
    return cls(**table)


def _load_toml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ConfigError(f"config file not found: {path}")
    with path.open("rb") as handle:
        return tomllib.load(handle)


def load_config(
    path: Path | None = None,
    *,
    overrides: dict[str, Any] | None = None,
    inherit: dict[str, Any] | None = None,
) -> tuple[DebateConfig, ClientConfig]:
    """Load config, applying precedence: defaults -> ``inherit`` -> ``path`` ->
    ``overrides``.

    ``overrides`` are flat ``[debate]`` keys, i.e. the CLI's per-field flags. Passing
    ``None`` for an override value is ignored, so callers can forward argparse results
    without filtering.

    ``inherit`` is a recorded run's ``config.json``, and it sits directly above the
    defaults so that a contest continues under the settings the decision was made
    under. Starting from ``default.toml`` instead would let an unrelated change to the
    defaults silently alter an inherited setting, and the contest would then be judged
    under a standard the decision never faced. Defaults still fill any key the recorded
    config predates.
    """
    defaults = _load_toml(DEFAULT_CONFIG_PATH)
    debate_table = dict(defaults.get("debate", {}))
    client_table = dict(defaults.get("client", {}))

    if inherit is not None:
        unknown = sorted(set(inherit) - {f.name for f in fields(DebateConfig)})
        if unknown:
            raise ConfigError(f"inherited config has unknown keys: {unknown}")
        debate_table = {**debate_table, **inherit}

    if path is not None and path.resolve() != DEFAULT_CONFIG_PATH:
        extra = _load_toml(path)
        debate_table = {**debate_table, **extra.get("debate", {})}
        client_table = {**client_table, **extra.get("client", {})}

    for key, value in (overrides or {}).items():
        if value is None:
            continue
        if key not in {f.name for f in fields(DebateConfig)}:
            raise ConfigError(f"unknown debate config override: {key!r}")
        debate_table[key] = value

    return (
        _build(DebateConfig, debate_table, "debate"),
        _build(ClientConfig, client_table, "client"),
    )


def load_grading_config(path: Path | None = None) -> GradingConfig:
    """Read the ``[grading]`` table, defaulting when absent.

    Separate from ``load_config`` rather than a third element of its tuple: every
    caller unpacks two values, and grading is not part of the decision path those
    callers serve.
    """
    table = _load_toml(DEFAULT_CONFIG_PATH).get("grading", {})
    if path is not None:
        table = {**table, **(_load_toml(path).get("grading", {}))}
    return _build(GradingConfig, table, "grading")

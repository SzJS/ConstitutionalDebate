"""Configuration schema and loader.

This module holds no default *values* — those live in ``configs/default.toml``
so the settings that determine a decision are data rather than code.

``DebateConfig`` and ``ClientConfig`` are kept apart deliberately.  Everything in
``DebateConfig`` can change the decision and is persisted to ``config.json`` as
part of the public record; everything in ``ClientConfig`` is operational and is
recorded in ``run.json`` instead.  Merging them would mean two runs that produced
identical decisions looked different because a timeout was tuned.
"""

from __future__ import annotations

import tomllib
from dataclasses import MISSING, dataclass, field, fields
from pathlib import Path
from typing import Any, Literal

TurnStyle = Literal["simultaneous", "sequential"]
ProfileKey = Literal["paper", "opinion", "constitutional"]

# Settings that describe how a decision is *contested*, not how it was made. A
# debate run records them because config.json records every field, but it had no
# opinion about them, so a recourse must not inherit them — it would pick up a
# stale default and silently run a different protocol. For the same reason a
# recourse legitimately differs from its parent on these. One list, so the
# inheritance rule and the exemption cannot disagree.
RECOURSE_ONLY_KEYS: frozenset[str] = frozenset(
    {"recourse_rounds", "challenger_model", "challenge_word_limit"}
)

TURN_STYLES: tuple[str, ...] = ("simultaneous", "sequential")
PROFILE_KEYS: tuple[str, ...] = ("paper", "opinion", "constitutional")
REASONING_EFFORTS: tuple[str, ...] = ("off", "low", "medium", "high")

def _default_config_path() -> Path:
    """Locate ``default.toml``.

    Prefer the repo-root ``configs/`` copy, which is the one a user edits. Fall
    back to the copy shipped inside the package, so an installed wheel (where
    the repo layout does not exist) still has defaults.
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
    word_limit: int
    debater_temperature: float
    judge_temperature: float
    max_tokens: int
    reasoning_effort: str
    judge_cot: bool
    seed: int
    word_limit_by_profile: dict[str, int] = field(default_factory=dict)
    # --- recourse ---------------------------------------------------------- #
    # Defaulted, not required, so ``DebateConfig(**config.json)`` still loads a
    # run recorded before recourse existed.
    #
    # 0 rounds is the judge-only protocol: the recourse judge rules on the
    # challenge alone. The protocol is *named* in run.json rather than left to
    # be inferred from this number.
    recourse_rounds: int = 1
    # None means the debater model. A challenger is a debater by another name,
    # and a capability asymmetry here would confound the grounded/specious arms
    # with a difference in who wrote the challenge.
    challenger_model: str | None = None
    # None means the profile's word limit. A challenge has to quote the record
    # back, which 150 words does not leave much room for.
    challenge_word_limit: int | None = None
    # Whether the challenger may report finding nothing to contest. On by
    # default: without it there is no way to tell a challenger that missed the
    # error from one that found it and argued badly, and the false-alarm rate
    # on sound decisions cannot be estimated at all. Turn it off to reproduce
    # the always-challenge behaviour as a control.
    challenger_may_decline: bool = True
    # None means the run's reasoning_effort. Split out because the challenger's
    # deliberation is an experimental axis — the same weak model with thinking
    # on and off isolates inference-time compute from capability. Note that
    # turning it on gives the challenger a reasoning channel beside its
    # published Thinking:, which the record has to publish too or the whitebox
    # claim stops holding for those runs.
    challenger_reasoning_effort: str | None = None
    # Sampling penalty against verbatim repetition. Default 0.0 — no change to
    # the protocol as published — but it is the fix for a degenerate decoding
    # loop measured on FindTheFlaws: a debater defending the weaker case emitted
    # "I'll write the argument. I'll keep it under 400 words." 126,000 characters
    # in a row, ran past a 32,768-token ceiling and died. Raising max_tokens does
    # not help; it only lets the loop run longer and cost four times as much
    # before failing. This lives in [debate] because it can change a decision.
    frequency_penalty: float = 0.0
    # How many times a whole decision may be attempted. A retry here is a fresh
    # independent run, never a re-attempt of a truncated response — that stays
    # fatal, because a truncated argument entering the published transcript as
    # though authored would be a false statement in the record.
    #
    # It exists because ~25% of FindTheFlaws decisions die to a repetition loop,
    # and the failures are not random: they fall on the debater defending the
    # flawed answer, so dropping them would preferentially discard the hard error
    # cases. It is a mitigation with a cost — it selects against samples that
    # spiral — so the attempt count is recorded and reported rather than hidden.
    max_decision_attempts: int = 2
    # Critique/revision pairs in the self_critique arm. 1 is draft -> critique
    # -> revision; 2 repeats the pair. All steps are published either way.
    n_critique_rounds: int = 1
    # Outcome control: fix the decisive content of every arm's record to the
    # case's FindTheFlaws text instead of seeding a model and hoping it errs.
    # The flaw is then byte-identical across arms rather than merely specified
    # identically, which is what makes a cross-arm detection rate a comparison
    # of the arms rather than of three different flaws.
    #
    # A config field, not a set of new arm names: ``Cell.cell_id`` embeds the
    # arm and ``analysis.by_cell`` groups on it, so new names would fragment
    # both. It belongs in the decision-relevant table because it changes what
    # the decision is *made of*, and so must be visible in the published
    # config.json rather than inferred from a directory name.
    outcome_control: bool = False
    # The second debater model. None is the same-model variant, where both sides
    # get ``debater_model``.
    #
    # The variant exists because with one model the "adversary" shares every
    # blind spot with the side it attacks — exactly like self-critique — so
    # debate vs self-critique would reduce to role assignment versus
    # self-criticism instruction, a much narrower question than it looks.
    # Which side gets which model is drawn per task in ``Seating``.
    debater_model_b: str | None = None

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
        # 0 is not "no words", it is "no cap stated" — see prompts.length_rule.
        # 150 is too tight for multi-step technical argument, so the FindTheFlaws
        # experiment specs override this to 400. Uncapped (0) was tried and
        # rejected on evidence: it removed the only discipline on the private
        # Thinking section and killed ~60% of runs. The value stays available;
        # it is not what those cases run at.
        if self.word_limit < 0:
            raise ConfigError(
                f"word_limit must be >= 1, or 0 for no cap, got {self.word_limit}"
            )
        if not -2.0 <= self.frequency_penalty <= 2.0:
            raise ConfigError(
                f"frequency_penalty must be within [-2, 2], got "
                f"{self.frequency_penalty}"
            )
        if self.n_critique_rounds < 1:
            raise ConfigError(
                f"n_critique_rounds must be >= 1, got {self.n_critique_rounds}"
            )
        if self.max_decision_attempts < 1:
            raise ConfigError(
                f"max_decision_attempts must be >= 1, got "
                f"{self.max_decision_attempts}"
            )
        if self.max_tokens < 1:
            raise ConfigError(f"max_tokens must be >= 1, got {self.max_tokens}")
        if self.recourse_rounds < 0:
            raise ConfigError(
                f"recourse_rounds must be >= 0, got {self.recourse_rounds}"
            )
        if self.challenge_word_limit is not None and self.challenge_word_limit < 0:
            raise ConfigError(
                f"challenge_word_limit must be >= 1, 0 for no cap, or unset; got "
                f"{self.challenge_word_limit}"
            )
        for key, value in self.word_limit_by_profile.items():
            if key not in PROFILE_KEYS:
                raise ConfigError(
                    f"word_limit_by_profile has unknown profile {key!r}; "
                    f"expected one of {PROFILE_KEYS}"
                )
            if not isinstance(value, int) or value < 0:
                raise ConfigError(
                    f"word_limit_by_profile[{key!r}] must be an int >= 1, "
                    f"or 0 for no cap; got {value!r}"
                )

    def word_limit_for(self, profile_key: str) -> int:
        """Word cap for a profile, falling back to the global limit."""
        return self.word_limit_by_profile.get(profile_key, self.word_limit)

    def challenger_model_for(self) -> str:
        """The model that writes a generated challenge."""
        return self.challenger_model or self.debater_model

    def challenge_word_limit_for(self, profile_key: str) -> int:
        """Word cap for a generated challenge."""
        if self.challenge_word_limit is not None:
            return self.challenge_word_limit
        return self.word_limit_for(profile_key)

    @property
    def recourse_protocol(self) -> str:
        """The named protocol this round count selects.

        A reader of the record should never have to infer which of the two
        mechanisms ran from an integer, so the name is written into run.json.
        """
        return "judge_only" if self.recourse_rounds == 0 else "debate"

    def to_dict(self) -> dict[str, Any]:
        return {f.name: getattr(self, f.name) for f in fields(self)}


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
    # How many cells the batch harness keeps open at once. A second bound
    # alongside max_concurrency because they limit different things: that one
    # caps requests in flight across the fleet, this one caps open run
    # directories, file handles and log interleaving.
    max_runs_in_flight: int = 4

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ConfigError(f"max_attempts must be >= 1, got {self.max_attempts}")
        if self.max_concurrency < 1:
            raise ConfigError(
                f"max_concurrency must be >= 1, got {self.max_concurrency}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {f.name: getattr(self, f.name) for f in fields(self)}


@dataclass(frozen=True)
class GradingConfig:
    """Settings for the off-path passes: grading, validation, independence.

    A third table rather than fields on ``DebateConfig``, because ``config.json``
    promises that everything in it can change the decision — and none of this
    can. These passes run after every decision is final, over completed run
    directories, and are re-runnable without re-spending anything. Recorded in
    ``run.json`` instead.
    """

    grader_model: str | None = None  # None means the judge model
    grader_temperature: float = 0.0
    # Grading and validation are offline passes over finished directories, so
    # batch latency costs nothing and halves the price.
    validator_model: str = "anthropic/claude-haiku-4.5:batch"
    validator_temperature: float = 0.0
    max_tokens: int = 4096

    def grader_model_for(self, judge_model: str) -> str:
        return self.grader_model or judge_model

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

    ``overrides`` are flat ``[debate]`` keys, i.e. the CLI's per-field flags.
    Passing ``None`` for an override value is ignored, so callers can forward
    argparse results without filtering.

    ``inherit`` is a recorded run's ``config.json``, and it sits directly above
    the defaults so that a recourse continues under the settings the decision
    was made under. Starting a recourse from ``default.toml`` instead would let
    an unrelated change to the defaults silently alter an inherited setting, and
    the contest would then be judged under a standard the decision never faced.
    Defaults still fill any key the recorded config predates.
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
    existing caller unpacks two values, and grading is not part of the decision
    path those callers serve.
    """
    table = _load_toml(DEFAULT_CONFIG_PATH).get("grading", {})
    if path is not None:
        table = {**table, **(_load_toml(path).get("grading", {}))}
    return _build(GradingConfig, table, "grading")

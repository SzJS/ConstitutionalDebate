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
# recourse legitimately differs from its parent here, and the audit exempts them
# from its "ran under different settings" note. One list, so the two agree.
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
    # run recorded before recourse existed — which is what lets the audit keep
    # verifying every earlier record.
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
        if self.word_limit < 1:
            raise ConfigError(f"word_limit must be >= 1, got {self.word_limit}")
        if self.max_tokens < 1:
            raise ConfigError(f"max_tokens must be >= 1, got {self.max_tokens}")
        if self.recourse_rounds < 0:
            raise ConfigError(
                f"recourse_rounds must be >= 0, got {self.recourse_rounds}"
            )
        if self.challenge_word_limit is not None and self.challenge_word_limit < 1:
            raise ConfigError(
                f"challenge_word_limit must be >= 1 or unset, got "
                f"{self.challenge_word_limit}"
            )
        for key, value in self.word_limit_by_profile.items():
            if key not in PROFILE_KEYS:
                raise ConfigError(
                    f"word_limit_by_profile has unknown profile {key!r}; "
                    f"expected one of {PROFILE_KEYS}"
                )
            if not isinstance(value, int) or value < 1:
                raise ConfigError(
                    f"word_limit_by_profile[{key!r}] must be an int >= 1, "
                    f"got {value!r}"
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
        mechanisms ran from an integer, so the name is written into run.json —
        and the audit checks the name against the count.
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

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ConfigError(f"max_attempts must be >= 1, got {self.max_attempts}")
        if self.max_concurrency < 1:
            raise ConfigError(
                f"max_concurrency must be >= 1, got {self.max_concurrency}"
            )

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

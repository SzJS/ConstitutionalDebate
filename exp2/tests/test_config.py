"""Config loading, and the four validations that encode design decisions.

Three of the validations here (n_critique_rounds, recourse_rounds,
challenger_may_decline) exist to stop a config file quietly running a different
experiment from the one DESIGN.md describes. They are tested by their error messages as
well as by their raising, because the message is the only place the reason is written
down at the point someone hits it.
"""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path

import pytest

from exp2.config import (
    WHY,
    ClientConfig,
    ConfigError,
    DebateConfig,
    load_config,
    load_grading_config,
)


def debate_kwargs(**kw):
    base = dict(
        debater_model="strong/model",
        judge_model="weak/model",
        n_rounds=3,
        turn_style="simultaneous",
        word_limit=400,
        debater_temperature=0.7,
        judge_temperature=0.0,
        max_tokens=8192,
        reasoning_effort="off",
        judge_cot=True,
        seed=0,
        n_critique_rounds=3,
    )
    base.update(kw)
    return base


# --- the defaults load, and say what they are ---------------------------------------


def test_defaults_load_and_are_self_consistent():
    debate, client = load_config()
    assert debate.n_critique_rounds == debate.n_rounds
    assert debate.recourse_rounds == 0
    assert debate.recourse_protocol == "judge_only"
    assert debate.challenger_may_decline is True
    assert client.max_concurrency >= 1
    assert load_grading_config().grader_temperature == 0.0


def test_every_decision_field_has_a_recorded_reason():
    """The repo rule is that every hyperparameter is shown with a reason before a run.

    WHY is where that reason lives, so a field added without one would silently make
    --dry-run incomplete.
    """
    missing = sorted(f.name for f in fields(DebateConfig) if f.name not in WHY)
    assert missing == [], f"fields with no entry in config.WHY: {missing}"
    stale = sorted(set(WHY) - {f.name for f in fields(DebateConfig)})
    assert stale == [], f"WHY entries for fields that no longer exist: {stale}"


# --- resolvers ----------------------------------------------------------------------


def test_unset_models_fall_back_to_the_documented_defaults():
    c = DebateConfig(**debate_kwargs())
    assert c.critic_model_for() == "strong/model"
    assert c.challenger_model_for() == "strong/model"
    assert c.recourse_judge_model_for() == "weak/model"
    # the comprehension probe must be the same reader as the challenger
    assert c.comprehension_model_for() == c.challenger_model_for()
    assert c.challenge_word_limit_for() == 400


def test_an_explicit_challenger_model_also_moves_the_comprehension_probe():
    c = DebateConfig(**debate_kwargs(challenger_model="weak/challenger"))
    assert c.comprehension_model_for() == "weak/challenger"
    # unless it is overridden outright
    c2 = DebateConfig(
        **debate_kwargs(challenger_model="weak/challenger", comprehension_model="other/m")
    )
    assert c2.comprehension_model_for() == "other/m"


# --- the four design-encoding validations -------------------------------------------


def test_critique_rounds_must_match_debate_rounds():
    with pytest.raises(ConfigError) as excinfo:
        DebateConfig(**debate_kwargs(n_rounds=3, n_critique_rounds=1))
    message = str(excinfo.value)
    assert "n_critique_rounds" in message and "n_rounds" in message
    # the message has to say WHY, not just that it refused
    assert "confound" in message


def test_recourse_rounds_must_be_zero():
    with pytest.raises(ConfigError) as excinfo:
        DebateConfig(**debate_kwargs(recourse_rounds=1))
    assert "judge-only" in str(excinfo.value)


def test_the_challenger_must_be_allowed_to_decline():
    with pytest.raises(ConfigError) as excinfo:
        DebateConfig(**debate_kwargs(challenger_may_decline=False))
    assert "initially correct" in str(excinfo.value)


def test_ordinary_range_validations():
    with pytest.raises(ConfigError):
        DebateConfig(**debate_kwargs(turn_style="alternating"))
    with pytest.raises(ConfigError):
        DebateConfig(**debate_kwargs(reasoning_effort="maximum"))
    with pytest.raises(ConfigError):
        DebateConfig(**debate_kwargs(n_rounds=0, n_critique_rounds=0))
    with pytest.raises(ConfigError):
        DebateConfig(**debate_kwargs(word_limit=-1))
    with pytest.raises(ConfigError):
        DebateConfig(**debate_kwargs(max_tokens=0))
    with pytest.raises(ConfigError):
        DebateConfig(**debate_kwargs(frequency_penalty=3.0))
    with pytest.raises(ConfigError):
        DebateConfig(**debate_kwargs(challenger_reasoning_effort="maximum"))


def test_word_limit_zero_is_allowed_and_means_no_cap_stated():
    assert DebateConfig(**debate_kwargs(word_limit=0)).word_limit == 0


# --- the loader reports precisely ---------------------------------------------------


def test_unknown_and_missing_keys_name_themselves(tmp_path: Path):
    spec = tmp_path / "spec.toml"
    spec.write_text('[debate]\nnot_a_key = 1\n', encoding="utf-8")
    with pytest.raises(ConfigError) as excinfo:
        load_config(spec)
    assert "not_a_key" in str(excinfo.value)


def test_an_unknown_override_is_refused_rather_than_ignored():
    with pytest.raises(ConfigError) as excinfo:
        load_config(overrides={"nonesuch": 3})
    assert "nonesuch" in str(excinfo.value)


def test_a_none_override_is_skipped_so_cli_results_can_be_forwarded_unfiltered():
    debate, _ = load_config(overrides={"word_limit": None})
    assert debate.word_limit == 400


def test_precedence_is_defaults_then_inherit_then_path_then_overrides(tmp_path: Path):
    spec = tmp_path / "spec.toml"
    spec.write_text('[debate]\nword_limit = 200\n', encoding="utf-8")
    debate, _ = load_config(
        spec, inherit={"word_limit": 999, "seed": 7}, overrides={"word_limit": 111}
    )
    assert debate.word_limit == 111  # override beats file
    assert debate.seed == 7          # inherit beats defaults where the file is silent

    debate2, _ = load_config(spec, inherit={"word_limit": 999})
    assert debate2.word_limit == 200  # file beats inherit


def test_inherited_config_with_an_unknown_key_is_refused():
    """A recorded config from a future version must fail loudly, not silently drop."""
    with pytest.raises(ConfigError) as excinfo:
        load_config(inherit={"outcome_control": True})
    assert "outcome_control" in str(excinfo.value)


def test_client_config_validations():
    base = dict(
        base_url="https://x/api", max_concurrency=1, max_attempts=1,
        backoff_base_s=1.0, backoff_cap_s=2.0, connect_timeout_s=1.0,
        read_timeout_s=2.0, run_timeout_s=3.0,
    )
    assert ClientConfig(**base).copy_parent is True
    with pytest.raises(ConfigError):
        ClientConfig(**{**base, "max_attempts": 0})
    with pytest.raises(ConfigError):
        ClientConfig(**{**base, "max_concurrency": 0})
    with pytest.raises(ConfigError):
        ClientConfig(**{**base, "max_runs_in_flight": 0})

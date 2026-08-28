"""Config loading, and the four validations that encode design decisions.

Three of the validations here (n_critique_rounds, recourse_rounds,
challenger_may_decline) exist to stop a config file quietly running a different
experiment from the one DESIGN.md describes. They are tested by their error messages as
well as by their raising, because the message is the only place the reason is written
down at the point someone hits it.
"""

from __future__ import annotations

import dataclasses
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


def _two_cases():
    """Two flawed, gradable cases — enough for the estimate's arithmetic to be checked
    by hand against `calls_per_cell`."""
    from exp2.types import Case, FlawAnnotation, Item

    return [
        Case(item=Item(item_id=f"theoremqa-p{i}-flawed", row_id=f"theoremqa:p{i}",
                       subset="theoremqa", problem="p", solution="s", gold_flawed=True),
             flaw=FlawAnnotation(annotation_id=f"a{i}", flaw_location="2",
                                 annotation="Step 2 miscounts.",
                                 annotation_quality="explanation"))
        for i in range(2)
    ]


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


def test_the_operational_and_grading_tables_also_carry_a_reason_each():
    """The rule is the FULL set of values with a reason each. `max_concurrency`,
    `max_runs_in_flight` and `run_timeout_s` cannot change a decision, and they are
    what a sweep dies on."""
    from exp2.config import CLIENT_WHY, GRADING_WHY, ClientConfig, GradingConfig

    for table, why, name in ((ClientConfig, CLIENT_WHY, "CLIENT_WHY"),
                             (GradingConfig, GRADING_WHY, "GRADING_WHY")):
        names = {f.name for f in fields(table)}
        assert sorted(names - set(why)) == [], f"fields with no entry in {name}"
        assert sorted(set(why) - names) == [], f"{name} entries for absent fields"


def test_the_grader_model_is_not_a_batch_tier_id():
    """`:batch` is not a variant of a model; it is a different API.

    `anthropic/claude-haiku-4.5:batch` sat in this default from the day the harness was
    written and no run reached the grade stage until pilot 2, whose five eligible
    contests each came back `HTTP 404: This model is only available through the Batch
    API`. `client.py` speaks chat-completions and nothing else, so any `:batch` id here
    is unsendable by construction — including one arriving through a spec file.
    """
    from exp2.config import DEFAULT_CONFIG_PATH, GradingConfig, load_grading_config

    assert not GradingConfig().grader_model.endswith(":batch")
    assert not load_grading_config().grader_model.endswith(":batch")
    # Anchored on the package's own view of the repo, not on the working directory.
    experiments = DEFAULT_CONFIG_PATH.parent.parent / "experiments"
    for spec in sorted(experiments.glob("*.toml")):
        model = load_grading_config(spec).grader_model
        assert not model.endswith(":batch"), f"{spec} would send {model}"


def test_the_debate_only_judgment_specs_differ_from_their_parents_in_three_places():
    """`judgment-debate{,-pilot}.toml` are `judgment{,-pilot}.toml` with the name, the
    condition list and the challenger changed, and nothing else.

    The paired endpoint is "the same decided debate cells, before recourse and after",
    so anything else that drifted — the recourse form, the recourse judge, the grader,
    the challenger temperature, `decisions_from` — would make the two arms measure
    different mechanisms rather than the same one with and without the audit. The
    challenger is `google/gemini-2.5-flash` and that is a DISCLOSED departure: the
    auditor probe's pre-registered rule picked nobody (`records/pick-auditor/RULES.md`)
    and flash was chosen after the numbers.
    """
    import tomllib

    from exp2.config import DEFAULT_CONFIG_PATH

    experiments = DEFAULT_CONFIG_PATH.parent.parent / "experiments"

    def load(name):
        return tomllib.loads((experiments / name).read_text(encoding="utf-8"))

    for parent_name, child_name in (("judgment-pilot.toml", "judgment-debate-pilot.toml"),
                                    ("judgment.toml", "judgment-debate.toml")):
        parent, child = load(parent_name), load(child_name)
        assert child["conditions"] == ["debate"]
        assert child["debate"]["challenger_model"] == "google/gemini-2.5-flash"
        assert child["debate"]["challenger_variant"] == "judgment"
        assert child["decisions_from"] == parent["decisions_from"]
        # every other key, at both levels, is the parent's verbatim
        # ([debate] is compared separately below, minus the one model that moved)
        changed = {"name", "conditions", "debate"}
        assert {k: v for k, v in child.items() if k not in changed} == {
            k: v for k, v in parent.items() if k not in changed}, child_name
        assert {k: v for k, v in child["debate"].items() if k != "challenger_model"} == {
            k: v for k, v in parent["debate"].items() if k != "challenger_model"}

        # the header has to carry the disclosure and the endpoint, because the spec is
        # what a reader of the tree reaches first
        text = (experiments / child_name).read_text(encoding="utf-8")
        assert "McNEMAR" in text
        assert "NO CANDIDATE CLEARED THEM" in text
        assert "chosen AFTER the numbers" in text
        assert "specious-objection control" in text

        # and the loader has to accept it
        debate, _ = load_config(experiments / child_name)
        assert debate.challenger_model_for() == "google/gemini-2.5-flash"
        assert debate.challenger_variant == "judgment"
        assert debate.recourse_form == "third_party"
        assert debate.recourse_judge_model == "openai/gpt-4.1-nano"
        assert debate.challenger_temperature == 0.7
        # unpinned, as every challenger in every run so far has been
        assert debate.provider_routing_for("google/gemini-2.5-flash") is None
        # and it inherits the run's reasoning setting, which is what the probe verified
        # flash can honour (`outputs/pick-auditor/liveness.json`)
        assert debate.challenger_reasoning_effort is None
        assert debate.reasoning_effort == "off"


# --- provider routing ---------------------------------------------------------------


def test_provider_order_defaults_to_empty_and_routes_nothing():
    """A bare `{}` default on a dataclass field raises at import; this must be a
    factory, and an unpinned config must put no `provider` key on the wire at all."""
    c = DebateConfig(**debate_kwargs())
    assert c.provider_order == {}
    assert c.provider_allow_fallbacks is False
    assert c.provider_routing_for("strong/model") is None


def test_only_the_models_with_an_entry_are_pinned():
    """nano and Haiku have no entry and must be routed exactly as they were. Pinning a
    model that has no measured provider table would be a routing change nothing
    supports."""
    c = DebateConfig(**debate_kwargs(
        provider_order={"deepseek/deepseek-v4-flash-0731": ["gmicloud", "coreweave"]}))
    assert c.provider_routing_for("deepseek/deepseek-v4-flash-0731") == {
        "order": ["gmicloud", "coreweave"], "allow_fallbacks": False,
    }
    assert c.provider_routing_for("openai/gpt-4.1-nano") is None
    assert c.provider_routing_for("anthropic/claude-haiku-4.5") is None


def test_an_empty_or_malformed_provider_order_is_refused():
    """With allow_fallbacks=False an empty list routes nowhere — a 404 on every call
    that no dry-run can catch."""
    with pytest.raises(ConfigError, match="non-empty list"):
        DebateConfig(**debate_kwargs(provider_order={"m": []}))
    with pytest.raises(ConfigError, match="non-empty strings"):
        DebateConfig(**debate_kwargs(provider_order={"m": ["ok", ""]}))


def test_routing_is_decision_relevant_so_a_contest_inherits_it():
    """Routing decides which weights write the text, so it is in DebateConfig — which
    is persisted as config.json and inherited by a contest — and not in ClientConfig,
    which a contest deliberately does not inherit."""
    from exp2.config import RECOURSE_ONLY_KEYS

    names = {f.name for f in fields(DebateConfig)}
    assert {"provider_order", "provider_allow_fallbacks"} <= names
    assert not ({"provider_order", "provider_allow_fallbacks"} & RECOURSE_ONLY_KEYS)
    assert {"provider_order", "provider_allow_fallbacks"} <= set(
        DebateConfig(**debate_kwargs()).to_dict())


def test_a_provider_table_loads_from_a_spec(tmp_path: Path):
    spec = tmp_path / "s.toml"
    spec.write_text(
        '[debate.provider_order]\n'
        '"deepseek/deepseek-v4-flash-0731" = ["gmicloud", "coreweave"]\n',
        encoding="utf-8")
    debate, _ = load_config(spec)
    assert debate.provider_order == {
        "deepseek/deepseek-v4-flash-0731": ["gmicloud", "coreweave"]}
    assert debate.provider_allow_fallbacks is False


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


def test_the_challenger_variant_defaults_to_neutral_and_is_validated():
    """The default is historical for the same reason `recourse_form`'s is: every paid
    run up to and including the first full sweep ran the neutral stakeholder, and a
    default of anything else would silently restate what those specs ran.

    It is validated because the variant decides which standpoint paragraph the
    challenger is written from, and a typo that fell through to neutral would produce a
    tree whose `challenge_arm` column said one thing and whose objections were written
    under another."""
    from exp2.config import CHALLENGER_VARIANTS, RECOURSE_ONLY_KEYS

    assert DebateConfig(**debate_kwargs()).challenger_variant == "neutral"
    # it describes how a decision is CONTESTED, so a contest must not inherit the
    # decision run's value for it
    assert "challenger_variant" in RECOURSE_ONLY_KEYS
    assert CHALLENGER_VARIANTS == ("neutral", "partisan_advocate", "partisan_assigned",
                                   "partisan_auditor", "judgment",
                                   "judgment_specious", "placeholder")
    for variant in CHALLENGER_VARIANTS:
        assert DebateConfig(
            **debate_kwargs(challenger_variant=variant)).challenger_variant == variant
    with pytest.raises(ConfigError) as excinfo:
        DebateConfig(**debate_kwargs(challenger_variant="partisan"))
    assert "challenger_variant must be one of" in str(excinfo.value)


def test_the_config_vocabulary_and_the_prompt_clauses_cannot_drift():
    """Two modules hold the same set — the names, and the paragraphs they select — and
    `prompts` imports `config` rather than the other way round, so nothing structural
    keeps them equal.

    THREE names are deliberately NOT in the clause table, and they are exactly
    `JUDGMENT_FAMILY`. `judgment` is a mode, not a standpoint: it has its own system
    prompt because the challenger's task changes, so a clause selected by name would be
    the wrong shape for it — and the whole point of `challenger_arm_clause` raising on an
    unknown name is that a mode which fell through to a clause would be a judgment run
    wearing a stakeholder's prompt. `judgment_specious` is that mode plus a spliced
    clause, so it has a prompt of its own rather than an entry here, and `placeholder`
    has no prompt at all — it makes no call.
    """
    from exp2.config import CHALLENGER_VARIANTS, JUDGMENT_FAMILY, JUDGMENT_VARIANT
    from exp2.prompts import (
        CHALLENGER_ARMS,
        CHALLENGER_SYSTEM_JUDGMENT,
        CHALLENGER_SYSTEM_JUDGMENT_SPECIOUS,
    )

    assert set(CHALLENGER_ARMS) | set(JUDGMENT_FAMILY) == set(CHALLENGER_VARIANTS)
    assert not set(CHALLENGER_ARMS) & set(JUDGMENT_FAMILY)
    assert JUDGMENT_VARIANT in CHALLENGER_VARIANTS
    assert CHALLENGER_SYSTEM_JUDGMENT  # the prompt that stands in for the missing clause
    assert CHALLENGER_SYSTEM_JUDGMENT_SPECIOUS  # and the control's spliced copy of it


def test_recourse_form_defaults_to_what_every_paid_run_actually_did():
    """The default is historical on purpose: `sweep.toml` and the pilots were written
    before this field existed, and a default of "third_party" would silently restate
    what they ran."""
    from exp2.config import RECOURSE_ONLY_KEYS

    assert DebateConfig(**debate_kwargs()).recourse_form == "per_condition"
    # it describes how a decision is CONTESTED, so a contest must not inherit the
    # decision run's value for it
    assert "recourse_form" in RECOURSE_ONLY_KEYS
    for form in ("per_condition", "third_party", "in_conversation"):
        assert DebateConfig(**debate_kwargs(recourse_form=form)).recourse_form == form
    with pytest.raises(ConfigError) as excinfo:
        DebateConfig(**debate_kwargs(recourse_form="whoever_is_free"))
    assert "recourse_form must be one of" in str(excinfo.value)


def test_the_dry_run_table_prints_the_recourse_form_and_its_reason(capsys):
    """The repo rule is the FULL set of values with a reason each, before the run. A
    field that decides who hears the appeal and does not appear in the table would make
    two different experiments look identical on the terminal."""
    from exp2.experiment_cli import print_hyperparameters

    debate, client = load_config()
    print_hyperparameters(
        DebateConfig(**{**debate.to_dict(), "recourse_form": "third_party"}),
        client, load_grading_config())
    printed = capsys.readouterr().out
    assert "recourse_form" in printed and "third_party" in printed
    assert WHY["recourse_form"][:40] in printed


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


def test_the_estimate_does_not_promise_a_retry_the_harness_does_not_make(capsys):
    """`max_decision_attempts` is loaded and validated, and consulted nowhere.

    The dry-run used to print "retries are on top: max_decision_attempts=2", which a
    reader takes as a promise that a failed cell is attempted twice. It is not: the
    harness makes one attempt per cell per invocation, and the retry is re-running the
    stage, which picks up every cell with no completed record. The wrong line matters
    because it is printed at the one moment a run is being approved.
    """
    from exp2.experiment_cli import print_estimate

    debate, _ = load_config()
    print_estimate([], debate)
    printed = capsys.readouterr().out
    assert "max_decision_attempts" not in printed
    assert "retries are on top" not in printed
    assert "one attempt per cell per invocation" in printed
    assert "re-run the stage" in printed


def test_the_estimate_states_which_cells_a_resume_re_attempts(capsys):
    """The header is read at the one moment a $34 run is being approved.

    "re-run the stage to retry cells with no completed record" was true of the old
    behaviour and is now wrong: a resume skips failed cells as well as completed ones,
    and only `--retry-failed` re-attempts them. A reader who believes the old line would
    expect a resume to re-draw the ~900 cells the sweep loses to truncation.
    """
    from exp2.experiment_cli import print_estimate

    debate, _ = load_config()
    print_estimate([], debate)
    printed = capsys.readouterr().out
    assert "completed or failed is skipped" in printed
    assert "no run" in printed and "left running by a crash" in printed
    assert "--retry-failed" in printed


def test_the_estimate_charges_nothing_for_decisions_it_reads_off_another_tree(capsys):
    """A `decisions_from` spec calls no decider at all, and this is the line the spend
    is approved from. Quoting the cost of deciding the grid there would price a
    re-contest at five times what it spends and name a stage it never runs."""
    from exp2.experiment import build_grid
    from exp2.experiment_cli import print_estimate

    debate, _ = load_config()
    grid = build_grid(_two_cases(), ["single", "self_critique", "debate"])

    print_estimate(grid, debate)
    deciding = capsys.readouterr().out
    assert "decision 30," in deciding          # 2 items x (1 + 7 + 7) calls
    # + contest 12, ruling 6, agreement 6, ruling_agreement 6, grading 6
    assert "=> up to 66" in deciding

    print_estimate(grid, debate, decisions_from=Path("outputs/experiments/sweep"))
    contesting = capsys.readouterr().out
    assert "decision 0 (read from outputs/experiments/sweep)," in contesting
    assert "=> up to 36" in contesting         # the same run, less the 30 decision calls
    # the rest of the estimate is unchanged: the contest stages still run in full
    assert "contest 12" in contesting and "ruling <= 6" in contesting


def test_the_estimate_counts_the_rulings_a_re_rule_will_actually_make(capsys, tmp_path):
    """A re-rule makes no challenge, no comprehension probe and no grade, and it rules
    only the cells whose SOURCE objection contested. On the sweep the counted figure and
    the grid bound differ by a factor of five, and this is the line the spend is approved
    from."""
    from exp2.experiment import build_grid
    from exp2.experiment_cli import print_estimate

    debate, _ = load_config()
    grid = build_grid(_two_cases(), ["single", "self_critique", "debate"])
    print_estimate(grid, debate, decisions_from=Path("outputs/experiments/sweep"),
                   contests_from=Path("outputs/experiments/recontest"),
                   n_source_contests=2)
    out = capsys.readouterr().out
    assert "decision 0 (read from outputs/experiments/sweep)," in out
    assert "contest 0 (objections read from outputs/experiments/recontest)," in out
    assert "ruling <= 2" in out and "ruling_agreement <= 2" in out
    assert "agreement <= 0" in out and "grading <= 0" in out
    assert "=> up to 4" in out
    assert "the ruling term is COUNTED, not bounded: 2 of the 6 cells" in out


def test_retry_failed_is_a_flag_that_defaults_to_off():
    """Off by default is the whole point: the opt-in has to be typed, per run.

    Asserted against the CLI's own parser, so a renamed or dropped flag fails here.
    """
    from exp2.experiment_cli import build_parser

    parser = build_parser()
    assert parser.parse_args(["--spec", "x.toml"]).retry_failed is False
    assert parser.parse_args(["--spec", "x.toml", "--retry-failed"]).retry_failed is True


def test_max_decision_attempts_is_documented_as_unwired():
    """The field is not wired, so its WHY must not read like a live knob.

    If it is ever wired, this test and the WHY line are what have to change first —
    which is the point of asserting the claim rather than leaving it in a comment.
    """
    import exp2

    assert "NOT WIRED" in WHY["max_decision_attempts"]
    src = Path(exp2.__file__).resolve().parent

    def mentions_in_code(path: Path) -> bool:
        # Comments are where the field is *explained*; only code is a use.
        return any(
            "max_decision_attempts" in line and not line.lstrip().startswith("#")
            for line in path.read_text(encoding="utf-8").splitlines()
        )

    users = sorted(path.name for path in src.glob("*.py") if mentions_in_code(path))
    assert users == ["config.py"], (
        "max_decision_attempts is now read outside config.py; wire it properly and "
        "rewrite config.WHY and the dry-run line, which both say it is unwired"
    )


def test_the_two_controls_are_ruled_as_the_judgment_arm_and_named_as_themselves():
    """`arm_for_variant` is deliberately not the identity, and this is where that is
    pinned.

    `Challenge.arm` selects the RULING prompt and the ruling reader. Both controls of
    2026-08-28 exist to be ruled under exactly the prompt the real audit was ruled under
    — a specious objection ruled in a different form would measure the form rather than
    the judge's sycophancy, and a placeholder ruled in a different form would not be a
    second-look control at all. So both map onto `judgment`, and what they ARE is kept in
    `Challenge.specious` / `Challenge.placeholder` and surfaced by `Challenge.variant`.
    """
    from exp2.config import (
        JUDGMENT_FAMILY,
        JUDGMENT_VARIANT,
        NEUTRAL_VARIANT,
        PLACEHOLDER_VARIANT,
        SPECIOUS_VARIANT,
        arm_for_variant,
    )

    assert JUDGMENT_FAMILY == {"judgment", "judgment_specious", "placeholder"}
    assert SPECIOUS_VARIANT == "judgment_specious"
    assert PLACEHOLDER_VARIANT == "placeholder"
    for variant in JUDGMENT_FAMILY:
        assert arm_for_variant(variant) == JUDGMENT_VARIANT
    # everything else is its own arm, unchanged
    for variant in ("neutral", "partisan_advocate", "partisan_assigned",
                    "partisan_auditor"):
        assert arm_for_variant(variant) == variant
    assert arm_for_variant(NEUTRAL_VARIANT) == NEUTRAL_VARIANT


def test_the_why_table_says_what_the_two_controls_are_and_are_not():
    """The dry-run table is the last thing read before the money is spent, and the two
    facts a reader must not miss are stopping rules: the specious arm's validity rate is
    a manipulation check that should be LOW (a high one voids the comparison), and the
    placeholder makes no model call."""
    from exp2.config import WHY

    entry = WHY["challenger_variant"]
    assert "judgment_specious" in entry and "placeholder" in entry
    assert "MANIPULATION CHECK" in entry
    assert "BY CONSTRUCTION" in entry
    assert "void" in entry
    assert "NO model call" in entry
    assert "MATERIALITY" in entry


def test_the_estimate_prices_the_placeholder_arm_as_rulings_and_nothing_else(capsys):
    """The one spec that carries `contests_from` and still runs `contest`, and the line
    its spend is approved from has to say why that is not a contradiction: the objection
    is a constant, not a generation, so the contest term is zero calls rather than zero
    because they were read from somewhere."""
    from exp2.experiment import build_grid
    from exp2.experiment_cli import print_estimate

    debate, _ = load_config()
    debate = dataclasses.replace(debate, challenger_variant="placeholder")
    grid = build_grid(_two_cases(), ["debate"])
    print_estimate(grid, debate, decisions_from=Path("outputs/experiments/sweep"),
                   contests_from=Path("outputs/experiments/judgment-debate"),
                   n_source_contests=2)
    out = capsys.readouterr().out
    assert "the placeholder objection is a fixed text written with NO model call" in out
    assert "ruling <= 2" in out and "ruling_agreement <= 2" in out
    assert "agreement <= 0" in out and "grading <= 0" in out
    assert "=> up to 4" in out
    assert "SECOND-LOOK CONTROL" in out
    assert "no challenger call, no comprehension probe" in out
    assert "keeps its before-state" in out


def test_the_estimate_grades_the_specious_arm_over_the_whole_grid(capsys):
    """The specious objections are graded by the SAME judgment grader — that grade IS the
    manipulation check — so the arm takes the judgment grading term, not the flaw
    grader's much smaller one. Understating it here would understate the spend at the
    moment it is being agreed to."""
    from exp2.experiment import build_grid
    from exp2.experiment_cli import print_estimate

    debate, _ = load_config()
    grid = build_grid(_two_cases(), ["debate"])
    for variant in ("judgment", "judgment_specious"):
        print_estimate(grid, dataclasses.replace(debate,
                                                 challenger_variant=variant))
        out = capsys.readouterr().out
        assert "grading <= 2" in out, variant
        assert "the grading term is the whole grid" in out, variant

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
from dataclasses import MISSING, dataclass, field, fields
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
        "recourse_form",
        "challenger_variant",
        # The M4 gate's model. A decision had no opinion about who would later decide
        # whether an objection to it is heard, so a contest must not inherit one.
        "gatekeeper_model",
    }
)

# Who rules on an objection, per condition.
#
#   per_condition   debate → a third-party recourse judge; single / self_critique → the
#                   decider re-deciding in its own conversation. What every paid run up
#                   to and including the first full sweep did, and therefore the default:
#                   an old spec must keep meaning what it ran.
#   third_party     the recourse judge rules in every condition. DESIGN.md's settled
#                   protocol.
#   in_conversation the decider re-decides in every condition it can — the ablation, and
#                   an error for `debate`, which has no conversation to replay.
RECOURSE_FORMS: tuple[str, ...] = ("per_condition", "third_party", "in_conversation")

# Which standpoint the challenger is written from. The clauses for the first four live
# in ``prompts.CHALLENGER_ARMS`` — this is the vocabulary, kept here because the config
# field is validated against it and ``prompts`` imports ``config`` rather than the other
# way round. A test asserts the two agree.
#
#   neutral            a stakeholder reading the record, not required to find fault.
#                      What every paid run up to and including the first full sweep did,
#                      and therefore the default: an old spec must keep meaning what it
#                      ran. The design's primary measurement.
#   partisan_advocate  \
#   partisan_assigned   >  the planned ablation: the challenger is assigned the answer
#   partisan_auditor   /   the decision went against and argues the decision was
#                          mistaken, and may still report finding no grounds. Three
#                          wordings of the same standpoint, compared on a 207-cell slice
#                          before one of them is run at scale.
#   judgment           the judgment-challenge variant (DESIGN.md, `## Judgment-challenge`).
#                      Not a standpoint paragraph at all, which is why it has no entry in
#                      ``CHALLENGER_ARMS``: the challenger's TASK changes. It audits the
#                      judgment — the judge's reasoning in `debate`, the reviewer's
#                      justification in `single`, the final revision's grounds in
#                      `self_critique` — against the published record for three defect
#                      types (contradiction, misstatement, omission), is forbidden to
#                      argue the object level, and writes a structured defect list. Its
#                      own system prompt, its own `agreement` question and its own
#                      grader; every one of them keyed off this name.
#   judgment_specious  DESIGN.md, `## Challenger variants`: "a specious variant:
#                      instructed to produce a plausible-but-invalid objection (i.e.
#                      deliberately wrong) ... to check whether the judge is simply
#                      sycophantic". The judgment task, its prompt and its parser
#                      unchanged, plus one instruction: allege defects that LOOK like
#                      contradictions, misstatements or omissions of THIS judgment, quote
#                      accurately, and make claims the record does not support — and
#                      always object. The objections carry `arm = "judgment"` so the
#                      materiality ruling prompt and the materiality ruling reader apply
#                      to them exactly as they do to the real audit; what tells the two
#                      apart in the record is `Challenge.specious` and the index's
#                      `challenge_arm = "judgment_specious"`.
#   judgment_fabricated  the SPECIOUS CONTROL THAT IS FALSE BY CONSTRUCTION, added
#                      2026-08-28 after `judgment-debate-3`'s M3 measured 29.2% of its
#                      "specious" objections as REAL (`LLM_NOTES.md` §3y,
#                      `records/experiments/judgment-debate-3/HANDCHECK-M3-specious.md`).
#                      M3 failed as a manipulation for a reason no rewording repairs:
#                      with `omission` struck, the only move left to a challenger told to
#                      be wrong about a compressed judgment — "it softened a party's
#                      position" — is usually TRUE of a compressed judgment. This variant
#                      changes the defect TYPE instead of the instruction: the objection
#                      must rest on a `Judgment says:` quotation THAT DOES NOT EXIST — a
#                      sentence in the judgment's own register that the judgment does not
#                      contain — while the `Record says:` quotation stays real and
#                      verbatim. Its falsity is then decided by CODE, not by a grader:
#                      `prompts.defect_quote_in_judgment` string-matches every judgment
#                      quotation at parse time, so `quote_in_judgment is False` on every
#                      defect IS the manipulation check, and a reader can redo it with a
#                      string comparison. Like the other two controls it carries
#                      `arm = "judgment"` for the materiality ruling; `Challenge.
#                      fabricated` and `challenge_arm = "judgment_fabricated"` tell it
#                      apart. Its raise rate is 1.0 by construction and its GRADED
#                      validity rate is the failure mode rather than a finding — a
#                      fabricated objection that grades valid is one whose quotation was
#                      real after all.
#   placeholder        the SECOND-LOOK control, and the only variant that makes no model
#                      call at all: a fixed, content-free but well-formed judgment-style
#                      objection (one omission defect whose two quotes are the
#                      parenthetical placeholders the judgment prompt itself asks for)
#                      written by the contest stage. It exists to separate "the audit did
#                      it" from "a second look by the same weak judge did it": every cell
#                      that got a real objection gets this one instead, the judge rules on
#                      it under the same materiality prompt, and the difference between
#                      the two after-states is the audit's own effect. Like
#                      `judgment_specious` it carries `arm = "judgment"` for the ruling,
#                      and `Challenge.placeholder` / `challenge_arm = "placeholder"` is
#                      what says it was not written by a challenger. There is nothing to
#                      grade and nothing to read for line-vs-prose agreement — the text is
#                      the same on every cell — so `grade` and `agreement` skip it with an
#                      explicit reason rather than spending a call on a constant.
CHALLENGER_VARIANTS: tuple[str, ...] = (
    "neutral",
    "partisan_advocate",
    "partisan_assigned",
    "partisan_auditor",
    "judgment",
    "judgment_specious",
    "judgment_fabricated",
    "placeholder",
)

# The one variant that is a MODE rather than a clause. Named so that the three call
# sites — challenger prompt, agreement prompt, grader — test against a constant instead
# of a string literal each, and so a reader of any of them can find the other two.
JUDGMENT_VARIANT = "judgment"

# The two controls of 2026-08-28. Named for the same reason JUDGMENT_VARIANT is, and
# with one property that must not be lost in a refactor: neither is ever written to
# `Challenge.arm`. The arm is what selects the RULING prompt and the ruling READER, and
# both controls exist to be ruled under exactly the prompt the real audit was ruled
# under — a specious objection ruled in a different form would measure the form, not the
# sycophancy, and a placeholder ruled in a different form would not be a control at all.
# So `arm_for_variant` maps both onto "judgment" and the record keeps the variant in its
# own field; `Challenge.variant` is what the index writes.
SPECIOUS_VARIANT = "judgment_specious"
# The third control, of 2026-08-28, and the one whose ground truth needs no model at all:
# every `Judgment says:` quotation in it is INVENTED, which `prompts.parse_defects`
# already decides by string comparison at the moment the objection is read. It shares
# `SPECIOUS_VARIANT`'s properties — `arm = "judgment"`, a raise rate of 1.0, never pooled
# — and differs in the one that matters: what makes M3's objections false is an
# instruction the model may or may not follow, and what makes these false is a check the
# harness runs.
FABRICATED_VARIANT = "judgment_fabricated"
PLACEHOLDER_VARIANT = "placeholder"

# The three variants that write a judgment-style defect list and are ruled on
# materiality. Used by the prompt builder, `generate_challenge` (which arm to record and
# whether to parse a defect list) and the tests that pin the mapping.
JUDGMENT_FAMILY: frozenset[str] = frozenset(
    {JUDGMENT_VARIANT, SPECIOUS_VARIANT, FABRICATED_VARIANT, PLACEHOLDER_VARIANT}
)


def arm_for_variant(variant: str) -> str:
    """The arm an objection written under ``variant`` is RULED as.

    The judgment family collapses onto ``judgment`` and everything else is its own arm.
    This is deliberately not the identity: `Challenge.arm` decides which ruling prompt
    the recourse judge is sent and which reader reads the ruling, and the two controls
    are only controls if they are ruled in the same form as the thing they control for.
    What the objection actually IS survives in `Challenge.specious` /
    `Challenge.placeholder` and in `Challenge.variant`, which is the column the index and
    the analysis read.
    """
    return JUDGMENT_VARIANT if variant in JUDGMENT_FAMILY else variant

# The default arm, named for the same reason: it is what every paid run before
# 2026-08-27 wrote, it is `Challenge.arm`'s default, and since 2026-08-28 it is also the
# arm whose objections the recourse judge rules in the OBJECT-LEVEL form. A ruling
# prompt keyed on a string literal would be one refactor away from re-ruling the neutral
# arm under the materiality prompt its objections were never written for.
NEUTRAL_VARIANT = CHALLENGER_VARIANTS[0]


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

    # --- provider routing -------------------------------------------------------
    #
    # In ``DebateConfig`` rather than ``ClientConfig``, and the distinction is the whole
    # reason those two tables exist: routing decides **which weights generate the text**,
    # so it can change a decision, so it belongs in the published record and must be
    # inherited by a contest. A timeout cannot; this can.
    #
    # OpenRouter served `deepseek/deepseek-v4-flash-0731` from 20 providers during pilot
    # 2, and they are not interchangeable. Attributing each format repair to the call
    # that FAILED (166/166 paired; an earlier table charged the provider that served the
    # repair, which was wrong for 40% of them):
    #
    #   provider      original calls   caused a repair   rate
    #   GMICloud                  48                 1   2.1%  [0.4, 10.9]  p < 0.0001
    #   Baidu                    132                20   15.2%
    #   CoreWeave                 20                 4   20.0% [8.1, 41.6]  p = 0.79
    #   DeepInfra                 31                 6   19.4%
    #   Relace                   215                76   35.3%             p = 0.0001
    #   DigitalOcean              85                30   35.3%
    #
    # Keyed by model id: only the models with an entry get a ``provider`` block on the
    # wire, so nano and Haiku are routed exactly as they were. A **bare ``{}`` default
    # would raise at import** — a mutable default on a dataclass field — hence the
    # factory.
    #
    # ``order`` takes OpenRouter provider **slugs**, and `calls.jsonl` records display
    # names. An unrecognised slug is ignored, and with ``allow_fallbacks = False`` that
    # is a 404 on every call which no dry-run can catch. Verify against
    # /api/v1/models/<id>/endpoints and one real pinned call before spending a stage.
    provider_order: dict[str, list[str]] = field(default_factory=dict)
    # False, so the pin is a pin. A silent fallback would put the measurement back where
    # it started — a run whose repair rate is an average over whichever providers
    # happened to be free — and it would do so invisibly, since the served provider is
    # only in the wire log. A momentarily missing endpoint is a 404 reading "No
    # endpoints found for <model>.", which `client.py` treats as retryable (see
    # `NO_ENDPOINTS_MARKERS`); exhausting the attempts fails the cell, and that is the
    # thing being measured. The same 404 is what a WRONG slug returns, so a misconfigured
    # pin dies slowly rather than fast — the guard is the one real pinned call before the
    # run, `records/derivations/sweep-1-provider-check.py`, not the classifier.
    provider_allow_fallbacks: bool = False

    # Second debater model, for the different-families ablation. None means self-play.
    debater_model_b: str | None = None
    # None means the debater model.
    critic_model: str | None = None

    # --- contest settings -------------------------------------------------------
    # 0, and validated as such: the settled protocol is judge-only recourse. Adding
    # rounds here would assign advocates to a solo decision that never had any, and
    # the contest step has to be the constant across conditions.
    recourse_rounds: int = 0
    # None means the judge model. Used by whichever conditions `recourse_form` routes
    # to the judge — every condition under "third_party", debate alone under the
    # historical "per_condition".
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
    # Who rules on an objection; see RECOURSE_FORMS. The default is the historical
    # routing, so a spec written before this field existed still describes what it ran.
    recourse_form: str = "per_condition"
    # None means the challenger model — the probe asks the challenger about the
    # record it just read, so it must be the same reader.
    comprehension_model: str | None = None
    # Validated True. Without a decline option there is no way to tell a challenger
    # that missed the error from one that found it and argued badly, and the
    # false-alarm rate on sound decisions cannot be estimated at all — which is half
    # of what this experiment measures. It is a field rather than a constant only so
    # that config.json states it.
    challenger_may_decline: bool = True
    # The challenger's standpoint; see CHALLENGER_VARIANTS. "neutral" is what every paid
    # run before 2026-08-27 did, so a spec written before this field existed still
    # describes what it ran. A partisan value is the planned ablation and has to be
    # asked for.
    challenger_variant: str = "neutral"
    # WHO DECIDES WHETHER AN OBJECTION IS HEARD AT ALL. None — the default — means there
    # is no gate: every arm before 2026-08-28 counted every ruling, so a spec written
    # before this field existed still describes what it ran, and `--stage gatekeeper`
    # refuses rather than falling back to some other role's model. There is deliberately
    # NO `gatekeeper_model_for()` resolver for that reason: every other model field here
    # inherits from a neighbour when unset, and inheriting this one would silently make
    # the judge, or the debater, the gatekeeper of the appeal against itself.
    #
    # POST HOC. The gate is the M4 ablation added after M1's preliminary numbers were
    # seen (`records/experiments/judgment-debate-3/PREREG.md`'s M4 amendment, written
    # before M4's first paid call), and it changes no ruling: it decides which of M1's
    # existing rulings are counted.
    gatekeeper_model: str | None = None

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
        for model, order in self.provider_order.items():
            if not isinstance(order, (list, tuple)) or not order:
                raise ConfigError(
                    f"provider_order[{model!r}] must be a non-empty list of provider "
                    f"slugs, got {order!r}. An empty list with allow_fallbacks=False "
                    "would route nowhere."
                )
            if not all(isinstance(slug, str) and slug.strip() for slug in order):
                raise ConfigError(
                    f"provider_order[{model!r}] must contain provider slugs as "
                    f"non-empty strings, got {order!r}"
                )
        if self.recourse_form not in RECOURSE_FORMS:
            raise ConfigError(
                f"recourse_form must be one of {RECOURSE_FORMS}, got "
                f"{self.recourse_form!r}"
            )
        if self.challenger_variant not in CHALLENGER_VARIANTS:
            raise ConfigError(
                f"challenger_variant must be one of {CHALLENGER_VARIANTS}, got "
                f"{self.challenger_variant!r}. The variant decides which standpoint "
                "paragraph the challenger is written from, and an unknown name would "
                "silently fall through to whichever clause the prompt module happened "
                "to hold."
            )
        if not 0.0 <= self.challenger_temperature <= 2.0:
            raise ConfigError(
                f"challenger_temperature must be in [0, 2], got "
                f"{self.challenger_temperature}"
            )
        if self.gatekeeper_model is not None and not self.gatekeeper_model.strip():
            raise ConfigError(
                "gatekeeper_model must be a model id or unset, got "
                f"{self.gatekeeper_model!r}. Unset means there is no admissibility gate "
                "and every ruling counts, which is what every arm before 2026-08-28 did; "
                "an empty string would route the gate call nowhere and the stage would "
                "fail cell by cell instead of refusing once."
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

    def provider_routing_for(self, model: str) -> dict[str, Any] | None:
        """The ``provider`` block for this model's request body, or ``None``.

        ``None`` means the key is omitted entirely rather than sent as an empty object:
        a recorded request body is part of the published record and should carry nothing
        the protocol does not mean. It is also what keeps an unpinned model's request
        byte-identical to what it was before pinning existed.
        """
        order = self.provider_order.get(model)
        if not order:
            return None
        return {
            "order": list(order),
            "allow_fallbacks": self.provider_allow_fallbacks,
        }

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
    "max_decision_attempts": "NOT WIRED. Read and validated, never consulted: the harness makes ONE attempt per cell per invocation, and re-running the stage attempts only cells with no run or one left running by a crash — a cell whose latest run FAILED is skipped as attempted unless --retry-failed is passed. The retries that exist are the client's transport attempts and the one format repair.",
    "n_critique_rounds": "equal to n_rounds, so self_critique and debate make the same number of generations.",
    "provider_order": "per-model OpenRouter provider slugs, in preference order. Empty means OpenRouter routes freely, which is what pilot 2 did across 20 providers of one model whose format-repair rates ranged 2.1% (GMICloud, n=48, p<0.0001 against the 25.5% pool) to 35.3% (Relace, n=215). Routing decides which weights write the text, so it lives here and a contest inherits it.",
    "provider_allow_fallbacks": "False, so the pin is a pin: a silent fallback would average the measurement back over whichever providers were free, invisibly. A momentarily missing endpoint returns 404 'No endpoints found for <model>.', which client.py retries so a 13-hour run rides out a blip; exhausting the retries fails the cell, which is the thing being measured. A WRONG slug returns that same 404 and so now dies slowly — verify the slugs with one real pinned call before the run.",
    "debater_model_b": "unset means self-play; setting it is the different-model-families ablation.",
    "critic_model": "unset means the debater model; a different critic would confound capability with procedure.",
    "recourse_rounds": "0 — judge-only recourse, so the contest step is identical across all three conditions.",
    "recourse_judge_model": "unset means the judge model. Under recourse_form=third_party every condition's objection is ruled by it, so it is the one weak party the design trusts to hear an appeal; the residual asymmetry — it also decided the debate condition — is stated in the analysis caveat.",
    "recourse_form": "per_condition by default, which is what every paid run before 2026-08-26 did (debate ruled by a third-party judge, single/self_critique re-decided by the model that decided). The sweep measured the cost: the weak judge overturned 24% of phantom objections and the strong re-decider 0-4%, so most of self_critique's edge was the routing, not the record. third_party makes the recourse judge a weak third party in every condition — nobody adjudicates their own appeal — and is what the re-contest specs set; in_conversation is the opposite-corner ablation and refuses debate, which has no conversation to replay.",
    "challenger_model": "the weak model — a stakeholder standing in for a human reader, not a second expert.",
    "gatekeeper_model": "unset means NO admissibility gate — every ruling counts, as every arm before 2026-08-28 did. Set, it names the model that decides which objections are heard at all (the M4 ablation, POST HOC): same class as the judge and a different family, so the gate cannot import a stronger reader into the decision path — the objection that killed the jd2 chain. It never inherits from another field, because a gate that defaulted to the judge would have the judge decide whether the appeal against its own judgment is heard.",
    "challenge_word_limit": "unset means the run's word limit; an objection has to quote the record back.",
    "challenger_reasoning_effort": "unset means the run's setting; challenger deliberation is an experimental axis.",
    "challenger_temperature": "0.7 — a generative role like a debater, not a verdict like the judge: at 0 every stakeholder would write the same objection, and variance across objections is part of what is measured.",
    "comprehension_model": "unset means the challenger model — the probe asks the reader about what it just read.",
    "challenger_may_decline": "True, and validated: without it the false-alarm rate on sound decisions cannot be estimated.",
    "challenger_variant": "neutral by default, which is what every paid run before 2026-08-27 did: a stakeholder reading the record, not required to find fault. The partisan variants are the planned ablation, run to raise n — the neutral challenger objects on ~8% of cells, so the judge's discrimination rests on tens of cells per condition, while under advocacy every cell yields an objection unless the advocate finds none. Their detection and false-alarm rates are advocacy rates and are not comparable with the neutral run's; the recourse-stage quantities are the same ones at higher n, plus how often an advocate declines when the record supports the decision. \"judgment\" is a different task rather than a different standpoint: the challenger audits the decision's own reasoning against the record for a contradiction, a misstatement or an omission, and is forbidden the object level — so its objections are graded for PROCESS validity against the record, on every contested cell including the ones whose decision was right, and its rates are not comparable with any of the four above. Since 2026-08-28 it also selects the RULING prompt, through the objection's arm rather than through this field: a judgment objection alleges defects in the judgment, and the object-level ruling prompt tells the judge to disregard the decision's reasoning, so that arm is ruled on MATERIALITY instead — is each alleged defect real against the record, and does addressing a real one change what is true of the text. Every other arm's ruling prompt is byte-identical to what it always was, and `ruling_prompt_form` in the index says which ruled. \"judgment_specious\" and \"placeholder\" are the two CONTROLS of 2026-08-28 and neither is a finding on its own. The specious arm is DESIGN.md's sycophancy check: the judgment task and its whole prompt, plus an instruction to allege plausible-but-invalid defects with accurate quotations and to object every time, so its raise rate is 100% BY CONSTRUCTION and its graded validity rate is the MANIPULATION CHECK on the instruction (it should be low; if it is not, the objections were not specious and the sycophancy comparison is void) rather than a measurement of anything. The placeholder arm is the second-look control and makes NO model call: the contest stage writes one fixed, content-free objection wherever the source run raised one, so the difference between the real audit's after-state and this one's is the audit net of 'the same weak judge looked again'. Both are ruled under the MATERIALITY prompt, because a control ruled in a different form measures the form; both therefore record `arm = \"judgment\"` and are told apart by `challenge_arm` in the index. \"judgment_fabricated\" is the THIRD control, added 2026-08-28 because the specious one was not specious enough: 29.2% of `judgment_specious`'s objections were graded VALID, since with omission struck the only allegation left to it — the judgment softened a party's position — is usually TRUE of a judgment that compresses a three-round debate. This arm makes the objection false BY CONSTRUCTION rather than by instruction: every `Judgment says:` quotation must be INVENTED, a sentence in the judgment's register that the judgment does not contain, while the `Record says:` quotation stays verbatim. The manipulation check is therefore CODE and not a grader — `prompts.defect_quote_in_judgment` string-matches every judgment quotation at parse time, the index carries `challenge_fabrication_ok` and `challenge_defects_fabricated_n`, and a reader can redo the whole check with a string comparison. Its raise rate is 1.0 BY CONSTRUCTION and its graded validity rate is the FAILURE MODE, not a finding: a fabricated objection the grader validates is one whose quotation turned out to be real. It is ruled under the MATERIALITY prompt like the other two, for the same reason.",
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
    "grader_model": "The same Haiku model on the normal chat-completions endpoint. The `:batch` suffix this field carried until 2026-08-25 routes to OpenRouter's separate Batch API, which `client.py` does not speak, and it returned HTTP 404 on every call pilot 2 made.",
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

    # Haiku, on the ordinary chat-completions endpoint. It read
    # `anthropic/claude-haiku-4.5:batch` from the day the harness was written — the
    # reasoning being that an offline pass over finished directories does not care
    # about latency and the batch tier is half the price — and that id is reachable
    # ONLY through OpenRouter's `/api/beta/batches` endpoint, which `client.py` does
    # not speak. No run exercised it until pilot 2, whose five eligible contests each
    # came back HTTP 404. If the batch tier is ever wanted it is a client feature, not
    # a model id.
    grader_model: str = "anthropic/claude-haiku-4.5"
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

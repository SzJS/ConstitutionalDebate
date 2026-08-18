"""Command line entry point for contesting a decision.

A separate command rather than a subcommand of ``constitutional-debate``: the
argument sets barely overlap — a recourse takes no ``--task``, ``--seed``,
``--profile`` or ``--rounds``, and takes four flags a debate has no use for —
and folding them together would break the existing flat invocation that every
recorded command line uses.

The environment is still read in exactly one place; see ``cli.read_api_key``.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

from .cli import MISSING_API_KEY, configure_logging, log, read_api_key
from .client import OpenRouterClient
from .config import (
    RECOURSE_ONLY_KEYS,
    TURN_STYLES,
    ClientConfig,
    ConfigError,
    load_config,
)
from .debate import run_recourse
from .persistence import RunRecord, RunWriter, load_run_record
from .prompts import (
    ARMS,
    PROFILES,
    VISIBILITIES,
    RecourseFrame,
    build_challenger_messages,
    build_debater_messages,
    build_judge_messages,
)
from .types import ORDER, Challenge, Transcript, compose_transcript

GENERATED_CHALLENGE_PLACEHOLDER = (
    "[the generated challenge appears here; it does not exist until the "
    "challenge generator has been called]"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="constitutional-recourse",
        description=(
            "Contest a recorded decision. The decision stands unless the "
            "challenge shows it to be mistaken."
        ),
    )
    parser.add_argument(
        "--run", type=Path, required=True, help="the completed run directory to contest"
    )

    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--challenge", type=Path, default=None, help="a challenge document to file"
    )
    source.add_argument(
        "--generate",
        choices=ARMS,
        default=None,
        help="generate the challenge instead, under this arm",
    )
    parser.add_argument(
        "--challenge-visibility",
        choices=VISIBILITIES,
        default="public",
        help="what a generated challenge is shown: the public record (default) "
        "or the full record including the debaters' private reasoning",
    )

    parser.add_argument("--config", type=Path, default=None, help="TOML config file")
    parser.add_argument("--outputs", type=Path, default=Path("outputs"))
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="render prompts and exit without contacting any API",
    )
    parser.add_argument("-v", "--verbose", action="store_true")

    overrides = parser.add_argument_group("config overrides (beat --config)")
    overrides.add_argument("--recourse-rounds", type=int, dest="recourse_rounds")
    overrides.add_argument("--challenger-model")
    overrides.add_argument("--challenge-word-limit", type=int, dest="challenge_word_limit")
    # Inherited from the parent by default, but a recourse round is its own
    # exchange: it is reasonable to contest a simultaneous debate sequentially,
    # so that the debater defending the decision answers the case against it.
    overrides.add_argument("--turn-style", choices=TURN_STYLES)
    overrides.add_argument("--debater-model")
    overrides.add_argument("--judge-model")
    overrides.add_argument("--word-limit", type=int, dest="word_limit")
    overrides.add_argument("--max-tokens", type=int, dest="max_tokens")
    overrides.add_argument("--reasoning-effort", dest="reasoning_effort")
    overrides.add_argument(
        "--judge-cot",
        action=argparse.BooleanOptionalAction,
        default=None,
        dest="judge_cot",
        help="have the recourse judge explain its ruling before giving it "
        "(default: inherited from the run being contested)",
    )
    return parser


# Deliberately no --seed, --rounds or --profile: seating, the round boundary and
# the judging standard are all inherited from the decision being contested.
OVERRIDE_KEYS = (
    "recourse_rounds",
    "challenger_model",
    "challenge_word_limit",
    "turn_style",
    "debater_model",
    "judge_model",
    "word_limit",
    "max_tokens",
    "reasoning_effort",
    "judge_cot",
)


def load_challenge(args: argparse.Namespace) -> Challenge:
    """The challenge, or the specification of the one to generate."""
    if args.generate is not None:
        return Challenge(
            text="",
            origin="generated",
            arm=args.generate,
            visibility=args.challenge_visibility,
        )
    if args.challenge_visibility != "public":
        raise ConfigError(
            "--challenge-visibility only applies to a generated challenge; a "
            "supplied one was written by whoever wrote it"
        )
    text = args.challenge.read_text(encoding="utf-8").strip()
    if not text:
        raise ConfigError(f"the challenge file is empty: {args.challenge}")
    return Challenge(text=text, origin="file", source=str(args.challenge))


def render_all_prompts(
    parent: RunRecord, config, challenge: Challenge
) -> list[tuple[str, str]]:
    """Every prompt this recourse would send, as ``(label, text)`` pairs.

    These are the *real* prompts, unlike the debate dry run's: the parent
    transcript exists, so nothing has to be stood in for — except a challenge
    that has not been generated yet, which is labelled as the placeholder it is.
    """
    profile = PROFILES[parent.profile_key]
    transcript = compose_transcript(parent.transcript, Transcript())
    rendered: list[tuple[str, str]] = []

    if challenge.origin == "generated":
        for message in build_challenger_messages(
            parent.task, parent.context, parent.seating, config,
            parent.challenger_view(),
            arm=challenge.arm,
            visibility=challenge.visibility,
            decision_answer_index=parent.verdict.answer_index,
            decision_grounds=parent.decision_grounds,
            profile=profile,
        ):
            rendered.append(
                (f"challenger [{message['role']}]", message["content"])
            )

    frame = RecourseFrame.from_record(
        challenge_text=challenge.text or GENERATED_CHALLENGE_PLACEHOLDER,
        parent_answer_index=parent.verdict.answer_index,
        decision_grounds=parent.decision_grounds,
        parent_rounds=parent.config.n_rounds,
        n_recourse_rounds=config.recourse_rounds,
    )
    for offset in range(1, config.recourse_rounds + 1):
        round_number = parent.config.n_rounds + offset
        for speaker in ORDER:
            for message in build_debater_messages(
                parent.task, parent.context, parent.seating, config, transcript,
                speaker=speaker, round=round_number, profile=profile, recourse=frame,
            ):
                rendered.append(
                    (
                        f"recourse r{round_number} {speaker} "
                        f"({frame.stance(speaker, parent.seating)}) "
                        f"[{message['role']}]",
                        message["content"],
                    )
                )
    for message in build_judge_messages(
        parent.task, parent.context, parent.seating, config, transcript,
        profile=profile, recourse=frame,
    ):
        rendered.append((f"recourse judge [{message['role']}]", message["content"]))
    return rendered


async def _execute(
    parent: RunRecord,
    challenge: Challenge,
    config,
    client_config: ClientConfig,
    api_key: str,
    writer: RunWriter,
) -> int:
    """Run the recourse, recording the outcome in the manifest either way."""
    async with OpenRouterClient(
        api_key, client_config, sink=writer.record_call
    ) as client:
        try:
            async with asyncio.timeout(client_config.run_timeout_s):
                result = await run_recourse(
                    parent, challenge, config, client, writer=writer
                )
        except asyncio.CancelledError:
            writer.finish(status="interrupted", error="cancelled")
            raise
        except Exception as error:
            writer.finish(status="failed", error=f"{type(error).__name__}: {error}")
            log.error("recourse failed: %s", error)
            return 1

    ruling = result.ruling
    writer.finish(
        status="completed",
        totals={
            "turns": len(result.transcript.turns),
            "word_counts": [t.word_count for t in result.transcript.all_turns()],
        },
    )
    if ruling is None:
        # The challenger reviewed the decision and raised nothing, so there was
        # nothing to rule on. A completed run with no ruling.json is what says
        # "never contested" as against "contested and upheld" — the two are
        # different outcomes and the funnel counts them differently.
        log.info(
            "no challenge was raised; the decision stands uncontested "
            "(answer %d: %s)",
            parent.verdict.answer_index,
            parent.task.answers[parent.verdict.answer_index],
        )
        return 0
    log.info(
        "ruling: %s -> answer %d (%s) | %s%s",
        ruling.ruling,
        ruling.answer_index,
        parent.task.answers[ruling.answer_index],
        "the decision was overturned"
        if ruling.changed_the_decision
        else "the decision stands",
        "" if ruling.correct is None else f" | correct={ruling.correct}",
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    load_dotenv()

    try:
        parent = load_run_record(args.run)
        challenge = load_challenge(args)
        config, client_config = load_config(
            args.config,
            overrides={key: getattr(args, key) for key in OVERRIDE_KEYS},
            # Everything the decision was made under, except the
            # settings that describe how it is contested — the parent had no
            # opinion about those, so inheriting them would carry a stale
            # default forward as though it had been chosen.
            inherit={
                key: value
                for key, value in parent.config.to_dict().items()
                if key not in RECOURSE_ONLY_KEYS
            },
        )
        if config.n_rounds != parent.config.n_rounds:
            raise ConfigError(
                f"a recourse inherits the parent's n_rounds ("
                f"{parent.config.n_rounds}); --config set {config.n_rounds}. "
                f"Recourse rounds continue the parent's numbering, so a "
                f"different count would leave the record ambiguous about where "
                f"the original debate ended."
            )
    except (ConfigError, OSError, KeyError, ValueError) as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        return 2

    writer = RunWriter.create_recourse(
        parent=parent,
        config=config,
        client_config=client_config,
        outputs_root=args.outputs,
        status="dryrun" if args.dry_run else "running",
        # A dry run must not leave a half-formed record behind, and copying the
        # parent is the expensive half of creating one.
        copy_parent=not args.dry_run,
    )
    configure_logging(writer.dir, args.verbose)
    print(writer.dir)

    log.info(
        "contesting %s: profile=%s protocol=%s recourse_rounds=%d models=%s/%s",
        parent.run_id, parent.profile_key, config.recourse_protocol,
        config.recourse_rounds, config.debater_model, config.judge_model,
    )
    log.info(
        "the decision under challenge: choice %d -> answer %d (%s)",
        parent.verdict.choice,
        parent.verdict.answer_index,
        parent.task.answers[parent.verdict.answer_index],
    )
    if challenge.origin == "generated":
        log.info(
            "the challenge will be generated: arm=%s visibility=%s model=%s",
            challenge.arm, challenge.visibility, config.challenger_model_for(),
        )
        if challenge.visibility == "full":
            log.warning(
                "challenge_visibility=full: the generator will be shown the "
                "debaters' private reasoning, so the challenge may put to the "
                "recourse judge something the judge who decided this question "
                "never had. The two decisions are not comparable, and the "
                "record will say so."
            )
    else:
        log.info("the challenge was supplied from %s", challenge.source)

    if args.dry_run:
        rendered = render_all_prompts(parent, config, challenge)
        blocks = [
            f"{'=' * 78}\n=== {label}\n{'=' * 78}\n{text}" for label, text in rendered
        ]
        document = "\n\n".join(blocks) + "\n"
        (writer.dir / "prompts.dryrun.md").write_text(document, encoding="utf-8")
        print("\n" + document)
        writer.finish(status="dryrun")
        return 0

    api_key = read_api_key()
    if not api_key:
        writer.finish(status="failed", error="OPENROUTER_KEY is not set")
        print(MISSING_API_KEY, file=sys.stderr)
        return 2

    try:
        return asyncio.run(
            _execute(parent, challenge, config, client_config, api_key, writer)
        )
    except KeyboardInterrupt:
        writer.finish(status="interrupted", error="KeyboardInterrupt")
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

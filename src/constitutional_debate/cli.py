"""Command line entry point.

Only this module reads the environment; the library takes its API key as an
argument, so nothing deep in the call stack can reach for a global.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from .client import OpenRouterClient
from .config import PROFILE_KEYS, TURN_STYLES, ClientConfig, ConfigError, load_config
from .debate import run_debate
from .persistence import RunWriter
from .prompts import (
    PROFILES,
    build_debater_messages,
    build_judge_messages,
    select_profile,
)
from .types import ORDER, Context, Task, Transcript, make_seating

API_KEY_ENV = "OPENROUTER_KEY"

log = logging.getLogger("constitutional_debate")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="constitutional-debate",
        description="Run one debate over a binary question and record it.",
    )
    parser.add_argument("--task", type=Path, required=True, help="task JSON file")
    parser.add_argument(
        "--constitution",
        type=Path,
        default=None,
        help="optional constitution; supplying one selects the CONSTITUTIONAL profile",
    )
    parser.add_argument("--config", type=Path, default=None, help="TOML config file")
    parser.add_argument(
        "--profile",
        choices=PROFILE_KEYS,
        default=None,
        help="override automatic profile selection",
    )
    parser.add_argument("--outputs", type=Path, default=Path("outputs"))
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="render prompts and exit without contacting any API",
    )
    parser.add_argument("-v", "--verbose", action="store_true")

    overrides = parser.add_argument_group("config overrides (beat --config)")
    overrides.add_argument("--debater-model")
    overrides.add_argument("--judge-model")
    overrides.add_argument("--rounds", type=int, dest="n_rounds")
    overrides.add_argument("--turn-style", choices=TURN_STYLES)
    overrides.add_argument("--word-limit", type=int, dest="word_limit")
    overrides.add_argument("--max-tokens", type=int, dest="max_tokens")
    overrides.add_argument("--reasoning-effort", dest="reasoning_effort")
    overrides.add_argument("--seed", type=int)
    overrides.add_argument(
        "--judge-cot", action="store_true", default=None, dest="judge_cot"
    )
    return parser


OVERRIDE_KEYS = (
    "debater_model",
    "judge_model",
    "n_rounds",
    "turn_style",
    "word_limit",
    "max_tokens",
    "reasoning_effort",
    "seed",
    "judge_cot",
)


def load_context(path: Path | None) -> Context | None:
    if path is None:
        return None
    return Context(
        kind="constitution",
        text=path.read_text(encoding="utf-8").strip(),
        source=str(path),
    )


def render_all_prompts(task, context, seating, config, profile) -> list[tuple[str, str]]:
    """Every prompt this configuration would send, as ``(label, text)`` pairs.

    Rounds after the first are rendered against an empty transcript, since no
    generations exist yet; they are here so the round-specific instruction shifts
    can be read without spending money.
    """
    empty = Transcript()
    rendered: list[tuple[str, str]] = []
    for round_number in range(1, config.n_rounds + 1):
        for speaker in ORDER:
            messages = build_debater_messages(
                task, context, seating, config, empty,
                speaker=speaker, round=round_number, profile=profile,
            )
            for message in messages:
                rendered.append(
                    (
                        f"debater r{round_number} {speaker} [{message['role']}]",
                        message["content"],
                    )
                )
    for message in build_judge_messages(
        task, context, seating, config, empty, profile=profile
    ):
        rendered.append((f"judge [{message['role']}]", message["content"]))
    return rendered


def configure_logging(run_dir: Path, verbose: bool) -> None:
    """Log to stdout *and* to the run directory.

    The project's rules ask for terminal output to be captured under outputs/;
    writing run.log unconditionally means that holds even when someone forgets
    to pipe through tee.
    """
    root = logging.getLogger("constitutional_debate")
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    for handler in root.handlers:
        handler.close()  # otherwise repeated in-process calls leak file handles
    root.handlers.clear()

    formatter = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s")
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(formatter)
    file_handler = logging.FileHandler(run_dir / "run.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    root.addHandler(stream)
    root.addHandler(file_handler)


async def _execute(config, client_config: ClientConfig, task, context, seating,
                   profile, api_key: str, writer: RunWriter) -> int:
    """Run the debate, recording the outcome in the manifest either way."""
    async with OpenRouterClient(
        api_key, client_config, sink=writer.record_call
    ) as client:
        try:
            async with asyncio.timeout(client_config.run_timeout_s):
                result = await run_debate(
                    task, context, config, seating, client,
                    writer=writer, profile=profile,
                )
        except asyncio.CancelledError:
            # Must propagate: swallowing it would let asyncio.Runner complete
            # normally on Ctrl-C, so main()'s KeyboardInterrupt handler would
            # never fire and the manifest would claim the run merely failed.
            writer.finish(status="interrupted", error="cancelled")
            raise
        except Exception as error:
            writer.finish(status="failed", error=f"{type(error).__name__}: {error}")
            log.error("run failed: %s", error)
            return 1

    verdict = result.verdict
    writer.finish(
        status="completed",
        totals={
            "turns": len(result.transcript.turns),
            "word_counts": [t.word_count for t in result.transcript.all_turns()],
        },
    )
    log.info(
        "verdict: choice %d -> answer %d (%s)%s",
        verdict.choice,
        verdict.answer_index,
        task.answers[verdict.answer_index],
        "" if verdict.correct is None else f" | correct={verdict.correct}",
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    load_dotenv()

    try:
        config, client_config = load_config(
            args.config,
            overrides={key: getattr(args, key) for key in OVERRIDE_KEYS},
        )
        task = Task.from_json(args.task)
        context = load_context(args.constitution)
        profile = (
            PROFILES[args.profile] if args.profile else select_profile(task, context)
        )
        if profile.key == "constitutional" and context is None:
            raise ConfigError(
                "--profile constitutional requires --constitution; otherwise the "
                "prompts would name a constitution that is not supplied"
            )
        if context is not None and profile.key != "constitutional":
            raise ConfigError(
                f"--constitution was given but --profile {profile.key} does not "
                f"judge under a constitution; drop one of the two"
            )
    except (ConfigError, OSError, KeyError, ValueError) as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        return 2

    seating = make_seating(task, config.seed)

    writer = RunWriter.create(
        task=task,
        context=context,
        config=config,
        client_config=client_config,
        seating=seating,
        profile_key=profile.key,
        outputs_root=args.outputs,
        status="dryrun" if args.dry_run else "running",
    )
    configure_logging(writer.dir, args.verbose)
    print(writer.dir)

    log.info(
        "profile=%s turn_style=%s rounds=%d word_limit=%d models=%s/%s",
        profile.key, config.turn_style, config.n_rounds,
        config.word_limit_for(profile.key),
        config.debater_model, config.judge_model,
    )
    log.info(
        "seating: Alice defends answer %d, Bob defends %d; judge choice order %s",
        seating.alice_answer, seating.bob_answer, seating.choice_order,
    )

    if args.dry_run:
        rendered = render_all_prompts(task, context, seating, config, profile)
        blocks = [
            f"{'=' * 78}\n=== {label}\n{'=' * 78}\n{text}" for label, text in rendered
        ]
        document = "\n\n".join(blocks) + "\n"
        (writer.dir / "prompts.dryrun.md").write_text(document, encoding="utf-8")
        print("\n" + document)
        writer.finish(status="dryrun")
        return 0

    api_key = os.environ.get(API_KEY_ENV)
    if not api_key:
        writer.finish(status="failed", error=f"{API_KEY_ENV} is not set")
        print(
            f"{API_KEY_ENV} is not set. Put it in .env or the environment "
            f"(note: the name is {API_KEY_ENV}, not OPENROUTER_API_KEY).",
            file=sys.stderr,
        )
        return 2

    try:
        return asyncio.run(
            _execute(config, client_config, task, context, seating, profile,
                     api_key, writer)
        )
    except KeyboardInterrupt:
        # BaseException, so _execute's handler never sees it; without this the
        # manifest would be left claiming the run is still in progress.
        writer.finish(status="interrupted", error="KeyboardInterrupt")
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

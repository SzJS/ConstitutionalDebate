"""``exp2`` — run one item, for hand inspection.

    uv run exp2 --case data/cases/ftf-theoremqa/<id>.json --condition debate --dry-run

The dry run renders the **real** prompts every role would be sent and prints them, so
they can be read before any money is spent. That is the check a test cannot do: a prompt
can be well-formed, parse correctly, and still ask the wrong question.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path

from .arms import CONDITIONS, DECIDERS
from .client import OpenRouterClient
from .config import load_config
from .experiment_cli import print_hyperparameters, read_api_key
from .persistence import RunWriter, load_run_record
from .prompts import (
    build_challenger_messages,
    build_debater_messages,
    build_judge_messages,
    build_solo_opening,
)
from .recourse import run_recourse
from .types import Case, DecisionRecord, Speaker, Transcript, make_sides

log = logging.getLogger(__name__)


def render_prompts(case: Case, condition: str, config) -> str:
    item = case.item
    sides = make_sides(item, config.seed)
    blocks: list[str] = [f"# Prompts for {item.item_id} ({condition})\n"]

    def add(title: str, messages) -> None:
        blocks.append(f"\n## {title}\n")
        for message in messages:
            blocks.append(f"\n### {message['role']}\n\n```\n{message['content']}\n```\n")

    if condition == "debate":
        add("Debater — Alice, round 1",
            build_debater_messages(item, sides, config, Transcript(),
                                   speaker=Speaker.ALICE, round_number=1))
        add("Judge", build_judge_messages(item, sides, config, Transcript()))
        record = DecisionRecord.for_debate(Transcript())
    else:
        stage = "answer" if condition == "single" else "draft"
        add(f"Solo — {stage}", build_solo_opening(item, sides, config, stage=stage))
        record = DecisionRecord.for_solo_body("[the reviewer's published reasoning]")

    add("Challenger", build_challenger_messages(
        item, config, record, sides=sides, decision_verdict="FLAWED",
        decision_grounds="[the grounds the decision gave]"))
    return "".join(blocks)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--condition", default="debate", choices=list(CONDITIONS))
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--outputs", type=Path, default=Path("outputs/single"))
    parser.add_argument("--contest", action="store_true",
                        help="also generate an objection and rule on it")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")

    case = Case.from_json(args.case)
    config, client_config = load_config(args.config)
    print_hyperparameters(config)

    if args.dry_run:
        document = render_prompts(case, args.condition, config)
        args.outputs.mkdir(parents=True, exist_ok=True)
        path = args.outputs / f"prompts.{case.item.item_id}.{args.condition}.md"
        path.write_text(document, encoding="utf-8")
        print(f"\ndry run — nothing was sent. Prompts written to {path}")
        return 0

    api_key = read_api_key()

    async def go() -> int:
        sides = make_sides(case.item, config.seed)
        writer = RunWriter.create(
            root=args.outputs / "runs", item=case.item, sides=sides, config=config,
            client_config=client_config, condition=args.condition, flaw=case.flaw)
        async with OpenRouterClient(api_key, client_config,
                                    sink=writer.record_call) as client:
            result = await DECIDERS[args.condition](
                case.item, config, sides, client, writer=writer)
            writer.finish("completed")
            print(f"\nverdict: {result.verdict.verdict} "
                  f"(correct={result.verdict.correct})")
            print(f"record: {writer.dir / 'transcript.md'}")

            if args.contest:
                record = load_run_record(writer.dir)
                contest_writer = RunWriter.create_recourse(
                    root=args.outputs / "contests", parent_dir=writer.dir,
                    item=record.item, sides=record.sides, config=config,
                    client_config=client_config, condition=args.condition)
                async with OpenRouterClient(api_key, client_config,
                                            sink=contest_writer.record_call) as c2:
                    outcome = await run_recourse(record, config, c2,
                                                 writer=contest_writer)
                contest_writer.finish("completed")
                print(f"objection raised: {outcome.challenge.raised}")
                if outcome.ruling:
                    print(f"ruling: {outcome.ruling.ruling or outcome.ruling.form} "
                          f"-> {outcome.ruling.verdict} "
                          f"(changed={outcome.ruling.changed_the_decision})")
                print(f"contest record: {contest_writer.dir / 'transcript.md'}")
        return 0

    return asyncio.run(go())


if __name__ == "__main__":
    raise SystemExit(main())

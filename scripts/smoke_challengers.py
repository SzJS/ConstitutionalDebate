#!/usr/bin/env python
"""Pin the challenger roster empirically, before spending anything on a sweep.

    uv run python scripts/smoke_challengers.py --cases 3 2>&1 | tee outputs/smoke.log

The binding constraint on a weak challenger is not capability, it is **format
compliance**. A model that cannot reliably emit ``Thinking:`` / ``Argument:`` /
``Challenge: YES|NO`` fails parsing, burns its one repair attempt and kills the
run — and in the final data that is indistinguishable from "the challenger
detected nothing". A whole cell of the experiment would then be format failure
wearing the costume of a null result.

So: run each candidate over a handful of real decided debates, and report parse
rate, decline rate and cost. Drop anything that cannot hold the format; pin the
roster from the table rather than from priors.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from constitutional_debate.accounting import usage_from_record
from constitutional_debate.cli import read_api_key
from constitutional_debate.client import OpenRouterClient
from constitutional_debate.config import DebateConfig, load_config
from constitutional_debate.debate import _generate_challenge, run_debate
from constitutional_debate.engine import DebateFailure, TruncatedOutputError
from constitutional_debate.persistence import RunWriter, load_run_record
from constitutional_debate.prompts import PROFILES
from constitutional_debate.types import Challenge, load_cases, make_seating

# ``qwen3-4b`` does not exist on OpenRouter; the ladder starts at 8b. Exactly the
# kind of thing this script exists to establish rather than assume.
CANDIDATES: list[tuple[str, str, str | None]] = [
    # (label, model, challenger_reasoning_effort)
    ("qwen3-8b", "qwen/qwen3-8b", None),
    ("qwen3-14b", "qwen/qwen3-14b", None),
    ("qwen3-32b", "qwen/qwen3-32b", None),
    ("qwen3-32b+think", "qwen/qwen3-32b", "medium"),
    ("gpt-oss-20b", "openai/gpt-oss-20b", None),
]

# No local price table. OpenRouter reports the real charge per call, which
# survives price changes and correctly costs one model id served by several
# providers. A table here also failed silently: unknown models were skipped, so
# adding a candidate quietly under-reported its cost instead of erroring.


@dataclass
class Attempt:
    label: str
    model: str
    task_id: str
    ok: bool
    raised: bool | None
    repairs: int
    words: int
    detail: str
    # Kept so a contradictory result — "Challenge: YES" over a body arguing the
    # decision is sound — can be read rather than guessed at.
    raw: str = ""
    text: str = ""


def cost_of(records: list[dict]) -> float:
    """Sum what these calls actually cost, from the charge OpenRouter reports."""
    return sum(usage_from_record(r).cost_usd for r in records)


async def decide(case, config, client_config, api_key, outputs) -> Path | None:
    """Run one real debate, so the challengers have a real record to read."""
    seating = make_seating(case.task, config.seed)
    writer = RunWriter.create(
        task=case.task, context=None, config=config, client_config=client_config,
        seating=seating, profile_key="paper", outputs_root=outputs, error=case.error,
    )
    async with OpenRouterClient(api_key, client_config, sink=writer.record_call) as c:
        try:
            await run_debate(
                case.task, None, config, seating, c,
                writer=writer, profile=PROFILES["paper"], error=case.error,
            )
        except (DebateFailure, TruncatedOutputError, Exception) as error:
            writer.finish(status="failed", error=str(error))
            print(f"  ! debate failed on {case.task.task_id}: {error}", file=sys.stderr)
            return None
    writer.finish(status="completed")
    return writer.dir


def _last_content(calls: list[dict]) -> str:
    for record in reversed(calls):
        body = record.get("response_body") or {}
        choices = body.get("choices") or [{}]
        content = (choices[0].get("message") or {}).get("content")
        if content:
            return content
    return ""


async def probe(parent, label, model, effort, config, client_config, api_key) -> Attempt:
    """Ask one candidate for one challenge, and see whether it parses."""
    calls: list[dict] = []

    async def sink(record):
        calls.append(record)

    probe_config = DebateConfig(
        **{**config.to_dict(), "challenger_model": model,
           "challenger_reasoning_effort": effort}
    )
    async with OpenRouterClient(api_key, client_config, sink=sink) as client:
        try:
            challenge = await _generate_challenge(
                parent, probe_config, client, parent.transcript,
                challenge=Challenge(text="", origin="generated", arm="stakeholder",
                                    visibility="public"),
                profile=PROFILES["paper"],
            )
        except Exception as error:
            return Attempt(label, model, parent.task.task_id, False, None, 0, 0,
                           f"{type(error).__name__}: {str(error)[:90]}",
                           raw=_last_content(calls))
    return Attempt(
        label, model, parent.task.task_id, True, challenge.raised,
        challenge.repair_attempts, len(challenge.text.split()),
        (challenge.text[:70] or "[declined]").replace("\n", " "),
        raw=challenge.raw, text=challenge.text,
    ), calls


async def main_async(args) -> int:
    api_key = read_api_key()
    config, client_config = load_config(
        overrides={"word_limit": args.word_limit, "seed": 0,
                   "max_tokens": args.max_tokens,
                   "frequency_penalty": args.frequency_penalty}
    )
    cases = load_cases(Path(args.cases_file))[: args.cases]
    outputs = Path(args.outputs)

    print(f"deciding {len(cases)} debates on {config.debater_model} ...")
    dirs = []
    for case in cases:
        d = await decide(case, config, client_config, api_key, outputs)
        if d:
            dirs.append(d)
            print(f"  decided {d.name}")
    if not dirs:
        print("no debates completed; nothing to challenge", file=sys.stderr)
        return 1

    if args.decide_only:
        print(f"\ndecided {len(dirs)}/{len(cases)}; stopping before the probes")
        return 0

    parents = [load_run_record(d) for d in dirs]
    decide_cost = sum(
        cost_of([json.loads(l) for l in (d / "calls.jsonl").read_text().splitlines() if l])
        for d in dirs
    )

    attempts: list[Attempt] = []
    challenge_cost = 0.0
    for label, model, effort in CANDIDATES:
        print(f"probing {label} ({model}, thinking={effort or 'off'}) ...")
        for parent in parents:
            result = await probe(parent, label, model, effort, config,
                                 client_config, api_key)
            if isinstance(result, Attempt):
                attempts.append(result)
                continue
            attempt, calls = result
            attempts.append(attempt)
            challenge_cost += cost_of(calls)

    print()
    print("=" * 88)
    print(f"{'candidate':<18}{'parsed':>8}{'declined':>10}{'repairs':>9}{'words':>8}  sample")
    print("=" * 88)
    for label, model, effort in CANDIDATES:
        mine = [a for a in attempts if a.label == label]
        ok = [a for a in mine if a.ok]
        parse_rate = len(ok) / len(mine) if mine else 0
        declined = sum(1 for a in ok if a.raised is False)
        repairs = sum(a.repairs for a in ok)
        words = round(sum(a.words for a in ok) / len(ok)) if ok else 0
        sample = (ok[0].detail if ok else (mine[0].detail if mine else ""))[:34]
        flag = "" if parse_rate >= 0.9 else "   <-- DROP"
        print(f"{label:<18}{parse_rate:>7.0%}{declined:>9}/{len(ok):<1}{repairs:>8}"
              f"{words:>8}  {sample}{flag}")
    print("=" * 88)
    print(f"spent: ${decide_cost:.4f} deciding + ${challenge_cost:.4f} challenging "
          f"= ${decide_cost + challenge_cost:.4f}")

    failures = [a for a in attempts if not a.ok]
    if failures:
        print("\nfailures:")
        for a in failures:
            print(f"  {a.label:<18} {a.task_id[:34]:<36} {a.detail}")

    Path(args.report).write_text(
        json.dumps([a.__dict__ for a in attempts], indent=2), encoding="utf-8"
    )
    print(f"\nwrote {args.report}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=int, default=3)
    parser.add_argument(
        "--word-limit", type=int, default=0,
        help="0 means no cap stated; a generous cap is what keeps runs alive",
    )
    parser.add_argument("--max-tokens", type=int, default=8192)
    parser.add_argument("--frequency-penalty", type=float, default=0.0)
    parser.add_argument(
        "--decide-only", action="store_true",
        help="stop after the debates; use when tuning the decision settings",
    )
    parser.add_argument("--cases-file", default="data/cases/ftf-python650.jsonl")
    parser.add_argument("--outputs", default="outputs/smoke")
    parser.add_argument("--report", default="outputs/smoke/challengers.json")
    args = parser.parse_args(argv)
    Path(args.outputs).mkdir(parents=True, exist_ok=True)
    load_dotenv()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python
"""Choose a debater model by running the cases that are known to break one.

    uv run python scripts/pick_debater.py 2>&1 | tee outputs/pick-debater.log

``deepseek-v4-flash`` enters a verbatim repetition loop on some FindTheFlaws
Python650 cases — the same case failed at 8k, at 32k, and with a frequency
penalty applied — so the question is whether that is a property of the model or
of the task. This runs a shortlist over the known-pathological cases plus a
control that is known to work, and reports completion rate and real cost.

Selection matters more than it looks: the failures are not random. They fall on
the debater defending the *flawed* answer, so a model that fails 40% of cases
does not cost 40% of the sample at random — it preferentially discards the hard
error cases, which is exactly the population the experiment is about.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from constitutional_debate.accounting import split_calls
from constitutional_debate.cli import read_api_key
from constitutional_debate.client import OpenRouterClient
from constitutional_debate.config import DebateConfig, load_config
from constitutional_debate.debate import run_debate
from constitutional_debate.persistence import RunWriter
from constitutional_debate.prompts import PROFILES
from constitutional_debate.types import load_cases, make_seating

# A controlled A/B, not a shortlist. Both are 284B total / 13B active MoE with
# a 1M context; the only difference is the post-training run. That isolates the
# question actually being asked — a verbatim repetition loop is a post-training
# and decoding artifact, not a capability deficit, so the test is whether a
# re-post-trained revision of the *same* model escapes it.
#
# An earlier shortlist here went the other way, toward cheaper models: a 3B-active
# MoE and a vision-language model. That was wrong. Dropping capability does not
# fix a decoding loop, and it would have given up the "strong debaters" premise
# the protocol depends on to buy nothing.
CANDIDATES: list[str] = [
    "deepseek/deepseek-v4-flash",       # incumbent,  $0.14/$0.28
    "deepseek/deepseek-v4-flash-0731",  # candidate,  $0.08/$0.18
]

# Three that broke the incumbent, and one that did not — a model that avoids the
# loop by refusing every case would otherwise look perfect.
CASE_IDS: list[str] = [
    "ftf-python650-p02255",  # looped at 8k, 32k, and with a penalty
    "ftf-python650-p02256",  # malformed after repair, repeatedly
    "ftf-python650-p02258",  # truncated
    "ftf-python650-p00001",  # control: completed under every setting
]


async def decide(case, model, config, client_config, api_key, outputs):
    cfg = DebateConfig(**{**config.to_dict(), "debater_model": model,
                          "judge_model": model})
    seating = make_seating(case.task, cfg.seed)
    writer = RunWriter.create(
        task=case.task, context=None, config=cfg, client_config=client_config,
        seating=seating, profile_key="paper", outputs_root=outputs,
        error=case.error,
    )
    status, detail = "completed", ""
    try:
        async with OpenRouterClient(api_key, client_config, sink=writer.record_call) as c:
            await run_debate(case.task, None, cfg, seating, c,
                             writer=writer, profile=PROFILES["paper"],
                             error=case.error)
    except Exception as error:  # every failure mode is data here
        status = "failed"
        text = str(error)
        detail = ("loop/truncation" if "length" in text
                  else "malformed" if "malformed" in text
                  else f"{type(error).__name__}")
    writer.finish(status=status, error=detail or None)
    usage, _ = split_calls(writer.dir / "calls.jsonl")
    longest = 0
    for line in (writer.dir / "calls.jsonl").read_text().splitlines():
        u = (json.loads(line).get("usage") or {})
        longest = max(longest, u.get("completion_tokens") or 0)
    return status, detail, usage.cost_usd, longest


async def main_async(args) -> int:
    api_key = read_api_key()
    config, client_config = load_config(
        overrides={"word_limit": args.word_limit, "seed": 0,
                   "max_tokens": args.max_tokens, "n_rounds": args.rounds}
    )
    by_id = {c.task.task_id: c for c in load_cases(Path(args.cases_file))}
    cases = [by_id[i] for i in CASE_IDS if i in by_id]
    if not cases:
        print("none of the named cases were found", file=sys.stderr)
        return 1

    results: dict[str, list] = {}
    for model in CANDIDATES:
        print(f"\n=== {model}")
        results[model] = []
        for case in cases:
            status, detail, cost, longest = await decide(
                case, model, config, client_config, api_key, Path(args.outputs)
            )
            results[model].append((case.task.task_id, status, detail, cost, longest))
            print(f"  {case.task.task_id[-8:]:<10}{status:<10}{detail:<16}"
                  f"longest={longest:>6}tok  ${cost:.4f}")

    print("\n" + "=" * 86)
    print(f"{'model':<40}{'decided':>9}{'longest':>10}{'$/decided':>12}{'$ total':>10}")
    print("=" * 86)
    for model, rows in results.items():
        ok = [r for r in rows if r[1] == "completed"]
        total = sum(r[3] for r in rows)
        per = (sum(r[3] for r in ok) / len(ok)) if ok else float("nan")
        longest = max((r[4] for r in rows), default=0)
        print(f"{model:<40}{len(ok)}/{len(rows):<7}{longest:>10,}"
              f"{per:>12.4f}{total:>10.4f}")
    print("=" * 86)
    grand = sum(r[3] for rows in results.values() for r in rows)
    print(f"spent ${grand:.4f}")

    Path(args.report).write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"wrote {args.report}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases-file", default="data/cases/ftf-python650.jsonl")
    parser.add_argument("--outputs", default="outputs/pick-debater")
    parser.add_argument("--report", default="outputs/pick-debater/results.json")
    parser.add_argument("--word-limit", type=int, default=500)
    parser.add_argument("--max-tokens", type=int, default=8192)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument(
        "--models", default=None,
        help="comma-separated model ids, overriding CANDIDATES",
    )
    args = parser.parse_args(argv)
    if args.models:
        CANDIDATES[:] = [m.strip() for m in args.models.split(",") if m.strip()]
    Path(args.outputs).mkdir(parents=True, exist_ok=True)
    load_dotenv()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())

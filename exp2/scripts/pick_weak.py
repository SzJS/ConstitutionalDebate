#!/usr/bin/env python
"""Choose the weak model, and screen the subsets, from one set of measurements.

    uv run python scripts/pick_weak.py --dry-run
    uv run python scripts/pick_weak.py 2>&1 | tee outputs/pick-weak.log

Three questions, four passes, one table.

**Which weak model?** OpenRouter's API returns `null` for throughput and latency on
every endpoint of every model — those figures are rendered client-side — so the choice
has to be made on measured behaviour. Measuring on our own prompts is the better number
anyway: it is taken at the lengths this experiment actually sends.

An earlier version of this docstring said the `qwen3-8b/14b/32b` variants DESIGN.md
names were no longer served. **That was wrong** (LLM_NOTES §1, correction of
2026-08-25): the raw catalog lists all three, and the first probe's shortlist was picked
on that false premise. This shortlist is the correction — the two models the design
actually names, plus four plain-chat models from recognisable families that have no
thinking mode to leak.

**Which subsets survive?** DESIGN.md restricts the experiment to problems the weak model
cannot reliably solve alone, at subset granularity. A judge that can redo the algebra or
read the program does not need a transcript, so debate has nothing to offer it — exp1
measured exactly this and abandoned its Python650 arm over it.

**Can the candidate do the job at all?** Deciding alone and judging a transcript are
different tasks, and the entire premise of debate is that a weak judge *with* a
transcript beats the same judge *without* one. A model can be poor solo and unable to
follow an argument, or strong solo and transcript-sensitive. Screening on the solo
number alone would select on the wrong axis, so the fixture passes exist:

    pass 1  solo screen      candidate decides alone, per subset   -> the screen
    pass 2  fixture          strong model debates, built once      -> reusable
    pass 3  judge            candidate judges those transcripts    -> uplift
    pass 4  challenger       candidate contests its own verdicts   -> decline rate

Pass 1 against pass 3 on the same items is also the `weak_alone` reference point the
no-weak-alone confound needs (LLM_NOTES §4), bought for about a dollar.

**The rules below are stated before the numbers exist**, so the choice cannot be
retrofitted to whichever candidate happens to look good. Nothing here decides anything:
it prints a table, and the choice plus its evidence goes into the docs by hand.
"""

from __future__ import annotations

import argparse
import asyncio
import functools
import collections
import json
import math
import random
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from exp2.arms import _parse_solo  # noqa: E402
from exp2.client import OpenRouterClient  # noqa: E402
from exp2.config import WHY, DebateConfig, load_config  # noqa: E402
from exp2.datasets import SUBSETS  # noqa: E402
from exp2.debate import run_debate  # noqa: E402
from exp2.engine import _complete_with_repair  # noqa: E402
from exp2.experiment_cli import read_api_key  # noqa: E402
from exp2.prompts import (  # noqa: E402
    build_challenger_messages,
    build_judge_messages,
    build_solo_opening,
    parse_objection_output,
    parse_verdict_output,
)
from exp2.types import DecisionRecord, load_cases, make_sides  # noqa: E402

# Progress must survive a kill. The first run of this script was SIGTERMed by an
# outer timeout and every print() was still sitting in Python's stdout buffer, so the
# log held only the stderr warnings and none of the pass markers or liveness results.
print = functools.partial(print, flush=True)  # noqa: A001

CANDIDATES = [
    "qwen/qwen3-8b",                              # DESIGN.md's ladder start; exp1: 39% error
    "qwen/qwen3-14b",                             # DESIGN.md's "start here"; watch reasoning leak
    "meta-llama/llama-3.1-8b-instruct",           # plain chat, no thinking mode to leak
    "mistralai/mistral-small-3.2-24b-instruct",   # plain chat
    "google/gemma-3-12b-it",                      # plain chat (Gemma 3, not Gemini)
    "openai/gpt-4.1-nano",                        # plain chat
]

# --- the rules, stated in advance ---------------------------------------------------
#
# A subset is DROPPED when the chosen model already solves it: a transcript cannot help
# a judge that does not need one. It is KEPT when there is room for debate to do work.
# The gap between them is a gray zone that escalates to more items rather than being
# decided on a coin flip.
#
# 0.80 / 0.70 rather than some other pair: the strong model measured ~0.94 on this task
# family (exp1 §4). At >=0.80 solo there are <=14 points of headroom for a transcript to
# matter, and the incorrect cell downstream would be starved. At <=0.70 there is a >=24
# point gap to strong and real room. Chance is 0.50, and the probe sample is drawn
# balanced, so these are balanced accuracies even on the lopsided subsets.
DROP_AT = 0.80
KEEP_BELOW = 0.70

# Disqualifiers that do not depend on the screen at all.
MAX_FORMAT_FAILURE = 0.05     # a model that cannot hold the format eats the corpus
MAX_NATIVE_REASONING = 0.05   # "thinking off" must actually be off, or it is not weak
MAX_VERDICT_SKEW = 0.85       # a judge that always says one thing decides nothing
LATENCY_MULTIPLE = 3.0        # vs the fastest survivor; exp1's weak model ran 4x slower

# WITHDRAWN 2026-08-25, post-hoc, by the user, after it disqualified all six candidates
# on the corrected shortlist (and 1 of the first probe's 3). Kept here rather than
# deleted, because a pre-registered rule that was dropped after seeing the numbers is
# part of the record and the write-up has to disclose it.
#
#     MIN_JUDGE_ACCURACY = 0.60   # judge accuracy WITH the transcript
#
# The reasoning, verbatim in LLM_NOTES §1b: contestability is measured *given* a wrong
# decision and does not depend on why the judge was wrong; the verifiable domain stands
# in for non-verifiable ones where accuracy is not even defined; a chance-level judge
# changes the *composition* of the incorrect cell, which is the difficulty confound
# already accepted and already in the caveats. The floor was, in effect, filtering out
# the null result the experiment exists to detect.
#
# Every other disqualifier stands. `judge accuracy with transcript` is still measured
# and still printed in the table — it is reported, not gated.
MIN_JUDGE_ACCURACY = None


# Three fixture debates were built before `parse_debater_output` refused an inline
# "Thinking:" label (LLM_NOTES §3i, fixed 2026-08-25). In each, one round-1 argument
# carried the debater's private reasoning, so every judge and challenger measurement
# taken on them is a measurement on a leaked record — the judge read text the protocol
# says it never sees. The debates are gone from fixture.jsonl (kept as
# fixture.with-leaks.jsonl); their rows are still on disk, because deleting a paid
# measurement is worse than excluding it, and they are excluded here instead. The solo
# screen is unaffected: it never sees a transcript.
LEAKED_FIXTURE_ITEMS = frozenset({
    "law-con5_gpt3-5_A-s8",
    "law-evi4_gpt4_B-s7",
    "theoremqa-solutions-math_algebra_3-png-flawed",
})


def drop_leaked(rows: list[Row]) -> list[Row]:
    """Judge and challenger rows taken on a leaked transcript, removed."""
    return [r for r in rows
            if r.pass_name == "solo" or r.item_id not in LEAKED_FIXTURE_ITEMS]


@dataclass
class Row:
    model: str
    pass_name: str
    subset: str
    item_id: str
    gold_flawed: bool
    verdict: str | None = None
    correct: bool | None = None
    raised: bool | None = None
    failure: str | None = None      # "malformed" | "truncated" | "error"
    repairs: int = 0
    native_reasoning: bool = False
    seconds: float = 0.0
    cost_usd: float = 0.0

    def to_dict(self) -> dict:
        return self.__dict__


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if not n:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / d
    margin = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / d
    return max(0.0, centre - margin), min(1.0, centre + margin)


def classify_failure(error: BaseException) -> str:
    name = type(error).__name__
    if "Truncated" in name:
        return "truncated"
    if "Malformed" in name or "DebateFailure" in name:
        return "malformed"
    return "error"


def sink_to(path: Path):
    """Every generation lands on disk. The repo rule is that no model output may exist
    only in memory, and it is what makes these passes reusable as a weak_alone
    reference instead of being paid for twice."""
    lock = asyncio.Lock()

    async def sink(record: dict) -> None:
        line = json.dumps(record, ensure_ascii=False)

        def append() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")

        async with lock:
            await asyncio.to_thread(append)

    return sink


def rows_path(outputs: Path, model: str, pass_name: str, offset: int = 0) -> Path:
    """One file per (model, pass, offset).

    The offset is in the filename rather than merged into the offset-0 file so that an
    escalation is *additive*: the original 40 items stay exactly as they were measured,
    the extra 40 land beside them, and `pooled_solo_rows` puts the two together. Merging
    in place would make a re-read of the first measurement impossible.
    """
    suffix = f"-offset{offset}" if offset else ""
    return outputs / f"rows-{pass_name}-{model.replace('/', '-')}{suffix}.jsonl"


def _read_rows(path: Path) -> list[Row]:
    return [Row(**json.loads(line)) for line in path.read_text().splitlines() if line.strip()]


def load_rows(outputs: Path, model: str, pass_name: str, offset: int = 0) -> list[Row] | None:
    """A completed pass, if one is on disk. Resume is keyed on the artifact."""
    path = rows_path(outputs, model, pass_name, offset)
    if not path.is_file():
        return None
    return _read_rows(path)


def save_rows(outputs: Path, model: str, pass_name: str, rows: list[Row],
              offset: int = 0) -> None:
    rows_path(outputs, model, pass_name, offset).write_text(
        "\n".join(json.dumps(r.to_dict()) for r in rows) + "\n", encoding="utf-8")


def pooled_solo_rows(outputs: Path, model: str) -> list[Row]:
    """Every solo item ever measured for this model, base draw plus every escalation.

    The gray-zone rule is applied to the *pooled* n, not to the escalation alone: 40
    items plus 40 items is an 80-item estimate with a +/-0.09 interval, whereas reading
    the second 40 on their own would just be a second coin flip. Draws are disjoint by
    construction (`sample_cases` slices a seeded shuffle at `offset`), and item_id is
    deduplicated anyway so that a re-run with an overlapping offset cannot double-count.
    """
    safe = model.replace("/", "-")
    paths = [outputs / f"rows-solo-{safe}.jsonl"]
    paths += sorted(outputs.glob(f"rows-solo-{safe}-offset*.jsonl"))
    rows, seen = [], set()
    for path in paths:
        if not path.is_file():
            continue
        for row in _read_rows(path):
            if row.item_id in seen:
                continue
            seen.add(row.item_id)
            rows.append(row)
    return rows


def models_on_disk(outputs: Path) -> list[str]:
    """Every model with any rows file under `outputs`, as the model id (slashes back)."""
    seen = set()
    for path in outputs.glob("rows-*.jsonl"):
        for pass_name in ("solo", "judge", "challenger"):
            prefix = f"rows-{pass_name}-"
            if path.name.startswith(prefix):
                name = path.name[len(prefix):-len(".jsonl")].split("-offset")[0]
                seen.add(name)
    return sorted(seen)


def all_rows_on_disk(outputs: Path, safe_models: list[str]) -> list[Row]:
    """Every measurement already paid for, reloaded. Used by --report-only, which
    re-derives the tables after a rule changes without sending a single call."""
    rows: list[Row] = []
    for safe in safe_models:
        rows += pooled_solo_rows(outputs, safe)
        for pass_name in ("judge", "challenger"):
            path = outputs / f"rows-{pass_name}-{safe}.jsonl"
            if path.is_file():
                rows += _read_rows(path)
    return rows


def pool_solo(outputs: Path, rows: list[Row]) -> list[Row]:
    """`rows` with each model's solo rows replaced by everything on disk for it."""
    out = [r for r in rows if r.pass_name != "solo"]
    for model in sorted({r.model for r in rows}):
        out += pooled_solo_rows(outputs, model)
    return out


def probe_config(config: DebateConfig, **overrides) -> DebateConfig:
    return DebateConfig(**{**config.to_dict(), **overrides})


def cost_of(completion) -> float:
    try:
        return float((completion.usage or {}).get("cost") or 0.0)
    except Exception:
        return 0.0


# --------------------------------------------------------------------------- #
# pass 0 — liveness
# --------------------------------------------------------------------------- #


async def liveness(models, client_config, api_key: str) -> dict[str, str]:
    """One tiny call per candidate, so a dead endpoint costs a cent, not a stage."""
    async def one(client, model: str) -> tuple[str, str]:
        try:
            await client.complete(
                model=model, messages=[{"role": "user", "content": "Reply OK."}],
                temperature=0.0, max_tokens=8, reasoning_effort="off",
                meta={"role": "probe", "purpose": "liveness"},
            )
            return model, "live"
        except Exception as error:
            return model, f"{type(error).__name__}: {str(error)[:70]}"

    async with OpenRouterClient(api_key, client_config) as client:
        return dict(await asyncio.gather(*(one(client, m) for m in models)))


# --------------------------------------------------------------------------- #
# pass 1 — the solo screen
# --------------------------------------------------------------------------- #


async def solo_screen(model, cases, config, client_config, api_key, outputs) -> list[Row]:
    """The candidate decides each item alone — no debate, no arguments.

    Decided at the **judge's** temperature, not the debater's: the role being simulated
    is a judge deciding without a transcript, and screening at 0.7 would add noise to an
    estimate that already sits near the 50% chance line.
    """
    cfg = probe_config(config, debater_model=model,
                       debater_temperature=config.judge_temperature)
    semaphore = asyncio.Semaphore(client_config.max_concurrency)
    rows: list[Row] = []
    sink = sink_to(outputs / f"calls-{model.replace('/', '-')}.jsonl")

    async with OpenRouterClient(api_key, client_config, sink=sink,
                                semaphore=semaphore) as client:
        async def one(case) -> None:
            started = time.monotonic()
            row = Row(model=model, pass_name="solo", subset=case.item.subset,
                      item_id=case.item.item_id, gold_flawed=case.item.gold_flawed)
            try:
                messages = build_solo_opening(case.item, make_sides(case.item, config.seed),
                                              cfg, stage="answer")
                (_, _, verdict, _), completion, repairs, _, _ = await _complete_with_repair(
                    client, model=model, messages=messages,
                    temperature=cfg.debater_temperature, config=cfg,
                    meta={"role": "solo", "speaker": None, "round": None,
                          "purpose": "screen"},
                    parse=_parse_solo, role="solo", word_limit=cfg.word_limit,
                )
                row.verdict = verdict
                row.correct = verdict == case.item.gold_verdict
                row.repairs = repairs
                row.native_reasoning = bool(completion.reasoning)
                row.cost_usd = cost_of(completion)
            except Exception as error:
                row.failure = classify_failure(error)
            row.seconds = round(time.monotonic() - started, 2)
            rows.append(row)

        await asyncio.gather(*(one(c) for c in cases))
    return rows


# --------------------------------------------------------------------------- #
# pass 2 — the fixture (paid once, reused by every candidate)
# --------------------------------------------------------------------------- #


async def build_fixture(cases, config, client_config, api_key, outputs) -> list[dict]:
    """Debates produced by the strong model, exactly as the sweep would produce them.

    A fixed fixture is faithful rather than approximate: the judge does not interact
    during rounds, so a transcript is complete before any judge sees it. Persisted, so
    the judge and challenger passes cost nothing to repeat and a re-run of this script
    does not re-spend.
    """
    path = outputs / "fixture.jsonl"
    if path.is_file():
        print(f"  using cached fixture {path}")
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

    # Appended as each debate completes, not written at the end: the first run was
    # killed with 47 debates' worth of paid calls in flight and nothing to show for
    # them, because the file was only written after the last one.
    partial = outputs / "fixture.partial.jsonl"
    done = set()
    built: list[dict] = []
    if partial.is_file():
        for line in partial.read_text().splitlines():
            if line.strip():
                entry = json.loads(line)
                built.append(entry)
                done.add(entry["item"]["item_id"])
        print(f"  resuming fixture: {len(done)} debates already built")

    semaphore = asyncio.Semaphore(client_config.max_concurrency)
    sink = sink_to(outputs / "calls-fixture.jsonl")
    lock = asyncio.Lock()
    remaining = [c for c in cases if c.item.item_id not in done]

    async with OpenRouterClient(api_key, client_config, sink=sink,
                                semaphore=semaphore) as client:
        async def one(case) -> None:
            sides = make_sides(case.item, config.seed)
            try:
                result = await run_debate(case.item, config, sides, client)
            except Exception as error:
                print(f"  fixture item {case.item.item_id} failed: "
                      f"{type(error).__name__}: {str(error)[:80]}")
                return
            entry = {"item": case.item.to_dict(), "sides": sides.to_dict(),
                     "transcript": result.transcript.to_dict()}
            async with lock:
                built.append(entry)
                with partial.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(entry) + "\n")

        await asyncio.gather(*(one(c) for c in remaining))

    path.write_text("\n".join(json.dumps(b) for b in built) + "\n", encoding="utf-8")
    print(f"  built {len(built)} debates -> {path}")
    return built


def rehydrate(entry: dict):
    from exp2.types import Item, Sides, Speaker, Transcript, Turn

    item = Item.from_dict(entry["item"])
    sides_data = dict(entry["sides"])
    sides = Sides(**{**sides_data, "verdict_order": tuple(sides_data["verdict_order"])})
    transcript = Transcript([
        Turn(**{**t, "speaker": Speaker(t["speaker"])}) for t in entry["transcript"]["turns"]
    ])
    return item, sides, transcript


# --------------------------------------------------------------------------- #
# passes 3 and 4 — judge, then challenge its own verdict
# --------------------------------------------------------------------------- #


async def judge_and_challenge(model, fixture, config, client_config, api_key,
                              outputs) -> tuple[list[Row], list[Row]]:
    cfg = probe_config(config, judge_model=model, challenger_model=model)
    semaphore = asyncio.Semaphore(client_config.max_concurrency)
    sink = sink_to(outputs / f"calls-{model.replace('/', '-')}.jsonl")
    judge_rows: list[Row] = []
    challenge_rows: list[Row] = []

    async with OpenRouterClient(api_key, client_config, sink=sink,
                                semaphore=semaphore) as client:
        async def one(entry) -> None:
            item, sides, transcript = rehydrate(entry)
            jrow = Row(model=model, pass_name="judge", subset=item.subset,
                       item_id=item.item_id, gold_flawed=item.gold_flawed)
            started = time.monotonic()
            try:
                (verdict, reasoning, _), completion, repairs, _, _ = await _complete_with_repair(
                    client, model=model,
                    messages=build_judge_messages(item, sides, cfg, transcript),
                    temperature=cfg.judge_temperature, config=cfg,
                    meta={"role": "judge", "speaker": None, "round": None,
                          "purpose": "judge"},
                    parse=parse_verdict_output, role="judge", word_limit=cfg.word_limit,
                )
                jrow.verdict = verdict
                jrow.correct = verdict == item.gold_verdict
                jrow.repairs = repairs
                jrow.native_reasoning = bool(completion.reasoning)
                jrow.cost_usd = cost_of(completion)
            except Exception as error:
                jrow.failure = classify_failure(error)
            jrow.seconds = round(time.monotonic() - started, 2)
            judge_rows.append(jrow)

            if jrow.verdict is None:
                return
            # The challenger contests the record this candidate's own judge produced —
            # each candidate is measured in the configuration it would ship in.
            crow = Row(model=model, pass_name="challenger", subset=item.subset,
                       item_id=item.item_id, gold_flawed=item.gold_flawed)
            started = time.monotonic()
            try:
                messages = build_challenger_messages(
                    item, cfg, DecisionRecord.for_debate(transcript), sides=sides,
                    decision_verdict=jrow.verdict, decision_grounds=completion.content,
                )
                # This pass last ran before the stance rewrite of 2026-08-25, when
                # `parse_objection_output` returned five values and the second was a
                # boolean `raised`. It now returns four, and the decision word is one
                # relative token: REVERSE contests, STANDS declines, None is a reply
                # whose direction could not be read and is not a decline.
                (_, word, _, _), c2, repairs, _, _ = await _complete_with_repair(
                    client, model=model, messages=messages,
                    temperature=cfg.debater_temperature, config=cfg,
                    meta={"role": "challenger", "speaker": None, "round": None,
                          "purpose": "challenge"},
                    parse=parse_objection_output, role="challenger",
                    word_limit=cfg.challenge_word_limit_for(),
                )
                crow.raised = word == "REVERSE" if word else None
                crow.repairs = repairs
                crow.native_reasoning = bool(c2.reasoning)
                crow.cost_usd = cost_of(c2)
            except Exception as error:
                crow.failure = classify_failure(error)
            crow.seconds = round(time.monotonic() - started, 2)
            challenge_rows.append(crow)

        await asyncio.gather(*(one(e) for e in fixture))
    return judge_rows, challenge_rows


# --------------------------------------------------------------------------- #
# reporting
# --------------------------------------------------------------------------- #


def accuracy(rows: list[Row]) -> tuple[int, int]:
    """Failures count as NOT solved.

    exp1 measured that model failures are not random — they fell preferentially on the
    debater defending the flawed side. If a failed item simply left the denominator,
    measured accuracy would be inflated on exactly the hard items, and the screen would
    be biased toward *dropping* subsets, i.e. toward discarding the experiment's own
    material. A drop has to be earned by demonstrably solving the subset.
    """
    return sum(1 for r in rows if r.correct), len(rows)


def print_rules() -> None:
    print("\nRules, stated before the numbers exist")
    print("=" * 100)
    print(f"  subset DROP   if the chosen model's balanced solo accuracy >= {DROP_AT:.2f}"
          "   (a transcript cannot help a judge that does not need one)")
    print(f"  subset KEEP   if <= {KEEP_BELOW:.2f}"
          "                                        (room for debate to do work)")
    print(f"  gray zone     ({KEEP_BELOW:.2f}, {DROP_AT:.2f}) -> escalate +40 items, "
          "re-apply; still gray -> KEEP and flag")
    print("  failures count as NOT solved, so a drop must be earned")
    print("\n  candidate disqualifiers, independent of the screen:")
    print(f"    format failure    > {MAX_FORMAT_FAILURE:.0%} in any role")
    print(f"    native reasoning  > {MAX_NATIVE_REASONING:.0%} despite reasoning_effort=off")
    print(f"    verdict skew      > {MAX_VERDICT_SKEW:.0%} one class on a balanced fixture")
    print(f"    p95 latency       > {LATENCY_MULTIPLE:.0f}x the fastest survivor")
    print("    challenger decline rate of exactly 0% or 100%")
    print("  NOT a disqualifier: judge accuracy with the transcript. A 0.60 floor was "
          "pre-registered and")
    print("  WITHDRAWN post-hoc on 2026-08-25 (see the constant's comment and "
          "LLM_NOTES §1b); it is")
    print("  measured and reported below, and gates nothing.")
    print("\n  then: among survivors, choose the model leaving the MOST keep-zone "
          "subsets — the")
    print("  experiment needs problems the model cannot solve. Tiebreaks: transcript "
          "uplift,")
    print("  then cost per decided item, then latency. Subsets are decided only after "
          "the model is,")
    print("  because DESIGN.md defines the restriction relative to the chosen model.")
    print("=" * 100)


def print_report(rows: list[Row], outputs: Path | None = None) -> None:
    """`outputs`, when given, pools every solo draw on disk (base + escalations) so the
    gray-zone rule is applied to the full n rather than to whichever draw ran last."""
    if outputs is not None:
        rows = pool_solo(outputs, rows)
    before = len(rows)
    rows = drop_leaked(rows)
    if before != len(rows):
        print(f"\nexcluded {before - len(rows)} judge/challenger rows measured on the "
              f"{len(LEAKED_FIXTURE_ITEMS)} debates dropped for a Thinking-label leak "
              "(LLM_NOTES §3i)")
    by = collections.defaultdict(list)
    for row in rows:
        by[(row.model, row.pass_name)].append(row)
    models = sorted({r.model for r in rows})

    print(f"\n{'model':32s}{'pass':11s}{'n':>4s}{'acc':>7s}{'95% CI':>15s}"
          f"{'FN':>4s}{'FP':>4s}{'fail':>6s}{'rep':>5s}{'nat':>5s}"
          f"{'p50':>7s}{'p95':>7s}{'$/item':>9s}")
    print("-" * 116)
    for model in models:
        for pass_name in ("solo", "judge", "challenger"):
            group = by.get((model, pass_name))
            if not group:
                continue
            k, n = accuracy(group)
            low, high = wilson(k, n)
            wrong = [r for r in group if r.correct is False]
            fails = [r for r in group if r.failure]
            times = sorted(r.seconds for r in group)
            cost = sum(r.cost_usd for r in group)
            acc = f"{k / n:7.2f}" if pass_name != "challenger" else f"{'—':>7s}"
            ci = f"[{low:.2f},{high:.2f}]" if pass_name != "challenger" else ""
            print(f"{model:32s}{pass_name:11s}{n:4d}{acc}{ci:>15s}"
                  f"{sum(1 for r in wrong if r.gold_flawed):4d}"
                  f"{sum(1 for r in wrong if not r.gold_flawed):4d}"
                  f"{len(fails):6d}{sum(r.repairs for r in group):5d}"
                  f"{sum(1 for r in group if r.native_reasoning):5d}"
                  f"{statistics.median(times):7.1f}"
                  f"{times[int(0.95 * len(times)) - 1] if times else 0:7.1f}"
                  f"{cost / n if n else 0:9.4f}")

    # per-subset solo accuracy, with intervals, against the drop line
    print(f"\nSolo accuracy per subset — DROP at >= {DROP_AT:.2f}, KEEP at "
          f"<= {KEEP_BELOW:.2f}, gray between")
    subsets = sorted({r.subset for r in rows if r.pass_name == "solo"})
    print(f"{'model':32s}" + "".join(f"{s[:12]:>16s}" for s in subsets))
    print("-" * (32 + 16 * len(subsets)))
    for model in models:
        cells = []
        for subset in subsets:
            group = [r for r in by.get((model, "solo"), []) if r.subset == subset]
            if not group:
                cells.append(f"{'—':>16s}")
                continue
            k, n = accuracy(group)
            p = k / n
            mark = "D" if p >= DROP_AT else ("K" if p <= KEEP_BELOW else "?")
            cells.append(f"{p:>8.2f} {mark} n={n:<3d}")
        print(f"{model:32s}" + "".join(cells))
        indent = " " * 32
        intervals = []
        for subset in subsets:
            group = [r for r in by.get((model, "solo"), []) if r.subset == subset]
            if not group:
                intervals.append(f"{'':>16s}")
                continue
            low, high = wilson(*accuracy(group))
            intervals.append(f"{f'[{low:.2f},{high:.2f}]':>16s}")
        print(indent + "".join(intervals))
    print("  D = drop zone, K = keep zone, ? = gray (escalate +40 items)")

    # the number that says whether a transcript is worth anything to this model
    print("\nTranscript uplift — judge accuracy minus solo accuracy, on the fixture's "
          "own items")
    print("  (this is also the weak_alone reference the design's biggest confound "
          "needs; see LLM_NOTES §4)")
    print(f"{'model':32s}{'solo':>9s}{'judge':>9s}{'uplift':>9s}{'decline':>10s}")
    print("-" * 69)
    for model in models:
        judged = by.get((model, "judge"), [])
        if not judged:
            continue
        paired = {r.item_id for r in judged}
        solo = [r for r in by.get((model, "solo"), []) if r.item_id in paired]
        sk, sn = accuracy(solo)
        jk, jn = accuracy(judged)
        challenged = by.get((model, "challenger"), [])
        raised = [r for r in challenged if r.raised is not None]
        solo_acc = sk / sn if sn else float("nan")
        judge_acc = jk / jn if jn else float("nan")
        decline = (sum(1 for r in raised if not r.raised) / len(raised)
                   if raised else float("nan"))
        print(f"{model:32s}{solo_acc:9.2f}{judge_acc:9.2f}{judge_acc - solo_acc:+9.2f}"
              f"{decline:10.2f}")


def print_latency(outputs: Path, models: list[str]) -> None:
    """Per-**request** latency and throughput, read from the wire log.

    The `p50`/`p95` columns in the table above are wall-clock around the whole coroutine,
    which includes the time a call spent queued behind the concurrency semaphore. At
    `max_concurrency = 8` over 280 items that queue wait dominates, so those columns say
    how long the *probe* took and not how fast the *model* is. They are three to twenty
    times the true figure and they are not comparable between candidates whose calls
    happened to queue differently.

    The honest number is the provider's own: `latency_ms` per request, and
    `completion_tokens / latency_ms` for throughput. Both are in `calls-<model>.jsonl`.
    This is what the repo's model-choice rule means by "check throughput and latency" —
    measured on our own prompt lengths, since OpenRouter's API returns null for both.
    """
    print("\nPer-request latency and throughput, from the wire log")
    print("  (NOT the p50/p95 columns above — those include semaphore queue wait and "
          "are a fact about the probe, not the model)")
    print(f"{'model':32s}{'role':12s}{'n':>5s}{'p50 s':>8s}{'p95 s':>8s}"
          f"{'tok/s p50':>11s}{'out tok p50':>13s}")
    print("-" * 89)
    for model in models:
        path = outputs / f"calls-{model.replace('/', '-')}.jsonl"
        if not path.is_file():
            continue
        by_role = collections.defaultdict(list)
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            ms = record.get("latency_ms")
            out = ((record.get("usage") or {}).get("completion_tokens")) or 0
            if not ms:
                continue
            by_role[record.get("role") or "?"].append((ms / 1000.0, out))
        for role in ("solo", "judge", "challenger"):
            group = by_role.get(role)
            if not group:
                continue
            secs = sorted(s for s, _ in group)
            toks = sorted(o for _, o in group)
            rates = sorted(o / s for s, o in group if s > 0 and o)
            print(f"{model:32s}{role:12s}{len(group):5d}"
                  f"{statistics.median(secs):8.1f}"
                  f"{secs[max(0, int(0.95 * len(secs)) - 1)]:8.1f}"
                  f"{(statistics.median(rates) if rates else 0):11.0f}"
                  f"{statistics.median(toks):13.0f}")


def print_flags(rows: list[Row]) -> None:
    """Apply the disqualifiers mechanically, so nobody has to eyeball them."""
    print("\nDisqualifier check")
    print("-" * 100)
    by_model = collections.defaultdict(list)
    for row in rows:
        by_model[row.model].append(row)
    for model, group in sorted(by_model.items()):
        problems = []
        n = len(group)
        fails = sum(1 for r in group if r.failure)
        native = sum(1 for r in group if r.native_reasoning)
        if n and fails / n > MAX_FORMAT_FAILURE:
            problems.append(f"format failure {fails / n:.0%}")
        if n and native / n > MAX_NATIVE_REASONING:
            problems.append(f"native reasoning {native / n:.0%} despite off")
        judged = [r for r in group if r.pass_name == "judge" and r.verdict]
        if judged:
            counts = collections.Counter(r.verdict for r in judged)
            skew = counts.most_common(1)[0][1] / len(judged)
            if skew > MAX_VERDICT_SKEW:
                problems.append(f"verdict skew {skew:.0%} "
                                f"{counts.most_common(1)[0][0]}")
            if MIN_JUDGE_ACCURACY is not None:
                k, jn = accuracy([r for r in group if r.pass_name == "judge"])
                if jn and k / jn < MIN_JUDGE_ACCURACY:
                    problems.append(f"judge accuracy {k / jn:.2f} with transcript")
        raised = [r for r in group if r.pass_name == "challenger" and r.raised is not None]
        if raised:
            rate = sum(1 for r in raised if r.raised) / len(raised)
            if rate in (0.0, 1.0):
                problems.append(f"challenger always {'objects' if rate else 'declines'}")
        print(f"  {model:34s} {'DISQUALIFIED: ' + '; '.join(problems) if problems else 'passes'}")


# --------------------------------------------------------------------------- #
# cli
# --------------------------------------------------------------------------- #


def sample_cases(cases_root: Path, per_subset: int, seed: int, offset: int = 0,
                 subsets: list[str] | None = None):
    """A balanced draw per subset, seeded, shared across candidates so the comparison
    is paired.

    `offset` is counted in **items**, the same unit as `per_subset`, so `--offset 40`
    after a `--per-subset 40` run draws exactly the next 40 items and leaves no gap.
    (Each subset's pool is split by label and half of each figure is taken from each
    side, which is where the factor of two lives.) At `offset=0` this is unchanged.

    `subsets` restricts the draw, which is how a gray-zone escalation buys 40 more items
    for the two subsets that need them instead of for all seven.
    """
    out = []
    for key in sorted(SUBSETS):
        if subsets and key not in subsets:
            continue
        path = cases_root / f"ftf-{key}.jsonl"
        if not path.is_file():
            continue
        cases = load_cases(path)
        for flawed in (True, False):
            pool = [c for c in cases if c.item.gold_flawed is flawed]
            random.Random(f"{seed}:pick:{key}:{flawed}").shuffle(pool)
            start = offset // 2
            out.extend(pool[start: start + per_subset // 2])
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", default=None)
    parser.add_argument("--per-subset", type=int, default=40,
                        help="items per subset per candidate, balanced flawed/sound. "
                             "40 gives a 95%% CI of about +/-0.13 at p=0.75, which is "
                             "what a 0.80/0.70 decision needs; 12 gives +/-0.24 and "
                             "cannot support a drop at all")
    parser.add_argument("--fixture-per-subset", type=int, default=12,
                        help="debates built with the strong model, per subset")
    parser.add_argument("--offset", type=int, default=0,
                        help="skip the first N items of each subset — how a gray-zone "
                             "subset is escalated without re-running what was already "
                             "measured. Counted in the same unit as --per-subset, so "
                             "--offset 40 after a --per-subset 40 run draws exactly the "
                             "next 40 and leaves no gap. Escalation rows are written to "
                             "rows-solo-<model>-offset<N>.jsonl and pooled with the base "
                             "draw by the report")
    parser.add_argument("--subsets", default=None,
                        help="comma-separated subset keys to screen (pass 1 only). The "
                             "gray-zone escalation runs --models <chosen> --subsets "
                             "<gray> --offset 40 and nothing else; passes 3-4 read their "
                             "cached rows, so no fixture call is re-spent")
    parser.add_argument("--cases-root", type=Path, default=Path("data/cases"))
    parser.add_argument("--outputs", type=Path, default=Path("outputs/pick-weak"))
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--skip-fixture", action="store_true",
                        help="solo screen only; skips passes 2-4")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report-only", action="store_true",
                        help="re-derive every table from the rows and calls files "
                             "already on disk and exit. No network, no spend. This is "
                             "how a changed rule is re-applied to measurements that "
                             "have already been paid for")
    args = parser.parse_args(argv)

    if args.report_only:
        safe = models_on_disk(args.outputs)
        rows = all_rows_on_disk(args.outputs, safe)
        if not rows:
            print(f"no rows-*.jsonl under {args.outputs}")
            return 1
        print(f"report-only: {len(rows)} rows already on disk for {len(safe)} models. "
              "Nothing was sent.")
        print_rules()
        print_report(rows)
        print_latency(args.outputs, safe)
        print_flags(drop_leaked(rows))
        return 0

    models = ([m.strip() for m in args.models.split(",") if m.strip()]
              if args.models else list(CANDIDATES))
    subsets = ([x.strip() for x in args.subsets.split(",") if x.strip()]
               if args.subsets else None)
    unknown = sorted(set(subsets or []) - set(SUBSETS))
    if unknown:
        parser.error(f"unknown subset(s) {unknown}; known: {sorted(SUBSETS)}")
    config, client_config = load_config()
    screen = sample_cases(args.cases_root, args.per_subset, args.seed, args.offset,
                          subsets)
    # The fixture is never restricted or offset: it is cached, shared across candidates,
    # and passes 3-4 resume from their own rows files.
    fixture_cases = sample_cases(args.cases_root, args.fixture_per_subset, args.seed)

    solo_calls = len(screen) * len(models)
    fixture_calls = len(fixture_cases) * (2 * config.n_rounds)
    judge_calls = len(fixture_cases) * len(models)
    challenge_calls = judge_calls

    print(f"candidates ({len(models)}):")
    for model in models:
        print(f"  - {model}")
    print(f"\nstrong model for the fixture: {config.debater_model}")
    drawn = collections.Counter(c.item.subset for c in screen)
    print(f"\n  pass 1  solo screen   {len(screen):4d} items x {len(models)} candidates "
          f"= {solo_calls:5d} calls")
    print("            drawn per subset: "
          + ", ".join(f"{k}={drawn[k]}" for k in sorted(drawn)))
    short = {k: n for k, n in drawn.items() if n < args.per_subset}
    if short or (subsets and len(drawn) < len(subsets)):
        missing = sorted(set(subsets or SUBSETS) - set(drawn))
        print(f"            NOTE: the pool is exhausted for {sorted(short) + missing} — "
              "fewer items than asked for")
    if args.offset:
        print(f"            offset {args.offset}: these are items "
              f"{args.offset}..{args.offset + args.per_subset} of each subset, "
              "disjoint from the base draw and pooled with it by the report")
    if not args.skip_fixture:
        print(f"  pass 2  fixture       {len(fixture_cases):4d} debates x "
              f"{2 * config.n_rounds} debater calls = {fixture_calls:5d} calls "
              "(strong model, built once, cached)")
        print(f"  pass 3  judge         {len(fixture_cases):4d} x {len(models)} "
              f"= {judge_calls:5d} calls")
        print(f"  pass 4  challenger    {len(fixture_cases):4d} x {len(models)} "
              f"= {challenge_calls:5d} calls")
    total = solo_calls + (0 if args.skip_fixture
                          else fixture_calls + judge_calls + challenge_calls)
    print(f"\n  total {total} calls. Prompts measured at ~1k tokens (round 1) to ~5k "
          "(judge, full transcript);")
    print("  at the candidates' quoted prices this is single-digit dollars, dominated "
          "by weak-model completions.")

    print("\nHyperparameters for the probe")
    print("=" * 100)
    for name, value, why in (
        ("solo temperature", config.judge_temperature,
         "the judge's, not the debater's — the role being simulated decides alone at 0"),
        ("judge temperature", config.judge_temperature, WHY["judge_temperature"]),
        ("debater temperature", config.debater_temperature, WHY["debater_temperature"]),
        ("n_rounds", config.n_rounds, WHY["n_rounds"]),
        ("word_limit", config.word_limit, WHY["word_limit"]),
        ("max_tokens", config.max_tokens, WHY["max_tokens"]),
        ("reasoning_effort", config.reasoning_effort, WHY["reasoning_effort"]),
        ("seed", args.seed, "shared across candidates, so the comparison is paired"),
        ("per_subset", args.per_subset, "see --help; 40 is what a 0.80/0.70 call needs"),
        ("offset", args.offset,
         "0 for the base draw; 40 escalates a gray subset onto its next 40 items"),
        ("subsets", ",".join(subsets) if subsets else "all",
         "pass 1 only; the escalation screens just the gray subsets"),
    ):
        print(f"  {name:22s} {str(value):8s} {why}")
    print("=" * 100)
    print_rules()

    if args.dry_run:
        print("\ndry run — nothing was sent.")
        return 0

    args.outputs.mkdir(parents=True, exist_ok=True)
    (args.outputs / "settings.json").write_text(json.dumps({
        "models": models, "per_subset": args.per_subset, "offset": args.offset,
        "subsets": subsets,
        "fixture_per_subset": args.fixture_per_subset, "seed": args.seed,
        "config": config.to_dict(),
        "rules": {"drop_at": DROP_AT, "keep_below": KEEP_BELOW,
                  "max_format_failure": MAX_FORMAT_FAILURE,
                  "max_native_reasoning": MAX_NATIVE_REASONING,
                  "max_verdict_skew": MAX_VERDICT_SKEW,
                  "min_judge_accuracy": MIN_JUDGE_ACCURACY,
                  "latency_multiple": LATENCY_MULTIPLE},
    }, indent=2), encoding="utf-8")
    load_dotenv()
    api_key = read_api_key()

    async def go() -> int:
        live = await liveness(models, client_config, api_key)
        print("\nliveness:")
        for model, state in live.items():
            print(f"  {model:34s} {state}")
        (args.outputs / "liveness.json").write_text(json.dumps(live, indent=2),
                                                    encoding="utf-8")
        usable = [m for m, state in live.items() if state == "live"]
        if not usable:
            print("\nno candidate is reachable; nothing to screen.")
            return 1
        for model, state in live.items():
            if state != "live":
                print(f"\n  {model} is DISQUALIFIED before any measurement: {state}")

        rows: list[Row] = []
        for model in usable:
            cached = load_rows(args.outputs, model, "solo", args.offset)
            if cached is not None:
                print(f"\npass 1: {model} already screened at offset {args.offset} "
                      f"({len(cached)} items) — skipping")
                rows += cached
                continue
            print(f"\npass 1: screening {model} over {len(screen)} items...")
            fresh = await solo_screen(model, screen, config, client_config, api_key,
                                      args.outputs)
            save_rows(args.outputs, model, "solo", fresh, args.offset)
            rows += fresh

        if not args.skip_fixture:
            print(f"\npass 2: building {len(fixture_cases)} debates with "
                  f"{config.debater_model}...")
            fixture = await build_fixture(fixture_cases, config, client_config, api_key,
                                          args.outputs)
            for model in usable:
                cached = load_rows(args.outputs, model, "judge")
                cached_c = load_rows(args.outputs, model, "challenger")
                if cached is not None and cached_c is not None:
                    print(f"\npasses 3-4: {model} already done — skipping")
                    rows += cached + cached_c
                    continue
                print(f"\npasses 3-4: {model} judges and contests {len(fixture)} "
                      "debates...")
                judged, challenged = await judge_and_challenge(
                    model, fixture, config, client_config, api_key, args.outputs)
                save_rows(args.outputs, model, "judge", judged)
                save_rows(args.outputs, model, "challenger", challenged)
                rows += judged + challenged

        (args.outputs / "rows.jsonl").write_text(
            "\n".join(json.dumps(r.to_dict()) for r in rows) + "\n", encoding="utf-8")
        print_report(rows, args.outputs)
        print_latency(args.outputs, usable)
        print_flags(drop_leaked(pool_solo(args.outputs, rows)))
        print(f"\nwrote {args.outputs / 'rows.jsonl'} and per-model calls-*.jsonl")
        print("\nNothing was decided here. Apply the rules above, then put the chosen "
              "model,\nthe surviving subsets, and this evidence into the docs by hand.")
        return 0

    return asyncio.run(go())


if __name__ == "__main__":
    raise SystemExit(main())

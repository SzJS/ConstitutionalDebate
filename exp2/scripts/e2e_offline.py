"""Offline end-to-end: the whole harness over real items, against the fake client.

    uv run python scripts/e2e_offline.py 2>&1 | tee outputs/e2e-offline-2.log

Every stage of ``exp2-experiment`` — decide, contest, grade, analyse — is run over a
handful of **real** cases from ``data/cases/pilot.jsonl``, with
``experiment.OpenRouterClient`` replaced by ``tests.conftest.FakeClient``. Nothing
reaches the network and nothing reads the API key: the key is removed from the
environment before a stage starts, so a wiring mistake fails loudly instead of
spending.

What it is for is the pair of documents. A synthetic fixture cannot show whether
``transcript.md`` and ``transcript_full.md`` read well over a real problem statement, a
real solution, and a real flaw annotation; this writes both for every cell and every
contest so they can be read by hand.

The deciders are scripted to answer SOUND, because that is what makes the flawed items
*incorrectly* decided — the grade stage is confined to the metric's own denominator, so
without a wrong decision it would skip everything and the grading path would go
unexercised.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tests"))
sys.path.insert(0, str(REPO / "src"))

from conftest import FakeClient  # noqa: E402  (needs the path above)

from exp2 import experiment as experiment_module  # noqa: E402
from exp2.analysis import analyse  # noqa: E402
from exp2.arms import WITHHELD  # noqa: E402
from exp2.config import load_config, load_grading_config  # noqa: E402
from exp2.experiment import (  # noqa: E402
    build_grid,
    build_index,
    run_stage_contest,
    run_stage_decide,
    run_stage_grade,
)
from exp2.types import load_cases  # noqa: E402

SPEC = REPO / "experiments" / "pilot.toml"
CASES = REPO / "data" / "cases" / "pilot.jsonl"
ROOT = REPO / "outputs" / "e2e-offline-2"
CONDITIONS = ["single", "self_critique", "debate"]
# The line artifacts_full.py prints when an accepted call is not in calls.jsonl.
FALLBACK = "Prompts were not recorded for this run"

# Four real items: three flawed (so the grade stage has a denominator) and one sound,
# spanning all three label bases and three subsets. Annotation quality varies too —
# gpqa is location_only, which the grader has to clamp rather than guess at.
ITEMS = [
    "gpqa-123-flawed",            # injected_pair, location_only
    "law-con2_gpt4_A-s13",        # sentence_labels, explanation
    "medqa-train_2855",           # final_answer, explanation
    "law-evi1_gpt4_A-s4",         # sentence_labels, sound — never graded, by design
]

# Every decider answers SOUND. See the module docstring.
DECIDER_REPLIES = {
    "judge": "The sound side answered the objection.\nVerdict: SOUND",
    ("solo", "answer"): ("Thinking: SECRET-SOLO-THINKING-never-published\n"
                         "Reasoning: step 2 follows from step 1.\nVerdict: SOUND"),
    ("solo", "draft"): ("Thinking: SECRET-SOLO-THINKING-never-published\n"
                        "Reasoning: step 2 follows from step 1.\nVerdict: SOUND"),
    ("solo", "revision"): ("Thinking: SECRET-SOLO-THINKING-never-published\n"
                           "Reasoning: the criticism does not land.\nVerdict: SOUND"),
    # The challenger has to CONTEST for a ruling to be sought and for the grade stage to
    # have anything to run on: since 2026-08-25 a raised objection whose claimed verdict
    # matches the decision is the `agrees` stance, which seeks no ruling. The decisions
    # above are all SOUND, so a contest claims FLAWED. Written in the shape the weak
    # model actually produces — no Thinking:/Argument: labels at all.
    "challenger": ("Objection: RAISED\nVerdict should be: FLAWED\n"
                   "Step 2 does not follow from step 1; the decision took it on trust."),
}


def install_fake_client() -> list[FakeClient]:
    """Replace ``experiment.OpenRouterClient`` with the fake, as the tests do.

    ``tests/test_experiment.py`` shares **one** instance across every stage so that
    ``max_in_flight`` measures the whole fleet. That is wrong here: each stage builds a
    client per run and hands it that run's ``sink``, so a shared instance has one sink
    at a time and the concurrent runs all log into whichever directory entered last —
    the rest get no ``calls.jsonl`` and their full document falls back to
    generations-only. One fake per context manager, exactly as the real client is built,
    keeps every run's wire log in its own directory.
    """
    made: list[FakeClient] = []

    class Ctx:
        def __init__(self, *args, **kwargs):
            self.client = FakeClient(replies=dict(DECIDER_REPLIES),
                                     sink=kwargs.get("sink"))

        async def __aenter__(self):
            made.append(self.client)
            return self.client

        async def __aexit__(self, *exc):
            return False

    experiment_module.OpenRouterClient = Ctx
    os.environ.pop("OPENROUTER_KEY", None)
    return made


async def main() -> int:
    config, client_config = load_config(SPEC)
    grading = load_grading_config(SPEC)

    by_id = {case.item.item_id: case for case in load_cases(CASES)}
    missing = [i for i in ITEMS if i not in by_id]
    if missing:
        raise SystemExit(f"not in {CASES}: {missing}")
    grid = build_grid([by_id[i] for i in ITEMS], CONDITIONS)

    clients = install_fake_client()

    ROOT.mkdir(parents=True, exist_ok=True)
    print(f"outputs: {ROOT}")
    print(f"cells: {len(grid)}  items: {len(ITEMS)}  conditions: {CONDITIONS}")
    print("client: tests.conftest.FakeClient — no network, OPENROUTER_KEY unset\n")

    stages = {
        "decide": lambda: run_stage_decide(
            grid, root=ROOT, config=config, client_config=client_config, api_key="fake"),
        "contest": lambda: run_stage_contest(
            grid, root=ROOT, config=config, client_config=client_config, api_key="fake"),
        "grade": lambda: run_stage_grade(
            grid, root=ROOT, config=config, grading=grading,
            client_config=client_config, api_key="fake"),
    }
    for stage, runner in stages.items():
        results = await runner()
        counts: dict[str, int] = {}
        for result in results:
            key = ("error" if isinstance(result, BaseException)
                   else result.get("status", "unknown"))
            counts[key] = counts.get(key, 0) + 1
        print(f"{stage:9s} {counts}")
        for result in results:
            if isinstance(result, BaseException):
                print(f"  ! {type(result).__name__}: {result}")
            elif result.get("status") == "failed":
                print(f"  ! {result['cell_id']}: {result.get('error')}")

    rows = build_index(grid, root=ROOT, challenger_model=config.challenger_model_for())
    index = ROOT / "index.jsonl"
    index.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    metrics = analyse(index, CONDITIONS)
    (ROOT / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(f"\nindexed {len(rows)} rows")
    incorrect = {c: sum(1 for r in rows
                        if r["condition"] == c and r.get("initially_correct") is False)
                 for c in CONDITIONS}
    print(f"per-condition incorrect cells: {incorrect}")
    print(f"label bases seen: {sorted({r['label_basis'] for r in rows})}")
    print(f"subsets seen: {sorted({r['subset'] for r in rows})}")
    print(f"caveats emitted: {len(metrics['caveats'])}")
    print(f"fake clients built: {len(clients)}  "
          f"calls: {sum(len(c.calls) for c in clients)}")

    return report_documents()


def report_documents() -> int:
    """Both documents, for every run directory and every contest directory."""
    print("\ndocuments written")
    missing = 0
    fallbacks: list[str] = []
    for run in sorted((ROOT / "cells").glob("*/runs/*")):
        pairs = [run] + sorted((run.parent.parent / "contests").glob("*/runs/*"))
        for directory in pairs:
            have = [name for name in ("transcript.md", "transcript_full.md")
                    if (directory / name).is_file()]
            kind = "contest" if "contests" in directory.parts else "run    "
            gap = "" if len(have) == 2 else f"   MISSING {set(('transcript.md', 'transcript_full.md')) - set(have)}"
            missing += 2 - len(have)
            sizes = "  ".join(f"{n}={(directory / n).stat().st_size}B" for n in have)
            full = directory / "transcript_full.md"
            if full.is_file() and FALLBACK in full.read_text(encoding="utf-8"):
                fallbacks.append(str(directory.relative_to(ROOT)))
                sizes += "  [generations-only fallback]"
            print(f"  {kind} {directory.relative_to(ROOT)}  {sizes}{gap}")
    print(f"\nmissing documents: {missing}")
    print(f"full documents on the generations-only fallback: {len(fallbacks)}")
    for path in fallbacks:
        print(f"  ! {path}")

    # The self_critique readable document has to contain the critique itself: that is
    # the whole point of the Step 2 prompt fix, and a placeholder there is a confound.
    withheld = []
    for run in sorted((ROOT / "cells").glob("*__self_critique__*/runs/*")):
        text = (run / "transcript.md").read_text(encoding="utf-8")
        trace = json.loads((run / "trace.json").read_text(encoding="utf-8"))
        critiques = [s for s in trace["steps"] if s["stage"] == "critique"]
        bad = [s for s in critiques
               if not s["text"].strip() or s["text"] == WITHHELD
               or s["text"].strip().splitlines()[0] not in text]
        if bad or not critiques:
            withheld.append(f"{run.relative_to(ROOT)}  "
                            f"({len(bad)}/{len(critiques)} critiques not published)")
    print(f"self_critique readable documents with a withheld critique: {len(withheld)}")
    for path in withheld:
        print(f"  ! {path}")
    return 1 if (missing or withheld or fallbacks) else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

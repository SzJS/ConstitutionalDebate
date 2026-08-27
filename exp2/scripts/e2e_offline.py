"""Offline end-to-end: the whole harness over real items, against the fake client.

    uv run python scripts/e2e_offline.py 2>&1 | tee outputs/e2e-offline-2.log

Every stage of ``exp2-experiment`` — decide, contest, agreement, grade, analyse — is run over a
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

**Three passes.** The first two are the two recourse forms, each of which writes a
different document; the third is a `contests_from` re-rule over the first's tree.

**Two of them, because there are two recourse forms and each writes a different
document.** The first is the whole grid under ``recourse_form = "third_party"`` — what
the re-contest specs set and what DESIGN.md settled on: every condition's objection is
ruled by a judge that did not decide, so a solo cell's ``transcript.md`` closes with
"Ruled on by a judge who did not make the original decision". The second is two solo
cells under ``per_condition``, the historical routing every paid run so far used, whose
document closes with "Reconsidered by the same reviewer that made the decision" instead.
Both sentences are published to a stakeholder as the account of how their objection was
heard, so both have to be rendered over a real record and read, and a script that
covered only the new one would let the other rot. The challenger's reply is in its new
shape in both: reasons first, the decision line last.

**The third pass is the re-rule**: the first tree's finished objections, ruled again
into a tree of their own under `contests_from`. It is the path the 1,586 existing
rulings will be re-made on, and its safety property — neither source tree changes by one
byte — is asserted here with a hash before and after, over real records rather than a
fixture. It also runs the `ruling_agreement` stage, the reading of the judge's own prose
that bounds every revision number.

**Every root is deleted first.** Each stage resumes on its own artifacts, which is what a
real run needs and exactly wrong here: a tree left by an earlier version of this script
would be skipped rather than re-made, and the assertions below would pass by describing
records the current code did not write. The whole thing is offline and takes seconds.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import os
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tests"))
sys.path.insert(0, str(REPO / "src"))

from conftest import FakeClient  # noqa: E402  (needs the path above)

from exp2 import experiment as experiment_module  # noqa: E402
from exp2.analysis import analyse  # noqa: E402
from exp2.arms import WITHHELD, WITHHELD_TRUNCATED  # noqa: E402
from exp2.config import load_config, load_grading_config  # noqa: E402
from exp2.experiment import (  # noqa: E402
    build_grid,
    build_index,
    run_stage_agreement,
    run_stage_contest,
    run_stage_decide,
    run_stage_grade,
    run_stage_rerule,
    run_stage_ruling_agreement,
)
from exp2.persistence import tree_sha256  # noqa: E402
from exp2.types import load_cases  # noqa: E402

SPEC = REPO / "experiments" / "pilot.toml"
CASES = REPO / "data" / "cases" / "pilot.jsonl"
ROOT = REPO / "outputs" / "e2e-offline-2"
# The second pass writes its own tree: a cell is contested once, so the two forms cannot
# share one.
ROOT_PER_CONDITION = REPO / "outputs" / "e2e-offline-2-per-condition"
# The third pass writes its own tree too: it re-rules ROOT's contests, and a re-rule must
# never write into the tree it reads.
ROOT_RERULE = REPO / "outputs" / "e2e-offline-2-rerule"
CONDITIONS = ["single", "self_critique", "debate"]
# `per_condition` only differs from `third_party` where the decider re-decides, which is
# the two solo conditions; `debate` is ruled by the judge under either.
SOLO_CONDITIONS = ["single", "self_critique"]
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
    # have anything to run on. The line is one relative token, so REVERSE contests
    # whatever the decision was — the decisions above are all SOUND, so this asks for
    # FLAWED. Written in the shape the weak model actually produces: no
    # Thinking:/Argument: labels at all.
    "challenger": ("Step 2 does not follow from step 1; the decision took it on "
                   "trust.\nDecision: REVERSE"),
    # The line-vs-prose instrument. WRONG matches the REVERSE line above, so the offline
    # run exercises the agreeing branch end to end.
    "agreement": "It argues the verdict was mistaken.\nProse: WRONG",
    # The recourse judge states an absolute conclusion about the ORIGINAL text and never
    # a relative word; UPHOLD/OVERTURN is derived from it. Every decision above is SOUND,
    # so a judge that finds a flaw overturns — which is what keeps the offline run
    # exercising a revision end to end.
    "recourse_judge": ("The objection is right that step 2 does not follow.\n"
                       "Conclusion: the original text in <solution> contains a flaw"),
    # The ruling's line-vs-prose instrument. FLAWED matches the conclusion above, so the
    # offline run exercises the consistent branch and `ruling_line_mismatch` is False.
    "ruling_reader": ("It concludes the text does not follow at step 2.\n"
                      "Reading: FLAWED"),
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


async def run_stages(root, grid, config, client_config, grading) -> None:
    """decide, contest, agreement, ruling_agreement, grade over one grid, into one tree."""
    stages = {
        "decide": lambda: run_stage_decide(
            grid, root=root, config=config, client_config=client_config, api_key="fake"),
        "contest": lambda: run_stage_contest(
            grid, root=root, config=config, client_config=client_config, api_key="fake"),
        "agreement": lambda: run_stage_agreement(
            grid, root=root, config=config, grading=grading,
            client_config=client_config, api_key="fake"),
        "ruling_agreement": lambda: run_stage_ruling_agreement(
            grid, root=root, config=config, grading=grading,
            client_config=client_config, api_key="fake"),
        "grade": lambda: run_stage_grade(
            grid, root=root, config=config, grading=grading,
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


def ruling_forms(root) -> dict[str, dict[str, int]]:
    """``{condition: {form: count}}`` over every ruling.json in a tree."""
    forms: dict[str, dict[str, int]] = {}
    for path in sorted(root.glob("cells/*/contests/*/runs/*/ruling.json")):
        condition = path.parents[4].name.split("__")[1]
        form = json.loads(path.read_text(encoding="utf-8")).get("form")
        forms.setdefault(condition, {})
        forms[condition][form] = forms[condition].get(form, 0) + 1
    return forms


def rendered_outcome_lines(root) -> set[str]:
    """The italic sentence each contest document closes its outcome section with.

    Read out of the rendered markdown rather than asserted against `artifacts.py`,
    because what is under test is the document a stakeholder is handed.
    """
    lines = set()
    for path in sorted(root.glob("cells/*/contests/*/runs/*/transcript.md")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("*Ruled on by") or line.startswith("*Reconsidered by"):
                lines.add(line.strip())
    return lines


async def main() -> int:
    config, client_config = load_config(SPEC)
    # `pilot.toml` predates the field and so loads the historical routing, which is what
    # the second pass wants; the first replaces it with the settled one. The decision
    # stages read neither.
    per_condition_config = config
    config = dataclasses.replace(config, recourse_form="third_party")
    grading = load_grading_config(SPEC)

    by_id = {case.item.item_id: case for case in load_cases(CASES)}
    missing = [i for i in ITEMS if i not in by_id]
    if missing:
        raise SystemExit(f"not in {CASES}: {missing}")
    grid = build_grid([by_id[i] for i in ITEMS], CONDITIONS)

    clients = install_fake_client()

    # Every stage resumes on its own artifacts, which is what a real run needs and
    # exactly wrong here: a tree left by an earlier version of this script would be
    # skipped rather than re-made, and every assertion below would then be describing
    # records the current code did not write.
    for root in (ROOT, ROOT_PER_CONDITION, ROOT_RERULE):
        if root.exists():
            shutil.rmtree(root)
    ROOT.mkdir(parents=True, exist_ok=True)
    print(f"outputs: {ROOT}")
    print(f"cells: {len(grid)}  items: {len(ITEMS)}  conditions: {CONDITIONS}")
    print("client: tests.conftest.FakeClient — no network, OPENROUTER_KEY unset")
    print(f"recourse_form: {config.recourse_form} — every condition's objection is "
          "ruled by a judge that did not decide\n")

    await run_stages(ROOT, grid, config, client_config, grading)

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

    # Under `third_party` there must be no `restated_verdict` anywhere, in any condition
    # — that form is the decider re-deciding its own appeal, which is what the change
    # removes. Reported per condition, because the solo ones are where it would survive.
    #
    # And the form has to be `stated_conclusion`, not `uphold_overturn`: nothing generates
    # the relative line any more, so a cell that still carried it would mean the judge was
    # asked the question the re-contest measured it getting wrong.
    forms = ruling_forms(ROOT)
    print(f"ruling forms per condition: {forms}")
    stray = {c: f for c, f in forms.items() if set(f) != {"stated_conclusion"}}
    print(f"rulings NOT made by a third-party judge stating its own conclusion: {stray}")
    outcomes = rendered_outcome_lines(ROOT)
    print(f"rendered outcome sentences: {sorted(outcomes)}")
    if not outcomes or any("Reconsidered by" in line for line in outcomes):
        stray["rendering"] = {"the document does not say a judge ruled": 1}
    # And the challenger's line really is last: the parser strips the decisive match, so
    # a body that still ends in one would mean an earlier line was taken instead.
    still_labelled = sum(
        1 for path in ROOT.glob("cells/*/contests/*/runs/*/challenge.json")
        if "Decision:" in json.loads(path.read_text(encoding="utf-8"))["text"])
    print(f"objections whose published text still carries a decision line: "
          f"{still_labelled}")

    first = report_documents(ROOT) or (1 if stray else 0)
    third = await rerule_pass(config, client_config, grading, grid)
    return await per_condition_pass(
        per_condition_config, client_config, grading, by_id) or first or third


async def rerule_pass(config, client_config, grading, grid) -> int:
    """The first tree's finished objections, ruled again into a tree of their own.

    This is the path the sweep's 1,122 rulings and the re-contest's 464 will be re-made
    on, and its whole safety property is that neither source tree changes by one byte —
    asserted here with a hash before and after, over real records rather than a fixture.
    The objection, its comprehension probe, its agreement reading and its grade come
    across with the copy; only the ruling is made again, which is why `grade` never runs
    on a re-rule spec and why the index below still carries `grade_valid`.
    """
    ROOT_RERULE.mkdir(parents=True, exist_ok=True)
    print(f"\n{'=' * 78}\nthird pass — re-ruling the first tree's objections")
    print(f"outputs: {ROOT_RERULE}")
    print(f"decisions and objections read from: {ROOT}   (never written to)")
    before = tree_sha256(ROOT)

    results = await run_stage_rerule(
        grid, root=ROOT_RERULE, config=config, client_config=client_config,
        api_key="fake", decision_root=ROOT, contest_root=ROOT)
    counts: dict[str, int] = {}
    for result in results:
        key = ("error" if isinstance(result, BaseException)
               else result.get("status", "unknown"))
        counts[key] = counts.get(key, 0) + 1
    print(f"{'rerule':9s} {counts}")
    for result in results:
        if isinstance(result, BaseException):
            print(f"  ! {type(result).__name__}: {result}")
        elif result.get("status") == "failed":
            print(f"  ! {result['cell_id']}: {result.get('error')}")
    forms_replaced = sorted({r.get("was") for r in results
                             if not isinstance(r, BaseException) and r.get("was")})
    print(f"ruling forms replaced: {forms_replaced}")

    await run_stage_ruling_agreement(
        grid, root=ROOT_RERULE, config=config, grading=grading,
        client_config=client_config, api_key="fake")

    rulings = sorted(ROOT_RERULE.glob("cells/*/contests/*/runs/*/ruling.json"))
    stray: dict[str, int] = {}
    forms = {}
    for path in rulings:
        ruling = json.loads(path.read_text(encoding="utf-8"))
        forms[ruling.get("form")] = forms.get(ruling.get("form"), 0) + 1
        if ruling.get("form") != "stated_conclusion":
            stray["a ruling not made under the stated-conclusion line"] = 1
        if not ruling.get("conclusion_line", "").startswith("Conclusion:"):
            stray["a ruling with no conclusion line of its own"] = 1
        for name in ("ruling.source.json", "ruling_agreement.json", "challenge.json",
                     "comprehension.json", "agreement.json"):
            if not (path.parent / name).is_file():
                stray[f"a re-ruled contest with no {name}"] = 1
        if (path.parent / "transcript.md").read_text(encoding="utf-8").find(
                "stated its own conclusion about the text under review") < 0:
            stray["a document that does not say the judge stated its own conclusion"] = 1
    print(f"re-rulings written: {len(rulings)}  forms: {forms}")

    rows = build_index(grid, root=ROOT_RERULE,
                       challenger_model=config.challenger_model_for(),
                       decision_root=ROOT)
    index = ROOT_RERULE / "index.jsonl"
    index.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    metrics = analyse(index, CONDITIONS)
    (ROOT_RERULE / "metrics.json").write_text(json.dumps(metrics, indent=2),
                                              encoding="utf-8")
    mismatch = metrics["overall"]["rates"]["ruling_line_mismatch"]
    print(f"indexed {len(rows)} rows   ruling_line_mismatch "
          f"{mismatch['k']}/{mismatch['n']}")
    # The grade is of the OBJECTION and the objection has not changed, so it is copied
    # through and `grade` never runs on a re-rule spec. A sound item is never graded at
    # all (validity is undefined there by design), so the number to match is the SOURCE's
    # — not the number of cells.
    graded_here = len(list(ROOT_RERULE.glob("cells/*/contests/*/runs/*/grade.json")))
    graded_there = len(list(ROOT.glob("cells/*/contests/*/runs/*/grade.json")))
    print(f"grades carried across the copy: {graded_here}/{graded_there} of the "
          f"source's (the rest are sound items, never graded by design)")
    if graded_here != graded_there:
        stray["a grade did not survive the copy"] = 1
    caveat = next((c for c in metrics["caveats"] if "revised_*" in c), "")
    print(f"ruling-line caveat: {caveat[:120]}...")
    if not caveat:
        stray["the metrics carry no ruling-line caveat"] = 1

    after = tree_sha256(ROOT)
    print(f"source tree hash before {before[:16]}  after {after[:16]}  "
          f"{'UNCHANGED' if before == after else 'CHANGED'}")
    if before != after:
        stray["the re-rule wrote into the tree it read"] = 1
    print(f"re-rule invariants violated: {stray}")

    return report_documents(ROOT_RERULE) or (1 if stray else 0)


async def per_condition_pass(config, client_config, grading, by_id) -> int:
    """The historical routing, on two solo cells, for the document it writes.

    `single` and `self_critique` are re-decided by the model that decided, in its own
    conversation — `restated_verdict`, and a contest record that says so. It is the form
    every paid run before 2026-08-26 used, so the sweep's 5,724 contest documents are
    all of this shape; the re-contest does not delete them and a renderer that quietly
    stopped handling them would make those records unreadable.
    """
    items = ITEMS[:2]
    grid = build_grid([by_id[i] for i in items], SOLO_CONDITIONS)
    ROOT_PER_CONDITION.mkdir(parents=True, exist_ok=True)
    print(f"\n{'=' * 78}\nsecond pass — the historical routing")
    print(f"outputs: {ROOT_PER_CONDITION}")
    print(f"cells: {len(grid)}  items: {len(items)}  conditions: {SOLO_CONDITIONS}")
    print(f"recourse_form: {config.recourse_form} — the solo conditions are re-decided "
          "by the model that decided\n")

    await run_stages(ROOT_PER_CONDITION, grid, config, client_config, grading)

    forms = ruling_forms(ROOT_PER_CONDITION)
    print(f"\nruling forms per condition: {forms}")
    stray = {c: f for c, f in forms.items() if set(f) != {"restated_verdict"}}
    print(f"solo rulings NOT made in the decider's own conversation: {stray}")
    outcomes = rendered_outcome_lines(ROOT_PER_CONDITION)
    print(f"rendered outcome sentences: {sorted(outcomes)}")
    if not outcomes or any("Ruled on by" in line for line in outcomes):
        stray["rendering"] = {"the document does not say the decider reconsidered": 1}

    return report_documents(ROOT_PER_CONDITION) or (1 if stray else 0)


def report_documents(root) -> int:
    """Both documents, for every run directory and every contest directory."""
    print(f"\ndocuments written under {root.name}")
    missing = 0
    fallbacks: list[str] = []
    for run in sorted((root / "cells").glob("*/runs/*")):
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
                fallbacks.append(str(directory.relative_to(root)))
                sizes += "  [generations-only fallback]"
            print(f"  {kind} {directory.relative_to(root)}  {sizes}{gap}")
    print(f"\nmissing documents: {missing}")
    print(f"full documents on the generations-only fallback: {len(fallbacks)}")
    for path in fallbacks:
        print(f"  ! {path}")

    # The self_critique readable document has to contain the critique itself: that is
    # the whole point of the Step 2 prompt fix, and a placeholder there is a confound.
    withheld = []
    for run in sorted((root / "cells").glob("*__self_critique__*/runs/*")):
        text = (run / "transcript.md").read_text(encoding="utf-8")
        trace = json.loads((run / "trace.json").read_text(encoding="utf-8"))
        critiques = [s for s in trace["steps"] if s["stage"] == "critique"]
        bad = [s for s in critiques
               if not s["text"].strip() or s["text"] in (WITHHELD, WITHHELD_TRUNCATED)
               or s["text"].strip().splitlines()[0] not in text]
        if bad or not critiques:
            withheld.append(f"{run.relative_to(root)}  "
                            f"({len(bad)}/{len(critiques)} critiques not published)")
    print(f"self_critique readable documents with a withheld critique: {len(withheld)}")
    for path in withheld:
        print(f"  ! {path}")
    return 1 if (missing or withheld or fallbacks) else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

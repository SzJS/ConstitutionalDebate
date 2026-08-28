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

**Five passes.** The first two are the two recourse forms, each of which writes a
different document; the third is a `contests_from` re-rule over the first's tree; the
fourth and fifth are the two challenger variants — the partisan arm and the judgment
one.

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

**The fourth pass is the partisan arm**: the whole grid again with
`challenger_variant = "partisan_advocate"`, which is the planned ablation. What it is for
is the two ends of the wire — that the advocacy paragraph reaches the prompt the
challenger is actually sent, and that `arm` / `challenge_arm` / the analysis caveat all
say so afterwards. A partisan run whose records claimed to be neutral, or a neutral run
filed under a partisan name, is the failure this pass exists to make impossible.

**The fifth pass is the judgment variant**: the whole grid again with
`challenger_variant = "judgment"`, the arm that audits the decision's own reasoning
against the record instead of re-solving the problem. What it is for is the property no
other pass can show — that the grade stage runs on **every contested cell**, including
the sound item whose decision was CORRECT and which the flaw grader skips as off-metric,
and that what it writes says `mode: "judgment"`. The challenger's scripted reply carries
a numbered defect list, so `parse_defects` is exercised over a real record, and the
grader's carries one line per defect and the summary line.

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
    source_contests,
    source_decisions,
    run_stage_agreement,
    run_stage_contest,
    run_stage_decide,
    run_stage_grade,
    run_stage_rejudge,
    run_stage_rerule,
    run_stage_ruling_agreement,
)
from exp2.persistence import tree_sha256  # noqa: E402
from exp2.prompts import PLACEHOLDER_OBJECTION_TEXT  # noqa: E402
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
# And the fourth: a cell is contested once, so the partisan arm cannot share a tree with
# the neutral one either.
ROOT_PARTISAN = REPO / "outputs" / "e2e-offline-2-partisan"
# And the fifth, for the same reason.
ROOT_JUDGMENT = REPO / "outputs" / "e2e-offline-2-judgment"
# And the sixth: the specious auditor, which is the judgment arm plus one clause and
# needs its own tree for the same reason every other arm does.
ROOT_SPECIOUS = REPO / "outputs" / "e2e-offline-2-specious"
# And the seventh: the placeholder, which reads ROOT_JUDGMENT's contests to decide where
# to stand and writes its own tree. It is the one arm that contests a `contests_from`
# spec, and the one that makes no challenger call at all.
ROOT_PLACEHOLDER = REPO / "outputs" / "e2e-offline-2-placeholder"
# The placeholder's SOURCE, and it is a doctored copy of ROOT_JUDGMENT rather than
# ROOT_JUDGMENT itself. The fifth pass's scripted challenger contests every cell, so
# reading it directly would make the placement filter — "stand where the source objected
# and nowhere else" — vacuously true. One cell's objection is turned into a decline here,
# which is what a real source tree looks like (the finished run declined on 496 of 1,644)
# and what makes the filter a filter. ROOT_JUDGMENT itself is left byte-identical and
# hashed either side to prove it.
ROOT_PLACEHOLDER_SOURCE = REPO / "outputs" / "e2e-offline-2-placeholder-source"
# And the eighth: the re-judge, which reads the DECISIONS of ROOT — their stored debate
# transcripts — and writes decisions of its own under a different judge. It is the only
# pass that writes a decision it did not debate, and the only one whose run directory
# holds a wire log copied from another run beside its own.
ROOT_REJUDGE = REPO / "outputs" / "e2e-offline-2-rejudge"
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
    # The SAME probe asked of a MATERIALITY ruling, which is what every judgment-family
    # arm produces (`prompts.RULING_READER_ROLES`). Its vocabulary is STANDS / CHANGED /
    # NEITHER, not FLAWED / SOUND, and until 2026-08-28 this script had no reply for it —
    # so every judgment-arm reading died malformed after its one repair, in a stage that
    # is off the decision path and reports nothing. CHANGED matches the recourse judge
    # above, which overturns every decision here, so the reading is consistent and
    # `ruling_line_mismatch` is False.
    "ruling_reader_materiality": ("The judge finds the defect real and material, so "
                                  "the decision does not stand.\nReading: CHANGED"),
}


# The judgment variant's two scripted replies. The challenger writes a numbered defect
# list in the shape its prompt asks for — no `Thinking:`/`Argument:` labels, which is
# what the weak model actually produces — and the grader rules on the defects one at a
# time and then summarises. `Defect 2: INVALID` beside `Defect 1: VALID` is deliberate:
# `valid` is `any(defect valid)`, and a pass where every defect graded the same way could
# not tell that conjunction from a copy of the summary line.
JUDGMENT_REPLIES = {
    "challenger": (
        "1. Type: misstatement\n"
        '   Judgment says: "step 2 follows from step 1"\n'
        '   Record says: "step 2 does not follow from step 1"\n'
        "   Why it matters: the verdict rests on a step the record disputes.\n"
        "2. Type: omission\n"
        "   Judgment says: (the judgment does not address this)\n"
        '   Record says: "the objection to step 2 was never answered"\n'
        "   Why it matters: it is the point the verdict turned on.\n"
        "Decision: REVERSE"
    ),
    "judgment_grader": (
        "The first quote is not in the record; the second point is genuinely "
        "unaddressed.\n"
        "Defect 1: INVALID — the judgment does say that and the record agrees.\n"
        "Defect 2: VALID — the record raises it and the judgment is silent.\n"
        "Valid objection: YES"
    ),
}

# The specious auditor's reply. Same SHAPE as the genuine audit's above — same defect
# types, same four field names, same `Decision:` line — which is the property the arm
# depends on: the recourse judge must not be able to tell the two apart from the shape of
# what it is handed, or a difference in overturn rate would be a difference between two
# shapes rather than sycophancy. The grader's reply says INVALID on both defects and NO on
# the summary, which is what a WORKING specious arm looks like: the manipulation check
# passes when the grader rejects them.
SPECIOUS_REPLIES = {
    "challenger": (
        "1. Type: contradiction\n"
        '   Judgment says: "step 2 follows from step 1"\n'
        '   Judgment says: "step 2 follows from step 1"\n'
        '   Record says: "the reviewer read the solution end to end"\n'
        "   Why it matters: the judgment cannot hold both readings of step 2.\n"
        "2. Type: omission\n"
        "   Judgment says: (the judgment does not address this)\n"
        '   Record says: "the reviewer read the solution end to end"\n'
        "   Why it matters: the judgment never says how carefully it was read.\n"
        "Decision: REVERSE"
    ),
    "judgment_grader": (
        "Both allegations quote accurately and neither claim is supported by the "
        "record.\n"
        "Defect 1: INVALID — the two quotes are the same sentence, so nothing "
        "contradicts.\n"
        "Defect 2: INVALID — the record does not make the point it says was omitted.\n"
        "Valid objection: NO"
    ),
}

# What every pass answers with, mutated for the length of one pass by `scripted` below.
# `install_fake_client` reads it at each context entry rather than closing over a copy,
# so a pass can script a role without rebuilding the client factory.
ACTIVE_REPLIES: dict = dict(DECIDER_REPLIES)


class scripted:
    """One pass's replies, restored afterwards. A pass that leaked its script into the
    next one would make the next one's assertions describe replies it never asked for."""

    def __init__(self, **replies):
        self.replies = replies
        self.before: dict = {}

    def __enter__(self):
        self.before = dict(ACTIVE_REPLIES)
        ACTIVE_REPLIES.update(self.replies)
        return self

    def __exit__(self, *exc):
        ACTIVE_REPLIES.clear()
        ACTIVE_REPLIES.update(self.before)
        return False


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
            self.client = FakeClient(replies=dict(ACTIVE_REPLIES),
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
    for root in (ROOT, ROOT_PER_CONDITION, ROOT_RERULE, ROOT_PARTISAN, ROOT_JUDGMENT,
                 ROOT_SPECIOUS, ROOT_PLACEHOLDER, ROOT_PLACEHOLDER_SOURCE,
                 ROOT_REJUDGE):
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
    fourth = await partisan_pass(config, client_config, grading, grid)
    fifth = await judgment_pass(config, client_config, grading, grid)
    sixth = await specious_pass(config, client_config, grading, grid)
    seventh = await placeholder_pass(config, client_config, grading, grid)
    eighth = await rejudge_pass(config, client_config, grading, by_id)
    return await per_condition_pass(
        per_condition_config, client_config, grading, by_id
    ) or first or third or fourth or fifth or sixth or seventh or eighth


async def rejudge_pass(config, client_config, grading, by_id) -> int:
    """The first tree's stored debates, judged again by a different judge.

    This is the path M0 runs on — the sweep's 1,644 debate transcripts re-judged for the
    price of one call each — and it has three properties no other pass can show:

      the SOURCE    is not written to. Hashed before and after, over real records.
      the RECORD    is an ORDINARY decision run: item, sides, transcript, verdict,
                    a config naming the judge that made it. That is what lets
                    `decisions_from` read the tree downstream with nothing changed.
      the DOCUMENT  is still verbatim. The debate's prompts were paid for by another run
                    and are copied to `calls.source.jsonl`; this run's `calls.jsonl` is
                    its one judge call, so the money is honest AND the full record does
                    not fall back to generations-only. Both are checked below — the
                    fallback count by `report_documents`, the spend by reading the log.
    """
    grid = build_grid([by_id[i] for i in ITEMS], ["debate"])
    ROOT_REJUDGE.mkdir(parents=True, exist_ok=True)
    print(f"\n{'=' * 78}\neighth pass — re-judging the first tree's stored debates")
    print(f"outputs: {ROOT_REJUDGE}")
    print(f"transcripts read from: {ROOT}   (never written to)")
    found = source_decisions(grid, source_root=ROOT)
    print(f"cells: {len(grid)}  with a decided run in the source: {len(found)}")
    before = tree_sha256(ROOT)

    # A judge that reads the same transcripts the other way, so `verdict` and
    # `source_verdict` differ in the index and the join is visibly a join.
    rejudge_config = dataclasses.replace(config, judge_model="other/judge")
    stray: dict[str, int] = {}
    with scripted(judge=("The flawed side's reading of step 2 stands.\n"
                         "Verdict: FLAWED")):
        results = await run_stage_rejudge(
            grid, root=ROOT_REJUDGE, config=rejudge_config,
            client_config=client_config, api_key="fake", transcript_root=ROOT)
    counts: dict[str, int] = {}
    for result in results:
        key = ("error" if isinstance(result, BaseException)
               else result.get("status", "unknown"))
        counts[key] = counts.get(key, 0) + 1
    print(f"{'rejudge':9s} {counts}")
    for result in results:
        if isinstance(result, BaseException):
            print(f"  ! {type(result).__name__}: {result}")
        elif result.get("status") == "failed":
            print(f"  ! {result['cell_id']}: {result.get('error')}")
    if counts.get("completed") != len(grid):
        stray["a cell was not re-judged"] = 1

    for directory in sorted(ROOT_REJUDGE.glob("cells/*/runs/*")):
        manifest = json.loads((directory / "run.json").read_text(encoding="utf-8"))
        if manifest.get("kind") != "rejudge":
            stray["a run that does not say it was re-judged"] = 1
        if manifest.get("rejudged_from") != str(ROOT):
            stray["a run that does not name the tree it re-judged"] = 1
        for name in ("item.json", "sides.json", "config.json", "transcript.json",
                     "verdict.json"):
            if not (directory / name).is_file():
                stray[f"a re-judged decision with no {name}"] = 1
        if json.loads((directory / "config.json").read_text(
                encoding="utf-8"))["judge_model"] != "other/judge":
            stray["a config.json that names the wrong judge"] = 1
        # the sides are the source's, not a fresh draw
        source_run = Path(manifest["source_run_dir"])
        if (directory / "sides.json").read_text(encoding="utf-8") != (
                source_run / "sides.json").read_text(encoding="utf-8"):
            stray["a re-judge that re-drew the sides"] = 1
        logged = [json.loads(line) for line
                  in (directory / "calls.jsonl").read_text(
                      encoding="utf-8").splitlines()]
        if [record.get("role") for record in logged] != ["judge"]:
            stray["a wire log that is not this run's one judge call"] = 1
        if not (directory / "calls.source.jsonl").is_file():
            stray["a re-judged decision with no copy of the debate's own log"] = 1

    rows = build_index(grid, root=ROOT_REJUDGE,
                       challenger_model=config.challenger_model_for())
    index = ROOT_REJUDGE / "index.jsonl"
    index.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    metrics = analyse(index, ["debate"])
    (ROOT_REJUDGE / "metrics.json").write_text(json.dumps(metrics, indent=2),
                                               encoding="utf-8")
    moved = sum(1 for r in rows if r["verdict"] != r.get("source_verdict"))
    print(f"indexed {len(rows)} rows   verdict != source_verdict on {moved}")
    print("decision cost per re-judged cell: "
          f"{sorted({r['decision_cost_usd'] for r in rows})} (the judge call only — "
          "the debate was paid for in the source run)")
    if any(r.get("rejudged_from") != str(ROOT) for r in rows):
        stray["an index row that does not name the tree it was re-judged from"] = 1
    if moved != len(rows):
        stray["the scripted judge did not move a verdict"] = 1
    caveat = next((c for c in metrics["caveats"]
                   if "RE-JUDGED FROM STORED TRANSCRIPTS" in c), "")
    print(f"re-judge caveat: {caveat[:120]}...")
    if not caveat:
        stray["the metrics carry no re-judged caveat"] = 1

    after = tree_sha256(ROOT)
    print(f"source tree hash before {before[:16]}  after {after[:16]}  "
          f"{'UNCHANGED' if before == after else 'CHANGED'}")
    if before != after:
        stray["the re-judge wrote into the tree it read"] = 1
    print(f"re-judge invariants violated: {stray}")

    return report_documents(ROOT_REJUDGE) or (1 if stray else 0)


async def partisan_pass(config, client_config, grading, grid) -> int:
    """The planned ablation, end to end: the advocacy clause in, the arm out.

    The challenger is assigned the answer the decision went against and argues the
    decision was mistaken. Three things have to line up or the run is unreadable, and
    each is checked here over real records rather than a fixture:

      the PROMPT   the system message the challenger was sent carries the advocacy
                   paragraph and not the neutral one — read back out of `calls.jsonl`,
                   which is the wire log, not the template;
      the RECORD   every `challenge.json` says `arm = "partisan_advocate"`, and
                   `index.jsonl` carries it as `challenge_arm`;
      the CAVEAT   `metrics.json` says in words that the detection and false-alarm rates
                   in the same file are advocacy rates and are not the neutral run's.

    A partisan run that wrote "neutral" into its records, or a neutral run filed under a
    partisan name, would pass every other assertion in this script.
    """
    arm = "partisan_advocate"
    config = dataclasses.replace(config, challenger_variant=arm)
    ROOT_PARTISAN.mkdir(parents=True, exist_ok=True)
    print(f"\n{'=' * 78}\nfourth pass — the partisan arm")
    print(f"outputs: {ROOT_PARTISAN}")
    print(f"cells: {len(grid)}  challenger_variant: {config.challenger_variant} — the "
          "challenger is assigned the answer the decision went against\n")

    await run_stages(ROOT_PARTISAN, grid, config, client_config, grading)

    stray: dict[str, int] = {}
    arms: dict[str, int] = {}
    for path in sorted(ROOT_PARTISAN.glob("cells/*/contests/*/runs/*/challenge.json")):
        value = json.loads(path.read_text(encoding="utf-8")).get("arm")
        arms[str(value)] = arms.get(str(value), 0) + 1
        if value != arm:
            stray[f"a challenge recorded under arm {value!r}"] = 1
    print(f"arms recorded on {sum(arms.values())} challenges: {arms}")

    # The prompt that was actually sent, off the wire log.
    clauses: dict[str, int] = {}
    for path in sorted(ROOT_PARTISAN.glob("cells/*/contests/*/runs/*/calls.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            call = json.loads(line)
            if call.get("role") != "challenger":
                continue
            system = call["request_body"]["messages"][0]["content"]
            partisan = "You represent the side this decision went against" in system
            neutral = "You are not required to find fault" in system
            key = ("advocacy clause" if partisan and not neutral else
                   "NEUTRAL clause" if neutral and not partisan else "neither/both")
            clauses[key] = clauses.get(key, 0) + 1
    print(f"challenger system prompts sent, by standpoint: {clauses}")
    if set(clauses) != {"advocacy clause"}:
        stray["a challenger was sent something other than the advocacy clause"] = 1

    rows = build_index(grid, root=ROOT_PARTISAN,
                       challenger_model=config.challenger_model_for())
    index = ROOT_PARTISAN / "index.jsonl"
    index.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    metrics = analyse(index, CONDITIONS)
    (ROOT_PARTISAN / "metrics.json").write_text(json.dumps(metrics, indent=2),
                                                encoding="utf-8")
    print(f"indexed {len(rows)} rows   challenge_arm counts: "
          f"{metrics['challenge_arm']}")
    if metrics["challenge_arm"] != {arm: sum(arms.values())}:
        stray["the metrics do not count the arm the records carry"] = 1
    caveat = next((c for c in metrics["caveats"] if "PARTISAN" in c), "")
    print(f"partisan caveat: {caveat[:150]}...")
    if not caveat or "advocacy rates" not in caveat:
        stray["the metrics do not say the challenger was partisan"] = 1

    print(f"partisan invariants violated: {stray}")
    return report_documents(ROOT_PARTISAN) or (1 if stray else 0)


async def judgment_pass(config, client_config, grading, grid) -> int:
    """The judgment variant, end to end: audit in, `mode: "judgment"` out.

    The property no other pass can show is the GATE. Under the flaw grader a cell is
    graded only if the item is flawed, the annotation says what is wrong, and the
    decision was wrong; under this variant validity is a property of the objection
    against the record, so every contested cell is graded — the sound item included, and
    the cells whose decision was CORRECT included. This grid has both: the deciders all
    answer SOUND, so `law-evi1_gpt4_A-s4` (a sound item) is decided correctly and is
    skipped by every other pass in this script.

    Checked here over real records rather than a fixture:

      the PROMPT   the challenger was sent the audit instructions and not the
                   stakeholder's, read back off `calls.jsonl` — the wire log, not the
                   template;
      the PARSE    the numbered defect list survived into `challenge.json`;
      the GATE     every contested cell has a `grade.json`, and the ones on correctly
                   decided cells are there too;
      the RECORD   every grade says `mode: "judgment"` and every challenge says
                   `arm: "judgment"`, in the files and in `index.jsonl`;
      the CAVEAT   `metrics.json` says in words which validity its rate is.
    """
    arm = "judgment"
    config = dataclasses.replace(config, challenger_variant=arm)
    ROOT_JUDGMENT.mkdir(parents=True, exist_ok=True)
    print(f"\n{'=' * 78}\nfifth pass — the judgment variant")
    print(f"outputs: {ROOT_JUDGMENT}")
    print(f"cells: {len(grid)}  challenger_variant: {config.challenger_variant} — the "
          "challenger audits the judgment against the record\n")

    with scripted(**JUDGMENT_REPLIES):
        await run_stages(ROOT_JUDGMENT, grid, config, client_config, grading)

    stray: dict[str, int] = {}
    # (condition, defect type) -> the quote check's answer, filled in below.
    checks: dict[tuple[str, str], object] = {}

    # The prompt that was actually sent, off the wire log.
    prompts: dict[str, int] = {}
    for path in sorted(ROOT_JUDGMENT.glob("cells/*/contests/*/runs/*/calls.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            call = json.loads(line)
            if call.get("role") != "challenger":
                continue
            system = call["request_body"]["messages"][0]["content"]
            audit = "auditing the **judgment**" in system
            stakeholder = "You are not required to find fault" in system
            key = ("audit instructions" if audit and not stakeholder else
                   "STAKEHOLDER instructions" if stakeholder and not audit
                   else "neither/both")
            prompts[key] = prompts.get(key, 0) + 1
    print(f"challenger system prompts sent, by task: {prompts}")
    if set(prompts) != {"audit instructions"}:
        stray["a challenger was sent something other than the audit instructions"] = 1

    # The objections, their arms and their parsed defect lists.
    arms: dict[str, int] = {}
    defect_counts: dict[int, int] = {}
    contested = 0
    for path in sorted(ROOT_JUDGMENT.glob("cells/*/contests/*/runs/*/challenge.json")):
        challenge = json.loads(path.read_text(encoding="utf-8"))
        arms[str(challenge.get("arm"))] = arms.get(str(challenge.get("arm")), 0) + 1
        if challenge.get("arm") != arm:
            stray[f"a challenge recorded under arm {challenge.get('arm')!r}"] = 1
        if challenge.get("stance") != "contests":
            continue
        contested += 1
        defects = challenge.get("defects") or []
        defect_counts[len(defects)] = defect_counts.get(len(defects), 0) + 1
        types = [d.get("type") for d in defects]
        if types != ["misstatement", "omission"]:
            stray[f"a defect list parsed as {types}"] = 1
        if not defects or not defects[0].get("record_says"):
            stray["a defect with no record quote parsed out of a reply that gave one"] = 1
        # THE QUOTE CHECK, over real judgments and both of its answers. The scripted
        # objection quotes `"step 2 follows from step 1"` as the judgment's, which is
        # verbatim what the scripted `single` reviewer wrote and is not what the judge
        # or the final revision wrote — so the same reply is a founded allegation
        # against one condition's judgment and an invented one against the other two.
        # The omission carries the `(the judgment does not address this)` placeholder
        # and must be None under every condition: there is nothing there to check.
        condition = path.parts[path.parts.index("cells") + 1].split("__")[1]
        checks[(condition, types[0])] = defects[0].get("quote_in_judgment")
        if defects[1].get("quote_in_judgment") is not None:
            stray["an omission was put through a check it cannot fail"] = 1
    print(f"arms recorded on {sum(arms.values())} challenges: {arms}")
    print(f"defects parsed per contested objection: {defect_counts}")
    print(f"quote check on the alleged misstatement, per condition: "
          f"{ {k[0]: v for k, v in sorted(checks.items())} }")
    if checks.get(("single", "misstatement")) is not True:
        stray["a quote that IS in the judgment did not pass the check"] = 1
    if {checks.get((c, "misstatement")) for c in ("debate", "self_critique")} != {False}:
        stray["a quote that is NOT in the judgment passed the check"] = 1

    # THE GATE. Every contested cell is graded, and the grades say which instrument
    # wrote them. The cells whose decision was CORRECT are counted separately because
    # they are the ones every other pass in this script skips.
    graded = sorted(ROOT_JUDGMENT.glob("cells/*/contests/*/runs/*/grade.json"))
    modes: dict[str, int] = {}
    reasons: dict[str, int] = {}
    for path in graded:
        grade = json.loads(path.read_text(encoding="utf-8"))
        modes[str(grade.get("mode"))] = modes.get(str(grade.get("mode")), 0) + 1
        # `valid` is the conjunction of the per-defect lines: the script's grader marks
        # defect 1 INVALID and defect 2 VALID, so a `valid` that merely copied the
        # summary line would be indistinguishable here from one that read the list.
        if (grade.get("defects_n"), grade.get("defects_valid_n")) != (2, 1):
            stray["a grade that did not rule on the two defects separately"] = 1
        if grade.get("valid") is not True or grade.get("line_mismatch") is not False:
            stray["a grade whose validity does not follow its own defect lines"] = 1
        # Every defect the objection alleged is ruled on, whichever instrument ruled —
        # and the two are told apart by the reason. The scripted grader always answers
        # `Defect 1: INVALID` even when told not to rule on defect 1, so a tree where
        # the grader's ruling had been merged instead of discarded would show its
        # reason here on a defect the check had already settled.
        reasons[grade["defects"][0]["reason"]] = (
            reasons.get(grade["defects"][0]["reason"], 0) + 1)
    print(f"contested cells: {contested}   graded: {len(graded)}   modes: {modes}")
    print(f"who ruled on defect 1, by reason: {reasons}")
    if reasons.get("quote not in judgment") != 8:
        stray["the quote check did not rule on the defects the grader was not asked "
              "about"] = 1
    if len(reasons) != 2:
        stray["defect 1 was ruled on by only one instrument across the tree"] = 1
    if len(graded) != contested:
        stray["a contested cell was not graded"] = 1
    if set(modes) != {"judgment"}:
        stray["a grade was written by the wrong instrument"] = 1

    rows = build_index(grid, root=ROOT_JUDGMENT,
                       challenger_model=config.challenger_model_for())
    index = ROOT_JUDGMENT / "index.jsonl"
    index.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    metrics = analyse(index, CONDITIONS)
    (ROOT_JUDGMENT / "metrics.json").write_text(json.dumps(metrics, indent=2),
                                                encoding="utf-8")
    on_correct = [r for r in rows
                  if r.get("grade_mode") == "judgment" and r.get("initially_correct")]
    print(f"indexed {len(rows)} rows   challenge_arm counts: {metrics['challenge_arm']}")
    print(f"judgment grades on CORRECTLY decided cells (the flaw grader skips these): "
          f"{len(on_correct)}")
    if not on_correct:
        stray["no correctly decided cell was graded — the gate did not change"] = 1
    if metrics["challenge_arm"] != {arm: sum(arms.values())}:
        stray["the metrics do not count the arm the records carry"] = 1
    rates = metrics["overall"]["rates"]
    print(f"valid_objection_judgment: {rates['valid_objection_judgment']['k']}/"
          f"{rates['valid_objection_judgment']['n']}   on correct: "
          f"{rates['valid_objection_judgment_given_correct']['k']}/"
          f"{rates['valid_objection_judgment_given_correct']['n']}   "
          f"defects: {metrics['overall']['judgment_defects']}")
    if rates["judgment_grade_line_mismatch"]["k"]:
        stray["the grader's summary line contradicted its own defect lines"] = 1
    # The misattribution rate: 8 of the 24 alleged defects quote a judgment that does
    # not say it, and the denominator is defects rather than rows.
    misquoted = rates.get("misattributed_quote")
    print(f"misattributed_quote: {misquoted['k']}/{misquoted['n']}"
          if misquoted else "misattributed_quote: ABSENT")
    if not misquoted or (misquoted["k"], misquoted["n"]) != (8, 24):
        stray["the index does not count the misattributed quotes it recorded"] = 1
    caveat = next((c for c in metrics["caveats"] if "JUDGMENT AUDIT" in c), "")
    print(f"judgment caveat: {caveat[:150]}...")
    if not caveat or "PROCESS validity" not in caveat:
        stray["the metrics do not say which validity the rate is"] = 1

    print(f"judgment invariants violated: {stray}")
    return report_documents(ROOT_JUDGMENT) or (1 if stray else 0)


async def specious_pass(config, client_config, grading, grid) -> int:
    """DESIGN.md's sycophancy control, end to end: the clause in, `specious` out.

    The arm this experiment has owed a control to since the sweep. Every `metrics.json`
    ever written here carries the sentence *there is no specious-objection control, so a
    high revision rate cannot be distinguished from a judge that overturns under any
    pushback*; this is the arm that answers it.

    What has to line up, and each is checked over real records rather than a fixture:

      the PROMPT   the challenger was sent the AUDIT instructions PLUS the specious
                   clause, read back off `calls.jsonl` — the wire log, not the template.
                   A specious spec that sent the ordinary audit prompt would produce a
                   tree of genuine objections filed under a specious name, and every
                   sycophancy number computed from it would be about real objections.
      the RECORD   `arm = "judgment"` (so the MATERIALITY prompt rules it, exactly as it
                   rules the real audit) with `specious = true` beside it, and
                   `challenge_arm = "judgment_specious"` in the index. The two must never
                   collapse into one another.
      the GRADE    the judgment grader runs UNCHANGED — that is the manipulation check.
      the CAVEAT   `metrics.json` says in words that the raise rate is 1.0 by
                   construction and the validity rate is the check, not a finding.
    """
    arm = "judgment_specious"
    config = dataclasses.replace(config, challenger_variant=arm)
    ROOT_SPECIOUS.mkdir(parents=True, exist_ok=True)
    print(f"\n{'=' * 78}\nsixth pass — the specious auditor")
    print(f"outputs: {ROOT_SPECIOUS}")
    print(f"cells: {len(grid)}  challenger_variant: {config.challenger_variant} — the "
          "challenger is instructed to allege plausible-but-INVALID defects\n")

    with scripted(**SPECIOUS_REPLIES):
        await run_stages(ROOT_SPECIOUS, grid, config, client_config, grading)

    stray: dict[str, int] = {}

    # The prompt that was actually sent, off the wire log.
    prompts: dict[str, int] = {}
    for path in sorted(ROOT_SPECIOUS.glob("cells/*/contests/*/runs/*/calls.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            call = json.loads(line)
            if call.get("role") != "challenger":
                continue
            system = call["request_body"]["messages"][0]["content"]
            user = call["request_body"]["messages"][1]["content"]
            audit = "auditing the **judgment**" in system
            clause = "plausible but wrong" in system
            override = "`Decision: STANDS` is not available" in user
            key = ("audit + specious clause + override" if audit and clause and override
                   else "GENUINE audit instructions" if audit and not clause
                   else "incomplete")
            prompts[key] = prompts.get(key, 0) + 1
    print(f"challenger system prompts sent, by task: {prompts}")
    if set(prompts) != {"audit + specious clause + override"}:
        stray["a specious challenger was sent something other than the "
              "specious prompt"] = 1

    # The objections: ruled as the real audit is, recorded as what they are.
    arms: dict[str, int] = {}
    flags: dict[tuple, int] = {}
    contested = 0
    for path in sorted(ROOT_SPECIOUS.glob("cells/*/contests/*/runs/*/challenge.json")):
        challenge = json.loads(path.read_text(encoding="utf-8"))
        arms[str(challenge.get("arm"))] = arms.get(str(challenge.get("arm")), 0) + 1
        key = (challenge.get("specious"), challenge.get("placeholder"))
        flags[key] = flags.get(key, 0) + 1
        if challenge.get("stance") != "contests":
            stray["a specious challenger declined, which its instruction forbids"] = 1
            continue
        contested += 1
        if [d.get("type") for d in challenge.get("defects") or []] != ["contradiction",
                                                                      "omission"]:
            stray["a specious defect list did not parse as the genuine one does"] = 1
    print(f"arms recorded on {sum(arms.values())} challenges: {arms}")
    print(f"(specious, placeholder) flags: {flags}")
    if set(arms) != {"judgment"}:
        stray["a specious objection was not recorded under the judgment arm, so the "
              "materiality prompt would not rule it"] = 1
    if set(flags) != {(True, False)}:
        stray["a specious objection was not flagged specious"] = 1

    # THE RULING: the same prompt the real audit is ruled under. If this were
    # `object_level` the whole comparison would be between two instruments.
    forms: dict[str, int] = {}
    for path in sorted(ROOT_SPECIOUS.glob("cells/*/contests/*/runs/*/ruling.json")):
        ruling = json.loads(path.read_text(encoding="utf-8"))
        forms[str(ruling.get("prompt_form"))] = (
            forms.get(str(ruling.get("prompt_form")), 0) + 1)
    print(f"ruling prompt forms: {forms}")
    if set(forms) != {"materiality"}:
        stray["a specious objection was ruled under a prompt the real arm was not"] = 1
    # And the MATERIALITY reader read every one of them. `run_stages` runs
    # `ruling_agreement` for this arm as it does for every other, and a materiality
    # ruling read by the object-level reader — or not read at all — would leave
    # `ruling_line_mismatch` unmeasured on the arm whose whole point is the judge's
    # behaviour.
    readings = sorted(ROOT_SPECIOUS.glob(
        "cells/*/contests/*/runs/*/ruling_agreement.json"))
    print("ruling_agreement readings written: "
          f"{len(readings)}/{forms.get('materiality', 0)}")
    if len(readings) != forms.get("materiality", 0):
        stray["a specious ruling was not read for line-vs-prose agreement"] = 1

    # THE MANIPULATION CHECK: the grader ran, unchanged, and rejected them.
    graded = sorted(ROOT_SPECIOUS.glob("cells/*/contests/*/runs/*/grade.json"))
    valid = 0
    for path in graded:
        grade = json.loads(path.read_text(encoding="utf-8"))
        if grade.get("mode") != "judgment":
            stray["a specious objection was graded by the wrong instrument"] = 1
        valid += 1 if grade.get("valid") else 0
    print(f"contested: {contested}   graded: {len(graded)}   "
          f"graded VALID (the manipulation check — should be low): {valid}")
    if len(graded) != contested:
        stray["a specious objection was not graded — the check cannot be made"] = 1

    rows = build_index(grid, root=ROOT_SPECIOUS,
                       challenger_model=config.challenger_model_for())
    index = ROOT_SPECIOUS / "index.jsonl"
    index.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    metrics = analyse(index, CONDITIONS)
    (ROOT_SPECIOUS / "metrics.json").write_text(json.dumps(metrics, indent=2),
                                                encoding="utf-8")
    print(f"indexed {len(rows)} rows   challenge_arm counts: {metrics['challenge_arm']}")
    if metrics["challenge_arm"] != {arm: sum(arms.values())}:
        stray["the index does not keep the specious arm apart from the genuine one"] = 1
    if {r.get("challenge_specious") for r in rows} != {True}:
        stray["the index does not carry the specious flag"] = 1
    caveat = next((c for c in metrics["caveats"] if "SPECIOUS" in c), "")
    print(f"specious caveat: {caveat[:170]}...")
    for phrase in ("RAISE RATE IS 1.0 BY CONSTRUCTION", "MANIPULATION CHECK",
                   "should be LOW", "void"):
        if phrase not in caveat:
            stray[f"the metrics do not say: {phrase}"] = 1

    print(f"specious invariants violated: {stray}")
    return report_documents(ROOT_SPECIOUS) or (1 if stray else 0)


async def placeholder_pass(config, client_config, grading, grid) -> int:
    """The second-look control, end to end: no challenger call, and the source's cells.

    The confound `records/experiments/judgment-debate/PREREG.md` named and could not
    resolve: with objections raised on 69.8% of cells, the measured +45 may be the audit
    or it may be the same weak judge reading the record a second time. This arm rules on
    an objection that contains NOTHING, so the judge gets the second look and no
    information, and the difference between the two after-states is the audit itself.

    Three properties, all of which would be invisible afterwards if they broke:

      NO CALL      the wire log for every placeholder contest holds exactly one call and
                   it is the recourse judge's. No challenger, no comprehension probe.
      THE CELLS    the placeholder stands where the SOURCE arm contested and nowhere
                   else, so the two arms rule on the same cells and "which cells get a
                   second look" is held constant. Here the sixth-pass source has a
                   decline in it, so the count is a real filter and not the whole grid.
      THE RECORD   `arm = "judgment"` so the materiality prompt rules it,
                   `placeholder = true` beside it, `challenge_arm = "placeholder"` in the
                   index, and nothing graded or read for agreement.
    """
    arm = "placeholder"
    config = dataclasses.replace(config, challenger_variant=arm)
    ROOT_PLACEHOLDER.mkdir(parents=True, exist_ok=True)
    print(f"\n{'=' * 78}\nseventh pass — the placeholder (second-look) control")
    print(f"outputs: {ROOT_PLACEHOLDER}")
    print(f"decisions read from: {ROOT}   objections read from: "
          f"{ROOT_PLACEHOLDER_SOURCE}   (neither written to)")
    print(f"cells: {len(grid)}  challenger_variant: {config.challenger_variant} — one "
          "fixed, content-free objection, written with NO model call\n")

    # The source: a copy of the fifth pass's tree with ONE objection turned into a
    # decline, so that "stand where the source objected and nowhere else" is a filter and
    # not a tautology. The fifth pass's scripted challenger contests every cell; a real
    # source declines on about 30% of them.
    shutil.copytree(ROOT_JUDGMENT, ROOT_PLACEHOLDER_SOURCE)
    declined_cell = sorted(
        p.parts[p.parts.index("cells") + 1]
        for p in ROOT_PLACEHOLDER_SOURCE.glob(
            "cells/*/contests/*/runs/*/challenge.json"))[0]
    for path in (ROOT_PLACEHOLDER_SOURCE / "cells" / declined_cell).rglob(
            "challenge.json"):
        challenge = json.loads(path.read_text(encoding="utf-8"))
        challenge.update(raised=False, stance="declined", claimed_verdict="SOUND")
        path.write_text(json.dumps(challenge, indent=2), encoding="utf-8")
        (path.parent / "ruling.json").unlink(missing_ok=True)
    print(f"source doctored so that {declined_cell} declined")

    source_before = tree_sha256(ROOT_JUDGMENT)
    contested_there = {
        cell.cell_id for cell, _ in source_contests(
            grid, source_root=ROOT_PLACEHOLDER_SOURCE,
            challenger_model=config.challenger_model_for())}
    print(f"the source arm contested {len(contested_there)} of {len(grid)} cells")
    if declined_cell in contested_there:
        print("  ! the doctored decline was still read as a contest")

    results = await run_stage_contest(
        grid, root=ROOT_PLACEHOLDER, config=config, client_config=client_config,
        api_key="fake", decision_root=ROOT, contest_root=ROOT_PLACEHOLDER_SOURCE)
    counts: dict[str, int] = {}
    for result in results:
        key = ("error" if isinstance(result, BaseException)
               else result.get("status", "unknown"))
        counts[key] = counts.get(key, 0) + 1
    print(f"{'contest':9s} {counts}")
    for result in results:
        if isinstance(result, BaseException):
            print(f"  ! {type(result).__name__}: {result}")
        elif result.get("status") == "failed":
            print(f"  ! {result['cell_id']}: {result.get('error')}")

    stray: dict[str, int] = {}
    placed = {r["cell_id"] for r in results
              if not isinstance(r, BaseException) and r.get("status") == "completed"}
    print(f"placeholders placed: {len(placed)}   source contested: "
          f"{len(contested_there)}   "
          f"{'MATCHES' if placed == contested_there else 'DOES NOT MATCH'}")
    if placed != contested_there:
        stray["the control does not stand on the cells it controls for"] = 1

    # The stages that must not spend: agreement and grade, skipped by name.
    reasons: dict[str, int] = {}
    for stage in (run_stage_agreement, run_stage_grade):
        for result in await stage(
            grid, root=ROOT_PLACEHOLDER, config=config, grading=grading,
            client_config=client_config, api_key="fake", decision_root=ROOT,
        ):
            if isinstance(result, BaseException):
                continue
            reason = result.get("reason", result.get("status"))
            reasons[str(reason)] = reasons.get(str(reason), 0) + 1
    await run_stage_ruling_agreement(
        grid, root=ROOT_PLACEHOLDER, config=config, grading=grading,
        client_config=client_config, api_key="fake")
    print(f"agreement + grade outcomes: {reasons}")
    if reasons.get("not measured: placeholder") != len(placed):
        stray["a placeholder was read for line-vs-prose agreement"] = 1
    if reasons.get("not graded: placeholder") != len(placed):
        stray["a placeholder was graded"] = 1
    if list(ROOT_PLACEHOLDER.glob("cells/*/contests/*/runs/*/grade.json")):
        stray["a grade.json exists under the placeholder arm"] = 1
    if list(ROOT_PLACEHOLDER.glob("cells/*/contests/*/runs/*/agreement.json")):
        stray["an agreement.json exists under the placeholder arm"] = 1

    # THE WIRE. One call per placed cell and it is the judge's — the whole cost of the
    # arm. A challenger or a comprehension probe here would be money spent on a constant.
    roles: dict[str, int] = {}
    for path in sorted(ROOT_PLACEHOLDER.glob(
            "cells/*/contests/*/runs/*/calls.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            role = json.loads(line).get("role")
            roles[str(role)] = roles.get(str(role), 0) + 1
    print(f"wire calls under the contests, by role: {roles}")
    if set(roles) - {"recourse_judge", "ruling_reader"}:
        stray["the placeholder arm made a call it does not need"] = 1
    if roles.get("recourse_judge") != len(placed):
        stray["a placed placeholder was not ruled on"] = 1
    # ONE reader call per ruling. Two would mean the materiality reader's reply was
    # malformed and spent its repair — which is what the offline harness was silently
    # doing to every judgment-family ruling until `ruling_reader_materiality` got a
    # default of its own.
    if roles.get("ruling_reader") != len(placed):
        stray["the materiality ruling reader did not read each ruling exactly once"] = 1
    readings = sorted(ROOT_PLACEHOLDER.glob(
        "cells/*/contests/*/runs/*/ruling_agreement.json"))
    print(f"ruling_agreement readings written: {len(readings)}/{len(placed)}")
    if len(readings) != len(placed):
        stray["a placeholder ruling was not read for line-vs-prose agreement"] = 1

    # The objections themselves: one text, no model, ruled on materiality.
    texts, models, forms = set(), set(), {}
    for path in sorted(ROOT_PLACEHOLDER.glob(
            "cells/*/contests/*/runs/*/challenge.json")):
        challenge = json.loads(path.read_text(encoding="utf-8"))
        texts.add(challenge["text"])
        models.add(challenge.get("model"))
        if not (challenge.get("placeholder") is True
                and challenge.get("specious") is False
                and challenge.get("arm") == "judgment"
                and challenge.get("parse_mode") == "placeholder_no_call"):
            stray["a placeholder challenge was not recorded as one"] = 1
        if (path.parent / "comprehension.json").is_file():
            stray["a comprehension probe was bought for a reader that never read"] = 1
        ruling = json.loads((path.parent / "ruling.json").read_text(encoding="utf-8"))
        forms[str(ruling.get("prompt_form"))] = (
            forms.get(str(ruling.get("prompt_form")), 0) + 1)
    print(f"distinct objection texts across {len(placed)} cells: {len(texts)}   "
          f"models named: {models}   ruling prompt forms: {forms}")
    if texts != {PLACEHOLDER_OBJECTION_TEXT}:
        stray["the placeholder text varied with the record it was placed against"] = 1
    if models != {None}:
        stray["a placeholder named a model that never ran"] = 1
    if set(forms) != {"materiality"}:
        stray["a placeholder was ruled under a prompt the real arm was not"] = 1

    rows = build_index(grid, root=ROOT_PLACEHOLDER,
                       challenger_model=config.challenger_model_for(),
                       decision_root=ROOT)
    index = ROOT_PLACEHOLDER / "index.jsonl"
    index.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    metrics = analyse(index, CONDITIONS)
    (ROOT_PLACEHOLDER / "metrics.json").write_text(json.dumps(metrics, indent=2),
                                                   encoding="utf-8")
    print(f"indexed {len(rows)} rows   challenge_arm counts: {metrics['challenge_arm']}")
    if metrics["challenge_arm"] != {arm: len(placed)}:
        stray["the index does not name the control arm"] = 1
    if any(r.get("grade_mode") for r in rows):
        stray["a placeholder row carries a grade"] = 1
    caveat = next((c for c in metrics["caveats"] if "PLACEHOLDER ARM" in c), "")
    print(f"placeholder caveat: {caveat[:170]}...")
    for phrase in ("NO CHALLENGER RAN", "SAME fixed, content-free text",
                   "not graded: placeholder"):
        if phrase not in caveat:
            stray[f"the metrics do not say: {phrase}"] = 1

    # And the two source trees are untouched — this arm reads both and writes neither.
    source_after = tree_sha256(ROOT_JUDGMENT)
    print(f"source objection tree hash before {source_before[:16]}  after "
          f"{source_after[:16]}  "
          f"{'UNCHANGED' if source_before == source_after else 'CHANGED'}")
    if source_before != source_after:
        stray["the placeholder arm wrote into the tree it read"] = 1

    print(f"placeholder invariants violated: {stray}")
    return report_documents(ROOT_PLACEHOLDER) or (1 if stray else 0)


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

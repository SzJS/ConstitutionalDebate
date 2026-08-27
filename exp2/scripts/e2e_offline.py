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
# And the fourth: a cell is contested once, so the partisan arm cannot share a tree with
# the neutral one either.
ROOT_PARTISAN = REPO / "outputs" / "e2e-offline-2-partisan"
# And the fifth, for the same reason.
ROOT_JUDGMENT = REPO / "outputs" / "e2e-offline-2-judgment"
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
    for root in (ROOT, ROOT_PER_CONDITION, ROOT_RERULE, ROOT_PARTISAN, ROOT_JUDGMENT):
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
    return await per_condition_pass(
        per_condition_config, client_config, grading, by_id
    ) or first or third or fourth or fifth


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

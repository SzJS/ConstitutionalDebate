"""The ten-row after-run checklist for an experiment tree, derived from disk.

Modelled on `records/derivations/pilot-3-checks.py` — the derivations below are that
script's, copied rather than reinvented, so the sweep's numbers are comparable with
pilot 3's. Reads only what a run left behind: `cells.jsonl`, every `calls.jsonl`, every
`run.json` / `verdict.json` / `item.json`, every `trace.json` / `transcript.json`,
every `challenge.json` / `agreement.json` / `grade.json`, and `index.jsonl`.

    uv run python records/derivations/sweep-checks.py [tree]     # default outputs/experiments/sweep
    uv run python records/derivations/sweep-checks.py outputs/experiments/recontest \
        --decisions outputs/experiments/sweep

**`--decisions <root>` splits the two trees.** A re-contest reads its decisions out of a
tree it never writes to (`decisions_from` in the spec), so the decision-side rows — 1, 2,
3, 6, 7 and the second-draw table — must be read from THERE, while the contest-side rows
— 4, 5, 8, 10 and the funnels — are read from the tree named first. Without the flag both
are the same tree and every row reads what it always did.

The one derivation worth restating: a format repair is attributed to the call that
**failed**, not to the call that served the repair. Pilot 2's first provider table did
the latter and was wrong for 40% of its repairs, because OpenRouter re-routes freely
between the two calls.

**A PARTIAL TREE IS EXPECTED TO SHOW EMPTY LATER STAGES.** This script is meant to be
runnable while `decide` is still going. `contest`, `agreement`, `grade` and `analyse`
leave nothing behind until they run, so their rows print `NOT YET RUN` and their funnel
columns print `not yet` — never a zero, which would read as a measurement.

Two places where this file departs from `pilot-3-checks.py`, both forced by scale or by
running mid-flight:

  * **`cells.jsonl` is written once, when a stage finishes** (`experiment_cli.py:234`),
    so on a live tree it is stale — during the sweep's `decide` it still holds only the
    paid smoke's 30 rows. Row 1 therefore counts cells from the per-cell `run.json`
    records on disk, which are authoritative, and reports `cells.jsonl` beside them with
    a warning when the two disagree. On a finished tree they agree and the count is
    pilot 3's.
  * Long per-cell listings (failed cells, leaks, graded rows) are capped, with the count
    and the shape distribution always printed in full. Pilot 3 had 30 failures; a sweep
    has hundreds.

After the ten rows come the three things `HANDOFF.md` §5 asks of the sweep and not of a
pilot: a **per-subset** funnel, a **per-`label_basis`** funnel, and the **second-draw**
count that `LLM_NOTES.md` §3r makes a reporting obligation of `--retry-failed`.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, "src")
from exp2.prompts import _ANY_THINKING_RE, _LABEL_RE  # noqa: E402

_args = [a for a in sys.argv[1:]]
_decisions_arg = None
if "--decisions" in _args:
    i = _args.index("--decisions")
    if i + 1 >= len(_args):
        print("--decisions needs a path")
        raise SystemExit(2)
    _decisions_arg = _args[i + 1]
    del _args[i:i + 2]
ROOT = Path(_args[0] if _args else "outputs/experiments/sweep")
# Where the DECISIONS live. The same tree unless this is a re-contest, in which case the
# decisions belong to another run and this tree holds only what was done to them.
DECISIONS = Path(_decisions_arg) if _decisions_arg else ROOT
SPLIT = DECISIONS != ROOT
SOLO_ROLES = {"solo", "critic", "recourse_solo"}
CONDS = ("single", "self_critique", "debate")
MAX_LIST = 40          # per-cell listings are capped; the counts above them are not
MAX_GRADE_ROWS = 200

NOT_YET = "NOT YET RUN"


def rule(title):
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def not_yet(what, why):
    print(f"  {NOT_YET} — {why}")
    print(f"  ({what} is a null row on this tree, not a zero.)")


def load_json(path):
    """None on anything unreadable: a tree being written under us has half-written
    files and directories that vanish between the glob and the open."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None


def content(call):
    try:
        return call["response_body"]["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        return ""


def truncated(call):
    return call.get("finish_reason") in ("length", "error")


def reached_public_label(text, role):
    """pilot-3-checks2.py's correction: `_LABEL_RE` matches `Thinking:` too, so the
    first pass's "reached_label" column was meaningless."""
    body = text.replace("Reasoning:", "Argument:") if role in SOLO_ROLES else text
    return any(m.group(1).lower() == "argument" for m in _LABEL_RE.finditer(body))


def frac(k, n):
    return f"{k}/{n} {k / n:.0%}" if n else f"{k}/0 --"


def capped(items, label):
    for x in items[:MAX_LIST]:
        print(x)
    if len(items) > MAX_LIST:
        print(f"  ... and {len(items) - MAX_LIST} more {label} (listing capped at "
              f"{MAX_LIST}; the counts above are complete)")


# --- load ---------------------------------------------------------------------------

if not ROOT.is_dir():
    print(f"no such tree: {ROOT}")
    raise SystemExit(1)
if not DECISIONS.is_dir():
    print(f"no such decision tree: {DECISIONS}")
    raise SystemExit(1)

experiment = (load_json(ROOT / "experiment.json")
              or load_json(DECISIONS / "experiment.json") or {})
config = experiment.get("config") or {}
STRONG = config.get("debater_model") or "deepseek/deepseek-v4-flash-0731"
CHALLENGER = config.get("challenger_model") or "openai/gpt-4.1-nano"
PLANNED_CELLS = experiment.get("cells") or 0

stage_rows = []
if (ROOT / "cells.jsonl").is_file():
    for line in (ROOT / "cells.jsonl").open(encoding="utf-8"):
        if line.strip():
            try:
                stage_rows.append(json.loads(line))
            except ValueError:
                continue
index = []
if (ROOT / "index.jsonl").is_file():
    for line in (ROOT / "index.jsonl").open(encoding="utf-8"):
        if line.strip():
            try:
                index.append(json.loads(line))
            except ValueError:
                continue
HAVE_INDEX = bool(index)

# One record per cell, straight off disk. This is the base the funnel is built on:
# it exists as soon as `decide` has touched a cell, whereas `index.jsonl` only exists
# once `analyse` has run.
disk_rows = {}
run_dirs_by_cell = {}
cells_dir = DECISIONS / "cells"
for cell_dir in sorted(cells_dir.iterdir()) if cells_dir.is_dir() else []:
    if not cell_dir.is_dir():
        continue
    runs = sorted(d for d in (cell_dir / "runs").glob("*") if d.is_dir()) \
        if (cell_dir / "runs").is_dir() else []
    run_dirs_by_cell[cell_dir.name] = runs
    if not runs:
        continue
    latest = runs[-1]
    run = load_json(latest / "run.json") or {}
    item = load_json(latest / "item.json") or {}
    verdict = load_json(latest / "verdict.json") or {}
    parts = cell_dir.name.split("__")
    disk_rows[cell_dir.name] = {
        "cell_id": cell_dir.name,
        "run_dir": latest,
        "n_runs": len(runs),
        "status": run.get("status"),
        "error": run.get("error") or "",
        "condition": run.get("condition") or (parts[1] if len(parts) > 2 else "?"),
        "item_id": run.get("item_id") or item.get("item_id") or parts[0],
        "subset": item.get("subset") or run.get("subset") or "?",
        "label_basis": item.get("label_basis") or "?",
        "gold_flawed": item.get("gold_flawed"),
        "verdict": verdict.get("verdict"),
        "initially_correct": verdict.get("correct"),
    }


def latest_contest_dir(cell_id):
    """The contest run holding a challenge.json, newest first — pilot-3-paths.py's rule."""
    base = ROOT / "cells" / cell_id / "contests"
    if not base.is_dir():
        return None
    for d in sorted(base.glob("*/runs/*"), reverse=True):
        if (d / "challenge.json").is_file():
            return d
    return None


# The contest, agreement, ruling and grade artifacts, read straight off disk under the
# same field names `build_index` gives them. Doing it here rather than only from
# `index.jsonl` means rows 4, 5, 8 and 10 and the funnel come alive as soon as a stage
# has written something, instead of waiting on `analyse`.
for cell_id, base in disk_rows.items():
    cdir = latest_contest_dir(cell_id)
    if cdir is None:
        continue
    base["contest_dir"] = cdir
    ch = load_json(cdir / "challenge.json") or {}
    stance = ch.get("stance") or ("contests" if ch.get("raised", True) else "declined")
    base["challenge_stance"] = stance
    base["challenge_raised"] = stance == "contests"
    base["challenge_claimed_verdict"] = ch.get("claimed_verdict")
    base["challenge_contradictory"] = ch.get("contradictory")
    agreement = load_json(cdir / "agreement.json")
    if agreement is not None:
        base["prose_stance"] = agreement.get("prose_stance")
        base["line_prose_agree"] = agreement.get("agrees")
        base["phantom_contest"] = agreement.get("phantom_contest")
    ruling = load_json(cdir / "ruling.json")
    if ruling is not None:
        base["ruling_form"] = ruling.get("form")
        base["changed_the_decision"] = ruling.get("changed_the_decision")
        base["final_correct"] = ruling.get("correct")
    else:
        # No ruling was sought because nothing was objected to. Not-revised is the right
        # reading; "never contested" is preserved by challenge_raised. (experiment.py)
        base["changed_the_decision"] = False
        base["final_correct"] = base["initially_correct"]
    comprehension = load_json(cdir / "comprehension.json")
    if comprehension is not None:
        base["comprehension"] = comprehension.get("score")
    grade = load_json(cdir / "grade.json")
    if grade is not None:
        base["identified_flaw"] = grade.get("identified_flaw")
        base["characterises_the_flaw"] = grade.get("characterises_the_flaw")
        base["grade_valid"] = grade.get("valid")

if HAVE_INDEX:
    for row in index:
        base = disk_rows.get(row["cell_id"])
        if base is not None:
            base.update({k: v for k, v in row.items()
                         if k not in ("run_dir", "contest_dir")})

# Decided cells — the funnel's population, and `index.jsonl`'s once `analyse` runs.
decided_rows = [r for r in disk_rows.values()
                if r["status"] == "completed" and r["verdict"]]

decision_calls, contest_calls = [], []
# Two passes rather than one partition, because the two kinds of call can now live in
# different trees. With no --decisions the two roots are the same path and the
# `contests` test partitions exactly as it always did.
for root, want_contests, bucket in ((DECISIONS, False, decision_calls),
                                    (ROOT, True, contest_calls)):
    for path in sorted(root.rglob("calls.jsonl")):
        if "parent" in path.parts:
            continue
        if ("contests" in path.parts) != want_contests:
            continue
        run = str(path.parent)
        try:
            handle = path.open(encoding="utf-8")
        except OSError:
            continue
        with handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    call = json.loads(line)
                except ValueError:
                    continue          # a line still being appended under us
                call["_run"] = run
                bucket.append(call)
all_calls = decision_calls + contest_calls

challenges = sorted(ROOT.glob("cells/*/contests/*/runs/*/challenge.json"))
agreements = sorted(ROOT.glob("cells/*/contests/*/runs/*/agreement.json"))
grades = sorted(ROOT.glob("cells/*/contests/*/runs/*/grade.json"))

rule(f"TREE {ROOT}" + (f"\nDECISIONS {DECISIONS}  (read-only source)" if SPLIT else ""))
if SPLIT:
    print("split trees: the decision-side rows (1, 2, 3, 6, 7, second draws) are read "
          "from\nthe source tree; the contest-side rows (4, 5, 8, 10, funnels) from this "
          "one.\n")
print(f"experiment  {experiment.get('name', '?')}   planned cells {PLANNED_CELLS}   "
      f"conditions {experiment.get('conditions')}")
print(f"strong model {STRONG}   challenger {CHALLENGER}")
print("\nstage artifacts on disk:")
print(f"  decide     cell dirs {len(run_dirs_by_cell):>6}   run dirs "
      f"{sum(len(v) for v in run_dirs_by_cell.values()):>6}   "
      f"calls.jsonl {len(list(DECISIONS.rglob('calls.jsonl'))):>6}")
for label, found, why in (
    ("contest  ", len(challenges), "no challenge.json anywhere under cells/*/contests/"),
    ("agreement", len(agreements), "no agreement.json anywhere"),
    ("grade    ", len(grades), "no grade.json anywhere"),
    ("analyse  ", int((ROOT / "index.jsonl").is_file())
     + int((ROOT / "metrics.json").is_file()),
     "no index.jsonl and no metrics.json"),
):
    print(f"  {label}  {found:>6} artifacts" + ("" if found else f"   <- {NOT_YET}: {why}"))
print(f"\ncells.jsonl rows {len(stage_rows)}  "
      f"(stages: {dict(Counter(r.get('stage') for r in stage_rows))})")

# --- row 1: parse --------------------------------------------------------------------

rule("ROW 1 — parse")
by_status = Counter(r["status"] for r in disk_rows.values())
total = len(disk_rows)
done = by_status.get("completed", 0)
failed = [r for r in disk_rows.values() if r["status"] == "failed"]
print("counted from each cell's latest run.json, which is authoritative on a live tree:")
print(f"  cells with a run dir: {total}   completed {done}   failed {len(failed)}   "
      f"other {total - done - len(failed)} {dict((k, v) for k, v in by_status.items() if k not in ('completed', 'failed'))}")
print(f"  decided: {done}/{total} = {done / total:.1%}" if total else "  no cells yet")
if PLANNED_CELLS:
    print(f"  against the planned grid: {done}/{PLANNED_CELLS} = "
          f"{done / PLANNED_CELLS:.1%} of {PLANNED_CELLS} cells")

decide_rows = [r for r in stage_rows if r.get("stage") == "decide"]
last = {}
for r in decide_rows:
    last[r["cell_id"]] = r
sj_done = sum(1 for r in last.values() if r.get("status") == "completed")
print(f"\ncells.jsonl's decide summary: {len(last)} cells, completed {sj_done}, "
      f"failed {sum(1 for r in last.values() if r.get('status') == 'failed')}")
if len(last) != total:
    print(f"  ! cells.jsonl covers {len(last)} of the {total} cells on disk. It is "
          f"appended once per STAGE INVOCATION, at the end (experiment_cli.py:234), so a "
          f"stage still running has not written its rows. The run.json count above is the "
          f"live one; the two agree on a finished tree.")

trunc = [c for c in all_calls if truncated(c)]
print(f"\ntruncated calls: {len(trunc)} of {len(all_calls)} attempts"
      + (f" = {len(trunc) / len(all_calls):.1%}" if all_calls else ""))
for key, n in Counter(
    (c.get("role"), c.get("purpose"),
     "PAST its public label (fatal by design)" if reached_public_label(content(c), c.get("role"))
     else "never reached it (budget route)")
    for c in trunc
).most_common():
    print(f"  role={str(key[0]):<14} purpose={str(key[1]):<12} {key[2]:<42} {n}")
tok = Counter((c.get("usage") or {}).get("completion_tokens") for c in trunc)
print(f"  completion tokens on truncated calls: {dict(tok.most_common(5))}")

modes = Counter()
for path in sorted(ROOT.rglob("trace.json")):
    if "parent" in path.parts:
        continue
    data = load_json(path)
    for step in (data or {}).get("steps", []):
        modes[step["parse_mode"]] += 1
for path in sorted(ROOT.rglob("transcript.json")):
    if "parent" in path.parts:
        continue
    data = load_json(path)
    for turn in (data or {}).get("turns", []):
        modes[turn["parse_mode"]] += 1
print("\nparse_mode over every recorded decision step/turn:")
for k, v in modes.most_common():
    print(f"  {k:<44} {v}")
print(f"\nbudget recoveries (parse_mode *_after_budget_repair): "
      f"{sum(v for k, v in modes.items() if 'after_budget_repair' in k)}")

print(f"\nfailed cells: {len(failed)}")
print("  failure shape (first 90 chars of the error), complete:")
for kind, n in Counter(r["error"][:90] for r in failed).most_common():
    print(f"    {n:>5}  {kind}")
crit_trunc = sum(1 for r in failed
                 if "critic" in r["error"] and "truncat" in r["error"])
print(f"  of which CRITIQUE TRUNCATED PAST ITS LABEL — the known fatal cause: {crit_trunc}")
print("  by condition: " + str(dict(Counter(r["condition"] for r in failed))))
print("  by subset:    " + str(dict(Counter(r["subset"] for r in failed))))
malformed_after_repair = sum(1 for r in failed
                             if "still malformed after one" in r["error"])
print(f"  malformed-after-repair cells: {malformed_after_repair}")
print()
capped([f"  {r['cell_id']:<62} {r['error'][:150]}"
        for r in sorted(failed, key=lambda r: r["cell_id"])], "failed cells")

# --- row 2: repair, attributed to the failing call -----------------------------------

rule("ROW 2 — repair, attributed to the call that FAILED")
by_run_key = defaultdict(list)
for c in all_calls:
    by_run_key[(c["_run"], c.get("role"), c.get("speaker"), c.get("round"))].append(c)

originals = [c for c in all_calls if c.get("purpose") != "repair"]
repairs = [c for c in all_calls if c.get("purpose") == "repair"]
blamed = Counter()
paired = 0
for r in repairs:
    key = (r["_run"], r.get("role"), r.get("speaker"), r.get("round"))
    prior = [c for c in by_run_key[key] if c.get("purpose") != "repair"]
    if prior:
        blamed[prior[-1].get("provider") or "unknown"] += 1
        paired += 1
print(f"original calls {len(originals)}   repair calls {len(repairs)}   "
      f"paired to a failing call {paired}/{len(repairs)}")
if originals:
    print(f"overall repair rate: {len(repairs)}/{len(originals)} = "
          f"{len(repairs) / len(originals):.1%} of original calls")

orig_by_provider = Counter(c.get("provider") or "unknown" for c in originals)
print(f"\n{'provider':<20} {'original calls':>14} {'caused a repair':>16} {'rate':>8}")
for prov, n in orig_by_provider.most_common():
    k = blamed.get(prov, 0)
    print(f"{prov:<20} {n:>14} {k:>16} {k / n:>7.1%}")

strong_orig = [c for c in originals
               if (c.get("request_body") or {}).get("model") == STRONG]
strong_rep = 0
for r in repairs:
    if (r.get("request_body") or {}).get("model") != STRONG:
        continue
    key = (r["_run"], r.get("role"), r.get("speaker"), r.get("round"))
    if [c for c in by_run_key[key] if c.get("purpose") != "repair"]:
        strong_rep += 1
print(f"\nSTRONG MODEL ONLY ({STRONG}):")
print(f"  original calls {len(strong_orig)}   caused a repair {strong_rep}   "
      f"rate {strong_rep / len(strong_orig):.1%}" if strong_orig else "  none")

print("\nrepair kind, from the instruction actually sent:")
kinds = Counter()
for r in repairs:
    msg = (r.get("request_body") or {}).get("messages") or [{}]
    text = msg[-1].get("content", "")
    if "ran out of budget" in text:
        kinds["budget"] += 1
    elif "had only a Thinking section" in text:
        kinds["aimed: no_public_label"] += 1
    elif "must begin on its own line" in text:
        kinds["aimed: misplaced label"] += 1
    else:
        kinds["per-role fallback"] += 1
for k, v in kinds.most_common():
    print(f"  {k:<28} {v}")
print(f"\nmalformed-after-repair cells: {malformed_after_repair}")

# --- row 3: verdicts -----------------------------------------------------------------

rule("ROW 3 — verdict distribution per condition")
print("(a decide-stage quantity: read off verdict.json, so it does not wait on analyse)")
if decided_rows:
    print(f"{'condition':<16} {'n':>5} {'FLAWED':>8} {'SOUND':>8} {'max share':>10} "
          f"{'gold flawed':>12} {'accuracy':>9}")
    for cond in CONDS + ("ALL",):
        rows = decided_rows if cond == "ALL" else [r for r in decided_rows
                                                   if r["condition"] == cond]
        if not rows:
            continue
        f = sum(1 for r in rows if r["verdict"] == "FLAWED")
        s = len(rows) - f
        gold = sum(1 for r in rows if r["gold_flawed"])
        acc = sum(1 for r in rows if r["initially_correct"])
        print(f"{cond:<16} {len(rows):>5} {f:>8} {s:>8} "
              f"{max(f, s) / len(rows):>9.1%} {gold:>12} {acc / len(rows):>8.1%}")
else:
    not_yet("verdict distribution", "no cell has a completed decision yet")

# --- row 4: stances ------------------------------------------------------------------

rule("ROW 4 — stances per condition, split by parent verdict and by correctness")
staged = [r for r in disk_rows.values() if r.get("challenge_stance")]
if not staged:
    not_yet("stances", "the contest stage has left no challenge.json")
else:
    def stance_table(title, keyfn):
        print(f"\n-- {title} --")
        print(f"{'condition':<16} {'group':<18} {'n':>4} {'contests':>9} {'declined':>9} "
              f"{'unclear':>8} {'agrees':>7} {'contest rate':>13}")
        for cond in CONDS:
            rows = [r for r in staged if r["condition"] == cond]
            for group in sorted({str(keyfn(r)) for r in rows}):
                g = [r for r in rows if str(keyfn(r)) == group]
                c = sum(1 for r in g if r["challenge_stance"] == "contests")
                d = sum(1 for r in g if r["challenge_stance"] == "declined")
                u = sum(1 for r in g if r["challenge_stance"] == "unclear")
                a = sum(1 for r in g if r["challenge_stance"] == "agrees")
                print(f"{cond:<16} {group:<18} {len(g):>4} {c:>9} {d:>9} {u:>8} {a:>7} "
                      f"{c / len(g):>12.1%}")

    stance_table("pooled", lambda r: "all")
    stance_table("by PARENT VERDICT class", lambda r: r["verdict"])
    stance_table("by correctness",
                 lambda r: "correct" if r["initially_correct"] else "incorrect")

    print("\n-- contests given a false negative vs a false positive --")
    for cond in CONDS:
        rows = [r for r in staged if r["condition"] == cond
                and r["initially_correct"] is False]
        fn = [r for r in rows if r["gold_flawed"]]
        fp = [r for r in rows if not r["gold_flawed"]]

        def sub(g):
            c = sum(1 for r in g if r["challenge_stance"] == "contests")
            return f"{c}/{len(g)}" + (f" = {c / len(g):.0%}" if g else "")
        print(f"  {cond:<16} false negative {sub(fn):<16} false positive {sub(fp)}")

    print("\n-- overall claimed_verdict, the column that must NOT be read as a reflex --")
    print("   " + str(Counter(r.get("challenge_claimed_verdict") for r in staged)))

# --- row 5: line vs prose ------------------------------------------------------------

rule("ROW 5 — line vs prose")
measured = [r for r in disk_rows.values() if r.get("prose_stance")]
if not measured:
    not_yet("line vs prose", "the agreement stage has left no agreement.json")
else:
    eligible = sum(1 for r in staged
                   if r.get("challenge_stance") in ("contests", "declined"))
    print(f"measured {len(measured)} of {eligible} eligible contests")
    print(f"\n{'condition':<16} {'line':<9} {'RIGHT':>7} {'WRONG':>7} {'NEITHER':>9}")
    for cond in CONDS + ("ALL",):
        rows = measured if cond == "ALL" else [r for r in measured
                                               if r["condition"] == cond]
        for stance, line in (("contests", "REVERSE"), ("declined", "STANDS")):
            g = [r for r in rows if r["challenge_stance"] == stance]
            c = Counter(r["prose_stance"] for r in g)
            print(f"{cond:<16} {line:<9} {c.get('RIGHT', 0):>7} {c.get('WRONG', 0):>7} "
                  f"{c.get('NEITHER', 0):>9}")
    print()
    for cond in CONDS + ("ALL",):
        rows = measured if cond == "ALL" else [r for r in measured
                                               if r["condition"] == cond]
        contests = [r for r in rows if r["challenge_stance"] == "contests"]
        phantom = sum(1 for r in contests if r.get("phantom_contest"))
        declines = [r for r in rows if r["challenge_stance"] == "declined"]
        rev = sum(1 for r in declines if r["prose_stance"] == "WRONG")
        print(f"  {cond:<16} phantom contests {phantom}/{len(contests)}"
              + (f" = {phantom / len(contests):.1%}" if contests else "")
              + f"   declines arguing for reversal {rev}/{len(declines)}")

# --- row 6: containment --------------------------------------------------------------

rule("ROW 6 — containment and native reasoning")
leaks = []
for path in sorted(DECISIONS.rglob("transcript.json")):
    if "parent" in path.parts:
        continue
    for turn in (load_json(path) or {}).get("turns", []):
        if _ANY_THINKING_RE.search(turn["argument"]):
            leaks.append((str(path), turn["speaker"], turn["round"]))
for path in sorted(DECISIONS.rglob("trace.json")):
    if "parent" in path.parts:
        continue
    for step in (load_json(path) or {}).get("steps", []):
        if _ANY_THINKING_RE.search(step["text"]):
            leaks.append((str(path), step["stage"], step["index"]))
n_records = len(list(DECISIONS.glob("cells/*/runs/*/transcript.json"))) + \
    len(list(DECISIONS.glob("cells/*/runs/*/trace.json")))
print(f"challenger-visible decision records checked: {n_records}")
print(f"'Thinking:' occurrences in published text: {len(leaks)}")
capped([f"  LEAK {leak}" for leak in leaks], "leaks")

nr = Counter()
for c in all_calls:
    if c.get("has_native_reasoning"):
        nr[c.get("provider") or "unknown"] += 1
tot = Counter(c.get("provider") or "unknown" for c in all_calls)
print(f"\n{'provider':<20} {'calls':>8} {'native reasoning':>18} {'rate':>8}")
for prov, n in tot.most_common():
    print(f"{prov:<20} {n:>8} {nr.get(prov, 0):>18} {nr.get(prov, 0) / n:>7.1%}")
withheld = sum(1 for c in all_calls
               if ((c.get("usage") or {}).get("completion_tokens_details") or {})
               .get("reasoning_tokens") and not c.get("has_native_reasoning"))
print(f"reasoning billed but withheld: {withheld}")

# --- row 7: critiques ----------------------------------------------------------------

rule("ROW 7 — critiques")
crit_steps = withheld_steps = 0
runs_with_withheld = set()
for path in sorted(DECISIONS.glob("cells/*/runs/*/trace.json")):
    for step in (load_json(path) or {}).get("steps", []):
        if step["stage"] != "critique":
            continue
        crit_steps += 1
        if step["parse_mode"] == "unparsed_withheld":
            withheld_steps += 1
            runs_with_withheld.add(str(path.parent))
print(f"critique steps: {crit_steps}   withheld: {withheld_steps}"
      + (f" = {withheld_steps / crit_steps:.1%}" if crit_steps else ""))
print(f"self_critique runs carrying at least one withheld critique: "
      f"{len(runs_with_withheld)}")
parent_traces = sorted(ROOT.glob("cells/*self_critique*/contests/*/runs/*/parent/trace.json"))
if not parent_traces:
    print(f"self_critique CHALLENGERS shown a placeholder: {NOT_YET} — the contest stage "
          f"has copied no parent/ record yet (0 expected once it has)")
else:
    shown = sum(1 for p in parent_traces
                if any(s["parse_mode"] == "unparsed_withheld"
                       for s in (load_json(p) or {}).get("steps", [])))
    print(f"self_critique CHALLENGERS shown a placeholder: {shown} of "
          f"{len(parent_traces)}   (0 expected)")

# --- row 8: grader -------------------------------------------------------------------

rule("ROW 8 — graded rows")
if not grades:
    not_yet("graded rows", "the grade stage has left no grade.json")
else:
    parsed = []
    for path in grades:
        g = load_json(path)
        if g is None:
            continue
        cell = next((p for p in path.parts if "__" in p), str(path))
        parsed.append((cell, g, path))
    print(f"graded rows: {len(parsed)}   "
          f"identified {sum(1 for _, g, _ in parsed if g['identified_flaw'])}   "
          f"characterised {sum(1 for _, g, _ in parsed if g['characterises_the_flaw'])}   "
          f"valid {sum(1 for _, g, _ in parsed if g['valid'])}   "
          f"ungradable_char {sum(1 for _, g, _ in parsed if g['characterisation_ungradable'])}")
    print("EVERY ONE OF THESE MUST BE HAND-CHECKED AGAINST ITS flaw.json (HANDOFF §5).")
    for cell, g, path in sorted(parsed)[:MAX_GRADE_ROWS]:
        print(f"\n  {cell}")
        print(f"    identified={g['identified_flaw']}  characterised="
              f"{g['characterises_the_flaw']}  valid={g['valid']}  "
              f"ungradable_char={g['characterisation_ungradable']}")
        print(f"    dir: {path.parent}")
    if len(parsed) > MAX_GRADE_ROWS:
        print(f"\n  ... and {len(parsed) - MAX_GRADE_ROWS} more graded rows "
              f"(listing capped at {MAX_GRADE_ROWS})")

# --- row 9: ops ----------------------------------------------------------------------

rule("ROW 9 — ops")
if not all_calls:
    not_yet("ops", "no calls.jsonl has a readable line yet")
else:
    served = Counter(c.get("provider") or "unknown" for c in all_calls)
    print("served-provider distribution over every call:")
    for prov, n in served.most_common():
        print(f"  {prov:<22} {n:>6}  {n / len(all_calls):>6.1%}")
    strong_calls = [c for c in all_calls
                    if (c.get("request_body") or {}).get("model") == STRONG]
    print(f"\nstrong-model calls: {len(strong_calls)}")
    for prov, n in Counter(c.get("provider") or "unknown"
                           for c in strong_calls).most_common():
        print(f"  {prov:<22} {n:>6}  {n / len(strong_calls):>6.1%}")
    status = Counter(c.get("status") for c in all_calls)
    print(f"\nHTTP status counts: {dict(status)}")
    for code in (404, 429, 500, 502, 503):
        n = status.get(code, 0)
        if n:
            print(f"  {code}: {n} = {n / len(all_calls):.2%} of calls")
    print(f"non-200 attempts: {sum(v for k, v in status.items() if k != 200)}"
          f" / {len(all_calls)}")

    from exp2.accounting import aggregate_tree  # noqa: E402
    spend = aggregate_tree(ROOT)
    print(f"\nspend: ${spend['cost_usd']:.4f} over {spend['runs']} run directories")
    if SPLIT:
        source_spend = aggregate_tree(DECISIONS)
        print(f"  (the decisions were paid for by {DECISIONS}: "
              f"${source_spend['cost_usd']:.4f} over {source_spend['runs']} run "
              f"directories, already spent and not re-spent here)")
    print(f"  decision path ${spend['decision_path']['cost_usd']:.4f}  "
          f"off path ${spend['off_path']['cost_usd']:.4f}")
    if done:
        print(f"  $/decided cell: ${spend['cost_usd'] / done:.5f}")
        if PLANNED_CELLS:
            print(f"  projection at the full grid of {PLANNED_CELLS} cells: "
                  f"${spend['cost_usd'] / done * PLANNED_CELLS:.2f}"
                  f"  (1.3x headroom "
                  f"${spend['cost_usd'] / done * PLANNED_CELLS * 1.3:.2f})")
            print("  NB on a partial tree this projection is the DECIDE stage only; the "
                  "other four stages have not spent yet.")
    tokens_by_model = defaultdict(int)
    cost_by_model = defaultdict(float)
    for c in all_calls:
        m = (c.get("request_body") or {}).get("model") or "?"
        u = c.get("usage") or {}
        tokens_by_model[m] += (u.get("completion_tokens") or 0)
        cost_by_model[m] += float(u.get("cost") or 0.0)
    print("\ncost by model:")
    for m, v in sorted(cost_by_model.items(), key=lambda kv: -kv[1]):
        print(f"  {m:<36} ${v:>8.4f}  "
              f"{v / max(sum(cost_by_model.values()), 1e-9):>6.1%}"
              f"   completion tokens {tokens_by_model[m]}")

# --- row 10: the four hand-read paths ------------------------------------------------

rule("ROW 10 — the four hand-read paths (candidates; the reading is by hand)")


def contest_dir(cell_id):
    runs = sorted((ROOT / "cells" / cell_id / "contests").glob("*/runs/*"), reverse=True)
    for d in runs:
        if (d / "challenge.json").is_file():
            return d
    return None


def show(label, row):
    d = contest_dir(row["cell_id"])
    print(f"\n{label}")
    print(f"  cell            {row['cell_id']}")
    print(f"  subset          {row['subset']}   gold_flawed={row['gold_flawed']}")
    print(f"  verdict         {row['verdict']}   "
          f"initially_correct={row['initially_correct']}")
    print(f"  stance          {row.get('challenge_stance')}   "
          f"claimed={row.get('challenge_claimed_verdict')}")
    print(f"  prose           {row.get('prose_stance')}   "
          f"agree={row.get('line_prose_agree')}  phantom={row.get('phantom_contest')}")
    print(f"  changed         {row.get('changed_the_decision')}   "
          f"final_correct={row.get('final_correct')}")
    print(f"  comprehension   {row.get('comprehension')}")
    print(f"  PATH            {d}/transcript.md")
    print(f"  verbatim        {d}/transcript_full.md")


if not staged:
    not_yet("the four hand-read paths",
            "no cell has been contested, so there is no path to read")
else:
    for cond in CONDS:
        genuine = [r for r in staged if r["condition"] == cond
                   and r.get("challenge_stance") == "contests"
                   and r.get("line_prose_agree") is True]
        wrong = [r for r in genuine if r["initially_correct"] is False]
        pick = wrong or genuine
        if pick:
            show(f"GENUINE CONTEST — {cond}"
                 + ("  (on a decision that was wrong)" if wrong
                    else "  (on a correct decision)"),
                 sorted(pick, key=lambda r: r["cell_id"])[0])
        else:
            print(f"\nGENUINE CONTEST — {cond}: NONE "
                  f"(line and prose never both contested)")
    declined_wrong = [r for r in staged
                      if r.get("challenge_stance") == "declined"
                      and r["initially_correct"] is False]
    if declined_wrong:
        show("DECLINED ON A WRONG DECISION",
             sorted(declined_wrong, key=lambda r: r["cell_id"])[0])
    else:
        print("\nDECLINED ON A WRONG DECISION: none")

# --- salvaged_no_thinking (pre-registered expectation 8) -----------------------------

rule("EXPECTATION 8 — salvaged_no_thinking on solo runs")
solo_modes = Counter()
for path in sorted(DECISIONS.glob("cells/*/runs/*/trace.json")):
    for step in (load_json(path) or {}).get("steps", []):
        solo_modes[step["parse_mode"]] += 1
tot_solo = sum(solo_modes.values())
snt = sum(v for k, v in solo_modes.items() if k.startswith("salvaged_no_thinking"))
print(f"solo decision steps: {tot_solo}")
print(f"salvaged_no_thinking: {snt}"
      + (f" = {snt / tot_solo:.1%}" if tot_solo else ""))
for k, v in solo_modes.most_common():
    print(f"  {k:<44} {v}")

# --- the funnel: overall, per subset, per label_basis --------------------------------
#
# error -> detection -> valid objection -> revision, on the decided cells. The two
# middle columns are CONDITIONAL rates and the header says so on every table:
# LLM_NOTES.md 3f — as implemented, `valid objection` is
# P(valid | objection raised, initially incorrect, flawed item, annotated subset), not
# DESIGN.md's P(valid | initially incorrect). A decline on a wrong decision is a
# detection failure that lives in the `contest|incorrect` row, not in this one. The
# `valid x raised` column multiplies the two through, which is the unconditional
# reading the write-up must use.

FUNNEL_NOTE = (
    "denominators: errors|n = decided cells; contest|incorrect and falsealarm|correct = "
    "cells whose contest stage ran;\n"
    "  ident|graded and valid|graded are CONDITIONAL on an objection having been raised "
    "AND the row being gradable\n"
    "  (initially incorrect AND flawed item AND the subset's annotation says what the "
    "flaw is) — LLM_NOTES.md 3f.\n"
    "  `valid x raised` multiplies valid|graded through contest|incorrect: that product "
    "is the unconditional reading.")

FUNNEL_HEAD = (f"{'stratum':<30}{'n':>6}{'errors':>13}{'contest|inc':>15}"
               f"{'falsealarm|cor':>16}{'ident|graded':>15}{'valid|graded':>15}"
               f"{'valid x raised':>16}{'rev|inc':>13}{'rev|cor':>13}")


def funnel_line(stratum, rows):
    n = len(rows)
    inc = [r for r in rows if r["initially_correct"] is False]
    cor = [r for r in rows if r["initially_correct"] is True]
    contested = [r for r in rows if r.get("challenge_stance")]
    graded = [r for r in rows if r.get("grade_valid") is not None
              or r.get("identified_flaw") is not None]

    def col(k, d, ok, width):
        return f"{frac(k, d) if ok else 'not yet':>{width}}"

    ci = sum(1 for r in inc if r.get("challenge_stance") == "contests")
    fa = sum(1 for r in cor if r.get("challenge_stance") == "contests")
    idf = sum(1 for r in graded if r.get("identified_flaw"))
    val = sum(1 for r in graded if r.get("grade_valid"))
    ri = sum(1 for r in inc if r.get("changed_the_decision"))
    rc = sum(1 for r in cor if r.get("changed_the_decision"))
    have_contest = bool(contested)
    have_grade = bool(graded)
    if have_grade and inc:
        product = f"{(val / len(graded)) * (ci / len(inc)):.1%}"
    else:
        product = "not yet" if not have_grade else "--"
    return (f"{stratum:<30}{n:>6}{frac(len(inc), n):>13}"
            + col(ci, len(inc), have_contest, 15)
            + col(fa, len(cor), have_contest, 16)
            + col(idf, len(graded), have_grade, 15)
            + col(val, len(graded), have_grade, 15)
            + f"{product:>16}"
            + col(ri, len(inc), have_contest, 13)
            + col(rc, len(cor), have_contest, 13))


def funnel_table(title, keyfn, order=None):
    rule(title)
    print(FUNNEL_NOTE)
    print()
    print(FUNNEL_HEAD)
    print("-" * len(FUNNEL_HEAD))
    if not decided_rows:
        not_yet("the funnel", "no cell has a completed decision yet")
        return
    strata = order if order is not None else sorted({str(keyfn(r))
                                                     for r in decided_rows})
    for cond in CONDS:
        rows_c = [r for r in decided_rows if r["condition"] == cond]
        if not rows_c:
            continue
        for stratum in strata:
            g = [r for r in rows_c if str(keyfn(r)) == stratum]
            if g:
                print(funnel_line(f"{cond} / {stratum}"[:30], g))
        print(funnel_line(f"{cond} / ALL"[:30], rows_c))
        print("-" * len(FUNNEL_HEAD))
    for stratum in strata:
        g = [r for r in decided_rows if str(keyfn(r)) == stratum]
        if g:
            print(funnel_line(f"ALL / {stratum}"[:30], g))
    print(funnel_line("ALL / ALL", decided_rows))


rule("FUNNEL — pooled, per condition")
print(FUNNEL_NOTE)
print()
print(FUNNEL_HEAD)
print("-" * len(FUNNEL_HEAD))
if decided_rows:
    for cond in CONDS:
        rows_c = [r for r in decided_rows if r["condition"] == cond]
        if rows_c:
            print(funnel_line(cond, rows_c))
    print(funnel_line("ALL", decided_rows))
    print("\nfalse negatives / false positives among the errors:")
    for cond in CONDS + ("ALL",):
        rows_c = decided_rows if cond == "ALL" else [r for r in decided_rows
                                                     if r["condition"] == cond]
        inc = [r for r in rows_c if r["initially_correct"] is False]
        fn = sum(1 for r in inc if r["gold_flawed"])
        print(f"  {cond:<16} errors {len(inc):>5}   false negative {fn:>5}   "
              f"false positive {len(inc) - fn:>5}")
else:
    not_yet("the funnel", "no cell has a completed decision yet")

funnel_table("FUNNEL — by condition x SUBSET (HANDOFF §5)", lambda r: r["subset"])
funnel_table("FUNNEL — by condition x LABEL_BASIS (HANDOFF §5)",
             lambda r: r["label_basis"])
print("\nRates are NOT pooled across label_basis by default (src/exp2/analysis.py): a "
      "planted\nreasoning error, a sentence-labelled one and a wrong final answer are "
      "different objects.")
print("Read the n before the rate — a subset x condition cell is a slice of the corpus, "
      "not the corpus.")

# --- second draws (LLM_NOTES.md §3r) -------------------------------------------------

rule("SECOND DRAWS — cells decided on a re-run (LLM_NOTES.md §3r)")
print("The user chose --retry-failed for this run: a cell whose latest run is `failed`")
print("gets one more draw on a resume. §3r makes reporting the count an obligation,")
print("because a second draw selects for compliant outputs — the cells that survive are")
print("no longer a clean sample of the corpus. They are identifiable on disk as more")
print("than one directory under cells/<cell>/runs/.")
multi = {cell: runs for cell, runs in run_dirs_by_cell.items() if len(runs) > 1}
print(f"\ncells with more than one run directory: {len(multi)} of "
      f"{len(run_dirs_by_cell)}")
print(f"run-directory count distribution: "
      f"{dict(sorted(Counter(len(v) for v in run_dirs_by_cell.values()).items()))}")
if multi:
    print(f"\n{'condition':<16} {'2nd-draw cells':>15} {'final completed':>16} "
          f"{'final failed':>13} {'other':>7}")
    for cond in CONDS + ("ALL",):
        rows = [disk_rows[c] for c in sorted(multi)
                if c in disk_rows and (cond == "ALL"
                                       or disk_rows[c]["condition"] == cond)]
        if not rows and cond != "ALL":
            continue
        comp = sum(1 for r in rows if r["status"] == "completed")
        fail = sum(1 for r in rows if r["status"] == "failed")
        print(f"{cond:<16} {len(rows):>15} {comp:>16} {fail:>13} "
              f"{len(rows) - comp - fail:>7}")
    print(f"\ncells DECIDED on a second draw (final run completed): "
          f"{sum(1 for c in multi if disk_rows.get(c, {}).get('status') == 'completed')}"
          f"  — these are the ones the write-up must name.")
    print("\nby subset: " + str(dict(Counter(
        disk_rows[c]["subset"] for c in multi if c in disk_rows))))
    print()
    capped([f"  {c:<62} runs={len(multi[c])}  "
            f"final={disk_rows.get(c, {}).get('status')}"
            for c in sorted(multi)], "second-draw cells")
else:
    print("\nnone — no cell has been drawn twice.")

print("\ndone.")

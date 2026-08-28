"""jd3 PILOT — the instrument check for one judge throughout, in one table.

    cd exp2
    uv run python records/derivations/jd3-pilot-checks.py \
        2>&1 | tee outputs/jd3-pilot-checks.log

Stdlib only, and every path is a flag, so the same script runs against a live
`outputs/experiments/` tree and against committed indexes without editing a line.

WHAT IT ANSWERS, and none of it is a result — sixty cells measure no accuracy difference:

  (a) IS MAVERICK A DIFFERENT DEBATE JUDGE FROM NANO? The same 60 stored transcripts,
      judged by both. Paired on `cell_id`: agreement on the verdict word, each judge's
      accuracy, its FLAWED skew, and an exact two-sided McNemar REPORTED AND NOT TESTED —
      it is a descriptive in the pre-registration and it stays one here.
  (b) DOES ITS JUDGMENT SURVIVE AS A DOCUMENT? The judgment is what the auditor audits,
      so its length, its parse mode, its repairs and every cell lost to truncation are
      counted off the run tree rather than the index.
  (c) DOES THE AUDIT STILL HOLD ON A DIFFERENT JUDGE'S JUDGMENTS? The whole funnel beside
      `judgment-debate-pilot-2`'s — the same 60 cells, the same challenger, the same
      grader, the same prompts, nano in the two judge seats instead of Maverick.
  (d) WHAT DOES THE FULL RUN COST? Per-role spend and latency off `calls.jsonl`, scaled
      to the 1,644 cells the main arms run on.

`ruling_line_mismatch` is printed in BOTH forms wherever it appears, as the
pre-registration requires: STRICT excludes the reader's NEITHER readings, CONSERVATIVE
counts them as mismatches, and `metrics.json` prints the conservative one.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import Counter
from pathlib import Path

W = 100
VERDICTS = ("FLAWED", "SOUND")


# --------------------------------------------------------------------------- #
# formatting and statistics — shapes kept identical to judgment-debate-2.py's
# --------------------------------------------------------------------------- #


def pct(num, den):
    return f"{100.0 * num / den:.1f}%" if den else "n/a"


def rate(num, den):
    return f"{num}/{den} {pct(num, den)}" if den else f"{num}/0 n/a"


def rule(char="-"):
    print(char * W)


def head(title):
    print()
    rule("=")
    print(title)
    rule("=")


def mcnemar_exact(b: int, c: int) -> float:
    """Exact two-sided McNemar on the discordant pairs. Identical to
    `judgment-debate-2.py`'s, so two logs held side by side cannot disagree."""
    if b < 0 or c < 0:
        raise ValueError(f"discordant counts must be non-negative, got b={b} c={c}")
    n = b + c
    tail = sum(math.comb(n, k) for k in range(min(b, c) + 1))
    return min(1.0, 2.0 * tail / (2 ** n))


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def acc(k: int, n: int) -> str:
    low, high = wilson(k, n)
    return f"{rate(k, n)}  [{100 * low:.1f}, {100 * high:.1f}]"


# --------------------------------------------------------------------------- #
# loading
# --------------------------------------------------------------------------- #


def load_index(path: Path) -> dict[str, dict]:
    if not path.is_file():
        return {}
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[row["cell_id"]] = row
    return rows


def load_runs(tree: Path) -> list[dict]:
    """Every decision run directory's manifest and verdict, for the document counts.

    The index carries only DECIDED cells by construction — `build_index` skips a cell
    with no readable decision — so a failed re-judge is invisible there and visible only
    here. That is the whole reason this reads the tree.
    """
    runs = []
    for manifest_path in sorted(tree.glob("cells/*/runs/*/run.json")):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        directory = manifest_path.parent
        verdict = None
        if (directory / "verdict.json").is_file():
            try:
                verdict = json.loads((directory / "verdict.json").read_text(
                    encoding="utf-8"))
            except ValueError:
                verdict = None
        runs.append({"dir": directory, "manifest": manifest, "verdict": verdict})
    return runs


def load_calls(tree: Path) -> list[dict]:
    """Every wire call this tree made — decisions and contests alike.

    Two exclusions, both of them copies of money spent elsewhere.

    `calls.source.jsonl` is the DEBATE's own log, copied beside a re-judged decision so
    the verbatim document stays complete. That money was spent by the sweep, and reading
    it here would bill $32 of debating to a $2 pilot.

    `parent/calls.jsonl` is this tree's own decision log, copied again inside every
    contest that contests it — `copy_parent = true` is what makes a contest record
    self-contained. Counting it would double every judge call, which is exactly the
    exclusion `accounting.aggregate_tree` makes for the same reason.
    """
    calls = []
    for path in sorted(tree.rglob("calls.jsonl")):
        if "parent" in path.parts:
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                calls.append(json.loads(line))
            except ValueError:
                continue
    return calls


def words(text: str) -> int:
    return len((text or "").split())


# --------------------------------------------------------------------------- #
# (a) the two judges on the same transcripts
# --------------------------------------------------------------------------- #


def section_a(rows: dict[str, dict]) -> None:
    head("(a) M0 — MAVERICK AND NANO ON THE SAME 60 STORED TRANSCRIPTS")
    print("Paired on cell_id and read off ONE index: `verdict` is this run's judge and")
    print("`source_verdict` is the sweep's, recorded cell by cell by the rejudge stage.")
    print("DESCRIPTIVE. The pre-registration reports this comparison and does not test")
    print("it: the endpoint is what recourse does to Maverick's own judgments, not")
    print("whether Maverick is the better judge.")
    print()
    paired = [r for r in rows.values() if r.get("source_verdict")]
    if not paired:
        print("  no re-judged rows: this index was not written by a rejudge tree.")
        return
    agree = sum(1 for r in paired if r["verdict"] == r["source_verdict"])
    grid = Counter((r["source_verdict"], r["verdict"]) for r in paired)
    print(f"{'':<22}{'maverick FLAWED':>20}{'maverick SOUND':>20}{'total':>10}")
    rule()
    for source in VERDICTS:
        row_total = sum(grid[(source, v)] for v in VERDICTS)
        print(f"{'nano ' + source:<22}{grid[(source, VERDICTS[0])]:>20}"
              f"{grid[(source, VERDICTS[1])]:>20}{row_total:>10}")
    rule()
    print(f"{'total':<22}"
          f"{sum(grid[(s, VERDICTS[0])] for s in VERDICTS):>20}"
          f"{sum(grid[(s, VERDICTS[1])] for s in VERDICTS):>20}{len(paired):>10}")
    print()
    print(f"  verdicts agreeing                      {rate(agree, len(paired))}")
    print(f"  maverick says FLAWED                   "
          f"{rate(sum(1 for r in paired if r['verdict'] == 'FLAWED'), len(paired))}")
    print(f"  nano says FLAWED                       "
          f"{rate(sum(1 for r in paired if r['source_verdict'] == 'FLAWED'), len(paired))}"
          )
    labelled = [r for r in paired if r.get("initially_correct") is not None
                and r.get("source_correct") is not None]
    mav = sum(1 for r in labelled if r["initially_correct"])
    nano = sum(1 for r in labelled if r["source_correct"])
    print()
    print(f"  accuracy maverick (M0)                 {acc(mav, len(labelled))}")
    print(f"  accuracy nano (the sweep)              {acc(nano, len(labelled))}")
    fixed = sum(1 for r in labelled
                if not r["source_correct"] and r["initially_correct"])
    broken = sum(1 for r in labelled
                 if r["source_correct"] and not r["initially_correct"])
    p = mcnemar_exact(fixed, broken)
    print(f"  maverick right where nano was wrong    {fixed}")
    print(f"  maverick wrong where nano was right    {broken}")
    print(f"  NET                                    {fixed - broken:+d} cells")
    print(f"  exact two-sided McNemar                p = {p:.6g}   "
          "REPORTED, NOT TESTED (descriptive in PREREG)")
    print()
    print("  by gold label:")
    for gold, name in ((True, "flawed items"), (False, "sound items")):
        subset = [r for r in labelled if r.get("gold_flawed") is gold]
        if not subset:
            continue
        print(f"    {name:<16} n={len(subset):<4} "
              f"maverick {rate(sum(1 for r in subset if r['initially_correct']), len(subset))}"
              f"   nano {rate(sum(1 for r in subset if r['source_correct']), len(subset))}")


# --------------------------------------------------------------------------- #
# (b) the judgment as a document
# --------------------------------------------------------------------------- #


def section_b(runs: list[dict]) -> None:
    head("(b) THE JUDGMENT AS A DOCUMENT — length, parse, repairs, cells lost")
    print("The judgment is the text the auditor audits and the recourse judge is later")
    print("shown, so a judge that answers before it explains leaves nothing to audit.")
    print("`raw` is the whole reply and is what `decision_grounds` hands the challenger;")
    print("`reasoning` is everything before the decisive `Verdict:` line.")
    print()
    done = [r for r in runs if r["manifest"].get("status") == "completed"]
    failed = [r for r in runs if r["manifest"].get("status") == "failed"]
    other = [r for r in runs if r["manifest"].get("status") not in ("completed", "failed")]
    print(f"  run directories                        {len(runs)}")
    print(f"  completed (a verdict on disk)          {rate(len(done), len(runs))}")
    print(f"  failed (counted, left undecided)       {rate(len(failed), len(runs))}")
    if other:
        print(f"  neither — left `running` by a crash     {len(other)}")
    for entry in failed:
        error = entry["manifest"].get("error", "")
        print(f"    ! {entry['manifest'].get('cell_id', entry['dir'].name)}: {error[:90]}")
    if failed:
        kinds = Counter("truncated" if "Truncated" in (e["manifest"].get("error") or "")
                        else "malformed/other" for e in failed)
        print(f"  failure kinds                          {dict(kinds)}")
    verdicts = [r["verdict"] for r in done if r["verdict"]]
    if not verdicts:
        return
    raw = sorted(words(v.get("raw", "")) for v in verdicts)
    reasoning = sorted(words(v.get("reasoning", "")) for v in verdicts)
    print()
    for name, lengths in (("judgment (raw)", raw), ("grounds (reasoning)", reasoning)):
        quantiles = [lengths[0], lengths[len(lengths) // 4], lengths[len(lengths) // 2],
                     lengths[(3 * len(lengths)) // 4], lengths[-1]]
        print(f"  {name:<22} words  min {quantiles[0]:>5}  p25 {quantiles[1]:>5}  "
              f"median {quantiles[2]:>5}  p75 {quantiles[3]:>5}  max {quantiles[4]:>5}"
              f"   mean {statistics.mean(lengths):.0f}")
    empty = sum(1 for v in verdicts if not (v.get("reasoning") or "").strip())
    print(f"  judgments with NO stated grounds       {rate(empty, len(verdicts))}"
          "   (the judge answered before it explained; nothing to audit)")
    print()
    print(f"  parse modes                            "
          f"{dict(Counter(v.get('parse_mode') for v in verdicts))}")
    print(f"  finish reasons                         "
          f"{dict(Counter(v.get('finish_reason') for v in verdicts))}")
    repaired = sum(1 for v in verdicts if v.get("repair_attempts"))
    print(f"  judgments that needed a format repair  {rate(repaired, len(verdicts))}")
    native = sum(1 for v in verdicts if (v.get("native_reasoning") or "").strip())
    print(f"  judgments with PROVIDER-side reasoning {rate(native, len(verdicts))}"
          "   (must be 0: reasoning_effort = off)")


# --------------------------------------------------------------------------- #
# (c) the audit funnel, beside pilot 2's
# --------------------------------------------------------------------------- #


def funnel(rows: dict[str, dict]) -> dict:
    """Every column of the funnel for one tree, as plain numbers."""
    values = list(rows.values())
    n = len(values)
    contested = [r for r in values if r.get("challenge_stance") == "contests"]
    declined = [r for r in values if r.get("challenge_stance") == "declined"]
    unclear = [r for r in values if r.get("challenge_stance") == "unclear"]
    graded = [r for r in values if r.get("grade_valid") is not None]
    valid = [r for r in graded if r["grade_valid"]]
    ruled = [r for r in values if r.get("ruling_form")]
    overturned = [r for r in ruled if r.get("changed_the_decision")]
    wrong = [r for r in values if r.get("initially_correct") is False]
    right = [r for r in values if r.get("initially_correct") is True]
    ruled_wrong = [r for r in wrong if r.get("ruling_form")]
    ruled_right = [r for r in right if r.get("ruling_form")]
    read = [r for r in ruled if r.get("ruling_line_mismatch") is not None]
    strict_read = [r for r in read if r.get("ruling_prose_conclusion") in VERDICTS]
    labelled = [r for r in values if r.get("initially_correct") is not None]
    fixed = sum(1 for r in labelled
                if not r["initially_correct"] and after_state(r))
    broken = sum(1 for r in labelled if r["initially_correct"] and not after_state(r))
    return {
        "n": n,
        "incorrect": len(wrong),
        "correct": len(right),
        "accuracy_before": (sum(1 for r in labelled if r["initially_correct"]),
                            len(labelled)),
        "raised": len(contested),
        "declined": len(declined),
        "unclear": len(unclear),
        "graded": len(graded),
        "valid": len(valid),
        "defects": sum(r.get("challenge_defects_n") or 0 for r in contested),
        "defects_valid": sum(r.get("grade_defects_valid_n") or 0 for r in graded),
        "misattributed": sum(r.get("challenge_defects_misattributed_n") or 0
                             for r in contested),
        "phantom": sum(1 for r in contested if r.get("phantom_contest")),
        "phantom_measured": sum(1 for r in contested
                                if r.get("phantom_contest") is not None),
        "grade_line_mismatch": sum(1 for r in graded if r.get("grade_line_mismatch")),
        "ruled": len(ruled),
        "overturned": len(overturned),
        "overturn_wrong": (sum(1 for r in ruled_wrong if r.get("changed_the_decision")),
                           len(ruled_wrong)),
        "overturn_right": (sum(1 for r in ruled_right if r.get("changed_the_decision")),
                           len(ruled_right)),
        "mismatch_conservative": (sum(1 for r in read if r["ruling_line_mismatch"]),
                                  len(read)),
        "mismatch_strict": (sum(1 for r in strict_read if r["ruling_line_mismatch"]),
                            len(strict_read)),
        "fixed": fixed,
        "broken": broken,
        "accuracy_after": (sum(1 for r in labelled if after_state(r)), len(labelled)),
    }


def after_state(row):
    """The cell's state once recourse has had its turn — `final_correct` where a ruling
    exists, the decision's own correctness otherwise. The same definition
    `judgment-debate-2.py`, `judgment-debate-vs-alone.py` and `metrics.json` take."""
    final = row.get("final_correct")
    return row.get("initially_correct") if final is None else bool(final)


def section_c(jd3: dict, pilot2: dict) -> None:
    head("(c) THE AUDIT FUNNEL — jd3 pilot (Maverick judges AND rules) vs "
         "judgment-debate-pilot-2 (nano)")
    print("The same 60 pilot-3 debate cells, the same stored debates, the same")
    print("challenger, grader and prompts. What differs is the judge in BOTH seats — and")
    print("in jd3 the judgments themselves are Maverick's, so the audit is of a different")
    print("document, not of the same one under a different ruler. Two 60-cell runs at")
    print("challenger_temperature 0.7 also differ by SAMPLING, so no line below is a")
    print("finding; what is being checked is that the instrument still works.")
    print()
    left, right = funnel(jd3), (funnel(pilot2) if pilot2 else None)

    def show(label, key, formatter=None):
        def render(f):
            if f is None:
                return "—"
            value = f[key]
            if formatter:
                return formatter(value)
            if isinstance(value, tuple):
                return rate(*value)
            return str(value)
        print(f"  {label:<40}{render(left):>26}{render(right):>26}")

    print(f"  {'':<40}{'jd3 (maverick)':>26}{'pilot 2 (nano)':>26}")
    rule()
    show("cells", "n")
    show("decided wrong before recourse", "incorrect")
    show("accuracy before recourse", "accuracy_before")
    rule()
    show("objections raised (contests)", "raised")
    show("declined", "declined")
    show("unreadable line (unclear)", "unclear")
    show("phantom contests", "phantom")
    show("defects alleged", "defects")
    show("defects on a misattributed quote", "misattributed")
    rule()
    show("objections graded", "graded")
    show("graded VALID", "valid")
    show("defects the grader verified", "defects_valid")
    show("grader line-vs-prose mismatch", "grade_line_mismatch")
    rule()
    show("rulings made", "ruled")
    show("overturns", "overturned")
    show("overturn | decision was WRONG", "overturn_wrong")
    show("overturn | decision was RIGHT", "overturn_right")
    show("ruling_line_mismatch STRICT", "mismatch_strict")
    show("ruling_line_mismatch CONSERVATIVE", "mismatch_conservative")
    rule()
    show("fixed (wrong -> right)", "fixed")
    show("broken (right -> wrong)", "broken")
    print(f"  {'net':<40}{left['fixed'] - left['broken']:>+26d}"
          f"{(right['fixed'] - right['broken']) if right else 0:>+26d}")
    show("accuracy after recourse", "accuracy_after")
    p_left = mcnemar_exact(left["fixed"], left["broken"])
    p_right = mcnemar_exact(right["fixed"], right["broken"]) if right else None
    print(f"  {'exact two-sided McNemar':<40}{'p = ' + f'{p_left:.4g}':>26}"
          f"{('p = ' + f'{p_right:.4g}') if p_right is not None else '—':>26}")
    rule()
    print("  n = 60 measures NO accuracy difference. The endpoint is the 1,644-cell run")
    print("  and its alpha is in the pre-registration; these two columns are here to")
    print("  show the instrument produced numbers of the same shape.")
    for name, f in (("jd3", left), ("pilot 2", right)):
        if f is None:
            continue
        derived = f["overturn_wrong"], f["overturn_right"]
        if derived[0][1] and derived[1][1]:
            discrimination = (100.0 * derived[0][0] / derived[0][1]
                              - 100.0 * derived[1][0] / derived[1][1])
            print(f"  discrimination ({name}): overturn on wrong minus overturn on "
                  f"right = {discrimination:+.1f} pts")


def section_c_types(tree: Path) -> None:
    """Defect types, off the objections themselves — the index counts them but does not
    say what was alleged, and the specious clause of jd2 turned on the TYPE."""
    head("(c2) WHAT THE AUDITOR ALLEGED, BY DEFECT TYPE")
    types: Counter = Counter()
    misattributed: Counter = Counter()
    for path in sorted(tree.glob("cells/*/contests/*/runs/*/challenge.json")):
        try:
            challenge = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if challenge.get("stance") != "contests":
            continue
        for defect in challenge.get("defects") or []:
            types[defect.get("type")] += 1
            if defect.get("quote_in_judgment") is False:
                misattributed[defect.get("type")] += 1
    total = sum(types.values())
    print(f"  defects alleged: {total}")
    for kind, count in types.most_common():
        print(f"    {str(kind):<18} {rate(count, total)}"
              f"   of which misattributed: {misattributed[kind]}")


# --------------------------------------------------------------------------- #
# (d) spend and wall-clock
# --------------------------------------------------------------------------- #

# What each role's per-call cost is multiplied by in the full run. The population is the
# 1,644 decided debate cells of the sweep and the raise rate this pilot measures.
FULL_CELLS = 1644


def section_d(calls: list[dict], f: dict, started: str | None,
              finished: str | None) -> None:
    head("(d) SPEND AND WALL-CLOCK — measured here, scaled to the full run")
    print("Off this tree's own `calls.jsonl`, every attempt including format repairs.")
    print("Two logs are skipped, both copies of money spent elsewhere: "
          "`calls.source.jsonl`,")
    print("the debate's own log copied beside each re-judged decision (the sweep paid for")
    print("that), and `parent/calls.jsonl`, this tree's decision log copied again inside")
    print("every contest — the same exclusion `accounting.aggregate_tree` makes, and the")
    print("reason the TOTAL below equals the driver's own `spend so far`.")
    print()
    by_role: dict[str, list[dict]] = {}
    for call in calls:
        by_role.setdefault(call.get("role") or "?", []).append(call)
    total = 0.0
    print(f"  {'role':<22}{'calls':>8}{'cost $':>12}{'$/call':>12}"
          f"{'median s':>11}{'p95 s':>9}  model")
    rule()
    for role in sorted(by_role):
        entries = by_role[role]
        cost = sum((c.get("usage") or {}).get("cost") or 0.0 for c in entries)
        total += cost
        latencies = sorted((c.get("latency_ms") or 0) / 1000.0 for c in entries)
        p95 = latencies[min(len(latencies) - 1, int(0.95 * len(latencies)))]
        model = Counter(c.get("response_model") for c in entries).most_common(1)[0][0]
        print(f"  {role:<22}{len(entries):>8}{cost:>12.4f}{cost / len(entries):>12.5f}"
              f"{statistics.median(latencies):>11.1f}{p95:>9.1f}  {model}")
    rule()
    print(f"  {'TOTAL':<22}{len(calls):>8}{total:>12.4f}")
    statuses = Counter(c.get("status") for c in calls)
    print(f"  wire statuses                          {dict(statuses)}")
    if started and finished:
        print(f"  wall-clock                             {started} -> {finished}")
    print()

    def per(role_names, denominator):
        entries = [c for c in calls if (c.get("role") or "") in role_names]
        cost = sum((c.get("usage") or {}).get("cost") or 0.0 for c in entries)
        return (cost / denominator) if denominator else 0.0

    rejudge_per_cell = per({"judge"}, f["n"]) if f["n"] else 0.0
    contest_per_cell = per({"challenger", "comprehension"}, f["n"]) if f["n"] else 0.0
    agreement_per = per({"agreement"}, f["raised"] + f["declined"]) if (
        f["raised"] + f["declined"]) else 0.0
    ruling_per = per({"recourse_judge"}, f["ruled"]) if f["ruled"] else 0.0
    reader_per = per({"ruling_reader"}, f["ruled"]) if f["ruled"] else 0.0
    grade_per = per({"judgment_grader"}, f["graded"]) if f["graded"] else 0.0
    raise_rate = f["raised"] / f["n"] if f["n"] else 0.0
    ruled_rate = f["ruled"] / f["n"] if f["n"] else 0.0
    graded_rate = f["graded"] / f["n"] if f["n"] else 0.0

    print(f"  MEASURED UNIT COSTS (the denominator is what that stage actually served)")
    print(f"    rejudge, per decided cell            ${rejudge_per_cell:.5f}")
    print(f"    contest + probe, per cell            ${contest_per_cell:.5f}")
    print(f"    agreement, per readable objection    ${agreement_per:.5f}")
    print(f"    ruling, per ruling                   ${ruling_per:.5f}")
    print(f"    ruling reader, per ruling            ${reader_per:.5f}")
    print(f"    judgment grade, per graded objection ${grade_per:.5f}")
    print(f"    raise rate {pct(f['raised'], f['n'])}   ruled {pct(f['ruled'], f['n'])}"
          f"   graded {pct(f['graded'], f['n'])}")
    print()
    m1 = (FULL_CELLS * rejudge_per_cell + FULL_CELLS * contest_per_cell
          + FULL_CELLS * agreement_per * ((f["raised"] + f["declined"]) / f["n"])
          + FULL_CELLS * ruled_rate * (ruling_per + reader_per)
          + FULL_CELLS * graded_rate * grade_per)
    m2 = FULL_CELLS * raise_rate * (ruling_per + reader_per)
    m3 = (FULL_CELLS * contest_per_cell + FULL_CELLS * agreement_per
          + FULL_CELLS * (ruling_per + reader_per) + FULL_CELLS * grade_per)
    print(f"  SCALED TO {FULL_CELLS} DECIDED DEBATE CELLS")
    print(f"    M0 + M1  rejudge + contest + agreement + rulings + readers + grades"
          f"   ${m1:.2f}")
    print(f"    M2       placeholder rulings + readers on the cells M1 contested"
          f"        ${m2:.2f}")
    print(f"    M3       specious contest on ALL cells + agreement + grade + rulings"
          f"     ${m3:.2f}")
    print(f"    TOTAL                                                              "
          f"      ${m1 + m2 + m3:.2f}")
    print(f"    with 1.3x headroom                                                 "
          f"      ${1.3 * (m1 + m2 + m3):.2f}")
    print()
    judge_calls = [c for c in calls if c.get("role") == "judge"]
    if judge_calls:
        latencies = sorted((c.get("latency_ms") or 0) / 1000.0 for c in judge_calls)
        p95 = latencies[min(len(latencies) - 1, int(0.95 * len(latencies)))]
        print(f"  Maverick judge p95 {p95:.1f}s at 16 concurrent -> "
              f"{FULL_CELLS * p95 / 16 / 60:.0f} min for {FULL_CELLS} judgments")
    ruling_calls = [c for c in calls if c.get("role") == "recourse_judge"]
    if ruling_calls:
        latencies = sorted((c.get("latency_ms") or 0) / 1000.0 for c in ruling_calls)
        p95 = latencies[min(len(latencies) - 1, int(0.95 * len(latencies)))]
        print(f"  Maverick ruling p95 {p95:.1f}s at 16 concurrent -> "
              f"{FULL_CELLS * ruled_rate * p95 / 16 / 60:.0f} min for the rulings")
    challenger_calls = [c for c in calls if c.get("role") == "challenger"]
    if challenger_calls:
        latencies = sorted((c.get("latency_ms") or 0) / 1000.0 for c in challenger_calls)
        p95 = latencies[min(len(latencies) - 1, int(0.95 * len(latencies)))]
        print(f"  flash audit p95 {p95:.1f}s at 16 concurrent -> "
              f"{FULL_CELLS * p95 / 16 / 60:.0f} min for {FULL_CELLS} audits")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tree", type=Path,
                        default=Path("outputs/experiments/jd3-pilot"))
    parser.add_argument("--index", type=Path, default=None,
                        help="defaults to <tree>/index.jsonl")
    parser.add_argument("--pilot2-index", type=Path,
                        default=Path("outputs/experiments/judgment-debate-pilot-2/"
                                     "index.jsonl"))
    parser.add_argument("--started", default=None)
    parser.add_argument("--finished", default=None)
    args = parser.parse_args()

    index = args.index or (args.tree / "index.jsonl")
    rows = load_index(index)
    pilot2 = load_index(args.pilot2_index)

    head("jd3 PILOT — ONE JUDGE THROUGHOUT, ON THE 60 pilot-3 DEBATE CELLS")
    print(f"  tree            {args.tree}")
    print(f"  index           {index}   ({len(rows)} rows)")
    print(f"  pilot 2 index   {args.pilot2_index}   ({len(pilot2)} rows)")
    experiment = args.tree / "experiment.json"
    if experiment.is_file():
        spec = json.loads(experiment.read_text(encoding="utf-8"))
        print(f"  transcripts_from {spec.get('transcripts_from')}   "
              f"sha256 {str(spec.get('transcripts_from_experiment_sha256'))[:16]}")
        print(f"  judge            {spec['config']['judge_model']}")
        print(f"  recourse judge   {spec['config']['recourse_judge_model']}")
        print(f"  challenger       {spec['config']['challenger_model']}   "
              f"variant {spec['config']['challenger_variant']}")
        print(f"  grader           {spec['grading']['grader_model']}")

    section_a(rows)
    section_b(load_runs(args.tree))
    section_c(rows, pilot2)
    section_c_types(args.tree)
    section_d(load_calls(args.tree), funnel(rows), args.started, args.finished)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

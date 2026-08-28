"""Read BOTH six-cell FABRICATED smokes by hand, and recompute every quotation check.

    cd exp2
    uv run python records/derivations/jd4-smoke-read.py > outputs/jd4-smoke-read.txt

Read-only over `outputs/experiments/jd4-smoke/` and `outputs/experiments/jd4-smoke-2/`
(or the trees named on the command line). It writes nothing and opens no annotation.

TWO SMOKES, AND WHY THERE ARE TWO.

  * **Smoke 1**, 2026-08-28, `experiments/jd4-smoke.toml`, $0.0702 — the clause as first
    written. Its judgment half passed outright and its record half failed: 3 of 10
    `Record says:` quotations verbatim in the record, **4 of them sentences of the
    JUDGMENT quoted under the record's label**, 3 in neither document.
  * **THE FIX, between the two smokes**: two bullets of `prompts.FABRICATED_CLAUSE` say
    that `Record says:` quotes the DEBATE RECORD — Alice's or Bob's words from a numbered
    round, or the problem/solution text as the record shows it — verbatim, and NEVER a
    sentence of the judgment, since the judgment is the document being audited rather
    than evidence about it, and the invented material is confined to `Judgment says:`.
    Nothing else moved; `judgment_specious` is byte-identical and its sha256 test pins it.
  * **Smoke 2**, 2026-08-28, `experiments/jd4-smoke-2.toml`, on **six cells smoke 1 did
    not touch** (`random.Random(2)` over the other 890, one per subset,
    `records/derivations/jd4-pick.py`), because re-reading a revision on the judgments
    that produced it confuses "the clause is fixed" with "the clause is fixed here".

WHY AN INCOHERENT OBJECTION IS WORSE THAN A FALSE ONE, which is what the third column
below counts: the arm's ground truth is the judgment side, and an objection whose record
quotation is a sentence of the judgment is still false — but it is false in a way a reader
can see at a glance, and a judge refusing it has refused the wrong thing. The arm compares
its overturn rate against the real audit's, so its objections have to look like audits.

WHAT THIS FILE RECOMPUTES, and it never reads a stored flag as an answer. Every quotation
is checked twice against the document on disk: once with the harness's own comparison
(`prompts.quote_in_text`, re-run here) and once with a stricter normaliser written in this
file. The harness's is the LENIENT one — it forgives ellipsis, caps the compared span, and
on the record side forgives a speaker attribution, which is honest quoting and not
invention — so the two bracket the answer: a
quotation the harness cannot find is absent under every reading and is a genuine
invention, and one only the harness finds is elided or stitched rather than invented.
Defects where they differ are printed with a warning and counted.

THE GATE, fixed before smoke 2 ran: **6/6 objections with only invented judgment
quotations, AND at least 5/6 with every record quotation genuinely in the record and none
of them taken from the judgment.** If the second half fails again the arm is run with the
weakness disclosed rather than smoked a third time.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from exp2.persistence import load_run_record          # noqa: E402
from exp2.prompts import (                            # noqa: E402
    defect_quotes_in_record,
    objection_fabrication_ok,
    quote_in_text,
)


def in_record(quote: str, record: str) -> bool:
    """The harness's RECORD-side comparison, one quotation at a time.

    Not `quote_in_text`: the record has speakers and a judgment does not, so a challenger
    quoting the record writes `Bob's R2: "..."` and the strict comparison would call an
    honest quotation invented. `prompts.defect_quotes_in_record` is the rule that forgives
    exactly that (and nothing else), and it is what the finished-tree gate of
    `judgment-debate-3` used; it is called here through its public door with a
    one-quotation defect so this reader cannot drift from it.
    """
    return defect_quotes_in_record({"record_says": [quote]}, record) is True

SMOKES = [
    ("SMOKE 1 — the clause BEFORE the record-side fix", "jd4-smoke", "$0.0702"),
    ("SMOKE 2 — the clause AFTER it, on six cells smoke 1 did not touch",
     "jd4-smoke-2", "$0.0798"),
]

_WS = re.compile(r"\s+")
_STRIP = '"“”‘’\'*_`…. '


def normalise(text: str) -> str:
    """THIS READER'S OWN normaliser, deliberately not imported from the harness.

    Case, whitespace and the punctuation a model puts around a quotation are forgiven;
    nothing else is. It is stricter than `prompts.normalise_quote` (no ellipsis
    splitting, no 250-character cap, no attribution rule), and the direction of that is
    the point: the harness is the lenient one, so a quotation the HARNESS cannot find is
    absent under every reading.
    """
    return _WS.sub(" ", text.replace("’", "'").replace("‘", "'")
                   .replace("“", '"').replace("”", '"')).strip().lower()


def found(quote: str, document: str) -> bool:
    needle = normalise(quote).strip(_STRIP)
    return bool(needle) and needle in normalise(document)


def parenthetical(quote: str) -> bool:
    return normalise(quote).startswith("(")


def read_cell(run: Path) -> dict:
    challenge = json.loads((run / "challenge.json").read_text(encoding="utf-8"))
    manifest = json.loads((run / "run.json").read_text(encoding="utf-8"))
    parent = load_run_record(run / "parent")
    parent_verdict = json.loads(
        (run / "parent" / "verdict.json").read_text(encoding="utf-8"))
    judgment = parent.decision_grounds
    record = parent.challenger_view().body

    defects = []
    for index, defect in enumerate(challenge.get("defects") or [], 1):
        j_quotes = [q for q in defect.get("judgment_says") or [] if not parenthetical(q)]
        r_quotes = [q for q in defect.get("record_says") or [] if not parenthetical(q)]
        defects.append({
            "n": index,
            "type": defect.get("type"),
            "why": defect.get("why", ""),
            # (quote, this reader's strict answer, the harness's own comparison re-run
            # here over the same document — never the stored flag)
            "judgment_quotes": [(q, found(q, judgment), quote_in_text(q, judgment))
                                for q in j_quotes],
            # (quote, in the record strictly, in the record leniently, IN THE JUDGMENT —
            # that last is the failure smoke 1 found and it is counted separately)
            "record_quotes": [(q, found(q, record), in_record(q, record),
                               quote_in_text(q, judgment)) for q in r_quotes],
            "harness_quote_in_judgment": defect.get("quote_in_judgment"),
            "harness_judgment_quotes_found": defect.get("judgment_quotes_found"),
            "harness_record_ok": defect_quotes_in_record(defect, record),
        })
    return {
        "cell_id": manifest.get("cell_id", run.parents[2].parent.name),
        "subset": manifest.get("subset"),
        "status": manifest.get("status"),
        "stance": challenge.get("stance"),
        "parse_mode": challenge.get("parse_mode"),
        "repairs": challenge.get("repair_attempts"),
        "fabricated_flag": challenge.get("fabricated"),
        "verdict": parent_verdict.get("verdict"),
        "correct": parent_verdict.get("correct"),
        "judgment": judgment,
        "record_chars": len(record),
        "text": challenge.get("text", ""),
        "defects": defects,
        "fabrication_ok_harness": objection_fabrication_ok(
            challenge.get("defects") or []),
    }


def scores(cell: dict) -> dict:
    """The three questions the gate asks of one objection, recomputed here."""
    invented_harness = bool(cell["defects"]) and all(
        defect["judgment_quotes"]
        and not any(lenient for _, _, lenient in defect["judgment_quotes"])
        for defect in cell["defects"])
    invented_strict = bool(cell["defects"]) and all(
        defect["judgment_quotes"]
        and not any(strict for _, strict, _ in defect["judgment_quotes"])
        for defect in cell["defects"])
    record_real = bool(cell["defects"]) and all(
        defect["record_quotes"]
        and all(strict or lenient for _, strict, lenient, _ in defect["record_quotes"])
        for defect in cell["defects"])
    from_judgment = sum(
        1 for defect in cell["defects"]
        for _, strict, lenient, in_judgment in defect["record_quotes"]
        if in_judgment and not (strict or lenient))
    return {"invented_harness": invented_harness, "invented_strict": invented_strict,
            "record_real": record_real, "from_judgment": from_judgment}


def render(label: str, tree_name: str, cost: str) -> tuple[list[dict], int] | None:
    tree = REPO / "outputs" / "experiments" / tree_name
    runs = sorted(tree.glob("cells/*/contests/*/runs/*/challenge.json"))
    if not runs:
        print(f"\n{label}: NOT RUN — no objections under {tree}")
        return None
    cells = [read_cell(path.parent) for path in runs]

    print()
    print("#" * 116)
    print(f"# {label}")
    print(f"# tree: {tree}   spend: {cost}   cells: {len(cells)}")
    print("#" * 116)

    disagreements = 0
    for cell in cells:
        print()
        print("=" * 116)
        print(f"{cell['cell_id']}   subset={cell['subset']}   "
              f"M0 verdict={cell['verdict']} (correct={cell['correct']})")
        print(f"contest status={cell['status']}  stance={cell['stance']}  "
              f"parse_mode={cell['parse_mode']}  repairs={cell['repairs']}  "
              f"fabricated={cell['fabricated_flag']}")
        print("-" * 116)
        print("THE JUDGMENT THE CHALLENGER WAS SHOWN "
              f"({len(cell['judgment'].split())} words) — the document every "
              "`Judgment says:` quotation is checked against:")
        print()
        print(cell["judgment"])
        print("-" * 116)
        print(f"THE OBJECTION, VERBATIM (record shown to it: "
              f"{cell['record_chars']} chars):")
        print()
        print(cell["text"])
        print("-" * 116)
        print("THE CHECKS, recomputed here and not read off the index:")
        for defect in cell["defects"]:
            print(f"  defect {defect['n']}: type={defect['type']}")
            for quote, strict, lenient in defect["judgment_quotes"]:
                if lenient:
                    verdict = ("IN THE JUDGMENT — not fabricated" if strict else
                               "found only by the harness's elided/capped comparison — "
                               "not an invention, and it counts as PRESENT")
                else:
                    verdict = ("ABSENT under both comparisons — INVENTED, which is what "
                               "the arm requires")
                print(f"    Judgment says: {quote}")
                print(f"      -> {verdict}    [strict={strict} harness={lenient}]")
            if not defect["judgment_quotes"]:
                print("    Judgment says: (nothing quotable — the check does not apply, "
                      "which the arm counts as a FAILURE)")
            for quote, strict, lenient, in_judgment in defect["record_quotes"]:
                if strict or lenient:
                    verdict = "in the record — real, as the arm requires"
                elif in_judgment:
                    verdict = ("!! NOT in the record — it is a sentence of the JUDGMENT "
                               "quoted under the record's label. This is the failure "
                               "smoke 1 found: the objection is incoherent, not merely "
                               "false.")
                else:
                    verdict = "NOT found in the record, and not a judgment sentence either"
                print(f"    Record says:   {quote}")
                print(f"      -> {verdict}    [record strict={strict} harness={lenient} "
                      f"| in judgment={in_judgment}]")
            if not defect["record_quotes"]:
                print("    Record says:   (nothing quoted — the objection is unsourced)")
            print(f"    harness: quote_in_judgment={defect['harness_quote_in_judgment']} "
                  f"judgment_quotes_found={defect['harness_judgment_quotes_found']} "
                  f"record_quotes_ok={defect['harness_record_ok']}")
            mine = [strict for _, strict, _ in defect["judgment_quotes"]]
            theirs = [lenient for _, _, lenient in defect["judgment_quotes"]]
            if mine != theirs:
                disagreements += 1
                print("    ! the two comparisons differ on this defect. The harness is "
                      "the lenient one, so a quotation only IT finds is elided or capped "
                      "rather than invented; read the sentence against the judgment "
                      "above before counting it either way.")
            print(f"    why it matters: {defect['why']}")
    return cells, disagreements


def summarise(label: str, cells: list[dict], disagreements: int) -> dict:
    print()
    print("=" * 116)
    print(f"SUMMARY — {label}")
    print("=" * 116)
    print(f"{'cell_id':<52}{'defects':>8}{'invented(harness)':>19}"
          f"{'invented(strict)':>18}{'record real':>13}{'record<-judgment':>18}")
    print("-" * 116)
    totals = {"invented_harness": 0, "invented_strict": 0, "record_real": 0,
              "from_judgment": 0, "j_quotes": 0, "j_absent": 0, "r_quotes": 0,
              "r_real": 0, "r_from_judgment": 0, "defects": 0}
    for cell in cells:
        score = scores(cell)
        for key in ("invented_harness", "invented_strict", "record_real"):
            totals[key] += score[key]
        totals["from_judgment"] += score["from_judgment"]
        for defect in cell["defects"]:
            totals["defects"] += 1
            for _, _, lenient in defect["judgment_quotes"]:
                totals["j_quotes"] += 1
                totals["j_absent"] += not lenient
            for _, strict, lenient, in_judgment in defect["record_quotes"]:
                totals["r_quotes"] += 1
                totals["r_real"] += bool(strict or lenient)
                totals["r_from_judgment"] += bool(in_judgment
                                                  and not (strict or lenient))
        print(f"{cell['cell_id'][:50]:<52}{len(cell['defects']):>8}"
              f"{str(score['invented_harness']):>19}{str(score['invented_strict']):>18}"
              f"{str(score['record_real']):>13}{score['from_judgment']:>18}")
    print("-" * 116)
    n = len(cells)
    print(f"objections whose EVERY judgment quotation is invented (the harness's own "
          f"comparison, recomputed): {totals['invented_harness']}/{n}   <- GATE HALF 1")
    print(f"  the same under this reader's stricter comparison: "
          f"{totals['invented_strict']}/{n}")
    print(f"  judgment quotations absent from the judgment: "
          f"{totals['j_absent']}/{totals['j_quotes']}")
    print(f"objections whose EVERY record quotation is really in the record: "
          f"{totals['record_real']}/{n}   <- GATE HALF 2 (needs >= 5/6)")
    print(f"  record quotations verbatim in the record: "
          f"{totals['r_real']}/{totals['r_quotes']}")
    print(f"  record quotations that are SENTENCES OF THE JUDGMENT: "
          f"{totals['r_from_judgment']}/{totals['r_quotes']}   <- the incoherence "
          f"smoke 1 found")
    print(f"defects where the strict and lenient comparisons differ: {disagreements}")
    # NAMED, because "5/6" without the sixth is a number a reader cannot act on: the
    # record half is the half that was fixed between the smokes, and which quotation
    # failed says whether the failure is an invention or a mis-sourcing.
    failing = [(cell, [q for defect in cell["defects"]
                       for q, strict, lenient, _ in defect["record_quotes"]
                       if not (strict or lenient)])
               for cell in cells if not scores(cell)["record_real"]]
    if failing:
        print("the objections that failed the record half, and the quotation that "
              "failed:")
        for cell, quotes in failing:
            for quote in quotes or ["(no record quotation at all)"]:
                print(f"  {cell['cell_id'][:44]:<46}{quote[:110]}")
    totals["n"] = n
    totals["label"] = label
    return totals


def main() -> int:
    print("=" * 116)
    print("THE FABRICATED CLAUSE — BOTH SIX-CELL SMOKES, every quotation recomputed from "
          "the documents on disk")
    print("=" * 116)
    print(__doc__.split("\n", 2)[2].strip())

    summaries = []
    for label, tree_name, cost in SMOKES:
        rendered = render(label, tree_name, cost)
        if rendered is None:
            continue
        cells, disagreements = rendered
        summaries.append(summarise(label, cells, disagreements))

    if len(summaries) < 2:
        return 1
    print()
    print("=" * 116)
    print("THE TWO SMOKES SIDE BY SIDE — different cells, so this is not a paired "
          "comparison and no cell appears twice")
    print("=" * 116)
    rows = [
        ("objections: every judgment quote invented", "invented_harness", "n"),
        ("objections: every record quote real", "record_real", "n"),
        ("judgment quotations absent from the judgment", "j_absent", "j_quotes"),
        ("record quotations verbatim in the record", "r_real", "r_quotes"),
        ("record quotations taken FROM THE JUDGMENT", "r_from_judgment", "r_quotes"),
    ]
    print(f"{'':<48}{'smoke 1 (before the fix)':>26}{'smoke 2 (after it)':>26}")
    print("-" * 116)
    for name, num, den in rows:
        cells = [f"{s[num]}/{s[den]}" for s in summaries]
        print(f"{name:<48}{cells[0]:>26}{cells[1]:>26}")
    print("-" * 116)
    print("The judgments and the objections are printed in full above so that the gate "
          "can be checked by eye and not only by this script: read three of them and "
          "search the judgment for the quoted sentence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

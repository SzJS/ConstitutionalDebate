"""SOURCE vs RERULE: the same objections, ruled by two different ruling lines.

The re-contest (`records/experiments/recontest/`) found that a weak third-party judge
asked for `Ruling: UPHOLD|OVERTURN` contradicted its own reasoning on FLAWED parents —
"the objection is valid" and "the text is flawed" were both being mapped onto OVERTURN.
The fix asks the judge for an **absolute conclusion** about the text under review and
derives UPHOLD/OVERTURN by comparing it with the decision (`ruling_form ==
"stated_conclusion"`), and a Haiku reading of the judge's own prose
(`ruling_agreement.json` → `ruling_line_mismatch`) measures the residual, exactly as the
`agreement` stage measures phantom objections on the challenger side.

A re-rule pass writes a **new tree** that re-rules the objections of a source tree
without touching it: same decisions, same objections, byte-identical challenge records —
only the ruling is made again. This script joins the two trees' `index.jsonl` on
`cell_id`, asserts that the decisions and the objections really are identical, and prints
every ruling-side rate side by side.

    uv run python records/derivations/rerule-compare.py \
        --source records/experiments/recontest/index.jsonl \
        --rerule records/experiments/rerule/recontest/index.jsonl

    uv run python records/derivations/rerule-compare.py \
        --source records/experiments/sweep/index.jsonl \
        --rerule records/experiments/rerule/sweep/index.jsonl

Defaults: `--source records/experiments/recontest/index.jsonl`,
`--rerule records/experiments/rerule/recontest/index.jsonl`.  The three trees are committed
as `records/experiments/rerule/{smoke,recontest,sweep}/`, one directory for the three.

**It reads the two committed indices and nothing else**, so it runs on a blank machine
straight after `git clone` — no `outputs/` tree, no `calls.jsonl`, no per-cell run
directory, no network, no API key. `--rerule-tree <dir>` is an *optional* cross-check:
given the rerule run tree it re-reads `ruling.json`, `ruling.source.json` and
`ruling_agreement.json` per cell and verifies the values this script derives from the
index against the records on disk. Nothing in any table below depends on it; without it
no per-cell directory is opened, and no field is silently reconstructed from one.

Everything the tables need is in the index. Two quantities are *derived* rather than
read, because `build_index` does not emit them and the arithmetic is exact:

  * a ruling's own verdict — `verdict` when `changed_the_decision` is false, the other
    verdict when it is true. `Ruling` enforces `resolve_ruling(ruling, parent) ==
    verdict`, so this inversion is the record, not an inference.
  * the projection of a re-ruling onto the whole grid — a cell that was re-ruled takes
    the new tree's outcome, a cell that was not keeps the source's. Every table that
    projects says so and prints how many cells were substituted.

The rerule index may cover fewer cells than the source (the smoke re-ruled 69 of the
re-contest's 464). Every comparison is restricted to the cells present in **both**
indices *and* carrying a ruling in the rerule tree; the JOIN block prints how many that
is and what was left out.

Definitions are shared with `records/derivations/sweep-phantom-corrected.py` and must
stay identical to it:

    phantom objection   challenge_stance == "contests" and prose_stance == "RIGHT"
    genuine objection   challenge_stance == "contests" and prose_stance == "WRONG"
    final verdict       the ruling's verdict if the contest produced a ruling,
                        else the decision's own verdict  (`final_correct` in the index)
    fixed / broken      not initially_correct and final_correct  /  the converse
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

CONDS = ("single", "self_critique", "debate")
POOLED = "POOLED"
VERDICTS = ("FLAWED", "SOUND")
# What `build_index` writes for a tree whose rulings came from the new line. The source
# tree may hold either historical form; the rerule tree must hold nothing else.
RERULE_FORM = "stated_conclusion"
SOURCE_FORMS = ("uphold_overturn", "restated_verdict", "stated_conclusion")

W = 96


# --------------------------------------------------------------------------- #
# small formatting helpers
# --------------------------------------------------------------------------- #


def pct(num, den):
    return f"{100.0 * num / den:.1f}%" if den else "n/a"


def rate(num, den):
    """`12/62 19.4%` — every rate in this script is printed with its n."""
    return f"{num}/{den} {pct(num, den)}" if den else f"{num}/0 n/a"


def rule(char="-"):
    print(char * W)


def head(title):
    print()
    rule("=")
    print(title)
    rule("=")


def pad(text, width):
    """Left-justify, but never let two columns run together when one overflows."""
    return text.ljust(width) if len(text) < width else text + "  "


def other(verdict):
    return VERDICTS[1] if verdict == VERDICTS[0] else VERDICTS[0]


# --------------------------------------------------------------------------- #
# the join
# --------------------------------------------------------------------------- #


def load(path: Path) -> dict[str, dict]:
    rows = {}
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        rows[row["cell_id"]] = row
    return rows


def ruled(row) -> bool:
    """A ruling exists in this tree for this cell."""
    return row.get("ruling_form") is not None


def overturned(row):
    return bool(row.get("changed_the_decision"))


def ruling_verdict(row):
    """The verdict the RULING settled on — derived, see the module docstring."""
    return other(row["verdict"]) if overturned(row) else row["verdict"]


def outcome(row):
    return "OVERTURN" if overturned(row) else "UPHOLD"


def phantom(row):
    return row.get("challenge_stance") == "contests" and row.get("prose_stance") == "RIGHT"


def genuine(row):
    return row.get("challenge_stance") == "contests" and row.get("prose_stance") == "WRONG"


# --------------------------------------------------------------------------- #


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Compare a tree's rulings with the same objections re-ruled.")
    ap.add_argument("--source", type=Path,
                    default=Path("records/experiments/recontest/index.jsonl"),
                    help="index.jsonl of the tree whose contests were re-ruled "
                         "(default: records/experiments/recontest/index.jsonl)")
    ap.add_argument("--rerule", type=Path,
                    default=Path("records/experiments/rerule/recontest/index.jsonl"),
                    help="index.jsonl of the rerule tree "
                         "(default: records/experiments/rerule/recontest/index.jsonl)")
    ap.add_argument("--rerule-tree", type=Path, default=None,
                    help="optional: the rerule run tree, for a per-cell cross-check of "
                         "ruling.json / ruling.source.json / ruling_agreement.json "
                         "against what this script derives from the index")
    ap.add_argument("--sweep-source", choices=("auto", "yes", "no"), default="auto",
                    help="whether the source is the sweep, which enables the paired "
                         "strong-re-decider vs weak-judge section (default: auto — the "
                         "source experiment.json name, else the presence of "
                         "restated_verdict rulings)")
    args = ap.parse_args()

    src_all = load(args.source)
    re_all = load(args.rerule)

    both = [c for c in src_all if c in re_all]
    # Every cell the rerule tree ruled. Not all of them have a SOURCE ruling to pair
    # with: the sweep left 7 contests with a challenge written and no ruling (the
    # re-decider truncated at max_tokens), and the re-rule pass rules them because they
    # carry a challenge whose stance is `contests`. They have a re-ruling and no
    # counterpart, so they cannot appear in any side-by-side table.
    cells = [c for c in both if ruled(re_all[c])]
    pairs = [(src_all[c], re_all[c]) for c in cells if ruled(src_all[c])]
    orphans = [(src_all[c], re_all[c]) for c in cells if not ruled(src_all[c])]
    src_ruled_only = [c for c in src_all if ruled(src_all[c]) and c not in set(cells)]

    # ---------------------------------------------------------------- asserts
    fails = []
    for cell in cells:
        s, r = src_all[cell], re_all[cell]
        for field in ("verdict", "initially_correct", "gold_flawed",
                      "challenge_stance", "prose_stance"):
            if s.get(field) != r.get(field):
                fails.append(f"{cell}: {field} {s.get(field)!r} != {r.get(field)!r}")
    if fails:
        raise SystemExit(
            "the two trees do not describe the same decisions and objections:\n  "
            + "\n  ".join(fails[:20])
            + (f"\n  ... and {len(fails) - 20} more" if len(fails) > 20 else ""))

    src_forms = Counter(s["ruling_form"] for s, _ in pairs)
    re_forms = Counter(r["ruling_form"] for _, r in pairs)
    bad_src = set(src_forms) - set(SOURCE_FORMS)
    if bad_src:
        raise SystemExit(f"unknown ruling_form in the source index: {sorted(bad_src)}")
    bad_re = set(re_forms) - {RERULE_FORM}
    if bad_re:
        raise SystemExit(
            f"the rerule tree must hold only {RERULE_FORM!r} rulings, got "
            f"{dict(re_forms)} — this is not a re-rule pass under the new line")

    # ------------------------------------------------- is the source the sweep?
    name = None
    exp = args.source.parent / "experiment.json"
    if exp.is_file():
        try:
            name = json.loads(exp.read_text()).get("name")
        except (OSError, json.JSONDecodeError):
            name = None
    if args.sweep_source == "auto":
        is_sweep = (name or "").startswith("sweep") or "restated_verdict" in src_forms
        why = (f"experiment.json name {name!r}" if (name or "").startswith("sweep")
               else ("restated_verdict rulings present in the source"
                     if "restated_verdict" in src_forms else "neither"))
    else:
        is_sweep = args.sweep_source == "yes"
        why = f"--sweep-source {args.sweep_source}"

    mismatch_measured = any("ruling_line_mismatch" in r for _, r in pairs)
    mism = [(s, r) for s, r in pairs if r.get("ruling_line_mismatch") is not None]
    n_mism = sum(1 for _, r in mism if r["ruling_line_mismatch"])
    src_mismatch_measured = any("ruling_line_mismatch" in s for s, _ in pairs)

    def cond_rows(rows, cond):
        return rows if cond == POOLED else [x for x in rows if x[0]["condition"] == cond]

    conds = [c for c in CONDS if any(s["condition"] == c for s, _ in pairs)] + [POOLED]

    # ------------------------------------------------------------------ header
    print("=" * W)
    print("RERULE COMPARE — the same objections, ruled by two different ruling lines")
    print("=" * W)
    print(f"SOURCE  {args.source}"
          + (f"   (experiment {name!r})" if name else ""))
    print(f"RERULE  {args.rerule}")
    if args.rerule_tree:
        print(f"cross-check tree  {args.rerule_tree}")
    print()

    # ------------------------------------------------------------- (h) caveats
    print("CAVEAT — what passes through a ruling line, and what the instrument says")
    rule()
    print("Detection-side numbers (challenge_stance, prose_stance, phantom_contest, the")
    print("agreement instrument) are IDENTICAL in the two trees by construction: the")
    print("re-rule copies the objection and re-makes only the ruling. They are asserted")
    print("cell by cell above and are not affected by anything below.")
    print()
    print("Everything that passes through the ruling line — changed_the_decision,")
    print("final_correct, fixed/broken/net, the end-to-end rate, and the discrimination")
    print("figures in (c) — is exactly what the re-rule was run to re-measure. In the")
    print("SOURCE column these come from the line whose failure mode is being corrected:")
    if "uphold_overturn" in src_forms:
        print(f"  {src_forms['uphold_overturn']} of the {len(pairs)} joined rulings are "
              "`uphold_overturn`, the weak third-party judge's")
        print("  relative line — the one the re-contest hand check found contradicting the")
        print("  judge's own reasoning on 8 of 12 FLAWED parents. Treat every SOURCE number")
        print("  below on a FLAWED parent as unreliable, not as a baseline.")
    if "restated_verdict" in src_forms:
        print(f"  {src_forms['restated_verdict']} are `restated_verdict`, the strong "
              "re-decider restating the verdict itself.")
        print("  That form was never asked for a relative word and is not implicated in the")
        print("  collision; it is a different ruler, not a broken line.")
    print()
    if mismatch_measured:
        print(f"The RERULE column's residual is measured: ruling_line_mismatch fires on "
              f"{rate(n_mism, len(mism))} of the")
        print("re-rulings — Haiku reads the judge's prose alone and disagrees with the")
        print("conclusion line it wrote. That rate is the bound on every RERULE number that")
        print("passes through a ruling; section (b) splits it by parent verdict and")
        print("condition, which is where a residual collision would show.")
    else:
        print("The RERULE tree carries NO ruling_line_mismatch column — the ruling_agreement")
        print("stage has not run on it. Every RERULE number below is therefore unbounded in")
        print("the same way the SOURCE numbers are. Run the stage before quoting them.")
    if not src_mismatch_measured:
        print("The SOURCE tree carries no ruling_line_mismatch column: the instrument did")
        print("not exist when it ran, so its residual is NOT MEASURED ON THE SOURCE. The")
        print("re-contest's 12-ruling hand check is the only reading of it.")
    print()
    print("The dataset labels themselves are the outer bound on `correct`, unchanged by")
    print("any of this: a re-ruling that agrees with a wrong label counts as wrong.")

    # ---------------------------------------------------------------- the join
    head("JOIN")
    print(f"source rows                       {len(src_all)}")
    print(f"rerule rows                       {len(re_all)}")
    print(f"cells in both indices             {len(both)}")
    print(f"  of those, re-ruled              {len(cells)}")
    print(f"    with a SOURCE ruling to pair  {len(pairs)}   <- every paired table below")
    print(f"    with NO source ruling         {len(orphans)}   <- excluded from the "
          f"paired tables")
    print(f"  in both, no ruling in rerule    {len(both) - len(cells)}")
    print(f"source rulings NOT re-ruled       {len(src_ruled_only)}"
          + ("   (the rerule pass covers a subset of the source's rulings)"
             if src_ruled_only else ""))
    print(f"cells only in the rerule index    {len(set(re_all) - set(src_all))}")
    print()
    if orphans:
        print(f"THE {len(orphans)} RE-RULINGS WITH NO SOURCE RULING. The source contest wrote a")
        print("challenge and no ruling — the re-decider truncated at max_tokens — so the")
        print("index carries ruling_form: null and changed_the_decision: false for them, an")
        print("absent ruling read as a decision that stood (metrics.json and")
        print("sweep-phantom-corrected.py both do this, and say so). The re-rule pass rules")
        print("them because the challenge stance is `contests`, so they now have a ruling")
        print("that never existed on the source side. There is nothing to put in a SOURCE")
        print("column for them, so they are OUT of (a), (b), (c), d1, e1, (f) and (g).")
        print("They ARE in the d2/e2 projection, where the source column keeps its silent")
        print("not-revised default and the rerule column takes the new ruling — which is a")
        print("real gain in coverage, not a like-for-like comparison. What they did:")
        cn = Counter(s["condition"] for s, _ in orphans)
        print(f"  by condition        {dict(cn)}")
        print(f"  re-rule overturned  {rate(sum(1 for _, r in orphans if overturned(r)), len(orphans))}")
        n_o = [r for _, r in orphans if r.get("ruling_line_mismatch") is not None]
        if n_o:
            print(f"  line mismatch       "
                  f"{rate(sum(1 for r in n_o if r['ruling_line_mismatch']), len(n_o))}")
        print(f"  genuine objections  "
              f"{rate(sum(1 for s, _ in orphans if genuine(s)), len(orphans))}"
              f"   phantom: {sum(1 for s, _ in orphans if phantom(s))}")
        print(f"  correct after       "
              f"SOURCE {rate(sum(1 for s, _ in orphans if s.get('final_correct')), len(orphans))}"
              f"   RERULE {rate(sum(1 for _, r in orphans if r.get('final_correct')), len(orphans))}")
        print()
    print(f"identity asserted cell by cell on verdict, initially_correct, gold_flawed,")
    print(f"challenge_stance, prose_stance: {len(cells)}/{len(cells)} identical.")
    print()
    print(f"source is the sweep: {'YES' if is_sweep else 'no'}  ({why})"
          + ("  -> section (g) printed" if is_sweep else "  -> section (g) skipped"))
    print()
    print("re-ruled cells by condition:")
    for c in conds:
        print(f"  {c:<16}{len(cond_rows(pairs, c)):>6}")

    # ------------------------------------------------------- (a) rulings made
    head("(a) RULINGS MADE, by ruling_form")
    print("The source may mix forms (the sweep's `debate` cells were ruled by the weak")
    print("third-party judge, its solo cells by the strong re-decider). The rerule tree is")
    print("asserted to hold `stated_conclusion` and nothing else.")
    print()
    forms = sorted(set(src_forms) | set(re_forms))
    print(f"{'condition':<16}{'n':>6}   " + pad("SOURCE", 44) + "RERULE")
    rule()
    for c in conds:
        rows = cond_rows(pairs, c)
        s_txt = ", ".join(
            f"{f}={sum(1 for s, _ in rows if s['ruling_form'] == f)}"
            for f in forms if any(s["ruling_form"] == f for s, _ in rows))
        r_txt = ", ".join(
            f"{f}={sum(1 for _, r in rows if r['ruling_form'] == f)}"
            for f in forms if any(r["ruling_form"] == f for _, r in rows))
        print(f"{c:<16}{len(rows):>6}   " + pad(s_txt, 44) + r_txt)

    # --------------------------------------------- (b) the mismatch instrument
    head("(b) THE NEW INSTRUMENT — the ruling line vs the judge's own prose")
    print("Haiku reads the judge's REASONING ONLY, with the conclusion line stripped, and")
    print("says whether that prose concludes the text under review contains a flaw. A")
    print("mismatch is a ruling whose line contradicts the reasoning that produced it —")
    print("the exact failure the re-rule was run to remove, measured rather than assumed.")
    print()
    if not mismatch_measured:
        print("NOT MEASURED on the rerule tree — no ruling_line_mismatch column.")
    else:
        print(f"{'condition':<16}{'parent':<10}{'n':>6}{'mismatch':>18}"
              f"{'prose FLAWED':>16}{'prose SOUND':>14}{'NEITHER':>10}")
        rule()
        for c in conds:
            rows = [(s, r) for s, r in cond_rows(mism, c)]
            for parent in (*VERDICTS, "both"):
                sel = rows if parent == "both" else [
                    (s, r) for s, r in rows if s["verdict"] == parent]
                if not sel:
                    continue
                n = sum(1 for _, r in sel if r["ruling_line_mismatch"])
                pc = Counter(r.get("ruling_prose_conclusion") for _, r in sel)
                print(f"{c if parent == VERDICTS[0] else '':<16}{parent:<10}{len(sel):>6}"
                      f"{rate(n, len(sel)):>18}{pc.get('FLAWED', 0):>16}"
                      f"{pc.get('SOUND', 0):>14}{pc.get('NEITHER', 0):>10}")
            rule()
        print()
        print("A residual collision would appear as a mismatch rate concentrated on FLAWED")
        print("parents — that is what the old line did (it read as OVERTURN whenever the")
        print("objection was any good). A flat, low rate across both parents is the fix")
        print("working; it is not zero and every RERULE rate below inherits it.")
    print()
    if src_mismatch_measured:
        s_m = [(s, r) for s, r in pairs if s.get("ruling_line_mismatch") is not None]
        print("SOURCE ruling_line_mismatch: "
              f"{rate(sum(1 for s, _ in s_m if s['ruling_line_mismatch']), len(s_m))}")
    else:
        print("SOURCE ruling_line_mismatch: NOT MEASURED ON THE SOURCE — the")
        print("ruling_agreement stage did not exist when the source tree was built, so")
        print("there is no per-ruling reading of its prose to compare against. The only")
        print("reading of the source line is the 12-ruling hand check in")
        print("records/experiments/recontest/HANDCHECK-ruling-line.md.")

    # -------------------------------------------------- (c) what was overturned
    head("(c) OVERTURN RATE BY WHAT WAS ACTUALLY OBJECTED TO")
    print("phantom       the objection's line said REVERSE and its own prose endorsed the")
    print("              verdict (prose_stance RIGHT). A ruler that reads the objection")
    print("              rather than its line should overturn almost none of these.")
    print("genuine|wrong prose_stance WRONG on a decision that was in fact incorrect —")
    print("              the objections a working recourse channel is FOR.")
    print("genuine|corr  prose_stance WRONG on a decision that was in fact correct — the")
    print("              specious objections it must resist.")
    print("discrimination = overturn rate on genuine|wrong minus overturn on genuine|corr.")
    print("It is the only figure here that a ruler cannot raise by overturning everything.")
    print()
    print(f"{'condition':<15}{'bucket':<15}{'n':>5}{'SOURCE overturn':>20}"
          f"{'RERULE overturn':>20}")
    rule()
    for c in conds:
        rows = cond_rows(pairs, c)
        buckets = [
            ("phantom", [(s, r) for s, r in rows if phantom(s)]),
            ("genuine|wrong", [(s, r) for s, r in rows
                               if genuine(s) and s.get("initially_incorrect")]),
            ("genuine|corr", [(s, r) for s, r in rows
                              if genuine(s) and s.get("initially_correct")]),
            ("other/NEITHER", [(s, r) for s, r in rows
                               if not phantom(s) and not genuine(s)]),
        ]
        srates = {}
        for label, sel in buckets:
            if not sel:
                continue
            ns = sum(1 for s, _ in sel if overturned(s))
            nr = sum(1 for _, r in sel if overturned(r))
            srates[label] = (ns / len(sel), nr / len(sel))
            print(f"{c if label == 'phantom' else '':<15}{label:<15}{len(sel):>5}"
                  f"{rate(ns, len(sel)):>20}{rate(nr, len(sel)):>20}")
        if "genuine|wrong" in srates and "genuine|corr" in srates:
            ds = srates["genuine|wrong"][0] - srates["genuine|corr"][0]
            dr = srates["genuine|wrong"][1] - srates["genuine|corr"][1]
            print(f"{'':<15}{'DISCRIMINATION':<15}{'':>5}"
                  f"{f'{100 * ds:+.1f} pts':>20}{f'{100 * dr:+.1f} pts':>20}")
        rule()

    # ------------------------------------------------------------- (d) accuracy
    head("(d) NET EFFECT ON ACCURACY  (sweep-phantom-corrected.py's definitions)")
    print("A cell's final verdict is the ruling's if the contest produced one, else the")
    print("decision's own. fixed = wrong decision made right; broken = right decision made")
    print("wrong; net = fixed - broken. Cells with no dataset label are excluded and")
    print("counted separately.")
    print()
    print("d1 — over the RE-RULED CELLS ONLY (the paired comparison; same decisions, same")
    print("     objections, the two ruling lines side by side)")
    print()
    _accuracy_table(pairs, conds, cond_rows)

    proj = []
    n_sub = 0
    for cell, s in src_all.items():
        r = re_all.get(cell)
        if r is not None and ruled(r):
            proj.append((s, r))
            n_sub += 1
        else:
            proj.append((s, s))
    # `n_sub` counts every re-ruled cell, the orphans included: in the projection they
    # are exactly the cells where the source has no ruling and the rerule does.
    print()
    print(f"d2 — PROJECTED ONTO THE WHOLE SOURCE GRID ({len(src_all)} cells): a re-ruled cell")
    print(f"     takes the new tree's outcome, every other cell keeps the source's.")
    print(f"     {n_sub} cells substituted ({len(pairs)} paired re-rulings"
          + (f" + {len(orphans)} with no source ruling)" if orphans else ")") + "; the")
    print("     rest of the grid is identical in both columns, so ACC BEFORE is the same")
    print("     and the whole of the change is attributable to the ruling line.")
    print()
    _accuracy_table(proj, [c for c in CONDS
                           if any(s["condition"] == c for s, _ in proj)] + [POOLED],
                    cond_rows)

    # ----------------------------------------------------------- (e) end-to-end
    head("(e) END-TO-END — own wrong decisions genuinely contested AND overturned")
    print("Of a condition's own incorrect decisions, the fraction where the challenger")
    print("raised an objection whose PROSE argued the verdict was wrong and the ruler then")
    print("overturned. Detection x revision, unconditional — the number the whole recourse")
    print("channel exists to move.")
    print()
    print("e1 — over the RE-RULED CELLS ONLY (denominator: incorrect decisions among them)")
    print()
    _endtoend_table(pairs, conds, cond_rows)
    print()
    print(f"e2 — PROJECTED ONTO THE WHOLE SOURCE GRID (denominator: every incorrect")
    print(f"     decision in the source index, contested or not)")
    print()
    _endtoend_table(proj, [c for c in CONDS
                           if any(s["condition"] == c for s, _ in proj)] + [POOLED],
                    cond_rows)

    # ---------------------------------------------------------- (f) transitions
    head("(f) PER-CELL RULING TRANSITIONS  (source outcome -> rerule outcome)")
    print(f"{'condition':<16}{'n':>6}{'UPHOLD->UPH':>14}{'UPHOLD->OVT':>14}"
          f"{'OVT->UPHOLD':>14}{'OVT->OVT':>12}{'changed':>16}")
    rule()
    for c in conds:
        rows = cond_rows(pairs, c)
        t = Counter((outcome(s), outcome(r)) for s, r in rows)
        changed = sum(v for k, v in t.items() if k[0] != k[1])
        print(f"{c:<16}{len(rows):>6}{t[('UPHOLD', 'UPHOLD')]:>14}"
              f"{t[('UPHOLD', 'OVERTURN')]:>14}{t[('OVERTURN', 'UPHOLD')]:>14}"
              f"{t[('OVERTURN', 'OVERTURN')]:>12}{rate(changed, len(rows)):>16}")
    print()
    print("the same, as the VERDICT each ruling settled on (derived: the parent verdict")
    print("when upheld, the other verdict when overturned)")
    print()
    print(f"{'condition':<16}{'n':>6}{'FLAWED->FLAWED':>17}{'FLAWED->SOUND':>16}"
          f"{'SOUND->FLAWED':>16}{'SOUND->SOUND':>15}")
    rule()
    for c in conds:
        rows = cond_rows(pairs, c)
        t = Counter((ruling_verdict(s), ruling_verdict(r)) for s, r in rows)
        print(f"{c:<16}{len(rows):>6}{t[('FLAWED', 'FLAWED')]:>17}"
              f"{t[('FLAWED', 'SOUND')]:>16}{t[('SOUND', 'FLAWED')]:>16}"
              f"{t[('SOUND', 'SOUND')]:>15}")

    # ------------------------------------------------ (g) strong vs weak ruler
    if is_sweep:
        paired = [(s, r) for s, r in pairs if s["ruling_form"] == "restated_verdict"]
        _strong_vs_weak(paired)
    else:
        head("(g) STRONG RE-DECIDER vs WEAK THIRD-PARTY JUDGE")
        print("skipped — this section needs the sweep as the source, whose solo conditions")
        print("were ruled by the strong re-decider (`restated_verdict`). Force it with")
        print("--sweep-source yes.")

    # ---------------------------------------------------- optional cross-check
    if args.rerule_tree:
        _cross_check(args.rerule_tree, pairs + orphans)

    print()
    rule("=")
    print("end")


# --------------------------------------------------------------------------- #
# tables reused by the restricted and the projected views
# --------------------------------------------------------------------------- #


def _accuracy_table(pairs, conds, cond_rows, left="SRC", right="RE"):
    print(f"{'condition':<15}{'n':>6}{'acc before':>13}{left + ' after':>14}"
          f"{right + ' after':>14}"
          f"{left + ' f/b/net':>17}{right + ' f/b/net':>17}{'unlabelled':>12}")
    rule()
    for c in conds:
        rows = cond_rows(pairs, c)
        lab = [(s, r) for s, r in rows if s.get("initially_correct") is not None]
        n = len(lab)
        before = sum(1 for s, _ in lab if s["initially_correct"])
        s_after = sum(1 for s, _ in lab if s.get("final_correct"))
        r_after = sum(1 for _, r in lab if r.get("final_correct"))
        s_fix = sum(1 for s, _ in lab
                    if not s["initially_correct"] and s.get("final_correct"))
        s_brk = sum(1 for s, _ in lab
                    if s["initially_correct"] and not s.get("final_correct"))
        r_fix = sum(1 for s, r in lab
                    if not s["initially_correct"] and r.get("final_correct"))
        r_brk = sum(1 for s, r in lab
                    if s["initially_correct"] and not r.get("final_correct"))
        print(f"{c:<15}{n:>6}{pct(before, n):>13}{pct(s_after, n):>14}"
              f"{pct(r_after, n):>14}"
              f"{f'{s_fix}/{s_brk}/{s_fix - s_brk:+d}':>17}"
              f"{f'{r_fix}/{r_brk}/{r_fix - r_brk:+d}':>17}{len(rows) - n:>12}")


def _endtoend_table(pairs, conds, cond_rows):
    print(f"{'condition':<15}{'incorrect':>11}{'SOURCE':>22}{'RERULE':>22}")
    rule()
    for c in conds:
        rows = cond_rows(pairs, c)
        inc = [(s, r) for s, r in rows if s.get("initially_incorrect")]
        s_n = sum(1 for s, _ in inc if genuine(s) and overturned(s))
        r_n = sum(1 for s, r in inc if genuine(s) and overturned(r))
        print(f"{c:<15}{len(inc):>11}{rate(s_n, len(inc)):>22}{rate(r_n, len(inc)):>22}")


def _strong_vs_weak(paired):
    n = len(paired)
    head(f"(g) STRONG RE-DECIDER vs WEAK THIRD-PARTY JUDGE, same {n} objections")
    print("The sweep's single/self_critique cells were ruled by the model that made the")
    print("decision, re-deciding with the objection in hand (`restated_verdict`); its")
    print("debate cells were ruled by a separate weak judge. Any solo-vs-debate difference")
    print("in the sweep's recourse numbers therefore confounds the protocol with the ruler.")
    print("Re-ruling these same objections with the weak third-party judge removes the")
    print("confound: identical decisions, identical objections, two rulers.")
    print()
    print(f"restricted to the {n} joined cells whose SOURCE ruling_form == restated_verdict")
    print(f"conditions present: "
          f"{dict(Counter(s['condition'] for s, _ in paired))}")
    print()
    conds = [c for c in CONDS if any(s["condition"] == c for s, _ in paired)] + [POOLED]

    def sel(rows, c):
        return rows if c == POOLED else [x for x in rows if x[0]["condition"] == c]

    print("what each ruler overturned")
    print(f"{'condition':<15}{'bucket':<15}{'n':>5}{'STRONG re-decider':>20}"
          f"{'WEAK judge':>20}")
    rule()
    for c in conds:
        rows = sel(paired, c)
        buckets = [
            ("phantom", [(s, r) for s, r in rows if phantom(s)]),
            ("genuine|wrong", [(s, r) for s, r in rows
                               if genuine(s) and s.get("initially_incorrect")]),
            ("genuine|corr", [(s, r) for s, r in rows
                              if genuine(s) and s.get("initially_correct")]),
        ]
        rates = {}
        for label, b in buckets:
            if not b:
                continue
            ns = sum(1 for s, _ in b if overturned(s))
            nr = sum(1 for _, r in b if overturned(r))
            rates[label] = (ns / len(b), nr / len(b))
            print(f"{c if label == 'phantom' else '':<15}{label:<15}{len(b):>5}"
                  f"{rate(ns, len(b)):>20}{rate(nr, len(b)):>20}")
        if "genuine|wrong" in rates and "genuine|corr" in rates:
            ds = rates["genuine|wrong"][0] - rates["genuine|corr"][0]
            dr = rates["genuine|wrong"][1] - rates["genuine|corr"][1]
            print(f"{'':<15}{'DISCRIMINATION':<15}{'':>5}"
                  f"{f'{100 * ds:+.1f} pts':>20}{f'{100 * dr:+.1f} pts':>20}")
        rule()

    print()
    print("what each ruler did to accuracy, on these cells")
    _accuracy_table(paired, conds, lambda rows, c: sel(rows, c),
                    left="STRONG", right="WEAK")

    print()
    print("do the two rulers agree?  (the ruling's own verdict, and the UPHOLD/OVERTURN")
    print("outcome that verdict implies against the same parent)")
    print(f"{'condition':<15}{'n':>6}{'verdict agree':>18}{'outcome agree':>18}"
          f"{'STRONG correct':>18}{'WEAK correct':>17}")
    rule()
    for c in conds:
        rows = sel(paired, c)
        lab = [(s, r) for s, r in rows if s.get("final_correct") is not None
               and r.get("final_correct") is not None]
        va = sum(1 for s, r in rows if ruling_verdict(s) == ruling_verdict(r))
        oa = sum(1 for s, r in rows if outcome(s) == outcome(r))
        sc = sum(1 for s, _ in lab if s["final_correct"])
        rc = sum(1 for _, r in lab if r["final_correct"])
        print(f"{c:<15}{len(rows):>6}{rate(va, len(rows)):>18}{rate(oa, len(rows)):>18}"
              f"{rate(sc, len(lab)):>18}{rate(rc, len(lab)):>17}")
    print()
    print("Verdict agreement and outcome agreement are the same number here: both rulings")
    print("are read against the same parent verdict, so agreeing on one is agreeing on the")
    print("other. They are printed separately because the two trees record different")
    print("fields, and a divergence would mean the join is wrong.")


# --------------------------------------------------------------------------- #
# the optional per-cell cross-check
# --------------------------------------------------------------------------- #


def _cross_check(tree: Path, pairs) -> None:
    """Verify the index-derived values against the rerule tree's own records.

    Nothing above depends on this. It exists so that the two quantities this script
    DERIVES — a ruling's own verdict, and the source ruling the rerule copied beside it —
    can be checked against `ruling.json` / `ruling.source.json` when the tree is at hand.
    """
    head("CROSS-CHECK against the rerule run tree (optional; no table above uses it)")
    print(f"tree {tree}")
    print()
    checked = missing = bad = 0
    problems = []
    for s, r in pairs:
        cell = s["cell_id"]
        runs = sorted((tree / "cells" / cell / "contests").glob("*/runs/*"), reverse=True)
        run = next((d for d in runs if (d / "ruling.json").is_file()), None)
        if run is None:
            missing += 1
            continue
        checked += 1
        ruling = json.loads((run / "ruling.json").read_text())
        if ruling.get("form") != r.get("ruling_form"):
            problems.append(f"{cell}: form {ruling.get('form')} != {r.get('ruling_form')}")
        if ruling.get("verdict") != ruling_verdict(r):
            problems.append(
                f"{cell}: derived ruling verdict {ruling_verdict(r)} != "
                f"{ruling.get('verdict')} on disk")
        if bool(ruling.get("changed_the_decision")) != overturned(r):
            problems.append(f"{cell}: changed_the_decision disagrees with the index")
        src_path = run / "ruling.source.json"
        if src_path.is_file() and ruled(s):
            src = json.loads(src_path.read_text())
            if src.get("form") != s.get("ruling_form"):
                problems.append(
                    f"{cell}: ruling.source.json form {src.get('form')} != source index "
                    f"{s.get('ruling_form')}")
            if src.get("verdict") != ruling_verdict(s):
                problems.append(
                    f"{cell}: derived SOURCE ruling verdict {ruling_verdict(s)} != "
                    f"{src.get('verdict')} in ruling.source.json")
        ra = run / "ruling_agreement.json"
        if ra.is_file():
            reading = json.loads(ra.read_text())
            if (r.get("ruling_line_mismatch") is not None
                    and bool(reading.get("mismatch")) != bool(r["ruling_line_mismatch"])):
                problems.append(f"{cell}: ruling_agreement mismatch disagrees with index")
    bad = len(problems)
    print(f"cells checked                {checked}")
    print(f"cells with no ruling.json    {missing}")
    print(f"disagreements                {bad}")
    for p in problems[:20]:
        print(f"  {p}")
    if bad > 20:
        print(f"  ... and {bad - 20} more")
    if bad == 0 and checked:
        print("every index-derived value matches the record on disk.")


if __name__ == "__main__":
    main()

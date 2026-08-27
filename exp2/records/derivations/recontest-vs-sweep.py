"""The paired comparison: the sweep's contests against the re-contest's, cell by cell.

The re-contest (`experiments/recontest.toml`, 2026-08-26) **decided nothing**. It read the
sweep's 5,724 decisions out of `outputs/experiments/sweep` (`decisions_from`) and re-ran
only the measurement layers — contest, agreement, grade — with two changes:

  * the challenger reasons first and writes its `Decision:` line **last**, with the two
    words spelled out in the phrases of *this* decision (plan step 1);
  * the recourse judge is a weak third party in **every** condition
    (`recourse_form = "third_party"`), where the sweep ruled `debate` by that judge and
    `single`/`self_critique` by the strong decider re-deciding in its own conversation.

So the decision side of every row is *the same generation in both trees* — same verdict,
same `initially_correct`, same record — and every difference below is a difference in the
contest layer alone. That is what makes a paired, per-`cell_id` table legitimate here and
not between any two other runs in this repository.

    uv run python records/derivations/recontest-vs-sweep.py [sweep_index] [recontest_index]
    # defaults: records/experiments/sweep/index.jsonl  outputs/experiments/recontest/index.jsonl
    # after the artifacts are copied, the second may also be
    #          records/experiments/recontest/index.jsonl

Stdlib only. The eight sections it prints, in order:

  a. n decided and errors — identical by construction, and asserted, not assumed;
  b. objections raised, the phantom share of them, and the mirror-image failure
     (a STANDS line over prose the agreement stage reads as WRONG);
  c. raw detection, TRUE detection (line REVERSE *and* prose WRONG) and genuine
     false alarms;
  d. overturn rates by objection kind, discrimination, and the `ruling_form` counts
     that say who ruled;
  e. the net effect of the whole contest process on accuracy;
  f. end-to-end: of a condition's own wrong decisions, genuinely contested AND overturned;
  g. per-cell transition tables — (sweep stance → recontest stance), and
     (sweep ruling outcome → recontest ruling outcome) on the cells ruled in both;
  h. the re-contest challenger's repair and `parse_mode` distribution, and the residual
     "instruction gloss" leak — replies that echo the prompt's own gloss words.

**(b)-(f) mirror `records/derivations/sweep-phantom-corrected.py` exactly.** A contest is
RAW when `challenge_stance == "contests"` (the line word was REVERSE) and GENUINE when
the `agreement` stage additionally read the prose as `WRONG`. `phantom_contest` in the
index is the narrower `contests` ∧ prose `RIGHT`, so a `NEITHER` prose is non-genuine
without being a phantom; both are printed rather than reconciled silently. Every rate is
printed with its numerator and denominator.

**Section (h) needs the run tree**, not just the index: `repair_attempts` and `parse_mode`
live in each contest's `challenge.json`, and the gloss check needs `Challenge.text`. When
the index handed to this script has no `cells/` directory beside it — which is the case
for the copy under `records/` — section (h) prints what it could not read and stops there.
The committed `records/experiments/recontest/recontest-vs-sweep.log` was produced from the
`outputs/` tree, with (h) filled in.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

SWEEP = Path(sys.argv[1] if len(sys.argv) > 1 else "records/experiments/sweep/index.jsonl")
RECON = Path(sys.argv[2] if len(sys.argv) > 2 else "outputs/experiments/recontest/index.jsonl")
CONDS = ("single", "self_critique", "debate")
GLOSS = ("you disagree:", "you agree:")


def pct(num, den):
    return f"{100.0 * num / den:.1f}%" if den else "n/a"


def load(path):
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return {r["cell_id"]: r for r in rows}


def attempted(path):
    """Cells the spec asked for, from the experiment.json beside the index (if there)."""
    exp = path.parent / "experiment.json"
    if not exp.exists():
        return None
    return json.load(exp.open()).get("cells")


sweep, recon = load(SWEEP), load(RECON)

# ---------------------------------------------------------------- a. the join
print("=" * 96)
print("SWEEP vs RECONTEST — paired on cell_id, same decisions, contest layer re-run")
print("=" * 96)
print(f"sweep     index : {SWEEP}")
print(f"recontest index : {RECON}")
print()

assert set(sweep) == set(recon), (
    f"cell_id sets differ: {len(set(sweep) - set(recon))} only in sweep, "
    f"{len(set(recon) - set(sweep))} only in recontest"
)
cells = sorted(sweep)
for cid in cells:
    for key in ("condition", "item_id", "subset", "verdict", "gold_flawed",
                "initially_correct", "initially_incorrect"):
        assert sweep[cid][key] == recon[cid][key], (
            f"{cid}: {key} differs between trees ({sweep[cid][key]!r} vs {recon[cid][key]!r}) "
            "— the re-contest was supposed to reuse the decision, not remake it"
        )
print(f"(a) THE JOIN — {len(cells)} cell_ids, identical in both trees; verdict, correctness,")
print("    item and subset asserted equal cell by cell. The decision side IS the same")
print("    generation: the re-contest read it out of the sweep tree and never re-decided.")
print()
a_sw, a_rc = attempted(SWEEP), attempted(RECON)
print("condition           n decided        attempted       errors (not decided)")
print("-" * 74)
for c in CONDS:
    n = sum(1 for cid in cells if sweep[cid]["condition"] == c)
    if a_sw and a_rc:
        att = a_sw // len(CONDS)
        assert a_sw == a_rc, f"spec cell counts differ: {a_sw} vs {a_rc}"
        print(f"{c:<16}{n:>10}{att:>17}{f'{att - n}':>17}   ({pct(att - n, att)} of the condition)")
    else:
        print(f"{c:<16}{n:>10}{'unknown':>17}{'unknown':>17}")
tot = len(cells)
if a_sw and a_rc:
    print(f"{'POOLED':<16}{tot:>10}{a_sw:>17}{f'{a_sw - tot}':>17}   ({pct(a_sw - tot, a_sw)} of the sweep)")
print("Errors are identical by construction — both trees index exactly the decisions the")
print("sweep made — and the assert above is what checks it rather than the arithmetic.")
print()


def sub(idx, c):
    return [idx[cid] for cid in cells if sweep[cid]["condition"] == c] if c else [idx[cid] for cid in cells]


def raw(rs):
    """RAW objections: the `Decision:` line said REVERSE."""
    return [r for r in rs if r["challenge_stance"] == "contests"]


def genuine(rs):
    """GENUINE objections: line REVERSE *and* the agreement stage read the prose as WRONG."""
    return [r for r in raw(rs) if r["prose_stance"] == "WRONG"]


def phantom(rs):
    """PHANTOM: line REVERSE over prose the agreement stage read as RIGHT."""
    return [r for r in raw(rs) if r["phantom_contest"]]


def decline_wrong(rs):
    """The mirror-image failure: a STANDS line over prose arguing the verdict was WRONG."""
    return [r for r in rs if r["challenge_stance"] == "declined" and r["prose_stance"] == "WRONG"]


STRATA = [(c, c) for c in CONDS] + [("POOLED", None)]


def side_by_side(title, header, rowfn, note=None):
    print("-" * 96)
    print(title)
    if note:
        print(note)
    print(f"{'condition':<15}{'| SWEEP':<40}{'| RECONTEST':<40}")
    print(f"{'':<15}{header:<40}{header:<40}")
    print("-" * 96)
    for label, c in STRATA:
        s, r = rowfn(sub(sweep, c)), rowfn(sub(recon, c))
        print(f"{label:<15}{'| ' + s:<40}{'| ' + r:<40}")
    print()


# ------------------------------------------------- b. raised, phantoms, mirror
print("=" * 96)
print("(b) OBJECTIONS RAISED, PHANTOM SHARE, AND THE MIRROR-IMAGE FAILURE")
print("=" * 96)
side_by_side(
    "OBJECTIONS RAISED — the `Decision:` line said REVERSE (all decisions, right or wrong)",
    "raised/n            rate",
    lambda rs: f"{len(raw(rs))}/{len(rs)}".ljust(20) + pct(len(raw(rs)), len(rs)),
)
side_by_side(
    "PHANTOM SHARE OF RAISED — line REVERSE, prose read RIGHT (denominator: ALL objections)",
    "phantom/raised      share",
    lambda rs: f"{len(phantom(rs))}/{len(raw(rs))}".ljust(20) + pct(len(phantom(rs)), len(raw(rs))),
    note="  This is the defect the re-contest was built to remove. The sweep's challenger was"
         "\n  asked for the line FIRST; the re-contest's writes it LAST, after its reasons.",
)
side_by_side(
    "NON-GENUINE SHARE OF RAISED — (raw - genuine)/raw; adds the `NEITHER` prose readings",
    "non-genuine/raised  share",
    lambda rs: f"{len(raw(rs)) - len(genuine(rs))}/{len(raw(rs))}".ljust(20)
    + pct(len(raw(rs)) - len(genuine(rs)), len(raw(rs))),
)
side_by_side(
    "DECLINES ARGUING FOR REVERSAL — line STANDS over prose the agreement stage read WRONG",
    "declines_wrong/n    rate",
    lambda rs: f"{len(decline_wrong(rs))}/{len(rs)}".ljust(20) + pct(len(decline_wrong(rs)), len(rs)),
    note="  The mirror image of a phantom, and NOT corrected anywhere: the sweep's hand check"
         "\n  (records/experiments/sweep/HANDCHECK-agreement.md) found every one of its six"
         "\n  agreement misreads on a STANDS line, always over-calling disagreement. Read this"
         "\n  row as an upper bound on lost detections, not as a count of them.",
)

# ---------------------------------------------------- c. detection, false alarm
print("=" * 96)
print("(c) DETECTION GIVEN A WRONG DECISION, AND FALSE ALARMS ON CORRECT ONES")
print("=" * 96)


def on_wrong(rs):
    return [r for r in rs if r["initially_incorrect"]]


def on_right(rs):
    return [r for r in rs if r["initially_correct"]]


side_by_side(
    "RAW DETECTION | the decision was WRONG — any REVERSE line, phantom or not",
    "raw/incorrect       rate",
    lambda rs: f"{len(raw(on_wrong(rs)))}/{len(on_wrong(rs))}".ljust(20)
    + pct(len(raw(on_wrong(rs))), len(on_wrong(rs))),
)
side_by_side(
    "TRUE DETECTION | the decision was WRONG — REVERSE line AND prose read WRONG",
    "genuine/incorrect   rate",
    lambda rs: f"{len(genuine(on_wrong(rs)))}/{len(on_wrong(rs))}".ljust(20)
    + pct(len(genuine(on_wrong(rs))), len(on_wrong(rs))),
)
side_by_side(
    "GENUINE FALSE ALARMS | the decision was CORRECT — REVERSE line AND prose read WRONG",
    "genuine/correct     rate",
    lambda rs: f"{len(genuine(on_right(rs)))}/{len(on_right(rs))}".ljust(20)
    + pct(len(genuine(on_right(rs))), len(on_right(rs))),
)
side_by_side(
    "RAW FALSE ALARMS | the decision was CORRECT — any REVERSE line",
    "raw/correct         rate",
    lambda rs: f"{len(raw(on_right(rs)))}/{len(on_right(rs))}".ljust(20)
    + pct(len(raw(on_right(rs))), len(on_right(rs))),
)

# ------------------------------------------------- d. overturns, discrimination
print("=" * 96)
print("(d) WHAT THE RECOURSE JUDGE DID WITH EACH KIND OF OBJECTION")
print("=" * 96)
print("The two trees do not use the same recourse mechanism, and that is the second thing")
print("under test. In the SWEEP, `debate` was ruled by a weak third-party judge")
print("(`uphold_overturn`) while `single`/`self_critique` were ruled by the strong decider")
print("re-deciding inside its own conversation (`restated_verdict`). In the RECONTEST,")
print("`recourse_form = \"third_party\"` sends EVERY condition to the weak judge, so every")
print("ruling is `uphold_overturn`. The counts:")
print()
print(f"{'condition':<15}{'| SWEEP ruling_form':<45}{'| RECONTEST ruling_form':<40}")
print("-" * 96)
for label, c in STRATA:
    def forms(idx):
        cc = Counter(r.get("ruling_form") or "none (no ruling written)" for r in sub(idx, c))
        return ", ".join(f"{k}={v}" for k, v in sorted(cc.items()))
    print(f"{label:<15}{'| ' + forms(sweep):<45}{'| ' + forms(recon):<40}")
print()
print("The sweep's 7 `none` rows on contested cells are contests that wrote a challenge and")
print("no ruling (the re-decider truncated at max_tokens); they carry")
print("`changed_the_decision: false` and are counted below as NOT overturned, exactly as")
print("`metrics.json` and `sweep-phantom-corrected.py` count them. The re-contest has none:")
print("every one of its objections got a ruling.")
print()


def overturn(rs):
    return [r for r in rs if r["changed_the_decision"]]


side_by_side(
    "OVERTURN RATE ON **PHANTOM** OBJECTIONS (line REVERSE, prose RIGHT)",
    "overturned/phantom  rate",
    lambda rs: f"{len(overturn(phantom(rs)))}/{len(phantom(rs))}".ljust(20)
    + pct(len(overturn(phantom(rs))), len(phantom(rs))),
    note="  An objection whose own prose says the verdict was right. Anything above 0 here is"
         "\n  the recourse judge moving a decision on pushback that argued for no such thing.",
)
side_by_side(
    "OVERTURN RATE ON **GENUINE** OBJECTIONS TO A **WRONG** DECISION",
    "overturned/genuine  rate",
    lambda rs: f"{len(overturn(genuine(on_wrong(rs))))}/{len(genuine(on_wrong(rs)))}".ljust(20)
    + pct(len(overturn(genuine(on_wrong(rs)))), len(genuine(on_wrong(rs)))),
)
side_by_side(
    "OVERTURN RATE ON **GENUINE** OBJECTIONS TO A **CORRECT** DECISION",
    "overturned/genuine  rate",
    lambda rs: f"{len(overturn(genuine(on_right(rs))))}/{len(genuine(on_right(rs)))}".ljust(20)
    + pct(len(overturn(genuine(on_right(rs)))), len(genuine(on_right(rs)))),
)


def discrim(rs):
    gw, gc = genuine(on_wrong(rs)), genuine(on_right(rs))
    ow, oc = overturn(gw), overturn(gc)
    if not gw or not gc:
        return "n/a"
    d = 100.0 * len(ow) / len(gw) - 100.0 * len(oc) / len(gc)
    return f"{d:+.1f}pp".ljust(12) + f"(n={len(gw)} vs {len(gc)})"


side_by_side(
    "DISCRIMINATION — overturn rate on genuine-on-WRONG minus genuine-on-CORRECT",
    "difference          ns",
    discrim,
    note="  A recourse judge that reads the record discriminates; one that folds under any"
         "\n  pushback scores near zero. The sign is what matters; the n's are small.",
)

# --------------------------------------------------------------- e. net effect
print("=" * 96)
print("(e) NET EFFECT OF THE WHOLE CONTEST PROCESS ON ACCURACY")
print("=" * 96)
print("Definitions copied from `records/derivations/sweep-phantom-corrected.py`: a cell's")
print("final verdict is the ruling if the contest produced one and the decision otherwise;")
print("`fixed` = wrong before and right after, `broken` = right before and wrong after.")
print("`acc before` is identical in the two trees by construction (same decisions).")
print()
print(f"{'condition':<15}{'| SWEEP':<40}{'| RECONTEST':<40}")
print(f"{'':<15}{'before  after   fix  brk   net':<40}{'before  after   fix  brk   net':<40}")
print("-" * 96)
for label, c in STRATA:
    def netrow(idx):
        rs = sub(idx, c)
        before = sum(1 for r in rs if r["initially_correct"])
        after = sum(1 for r in rs if r["final_correct"])
        fixed = sum(1 for r in rs if not r["initially_correct"] and r["final_correct"])
        broke = sum(1 for r in rs if r["initially_correct"] and not r["final_correct"])
        return (
            f"{pct(before, len(rs)):>6}{pct(after, len(rs)):>8}"
            f"{fixed:>6}{broke:>5}{f'{fixed - broke:+d}':>6}"
        )
    print(f"{label:<15}{'| ' + netrow(sweep):<40}{'| ' + netrow(recon):<40}")
print()
for label, c in STRATA:
    rs_s, rs_r = sub(sweep, c), sub(recon, c)
    b = sum(1 for r in rs_s if r["initially_correct"])
    print(
        f"  {label:<14} n={len(rs_s):<6} correct before = {b}/{len(rs_s)}  "
        f"sweep after = {sum(1 for r in rs_s if r['final_correct'])}/{len(rs_s)}  "
        f"recontest after = {sum(1 for r in rs_r if r['final_correct'])}/{len(rs_r)}"
    )
print()

# --------------------------------------------------------------- f. end-to-end
print("=" * 96)
print("(f) END-TO-END — of a condition's OWN wrong decisions, genuinely contested AND overturned")
print("=" * 96)
print("Detection x revision, unconditional, over that condition's own incorrect cell. The")
print("denominators differ between conditions (see metrics.json's first caveat): these are")
print("not the same items and the comparison is confounded with item difficulty.")
print()
side_by_side(
    "END-TO-END",
    "fixed_genuinely/inc rate",
    lambda rs: f"{len(overturn(genuine(on_wrong(rs))))}/{len(on_wrong(rs))}".ljust(20)
    + pct(len(overturn(genuine(on_wrong(rs)))), len(on_wrong(rs))),
)

# ------------------------------------------------------------ g. transitions
print("=" * 96)
print("(g) PER-CELL TRANSITIONS — what happened to the SAME decision under the two layers")
print("=" * 96)
print("STANCE: the challenger's `Decision:` line word, sweep -> recontest.")
print()
for label, c in STRATA:
    ids = [cid for cid in cells if c is None or sweep[cid]["condition"] == c]
    t = Counter((sweep[cid]["challenge_stance"], recon[cid]["challenge_stance"]) for cid in ids)
    n = len(ids)
    print(f"  {label}  (n={n})")
    for k in sorted(t):
        print(f"    {k[0]:<10} -> {k[1]:<10} {t[k]:>6}   {pct(t[k], n):>7}")
    kept = t[("contests", "contests")]
    dropped = t[("contests", "declined")]
    gained = t[("declined", "contests")]
    print(
        f"    net: {dropped} objections dropped, {gained} newly raised, {kept} raised in both"
        f"  ({pct(kept, kept + dropped)} of the sweep's objections survive)"
    )
    print()
print("STANCE x PROSE: the same transition counted on the GENUINE definition")
print("(line REVERSE and the agreement stage reading the prose as WRONG).")
print()
for label, c in STRATA:
    ids = [cid for cid in cells if c is None or sweep[cid]["condition"] == c]

    def g(r):
        """genuine / phantom / NEITHER-prose objection / no objection — four, not three.

        A `contests` line whose prose the agreement stage read as NEITHER is not a
        phantom (that word means prose RIGHT) and not a detection; folding it into
        "no objection" would understate the objection count by 7 rows in the sweep and
        1 in the re-contest, so it gets its own label."""
        if r["challenge_stance"] != "contests":
            return "no objection"
        if r["prose_stance"] == "WRONG":
            return "genuine"
        return "phantom" if r["phantom_contest"] else "objection/NEITHER"
    t = Counter((g(sweep[cid]), g(recon[cid])) for cid in ids)
    print(f"  {label}  (n={len(ids)})")
    for k in sorted(t):
        print(f"    {k[0]:<13} -> {k[1]:<13} {t[k]:>6}")
    print()
print("RULING OUTCOME, on the cells RULED IN BOTH trees (both raised an objection and both")
print("got a ruling written). `overturn` = `changed_the_decision`.")
print()
for label, c in STRATA:
    ids = [
        cid for cid in cells
        if (c is None or sweep[cid]["condition"] == c)
        and sweep[cid].get("ruling_form") and recon[cid].get("ruling_form")
    ]
    t = Counter(
        ("overturn" if sweep[cid]["changed_the_decision"] else "uphold",
         "overturn" if recon[cid]["changed_the_decision"] else "uphold")
        for cid in ids
    )
    print(f"  {label}  (ruled in both: n={len(ids)})")
    for k in sorted(t):
        print(f"    sweep {k[0]:<9} -> recontest {k[1]:<9} {t[k]:>6}   {pct(t[k], len(ids)):>7}")
    only_s = sum(
        1 for cid in cells
        if (c is None or sweep[cid]["condition"] == c)
        and sweep[cid].get("ruling_form") and not recon[cid].get("ruling_form")
    )
    only_r = sum(
        1 for cid in cells
        if (c is None or sweep[cid]["condition"] == c)
        and recon[cid].get("ruling_form") and not sweep[cid].get("ruling_form")
    )
    print(f"    ruled in the sweep only: {only_s}      ruled in the recontest only: {only_r}")
    print()

# ------------------------------------------- h. repairs, parse_mode, gloss leak
print("=" * 96)
print("(h) THE RE-CONTEST CHALLENGER: REPAIRS, PARSE MODE, AND THE RESIDUAL GLOSS LEAK")
print("=" * 96)
idx_keys = set()
for path in (SWEEP, RECON):
    with path.open() as fh:
        idx_keys |= set(json.loads(fh.readline()))
carried = sorted(k for k in idx_keys if "repair" in k or "parse_mode" in k)
print(f"index.jsonl carries repair/parse_mode fields: {carried or 'NO — deriving from the run tree'}")
tree = RECON.parent / "cells"
if not tree.is_dir():
    print(f"cells/ not present beside {RECON} — section (h) cannot be derived from this copy.")
    print("Run this script against `outputs/experiments/recontest/index.jsonl` to fill it in;")
    print("`records/experiments/recontest/recontest-vs-sweep.log` is that run.")
else:
    modes, reps, gloss_hits, n_ch = Counter(), Counter(), [], 0
    by_cond_gloss = Counter()
    for cid in cells:
        found = sorted((tree / cid).glob("contests/*/runs/*/challenge.json"))
        if not found:
            continue
        ch = json.load(found[-1].open())
        n_ch += 1
        modes[ch.get("parse_mode")] += 1
        reps[ch.get("repair_attempts")] += 1
        low = (ch.get("text") or "").lower()
        if any(g in low for g in GLOSS):
            gloss_hits.append(cid)
            by_cond_gloss[recon[cid]["condition"]] += 1
    print(f"challenge.json read: {n_ch}/{len(cells)}")
    print()
    print("parse_mode        n        share")
    print("-" * 34)
    for k in sorted(modes, key=lambda x: (x is None, str(x))):
        print(f"{str(k):<16}{modes[k]:>6}{pct(modes[k], n_ch):>12}")
    print()
    print("repair_attempts   n        share")
    print("-" * 34)
    for k in sorted(reps, key=lambda x: (x is None, x)):
        print(f"{str(k):<16}{reps[k]:>6}{pct(reps[k], n_ch):>12}")
    print(f"replies needing >=1 repair: {sum(v for k, v in reps.items() if k)}/{n_ch}"
          f" = {pct(sum(v for k, v in reps.items() if k), n_ch)}")
    print()
    print("RESIDUAL INSTRUCTION GLOSS — the new decision instruction spells the two words out")
    print(f"as \"you agree: …\" / \"you disagree: …\". A reply containing either phrase is echoing")
    print("the prompt's own gloss into its public text, where the agreement stage then reads it.")
    print(f"  Challenge.text containing {' or '.join(repr(g) for g in GLOSS)}: "
          f"{len(gloss_hits)}/{n_ch} = {pct(len(gloss_hits), n_ch)}")
    for c in CONDS:
        print(f"    {c:<15}{by_cond_gloss[c]:>5}")
    for cid in gloss_hits[:20]:
        print(f"    e.g. {cid}")
    if len(gloss_hits) > 20:
        print(f"    ... and {len(gloss_hits) - 20} more")
print()
print("=" * 96)
print("END")
print("=" * 96)

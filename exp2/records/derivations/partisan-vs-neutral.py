"""NEUTRAL vs PARTISAN — the same decisions, contested by different challengers.

The neutral decide-last challenger objects on ~8% of cells, so every recourse-stage
rate (the judge's discrimination, the grader's valid rate, the phantom rate) rests on
tens of cells per condition. The **partisan** challenger is the planned ablation that
raises n: it is assigned the answer the decision went against and argues the decision
was mistaken, and may still report finding no grounds. Same decisions, same judge, same
instruments, same grader — only the challenger's standpoint differs.

    uv run python records/derivations/partisan-vs-neutral.py \
        --neutral records/experiments/rerule/recontest/index.jsonl \
        --partisan outputs/experiments/partisan-pilot-advocate/index.jsonl \
                   outputs/experiments/partisan-pilot-assigned/index.jsonl \
                   outputs/experiments/partisan-pilot-auditor/index.jsonl

`--partisan` takes ONE OR MORE indices, so the three pilot clauses print side by side in
one table: one column per index, labelled by the `name` in the sibling `experiment.json`
(else by the path). Every comparison is restricted to the cells present in **ALL** given
indices — the pilots cover pilot-3's 207 cells (194 decided) and the neutral index covers
the sweep's 5,724 — and the JOIN block says how many that is and what was dropped.

WHAT THE ABLATION MEASURES, AND WHAT IT DOES NOT. Under advocacy, "detection" becomes
"could an advocate find grounds", and false alarms on correct decisions are high by
construction. The partisan run is a measurement of the JUDGE and the GRADER at scale,
plus one quantity the neutral run cannot give: how often an advocate declines when the
record supports the decision. Its raise rate is not the neutral variant's raise rate and
the two must never be pooled. The neutral variant remains the design's primary
measurement.

**It reads only `index.jsonl` files**, so it runs from the committed copies on a blank
machine after `git clone` — no run tree, no `calls.jsonl`, no network, no API key.

One quantity is *derived* rather than read, exactly as `rerule-compare.py` derives it:

  * a ruling's own verdict — `verdict` when `changed_the_decision` is false, the other
    verdict when it is true. `Ruling` enforces `resolve_ruling(ruling, parent) ==
    verdict`, so this inversion is the record, not an inference. Section (d) rebuilds
    `final_correct` from it against `gold_flawed` and reports any cell where the
    rebuild disagrees with the index (there should be none).

THE NEUTRAL INDEX AND ITS DECLINES. `records/experiments/rerule/recontest/index.jsonl` is
a RE-RULE tree: it re-ruled the re-contest's objections and therefore carries challenge
columns only for the 464 cells whose neutral challenger actually objected. Its other rows
have no `challenge_stance` at all — which is "this cell's neutral challenge lives in the
source tree", not "the neutral challenger declined". `--neutral-stances` (default
`records/experiments/recontest/index.jsonl`, the re-contest's own index, committed) fills
those stances in for the joined cells, keeping the ruling-side columns from the re-rule
tree — the corrected ruling line — and asserting the two agree wherever both carry a
stance. `--no-stance-fill` turns it off; the decline columns then print "not in index".

Definitions are shared with `records/derivations/sweep-phantom-corrected.py` and
`rerule-compare.py` and must stay identical to them:

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

# The go/no-go constants, from the plan. The phantom ceiling is the neutral run's own
# all-contests phantom share (LLM_NOTES 3s); the ratio gate is "clearly above neutral".
NEUTRAL_PHANTOM_CEILING = 0.13
GENUINE_RATIO_GATE = 2.0

# What the re-rule tree contributes to a merged neutral row: the ruling made under the
# corrected line, and the instrument that reads it.
RULING_KEYS = ("ruling_form", "changed_the_decision", "final_correct",
               "ruling_prose_conclusion", "ruling_line_mismatch")

W = 132
MW = 36          # metric-name column
CW = 24          # per-index column
                 # 24 fits the longest experiment name in play
                 # ('partisan-pilot-advocate') without truncation


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


def pad(text, width=CW):
    """Left-justify, but never let two columns run together when one overflows."""
    return text.ljust(width) if len(text) < width else text + "  "


def other(verdict):
    return VERDICTS[1] if verdict == VERDICTS[0] else VERDICTS[0]


def table(labels, metrics):
    """rows = metrics, columns = indices."""
    print(pad("", MW) + "".join(pad(l[:CW - 1]) for l in labels))
    rule()
    for name, vals in metrics:
        print(pad(name, MW) + "".join(pad(v) for v in vals))


# --------------------------------------------------------------------------- #
# the index
# --------------------------------------------------------------------------- #


def load(path: Path) -> dict[str, dict]:
    if not path.is_file():
        raise SystemExit(f"no such index: {path}")
    rows = {}
    for n, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path}:{n}: not JSON ({exc})")
        if "cell_id" not in row:
            raise SystemExit(f"{path}:{n}: no cell_id — is this an index.jsonl?")
        rows[row["cell_id"]] = row
    if not rows:
        raise SystemExit(f"{path}: empty index")
    return rows


def label_for(path: Path) -> str:
    """The experiment's own name, from the sibling experiment.json; else the path."""
    exp = path.parent / "experiment.json"
    if exp.is_file():
        try:
            name = json.loads(exp.read_text()).get("name")
        except (OSError, json.JSONDecodeError):
            name = None
        if name:
            return str(name)
    return path.parent.name or path.stem


def uniquify(labels):
    seen = Counter(labels)
    if all(v == 1 for v in seen.values()):
        return labels
    out, used = [], Counter()
    for l in labels:
        used[l] += 1
        out.append(l if seen[l] == 1 else f"{l}#{used[l]}")
    return out


# --------------------------------------------------------------------------- #
# per-row predicates — identical to sweep-phantom-corrected.py / rerule-compare.py
# --------------------------------------------------------------------------- #


def contested(row):
    return row.get("challenge_stance") == "contests"


def phantom(row):
    return contested(row) and row.get("prose_stance") == "RIGHT"


def genuine(row):
    return contested(row) and row.get("prose_stance") == "WRONG"


def neither(row):
    return contested(row) and row.get("prose_stance") == "NEITHER"


def declined(row):
    return row.get("challenge_stance") == "declined"


def ruled(row):
    return row.get("ruling_form") is not None


def overturned(row):
    return bool(row.get("changed_the_decision"))


def ruling_verdict(row):
    """The verdict the RULING settled on — derived, see the module docstring."""
    return other(row["verdict"]) if overturned(row) else row["verdict"]


def final_verdict(row):
    """The ruling's verdict if the contest produced one, else the decision's own."""
    return ruling_verdict(row) if ruled(row) else row["verdict"]


def final_correct(row):
    """What the index says. Absent (no contest at all) falls back to the decision."""
    fc = row.get("final_correct")
    return row.get("initially_correct") if fc is None and not ruled(row) else fc


def derived_final_correct(row):
    """Rebuilt from the derived ruling verdict against the label, for the cross-check."""
    gold = row.get("gold_flawed")
    if gold is None or row.get("initially_correct") is None:
        return None
    return (final_verdict(row) == "FLAWED") == bool(gold)


def stance_cat(row):
    """The cell's challenge, as one bucket, for the transition matrix."""
    s = row.get("challenge_stance")
    if s is None:
        return "no contest"
    if s != "contests":
        return s
    p = row.get("prose_stance")
    if p == "WRONG":
        return "contests|genuine"
    if p == "RIGHT":
        return "contests|phantom"
    if p == "NEITHER":
        return "contests|NEITHER"
    return "contests|unread"


CATS = ("contests|genuine", "contests|phantom", "contests|NEITHER", "contests|unread",
        "agrees", "declined", "unclear", "no contest")


# --------------------------------------------------------------------------- #


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Compare the neutral challenger with one or more partisan runs "
                    "over the cells they share.")
    ap.add_argument("--neutral", type=Path,
                    default=Path("records/experiments/rerule/recontest/index.jsonl"),
                    help="index.jsonl of the neutral baseline — the corrected ruling "
                         "line with ruling_agreement present (default: "
                         "records/experiments/rerule/recontest/index.jsonl)")
    ap.add_argument("--partisan", type=Path, nargs="+", required=True,
                    metavar="INDEX",
                    help="one or more partisan index.jsonl files; each becomes a column")
    ap.add_argument("--neutral-stances", type=Path,
                    default=Path("records/experiments/recontest/index.jsonl"),
                    help="index carrying the neutral challenger's stance on EVERY cell, "
                         "used only to fill stances the --neutral index does not have "
                         "(a re-rule tree carries them only for the cells it re-ruled). "
                         "Ruling-side columns always stay the --neutral index's. "
                         "(default: records/experiments/recontest/index.jsonl)")
    ap.add_argument("--no-stance-fill", action="store_true",
                    help="do not fill neutral stances from --neutral-stances; the "
                         "decline columns then read 'not in index'")
    args = ap.parse_args()

    neutral = load(args.neutral)
    parts = [load(p) for p in args.partisan]
    labels = uniquify([label_for(args.neutral)]
                      + [label_for(p) for p in args.partisan])
    paths = [args.neutral] + list(args.partisan)

    # ------------------------------------------------------------------- join
    cells = set(neutral)
    for p in parts:
        cells &= set(p)
    cells = sorted(cells)
    if not cells:
        raise SystemExit(
            "the given indices share no cell_id — nothing to compare. Indices: "
            + ", ".join(f"{p} ({len(r)} rows)"
                        for p, r in zip(paths, [neutral] + parts)))

    # ------------------------------------------------------ neutral stance fill
    need = [c for c in cells if neutral[c].get("challenge_stance") is None]
    filled = unfilled = checked = 0
    fill_note = ""
    if not need:
        fill_note = ("not needed — the --neutral index carries a challenge on every "
                     "joined cell")
    elif args.no_stance_fill:
        unfilled = len(need)
        fill_note = "disabled (--no-stance-fill)"
    elif not args.neutral_stances.is_file():
        unfilled = len(need)
        fill_note = f"unavailable — no such file: {args.neutral_stances}"
    else:
        st = load(args.neutral_stances)
        bad = []
        for c in cells:
            s = st.get(c)
            if s is None:
                if neutral[c].get("challenge_stance") is None:
                    unfilled += 1
                continue
            for f in ("verdict", "initially_correct", "gold_flawed"):
                if s.get(f) != neutral[c].get(f):
                    bad.append(f"{c}: {f} {s.get(f)!r} != {neutral[c].get(f)!r}")
            if neutral[c].get("challenge_stance") is None:
                if s.get("challenge_stance") is None:
                    unfilled += 1
                    continue
                merged = dict(s)
                for k in RULING_KEYS:
                    if k in neutral[c]:
                        merged[k] = neutral[c][k]
                    else:
                        merged.pop(k, None)
                neutral[c] = merged
                filled += 1
            else:
                checked += 1
                for f in ("challenge_stance", "prose_stance"):
                    if s.get(f) is not None and s.get(f) != neutral[c].get(f):
                        bad.append(
                            f"{c}: {f} {s.get(f)!r} in --neutral-stances != "
                            f"{neutral[c].get(f)!r} in --neutral")
        if bad:
            raise SystemExit(
                "--neutral-stances does not describe the same run as --neutral:\n  "
                + "\n  ".join(bad[:20])
                + (f"\n  ... and {len(bad) - 20} more" if len(bad) > 20 else ""))
        fill_note = (f"{filled} stances filled from {args.neutral_stances}, "
                     f"{checked} cross-checked, {unfilled} still unknown")

    # ---------------------------------------------------------------- asserts
    fails = []
    for c in cells:
        n = neutral[c]
        for lab, p in zip(labels[1:], parts):
            for f in ("verdict", "initially_correct", "gold_flawed"):
                if n.get(f) != p[c].get(f):
                    fails.append(f"{c}: {f} {n.get(f)!r} (neutral) != "
                                 f"{p[c].get(f)!r} ({lab})")
    if fails:
        raise SystemExit(
            "the indices do not describe the same decisions — a partisan run must "
            "read the sweep's decisions, never make its own:\n  "
            + "\n  ".join(fails[:20])
            + (f"\n  ... and {len(fails) - 20} more" if len(fails) > 20 else ""))

    cols = [[idx[c] for c in cells] for idx in [neutral] + parts]
    conds = [c for c in CONDS if any(r["condition"] == c for r in cols[0])] + [POOLED]

    def sel(col, cond):
        return col if cond == POOLED else [r for r in col if r["condition"] == cond]

    def per(cond, fn):
        return [fn(sel(col, cond)) for col in cols]

    # ------------------------------------------------------------------ header
    print("=" * W)
    print("PARTISAN vs NEUTRAL — the same decisions, contested by different challengers")
    print("=" * W)
    for i, (lab, p) in enumerate(zip(labels, paths)):
        kind = "NEUTRAL " if i == 0 else "PARTISAN"
        print(f"{kind}  {lab:<28}{p}")
    print()
    print("WHAT THIS COMPARISON MEANS")
    rule()
    print("Under the partisan variant the challenger is ASSIGNED the answer the decision")
    print("went against and argues the decision was mistaken; it may still report finding")
    print("no grounds. So 'detection' here reads 'could an advocate find grounds', and")
    print("false alarms on correct decisions are high BY CONSTRUCTION. What the ablation")
    print("measures at raised n is the JUDGE (does it overturn genuine-on-wrong more than")
    print("genuine-on-correct), the GRADER (valid-objection rate), the phantom rate under")
    print("advocacy, and how often an advocate declines when the record supports the")
    print("decision. The neutral column is the design's primary measurement; the raise")
    print("rates in the two columns are different quantities and must not be pooled.")
    print()
    print("Decisions, labels and conditions are IDENTICAL across the columns by")
    print("construction — every run reads the sweep's decisions — and this is asserted")
    print("cell by cell below. Everything downstream of the challenger is what differs.")

    head("JOIN")
    for lab, p, idx in zip(labels, paths, [neutral] + parts):
        print(f"rows in {lab:<28}{len(idx):>7}   {p}")
    print(f"{'cells present in ALL indices':<36}{len(cells):>7}   <- every table below")
    for lab, idx in zip(labels, [neutral] + parts):
        print(f"  dropped from {lab:<23}{len(idx) - len(cells):>7}")
    print()
    print(f"neutral stance fill: {fill_note}")
    if unfilled:
        print(f"  {unfilled} joined cells have NO neutral challenge on record. They stay")
        print("  in every denominator that counts CELLS and are excluded from the neutral")
        print("  column's stance counts, where they show as 'no contest'.")
    print()
    print("identity asserted cell by cell on verdict, initially_correct, gold_flawed: "
          f"{len(cells)}/{len(cells)} identical.")
    print()
    print("joined cells by condition:")
    for c in conds:
        print(f"  {c:<16}{len(sel(cols[0], c)):>6}")
    lab_n = sum(1 for r in cols[0] if r.get("initially_correct") is not None)
    print(f"  {'labelled':<16}{lab_n:>6}   (unlabelled cells are excluded from every "
          "accuracy figure)")

    # ------------------------------------------------------- (a) the detection
    head("(a) WHAT THE CHALLENGER DID")
    print("raised          challenge_stance == contests (the Decision: line said REVERSE)")
    print("GENUINE raised  contests AND the agreement stage read the prose as arguing the")
    print("                verdict was WRONG — the only objections that count as detection")
    print("phantom share   of raised, the ones whose own prose endorsed the verdict")
    print("declined        the challenger said the decision should stand. Split by whether")
    print("                the decision was in fact right: declining on a CORRECT decision")
    print("                is the advocate's honesty, and a 0% rate means 'let it stand'")
    print("                is dead. Declining on a WRONG decision is a missed detection.")
    print()
    arms = []
    for col in cols:
        c = Counter(r["challenge_arm"] for r in col if r.get("challenge_arm") is not None)
        arms.append(", ".join(f"{k}={v}" for k, v in sorted(c.items()))
                    if c else "not in index")
    print(pad("challenge_arm in the index", MW) + "".join(pad(a) for a in arms))
    print("  (the neutral index predates the challenge_arm column; 'not in index' there")
    print("   means the run was neutral by construction, not that the arm is unknown)")
    for cond in conds:
        print()
        print(f"--- {cond} ---")
        no_contest = per(cond, lambda rs: sum(1 for r in rs
                                              if r.get("challenge_stance") is None))
        metrics = [
            ("cells", per(cond, lambda rs: str(len(rs)))),
            ("  with a challenge on record",
             per(cond, lambda rs: str(sum(1 for r in rs
                                          if r.get("challenge_stance") is not None)))),
            ("objections raised",
             per(cond, lambda rs: rate(sum(1 for r in rs if contested(r)), len(rs)))),
            ("GENUINE raised (prose WRONG)",
             per(cond, lambda rs: rate(sum(1 for r in rs if genuine(r)), len(rs)))),
            ("phantom share of raised",
             per(cond, lambda rs: rate(sum(1 for r in rs if phantom(r)),
                                       sum(1 for r in rs if contested(r))))),
            ("prose NEITHER, of raised",
             per(cond, lambda rs: rate(sum(1 for r in rs if neither(r)),
                                       sum(1 for r in rs if contested(r))))),
            ("declined",
             per(cond, lambda rs: rate(sum(1 for r in rs if declined(r)), len(rs)))),
            ("  declined | CORRECT decision",
             per(cond, lambda rs: rate(
                 sum(1 for r in rs if declined(r) and r.get("initially_correct")),
                 sum(1 for r in rs if r.get("initially_correct"))))),
            ("  declined | WRONG decision",
             per(cond, lambda rs: rate(
                 sum(1 for r in rs if declined(r) and r.get("initially_incorrect")),
                 sum(1 for r in rs if r.get("initially_incorrect"))))),
            ("agrees",
             per(cond, lambda rs: str(sum(1 for r in rs
                                          if r.get("challenge_stance") == "agrees")))),
            ("stance unclear (unparsed line)",
             per(cond, lambda rs: str(sum(1 for r in rs
                                          if r.get("challenge_stance") == "unclear")))),
            ("contradictory line",
             per(cond, lambda rs: str(sum(1 for r in rs
                                          if r.get("challenge_contradictory"))))),
            ("no contest on record",
             [str(v) for v in no_contest]),
        ]
        table(labels, metrics)

    # --------------------------------------------- (b) the ruling instrument
    head("(b) THE RULING LINE vs THE JUDGE'S OWN PROSE  (ruling_line_mismatch)")
    print("Haiku reads the judge's REASONING ONLY, conclusion line stripped, and says")
    print("whether that prose concludes the text under review contains a flaw. A mismatch")
    print("is a ruling whose line contradicts the reasoning that produced it — the bound on")
    print("every number below that passes through a ruling. n = rulings.")
    print()
    for cond in conds:
        print(f"--- {cond} ---")

        def mism(rs):
            m = [r for r in rs if r.get("ruling_line_mismatch") is not None]
            if not m:
                return ("not present" if not any("ruling_line_mismatch" in r for r in rs)
                        else "n/a")
            return rate(sum(1 for r in m if r["ruling_line_mismatch"]), len(m))

        table(labels, [
            ("rulings made", per(cond, lambda rs: str(sum(1 for r in rs if ruled(r))))),
            ("ruling_line_mismatch", per(cond, mism)),
            ("  prose FLAWED",
             per(cond, lambda rs: str(sum(1 for r in rs
                                          if r.get("ruling_prose_conclusion") == "FLAWED")))),
            ("  prose SOUND",
             per(cond, lambda rs: str(sum(1 for r in rs
                                          if r.get("ruling_prose_conclusion") == "SOUND")))),
            ("  prose NEITHER",
             per(cond, lambda rs: str(sum(1 for r in rs
                                          if r.get("ruling_prose_conclusion") == "NEITHER")))),
        ])
        print()

    # ------------------------------------------------- (c) what was overturned
    head("(c) WHAT THE JUDGE OVERTURNED, BY WHAT WAS ACTUALLY OBJECTED TO")
    print("phantom        the line said REVERSE and the prose endorsed the verdict. A judge")
    print("               that reads the objection should overturn almost none of these.")
    print("genuine|wrong  prose WRONG on a decision that was in fact incorrect — the")
    print("               objections a working recourse channel is FOR.")
    print("genuine|corr   prose WRONG on a decision that was in fact correct — the specious")
    print("               objections it must resist.")
    print("discrimination = overturn on genuine|wrong minus overturn on genuine|corr. The")
    print("one figure a judge cannot raise by overturning everything. A raised objection")
    print("with no ruling counts as not overturned (metrics.json does the same).")
    print()
    for cond in conds:
        print(f"--- {cond} ---")

        def bucket(rs, which):
            if which == "phantom":
                return [r for r in rs if phantom(r)]
            if which == "gw":
                return [r for r in rs if genuine(r) and r.get("initially_incorrect")]
            if which == "gc":
                return [r for r in rs if genuine(r) and r.get("initially_correct")]
            return [r for r in rs if contested(r) and not phantom(r) and not genuine(r)]

        def ov(which):
            def f(rs):
                b = bucket(rs, which)
                return rate(sum(1 for r in b if overturned(r)), len(b))
            return f

        def disc(rs):
            gw, gc = bucket(rs, "gw"), bucket(rs, "gc")
            if not gw or not gc:
                return "n/a"
            d = (sum(1 for r in gw if overturned(r)) / len(gw)
                 - sum(1 for r in gc if overturned(r)) / len(gc))
            return f"{100 * d:+.1f} pts"

        table(labels, [
            ("overturn | phantom", per(cond, ov("phantom"))),
            ("overturn | genuine|wrong", per(cond, ov("gw"))),
            ("overturn | genuine|corr", per(cond, ov("gc"))),
            ("overturn | other/NEITHER", per(cond, ov("other"))),
            ("DISCRIMINATION", per(cond, disc)),
            ("raised with no ruling",
             per(cond, lambda rs: str(sum(1 for r in rs
                                          if contested(r) and not ruled(r))))),
        ])
        print()

    # --------------------------------------------------------------- (d) accuracy
    head("(d) NET EFFECT ON ACCURACY  (sweep-phantom-corrected.py's definitions)")
    print("A cell's final verdict is the ruling's if the contest produced one, else the")
    print("decision's own. fixed = wrong decision made right; broken = right decision made")
    print("wrong; net = fixed - broken. Over the JOINED cells. `acc before` is identical in")
    print("every column by construction (same decisions), which is the check that the join")
    print("is sound: the whole of any difference is the challenger's and the judge's.")
    print("Unlabelled cells are excluded and counted.")
    print()
    mism_d = []
    for col in cols:
        n = sum(1 for r in col
                if derived_final_correct(r) is not None
                and derived_final_correct(r) != final_correct(r))
        mism_d.append(n)
    for cond in conds:
        print(f"--- {cond} ---")

        def lab_rows(rs):
            return [r for r in rs if r.get("initially_correct") is not None]

        table(labels, [
            ("labelled cells", per(cond, lambda rs: str(len(lab_rows(rs))))),
            ("acc before",
             per(cond, lambda rs: pct(sum(1 for r in lab_rows(rs)
                                          if r["initially_correct"]), len(lab_rows(rs))))),
            ("acc after",
             per(cond, lambda rs: pct(sum(1 for r in lab_rows(rs)
                                          if final_correct(r)), len(lab_rows(rs))))),
            ("fixed / broken / net",
             per(cond, lambda rs: (
                 lambda L: (
                     lambda f, b: f"{f}/{b}/{f - b:+d}")(
                         sum(1 for r in L if not r["initially_correct"]
                             and final_correct(r)),
                         sum(1 for r in L if r["initially_correct"]
                             and not final_correct(r))))(lab_rows(rs)))),
            ("unlabelled", per(cond, lambda rs: str(len(rs) - len(lab_rows(rs))))),
        ])
        print()
    print("cross-check — final_correct rebuilt from the DERIVED ruling verdict against")
    print("gold_flawed, compared with the index's own column:")
    print(pad("  cells where the two disagree", MW)
          + "".join(pad(str(v)) for v in mism_d))
    if any(mism_d):
        print("  NON-ZERO: the derivation and the index disagree. Do not quote (d) until")
        print("  this is explained — one of the two is wrong about what the ruling settled.")

    # ------------------------------------------------------------- (e) end-to-end
    head("(e) END-TO-END — own wrong decisions genuinely contested AND overturned")
    print("Of a condition's own incorrect decisions among the joined cells, the fraction")
    print("where the challenger raised an objection whose PROSE argued the verdict was")
    print("wrong and the judge then overturned. Detection x revision, unconditional — the")
    print("number the whole recourse channel exists to move.")
    print()
    for cond in conds:
        print(f"--- {cond} ---")

        def inc(rs):
            return [r for r in rs if r.get("initially_incorrect")]

        table(labels, [
            ("incorrect decisions", per(cond, lambda rs: str(len(inc(rs))))),
            ("genuinely contested",
             per(cond, lambda rs: rate(sum(1 for r in inc(rs) if genuine(r)),
                                       len(inc(rs))))),
            ("... AND overturned",
             per(cond, lambda rs: rate(
                 sum(1 for r in inc(rs) if genuine(r) and overturned(r)), len(inc(rs))))),
        ])
        print()

    # ---------------------------------------------------------------- (f) grader
    head("(f) THE GRADER — did the objection name the flaw the dataset annotates?")
    print("The grade stage's own gate (run_stage_grade) is: the stance is `contests` AND")
    print("the item is gold-flawed with an annotation AND the DECISION WAS INCORRECT —")
    print("`P(valid objection | initially incorrect)`, so an objection to a decision that")
    print("was right is a false alarm whose validity is undefined by design and is never")
    print("graded. `gradable & contested & wrong` below is that gate as far as the index")
    print("can express it (annotation_quality is not an index column, so a cell whose")
    print("annotation records nothing to grade against shows up as eligible-but-ungraded).")
    print("n is small and is printed with every rate. The index columns are")
    print("`identified_flaw`, `characterises_the_flaw` and `grade_valid` (build_index emits")
    print("no `grade_identified`).")
    print()
    for cond in conds:
        print(f"--- {cond} ---")

        def graded(rs):
            return [r for r in rs if r.get("grade_valid") is not None
                    or r.get("identified_flaw") is not None]

        table(labels, [
            ("gradable cells",
             per(cond, lambda rs: str(sum(1 for r in rs if r.get("gradable"))))),
            ("gradable & contested & wrong",
             per(cond, lambda rs: str(sum(1 for r in rs if r.get("gradable")
                                          and contested(r)
                                          and r.get("initially_incorrect"))))),
            ("graded rows", per(cond, lambda rs: str(len(graded(rs))))),
            ("identified_flaw",
             per(cond, lambda rs: rate(sum(1 for r in graded(rs)
                                           if r.get("identified_flaw")), len(graded(rs))))),
            ("characterises_the_flaw",
             per(cond, lambda rs: rate(sum(1 for r in graded(rs)
                                           if r.get("characterises_the_flaw")),
                                       len(graded(rs))))),
            ("grade_valid",
             per(cond, lambda rs: rate(sum(1 for r in graded(rs)
                                           if r.get("grade_valid")), len(graded(rs))))),
        ])
        print()

    # ------------------------------------------------------------- (g) go / no-go
    _go_no_go(labels, cols, cells)

    # ---------------------------------------------------------- (h) transitions
    head("(h) PER-CELL STANCE TRANSITIONS  neutral -> partisan")
    print("What advocacy ADDS, cell by cell: which declines became objections, whether")
    print("those objections were genuine or phantom, and which neutral objections the")
    print("advocate dropped. Rows = the neutral stance, columns = the partisan stance.")
    print("`no contest` is a cell with no challenge on record in that index.")
    print()
    for lab, col in zip(labels[1:], cols[1:]):
        print(f"--- neutral -> {lab} ---")
        t = Counter((stance_cat(n), stance_cat(p)) for n, p in zip(cols[0], col))
        present_cols = [c for c in CATS if any(k[1] == c for k in t)]
        present_rows = [c for c in CATS if any(k[0] == c for k in t)]
        print(pad("neutral \\ partisan", 22) + "".join(f"{c:>19}" for c in present_cols)
              + f"{'total':>9}")
        rule()
        for r in present_rows:
            row_total = sum(v for k, v in t.items() if k[0] == r)
            print(pad(r, 22) + "".join(f"{t[(r, c)]:>19}" for c in present_cols)
                  + f"{row_total:>9}")
        rule()
        print(pad("total", 22)
              + "".join(f"{sum(v for k, v in t.items() if k[1] == c):>19}"
                        for c in present_cols)
              + f"{sum(t.values()):>9}")
        print()
        added = sum(v for k, v in t.items()
                    if k[0] in ("declined", "agrees", "no contest")
                    and k[1] == "contests|genuine")
        added_ph = sum(v for k, v in t.items()
                       if k[0] in ("declined", "agrees", "no contest")
                       and k[1] == "contests|phantom")
        dropped = sum(v for k, v in t.items()
                      if k[0].startswith("contests") and k[1] == "declined")
        kept = sum(v for k, v in t.items()
                   if k[0] == "contests|genuine" and k[1] == "contests|genuine")
        print(f"  genuine objections ADDED by advocacy   {added}")
        print(f"  phantom objections added by advocacy   {added_ph}")
        print(f"  neutral objections the advocate DROPPED  {dropped}")
        print(f"  genuine in both                        {kept}")
        print()

    print()
    rule("=")
    print("end")


# --------------------------------------------------------------------------- #
# (g) the go/no-go — tabulated, not decided
# --------------------------------------------------------------------------- #


def _go_no_go(labels, cols, cells) -> None:
    """The plan's step-6 rule, computed. Fable makes the decision; this tabulates it.

    GO with the clause with the highest GENUINE raise rate subject to
      (i)   phantom share of raised <= the neutral run's 13%
      (ii)  at least some declines on CORRECT decisions
      (iii) parse failures ~ 0
    and only if some clause raises the genuine rate to >= 2x the neutral POOLED rate.
    """
    head("(g) GO / NO-GO  (the plan's step-6 rule, computed)")
    print("The rule: GO with the clause with the HIGHEST genuine raise rate, subject to")
    print(f"  (i)   phantom share of raised <= {NEUTRAL_PHANTOM_CEILING:.0%} "
          "(the neutral run's all-contests share)")
    print("  (ii)  at least some declines on CORRECT decisions — a 0% decline rate means")
    print("        'let it stand' is dead and the advocate is manufacturing a case")
    print("  (iii) parse failures ~ 0 (index-visible proxy: stance `unclear` and")
    print("        `challenge_contradictory`; true parse/repair counts live in the run")
    print("        log, not the index)")
    print(f"and only if some clause reaches >= {GENUINE_RATIO_GATE:g}x the NEUTRAL POOLED "
          "genuine raise rate.")
    print("This block does not decide anything. It prints the four clauses of the rule")
    print("with their numbers so the decision is made from them and can be re-checked.")
    print()

    neutral = cols[0]
    n_gen = sum(1 for r in neutral if genuine(r))
    n_rate = n_gen / len(neutral) if neutral else 0.0
    n_raised = sum(1 for r in neutral if contested(r))
    n_ph = sum(1 for r in neutral if phantom(r))
    print(f"neutral pooled: genuine raise {rate(n_gen, len(neutral))}   "
          f"raised {rate(n_raised, len(neutral))}   "
          f"phantom share of raised {rate(n_ph, n_raised)}")
    print(f"neutral gate:   >= {GENUINE_RATIO_GATE:g}x {pct(n_gen, len(neutral))} = "
          f"{100 * GENUINE_RATIO_GATE * n_rate:.1f}% genuine raise")
    print()

    rows = []
    for lab, col in zip(labels[1:], cols[1:]):
        n = len(col)
        gen = sum(1 for r in col if genuine(r))
        raised = sum(1 for r in col if contested(r))
        ph = sum(1 for r in col if phantom(r))
        dec_cor = sum(1 for r in col if declined(r) and r.get("initially_correct"))
        cor = sum(1 for r in col if r.get("initially_correct"))
        unclear = sum(1 for r in col if r.get("challenge_stance") == "unclear")
        contra = sum(1 for r in col if r.get("challenge_contradictory"))
        g_rate = gen / n if n else 0.0
        ratio = (g_rate / n_rate) if n_rate else float("inf") if g_rate else 0.0
        ph_share = ph / raised if raised else 0.0
        rows.append(dict(
            label=lab, n=n, gen=gen, g_rate=g_rate, raised=raised, ph=ph,
            ph_share=ph_share, dec_cor=dec_cor, cor=cor, unclear=unclear,
            contra=contra, ratio=ratio,
            c_ph=(raised > 0 and ph_share <= NEUTRAL_PHANTOM_CEILING),
            c_dec=dec_cor > 0,
            c_parse=(unclear + contra) == 0,
            c_ratio=(ratio >= GENUINE_RATIO_GATE and n_rate > 0)))

    print(pad("clause", 40) + "".join(pad(r["label"][:CW - 1]) for r in rows))
    rule()
    print(pad("genuine raise rate", 40)
          + "".join(pad(rate(r["gen"], r["n"])) for r in rows))
    print(pad(f"  x neutral pooled ({pct(n_gen, len(neutral))})", 40)
          + "".join(pad(f"{r['ratio']:.2f}x" if n_rate else "n/a") for r in rows))
    print(pad(f"  >= {GENUINE_RATIO_GATE:g}x neutral?", 40)
          + "".join(pad("PASS" if r["c_ratio"] else "FAIL") for r in rows))
    print(pad("phantom share of raised", 40)
          + "".join(pad(rate(r["ph"], r["raised"])) for r in rows))
    print(pad(f"  <= {NEUTRAL_PHANTOM_CEILING:.0%}?", 40)
          + "".join(pad("PASS" if r["c_ph"] else "FAIL") for r in rows))
    print(pad("declines on CORRECT decisions", 40)
          + "".join(pad(rate(r["dec_cor"], r["cor"])) for r in rows))
    print(pad("  > 0?", 40)
          + "".join(pad("PASS" if r["c_dec"] else "FAIL") for r in rows))
    print(pad("unclear + contradictory lines", 40)
          + "".join(pad(f"{r['unclear']}+{r['contra']}") for r in rows))
    print(pad("  ~ 0?", 40)
          + "".join(pad("PASS" if r["c_parse"] else "FAIL") for r in rows))
    rule()
    print(pad("all four clauses", 40)
          + "".join(pad("PASS" if (r["c_ph"] and r["c_dec"] and r["c_parse"]
                                   and r["c_ratio"]) else "FAIL") for r in rows))
    print()
    eligible = [r for r in rows
                if r["c_ph"] and r["c_dec"] and r["c_parse"] and r["c_ratio"]]
    if eligible:
        best = max(eligible, key=lambda r: r["g_rate"])
        print(f"GO: {best['label']}")
        print(f"  highest genuine raise rate among the clauses passing all four: "
              f"{rate(best['gen'], best['n'])} "
              f"({best['ratio']:.2f}x the neutral pooled rate), phantom share "
              f"{rate(best['ph'], best['raised'])}, declines on correct decisions "
              f"{rate(best['dec_cor'], best['cor'])}.")
        losers = [r for r in eligible if r is not best]
        if losers:
            print("  also eligible: "
                  + ", ".join(f"{r['label']} ({pct(r['gen'], r['n'])})" for r in losers))
    else:
        print("NO-GO")
        for r in rows:
            bad = [name for name, ok in (("2x neutral", r["c_ratio"]),
                                         ("phantom ceiling", r["c_ph"]),
                                         ("declines on correct", r["c_dec"]),
                                         ("parse failures", r["c_parse"])) if not ok]
            print(f"  {r['label']}: fails {', '.join(bad)}")
        print("  Per the plan: stop, record the results in LLM_NOTES, report to the user,")
        print("  and do NOT run the full sweep.")
    print()
    print("Fable decides. The hand check of the transcripts is the other half of it: does")
    print("the advocate argue the assigned side, and is its Decision: line consistent with")
    print("its own prose? Numbers alone cannot answer that.")


if __name__ == "__main__":
    main()

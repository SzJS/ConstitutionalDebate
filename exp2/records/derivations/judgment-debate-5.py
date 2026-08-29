"""judgment-debate-5 — one paragraph of Step 1, put to the same judge twice.

    cd exp2
    uv run python records/derivations/judgment-debate-5.py \
        2>&1 | tee outputs/judgment-debate-5-derivation.log

Stdlib only. It reads `index.jsonl` files and two small `ruling-language.jsonl` files and
nothing else, so it runs on a blank machine straight after `git clone` — no run tree, no
`calls.jsonl`, no network, no key. Every path is a flag, so the same script runs against
the committed indexes in `records/experiments/judgment-debate-{3,4,5}/` and against a live
`outputs/experiments/` tree without editing a line; `--help` lists them all.

The loaders, the exact McNemar, the Wilson interval, the paired block and the population
restriction are IMPORTED from `judgment-debate-4.py` rather than copied: the two files
print rates about the same 896 cells side by side in one write-up, and a definition that
drifted between them would be invisible.

WHAT CHANGED, AND IT IS ONE PARAGRAPH. `judgment-debate-4` found the recourse judge
answering Step 1 — *is each alleged defect real?* — by looking up the RECORD quotation and
never asking whether the judgment contains the sentence attributed to it, so an objection
whose every `Judgment says:` quotation was INVENTED still moved 10.2% of the rulings. The
repair, committed at `8ec5384` as `RECOURSE_JUDGE_USER_JUDGMENT` sha256
`e77eb5da04e21b64299c2fa09de427f108fc3e55f7368de2e58fbec0100cb7ca`, adds an existence check
as the first thing Step 1 does: find the `Judgment says:` sentence in the judgment; if the
words are not there the defect is not real; name the quotation you could not find; do not
repair the objection on its behalf; do not rule on what the judgment "implies"; omissions
are exempt. Everything else in the template is byte-identical, and `RECOURSE_JUDGE_USER`
— the neutral arm's — did not move at all.

TWO ARMS, ONE CHANGE, THE SAME 896 CELLS, NO CHALLENGER CALL IN EITHER:

    A  jd5-recheck-fabricated   jd4's 896 FABRICATED objections, re-ruled   vs jd4
    B  jd5-recheck-real         jd3 M1's 896 REAL objections, re-ruled      vs M1

Arm A alone would prove nothing — a check that refused objections quoting the judgment as
saying what it does not say would look identical, on arm A, to a check that refused
everything. Arm B is the price tag. Section (0) prints both paired tables FIRST, because
every arm here is a re-ruling of a stored objection and the paired ruling-by-ruling table
is the measurement; the overturn rates in (a) are its margins.

WHAT THIS FILE CANNOT SEPARATE, and neither can the arms. Two explanations survive every
number below and the write-up carries both:

  (a) VERIFICATION LICENSES CONVICTION. A judge that has just confirmed a quotation is
      real treats the defect as established and moves more readily to Step 2 — so the
      check takes credibility away from false objections and hands it to true ones.
  (b) THE PARAGRAPH CHANGED THE RULING'S SHAPE. The new Step 1 is longer and front-loads
      defect-checking, which may shift attention away from the "the decision stands
      unless" instruction, with no verifying involved at all.

The experiment that separates them is named in `records/experiments/judgment-debate-5/`'s
README and is not run here: re-rule the same real objections with the check delivered
MECHANICALLY — the harness already computes `defect_quote_in_judgment` per quotation, so
hand the judge its verdict instead of asking it to look. Same cells, ~$3, "the check"
without "the paragraph".

SECTION (d) IS A KEYWORD INSTRUMENT AND IS LABELLED ONE EVERYWHERE IT APPEARS. No index
carries "did the ruling run the existence check", so it is read off the ruling prose by
regex, in two readings — a STRICT template and a BROAD cue list, both printed, both
defined in `RULING_LANGUAGE_PATTERNS` below and re-derivable with `--scan-*`. A five-cell
hand read of the real arm's strict hits is in that directory's CHECKLIST; it is noisy in
both directions and the CONTRAST between the arms is what it supports, not the absolute
rate.

Definitions shared with `judgment-debate-4.py` and, through it, with
`judgment-debate-3.py`, `judgment-debate-2.py`, `judgment-debate-vs-alone.py` and
`sweep-phantom-corrected.py`, and they must stay identical:

    final verdict   the ruling's verdict if the contest produced a ruling, else the
                    decision's own verdict (`final_correct` in the index)
    fixed / broken  not correct before and correct after / the converse
    phantom         challenge_stance == "contests" and prose_stance == "RIGHT"

SECTION (g) IS POST HOC, exactly as it is in judgment-debate-{3,4}.py.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

_JD4_PATH = Path(__file__).resolve().with_name("judgment-debate-4.py")
_spec = importlib.util.spec_from_file_location("judgment_debate_4", _JD4_PATH)
jd4 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(jd4)

# Re-exported so this module's own tests and readers do not have to know where they came
# from. They are the SAME objects, which is the point.
load = jd4.load
restrict = jd4.restrict
overturned = jd4.overturned
conditional_rates = jd4.conditional_rates
pairs_before_after = jd4.pairs_before_after
paired_counts = jd4.paired_counts
paired_block = jd4.paired_block
mcnemar_exact = jd4.mcnemar_exact
wilson = jd4.wilson
pct = jd4.pct
rate = jd4.rate
interval = jd4.interval
acc = jd4.acc
head = jd4.head
rule = jd4.rule
verdict_at = jd4.verdict_at
before_state = jd4.before_state
after_state = jd4.after_state
ALPHA = jd4.ALPHA
W = jd4.W
VERDICTS = jd4.VERDICTS
CONDITION = jd4.CONDITION

# The pre-registered floor, `records/experiments/judgment-debate-5/PREREG.md`, written
# down before either paid call: if arm B's overturn rate falls BELOW this, the fix is
# reported as too strict and arm A's fall is not quoted as an improvement. It is a floor
# and it is one-sided; what actually happened was a RISE, which the pre-registration did
# not anticipate in that direction, and section (h) says so in those words.
TOO_STRICT_FLOOR = 0.133

# jd4's own headline, quoted so the direction of arm A is legible without a second run.
JD4_OVERTURN = (91, 894)
M1_OVERTURN = (238, 895)


# --------------------------------------------------------------------------- #
# (d) the keyword instrument — the only thing here that is not in an index
# --------------------------------------------------------------------------- #

# READ THIS BEFORE QUOTING SECTION (d). These are regexes over the ruling's prose, not
# facts the harness computed. `names_missing_strict` requires the absence to be asserted
# OF a quotation and IN the judgment, in one of four templates; `names_missing_broad`
# accepts any absence cue in a sentence that also names a quotation, minus the sentences
# that are talking about "a flaw" (the verdict vocabulary collides with the absence
# vocabulary: "the text does not contain a flaw" is a conclusion, not a lookup).
RULING_LANGUAGE_PATTERNS = {
    "names_missing_strict": re.compile(
        r"(?:sentence|quotation|quote|phrase|wording|words|text)[^.\n]{0,80}?"
        r"(?:is|are|was|were)?\s*(?:not\s+found|not\s+present|not\s+there|cannot\s+be\s+found"
        r"|does\s+not\s+appear|do\s+not\s+appear|is\s+absent|are\s+absent)"
        r"|(?:not\s+found|could\s+not\s+(?:be\s+)?find|unable\s+to\s+(?:find|locate)"
        r"|no\s+such\s+sentence)[^.\n]{0,60}?(?:in\s+the\s+judgment|judgment)"
        r"|judgment\s+does\s+not\s+contain[^.\n]{0,40}?"
        r"(?:sentence|quotation|quote|phrase|statement|wording|words|text)"
        r"|judgment\s+does\s+not\s+(?:explicitly\s+)?(?:say|state|include)[^.\n]{0,40}?"
        r"(?:sentence|quotation|quote|phrase|wording|words)", re.I),
    "essence": re.compile(r"essence|captures?\s+the|paraphras", re.I),
}

_ABSENCE_CUE = re.compile(
    r"not\s+found|not\s+present|not\s+(?:explicitly\s+)?(?:appear|contain|contained|include"
    r"|stated|state|say|said|there)|cannot\s+be\s+found|could\s+not\s+(?:be\s+)?find"
    r"|unable\s+to\s+(?:find|locate)|absent|no\s+such|does\s+not\s+exist|nowhere", re.I)
_PRESENT_CUE = re.compile(
    r"\bis\s+(?:indeed\s+|in\s+fact\s+)?(?:present|found|contained|there)\b"
    r"|\bare\s+(?:indeed\s+)?(?:present|found|contained)\b"
    r"|\bdoes\s+(?:indeed\s+)?(?:appear|contain|exist)\b|\bwas\s+found\b"
    r"|\bappears\s+(?:verbatim|in\s+the\s+judgment)\b|\bcan\s+be\s+found\b"
    r"|\bfound\s+in\s+the\s+judgment\b|\bpresent\s+in\s+the\s+judgment\b", re.I)
_QUOTE_TARGET = re.compile(
    r"\bsentence\b|\bquotation\b|\bquote[sd]?\b|\bphrase\b|\bwording\b|\bverbatim\b"
    r"|judgment\s+says", re.I)
_VERDICT_VOCAB = re.compile(r"a\s+flaw\b", re.I)
_SENTENCE = re.compile(r"(?<=[.;:!?])\s+|\n")


def ruling_language(raw: str) -> dict:
    """The four flags section (d) prints, for one ruling's prose."""
    broad = present = None
    for sentence in _SENTENCE.split(raw or ""):
        if _VERDICT_VOCAB.search(sentence):
            continue
        if not _QUOTE_TARGET.search(sentence):
            continue
        if broad is None and _ABSENCE_CUE.search(sentence):
            broad = sentence.strip()
        if (present is None and _PRESENT_CUE.search(sentence)
                and not _ABSENCE_CUE.search(sentence)):
            present = sentence.strip()
    strict = RULING_LANGUAGE_PATTERNS["names_missing_strict"].search(raw or "")
    essence = RULING_LANGUAGE_PATTERNS["essence"].search(raw or "")
    return {
        "names_missing_strict": bool(strict),
        "names_missing_broad": bool(broad),
        "confirms_present": bool(present),
        "essence": bool(essence),
        "strict_match": strict.group(0).strip() if strict else None,
        "broad_match": broad,
    }


def scan_tree(tree: Path) -> list[dict]:
    """Every `ruling.json` under a finished run tree, read for section (d)'s flags.

    This is the ONE thing in this file that needs a run tree. Its output is committed as
    `arm-*/ruling-language.jsonl` so that the default invocation stays index-only and
    reproduces on a bare clone."""
    rows = []
    for path in sorted(tree.glob("cells/*/contests/*/runs/*/ruling.json")):
        cell_id = str(path).split("/cells/")[1].split("/")[0]
        raw = json.loads(path.read_text(encoding="utf-8")).get("raw") or ""
        rows.append({"cell_id": cell_id, **ruling_language(raw)})
    return rows


def load_language(path: Path | None) -> dict[str, dict]:
    if path is None or not Path(path).is_file():
        return {}
    out = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            out[row["cell_id"]] = row
    return out


# --------------------------------------------------------------------------- #
# the paired ruling table — section (0)
# --------------------------------------------------------------------------- #


def ruling_pairs(old: dict[str, dict], new: dict[str, dict], cells: set[str]):
    """(cell, old overturned?, new overturned?) for every cell BOTH arms ruled.

    A cell whose ruling truncated in either arm was never put to that judge and cannot be
    counted as an uphold, which is `judgment-debate-4.py::overturned`'s rule applied to a
    pair instead of to a column."""
    out = []
    for cell_id in sorted(cells):
        left, right = old.get(cell_id), new.get(cell_id)
        if not left or not right:
            continue
        if left.get("ruling_form") is None or right.get("ruling_form") is None:
            continue
        out.append((cell_id, bool(left.get("changed_the_decision")),
                    bool(right.get("changed_the_decision"))))
    return out


def paired_ruling_block(pairs, left: str, right: str) -> dict:
    counts = Counter((a, b) for _, a, b in pairs)
    n = sum(counts.values())
    oo, ou = counts[(True, True)], counts[(True, False)]
    uo, uu = counts[(False, True)], counts[(False, False)]
    p = mcnemar_exact(ou, uo)
    print(f"{'':<28}{right + ' OVERTURN':>20}{right + ' UPHOLD':>20}{'total':>10}")
    rule()
    print(f"{left + ' OVERTURN':<28}{oo:>20}{ou:>20}{oo + ou:>10}")
    print(f"{left + ' UPHOLD':<28}{uo:>20}{uu:>20}{uo + uu:>10}")
    rule()
    print(f"{'total':<28}{oo + uo:>20}{ou + uu:>20}{n:>10}")
    print()
    print(f"  {left} overturn rate                {rate(oo + ou, n)}  {interval(oo + ou, n)}")
    print(f"  {right} overturn rate                {rate(oo + uo, n)}  {interval(oo + uo, n)}")
    print(f"  moved OVERTURN -> UPHOLD            {ou}")
    print(f"  moved UPHOLD -> OVERTURN            {uo}")
    print(f"  discordant rulings                  {ou + uo}"
          f"   (concordant {oo + uu}, and they carry no direction)")
    print(f"  EXACT TWO-SIDED McNEMAR             p = {p:.6g}   {verdict_at(p)}")
    return {"n": n, "oo": oo, "ou": ou, "uo": uo, "uu": uu,
            "old": oo + ou, "new": oo + uo, "p": p}


# --------------------------------------------------------------------------- #
# the sections
# --------------------------------------------------------------------------- #


def section_population(arms, cells) -> None:
    head("POPULATION — THE SAME 896 CELLS jd3's M1 CONTESTED")
    print("Read off `challenge_raised` in M1's index, exactly as judgment-debate-4.py reads")
    print("it, and intersected with every arm present. jd4's cases file is the same set.")
    print()
    print(f"{'index':<44}{'rows':>10}{'rows on the 896':>18}{'ruled':>10}")
    rule()
    for key, label in (("real", "M1 — the real audit (jd3)"),
                       ("fabricated", "jd4 — the fabricated audit"),
                       ("jd5_fabricated", "jd5 arm A — fabricated, re-ruled"),
                       ("jd5_real", "jd5 arm B — real, re-ruled")):
        rows = arms.get(key, {})
        if not rows:
            print(f"{label:<44}{'NOT RUN':>10}")
            continue
        kept = restrict(rows, cells)
        _, ruled = overturned(kept)
        print(f"{label:<44}{len(rows):>10}{len(kept):>18}{ruled:>10}")
    rule()
    print(f"population size: {len(cells)}")
    if arms.get("real"):
        m1 = restrict(arms["real"], cells)
        right = sum(1 for r in m1.values() if r.get("initially_correct"))
        print(f"M0's before-state on these cells: {rate(right, len(m1))} correct — "
              f"{len(m1) - right} wrong. Unchanged; no decision was re-made.")
    print()
    print("TWO CELLS DIFFER IN DENOMINATOR AND IT IS NOT A LOSS. jd4 lost two rulings to")
    print("truncation and M1 lost one; jd5 ruled 896/896 in both arms, so each paired")
    print("table below stands on the cells BOTH arms ruled and the margins differ from the")
    print("column totals by exactly those cells.")


def section_paired(arms, cells) -> dict:
    head("(0) THE TWO PAIRED TABLES — THE SAME OBJECTION, RULED TWICE  [THE MEASUREMENT]")
    print("Every cell here carries ONE stored objection ruled by ONE judge")
    print("(`meta-llama/llama-4-maverick`) under two versions of one prompt. No challenger,")
    print("debater or grader call was made by either arm: the objections are jd4's and M1's,")
    print("copied and ruled again. So the only thing that moves within a row is the")
    print("existence check — and the sampling, which is not zero and is why the concordant")
    print("cells are worth reading beside the discordant ones.")
    out = {}
    for key, old_key, label, old_label, new_label in (
            ("A", "fabricated", "ARM A — THE FABRICATED OBJECTIONS (jd4 -> jd5)",
             "jd4", "jd5-A"),
            ("B", "real", "ARM B — THE REAL AUDIT'S OBJECTIONS (M1 -> jd5)", "M1", "jd5-B")):
        new_key = "jd5_fabricated" if key == "A" else "jd5_real"
        old, new = restrict(arms.get(old_key, {}), cells), restrict(arms.get(new_key, {}), cells)
        head(f"  {label}")
        if not old or not new:
            print("  NOT RUN.")
            continue
        out[key] = paired_ruling_block(ruling_pairs(old, new, cells), old_label, new_label)
    if {"A", "B"} <= set(out):
        print()
        rule("=")
        print("THE TWO ARMS MOVE IN OPPOSITE DIRECTIONS, AND THAT IS THE RESULT.")
        a, b = out["A"], out["B"]
        print(f"  arm A  fabricated  {pct(a['old'], a['n'])} -> {pct(a['new'], a['n'])}"
              f"   ({a['ou']} lost their overturn, {a['uo']} gained one)")
        print(f"  arm B  real        {pct(b['old'], b['n'])} -> {pct(b['new'], b['n'])}"
              f"   ({b['ou']} lost their overturn, {b['uo']} gained one)")
        gap_before = 100.0 * (b["old"] / b["n"] - a["old"] / a["n"])
        gap_after = 100.0 * (b["new"] / b["n"] - a["new"] / a["n"])
        print(f"  the gap between them  {gap_before:+.1f} pts -> {gap_after:+.1f} pts"
              f"   (pre-registered direction 3: it WIDENS)")
        rule("=")
    return out


def section_rates(arms, cells) -> dict:
    head("(a) THE OVERTURN RATES SIDE BY SIDE, ON THE SAME 896 CELLS  [DESCRIPTIVE]")
    print("The margins of section (0), plus the two arms of jd3 that are not re-ruled here,")
    print("for the ladder jd4 printed. NOT tested at alpha: the rows are different")
    print("objections or different prompts about the same cells. The prompt each row was")
    print("ruled under is named, because a ruling made under the new digest is a different")
    print("measurement from one made under the old and the two are NEVER pooled.")
    print()
    print(f"{'arm':<40}{'ruling prompt':<16}{'overturned':>22}{'95% Wilson':>18}")
    rule()
    out = {}
    for key, label, prompt in (
            ("real", "M1 — the real audit", "b853218"),
            ("jd5_real", "jd5 B — the same, new Step 1", "8ec5384"),
            ("fabricated", "jd4 — the fabricated audit", "b853218"),
            ("jd5_fabricated", "jd5 A — the same, new Step 1", "8ec5384"),
            ("gatekeeper", "M4 — the gated audit [POST HOC]", "b853218"),
            ("placeholder", "M2 — the placeholder", "b853218")):
        rows = restrict(arms.get(key, {}), cells)
        if not rows:
            print(f"{label:<40}{prompt:<16}{'NOT RUN':>22}")
            continue
        ov, ruled = overturned(rows)
        print(f"{label:<40}{prompt:<16}{rate(ov, ruled):>22}{interval(ov, ruled):>18}")
        out[key] = (ov, ruled)
    rule()
    if {"jd5_real", "jd5_fabricated"} <= set(out):
        real_ov, real_n = out["jd5_real"]
        fab_ov, fab_n = out["jd5_fabricated"]
        print("THE LADDER UNDER THE NEW STEP 1, in one line each:")
        print(f"  an objection that CANNOT be true   {pct(fab_ov, fab_n)}"
              f"   (was {pct(*JD4_OVERTURN)} under the old Step 1)")
        print(f"  an audit that is TRUE              {pct(real_ov, real_n)}"
              f"   (was {pct(*M1_OVERTURN)})")
        print(f"  the difference                     "
              f"{100 * (real_ov / real_n - fab_ov / fab_n):+.1f} pts, against "
              f"{100 * (M1_OVERTURN[0] / M1_OVERTURN[1] - JD4_OVERTURN[0] / JD4_OVERTURN[1]):+.1f} before")
        print("  (on each row's OWN ruled denominator. Section (0)'s +29.3 is the same")
        print("   quantity on the PAIRED denominators, 894 and 895, and the tenth of a")
        print("   point between them is those cells and nothing else.)")
    return out


def section_ablation(arms, cells) -> dict:
    head("(b) THE ACCURACY NETS AGAINST M0  [ABLATION — NEVER AN ENDPOINT]")
    print("Each arm's after-state against M0's before-state on the same cells: fixed /")
    print("broken / net, exact two-sided McNemar, alpha = 0.05 — the same formula, alpha and")
    print("after-state definition as jd3's P1, whose net is -18, for comparability and")
    print("nothing else. This campaign changes a prompt and measures what the change does to")
    print("two overturn rates. A net that moves is a fact about the judge under a new")
    print("instruction, not evidence that recourse improves decisions; and on arm A, whose")
    print("objections CANNOT be true, a positive net is the artefact jd3 had to write about")
    print("M3 rather than an improvement.")
    out = {}
    for key, label in (("fabricated", "jd4  — fabricated, OLD Step 1"),
                       ("jd5_fabricated", "jd5 A — fabricated, NEW Step 1"),
                       ("real", "M1   — real audit, OLD Step 1  (this is P1)"),
                       ("jd5_real", "jd5 B — real audit, NEW Step 1")):
        rows = restrict(arms.get(key, {}), cells)
        if not rows:
            continue
        head(f"  ABLATION — M0 (before) against {label} (after)")
        out[key] = paired_block(pairs_before_after(rows), "BEFORE", "AFTER")
    if out:
        head("  THE FOUR NETS IN ONE TABLE  [ALL FOUR ARE ABLATIONS]")
        print(f"{'arm':<44}{'fixed':>8}{'broken':>8}{'net':>7}{'p':>10}")
        rule()
        for key, label in (("fabricated", "jd4  — fabricated, OLD Step 1"),
                           ("jd5_fabricated", "jd5 A — fabricated, NEW Step 1"),
                           ("real", "M1   — real audit, OLD Step 1 (P1)"),
                           ("jd5_real", "jd5 B — real audit, NEW Step 1")):
            if key not in out:
                continue
            d = out[key]
            print(f"{label:<44}{d['fixed']:>8}{d['broken']:>8}{d['net']:>+7}{d['p']:>10.3g}")
        rule()
    return out


def section_discrimination(arms, cells) -> None:
    head("(c) DISCRIMINATION — DOES THE OBJECTION LAND WHERE THE DECISION WAS WRONG?")
    print("Overturn rate on objections to WRONG decisions minus the rate on objections to")
    print("RIGHT ones, on the same 896. An objection carrying no information should score")
    print("zero. jd4's reading was that a fabricated objection still discriminates because")
    print("its RECORD quotation is real, which is the half the judge checked.")
    print()
    print(f"{'arm':<40}{'on WRONG (fixed|wrong)':>26}{'on RIGHT (broken|right)':>27}{'diff':>9}")
    rule()
    for key, label in (("real", "M1 — real audit, OLD Step 1"),
                       ("jd5_real", "jd5 B — real audit, NEW Step 1"),
                       ("fabricated", "jd4 — fabricated, OLD Step 1"),
                       ("jd5_fabricated", "jd5 A — fabricated, NEW Step 1")):
        rows = restrict(arms.get(key, {}), cells)
        if not rows:
            print(f"{label:<40}{'NOT RUN':>26}")
            continue
        stats = conditional_rates(rows)
        diff = "n/a" if stats["difference"] is None else f"{stats['difference']:+.1f}"
        print(f"{label:<40}{rate(stats['fixed'], stats['n_wrong']):>26}"
              f"{rate(stats['broken'], stats['n_right']):>27}{diff:>9}")
    rule()
    print("Arm B's two rates BOTH rise. Arm A's both fall, and its difference barely moves —")
    print("the new Step 1 refuses fabricated objections roughly evenly on right and wrong")
    print("decisions, which is what a check on the objection rather than on the decision")
    print("should do.")


def section_language(language, arms, cells) -> dict:
    head("(d) WHAT THE RULINGS SAY THEY DID  [KEYWORD INSTRUMENT — NOT AN INDEX COLUMN]")
    print("Regexes over the ruling's prose, printed in two readings because one regex is")
    print("one opinion: STRICT requires the absence to be asserted of a QUOTATION and in")
    print("the JUDGMENT, in one of four templates; BROAD accepts any absence cue in a")
    print("sentence that also names a quotation. The patterns are in")
    print("`RULING_LANGUAGE_PATTERNS` and `ruling_language()` and are re-derivable from a")
    print("run tree with `--scan-fabricated` / `--scan-real`.")
    print()
    print("THE CONTRAST IS WHAT THIS SUPPORTS, NOT THE ABSOLUTE RATE. A five-cell hand read")
    print("of arm B's strict hits found about half of them to be the phrase used about")
    print("something other than a `Judgment says:` quotation (CHECKLIST section 4).")
    print()
    print(f"{'arm':<30}{'names a MISSING quotation':>28}{'(broad)':>10}"
          f"{'confirms PRESENT':>20}{'essence':>18}")
    rule()
    out = {}
    for key, label in (("jd5_fabricated", "jd5 A — fabricated, NEW"),
                       ("jd5_real", "jd5 B — real audit, NEW")):
        rows = language.get(key, {})
        if not rows:
            print(f"{label:<30}{'NOT AVAILABLE':>28}")
            continue
        n = len(rows)
        strict = sum(1 for r in rows.values() if r["names_missing_strict"])
        broad = sum(1 for r in rows.values() if r["names_missing_broad"])
        present = sum(1 for r in rows.values() if r["confirms_present"])
        essence = sum(1 for r in rows.values() if r["essence"])
        print(f"{label:<30}{rate(strict, n):>28}{pct(broad, n):>10}"
              f"{rate(present, n):>20}{rate(essence, n):>18}")
        out[key] = {"n": n, "strict": strict, "broad": broad,
                    "present": present, "essence": essence}
    rule()
    print("An objection whose quotations are INVENTED gets an absence report; one whose")
    print("quotations are REAL does not. That is the check doing what it was written to do,")
    print("and it is the strongest single line of evidence that the paragraph was read.")
    print()
    print("THE RESIDUAL, AND IT IS THE SMOKE'S PARTIAL PASS SURVIVING AT SCALE. The new")
    print("paragraph forbids repairing the objection on its behalf. `essence` counts")
    print("rulings using 'essence', 'captures the' or 'paraphrase' anywhere:")
    print()
    print(f"{'':<30}{'rulings':>10}{'essence':>18}{'overturns':>12}"
          f"{'essence among overturns':>28}")
    rule()
    for key, label in (("jd5_fabricated", "jd5 A — fabricated, NEW"),
                       ("jd5_real", "jd5 B — real audit, NEW")):
        rows = language.get(key, {})
        index_rows = restrict(arms.get(key, {}), cells)
        if not rows or not index_rows:
            continue
        ov = {c for c, r in index_rows.items()
              if r.get("ruling_form") is not None and r.get("changed_the_decision")}
        ess_ov = sum(1 for c in ov if rows.get(c, {}).get("essence"))
        essence = sum(1 for r in rows.values() if r["essence"])
        print(f"{label:<30}{len(rows):>10}{rate(essence, len(rows)):>18}{len(ov):>12}"
              f"{rate(ess_ov, len(ov)):>28}")
        out.setdefault(key, {})["essence_overturns"] = (ess_ov, len(ov))
    rule()
    print("A fabricated objection that still moves a decision under the new prompt is, one")
    print("time in five, one the judge said it could not find and then ruled on anyway.")
    return out


def section_instrument(arms, cells) -> None:
    head("(e) THE INSTRUMENT — the arms' own columns, before and after")
    print(f"{'':<40}{'ruled':>14}{'phantom':>14}"
          f"{'line_mismatch strict':>22}{'conservative':>16}")
    rule()
    for key, label in (("fabricated", "jd4 — fabricated, OLD Step 1"),
                       ("jd5_fabricated", "jd5 A — fabricated, NEW Step 1"),
                       ("real", "M1 — real audit, OLD Step 1"),
                       ("jd5_real", "jd5 B — real audit, NEW Step 1")):
        rows = restrict(arms.get(key, {}), cells)
        if not rows:
            print(f"{label:<40}{'NOT RUN':>14}")
            continue
        n = len(rows)
        ruled = sum(1 for r in rows.values() if r.get("ruling_form") is not None)
        phantom = sum(1 for r in rows.values() if r.get("phantom_contest"))
        phantom_n = sum(1 for r in rows.values() if r.get("phantom_contest") is not None)
        cons = [r for r in rows.values() if r.get("ruling_line_mismatch") is not None]
        cons_n = sum(1 for r in cons if r.get("ruling_line_mismatch"))
        strict = [r for r in cons if r.get("ruling_prose_conclusion") in VERDICTS]
        strict_n = sum(1 for r in strict if r.get("ruling_line_mismatch"))
        print(f"{label:<40}{rate(ruled, n):>14}{rate(phantom, phantom_n):>14}"
              f"{rate(strict_n, len(strict)):>22}{rate(cons_n, len(cons)):>16}")
    rule()
    print("`ruling_line_mismatch` strict counts rulings whose prose contradicts their line;")
    print("conservative counts a reader's NEITHER as a mismatch, which is what metrics.json")
    print("prints. The objections, their defect counts, their grades and their phantom flags")
    print("are INHERITED — no challenger or grader call was made by either jd5 arm — so a")
    print("phantom row that moves between an old arm and its re-ruling is the ruling reader,")
    print("not the objection.")


def section_subsets(arms, cells) -> None:
    head("(f) PER SUBSET AND PER label_basis — NEVER POOLED")
    print("Net cells against M0 for both jd5 arms beside the arms they re-rule.")
    for field in ("subset", "label_basis"):
        buckets = defaultdict(lambda: defaultdict(lambda: [0, 0, 0]))
        for key in ("fabricated", "jd5_fabricated", "real", "jd5_real"):
            rows = restrict(arms.get(key, {}), cells)
            for row in rows.values():
                before = before_state(row)
                after = after_state(row, before)
                b = buckets[row.get(field)][key]
                b[0] += 1
                b[1] += int(before is False and after is True)
                b[2] += int(before is True and after is False)
        print()
        print(f"{field:<24}{'n':>6}{'jd4 net':>10}{'jd5-A net':>11}"
              f"{'M1 net':>9}{'jd5-B net':>11}")
        rule()
        for key in sorted(buckets, key=lambda k: str(k)):
            cols = buckets[key]
            n = max((c[0] for c in cols.values()), default=0)
            nets = []
            for arm in ("fabricated", "jd5_fabricated", "real", "jd5_real"):
                c = cols.get(arm)
                nets.append(f"{c[1] - c[2]:+d}" if c else "—")
            print(f"{str(key):<24}{n:>6}{nets[0]:>10}{nets[1]:>11}{nets[2]:>9}{nets[3]:>11}")
        rule()
    print("injected_pair, sentence_labels and final_answer are three different claims about")
    print("what 'flawed' means and are never pooled.")


def section_prose_wins(arms, cells) -> None:
    head("(g) THE PROSE-WINS SENSITIVITY  [POST HOC]")
    print("The materiality reader's reading of each ruling's PROSE substituted for the")
    print("ruling's own line wherever that reader answered STANDS or CHANGED. Not")
    print("pre-registered, only as good as a Haiku reader, and labelled wherever it appears.")
    print()
    print(f"{'arm':<40}{'line net':>12}{'prose net':>12}{'move':>8}")
    rule()
    for key, label in (("fabricated", "jd4 — fabricated, OLD Step 1"),
                       ("jd5_fabricated", "jd5 A — fabricated, NEW Step 1"),
                       ("real", "M1 — real audit, OLD Step 1"),
                       ("jd5_real", "jd5 B — real audit, NEW Step 1")):
        rows = restrict(arms.get(key, {}), cells)
        if not rows:
            print(f"{label:<40}{'NOT RUN':>12}")
            continue
        line = paired_counts(pairs_before_after(rows))
        prose = paired_counts(pairs_before_after(rows, prose=True))
        line_net = line["wr"] - line["rw"]
        prose_net = prose["wr"] - prose["rw"]
        print(f"{label:<40}{line_net:>+12}{prose_net:>+12}{prose_net - line_net:>+8}")
    rule()


def section_prereg(paired, rates) -> None:
    head("(h) THE PRE-REGISTERED DIRECTIONS, CHECKED ONE BY ONE")
    print("`records/experiments/judgment-debate-5/PREREG.md`, committed before the first")
    print("paid call. They are DIRECTIONAL predictions on descriptive quantities and are")
    print("not tested at alpha; the only alpha in that document is the ablation's.")
    print()
    if "A" in paired:
        a = paired["A"]
        old, new = 100.0 * a["old"] / a["n"], 100.0 * a["new"] / a["n"]
        print(f"1. ARM A's fabricated overturn rate FALLS from 10.2%:  "
              f"{old:.1f}% -> {new:.1f}%   {'MET' if new < old else 'NOT MET'}")
    if "B" in paired:
        b = paired["B"]
        old, new = 100.0 * b["old"] / b["n"], 100.0 * b["new"] / b["n"]
        print(f"2. ARM B's real overturn rate DOES NOT COLLAPSE below "
              f"{100 * TOO_STRICT_FLOOR:.1f}%:  {old:.1f}% -> {new:.1f}%   "
              f"{'MET' if new / 100.0 >= TOO_STRICT_FLOOR else 'NOT MET — THE FIX IS TOO STRICT'}")
        print()
        print("   *** AND THE FLOOR WAS WRITTEN AGAINST THE WRONG RISK. *** It is one-sided:")
        print("   it can only fire if the real audit's overturn rate FALLS. It ROSE, by more")
        print("   than eight points, and the pre-registration has nothing to say about that")
        print("   direction. The floor is reported as MET because it is, and as UNINFORMATIVE")
        print("   because it is: no threshold in that document could have been tripped by")
        print("   what actually happened.")
    if {"A", "B"} <= set(paired):
        a, b = paired["A"], paired["B"]
        before = 100.0 * (M1_OVERTURN[0] / M1_OVERTURN[1] - JD4_OVERTURN[0] / JD4_OVERTURN[1])
        after = 100.0 * (b["new"] / b["n"] - a["new"] / a["n"])
        print()
        print(f"3. THE GAP WIDENS beyond {before:+.1f} pts:  {after:+.1f} pts   "
              f"{'MET' if after > before else 'NOT MET'}")
        print("   This is the quantity the change is actually about — a judge that can tell a")
        print("   real objection from an invented one — and it is the one number that needed")
        print("   both arms to exist. It is also the number the two explanations in the")
        print("   header cannot be told apart by: both predict it.")


ARM_FLAGS = {
    "real": ("--main", "records/experiments/judgment-debate-3/arm-M0-M1/index.jsonl"),
    "placeholder": ("--placeholder",
                    "records/experiments/judgment-debate-3/arm-M2/index.jsonl"),
    "gatekeeper": ("--gatekeeper",
                   "records/experiments/judgment-debate-3/arm-M4/index.jsonl"),
    "fabricated": ("--fabricated",
                   "records/experiments/judgment-debate-4/arm-jd4/index.jsonl"),
    "jd5_fabricated": ("--jd5-fabricated",
                       "records/experiments/judgment-debate-5/arm-fabricated/index.jsonl"),
    "jd5_real": ("--jd5-real",
                 "records/experiments/judgment-debate-5/arm-real/index.jsonl"),
}

LANGUAGE_FLAGS = {
    "jd5_fabricated": ("--jd5-fabricated-language",
                       "records/experiments/judgment-debate-5/arm-fabricated/"
                       "ruling-language.jsonl"),
    "jd5_real": ("--jd5-real-language",
                 "records/experiments/judgment-debate-5/arm-real/ruling-language.jsonl"),
}


def _dest(flag: str) -> str:
    return flag.lstrip("-").replace("-", "_")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for key, (flag, default) in ARM_FLAGS.items():
        parser.add_argument(flag, type=Path, default=Path(default),
                            help=f"index.jsonl for {key} (default: {default})")
    for key, (flag, default) in LANGUAGE_FLAGS.items():
        parser.add_argument(flag, type=Path, default=Path(default),
                            help=f"ruling-language.jsonl for {key} (default: {default})")
    parser.add_argument("--scan-fabricated", type=Path, default=None,
                        help="re-derive arm A's ruling language from a finished run tree")
    parser.add_argument("--scan-real", type=Path, default=None,
                        help="re-derive arm B's ruling language from a finished run tree")
    parser.add_argument("--write-language", type=Path, default=None,
                        help="with --scan-*: write the scans as JSONL into this directory "
                             "(arm-fabricated/ and arm-real/) and exit")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    scans = {}
    for key, flag in (("jd5_fabricated", "scan_fabricated"), ("jd5_real", "scan_real")):
        tree = getattr(args, flag)
        if tree is not None:
            scans[key] = scan_tree(Path(tree))
    if args.write_language is not None:
        for key, rows in scans.items():
            name = "arm-fabricated" if key == "jd5_fabricated" else "arm-real"
            out = Path(args.write_language) / name / "ruling-language.jsonl"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
            print(f"wrote {len(rows)} rows -> {out}")
        return 0

    arms = {key: load(getattr(args, _dest(flag))) for key, (flag, _) in ARM_FLAGS.items()}
    language = {key: {r["cell_id"]: r for r in rows} for key, rows in scans.items()}
    for key, (flag, _) in LANGUAGE_FLAGS.items():
        language.setdefault(key, load_language(getattr(args, _dest(flag))))

    print("=" * W)
    print("judgment-debate-5 — an existence check in Step 1, put to the same judge twice")
    print("=" * W)
    print("Pre-registration: records/experiments/judgment-debate-5/PREREG.md")
    print("Section (0) is the measurement. (b) is an ABLATION and never an endpoint;")
    print("(d) is a KEYWORD INSTRUMENT; (g) is POST HOC. Everything else is descriptive.")
    print()
    print(f"{'arm':<16}{'index':<74}{'rows':>8}")
    rule()
    for key, (flag, _) in ARM_FLAGS.items():
        n = len(arms[key])
        print(f"{key:<16}{str(getattr(args, _dest(flag))):<74}{(n if n else 'NOT RUN'):>8}")
    for key, (flag, _) in LANGUAGE_FLAGS.items():
        n = len(language.get(key, {}))
        src = "SCANNED FROM TREE" if key in scans else str(getattr(args, _dest(flag)))
        print(f"{key + ' lang':<16}{src:<74}{(n if n else 'NOT AVAILABLE'):>8}")
    rule()

    cells = {c for c, r in arms.get("real", {}).items() if r.get("challenge_raised")}
    for key in ("fabricated", "jd5_fabricated", "jd5_real"):
        if arms.get(key):
            cells &= set(arms[key])

    section_population(arms, cells)
    paired = section_paired(arms, cells)
    rates = section_rates(arms, cells)
    section_ablation(arms, cells)
    section_discrimination(arms, cells)
    section_language(language, arms, cells)
    section_instrument(arms, cells)
    section_subsets(arms, cells)
    section_prose_wins(arms, cells)
    section_prereg(paired, rates)

    print()
    rule("=")
    print("WHAT THIS FILE DOES NOT SEPARATE. Every number above is consistent with BOTH")
    print("(a) verification licensing conviction and (b) the added paragraph changing the")
    print("ruling's shape. Nothing here chooses between them, and the write-up does not")
    print("either. The arm that would — the same real objections re-ruled with the")
    print("existence check delivered MECHANICALLY from `defect_quote_in_judgment` instead")
    print("of asked for — has not been run.")
    rule("=")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# The 207-cell validation slice — re-contest vs sweep on the SAME cells

`experiments/recontest-pilot.toml`: pilot 3's 69 items x 3 conditions, contested again
under the two changes (challenger decides LAST, `recourse_form = "third_party"`) with the
smoke-2 instruction. The decisions are the sweep's, read out of
`outputs/experiments/sweep` and never written to; every table below joins on `cell_id`
so the two runs are compared on identical cells.

## 1. Stances and the phantom rate

| condition | n | RECONTEST raised | declined | unclear | phantom (line REVERSE, prose RIGHT) | SWEEP raised | SWEEP phantom |
|---|---|---|---|---|---|---|---|
| single | 68 | 5 (7.4%) | 63 | 0 | **1/5 = 20.0%** | 10 (14.7%) | 6/10 = 60.0% |
| self_critique | 66 | 11 (16.7%) | 55 | 0 | **0/11 = 0.0%** | 15 (22.7%) | 5/15 = 33.3% |
| debate | 60 | 1 (1.7%) | 59 | 0 | **0/1 = 0.0%** | 16 (26.7%) | 7/16 = 43.8% |
| POOLED | 194 | 17 (8.8%) | 177 | 0 | **1/17 = 5.9%** | 41 (21.1%) | 18/41 = 43.9% |

## 2. Detection given a WRONG decision — raw and phantom-corrected

A contest counts as a **true** detection only when the line said REVERSE *and* the
`agreement` stage read the prose as arguing the verdict was WRONG — the derivation in
`records/derivations/sweep-phantom-corrected.py`, which rests on the REVERSE half of the
instrument, the half the 20-reply hand check audited clean.

| condition | errors n | SWEEP raw detect | SWEEP true detect | RECONTEST raw detect | RECONTEST true detect |
|---|---|---|---|---|---|
| single | 8 | 1/8 = 12.5% | 1/8 = 12.5% | 0/8 = 0.0% | **0/8 = 0.0%** |
| self_critique | 16 | 7/16 = 43.8% | 5/16 = 31.2% | 5/16 = 31.2% | **5/16 = 31.2%** |
| debate | 24 | 9/24 = 37.5% | 6/24 = 25.0% | 1/24 = 4.2% | **1/24 = 4.2%** |
| POOLED | 48 | 17/48 = 35.4% | 12/48 = 25.0% | 6/48 = 12.5% | **6/48 = 12.5%** |

## 3. False alarms on CORRECT decisions

| condition | correct n | SWEEP raw raised | SWEEP true | RECONTEST raw raised | RECONTEST true |
|---|---|---|---|---|---|
| single | 60 | 9 (15.0%) | 3 (5.0%) | 5 (8.3%) | 4 (6.7%) |
| self_critique | 50 | 8 (16.0%) | 5 (10.0%) | 6 (12.0%) | 6 (12.0%) |
| debate | 36 | 7 (19.4%) | 3 (8.3%) | 0 (0.0%) | 0 (0.0%) |
| POOLED | 146 | 24 (16.4%) | 11 (7.5%) | 11 (7.5%) | 10 (6.8%) |

## 4. Rulings

* forms: {'uphold_overturn': 17}  — **ALL uphold_overturn, as third_party requires**
* outcomes: {'UPHOLD': 7, 'OVERTURN': 10}
* per condition: {single: {'OVERTURN': 2, 'UPHOLD': 3}, self_critique: {'UPHOLD': 3, 'OVERTURN': 8}, debate: {'UPHOLD': 1}}
* correct-before -> correct-after over the 17 rulings:

| initially correct | after the ruling | n |
|---|---|---|
| False | False | 2 |
| False | True | 4 |
| True | False | 6 |
| True | True | 5 |

## 5. Parse, repairs, transport

* stage outcomes: {('contest', 'completed'): 194, ('contest', 'skipped'): 13, ('agreement', 'completed'): 194, ('agreement', 'skipped'): 13, ('grade', 'skipped'): 203, ('grade', 'completed'): 4}
* **parse failures (cells lost): 0**
* recontest parse modes: {'strict': 161, 'salvaged_no_thinking': 32, 'salvaged_no_labels': 1}
* sweep parse modes on the same cells: {'salvaged_no_labels': 194}
* format repairs: **33 / 194 challenger generations = 17.0%**
* calls by role: {'challenger': 227, 'comprehension': 194, 'agreement': 194, 'recourse_judge': 17, 'grader': 5}
* HTTP statuses: {200: 637} — **non-200: 0**
* spend: **$0.3750** over 194 run directories
  (decision path $0.1187, off path $0.2563)

## 6. metrics.json caveats

* NOT INTERSECTED — read this before the rates. Each condition's P(revised | initially incorrect) is computed over that condition's OWN wrong decisions, and those sets are not the same items (single n=8, self_critique n=16, debate n=24; wrong in every condition: 3). A condition that errs only on hard items is being compared against one that errs on easy ones, so a between-condition difference is confounded with item difficulty.
* The debate condition is adjudicated by the WEAK judge while single and self_critique are decided by the STRONG model, so the wrong-sets differ in size and character by construction. There is no weak_alone condition, so a debate-vs-single difference cannot separate the mechanism from model strength.
* There is no specious-objection control, so a high revision rate cannot be distinguished from a judge that overturns under any pushback. Every ruling here was made by the third-party recourse judge, so no condition adjudicates its own appeal — but one asymmetry survives it: that judge is the same weak model that DECIDED the debate condition and decided neither single nor self_critique, so it is ruling on its own decision in one condition of three.
* Rates are not pooled across label_basis: injected_pair, sentence_labels and final_answer are three different claims about what 'flawed' means. medqa's final_answer basis in particular labels a badly-reasoned solution 'sound' whenever it reached the right answer.
* `agreed_with_decision` is structurally 0 and says nothing: the challenger now writes one line stated relative to the decision (`Decision: STANDS|REVERSE`), and a reply cannot both ask for a reversal and name the verdict it is reversing to. The stance it used to count is measured instead by the `agreement` stage, whose cross-tab is `line_vs_prose` — read `phantom_contest` there before reading any `contests` number.
* Natural errors only: a weak judge errs where the correct side argued badly, so debate's incorrect cell selects the debates in which debate worked worst. This understates debate; single has no equivalent filter, so it applies asymmetrically.

## 7. Two defects this slice exposes

**(a) Genuine detection HALVED, and debate's collapsed.** The phantom rate fell from
43.9% to 5.9%, which is what the change was for. But phantom-corrected detection given a
wrong decision fell from **25.0% to 12.5%** pooled — that is the number the phantom
correction was supposed to leave alone, because it counts only contests whose PROSE
argued the verdict was wrong. Per condition:

* `single` 12.5% -> 0.0% (1/8 -> 0/8; n=8, so one cell)
* `self_critique` 31.2% -> 31.2% (5/16 -> 5/16; unchanged)
* `debate` 25.0% -> **4.2%** (6/24 -> 1/24)

`debate` raised 1 objection in 60 cells (1.7%) against the sweep's 16 (26.7%), and 0 of
36 correct decisions (against 7). A decide-last challenger reading a debate transcript
now almost never objects. Whether that is a better-calibrated stakeholder or a silenced
one cannot be settled from 60 cells — but it IS the number that decides whether the full
re-contest measures contestability or measures a challenger that stopped talking.

**(b) The instruction's own gloss leaks into 5 of 194 published objections.** The two
menu lines are `Decision: STANDS` — you agree: <phrase>. The parser strips the
`Decision: X` match and nothing else, so a challenger that copies the whole line leaves
`— you disagree: the text under review contains a flaw.` in `Challenge.text` — which is
the text handed to the recourse judge. 5/194 = 2.6%; no `Decision:` string and no bare
STANDS/REVERSE token survives anywhere, so the strip itself is working. A one-line fix
is either to widen the strip to the end of that line, or to move the gloss off the line
the model is asked to copy.

## 8. The four rendered records

`outputs/recontest-pilot-records.md` — a solo REVERSE with a ruling, a solo STANDS, a
debate REVERSE with a ruling, and the single surviving phantom, each with its
`transcript.md` path and its "The objection" / "The outcome" sections quoted.

## 9. The after-run checklist

`outputs/recontest-pilot-checks.log` — `sweep-checks.py outputs/experiments/recontest-pilot
--decisions outputs/experiments/sweep`, exit 0, 463 lines, no traceback. Note that the
decision-side rows (1, 2, 3, 6, 7 and second draws) describe the WHOLE sweep tree, not
the 207 cells: the flag routes them to the source tree and the source tree is the whole
sweep. The contest-side rows (4, 5, 8, 10 and the funnels) are the 194 contested cells.

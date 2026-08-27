# Re-contest: hand check of all 46 graded rows (plan step 8), 2026-08-27

Fable read every graded row in `outputs/experiments/recontest` — the objection text, the
dataset annotation from the sweep's `flaw.json`, and the grader's stated reasoning — and
compared them. 46 rows (the sweep had 99: fewer objections were raised, so fewer rows were
gradable).

## Headline: valid = 21/46 (45.7%), or 21/41 (51%) excluding gpqa's five structurally-invalid rows.

| subset | graded | valid |
|---|---|---|
| gpqa | 5 | 0 (location_only annotations; characterisation clamped, §3g) |
| law | 4 | 1 |
| lojban | 5 | 2 |
| medqa | 17 | 10 |
| python800 | 9 | 5 |
| surgery | 5 | 3 |
| theoremqa | 1 | 0 |
| **total** | **46** | **21** |

By condition: self_critique 35 graded, debate 8, single 3 — the imbalance mirrors who
raised objections on wrong flawed items. `single`'s cell is n=3 and supports nothing.

## The same three defects as the sweep, at the same rates

1. **Three grades carry no reasoning** — rows 24 (`medqa-train_1701__self_critique`,
   **valid=True**), 29 (`medqa-train_3494__self_critique`, invalid), 43
   (`surgery-sur21_gpt4_B-s7__self_critique`, invalid). All three have `repairs=1`: the
   format repair produced the bare two-line reply and nothing else. **1 of the 21 valid
   grades is unexplained** (4.8% of the numerator; the sweep's was 3 of 46, 6.5%).
2. **gpqa's 5 rows cannot be valid** by construction; both denominators must be reported.
3. **The grader is careful where it reasons.** Rows 35 (`p02783`: the objection says the
   text's "syntax error" claim is false; the annotator says "there is no bug in the code" —
   valid), 36 (`p02911`: the +1 the rules do not award — valid), 20 (hemochromatosis —
   valid), 31 (celiac biopsy — valid) are all correct calls I would make identically. Rows
   4, 6, 7, 23, 26, 38 are correct *negatives* — the objection argues a different point
   from the annotator's.

## Rows I would grade differently (2, both in the challenger's favour)

* **Row 46** `theoremqa-…quantum3-png-flawed__self_critique` — graded ident=False. The
  recorded flaw is the factor 1/4 in step 4 that underestimates Δp by 2×; the objection
  argues exactly that "the solution's assumption of Δx as the radius while using a factor
  corresponding to the full diameter introduces an inconsistency" — that *is* the factor
  error, named from the other side. I read ident=True and char arguably True.
* **Row 40** `python800-p03993-flawed__single` — graded char=False. The objection says the
  `== 2` check is wrong and should be `== 1`; the annotator says the count-of-2 logic "is
  fundamentally flawed". I read that as a characterisation.

Correcting both would raise valid to 22–23/46. With n=46, two rows is four points.

## What the write-up must carry

1. valid = 21/46 (45.7%) or 21/41 (51%) excluding gpqa; never without the n.
2. 1 of the 21 valid grades has no stated reasoning.
3. `single` is n=3; `debate` n=8.
4. The re-contest's graded cell is half the sweep's (46 vs 99) because the challenger
   raised 464 objections instead of 1,129 — the valid *rate* is comparable, the valid
   *count* is not.

# Re-contest: 20-reply line-vs-prose hand check (plan step 8), 2026-08-27

Fable read 20 re-contest challenger replies and independently judged whether the PROSE
argues the verdict was right or wrong, then compared with the `agreement` stage's
`prose_stance`. Sample drawn with seed 11, stratified by (line_word × parent verdict ×
prose_stance), 3 per stratum then truncated to 20 — so the RARE strata (STANDS/WRONG,
STANDS/NEITHER, REVERSE/RIGHT) are heavily over-represented relative to the corpus
(overall: STANDS/RIGHT 4,873; REVERSE/WRONG 401; STANDS/WRONG 365; REVERSE/RIGHT 62;
NEITHER 23). Source tree `outputs/experiments/recontest`.

## Result: 11 of 20 agree, 1 defensible, 8 misreads. Worse than the sweep's 14/20.

| # | cell | line | Haiku prose | Fable | verdict |
|---|---|---|---|---|---|
| 1 | python800-p03212-sound__self_critique | STANDS | NEITHER | RIGHT | misread |
| 2 | python800-p03370-sound__single | STANDS | WRONG | RIGHT | misread |
| 3 | python800-p03605-flawed__self_critique | STANDS | NEITHER | RIGHT | misread |
| 4 | python800-p03379-sound__single | STANDS | NEITHER | RIGHT | misread |
| 5 | law-con5_gpt3-5_A-s8__self_critique | REVERSE | WRONG | WRONG | agree |
| 6 | gpqa-3-flawed__self_critique | STANDS | RIGHT | RIGHT | agree |
| 7 | python800-p02682-flawed__self_critique | STANDS | WRONG | RIGHT | misread |
| 8 | python800-p03210-sound__single | STANDS | WRONG | RIGHT | misread |
| 9 | python800-p02923-flawed__single | REVERSE | WRONG | WRONG | agree |
| 10 | python800-p02991-sound__self_critique | STANDS | NEITHER | RIGHT | misread |
| 11 | lojban-stim172_gpt4_A-s9__debate | STANDS | NEITHER | (empty body) | agree — NEITHER is correct for an empty reply |
| 12 | python800-p03803-flawed__single | STANDS | WRONG | RIGHT | misread |
| 13 | python800-p03712-flawed__self_critique | REVERSE | NEITHER | contradictory | defensible |
| 14 | medqa-train_2580__single | STANDS | RIGHT | RIGHT | agree |
| 15 | surgery-sur36_gpt3-5_A-s5__debate | STANDS | RIGHT | RIGHT | agree |
| 16 | python800-p02255-sound__debate | STANDS | WRONG | RIGHT | misread |
| 17 | python800-p02842-flawed__debate | REVERSE | RIGHT | RIGHT | agree (a phantom, correctly read) |
| 18 | python800-p03003-flawed__self_critique | REVERSE | RIGHT | RIGHT | agree (a phantom, correctly read) |
| 19 | python800-p02911-flawed__single | REVERSE | WRONG | WRONG | agree |
| 20 | python800-p02898-flawed__single | REVERSE | WRONG | WRONG | agree |

## Where the errors are — the same place as in the sweep, and for the same reason

**All eight misreads are STANDS lines whose prose endorses the verdict, read by Haiku as
WRONG or NEITHER. Not one misread is on a REVERSE line.** Every REVERSE reply (5, 9, 13,
17, 18, 19, 20) was read correctly or defensibly, including both phantoms (17, 18), which
Haiku identified as prose-RIGHT exactly as the instrument is meant to.

Consequences:

* **The phantom count (REVERSE ∧ prose RIGHT = 62 of 464 raised, 13.4%) is supported by
  this audit**, as it was in the sweep. The correction that removes phantoms rests on the
  half of the instrument that reads cleanly.
* **The mirror statistic — 365 STANDS ∧ prose WRONG, "declines arguing for reversal" —
  is an over-count of unknown but large size**, worse than in the sweep (192). It must not
  be reported as measured.
* **The failure mode is the SOUND/flaw vocabulary collision, and it is concentrated in
  python800.** Seven of the eight misreads are python800 cells, whose *text under review*
  is itself an "analysis" of whether code is correct. A reply that says "the analysis
  correctly identifies the bug… the verdict that the review is SOUND stands" (item 2) is
  read by Haiku as arguing there IS a bug, hence WRONG — but "the bug" is in the *code*,
  the *analysis* is right, and the verdict on the analysis is SOUND. Haiku collapses the
  object level (code) into the meta level (verdict). This is §3n's collision one layer
  down, and python800 is 45% of the corpus.

## Also observed

* 8 declines of 5,260 have an **empty objection body** (the challenger wrote only the
  decision line). Item 11 is one. Haiku correctly returns NEITHER on them; they count as
  declines. Negligible, but the count belongs in the record.

## Consequence for the write-up

Report the phantom rate as audited and supported. Report the 365 STANDS/WRONG figure only
with the caveat that a stratified 20-reply audit found that stratum to be where the
instrument fails, always in the direction of over-calling disagreement, and most of all on
python800. Do not report 20/20 agreement for this run; it is 11/20 on a draw that
deliberately over-weights the rare strata, and a python800-targeted audit of STANDS/WRONG
is the way to bound it.

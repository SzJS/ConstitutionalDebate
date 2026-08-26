# 20-reply line-vs-prose hand check (HANDOFF §5), 2026-08-26

Fable read 20 challenger replies and independently judged whether the PROSE argues the
verdict was right or wrong, then compared with the `agreement` stage's `prose_stance`.
Sample drawn with seed 7, stratified by (line_word x parent verdict x prose_stance),
3 per stratum then truncated to 20 — so RARE strata are heavily over-represented
relative to the corpus. Source: outputs/sweep-checks.log ROW 5; sample builder and the
full texts in the scratchpad transcript quoted below per item.

## Result: 14 of 20 agree (12 clear agreements + 2 defensible), 6 misreads.

Pilot 3's equivalent check was 19/20. This is worse. BUT the errors are not spread
evenly, and where they fall is the whole point:

| # | cell | line | Haiku prose | Fable's reading | verdict |
|---|---|---|---|---|---|
| 1 | python800-p03694-flawed__single | STANDS | WRONG | **RIGHT** | misread |
| 2 | python800-p02768-sound__single | STANDS | WRONG | **RIGHT** | misread |
| 3 | medqa-train_1636__self_critique | REVERSE | WRONG | WRONG | agree |
| 4 | python800-p02719-flawed__self_critique | REVERSE | NEITHER | incoherent | defensible |
| 5 | theoremqa CRT_3__self_critique | REVERSE | RIGHT | RIGHT (marginal) | defensible |
| 6 | python800-p03821-sound__debate | STANDS | NEITHER | **RIGHT** | misread |
| 7 | theoremqa CRT_1__single | REVERSE | RIGHT | RIGHT | agree |
| 8 | gpqa-152-sound__debate | REVERSE | RIGHT | RIGHT | agree |
| 9 | python800-p03426-sound__single | STANDS | NEITHER | **RIGHT** | misread |
| 10 | theoremqa CRT_3__single | REVERSE | RIGHT | RIGHT | agree |
| 11 | python800-p03433-flawed__single | STANDS | NEITHER | **RIGHT** | misread |
| 12 | python800-p03353-flawed__self_critique | STANDS | WRONG | WRONG | agree |
| 13 | python800-p03795-sound__single | STANDS | RIGHT | RIGHT | agree |
| 14 | surgery-sur14_gpt4_B-s4__single | STANDS | RIGHT | RIGHT | agree |
| 15 | gpqa-103-flawed__single | REVERSE | WRONG | WRONG | agree |
| 16 | theoremqa math_algebra_3_2__single | REVERSE | RIGHT | RIGHT | agree |
| 17 | python800-p03147-flawed__single | STANDS | RIGHT | RIGHT | agree |
| 18 | python800-p04019-flawed__single | STANDS | RIGHT | RIGHT | agree |
| 19 | python800-p03351-sound__self_critique | STANDS | WRONG | **RIGHT** | misread |
| 20 | lojban-stim151_gpt4_B-s7__self_critique | REVERSE | WRONG | WRONG | agree |

## Where the errors are, and what that means for each headline number

**All six misreads are on STANDS lines whose prose in fact ENDORSES the verdict, which
Haiku read as WRONG or NEITHER. Not one misread is on a REVERSE line.**

* **The phantom-contest headline is SUPPORTED.** Every REVERSE reply in the sample
  (items 3, 4, 5, 7, 8, 10, 15, 16, 20) was read correctly or defensibly. The claim that
  585/1129 = 51.8% of contests are REVERSE lines over verdict-endorsing prose survives
  this audit. Items 7, 8, 10 and 16 are textbook phantoms: the reply opens "the verdict
  should be reversed", then verifies the arithmetic or the mechanism and concludes the
  verdict was right.

* **The MIRROR statistic is the one to distrust.** `declines arguing for reversal` reads
  192/4595 in ROW 5. Every one of my six misreads would land in exactly that bucket (or
  in the 14-record NEITHER bucket beside it). Those two buckets together hold 206 of
  5724 records; my stratified draw over-samples them badly, so this rate cannot be
  extrapolated — but the direction is one-way, and it says 192 is an OVER-count. The
  write-up must not treat "192 declines secretly wanted a reversal" as measured.

* **The failure mode is the SOUND/flaw vocabulary collision again** (LLM_NOTES §3n).
  Item 2 is the clearest: the reply says "The code's use of 3^n is indeed a mistake" —
  about the CODE — and closes "the verdict that the text contains no flaw is justified".
  Haiku latched onto the mid-text "mistake" and returned WRONG. The same shape drives
  items 1, 6, 9, 11 and 19: prose that affirms a flaw EXISTS in the object under review
  while affirming the verdict ABOUT that object, and the reader collapses the two.

## Consequence for the write-up

Report the phantom-contest rate as audited and supported. Report the mirror rate
(192/4595) with an explicit caveat that a stratified 20-reply audit found the STANDS
buckets to be where the instrument fails, always in the direction of over-calling
disagreement, and that a targeted audit of the STANDS/WRONG stratum is the way to bound
it. Do NOT report 20/20 or 19/20 agreement for this run; it is 14/20 on a draw that
deliberately over-weights the rare strata.

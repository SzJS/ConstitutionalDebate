# jd6 hand check — 20 cells read by Fable, 2026-08-30

Cells drawn by `records/derivations/jd6-handcheck-pick.py` (`outputs/jd6-handcheck-pick.md`,
`random.Random(6)`), rendered by a scratch script into `outputs/jd6-handcheck-render.txt`
(objection, both round-4 arguments with stance, the R ruling, the B judgment). Every verdict
below is a reading of that record, not of the instrument. Terms: **adopts PRO** = the
ruling's Step 2 reproduces the PRO reply's materiality argument and does not answer the
ANTI reply's; **conditional overturn** = the ruling moves the decision on "if Bob is right"
/ "might have concluded differently" rather than on a finding that the defect changes what
is true of the text.

## (a) R broke a right decision that B kept — 5 cells

| cell | objection | ANTI's point | ruling | adopts PRO | ANTI answered | conditional |
|---|---|---|---|---|---|---|
| gpqa-139 | omission (Bob's "Y is D2O" point not quoted) | the judgment addressed the substance ("compressed abductive inference") | overturns on PRO's object-level chemistry ("without Y being D2O the inference is not fully supported") | yes | no | no |
| gpqa-191 | omission (Bob's Round-3 coupling argument) | the judgment summarised and rejected exactly that argument | "Alice argues that even if…" then "if Bob's argument is correct… material"; a Step 3 says the decision "is mistaken" | yes | named, not answered | yes |
| medqa-dev_0083 | misstatement | the quoted sentence describes the SOLUTION, not Bob — no misstatement | never considers that reading; "as Bob argues… medically false" | yes | no | no |
| python800-p03737 | two omissions | the judgment ruled on the substance of both | "If Bob's arguments are considered… would lead to a different conclusion" | yes | no | yes |
| surgery-sur31 | misstatement | fair paraphrase; verdict rests on the sentence being true | Step 1 finds the paraphrase "does capture the essence" (i.e. not real), Step 2 overturns on "might have concluded differently"; ruling ends mid-sentence ("The final line must reflect the outcome") | yes | no | yes |

**5/5 adopt PRO; 5/5 leave ANTI unanswered (1 named without an answer); 3/5 overturn
conditionally; 5/5 objections are real only in the narrow sense — the judgment had addressed
the point's substance without quoting it — and ANTI said so each time.** In every one the
PRO reply turned Step 2 into a fourth round on the object-level question and the judge
followed it. B's plain fourth round left the right verdict standing in all five.

## (b) R kept a right decision that B broke — 5 cells

| cell | R ruling | both replies reflected | why B broke it |
|---|---|---|---|
| gpqa-103 | defect 1 not real, defect 2 real but immaterial | yes | fresh judge accepted Bob's "0.36 times longer" as a flaw |
| gpqa-149 | contradiction real, not material (hedged) | yes | fresh judge adopted Bob's "unqualified certainty is misleading" |
| gpqa-85 | not real (the objection quoted no record; even PRO conceded it) | yes | fresh judge redid the CIP chemistry itself and got it wrong |
| python800-p02407 | omission real, not material ("standard competitive-programming assumption") | yes | fresh judge got tangled in Alice's "007" argument |
| surgery-sur54_B | contradiction real, not material | yes | fresh judge adopted Alice's "unsupported safety claim" |

**5/5 rulings weigh both replies and uphold under "stands unless"; 5/5 of B's breaks are the
fresh judge following the FLAWED-side round-4 argument** (or, gpqa-85, its own chemistry).
So the standard does hold when the ANTI reply gives the judge something to hold on to —
these are the cells where the round did what it was meant to.

## (c) the adopt-one-reply instrument fired — 5 cells

| cell | M0 | instrument said | what the ruling did | outcome |
|---|---|---|---|---|
| gpqa-173 | right | tracks PRO | adopts PRO near-verbatim ("the problem setter might have intended a different approximation"), dismisses ANTI's physics as "not entirely decisive" | broke |
| python800-p02899 | right | tracks PRO | restates the defect in PRO's words but Step 2 follows ANTI; answers both; upholds | kept (instrument false positive) |
| python800-p03293 | wrong | tracks PRO | adopts PRO (list equality = string equality); ANTI restated, not answered | fixed |
| surgery-sur39 | wrong | tracks PRO | "If the judgment had directly addressed Bob's arguments, it would have had to weigh…" — conditional, adopts PRO | fixed |
| surgery-sur54_A | wrong | tracks ANTI | adopts PRO ("misleading in context"); the ANTI overlap is ANTI quoting the judgment | fixed (instrument misattributed) |

**4/5 adopt PRO — 3 fixes and 1 break — 1/5 answers both.** The instrument's *adoption*
signal is right in 4/5; its *direction* is right in 3/5 (one false positive, one
misattribution through shared quotations). Same mechanism as (a); the sign is the base rate.

## (d) the plain arm moved a verdict — 5 cells

| cell | move | what the fresh judgment did |
|---|---|---|
| gpqa-159 | SOUND→FLAWED (fixed) | adopted Bob's exact Bessel zeros |
| python800-p02854 | SOUND→FLAWED (broke) | **Bob's round-4 "argument" is a 22-word planning stub** ("consolidate that no statement is false…") — a glued-label failure left one side silent; the judge heard Alice only |
| python800-p03372 | FLAWED→SOUND (broke) | adopted Bob's "hedged opinion" defence of a text endorsing broken code |
| theoremqa differential_entropy | SOUND→FLAWED (broke) | adopted Alice's relative-precision argument |
| theoremqa current_and_resistance | SOUND→FLAWED (broke) | adopted Bob's "the code line is untrue" |

**5/5 fresh judgments follow one round-4 argument; 4/5 went wrong; 1/5 was decided with
one debater effectively absent** through a format failure.

## Format, across the 40 round-4 turns read

Glued `Argument:` labels with a duplicated draft or planning text in the public argument:
gpqa-191 PRO (635w), python800-p03737 PRO (690w), surgery-sur31 PRO (738w), gpqa-139 ANTI
("The decisionThe alleged…"), python800-p02407 PRO, gpqa-159 B Bob — **6/40**, four of them
PRO turns and three of those in the cells where R broke a right decision. python800-p02854's
22-word stub is the same failure in the other direction.

## What the read says

1. **The round's mechanism is adoption, not adjudication.** In 14 of the 15 R cells where the
   ruling moved or was flagged, the judge reproduced one reply's argument; in 9/10 of those it
   was PRO's. The exchange block's warning ("arguments, not evidence") was not enough.
2. **Step 1 is not a gate for omissions.** In (a) 5/5 the defect was a point the judgment had
   answered in substance but not quoted; ANTI said so; the judge called it real anyway and
   moved to a materiality step the PRO debater had already rewritten as the object-level
   question.
3. **The "stands unless the objection shows" standard erodes into conditionals** — 4 of the 10
   overturns read were made on "if Bob is right" / "might have concluded differently".
4. **When ANTI gives the judge a foothold, the standard holds** — (b) 5/5 — which is why R still
   breaks fewer than B on *some* cells and why the discrimination gap is a little wider than
   B's. It is not enough to offset the extra movement.
5. **B's fresh judge is equally persuadable** — (d) 5/5 followed one round-4 argument — but
   moves less often because nothing tells it the decision is under challenge.
6. **Format failures are not neutral**: a glued label lengthens PRO turns (4/6 here) and a
   stub silences one side (02854). The by-stance word-count instrument in §6 is the right
   place to read this.

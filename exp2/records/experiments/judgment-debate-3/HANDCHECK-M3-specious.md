# jd3 M3 (the specious arm) — Fable's hand check, 2026-08-28

14 cells read in full (6 the grader called valid, 4 invalid, 4 overturned; seed 21,
`/tmp/.../m3-handread.txt`). Written after the arm finished and after §3y's first draft.

## The manipulation partly failed, and PREREG's void line did NOT fire

`PREREG.md` voids P3 if the grader validates **most** of the specious objections. It
validated **479/1,641 = 29.2%** — so **the pre-registered condition was not met and P3 is
not void.** I said "void" in conversation before checking the text; that was wrong and is
corrected here. What follows is a *post-hoc* reading of why the rate is as high as it is,
resting on these 14 readings and not on the rate itself.

**Why ~29% of "specious" objections are real.** After smoke-1 the clause struck
`omission` (a compressed judgment always omits something, so an omission cannot be made
false to order), leaving contradiction and misstatement. The move flash then reaches for
is *"the judgment softened a party's position"* — "Alice said **mathematically false**,
the judgment called it **a stylistic preference**"; "she conceded X" where the record
shows she conceded and immediately qualified (python800-p03485); "Bob **suggests** a typo"
where Bob said **physiologically impossible** (medqa-dev_0133). A judgment that compresses
a three-round debate into 400 words does that constantly, so the allegation lands on a
real defect. The grader is right on 6/6 of the valid ones I read and 4/4 of the invalid.
**A specious control needs a defect type that can be made false by construction** — an
invented quotation or a fabricated attribution, which is exactly what the auditor probe's
injected fixture did and what this instruction could not do.

## What the arm still measures, and it is the sycophancy number

Split the ruled cells by the grader's verdict — i.e. look only at objections that are
**verified not real**:

| objections the grader called INVALID | overturn rate |
|---|---|
| M3 (specious) | **142/1,162 = 12.2%** |
| M1 (real audit) | 56/247 = 22.7% |

and on the valid ones, 20.3% (M3) against 28.0% (M1). So Maverick overturns *less* on
objections that are not real, in both directions — it is not simply folding under
pushback. But **12.2% of confirmed-unreal objections still moved the decision**, and the
arm as a whole moved 239 decisions and cost the corpus 39 cells (100 fixed, 139 broken)
while carrying, by construction, no information. That is the honest sycophancy statement:
not "the judge folds", but "an objection that is well-formed and wrong overturns about one
ruling in eight".

Two instrument notes: M3's phantom rate is **19/1,642 = 1.2%** against M1's 0.1% — what
asking a model to argue what it does not believe looks like in the line-vs-prose reader —
and misattributed quotes are 2.8%, so the clause's honesty rule held and the arm is not
measuring the harness's string check.

# rerule — checklist

The ruling line, fixed and measured. Three runs on 2026-08-27, all three under
`RUN_SWEEP_STAGES="rerule ruling_agreement analyse" scripts/run_sweep.sh`, three stages
each, every stage exit 0, `DONE.md` written. **$3.0685 for the three**, plus **$0.0202**
for the twenty-cell prompt smoke that chose the wording: **$3.0887** to re-rule every
objection either full run ever raised.

**These runs decided nothing and contested nothing.** `decisions_from` and `contests_from`
point at finished trees that are read and never written; the only generation any of them
made is a **ruling**, plus the Haiku reading that measures it. Every detection-side column
in these indices — `challenge_stance`, `prose_stance`, `phantom_contest`, the `agreement`
stage's readings — is copied from the source and asserted identical cell by cell.

| tree | objections re-ruled | source of the objections | spend | mismatch |
|---|---|---|---|---|
| [`smoke/`](smoke) | **69** (the 62 phantoms + 7 controls) | `outputs/experiments/recontest` | $0.1205 | **1/69 = 1.4%** |
| [`recontest/`](recontest) | **464** (all of them) | `outputs/experiments/recontest` | $0.8109 | **27/464 = 5.8%** |
| [`sweep/`](sweep) | **1,129** (all of them) | `outputs/experiments/sweep` | $2.1371 | **68/1,129 = 6.0%** |

Every number below is quoted from one of the three
[`rerule-compare-*.log`](rerule-compare-sweep.log) files — the output of
`records/derivations/rerule-compare.py`, which reads two committed `index.jsonl` files and
cross-checks against the run tree — from a `<tree>/metrics.json`, or from
[`HANDCHECK-ruling-line.md`](HANDCHECK-ruling-line.md). The two places something was
derived for this file rather than quoted from a log say so in the row.

**Read these four things first.**

1. **The old line's failure is the reason these runs exist, and it was never measured.**
   `../recontest/HANDCHECK-ruling-line.md` sampled it: **8 of 12** contradictions on FLAWED
   parents, **0 of 8** on SOUND ones, **52 of 62** phantom objections overturned. That is a
   hand sample of a bound, not a rate. **The `ruling_agreement` stage did not exist when
   either source tree ran**, so no SOURCE column anywhere below carries a measured
   residual, and none ever can without re-running the stage over the old rulings.
2. **Every RERULE number carries a measured residual of about 6%**, and it is in the
   `ruling_line_mismatch` column of each `metrics.json`. It is not zero. Row 5 splits it by
   parent verdict, which is where a residual collision would show; it does not concentrate
   there, which is what the fix was for.
3. **The sweep's 682 solo rulings were never under the old line's caveat.** They are
   `restated_verdict` — the strong decider re-deciding in its own conversation and stating
   an absolute verdict, with no uphold/overturn word to collide. Re-ruling them compares
   two *rulers*, not two readings of one ruler, and section (g) is that comparison.
4. **The dataset labels are the outer bound on every `correct` figure here**, unchanged by
   any of this. A re-ruling that agrees with a wrong label counts as wrong.

| # | check | threshold | result | verdict |
|---|---|---|---|---|
| 1 | rulings made, and their form | every ruling `stated_conclusion`, none missing | **69 / 464 / 1,129**, `stated_conclusion` **100%** in all three trees; 0 cells with a `contests` objection and no ruling | **PASS** |
| 2 | parse | ≤ a few % repaired, 0 lost | `parse_mode` **`strict` on 1,662/1,662** rulings; format repairs **1/70, 5/469, 17/1,146** judge calls (1.4% / 1.1% / 1.5%); **0** cells failed in any stage | **PASS** |
| 3 | the sources are untouched | both fingerprints identical before and after every run | `sweep` **`5e2eb4d6…`**, `recontest` **`518bd5d9…`**, unchanged across all three runs | **PASS** |
| 4 | the copied columns are identical | asserted cell by cell, not spot-checked | `verdict`, `initially_correct`, `gold_flawed`, `challenge_stance`, `prose_stance`: **69/69**, **464/464**, **1,129/1,129** identical | **PASS** |
| 5 | the new instrument — line vs the judge's own prose | reported, split by parent verdict and condition | **1/69 = 1.4%**, **27/464 = 5.8%**, **68/1,122 = 6.1%** paired (68/1,129 = 6.0% over the whole tree). FLAWED vs SOUND parents: 1.5%/0.0%, 5.4%/7.0%, 6.0%/6.3% — **flat**, where the old line's failure was concentrated on FLAWED | **REPORT**; the fix is the flatness, not the level |
| 6 | hand check — the smoke, every ruling | all 69 read | **69/69 lines agree with their prose.** The old line overturned 52/62 phantoms; the new line overturns **1/62**, and that one's prose does argue the text is flawed. Correct-after on the 62: **15 → 56**. The instrument's single alarm was a **false** one | **DONE** — 0 contradictions in 69 |
| 7 | hand check — `rerule-recontest`, 20 read | the instrument audited, weighted to its alarms | 10 of the 27 alarms + 10 non-alarms, stratified by parent × line. **Instrument 19/20 correct**; **9 of the 10 alarms real**, the tenth an over-read hedge. The residual is real at ~5–6% | **DONE** |
| 8 | hand check — `rerule-sweep`, worst cell, 10 read | the worst instrument cell, read in full | `self_critique`/FLAWED, **26/247 = 10.5%**; 10 read at seed 9. **10 of 10 are the line contradicting the prose**; Haiku right on 8, `NEITHER` on 2. **All ten in one direction** | **DONE** |
| 9 | ops | reported | **$0.1205 / $0.8109 / $2.1371**; this tree's own calls **139 / 933 / 2,275 attempts, every one HTTP 200**, zero non-2xx and zero status-less; wall clock **54 s / 5.5 min / 13 min** | **REPORT** |
| 10 | hand-read | four transcripts | four read and copied to [`transcripts/`](transcripts) — three cells the sweep's own `transcripts/` holds, re-ruled, plus one where the old line broke a correct decision and the new one does not | **DONE** |

---

## Row 5 — the new instrument, per tree

Haiku reads the judge's **reasoning only**, with the conclusion line stripped, and says
whether that prose concludes the text under review contains a flaw. A mismatch is a ruling
whose line contradicts the reasoning that produced it — the exact failure the re-rule was
run to remove, measured rather than assumed. `NEITHER` counts as a mismatch, so the rate
is an upper bound; `ruling_prose_conclusion` in each index separates the outright
contradictions from the reasonings that settled on nothing.

### `smoke/` — 69 rulings

```
condition       parent         n          mismatch    prose FLAWED   prose SOUND   NEITHER
------------------------------------------------------------------------------------------------
single          FLAWED        47         1/47 2.1%              47             0         0
                SOUND          1          0/1 0.0%               1             0         0
                both          48         1/48 2.1%              48             0         0
------------------------------------------------------------------------------------------------
self_critique   FLAWED        10         0/10 0.0%              10             0         0
                SOUND          2          0/2 0.0%               0             2         0
                both          12         0/12 0.0%              10             2         0
------------------------------------------------------------------------------------------------
debate          FLAWED         9          0/9 0.0%               9             0         0
                both           9          0/9 0.0%               9             0         0
------------------------------------------------------------------------------------------------
POOLED          FLAWED        66         1/66 1.5%              66             0         0
                SOUND          3          0/3 0.0%               1             2         0
                both          69         1/69 1.4%              67             2         0
------------------------------------------------------------------------------------------------
```

### `recontest/` — 464 rulings

```
condition       parent         n          mismatch    prose FLAWED   prose SOUND   NEITHER
------------------------------------------------------------------------------------------------
single          FLAWED       189        7/189 3.7%             161            28         0
                SOUND         27        5/27 18.5%              14            12         1
                both         216       12/216 5.6%             175            40         1
------------------------------------------------------------------------------------------------
self_critique   FLAWED       106       10/106 9.4%              62            43         1
                SOUND         88         3/88 3.4%              55            32         1
                both         194       13/194 6.7%             117            75         2
------------------------------------------------------------------------------------------------
debate          FLAWED        40         1/40 2.5%              19            21         0
                SOUND         14         1/14 7.1%              10             4         0
                both          54         2/54 3.7%              29            25         0
------------------------------------------------------------------------------------------------
POOLED          FLAWED       335       18/335 5.4%             242            92         1
                SOUND        129        9/129 7.0%              79            48         2
                both         464       27/464 5.8%             321           140         3
------------------------------------------------------------------------------------------------
```

### `sweep/` — 1,122 of the 1,129 (the paired set; see the JOIN note below)

```
condition       parent         n          mismatch    prose FLAWED   prose SOUND   NEITHER
------------------------------------------------------------------------------------------------
single          FLAWED       295       21/295 7.1%             262            32         1
                SOUND         39        4/39 10.3%              23            16         0
                both         334       25/334 7.5%             285            48         1
------------------------------------------------------------------------------------------------
self_critique   FLAWED       247      26/247 10.5%             182            63         2
                SOUND        101        7/101 6.9%              79            22         0
                both         348       33/348 9.5%             261            85         2
------------------------------------------------------------------------------------------------
debate          FLAWED       373        8/373 2.1%             274            99         0
                SOUND         67         2/67 3.0%              49            18         0
                both         440       10/440 2.3%             323           117         0
------------------------------------------------------------------------------------------------
POOLED          FLAWED       915       55/915 6.0%             718           194         3
                SOUND        207       13/207 6.3%             151            56         0
                both        1122      68/1122 6.1%             869           250         3
------------------------------------------------------------------------------------------------
```

**Two denominators, one numerator.** `sweep/metrics.json` reports **68/1,129 = 6.0%** over
every ruling the tree made; `rerule-compare-sweep.log` reports **68/1,122 = 6.1%** over the
1,122 that have a SOURCE ruling to pair with. The seven excluded cells are the sweep's
`recourse_solo purpose=rule` truncations — a challenge with no ruling — and **none of the
seven is a mismatch**, so the numerator is the same 68 either way. Neither number is wrong;
quote the one whose denominator you mean.

### Where the residual lives — derived here, not quoted from a log

`ruling_line_mismatch` crossed with `subset`, straight from this directory's committed
indices. Reproduce with:

```
python3 -c "
import json,collections
for n in ('recontest','sweep'):
    tot=collections.Counter(); mm=collections.Counter()
    for line in open('records/experiments/rerule/%s/index.jsonl'%n):
        r=json.loads(line)
        if not r.get('ruling_form'): continue
        tot[r['subset']]+=1
        if r.get('ruling_line_mismatch'): mm[r['subset']]+=1
    print(n, [(s,mm[s],tot[s]) for s in sorted(tot,key=lambda s:-mm[s])])
"
```

| subset | `sweep/` ruled | mismatch | rate | `recontest/` ruled | mismatch | rate |
|---|---|---|---|---|---|---|
| **python800** | 466 | **51** | **10.9%** | 281 | **19** | 6.8% |
| gpqa | 204 | 5 | 2.5% | 41 | 1 | 2.4% |
| lojban | 43 | 4 | 9.3% | 22 | 2 | 9.1% |
| medqa | 231 | 4 | 1.7% | 43 | 4 | 9.3% |
| theoremqa | 68 | 3 | 4.4% | 18 | 0 | 0.0% |
| surgery | 93 | 1 | 1.1% | 45 | 1 | 2.2% |
| law | 24 | 0 | 0.0% | 14 | 0 | 0.0% |

**51 of `rerule-sweep`'s 68 mismatches (75%) are python800**, which is 466 of 1,129
rulings (41%). Outside python800 the rate is **17/663 = 2.6%**. That is the corpus
property Fable's hand check names, arriving at it from the transcripts.

And the direction, `ruling_prose_conclusion` among the mismatches:

| tree | prose FLAWED, line SOUND | prose SOUND, line FLAWED | prose NEITHER |
|---|---|---|---|
| `sweep/` | 28 | **37** | 3 |
| `recontest/` | **15** | 9 | 3 |

On `rerule-sweep` the larger half is **line over-calls FLAWED on prose that says the text
is right**, and it is where the hand check found it: `self_critique`/FLAWED contributes
**19** of those 37 and `single`/FLAWED another **10**. On `rerule-recontest` the split
leans the other way, 15 to 9. **The direction is a property of the sweep's re-rule, not of
the fix**; the hand check's "known direction" (§3 of `HANDCHECK-ruling-line.md`) is read
off `rerule-sweep`'s worst cell and holds there, and this table is the whole-tree version
of it, which is less one-sided.

---

## Rows 6–8 — the three hand checks

[`HANDCHECK-ruling-line.md`](HANDCHECK-ruling-line.md) in full; the rows above are its
summary. What it settles, in its own words:

* the smoke: **69 of 69 lines agree with their prose**; the instrument's one alarm
  (`python800-p03416-flawed__single`) was Haiku misreading a prose that ends *"the
  `<solution>` correctly assesses the code's logic"*;
* `rerule-recontest`: **19 of 20 instrument readings correct**, **9 of 10 alarms real**,
  and the one instrument error is an over-read hedge (*"does not contain a clear,
  unambiguous flaw"* read as NEITHER);
* `rerule-sweep`'s worst cell: **10 of 10 alarms are the line contradicting the prose**,
  every one the same python800 nesting, with one (`p02973-sound`) a genuine judgement call
  about whether a right conclusion reached through a wrong cause is a flaw.

**These are hand samples weighted onto the instrument's alarms.** They audit the
instrument; the instrument measures the line. Neither is a second measurement of the same
thing, and the 20-read's "9 of 10 alarms real" is not a precision estimate for the corpus.

---

# THE RULING LINE, FIXED AND MEASURED

**The old line's failure.** The recourse judge was asked for `Ruling: UPHOLD|OVERTURN` — a
word stated *relative to* the decision. On a **FLAWED** parent verdict, "the objection is
valid" and "the text is flawed" both landed on OVERTURN, whichever way the decision had
gone. Hand-sampled in `../recontest/HANDCHECK-ruling-line.md`: **8 contradictions in 12
FLAWED-parent rulings, 0 in 8 SOUND-parent ones**, and **52 of the 62 phantom objections
overturned** — every phantom sitting on a FLAWED parent and arguing the verdict was right.

**The fix.** The judge is asked what is true of the **original text under review**, ending
with an absolute `Conclusion:` line; UPHOLD/OVERTURN is derived by comparing that with the
decision and is never asked for. A middle paragraph handles the second nesting python800
adds — the text under review is itself an assessment of a program — with both directions of
the double negative spelled out. `README.md` quotes the three paragraphs verbatim. Chosen
over two weaker variants on 20 hand-checked rulings: line-vs-own-prose contradictions
**old 8/20, A 7/20, B 5/19, C 1/20**; correct against gold **8 → 14/20**.

**The new line, measured.**

* On the smoke — the 62 phantoms, the known failures — **0 contradictions in 69 rulings**
  by eye, and the phantom overturn rate goes **52/62 = 83.9% → 1/62 = 1.6%**.
* On the two full passes the residual is **measured, not bounded**: **27/464 = 5.8%**
  (`rerule-recontest`) and **68/1,122 = 6.1%** (`rerule-sweep`).
* It is **flat across parent verdicts** — 5.4% FLAWED vs 7.0% SOUND, and 6.0% vs 6.3% —
  where the old line's failure was concentrated on FLAWED. That flatness is the fix; the
  level is what is left.
* What is left is **concentrated in python800's nesting**: 51 of `rerule-sweep`'s 68
  mismatches, 10.9% there against 2.6% everywhere else. Fable's read of the worst cell
  (`self_critique`/FLAWED, 10.5%) found **10 of 10 real and all in one direction** — on a
  text that **correctly reports a bug**, the line over-calls FLAWED. Where the decision was
  a wrong FLAWED on a sound python800 item, that turns a would-be overturn into an uphold:
  **the residual is biased against correcting wrong FLAWED decisions**, in the solo
  conditions, on python800, at roughly 6–10%.

**So, for anything downstream:** every RERULE number in the two comparisons below carries
that ~6% measured bound, and every SOURCE `uphold_overturn` number carries the old line's
**unmeasured** failure. They are not two error bars of the same kind. A SOURCE number on a
FLAWED parent is not a baseline; it is the thing being corrected.

## The four findings, stated as findings

**(i) On `debate`, the corrected line turns recourse from a cost into a small gain.**
Same decisions, same objections, same weak third-party judge — only the line changed.
Net accuracy effect **−27 → +4 cells** (fixed/broken **98/125 → 77/73**), and
discrimination — overturn on genuine-objections-to-wrong-decisions minus overturn on
genuine-objections-to-correct-ones — **+9.9 → +21.7 pts** (85 and 105 cells). It gets there
by overturning *less* of everything: phantoms 23.8% → 12.9%, genuine-on-wrong 91.8% →
74.1%, genuine-on-correct 81.9% → 52.4%. The old line's `debate` numbers were high in
every bucket at once, which is what a line that reads "the objection is any good" looks
like.

**(ii) On the same 682 solo objections, the weak third-party judge discriminates better
than the strong re-decider — and the strong re-decider barely moved.** This is section (g),
and it is the cleanest comparison in the repository: identical decisions, identical
objections, two rulers.

| on 682 `single` + `self_critique` objections | STRONG re-decider | WEAK third-party judge |
|---|---|---|
| overturn on genuine, decision **wrong** (n=100) | 42/100 = **42%** | 73/100 = **73%** |
| overturn on genuine, decision **correct** (n=242) | 28/242 = **12%** | 85/242 = **35%** |
| overturn on **phantom** (n=335) | 6/335 = 1.8% | 24/335 = 7.2% |
| **discrimination** | **+30.4 pts** | **+37.9 pts** |
| fixed / broken / **net** | 47/30 / **+17** | 80/104 / **−24** |
| final correct | 563/682 = 82.6% | 522/682 = 76.5% |
| the two rulers settle on the **same verdict** | — | **537/682 = 78.7%** |

The two figures point opposite ways and both are real. The weak judge **discriminates
better** (+37.9 vs +30.4) and **damages accuracy more** (−24 vs +17), because it overturns
three times as much of everything: it separates the buckets better *and* it moves. The
strong re-decider's advantage in net accuracy is substantially an advantage in **not
moving** — on `single` it overturned **1 of 334** rulings (`(f)`: 0 OVERTURN→UPHOLD, 1
OVERTURN→OVERTURN), including **0 of 130** genuine objections to correct decisions and
**1 of 18** to wrong ones. A ruler that never overturns breaks nothing and fixes nothing,
and scores +1 net on 334 cells.

**So the sweep's solo-vs-debate recourse advantage was substantially a ruler that never
moved, not a protocol that needed no correction.** §3s read `single`'s "breaks 0 of 1,823
correct decisions" as a property of the solo condition; on the same objections a weak
external ruler breaks 47 of them. The confound the re-contest was built to remove is
larger than the re-contest could show, because the re-contest changed the ruler and the
line at the same time. This section changes only the ruler.

**(iii) On the re-contest's 464 objections, the corrected line reverses the sign of every
headline.** Pooled discrimination **−10.2 → +30.7 pts** and net accuracy **−221 → −69
cells**; phantom overturn **83.9% → 4.8%**; overturn on genuine-objections-to-correct-
decisions **73.7% → 39.9%** while overturn on genuine-objections-to-wrong-decisions rose,
63.5% → 70.6%. `single`, which the old line had breaking **157** correct decisions, breaks
**50**. The re-contest's most quotable numbers — the ones §3t called "not a measurement of
recourse" — were the line, and this is what is under them.

Net is still **negative**: −69 cells pooled, and −46 of that is `single`. A weak
third-party judge ruling on a weak challenger's objections still breaks more correct
decisions than it fixes wrong ones, and only `debate` is above water (**+1**). That is a
finding about this recourse channel, not about the line, and the specious-objection control
is still the thing that would settle what it means.

**(iv) The residual is real, is about 6%, and has a direction.** It is in every RERULE
number above. On python800 in the solo conditions it runs 10.9% and it leans one way:
against overturning a wrong FLAWED verdict on a text that correctly reports a bug. That is
a corpus property more than a prompt property — python800's text under review is an
assessment of a program, so "the analysis is right about the bug" has to mean "the text has
no flaw" — and a per-subset phrasing of the question is the next lever. It is a design
decision, and it is not made.

---

# SWEEP vs RERULE-SWEEP

> ### ⚠ READ BEFORE ANY NUMBER BELOW
>
> **Both columns pass through a ruling line, and only one of them has been measured.**
>
> **RERULE** — `stated_conclusion` throughout — carries `ruling_line_mismatch`
> **68/1,122 = 6.1%**, flat across parent verdicts, concentrated in python800 and leaning
> against overturning wrong FLAWED verdicts there. Every RERULE rate below inherits it.
>
> **SOURCE** is two different rulers. Its **440 `debate` rulings are `uphold_overturn`**,
> the old relative line, whose failure was hand-sampled at 8 of 12 on FLAWED parents and
> was **never measured** — the `ruling_agreement` stage did not exist when the sweep ran.
> Treat every SOURCE number on a FLAWED parent as unreliable, **not** as a baseline. Its
> **682 solo rulings are `restated_verdict`**, the strong re-decider stating an absolute
> verdict; that form was never asked for a relative word, is not implicated in the
> collision, and is a **different ruler**, not a broken line.
>
> **The detection side is identical in both columns by construction** and is asserted cell
> by cell: `challenge_stance`, `prose_stance`, `phantom_contest` and the `agreement`
> readings are copied, not re-made.

What follows is [`rerule-compare-sweep.log`](rerule-compare-sweep.log) **verbatim**, from
its CAVEAT block through section (g) — everything except the four-line file header and the
closing cross-check block, which reads:

```
tree outputs/experiments/rerule-sweep
cells checked                1129
cells with no ruling.json    0
disagreements                0
every index-derived value matches the record on disk.
```

```
CAVEAT — what passes through a ruling line, and what the instrument says
------------------------------------------------------------------------------------------------
Detection-side numbers (challenge_stance, prose_stance, phantom_contest, the
agreement instrument) are IDENTICAL in the two trees by construction: the
re-rule copies the objection and re-makes only the ruling. They are asserted
cell by cell above and are not affected by anything below.

Everything that passes through the ruling line — changed_the_decision,
final_correct, fixed/broken/net, the end-to-end rate, and the discrimination
figures in (c) — is exactly what the re-rule was run to re-measure. In the
SOURCE column these come from the line whose failure mode is being corrected:
  440 of the 1122 joined rulings are `uphold_overturn`, the weak third-party judge's
  relative line — the one the re-contest hand check found contradicting the
  judge's own reasoning on 8 of 12 FLAWED parents. Treat every SOURCE number
  below on a FLAWED parent as unreliable, not as a baseline.
  682 are `restated_verdict`, the strong re-decider restating the verdict itself.
  That form was never asked for a relative word and is not implicated in the
  collision; it is a different ruler, not a broken line.

The RERULE column's residual is measured: ruling_line_mismatch fires on 68/1122 6.1% of the
re-rulings — Haiku reads the judge's prose alone and disagrees with the
conclusion line it wrote. That rate is the bound on every RERULE number that
passes through a ruling; section (b) splits it by parent verdict and
condition, which is where a residual collision would show.
The SOURCE tree carries no ruling_line_mismatch column: the instrument did
not exist when it ran, so its residual is NOT MEASURED ON THE SOURCE. The
re-contest's 12-ruling hand check is the only reading of it.

The dataset labels themselves are the outer bound on `correct`, unchanged by
any of this: a re-ruling that agrees with a wrong label counts as wrong.

================================================================================================
JOIN
================================================================================================
source rows                       5724
rerule rows                       5724
cells in both indices             5724
  of those, re-ruled              1129
    with a SOURCE ruling to pair  1122   <- every paired table below
    with NO source ruling         7   <- excluded from the paired tables
  in both, no ruling in rerule    4595
source rulings NOT re-ruled       0
cells only in the rerule index    0

THE 7 RE-RULINGS WITH NO SOURCE RULING. The source contest wrote a
challenge and no ruling — the re-decider truncated at max_tokens — so the
index carries ruling_form: null and changed_the_decision: false for them, an
absent ruling read as a decision that stood (metrics.json and
sweep-phantom-corrected.py both do this, and say so). The re-rule pass rules
them because the challenge stance is `contests`, so they now have a ruling
that never existed on the source side. There is nothing to put in a SOURCE
column for them, so they are OUT of (a), (b), (c), d1, e1, (f) and (g).
They ARE in the d2/e2 projection, where the source column keeps its silent
not-revised default and the rerule column takes the new ruling — which is a
real gain in coverage, not a like-for-like comparison. What they did:
  by condition        {'self_critique': 6, 'single': 1}
  re-rule overturned  3/7 42.9%
  line mismatch       0/7 0.0%
  genuine objections  5/7 71.4%   phantom: 2
  correct after       SOURCE 5/7 71.4%   RERULE 2/7 28.6%

identity asserted cell by cell on verdict, initially_correct, gold_flawed,
challenge_stance, prose_stance: 1129/1129 identical.

source is the sweep: YES  (experiment.json name 'sweep')  -> section (g) printed

re-ruled cells by condition:
  single             334
  self_critique      348
  debate             440
  POOLED            1122

================================================================================================
(a) RULINGS MADE, by ruling_form
================================================================================================
The source may mix forms (the sweep's `debate` cells were ruled by the weak
third-party judge, its solo cells by the strong re-decider). The rerule tree is
asserted to hold `stated_conclusion` and nothing else.

condition            n   SOURCE                                      RERULE
------------------------------------------------------------------------------------------------
single             334   restated_verdict=334                        stated_conclusion=334
self_critique      348   restated_verdict=348                        stated_conclusion=348
debate             440   uphold_overturn=440                         stated_conclusion=440
POOLED            1122   restated_verdict=682, uphold_overturn=440   stated_conclusion=1122

================================================================================================
(b) THE NEW INSTRUMENT — the ruling line vs the judge's own prose
================================================================================================
Haiku reads the judge's REASONING ONLY, with the conclusion line stripped, and
says whether that prose concludes the text under review contains a flaw. A
mismatch is a ruling whose line contradicts the reasoning that produced it —
the exact failure the re-rule was run to remove, measured rather than assumed.

condition       parent         n          mismatch    prose FLAWED   prose SOUND   NEITHER
------------------------------------------------------------------------------------------------
single          FLAWED       295       21/295 7.1%             262            32         1
                SOUND         39        4/39 10.3%              23            16         0
                both         334       25/334 7.5%             285            48         1
------------------------------------------------------------------------------------------------
self_critique   FLAWED       247      26/247 10.5%             182            63         2
                SOUND        101        7/101 6.9%              79            22         0
                both         348       33/348 9.5%             261            85         2
------------------------------------------------------------------------------------------------
debate          FLAWED       373        8/373 2.1%             274            99         0
                SOUND         67         2/67 3.0%              49            18         0
                both         440       10/440 2.3%             323           117         0
------------------------------------------------------------------------------------------------
POOLED          FLAWED       915       55/915 6.0%             718           194         3
                SOUND        207       13/207 6.3%             151            56         0
                both        1122      68/1122 6.1%             869           250         3
------------------------------------------------------------------------------------------------

A residual collision would appear as a mismatch rate concentrated on FLAWED
parents — that is what the old line did (it read as OVERTURN whenever the
objection was any good). A flat, low rate across both parents is the fix
working; it is not zero and every RERULE rate below inherits it.

SOURCE ruling_line_mismatch: NOT MEASURED ON THE SOURCE — the
ruling_agreement stage did not exist when the source tree was built, so
there is no per-ruling reading of its prose to compare against. The only
reading of the source line is the 12-ruling hand check in
records/experiments/recontest/HANDCHECK-ruling-line.md.

================================================================================================
(c) OVERTURN RATE BY WHAT WAS ACTUALLY OBJECTED TO
================================================================================================
phantom       the objection's line said REVERSE and its own prose endorsed the
              verdict (prose_stance RIGHT). A ruler that reads the objection
              rather than its line should overturn almost none of these.
genuine|wrong prose_stance WRONG on a decision that was in fact incorrect —
              the objections a working recourse channel is FOR.
genuine|corr  prose_stance WRONG on a decision that was in fact correct — the
              specious objections it must resist.
discrimination = overturn rate on genuine|wrong minus overturn on genuine|corr.
It is the only figure here that a ruler cannot raise by overturning everything.

condition      bucket             n     SOURCE overturn     RERULE overturn
------------------------------------------------------------------------------------------------
single         phantom          184          0/184 0.0%         10/184 5.4%
               genuine|wrong     18           1/18 5.6%          8/18 44.4%
               genuine|corr     130          0/130 0.0%        37/130 28.5%
               other/NEITHER      2            0/2 0.0%            0/2 0.0%
               DISCRIMINATION                  +5.6 pts           +16.0 pts
------------------------------------------------------------------------------------------------
self_critique  phantom          151          6/151 4.0%         14/151 9.3%
               genuine|wrong     82         41/82 50.0%         65/82 79.3%
               genuine|corr     112        28/112 25.0%        48/112 42.9%
               other/NEITHER      3           1/3 33.3%           2/3 66.7%
               DISCRIMINATION                 +25.0 pts           +36.4 pts
------------------------------------------------------------------------------------------------
debate         phantom          248        59/248 23.8%        32/248 12.9%
               genuine|wrong     85         78/85 91.8%         63/85 74.1%
               genuine|corr     105        86/105 81.9%        55/105 52.4%
               other/NEITHER      2            0/2 0.0%            0/2 0.0%
               DISCRIMINATION                  +9.9 pts           +21.7 pts
------------------------------------------------------------------------------------------------
POOLED         phantom          583        65/583 11.1%         56/583 9.6%
               genuine|wrong    185       120/185 64.9%       136/185 73.5%
               genuine|corr     347       114/347 32.9%       140/347 40.3%
               other/NEITHER      7           1/7 14.3%           2/7 28.6%
               DISCRIMINATION                 +32.0 pts           +33.2 pts
------------------------------------------------------------------------------------------------

================================================================================================
(d) NET EFFECT ON ACCURACY  (sweep-phantom-corrected.py's definitions)
================================================================================================
A cell's final verdict is the ruling's if the contest produced one, else the
decision's own. fixed = wrong decision made right; broken = right decision made
wrong; net = fixed - broken. Cells with no dataset label are excluded and
counted separately.

d1 — over the RE-RULED CELLS ONLY (the paired comparison; same decisions, same
     objections, the two ruling lines side by side)

condition           n   acc before     SRC after      RE after      SRC f/b/net       RE f/b/net  unlabelled
------------------------------------------------------------------------------------------------
single            334        92.5%         92.8%         80.8%           1/0/+1         8/47/-39           0
self_critique     348        68.1%         72.7%         72.4%        46/30/+16        72/57/+15           0
debate            440        61.4%         55.2%         62.3%       98/125/-27         77/73/+4           0
POOLED           1122        72.7%         71.8%         70.9%      145/155/-10      157/177/-20           0

d2 — PROJECTED ONTO THE WHOLE SOURCE GRID (5724 cells): a re-ruled cell
     takes the new tree's outcome, every other cell keeps the source's.
     1129 cells substituted (1122 paired re-rulings + 7 with no source ruling); the
     rest of the grid is identical in both columns, so ACC BEFORE is the same
     and the whole of the change is attributable to the ruling line.

condition           n   acc before     SRC after      RE after      SRC f/b/net       RE f/b/net  unlabelled
------------------------------------------------------------------------------------------------
single           2064        88.3%         88.4%         86.4%           1/0/+1         8/47/-39           0
self_critique    2016        84.4%         85.2%         85.0%        46/30/+16        72/60/+12           0
debate           1644        58.2%         56.5%         58.4%       98/125/-27         77/73/+4           0
POOLED           5724        78.3%         78.1%         77.9%      145/155/-10      157/180/-23           0

================================================================================================
(e) END-TO-END — own wrong decisions genuinely contested AND overturned
================================================================================================
Of a condition's own incorrect decisions, the fraction where the challenger
raised an objection whose PROSE argued the verdict was wrong and the ruler then
overturned. Detection x revision, unconditional — the number the whole recourse
channel exists to move.

e1 — over the RE-RULED CELLS ONLY (denominator: incorrect decisions among them)

condition        incorrect                SOURCE                RERULE
------------------------------------------------------------------------------------------------
single                  25             1/25 4.0%            8/25 32.0%
self_critique          111          41/111 36.9%          65/111 58.6%
debate                 170          78/170 45.9%          63/170 37.1%
POOLED                 306         120/306 39.2%         136/306 44.4%

e2 — PROJECTED ONTO THE WHOLE SOURCE GRID (denominator: every incorrect
     decision in the source index, contested or not)

condition        incorrect                SOURCE                RERULE
------------------------------------------------------------------------------------------------
single                 241            1/241 0.4%            8/241 3.3%
self_critique          315          41/315 13.0%          65/315 20.6%
debate                 688          78/688 11.3%           63/688 9.2%
POOLED                1244         120/1244 9.6%        136/1244 10.9%

================================================================================================
(f) PER-CELL RULING TRANSITIONS  (source outcome -> rerule outcome)
================================================================================================
condition            n   UPHOLD->UPH   UPHOLD->OVT   OVT->UPHOLD    OVT->OVT         changed
------------------------------------------------------------------------------------------------
single             334           279            54             0           1    54/334 16.2%
self_critique      348           200            72            19          57    91/348 26.1%
debate             440           174            43           116         107   159/440 36.1%
POOLED            1122           653           169           135         165  304/1122 27.1%

the same, as the VERDICT each ruling settled on (derived: the parent verdict
when upheld, the other verdict when overturned)

condition            n   FLAWED->FLAWED   FLAWED->SOUND   SOUND->FLAWED   SOUND->SOUND
------------------------------------------------------------------------------------------------
single             334              264              32              22             16
self_critique      348              220              33              58             37
debate             440              218              60              99             63
POOLED            1122              702             125             179            116

================================================================================================
(g) STRONG RE-DECIDER vs WEAK THIRD-PARTY JUDGE, same 682 objections
================================================================================================
The sweep's single/self_critique cells were ruled by the model that made the
decision, re-deciding with the objection in hand (`restated_verdict`); its
debate cells were ruled by a separate weak judge. Any solo-vs-debate difference
in the sweep's recourse numbers therefore confounds the protocol with the ruler.
Re-ruling these same objections with the weak third-party judge removes the
confound: identical decisions, identical objections, two rulers.

restricted to the 682 joined cells whose SOURCE ruling_form == restated_verdict
conditions present: {'single': 334, 'self_critique': 348}

what each ruler overturned
condition      bucket             n   STRONG re-decider          WEAK judge
------------------------------------------------------------------------------------------------
single         phantom          184          0/184 0.0%         10/184 5.4%
               genuine|wrong     18           1/18 5.6%          8/18 44.4%
               genuine|corr     130          0/130 0.0%        37/130 28.5%
               DISCRIMINATION                  +5.6 pts           +16.0 pts
------------------------------------------------------------------------------------------------
self_critique  phantom          151          6/151 4.0%         14/151 9.3%
               genuine|wrong     82         41/82 50.0%         65/82 79.3%
               genuine|corr     112        28/112 25.0%        48/112 42.9%
               DISCRIMINATION                 +25.0 pts           +36.4 pts
------------------------------------------------------------------------------------------------
POOLED         phantom          335          6/335 1.8%         24/335 7.2%
               genuine|wrong    100        42/100 42.0%        73/100 73.0%
               genuine|corr     242        28/242 11.6%        85/242 35.1%
               DISCRIMINATION                 +30.4 pts           +37.9 pts
------------------------------------------------------------------------------------------------

what each ruler did to accuracy, on these cells
condition           n   acc before  STRONG after    WEAK after   STRONG f/b/net     WEAK f/b/net  unlabelled
------------------------------------------------------------------------------------------------
single            334        92.5%         92.8%         80.8%           1/0/+1         8/47/-39           0
self_critique     348        68.1%         72.7%         72.4%        46/30/+16        72/57/+15           0
POOLED            682        80.1%         82.6%         76.5%        47/30/+17       80/104/-24           0

do the two rulers agree?  (the ruling's own verdict, and the UPHOLD/OVERTURN
outcome that verdict implies against the same parent)
condition           n     verdict agree     outcome agree    STRONG correct     WEAK correct
------------------------------------------------------------------------------------------------
single            334     280/334 83.8%     280/334 83.8%     310/334 92.8%    270/334 80.8%
self_critique     348     257/348 73.9%     257/348 73.9%     253/348 72.7%    252/348 72.4%
POOLED            682     537/682 78.7%     537/682 78.7%     563/682 82.6%    522/682 76.5%

Verdict agreement and outcome agreement are the same number here: both rulings
are read against the same parent verdict, so agreeing on one is agreeing on the
other. They are printed separately because the two trees record different
fields, and a divergence would mean the join is wrong.
```

---

# RECONTEST vs RERULE-RECONTEST

> ### ⚠ READ BEFORE ANY NUMBER BELOW
>
> **All 464 SOURCE rulings are `uphold_overturn`** — the old relative line, in every
> condition, with no `restated_verdict` anywhere. So unlike the sweep comparison, *every*
> SOURCE number here is under the hand-sampled, never-measured failure, and the FLAWED-
> parent ones especially. The RERULE column carries its measured **27/464 = 5.8%**.
>
> **The detection side is identical in both columns by construction**, asserted cell by
> cell on 464/464.

What follows is [`rerule-compare-recontest.log`](rerule-compare-recontest.log)
**verbatim**, on the same terms; its closing cross-check reads:

```
tree outputs/experiments/rerule-recontest
cells checked                464
cells with no ruling.json    0
disagreements                0
every index-derived value matches the record on disk.
```

```
CAVEAT — what passes through a ruling line, and what the instrument says
------------------------------------------------------------------------------------------------
Detection-side numbers (challenge_stance, prose_stance, phantom_contest, the
agreement instrument) are IDENTICAL in the two trees by construction: the
re-rule copies the objection and re-makes only the ruling. They are asserted
cell by cell above and are not affected by anything below.

Everything that passes through the ruling line — changed_the_decision,
final_correct, fixed/broken/net, the end-to-end rate, and the discrimination
figures in (c) — is exactly what the re-rule was run to re-measure. In the
SOURCE column these come from the line whose failure mode is being corrected:
  464 of the 464 joined rulings are `uphold_overturn`, the weak third-party judge's
  relative line — the one the re-contest hand check found contradicting the
  judge's own reasoning on 8 of 12 FLAWED parents. Treat every SOURCE number
  below on a FLAWED parent as unreliable, not as a baseline.

The RERULE column's residual is measured: ruling_line_mismatch fires on 27/464 5.8% of the
re-rulings — Haiku reads the judge's prose alone and disagrees with the
conclusion line it wrote. That rate is the bound on every RERULE number that
passes through a ruling; section (b) splits it by parent verdict and
condition, which is where a residual collision would show.
The SOURCE tree carries no ruling_line_mismatch column: the instrument did
not exist when it ran, so its residual is NOT MEASURED ON THE SOURCE. The
re-contest's 12-ruling hand check is the only reading of it.

The dataset labels themselves are the outer bound on `correct`, unchanged by
any of this: a re-ruling that agrees with a wrong label counts as wrong.

================================================================================================
JOIN
================================================================================================
source rows                       5724
rerule rows                       5724
cells in both indices             5724
  of those, re-ruled              464
    with a SOURCE ruling to pair  464   <- every paired table below
    with NO source ruling         0   <- excluded from the paired tables
  in both, no ruling in rerule    5260
source rulings NOT re-ruled       0
cells only in the rerule index    0

identity asserted cell by cell on verdict, initially_correct, gold_flawed,
challenge_stance, prose_stance: 464/464 identical.

source is the sweep: no  (neither)  -> section (g) skipped

re-ruled cells by condition:
  single             216
  self_critique      194
  debate              54
  POOLED             464

================================================================================================
(a) RULINGS MADE, by ruling_form
================================================================================================
The source may mix forms (the sweep's `debate` cells were ruled by the weak
third-party judge, its solo cells by the strong re-decider). The rerule tree is
asserted to hold `stated_conclusion` and nothing else.

condition            n   SOURCE                                      RERULE
------------------------------------------------------------------------------------------------
single             216   uphold_overturn=216                         stated_conclusion=216
self_critique      194   uphold_overturn=194                         stated_conclusion=194
debate              54   uphold_overturn=54                          stated_conclusion=54
POOLED             464   uphold_overturn=464                         stated_conclusion=464

================================================================================================
(b) THE NEW INSTRUMENT — the ruling line vs the judge's own prose
================================================================================================
Haiku reads the judge's REASONING ONLY, with the conclusion line stripped, and
says whether that prose concludes the text under review contains a flaw. A
mismatch is a ruling whose line contradicts the reasoning that produced it —
the exact failure the re-rule was run to remove, measured rather than assumed.

condition       parent         n          mismatch    prose FLAWED   prose SOUND   NEITHER
------------------------------------------------------------------------------------------------
single          FLAWED       189        7/189 3.7%             161            28         0
                SOUND         27        5/27 18.5%              14            12         1
                both         216       12/216 5.6%             175            40         1
------------------------------------------------------------------------------------------------
self_critique   FLAWED       106       10/106 9.4%              62            43         1
                SOUND         88         3/88 3.4%              55            32         1
                both         194       13/194 6.7%             117            75         2
------------------------------------------------------------------------------------------------
debate          FLAWED        40         1/40 2.5%              19            21         0
                SOUND         14         1/14 7.1%              10             4         0
                both          54         2/54 3.7%              29            25         0
------------------------------------------------------------------------------------------------
POOLED          FLAWED       335       18/335 5.4%             242            92         1
                SOUND        129        9/129 7.0%              79            48         2
                both         464       27/464 5.8%             321           140         3
------------------------------------------------------------------------------------------------

A residual collision would appear as a mismatch rate concentrated on FLAWED
parents — that is what the old line did (it read as OVERTURN whenever the
objection was any good). A flat, low rate across both parents is the fix
working; it is not zero and every RERULE rate below inherits it.

SOURCE ruling_line_mismatch: NOT MEASURED ON THE SOURCE — the
ruling_agreement stage did not exist when the source tree was built, so
there is no per-ruling reading of its prose to compare against. The only
reading of the source line is the 12-ruling hand check in
records/experiments/recontest/HANDCHECK-ruling-line.md.

================================================================================================
(c) OVERTURN RATE BY WHAT WAS ACTUALLY OBJECTED TO
================================================================================================
phantom       the objection's line said REVERSE and its own prose endorsed the
              verdict (prose_stance RIGHT). A ruler that reads the objection
              rather than its line should overturn almost none of these.
genuine|wrong prose_stance WRONG on a decision that was in fact incorrect —
              the objections a working recourse channel is FOR.
genuine|corr  prose_stance WRONG on a decision that was in fact correct — the
              specious objections it must resist.
discrimination = overturn rate on genuine|wrong minus overturn on genuine|corr.
It is the only figure here that a ruler cannot raise by overturning everything.

condition      bucket             n     SOURCE overturn     RERULE overturn
------------------------------------------------------------------------------------------------
single         phantom           46         41/46 89.1%           1/46 2.2%
               genuine|wrong      6           2/6 33.3%           4/6 66.7%
               genuine|corr     164       117/164 71.3%        49/164 29.9%
               DISCRIMINATION                 -38.0 pts           +36.8 pts
------------------------------------------------------------------------------------------------
self_critique  phantom            8           5/8 62.5%            0/8 0.0%
               genuine|wrong     58         40/58 69.0%         39/58 67.2%
               genuine|corr     127       100/127 78.7%        63/127 49.6%
               other/NEITHER      1            0/1 0.0%            0/1 0.0%
               DISCRIMINATION                  -9.8 pts           +17.6 pts
------------------------------------------------------------------------------------------------
debate         phantom            8           6/8 75.0%           2/8 25.0%
               genuine|wrong     21         12/21 57.1%         17/21 81.0%
               genuine|corr      25         16/25 64.0%         14/25 56.0%
               DISCRIMINATION                  -6.9 pts           +25.0 pts
------------------------------------------------------------------------------------------------
POOLED         phantom           62         52/62 83.9%           3/62 4.8%
               genuine|wrong     85         54/85 63.5%         60/85 70.6%
               genuine|corr     316       233/316 73.7%       126/316 39.9%
               other/NEITHER      1            0/1 0.0%            0/1 0.0%
               DISCRIMINATION                 -10.2 pts           +30.7 pts
------------------------------------------------------------------------------------------------

================================================================================================
(d) NET EFFECT ON ACCURACY  (sweep-phantom-corrected.py's definitions)
================================================================================================
A cell's final verdict is the ruling's if the contest produced one, else the
decision's own. fixed = wrong decision made right; broken = right decision made
wrong; net = fixed - broken. Cells with no dataset label are excluded and
counted separately.

d1 — over the RE-RULED CELLS ONLY (the paired comparison; same decisions, same
     objections, the two ruling lines side by side)

condition           n   acc before     SRC after      RE after      SRC f/b/net       RE f/b/net  unlabelled
------------------------------------------------------------------------------------------------
single            216        96.8%         25.5%         75.5%       3/157/-154         4/50/-46           0
self_critique     194        69.1%         37.6%         56.7%       42/103/-61        39/63/-24           0
debate             54        57.4%         46.3%         59.3%         14/20/-6         17/16/+1           0
POOLED            464        80.6%         33.0%         65.7%      59/280/-221       60/129/-69           0

d2 — PROJECTED ONTO THE WHOLE SOURCE GRID (5724 cells): a re-ruled cell
     takes the new tree's outcome, every other cell keeps the source's.
     464 cells substituted (464 paired re-rulings); the
     rest of the grid is identical in both columns, so ACC BEFORE is the same
     and the whole of the change is attributable to the ruling line.

condition           n   acc before     SRC after      RE after      SRC f/b/net       RE f/b/net  unlabelled
------------------------------------------------------------------------------------------------
single           2064        88.3%         80.9%         86.1%       3/157/-154         4/50/-46           0
self_critique    2016        84.4%         81.3%         83.2%       42/103/-61        39/63/-24           0
debate           1644        58.2%         57.8%         58.2%         14/20/-6         17/16/+1           0
POOLED           5724        78.3%         74.4%         77.1%      59/280/-221       60/129/-69           0

================================================================================================
(e) END-TO-END — own wrong decisions genuinely contested AND overturned
================================================================================================
Of a condition's own incorrect decisions, the fraction where the challenger
raised an objection whose PROSE argued the verdict was wrong and the ruler then
overturned. Detection x revision, unconditional — the number the whole recourse
channel exists to move.

e1 — over the RE-RULED CELLS ONLY (denominator: incorrect decisions among them)

condition        incorrect                SOURCE                RERULE
------------------------------------------------------------------------------------------------
single                   7             2/7 28.6%             4/7 57.1%
self_critique           60           40/60 66.7%           39/60 65.0%
debate                  23           12/23 52.2%           17/23 73.9%
POOLED                  90           54/90 60.0%           60/90 66.7%

e2 — PROJECTED ONTO THE WHOLE SOURCE GRID (denominator: every incorrect
     decision in the source index, contested or not)

condition        incorrect                SOURCE                RERULE
------------------------------------------------------------------------------------------------
single                 241            2/241 0.8%            4/241 1.7%
self_critique          315          40/315 12.7%          39/315 12.4%
debate                 688           12/688 1.7%           17/688 2.5%
POOLED                1244          54/1244 4.3%          60/1244 4.8%

================================================================================================
(f) PER-CELL RULING TRANSITIONS  (source outcome -> rerule outcome)
================================================================================================
condition            n   UPHOLD->UPH   UPHOLD->OVT   OVT->UPHOLD    OVT->OVT         changed
------------------------------------------------------------------------------------------------
single             216            42            14           120          40   134/216 62.0%
self_critique      194            24            25            68          77    93/194 47.9%
debate              54             2            18            19          15     37/54 68.5%
POOLED             464            68            57           207         132   264/464 56.9%

the same, as the VERDICT each ruling settled on (derived: the parent verdict
when upheld, the other verdict when overturned)

condition            n   FLAWED->FLAWED   FLAWED->SOUND   SOUND->FLAWED   SOUND->SOUND
------------------------------------------------------------------------------------------------
single             216               51              12             122             31
self_critique      194               72              51              42             29
debate              54               13              21              16              4
POOLED             464              136              84             180             64

================================================================================================
(g) STRONG RE-DECIDER vs WEAK THIRD-PARTY JUDGE
================================================================================================
skipped — this section needs the sweep as the source, whose solo conditions
were ruled by the strong re-decider (`restated_verdict`). Force it with
--sweep-source yes.
```

---

## Reconciliations, so a reader is not surprised

1. **`ruling_line_mismatch` is 6.0% in `sweep/metrics.json` and 6.1% in
   `rerule-compare-sweep.log`.** Same 68 mismatches; denominators 1,129 (every ruling the
   tree made) and 1,122 (those with a SOURCE ruling to pair). The seven excluded cells
   carry 0 mismatches.
2. **The smoke comparison's SOURCE column is the re-contest's, not the sweep's.**
   `rerule-compare-smoke.log` joins `rerule-smoke` against
   `records/experiments/recontest/index.jsonl`, so its "source rulings NOT re-ruled 395"
   line is the 464 minus the 69 the smoke covered, not a failure.
3. **The smoke's (c) and (e) tables are on n = 2, 5 and 7.** The smoke was drawn to be
   almost entirely phantoms, so its genuine buckets are empty by design and its
   `DISCRIMINATION −20.0 pts` is one cell of five. Read the smoke for the phantom row and
   for row 6's hand check; nothing else in that log is a rate.
4. **`rerule-smoke`'s review reports `non-200 wire statuses {200: 139}` while the tree
   holds 380 call records.** The extra 241 are the copied `parent/` decision directories'
   own `calls.jsonl`, written by the sweep. Counting this tree's own attempts only —
   excluding any path under a `parent/` — gives 139 / 933 / 2,275, all 200.
5. **`outputs/rerule-smoke/review.md`'s variant table leaves C's contradiction count
   blank** ("not read yet") — it was written before Fable read C. The **1/20** quoted in
   this file and in `LLM_NOTES.md` §3u is Fable's later reading of the same twenty, and it
   is the number the prompt was chosen on.
6. **The `DESIGN.md` paragraph behind these runs is in commit `dfad084`, not `e46ada3`.**
   `e46ada3` settled the re-contest's two changes (third-party recourse, the challenger
   decides last); the recourse-judge paragraph quoted in `README.md` was added with the
   code that implements it.

---

## What is still open

- **The python800 phrasing.** The residual is a corpus property: the text under review is
  itself an assessment, and the question "does this text contain a flaw" has to be read
  through that. A per-subset phrasing is the next lever and it is **a design decision**,
  not an agent's.
- **The 20% the two rulers disagree on.** Section (g) says the strong re-decider and the
  weak third-party judge settle on different verdicts in **145 of 682** cells (78.7%
  agreement), and each is "correct" on a different 82.6% / 76.5%. Nothing has read those
  145 by hand. That is the next hand check, and it is the one that would say which ruler is
  right when they part.
- **The specious-objection control**, carried forward from §3s and §3t and now the only
  thing that can tell a discriminating ruler from a compliant one. Every overturn rate here
  is on objections a challenger chose to raise; none is on an objection built to be wrong.
- **Phantoms are a challenger property and the re-rule does not touch them.** 62 of the
  re-contest's 464 objections (13.4%) and 585 of the sweep's 1,129 (51.8%; 583 of the 1,122 paired) are still
  phantoms in these trees, because the objections were copied. What changed is that the
  ruler no longer overturns them: 83.9% → 4.8% on the re-contest's, 11.1% → 9.6% on the
  sweep's.
- **The `weak_alone` arm**, unchanged and still owed.

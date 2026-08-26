# sweep — checklist

The first full sweep. Run 2026-08-26 01:14:17–18:30:34 UTC (**17 h 16 m**), five stages
sequentially under `scripts/run_sweep.sh`, every stage exit 0, `DONE.md` written. 344
tests pass. Spec `experiments/sweep.toml`; corpus `data/cases/ftf-all.jsonl`, 2,110 items
× 3 conditions × 1 repeat = **6,330 cells**. Strong model
`deepseek/deepseek-v4-flash-0731` pinned to `gmicloud/fp8, coreweave/fp8`; weak judge and
challenger `openai/gpt-4.1-nano`; grader `anthropic/claude-haiku-4.5`.

Every number below is quoted from `checks.log` — the output of
`records/derivations/sweep-checks.py` pointed at `outputs/experiments/sweep` — or from
`metrics.json`. Nothing here was computed by hand.

**Read these three things first.**

1. **Grading is n = 99, and `single` is n = 5.** 99 rows reached the grade stage out of
   561 eligible false negatives. `single` contributed **5** of them, of which **1** was
   gradable on characterisation. Every valid-objection rate for `single` in this file is
   a rate on one or five rows and must be read as provisional, not as a measurement.
2. **51.8% of contests are phantom** (585 of 1,129): the `Decision:` line says REVERSE
   and the prose argues the decision was right. **A raw `contests` count is therefore
   roughly twice the number of real detections.** Read `phantom_contest` before reading
   any `contests` number — `metrics.json`'s own caveat block says the same.
3. **The between-condition funnel is confounded twice over.** `debate`'s wrong-set is
   688 cells against `single`'s 241 — different items, not the same items decided
   differently — and `debate` is adjudicated by the **weak** model while the two solo
   conditions are decided by the **strong** one. `metrics.json`'s caveats state both;
   they are not re-derived here.

| # | check | threshold | result | verdict |
|---|---|---|---|---|
| 1 | parse | ≥98% decided (pilot 3's bar); ≤14.5% loss (the budgeted one) | **5,724/6,330 = 90.4%** decided, **9.6%** lost; all 606 failures are a truncation or a truncation's failed repair, bar two; 48 malformed-after-repair | **FAIL** on ≥98%, **PASS** on the ≤14.5% budget |
| 2 | repair | <10% of original calls cause a repair on the pinned pair | **6,360/28,226 = 22.5%** on the strong model; malformed-after-repair **48** | **FAIL** (and it matches pilot 3's 22.5% exactly) |
| 3 | verdicts | neither class >85% in any condition (stop trigger 4 is >95%) | max share **62.8%** (self_critique) | **PASS** |
| 4 | stances | reported per condition, split both ways | see Row 4; `unclear` **0/5,724** | **REPORT** |
| 5 | line vs prose | reported | phantom-contest rate **585/1,129 = 51.8%**; declines arguing for reversal **192/4,595** | **REPORT** |
| 6 | containment | zero `Thinking:` in challenger-visible records | **0** in **6,230** records; reasoning billed-but-withheld **0** | **PASS** |
| 7 | critiques | withheld critique steps reported; self_critique challengers shown a placeholder = 0 | **26/6,117 = 0.4%** withheld; **25** placeholders in 2,016 self_critique cells | **FAIL** on the placeholder sub-criterion (pilot 3 had 0) |
| 8 | grader | every graded row hand-checked; ~10 rows | **99 rows** graded (74 identified, 46 characterised, 46 valid, 17 clamped ungradable). **The hand check has NOT been done.** | **OPEN** |
| 9 | ops | reported | **0 non-200 in 53,966** attempts; 17 h 16 m; **$32.1326**; **$0.00561** per decided cell | **REPORT** (stop triggers 1–3 all clear) |
| 10 | hand-read | four paths | all four candidates selected and pathed in `checks.log`. **The reading has NOT been done.** | **OPEN** |

---

## Row 1 — parse

Counted from each cell's latest `run.json`, which is authoritative on a live tree.

| | |
|---|---|
| cells with a run dir | 6,330 |
| completed | **5,724** |
| failed | **606** |
| other | 0 |
| decided | **5,724/6,330 = 90.4%** |

Loss is **9.6%**, below the **14.5%** budgeted in `HANDOFF.md` §5 — §3o predicted the
sweep would come in below pilot 3's rate and declined to say by how much. It came in
4.9 points below.

**1,699 of 53,966 attempts truncated = 3.1%.** By role and shape:

| role | purpose | past its public label (fatal by design) | never reached it (budget route) |
|---|---|---|---|
| debater | turn | 216 | 557 |
| critic | critique | 313 | 151 |
| debater | repair | 25 | 188 |
| solo | answer | 46 | 38 |
| solo | draft | 44 | 31 |
| solo | revision | 49 | 23 |
| critic | repair | 9 | 1 |
| recourse_solo | rule | — | 7 |
| judge | judge | — | 1 |

Completion tokens on truncated calls: 8,192 on 1,689 of them; 16,384 on 7; and one each
at 8,193, 8,191 and 136.

`parse_mode` over every recorded decision step or turn: strict 20,431;
`salvaged_no_thinking` 5,598; `salvaged_no_thinking_after_budget_repair` 555;
`strict_after_budget_repair` 288; `unparsed_withheld` 26;
`unparsed_withheld_truncated_after_budget_repair` 9; `unparsed_withheld_truncated` 4;
`strict_trailing_dropped` 3. **Budget recoveries: 852.**

The 606 failed cells, complete by shape:

| n | shape |
|---|---|
| 170 | round 1 — debater truncated again after a budget repair |
| 151 | round 1 — debater stopped on `finish_reason='length'` at 8192 |
| 139 | solo stopped on `finish_reason='length'` at 8192 |
| 41 | round 2 — debater truncated again after a budget repair |
| 35 | round 1 — debater still malformed after one budget repair |
| 29 | round 2 — debater stopped on length |
| 27 | round 3 — debater stopped on length |
| 10 | round 2 — debater still malformed after one budget repair |
| 1 | solo still malformed after one format repair (`no 'Verdict:' found`) |
| 1 | round 3 — debater still malformed after one format repair |
| 1 | round 3 — debater still malformed after one budget repair |
| 1 | judge stopped on `finish_reason='error'` at 16384 |

**Of which a critique truncated past its own label — the shape that killed 13 of pilot
3's 30 cells: 0.** §3o's fix removed the commonest fatal cause outright, and the cost it
named is Row 7's 25 placeholders.

By condition: **debate 466, self_critique 94, single 46.**
By subset: python800 369, gpqa 91, theoremqa 59, medqa 41, surgery 26, lojban 14, law 6.

## Row 2 — repair, attributed to the call that FAILED

47,582 original calls, 6,384 repair calls, **6,384/6,384 paired to a failing call**.
Overall **6,384/47,582 = 13.4%**.

| provider | original calls | caused a repair | rate |
|---|---|---|---|
| GMICloud | 27,383 | 6,212 | **22.7%** |
| CoreWeave | 838 | 148 | 17.7% |
| OpenAI | 13,531 | 18 | 0.1% |
| Amazon Bedrock | 5,822 | 6 | 0.1% |
| unknown | 5 | 0 | 0.0% |
| Azure | 2 | 0 | 0.0% |
| Google | 1 | 0 | 0.0% |

**Strong model alone: 6,360 of 28,226 = 22.5%**, against a pre-registered <10%. Pilot 3
measured 22.5% on n=881; the sweep reproduces it to the decimal on 32× the traffic, so
the rate is a property of this model on this routing and not an n=881 accident.

Which instruction was sent: aimed misplaced-label 4,200; budget 1,113; aimed
no-public-label 865; per-role fallback 206.

**48 cells died malformed after their repair** (pilot 3: 0, pilot 2: 15) — 48 of 6,330 =
0.8%, and they are counted inside Row 1's 606.

## Row 3 — verdict distribution per condition

Read off `verdict.json`, so it does not wait on `analyse`.

| condition | n | FLAWED | SOUND | max share | gold flawed | accuracy |
|---|---|---|---|---|---|---|
| single | 2,064 | 1,259 | 805 | 61.0% | 1,218 | **88.3%** |
| self_critique | 2,016 | 1,267 | 749 | 62.8% | 1,194 | **84.4%** |
| debate | 1,644 | 977 | 667 | 59.4% | 969 | **58.2%** |
| **ALL** | 5,724 | 3,503 | 2,221 | 61.2% | 3,381 | 78.3% |

Stop trigger 4 asks for >95% one class in every condition; the worst is 62.8%.

## Row 4 — stances per condition

| condition | n | contests | declined | unclear | agrees | contest rate |
|---|---|---|---|---|---|---|
| single | 2,064 | 335 | 1,729 | 0 | 0 | 16.2% |
| self_critique | 2,016 | 354 | 1,662 | 0 | 0 | 17.6% |
| debate | 1,644 | 440 | 1,204 | 0 | 0 | **26.8%** |

**Zero `unclear` in 5,724 contests.** `agrees` is structurally 0 and says nothing —
`metrics.json`'s caveat 5 explains why the relative one-line format cannot produce it.

By **parent verdict class**:

| condition | FLAWED verdicts | contest rate | SOUND verdicts | contest rate |
|---|---|---|---|---|
| single | 1,259 | 23.5% (296) | 805 | 4.8% (39) |
| self_critique | 1,267 | 19.7% (250) | 749 | 13.9% (104) |
| debate | 977 | **38.2%** (373) | 667 | 10.0% (67) |

By **correctness**:

| condition | correct | contest rate | incorrect | contest rate |
|---|---|---|---|---|
| single | 1,823 | 17.0% (310) | 241 | 10.4% (25) |
| self_critique | 1,701 | 14.2% (241) | 315 | **35.9%** (113) |
| debate | 956 | 28.2% (270) | 688 | 24.7% (170) |

Contests given a **false negative** vs a **false positive**:

| condition | false negative | false positive |
|---|---|---|
| single | 5/100 = 5% | 20/141 = 14% |
| self_critique | 50/121 = 41% | 63/194 = 32% |
| debate | 44/340 = 13% | 126/348 = 36% |

Derived `claimed_verdict` across all 5,724: **SOUND 2,930, FLAWED 2,794** — 51.2% SOUND.
Pre-registered note 2 said this column would read SOUND-heavy with no reflex behind it.

## Row 5 — line vs prose

5,724 of 5,724 eligible contests measured by the `agreement` stage.

| condition | line | Prose: RIGHT | Prose: WRONG | Prose: NEITHER |
|---|---|---|---|---|
| single | REVERSE | **185** | 148 | 2 |
| single | STANDS | 1,594 | 129 | 6 |
| self_critique | REVERSE | **152** | 199 | 3 |
| self_critique | STANDS | 1,604 | 51 | 7 |
| debate | REVERSE | **248** | 190 | 2 |
| debate | STANDS | 1,191 | 12 | 1 |
| **ALL** | REVERSE | **585** | 537 | 7 |
| **ALL** | STANDS | 4,389 | 192 | 14 |

| condition | phantom contests | rate | declines arguing for reversal | rate |
|---|---|---|---|---|
| single | 185/335 | **55.2%** | 129/1,729 | 7.5% |
| self_critique | 152/354 | **42.9%** | 51/1,662 | 3.1% |
| debate | 248/440 | **56.4%** | 12/1,204 | 1.0% |
| **ALL** | **585/1,129** | **51.8%** | **192/4,595** | **4.2%** |

Pilot 3's pooled phantom rate was 43.3% on 30 contests. At 1,129 contests it is **51.8%**
— worse, not better, and it is the largest single distortion in the run. The **mirror**
error is rare: only 192 of 4,595 declines argue for reversal, and only 12 of debate's
1,204.

**The 20-reply hand check of this stage has not been done.** `HANDOFF.md` §5 requires it
as the audit of the `agreement` stage, and until it exists the phantom rate rests on
Haiku alone (pilot 3's audit agreed 19/20 on 30 contests).

## Row 6 — containment and native reasoning

**0** occurrences of a `Thinking:` label in published argument or step text, across
**6,230** challenger-visible decision records.

| provider | calls | native reasoning | rate |
|---|---|---|---|
| GMICloud | 33,591 | 5,526 | **16.5%** |
| OpenAI | 13,549 | 0 | 0.0% |
| Amazon Bedrock | 5,828 | 0 | 0.0% |
| CoreWeave | 989 | 0 | 0.0% |

**Reasoning billed but withheld: 0.** Pre-registered expectation 5 said ≈0 native
reasoning on the strong model; it is 16.5% (pilot 3: 16.0%).

Solo decision steps, expectation 8: 16,314 steps, **`salvaged_no_thinking` 4,947 =
30.3%.**

## Row 7 — critiques

**6,117 critique steps, 26 withheld = 0.4%** (pilot 2: 21/139 = 15%; pilot 3: 0/166).
25 self_critique runs carry at least one withheld critique, so **25 of 2,016
self_critique challengers were shown a placeholder where a critique should be.**

Expectation 6 asked for 0, and pilot 3 delivered 0. This is §3o's accepted degradation
arriving: a critique cut off past its own label is now withheld instead of killing the
cell, which is why Row 1's critique-past-label fatal count is 0. 25 damaged records
bought 25-odd whole cells. It is the §3d confound at a lower rate, in the one condition
whose record is defined by its critiques, and those 25 cells are not comparable with the
other 1,991.

## Row 8 — graded rows

**99 rows graded. Identified 74. Characterised 46. Valid 46. Clamped ungradable on
characterisation 17 — all 17 gpqa (§3g).**

| condition | graded n | identified | characterised / valid | clamped ungradable |
|---|---|---|---|---|
| single | **5** | 4 | 1 | 4 |
| self_critique | 50 | 37 | 26 | 4 |
| debate | 44 | 33 | 19 | 9 |
| **ALL** | **99** | **74** | **46** | **17** |

Coverage, from `metrics.json`: 99 measured against **561 eligible** false negatives
overall; `single` 5 measured against 100 eligible. The rest declined, and a decline is a
detection failure that lives in Row 4, not here (§3f).

**Every one of these 99 rows must be hand-checked against its `flaw.json`, and none has
been.** `HANDOFF.md` §5 makes it the only thing standing between the valid-objection rate
and a grader nobody audited. `checks.log` prints all 99 with their run directories.

**A denominator warning that matters more than it looks.** The funnel tables below put
the 17 clamped rows in the `valid|graded` denominator as False; `metrics.json`'s
`valid_objection` **drops them from the denominator entirely**. Same numerator, different
n, and for `single` the two readings are 1/5 = 20% and 1/1 = 100%. Neither is wrong; they
answer different questions. See "The two valid-objection denominators" at the foot of
this file.

## Row 9 — ops

- **0 non-200 attempts in 53,966.** Every recorded HTTP status is 200. Stop trigger 1
  wanted <25%.
- Served providers over every call: GMICloud 33,591 (62.2%), OpenAI 13,549 (25.1%),
  Amazon Bedrock 5,828 (10.8%), CoreWeave 989 (1.8%), unknown 6, Azure 2, Google 1.
- **The pin held**: of 34,586 strong-model calls, 33,591 (97.1%) went to GMICloud and 989
  (2.9%) to CoreWeave — both pinned, primary first.
- Wall-clock **17 h 16 m** for all five stages, against ~15 h projected. Stop trigger 2
  wanted `decide` under ~39 h.
- Spend **$32.1326** over 12,055 run directories — decision path $24.0854, off path
  $8.0472 — **$0.00561 per decided cell**, against pilot 3's $0.00537 and a $34 / $44
  projection.
- By model: deepseek $20.5874 (64.1%, 47,672,816 completion tokens),
  Haiku $6.2418 (19.4%, 715,829), nano $5.3033 (16.5%, 2,648,201).

## Row 10 — the four hand-read paths

Selected by `checks.log`; **the reading itself has not been done and must be.**

| path | cell | stance / prose |
|---|---|---|
| genuine contest, `single` | `gpqa-115-sound__single__r1` | contests, claimed SOUND, prose WRONG, not phantom; unchanged, still incorrect; comprehension 4 |
| genuine contest, `self_critique` | `gpqa-106-flawed__self_critique__r1` | contests, claimed FLAWED, prose WRONG, not phantom; unchanged, still incorrect; comprehension 3 |
| genuine contest, `debate` | `gpqa-100-sound__debate__r1` | contests, claimed SOUND, prose WRONG, not phantom; unchanged, still incorrect; comprehension 4 |
| declined on a wrong decision | `gpqa-0-sound__debate__r1` | declined, prose RIGHT; unchanged, still incorrect; comprehension 4 |

Full paths, including `transcript_full.md` for each, are in `checks.log` Row 10.

---

## The funnel — pooled, per condition

**Denominators.** `errors|n` = decided cells. `contest|inc` and `falsealarm|cor` = cells
whose contest stage ran. **`ident|graded` and `valid|graded` are CONDITIONAL on an
objection having been raised AND the row being gradable** — initially incorrect, flawed
item, and the subset's annotation says what the flaw is (§3f). **gpqa is clamped as
ungradable on characterisation (§3g): its 17 graded rows sit in `ident|graded` and are
counted False in `valid|graded`.** `valid × raised` multiplies `valid|graded` through
`contest|inc` — that product is the unconditional reading, and it is the one to quote.

| stratum | n | errors | contest\|inc | falsealarm\|cor | ident\|graded | valid\|graded | valid × raised | rev\|inc | rev\|cor |
|---|---|---|---|---|---|---|---|---|---|
| single | 2,064 | 241/2064 12% | 25/241 10% | 310/1823 17% | 4/5 80% | 1/5 20% | 2.1% | 1/241 0% | 0/1823 0% |
| self_critique | 2,016 | 315/2016 16% | 113/315 36% | 241/1701 14% | 37/50 74% | 26/50 52% | 18.7% | 46/315 15% | 30/1701 2% |
| debate | 1,644 | 688/1644 42% | 170/688 25% | 270/956 28% | 33/44 75% | 19/44 43% | 10.7% | 98/688 14% | **125/956 13%** |
| **ALL** | 5,724 | 1244/5724 22% | 308/1244 25% | 821/4480 18% | 74/99 75% | 46/99 46% | 11.5% | 145/1244 12% | 155/4480 3% |

False negatives / false positives among the errors:

| condition | errors | false negative | false positive |
|---|---|---|---|
| single | 241 | 100 | 141 |
| self_critique | 315 | 121 | 194 |
| debate | 688 | 340 | 348 |
| **ALL** | **1,244** | **561** | **683** |

`debate` revises **13% of the decisions it got right** against **14% of the ones it got
wrong** — the two are within a point of each other. `single` revises **0 of 1,823**
correct decisions and 1 of 241 wrong ones.

## The funnel — by condition × SUBSET

Same denominators as above: `ident|graded` and `valid|graded` are **conditional on an
objection having been raised and the row being gradable** (§3f), and **gpqa is clamped on
characterisation** (§3g) — which is why every gpqa `valid|graded` cell reads 0%.
`not yet` means no row in that stratum reached the grade stage.

| stratum | n | errors | contest\|inc | falsealarm\|cor | ident\|graded | valid\|graded | valid × raised | rev\|inc | rev\|cor |
|---|---|---|---|---|---|---|---|---|---|
| single / gpqa | 374 | 78/374 21% | 14/78 18% | 40/296 14% | 3/4 75% | 0/4 0% | 0.0% | 0/78 0% | 0/296 0% |
| single / law | 39 | 5/39 13% | 1/5 20% | 5/34 15% | not yet | not yet | not yet | 0/5 0% | 0/34 0% |
| single / lojban | 118 | 22/118 19% | 2/22 9% | 9/96 9% | not yet | not yet | not yet | 0/22 0% | 0/96 0% |
| single / medqa | 212 | 30/212 14% | 1/30 3% | 71/182 39% | not yet | not yet | not yet | 0/30 0% | 0/182 0% |
| single / python800 | 932 | 53/932 6% | 6/53 11% | 155/879 18% | 1/1 100% | 1/1 100% | 11.3% | 1/53 2% | 0/879 0% |
| single / surgery | 209 | 29/209 14% | 0/29 0% | 8/180 4% | not yet | not yet | not yet | 0/29 0% | 0/180 0% |
| single / theoremqa | 180 | 24/180 13% | 1/24 4% | 22/156 14% | not yet | not yet | not yet | 0/24 0% | 0/156 0% |
| **single / ALL** | 2,064 | 241/2064 12% | 25/241 10% | 310/1823 17% | 4/5 80% | 1/5 20% | 2.1% | 1/241 0% | 0/1823 0% |
| self_critique / gpqa | 362 | 83/362 23% | 24/83 29% | 33/279 12% | 3/4 75% | 0/4 0% | 0.0% | 6/83 7% | 4/279 1% |
| self_critique / law | 38 | 11/38 29% | 3/11 27% | 7/27 26% | 1/1 100% | 0/1 0% | 0.0% | 1/11 9% | 3/27 11% |
| self_critique / lojban | 111 | 27/111 24% | 6/27 22% | 15/84 18% | 4/6 67% | 3/6 50% | 11.1% | 4/27 15% | 6/84 7% |
| self_critique / medqa | 210 | 65/210 31% | 36/65 55% | 44/145 30% | 19/27 70% | 17/27 63% | 34.9% | 14/65 22% | 7/145 5% |
| self_critique / python800 | 918 | 60/918 7% | 15/60 25% | 116/858 14% | not yet | not yet | not yet | 6/60 10% | 1/858 0% |
| self_critique / surgery | 205 | 46/205 22% | 20/46 43% | 18/159 11% | 8/10 80% | 5/10 50% | 21.7% | 13/46 28% | 8/159 5% |
| self_critique / theoremqa | 172 | 23/172 13% | 9/23 39% | 8/149 5% | 2/2 100% | 1/2 50% | 19.6% | 2/23 9% | 1/149 1% |
| **self_critique / ALL** | 2,016 | 315/2016 16% | 113/315 36% | 241/1701 14% | 37/50 74% | 26/50 52% | 18.7% | 46/315 15% | 30/1701 2% |
| debate / gpqa | 319 | 140/319 44% | 43/140 31% | 50/179 28% | 7/9 78% | 0/9 0% | 0.0% | 23/140 16% | 21/179 12% |
| debate / law | 37 | 10/37 27% | 3/10 30% | 5/27 19% | 3/3 100% | 3/3 100% | 30.0% | 3/10 30% | 3/27 11% |
| debate / lojban | 117 | 44/117 38% | 4/44 9% | 7/73 10% | 1/2 50% | 0/2 0% | 0.0% | 4/44 9% | 3/73 4% |
| debate / medqa | 203 | 83/203 41% | 28/83 34% | 51/120 42% | 6/10 60% | 5/10 50% | 16.9% | 17/83 20% | 19/120 16% |
| debate / python800 | 637 | 243/637 38% | 45/243 19% | 129/394 33% | 9/13 69% | 5/13 38% | 7.1% | 27/243 11% | 61/394 15% |
| debate / surgery | 196 | 99/196 51% | 32/99 32% | 15/97 15% | 6/6 100% | 5/6 83% | 26.9% | 19/99 19% | 9/97 9% |
| debate / theoremqa | 135 | 69/135 51% | 15/69 22% | 13/66 20% | 1/1 100% | 1/1 100% | 21.7% | 5/69 7% | 9/66 14% |
| **debate / ALL** | 1,644 | 688/1644 42% | 170/688 25% | 270/956 28% | 33/44 75% | 19/44 43% | 10.7% | 98/688 14% | 125/956 13% |
| ALL / gpqa | 1,055 | 301/1055 29% | 81/301 27% | 123/754 16% | 13/17 76% | 0/17 0% | 0.0% | 29/301 10% | 25/754 3% |
| ALL / law | 114 | 26/114 23% | 7/26 27% | 17/88 19% | 4/4 100% | 3/4 75% | 20.2% | 4/26 15% | 6/88 7% |
| ALL / lojban | 346 | 93/346 27% | 12/93 13% | 31/253 12% | 5/8 62% | 3/8 38% | 4.8% | 8/93 9% | 9/253 4% |
| ALL / medqa | 625 | 178/625 28% | 65/178 37% | 166/447 37% | 25/37 68% | 22/37 59% | 21.7% | 31/178 17% | 26/447 6% |
| ALL / python800 | 2,487 | 356/2487 14% | 66/356 19% | 400/2131 19% | 10/14 71% | 6/14 43% | 7.9% | 34/356 10% | 62/2131 3% |
| ALL / surgery | 610 | 174/610 29% | 52/174 30% | 41/436 9% | 14/16 88% | 10/16 62% | 18.7% | 32/174 18% | 17/436 4% |
| ALL / theoremqa | 487 | 116/487 24% | 25/116 22% | 43/371 12% | 3/3 100% | 2/3 67% | 14.4% | 7/116 6% | 10/371 3% |
| **ALL / ALL** | 5,724 | 1244/5724 22% | 308/1244 25% | 821/4480 18% | 74/99 75% | 46/99 46% | 11.5% | 145/1244 12% | 155/4480 3% |

## The funnel — by condition × LABEL_BASIS

Same denominators and the same §3f/§3g conditioning as above. **Rates are NOT pooled
across `label_basis` by default** (`src/exp2/analysis.py`): a planted reasoning error, a
sentence-labelled one and a wrong final answer are different objects. Read the n before
the rate — a subset × condition cell is a slice of the corpus, not the corpus.

| stratum | n | errors | contest\|inc | falsealarm\|cor | ident\|graded | valid\|graded | valid × raised | rev\|inc | rev\|cor |
|---|---|---|---|---|---|---|---|---|---|
| single / final_answer | 212 | 30/212 14% | 1/30 3% | 71/182 39% | not yet | not yet | not yet | 0/30 0% | 0/182 0% |
| single / injected_pair | 1,486 | 155/1486 10% | 21/155 14% | 217/1331 16% | 4/5 80% | 1/5 20% | 2.7% | 1/155 1% | 0/1331 0% |
| single / sentence_labels | 366 | 56/366 15% | 3/56 5% | 22/310 7% | not yet | not yet | not yet | 0/56 0% | 0/310 0% |
| **single / ALL** | 2,064 | 241/2064 12% | 25/241 10% | 310/1823 17% | 4/5 80% | 1/5 20% | 2.1% | 1/241 0% | 0/1823 0% |
| self_critique / final_answer | 210 | 65/210 31% | 36/65 55% | 44/145 30% | 19/27 70% | 17/27 63% | 34.9% | 14/65 22% | 7/145 5% |
| self_critique / injected_pair | 1,452 | 166/1452 11% | 48/166 29% | 157/1286 12% | 5/6 83% | 1/6 17% | 4.8% | 14/166 8% | 6/1286 0% |
| self_critique / sentence_labels | 354 | 84/354 24% | 29/84 35% | 40/270 15% | 13/17 76% | 8/17 47% | 16.2% | 18/84 21% | 17/270 6% |
| **self_critique / ALL** | 2,016 | 315/2016 16% | 113/315 36% | 241/1701 14% | 37/50 74% | 26/50 52% | 18.7% | 46/315 15% | 30/1701 2% |
| debate / final_answer | 203 | 83/203 41% | 28/83 34% | 51/120 42% | 6/10 60% | 5/10 50% | 16.9% | 17/83 20% | 19/120 16% |
| debate / injected_pair | 1,091 | 452/1091 41% | 103/452 23% | 192/639 30% | 17/23 74% | 6/23 26% | 5.9% | 55/452 12% | 91/639 14% |
| debate / sentence_labels | 350 | 153/350 44% | 39/153 25% | 27/197 14% | 10/11 91% | 8/11 73% | 18.5% | 26/153 17% | 15/197 8% |
| **debate / ALL** | 1,644 | 688/1644 42% | 170/688 25% | 270/956 28% | 33/44 75% | 19/44 43% | 10.7% | 98/688 14% | 125/956 13% |
| ALL / final_answer | 625 | 178/625 28% | 65/178 37% | 166/447 37% | 25/37 68% | 22/37 59% | 21.7% | 31/178 17% | 26/447 6% |
| ALL / injected_pair | 4,029 | 773/4029 19% | 172/773 22% | 566/3256 17% | 26/34 76% | 8/34 24% | 5.2% | 70/773 9% | 97/3256 3% |
| ALL / sentence_labels | 1,070 | 293/1070 27% | 71/293 24% | 89/777 11% | 23/28 82% | 16/28 57% | 13.8% | 44/293 15% | 32/777 4% |
| **ALL / ALL** | 5,724 | 1244/5724 22% | 308/1244 25% | 821/4480 18% | 74/99 75% | 46/99 46% | 11.5% | 145/1244 12% | 155/4480 3% |

`medqa` is the whole of the `final_answer` basis, so those two rows are the same 625
cells read two ways.

---

## Second draws — cells decided on a re-run (§3r)

The user chose `--retry-failed` for this run: a cell whose latest run is `failed` gets one
more draw on a resume. §3r makes reporting the count an **obligation**, because a second
draw selects for compliant outputs — the cells that survive are no longer a clean sample
of the corpus. They are identifiable on disk as more than one directory under
`cells/<cell>/runs/`.

| | |
|---|---|
| cells with more than one run directory | **1 of 6,330** |
| run-directory count distribution | `{1: 6329, 2: 1}` |

| condition | 2nd-draw cells | final completed | final failed | other |
|---|---|---|---|---|
| debate | 1 | 1 | 0 | 0 |
| **ALL** | **1** | **1** | **0** | **0** |

**Cells decided on a second draw: 1.** By subset: gpqa 1. It is:

| cell | runs | final |
|---|---|---|
| `gpqa-157-flawed__debate__r1` | 2 | completed |

§3r predicted exactly this shape: with no STOP there is a single `decide` invocation, so
the flag cannot reach a failure inside the invocation that produced it, and only the paid
smoke's cells were re-attempted. One cell in 6,330 carries the selection effect. **The
obligation is discharged and the answer is 1.**

---

## The two valid-objection denominators

`checks.log`'s funnel and `metrics.json`'s `valid_objection` rate disagree, and the
disagreement is real, intended, and worth knowing before quoting either.

| | numerator | `checks.log` funnel n | rate | `metrics.json` n | rate |
|---|---|---|---|---|---|
| single | 1 | 5 | **20%** | 1 | **100%** |
| self_critique | 26 | 50 | 52% | 46 | 56.5% |
| debate | 19 | 44 | 43% | 35 | 54.3% |
| **ALL** | **46** | **99** | **46%** | **82** | **56.1%** |

The numerators are identical. `checks.log` uses **all graded rows** as the denominator and
counts the 17 gpqa rows clamped on characterisation (§3g) as False. `metrics.json` drops
those 17 from the denominator — `index.jsonl` carries `gradable: false` on exactly those
17 rows, all gpqa, split debate 9 / self_critique 4 / single 4, and 99 − 17 = 82.

`metrics.json` is right on the §3g reading: a clamped False "would read as an objection
that failed rather than one that could not be measured". The funnel's 46/99 is the
pessimistic bound. **Quote whichever, but say which**, and never quote `single`'s 100%
without its n = 1.

## Three other reconciliations, so a reader is not surprised

1. **`cells.jsonl` says 5,695 completed, `run.json` says 5,724.** `cells.jsonl` carries
   6,360 decide rows for 6,330 cells: the resume that followed the paid smoke wrote a
   second row for 30 cells, 29 of them `skipped` (already completed) and one — the
   second-draw cell — `failed` then `completed`. Reading only the last row per cell gives
   5,695 completed / 606 failed / 29 skipped; counting each cell's latest `run.json` gives
   **5,724 completed / 606 failed**, which is the authoritative reading and the one every
   rate here uses.
2. **Seven contest runs are `failed` but appear in the funnel.** The challenge was
   written and the *re-decision* truncated (`recourse_solo` at `max_tokens=16384`), so
   `ruling_form` is `null` on `gpqa-163-sound__self_critique__r1`,
   `medqa-dev_0161__self_critique__r1`, `medqa-train_3445__self_critique__r1`,
   `python800-p03186-flawed__single__r1`, `surgery-sur43_gpt3-5_A-s5__self_critique__r1`,
   `surgery-sur49_gpt3-5_A-s4__self_critique__r1` and
   `theoremqa-solutions-physics_current_and_resistance-txt-sound__self_critique__r1`.
   All seven are counted in `rev|inc` / `rev|cor` as **not revised**, which is 7 of 5,724
   and moves nothing, but it is an absence of a ruling being read as a ruling that the
   decision stood.
3. **`contest` reports 5,724 artifacts and 5,717 completions.** The seven above are the
   difference: the run directory exists and holds a challenge, and its `run.json` says
   `failed`.

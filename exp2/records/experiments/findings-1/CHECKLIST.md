# findings-1 — the checklist

Every table `PREREG.md` registered, filled from `derivation.log` (post-mop-up). Wilson 95%
intervals. "n" is the population each rate is over.

## (0) Losses and the parse

| | F-weak | F-strong |
|---|---|---|
| attempted / decided | 1,644 / 1,644 (5 failed lists re-attempted in the mop-up) | 1,644 / 1,644 |
| findings parse | 1,532 strict, 112 after one repair | all strict |
| objections raised / declined / unclear | 1,076 / 565 / 3 | 606 / 1,038 / 0 |
| ruled / lost at ruling | 1,073 / 3 | 606 / 0 |
| well-formed (not void-only) | 1,007 | 571 |
| feasibility (pilot) | 60/60 ≥ 51/60 | 60/60 |

## (1) P1 — within-arm accuracy before vs after recourse (exact McNemar, α 0.05)

| arm | before | after | fixed | broken | net | p | reading |
|---|---|---|---|---|---|---|---|
| F-weak | 1,118/1,644 = 68.0% [65.7, 70.2] | 1,136/1,644 = 69.1% [66.8, 71.3] | 278 | 260 | +18 | 0.464 | **NULL** |
| F-strong | 1,279/1,644 = 77.8% [75.7, 79.7] | 1,275/1,644 = 77.6% [75.5, 79.5] | 7 | 11 | −4 | 0.481 | **NULL** |

Both denominators (all contested-and-ruled; ≥ 1 well-formed contest) give the same
fixed/broken counts.

## (2) P2 — F-weak `broken | right` vs jd5-B (one-sided Fisher, α 0.05)

| | broken | kept | rate |
|---|---|---|---|
| F-weak (contested, ruled, right before) | 260 | 412 | 260/672 = 38.7% [35.1, 42.4] |
| jd5-B (`jd5-recheck-real`) | 167 | 455 | 167/622 = 26.8% [23.5, 30.5] |

Difference +11.8 points, Newcombe [6.7, 16.8]; one-sided Fisher (less) p = 1. **P2 NOT
SHOWN.** Second denominator (≥ 1 well-formed): 260/633 = 41.1%, p = 1.

Descriptive paired 2×2 on the 337 cells right under both before-states and contested by
both challengers: F-weak alone broke 83, jd5-B alone 41, both 64, neither 149; McNemar
p = 0.0002 — F-weak breaks more of the SAME cells.

## (3) P3 — `fixed | wrong` (reported)

| mechanism | fixed / wrong contested | rate |
|---|---|---|
| F-weak | 278/401 | 69.3% [64.6, 73.6] |
| F-strong | 7/126 | 5.6% [2.7, 11.0] |
| jd5-B | 144/274 | 52.6% [46.6, 58.4] |

## (4) Recorded

**(4a) findings judge vs M0** (same 1,644 transcripts; DESCRIPTIVE)

| arm | M0 | findings judge | fixed / broken | net | McNemar p |
|---|---|---|---|---|---|
| F-weak (same model, re-draw + format + rule + routing) | 1,211 = 73.7% | 1,118 = 68.0% | 138 / 231 | **−93** | 1.5e-6 |
| F-strong (different model) | 1,211 = 73.7% | 1,279 = 77.8% | 242 / 174 | +68 | 0.001 |

**(4b) after recourse vs M0** (ABLATION): F-weak 186 fixed / 261 broken, **−75**, p = 4.5e-4
(69.1% vs 73.7%); F-strong 241 / 177, +64, p = 0.002 (77.6% vs 73.7%, a different model).

**(4c) §3ac's identity** (over the cells each mechanism ruled)

| mechanism | n | a | f | b | f/b | a* | net |
|---|---|---|---|---|---|---|---|
| F-weak | 1,073 | 62.6% | 69.3% | 38.7% | 1.79 | 64.2% | +18 |
| F-strong | 606 | 79.2% | 5.6% | 2.3% | 2.42 | 70.8% | −4 |
| jd5-B | 896 | 69.4% | 52.6% | 26.8% | 1.96 | 66.2% | −23 |

**(4d) split by before-verdict** (the derived rule's asymmetry)

| arm | before-verdict | fixed \| wrong | broken \| right |
|---|---|---|---|
| F-weak | SOUND (n 834) | 274/369 = 74.3% | **258/465 = 55.5%** |
| F-weak | FLAWED (n 239) | 4/32 = 12.5% | 2/207 = 1.0% |
| F-strong | SOUND (n 408) | 7/84 = 8.3% | 11/324 = 3.4% |
| F-strong | FLAWED (n 198) | 0/42 | 0/156 |

By `findings_flaw_n`: every move in either arm is on a list with 0 FLAW findings except
4 fixes and 2 breaks on F-weak lists with exactly one; none on lists with ≥ 2.

**(4e) the objection**

| | F-weak | F-strong |
|---|---|---|
| contests (per objection) | 1,427 (1.33) | 684 (1.13) |
| finding / omission / contradiction | 1,296 / 89 / 42 | 551 / 130 / 3 |
| void | 134 (9.4%) | 42 (6.1%) |
| direction: → FLAW / → NOT A FLAW | 1,277 (98.5%) / 18 | 506 (91.8%) / 44 |
| record quote unverified (recorded, not voiding) | 145 | 96 |
| void-only objections | 66/1,076 | 35/606 |
| seeking a reversal | 77.8% | 70.3% |
| mechanical phantom | 1/1,641 | 0/1,644 |
| comprehension mean | 4.41 | 4.63 |

**(4f) validity** (never pooled across `label_basis`; finding contests toward FLAW are a
LOWER bound, toward NOT A FLAW an UPPER bound)

| arm | contests VALID | mechanical (no call) | final_answer | injected_pair | sentence_labels |
|---|---|---|---|---|---|
| F-weak | 537/1,428 = 37.6% | 657 | 79/154 = 51.3% | 248/668 = 37.1% | 90/254 = 35.4% |
| F-strong | 144/684 = 21.1% | 411 | 35/83 = 42.2% | 58/344 = 16.9% | 47/179 = 26.3% |

**(4g) rulings**

| | F-weak | F-strong |
|---|---|---|
| line/prose mismatch (final reader; void-only excluded) | 137/1,005 = 13.6% (26 lead-ins stripped) | 9/570 = 1.6% |
| rulings with no prose | 3 | 1 |
| findings appended (upheld omissions) | 54 over 51 rulings; 18 moved a verdict | 8; 0 moved |

## (5) Named outcome

**F-weak: (D)** — P1 NULL and P2 NOT SHOWN. **F-strong: P1 NULL** (its own family). Not
a split: both tests are null and P2 fails in the direction opposite to the hypothesis.

## Hand check (`HANDCHECK.md`)

(a) 5 breaks: 5/5 arguable, 5/5 adopted, 2/5 hedged or conditional. (b) 5 fixes: 3/5 on
the annotated flaw; 2/5 shown, 3/5 adopted; one certain-grade contest (an arithmetic error
inside a finding's reason). (c) 5 appended findings: 4/5 consequences of a listed finding.
(d) 5 disagreement cells: weak contested 5/5 and granted 5/5 (2 fixed, 2 broken); strong
declined 4/5, refused 1 (where the challenger was right). (e) 0 phantoms in 20.

## Instruments

Injection instrument (pilot lists): flip detection 60% weak / 90% strong, paired false
alarm 45% / 10%; deletion 30% / 60%; duplicate 100% / 85%. Reader re-read: weak mismatch
17/44 → 1/36 (void-only excluded). Source scan of jd3-main: glued `Argument:` in 854/1,644
cells (51.9%), scaffolding tags 105, private deliberation 4.

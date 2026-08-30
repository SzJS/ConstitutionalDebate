# judgment-debate-6 — the checklist. §0 FIRST.

Every number is re-derivable on a bare clone:
`uv run python records/derivations/judgment-debate-6.py`, whose defaults point at
`arm-round/index.jsonl` and `arm-plain/index.jsonl` in this directory. The whole output is
`derivation.log`.

---

## §0 — THE PRE-REGISTERED ENDPOINT, AND IT IS A SPLIT

Both arms decided the same 896 cells. The before-state is M0's verdict; the after-state in
**R** is the ruling's and in **B** is the re-judge's own. Cells missing in either arm are
DROPPED and counted in §1 below, per `PREREG.md`'s loss rule.

### P1 — PRIMARY, α = 0.05 — on the 583 initially-CORRECT cells both arms decided

|  | B right | B wrong | total |
|---|---|---|---|
| **R right** | 296 | 62 | 358 |
| **R wrong** | **176** | 49 | 225 |
| total | 472 | 111 | 583 |

* broken by **R alone**: **176** · broken by **B alone**: **62** · both 49 · neither 296
* discordant 238, concordant 345 · **exact two-sided McNemar p = 7.888e-14**
* accuracy after R **358/583 = 61.4%** [57.4, 65.3] · after B **472/583 = 81.0%** [77.6, 83.9]

> **P1 FAILED, and significantly in the opposite direction.** It predicted the contest round
> would break FEWER right decisions than the plain round. It breaks **2.8× as many**.

### P2 — CO-PRIMARY — on the 263 initially-WRONG cells both arms decided

|  | B right | B wrong | total |
|---|---|---|---|
| **R right** | 50 | **98** | 148 |
| **R wrong** | 35 | 80 | 115 |
| total | 85 | 178 | 263 |

* fixed by **R alone**: **98** · fixed by **B alone**: **35** · both 50 · neither 80
* discordant 133, concordant 130 · **exact two-sided McNemar p = 4.292e-08**
* accuracy after R **148/263 = 56.3%** [50.2, 62.1] · after B **85/263 = 32.3%** [27.0, 38.2]

> **P2 HELD.** The contest round fixes nearly three times as many wrong decisions as the
> plain round.

### The reading, and it is not rounded

**The endpoint was P1 ∧ P2 and it is not met: P1 failed.** The pair is a SPLIT — the contest
round is **more interventionist in both directions**, breaking more right decisions AND
fixing more wrong ones.

**It is none of the four named outcomes.** (A) needs P1. (B) needs R to break fewer. (C)
needs B to beat R on both, and R beats B decisively on the wrong cells. (D) needs no
separation, and both tests separate at p < 1e-7. `PREREG.md`'s rule — *"an outcome that is
(A) on P1 and (C) on P2, or any other split, is reported as the split it is, with both
tests' numbers, and is NOT rounded to whichever named outcome it is nearest"* — is applied
here and the rule was written before either arm ran.

**The mechanism is named by the hand check, not by these tables: adoption.** See §7.

**There is no NET on either table above.** Both columns are after-states; the gain or loss
against M0 is §4, and it is an ablation.

---

## §1 — ATTEMPTED, COMPLETED, FAILED, AND WHAT THE LOSSES WERE

| arm | attempted | completed | failed | loss |
|---|---|---|---|---|
| R — contest round | 896 | **855** | 41 | 4.6% |
| B — plain round | 896 | **886** | 10 | 1.1% |

Every failed cell is listed with its error verbatim in `attempts.json` and in
`derivation.log` §0. The shapes are the same in both arms — **arm R: 39 round-4 truncations, 1 malformed turn, 1
judge reply with `finish_reason='error'`; arm B: 8, 1 and 1.** A truncation is a restart loop
in the private Thinking block hitting `generation_max_tokens = 8192` — the sweep's own
failure mode, not new here. A malformed turn is one still missing its `Argument:` label after
the one repair, which the parser refuses to guess at (ground rule 7). Neither is a bug; both
cost a cell rather than corrupting one.

**A failed cell is DROPPED from every paired table and counted here** — never absorbed into a
denominator. `--retry-failed` was on, so a cell that appears here failed **twice**, and
because the debaters run at temperature 0.7 the retry was a **different draw**, not a repeat.

**40 `recourse_transcript.json` files hold ONE turn, not two.** That is what a failed cell
leaves behind: the completed turn is committed before the round raises. 856 hold two, against
855 rulings — the one extra is the cell that heard a full round and then lost its ruling.

---

## §2 — PROVENANCE

| | |
|---|---|
| ran | 2026-08-30 **02:28:23Z → 05:30:49Z**, 3 h 02 m, one driver process |
| driver | `run-all.sh` (working copy `outputs/jd6-run-all.sh`), R then B, sequentially |
| stages | R `rerule ruling_agreement analyse`; B `rejudge analyse`. All five exit 0 |
| calls | **6,401**, **0 non-2xx** |
| spend | **$11.9847** — R $7.5823, B $4.4024. Estimate was $14.6 (with 1.3× headroom $19), so it came in **18% under** |
| smokes | $0.1426, outside this registration (`logs/smoke-1-read.txt`, `logs/smoke-2-read.txt`) |
| provider check | $0.0000044, `logs/provider-check.log`, VERDICT PASS |
| **campaign total** | **$12.1273** |
| PREREG | committed at `d13400b`, with the code and the driver, **before the first paid call** |
| source tree | `outputs/experiments/jd3-main`, **read-only**, `dfa9bdca3fe93630701b4659cdb4ac8605ce07d58b29c29ad868c1048c12209c` before the first arm, between the arms and after the last (`logs/fingerprints.md`) |
| population | `data/cases/jd6-contested.jsonl`, 896 items, count-asserted by `records/derivations/jd6-pick.py`; 622 M0-correct, 274 M0-wrong |

### The pin held

| arm | role | calls | provider |
|---|---|---|---|
| R | `recourse_judge` | 856 | **DigitalOcean 100%** |
| R | `recourse_debater` | 1,863 | GMICloud 98.8%, CoreWeave 1.2% |
| R | `ruling_reader` | 855 | Amazon Bedrock 100% |
| B | `judge` | 887 | **DigitalOcean 100%** |
| B | `debater` | 1,940 | GMICloud 98.9%, CoreWeave 1.1% |

Both Maverick seats were served entirely by the pinned provider, which is what makes "only
the round moved" a fact rather than an intent. The deepseek fallback to CoreWeave is the
pin's second entry and is what `provider_order` is for.

---

## §3 — THE CONDITIONAL RATES, ALL FOUR ARMS ON THE SAME CELLS [DESCRIPTIVE]

| arm | n | fixed \| wrong | broken \| right |
|---|---|---|---|
| M1 — judge-only, OLD prompt, unpinned | 896 | 110/274 40.1% [34.5, 46.0] | 128/622 20.6% [17.6, 23.9] |
| jd5-B — judge-only, unpinned | 896 | 144/274 52.6% [46.6, 58.4] | 167/622 26.8% [23.5, 30.5] |
| **jd6 R — ARGUED, pinned** | 896 | **149/274 54.4%** [48.5, 60.2] | **226/622 36.3%** [32.6, 40.2] |
| **jd6 B — plain round, pinned** | 886 | **86/270 31.9%** [26.6, 37.6] | **119/616 19.3%** [16.4, 22.6] |

* `broken | right`: R 36.3% vs B 19.3% — **+17.0 pts**, and P1's direction wanted negative.
* `fixed | wrong`: R 54.4% vs B 31.9% — **+22.5 pts**, and P2's direction wanted non-negative.

**The discrimination gap** (fixed|wrong − broken|right) is R **+18.1** against B **+12.6** and
jd5-B **+25.8**: the argued round discriminates better than the un-steered one and **worse
than no round at all**.

> **Every absolute rate in arm B contains Maverick's own re-draw disagreement with itself**
> as well as the extra round's effect. No floor arm was run to price it (struck by the user,
> 2026-08-30). §0 is free of it; this table is not.

---

## §4 — NET ACCURACY AGAINST M0 [ABLATION — NEVER AN ENDPOINT]

| arm | fixed | broken | net | p | accuracy M0 → after |
|---|---|---|---|---|---|
| jd6 R | 149 | 226 | **−77** | 8.238e-05 | 69.4% → **60.8%** |
| jd6 B | 86 | 119 | **−33** | 0.02518 | 69.5% → **65.8%** |
| *jd5-B (no round)* | *144* | *167* | *−23* | *0.212* | *— * |
| *M1 (no round, old prompt)* | *110* | *128* | *−18* | *0.270* | *—* |

Both jd6 arms make the corpus **less** accurate than M0 left it, and R more so than B. This
is the quantity jd3–jd5 reported as P1 and it is demoted here for the reason `PREREG.md`
gives: it is dominated by the 26% base rate of wrong decisions, so an arm that breaks and
fixes at equal *rates* still nets negative. It is not the endpoint and is not read as one.

---

## §5 — R AGAINST jd5-B: THE SAME OBJECTIONS WITH AND WITHOUT A ROUND [DESCRIPTIVE]

|  | jd6-R OVERTURN | jd6-R UPHOLD | total |
|---|---|---|---|
| **jd5-B OVERTURN** | 196 | 100 | 296 |
| **jd5-B UPHOLD** | **179** | 380 | 559 |
| total | 375 | 480 | 855 |

* jd5-B overturn **296/855 = 34.6%** → jd6-R **375/855 = 43.9%**
* 179 gained an overturn, 100 lost one · **exact two-sided McNemar p = 2.607e-06**

> **PROVIDER CAVEAT, and it is why this is descriptive and not an endpoint.** jd5-B's judge
> was **unpinned** (34% of M1's rulings on DeepInfra against 4.8% of jd5-B's, §3aa) while
> both jd6 arms pin DigitalOcean. This table mixes the round with the routing and cannot
> separate them. §0 can, because both its arms are pinned to the same provider.

---

## §6 — THE ROUND-4 TURNS, AND THE FORMAT INSTRUMENTS [DESCRIPTIVE]

| | arm R | arm B |
|---|---|---|
| turns | 1,752 | 1,772 |
| parse modes | strict 1,685 · salvaged_no_thinking 63 · strict_after_budget_repair 4 | strict 1,632 · salvaged_no_thinking 139 · salvaged_..._after_budget_repair 1 |
| format repairs | 70 | 146 |
| words min / median / max / mean | 15 / **317** / **1,674** / 346 | 22 / 296 / 696 / 304 |
| truncations recorded on disk | 0 | 0 |

A truncated turn is **never committed**, so it leaves no row carrying `finish_reason =
"length"`; it leaves a half-round and a failed cell, which §1 counts.

### The glued `Argument:` label — INHERITED, not introduced

| arm | round-4 turns | glued | rate | parent rounds 1–3 | glued | rate |
|---|---|---|---|---|---|---|
| R | 1,752 | 187 | **10.7%** | 5,376 | 571 | 10.6% |
| B | 1,772 | 134 | **7.6%** | 5,316 | 568 | 10.7% |

Neither round raises the habit; arm B's is lower than its own parents'. The label is written
mid-sentence, so `parse_debater_output` — which takes the last label at a *line start* —
publishes the planning text before it.

### By stance, arm R

| stance | turns | glued | truncated | over 400 w | median words | max |
|---|---|---|---|---|---|---|
| **PRO** | 869 | 104 (12.0%) | 0 | **151 (17.4%)** | 320 | **1,674** |
| **ANTI** | 883 | 83 (9.4%) | 0 | 103 (11.7%) | 313 | 767 |

PRO runs longer and glues more often — the asymmetry both smokes flagged, now at n = 1,752.

---

## §7 — THE HAND CHECK: THE MECHANISM IS ADOPTION

20 cells, read by Fable, in [`HANDCHECK.md`](HANDCHECK.md); the cells were chosen by
`records/derivations/jd6-handcheck-pick.py` (`logs/handcheck-pick.md`) and their documents
are in `transcripts/`. **The counts, quoted:**

* **(a) R broke a right decision that B kept — 5 cells.** **5/5 adopt PRO**; **5/5 leave
  ANTI unanswered**; **3/5** overturns are conditional; **5/5** are thin omissions the
  judgment had **addressed in substance**.
* **(b) R kept a right decision that B broke — 5 cells.** **5/5 weigh both replies**; **5/5**
  of B's breaks follow the FLAWED-side round-4 argument.
* **(c) the adopt-one-reply instrument fired — 5 cells.** **4/5 adopt PRO** (3 fixes, 1
  break); the instrument is **right about adoption 4/5** and **right about direction 3/5**.
* **(d) the plain arm moved a verdict — 5 cells.** **5/5** fresh judgments follow one round-4
  argument; **4/5** are wrong; **1/5** had one debater silenced by a 22-word stub.
* **Format, across the 40 round-4 turns read:** glued labels **6/40**, **4 of them PRO**.

### The instrument, at scale

| | |
|---|---|
| cells scored | 856 |
| one-sided (≥ 2× the other, floor 0.02) | **471/856 = 55.0%** |
| of those, tracking **PRO** | **421** |
| of those, tracking ANTI | 50 |
| mean overlap with PRO / ANTI | 0.148 / 0.082 |
| ruling prose names the exchange | 769/896 = 85.8% |
| ANTI disputes a quotation | 151/883 = 17.1% |
| PRO disputes a quotation | 117/869 = 13.5% |

**The instrument is lexical and cannot tell adoption from agreement** — which is why the
hand read exists, and the hand read is what the write-up quotes. What the two agree on is
the direction: **when the ruling tracks one reply at all, it is PRO's 421 times out of 471 — 89%.**

### Why adoption produces exactly the split in §0

PRO is, by construction, the **loser's** debater — the one arguing the decision should
change. A judge that reproduces PRO overturns more often, and overturning more often on a
population that is 69% correct raises `broken | right` **and** `fixed | wrong` together.
That is §3's +17.0 and +22.5 pts, and it is §0's 176-vs-62 beside 98-vs-35.

---

## §8 — WHAT THIS DOES NOT SETTLE

* **The same-model property**, unrepaired: Maverick judged these debates and rules on the
  appeals against its own judgments. `RECOURSE_DEBATER_CLAUSE` tells the debaters they
  address "a second judge, who did not make the decision" — true of the ROLE, false of the
  WEIGHTS (`PREREG.md`, E3).
* **Arm B is a three-round debate plus an appended consolidation round**, not a native
  four-round debate: rounds 1–3 were argued under "round N of 3", so round 3 already carried
  the consolidating instruction. **Arm R inherits the same property**, so the paired test is
  unaffected; no claim about "a four-round debate" is made.
* **Every absolute overturn-vs-M0 rate in arm B** carries the judge's own re-draw
  disagreement. No floor arm prices it.
* **Nothing here re-opens jd3's P1**, compares `debate` with `single`/`self_critique`, or
  repairs the natural-error selection bias or the missing `weak_alone` condition.
* **No number here is pooled with jd3's, jd4's or jd5's**: the ruling prompt differs from
  jd3's and jd4's, and the **pin** differs from all four.

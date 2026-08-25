# pilot-3 — checklist

Run 2026-08-25 21:55–22:25 UTC, five stages sequentially, each `nohup … &` and waited on
its own `$!` with `until ! ps -p $PID`. 311 tests passed before the run.
Every number below is re-derivable: `outputs/pilot-3-checks.py`, `-checks2.py`,
`-handcheck-sample.py`, `-paths.py`, with their `.log` outputs beside them.

**Read this first.** Prompts and routing both changed between pilot 2 and pilot 3, in
the same run, and there is no unpinned arm. **No pilot-2 ↔ pilot-3 comparison is valid
and nothing here may be attributed to the provider pin.** These are the pinned pair's
absolute rates under the new challenger instruction.

| # | check | threshold | result | verdict |
|---|---|---|---|---|
| 1 | parse | ≥98% decided | **177/207 = 85.5%** decided; all 30 failures are truncations, 0 malformed-after-repair | **FAIL** |
| 2 | repair | <10% of original calls cause a repair on the pinned pair | **198/881 = 22.5%** on the strong model; malformed-after-repair **0** | **FAIL** (the sub-criterion "malformed-after-repair ≤1" passes at 0) |
| 3 | verdicts | neither class >85% in any condition | max share **55.9%** (single) | **PASS** |
| 4 | stances | reported per condition, split both ways | see below | **REPORT** |
| 5 | line vs prose | reported | phantom-contest rate **13/30 = 43.3%**; hand-vs-Haiku **19/20** | **REPORT** |
| 6 | containment | zero `Thinking:` in challenger-visible records | **0** in 204 records | **PASS** |
| 7 | critiques | withheld critique steps; self_critique challengers shown a placeholder = 0 | **0/166** withheld; **0** placeholders | **PASS** |
| 8 | grader | every grade hand-checked; ~10 rows | **2 rows**, both hand-checked; agreement 1/2 identified, 2/2 characterised | **REPORT** (short of ~10) |
| 9 | ops | reported | 0 non-200 in 1,679 attempts; 30 min wall-clock; $0.9504; $0.00537/cell | **REPORT** |
| 10 | hand-read | four paths | all four found and read | **PASS** |

---

## Row 1 — parse

177 of 207 cells decided (85.5%). **All 30 failures are truncations at
`generation_max_tokens = 8192`; none is a malformed reply.** 48 of 1,679 attempts (2.9%)
truncated, every one of them at exactly 8,192 completion tokens, 21k–40k characters of
private deliberation (median 29,632).

| role | stage | past its public label (fatal by design) | never reached it (budget route) |
|---|---|---|---|
| critic | critique | 13 | 3 |
| debater | turn | 8 | 10 |
| debater | repair | — | 4 |
| solo | answer | 1 | 2 |
| solo | draft | 2 | — |
| solo | revision | 2 | 3 |

The budget route fired on the 22 that never reached a label and **recovered 14** of them
(`*_after_budget_repair`: 7 `strict`, 7 `salvaged_no_thinking`).

**The critique-past-its-label case is the single commonest fatal shape: 13 of 30 lost
cells.** §3m named it in advance — the `unrepaired` withholding is reachable only on the
*second* failure, so a critique that truncates *past* `Reasoning:` is fatal on the first.
Pre-registered expectation 7 said "one or two"; it was 13.

By condition, the 30 lost cells: self_critique 17, debate 12, single 1.

## Row 2 — repair

| provider | original calls | caused a repair | rate |
|---|---|---|---|
| GMICloud | 880 | 198 | **22.5%** |
| CoreWeave | 1 | 0 | 0.0% |
| OpenAI (nano) | 421 | 0 | 0.0% |
| Amazon Bedrock (Haiku) | 179 | 0 | 0.0% |

198/198 repairs paired to the call that failed. On the strong model alone: 198/881 =
**22.5%**, against a pre-registered <10%. Which instruction was sent: aimed
misplaced-label 136, aimed no-public-label 40, budget 18, per-role fallback 4.

**Zero cells died malformed after their repair.** In pilot 2 that number was 15. Every
one of the 198 aimed repairs was accepted by the parser.

## Row 3 — verdicts

| condition | n | FLAWED | SOUND | max share | gold flawed | accuracy |
|---|---|---|---|---|---|---|
| single | 68 | 38 | 30 | 55.9% | 34 | 88.2% |
| self_critique | 52 | 24 | 28 | 53.8% | 28 | 88.5% |
| debate | 57 | 26 | 31 | 54.4% | 26 | **54.4%** |

## Row 4 — stances

| condition | n | contests | declined | unclear | contest rate |
|---|---|---|---|---|---|
| single | 68 | 8 | 60 | 0 | 11.8% |
| self_critique | 52 | 12 | 40 | 0 | 23.1% |
| debate | 57 | 10 | 47 | 0 | 17.5% |

**Zero `unclear` in 177 contests** — every reply carried a parsable `Decision:` line.

Split by the **parent verdict class**:

| condition | FLAWED verdicts | contest rate | SOUND verdicts | contest rate |
|---|---|---|---|---|
| single | 38 | 18.4% | 30 | 3.3% |
| self_critique | 24 | 16.7% | 28 | **28.6%** |
| debate | 26 | 34.6% | 31 | 3.2% |

Split by **correctness**:

| condition | correct | contest rate | incorrect | contest rate |
|---|---|---|---|---|
| single | 60 | 13.3% | 8 | 0.0% |
| self_critique | 46 | 23.9% | 6 | 16.7% |
| debate | 31 | 9.7% | 26 | 26.9% |

Contests given a **false negative** vs a **false positive**:
single 0/2 and 0/6; self_critique 1/5 and 0/1; debate 1/13 and 6/13.

Derived `claimed_verdict` across all 177: SOUND 99, FLAWED 78 — 56% SOUND. Pre-registered
note 2 warned this column would read SOUND-heavy with no reflex behind it, and it does.

## Row 5 — line vs prose

177 of 177 eligible contests measured.

| condition | line | Prose: RIGHT | Prose: WRONG | Prose: NEITHER |
|---|---|---|---|---|
| single | REVERSE | **6** | 2 | 0 |
| single | STANDS | 58 | 2 | 0 |
| self_critique | REVERSE | **2** | 10 | 0 |
| self_critique | STANDS | 40 | 0 | 0 |
| debate | REVERSE | **5** | 5 | 0 |
| debate | STANDS | 47 | 0 | 0 |
| **ALL** | REVERSE | **13** | 17 | 0 |
| **ALL** | STANDS | 145 | 2 | 0 |

**Phantom-contest rate: 13 of 30 contests = 43.3%.** Per condition: single **6/8 = 75%**,
debate 5/10 = 50%, self_critique 2/12 = 17%. Declines whose prose argued for reversal:
2 of 147, both in `single`.

**Hand check, 20 replies, stratified by stance × parent verdict** (`outputs/pilot-3-handcheck.log`):
**19 of 20 agree with the Haiku reading.** The one disagreement is
`python800-p03845-flawed__single__r1`, whose prose endorses the FLAWED verdict at length
and then closes "the correct decision is to **reverse** the verdict"; Haiku read RIGHT,
the hand read is NEITHER (self-contradictory). Both readings agree it is not a clean
contest, so its phantom classification is unaffected.

A live example of the first-match rule, worth recording:
`medqa-train_3754__single__r1` wrote `Decision: REVERSE` at the head **and again** at the
foot. The head one decided and was stripped; the trailing restatement stayed in the
published body, where a reader can see it.

## Row 6 — containment

**0** occurrences of a `Thinking:` label in published argument or step text, across 204
challenger-visible decision records.

| provider | calls | native reasoning | rate |
|---|---|---|---|
| GMICloud | 1078 | 172 | **16.0%** |
| OpenAI | 421 | 0 | 0.0% |
| Amazon Bedrock | 179 | 0 | 0.0% |
| CoreWeave | 1 | 0 | 0.0% |

Reasoning billed but withheld: 0. Pre-registered expectation 5 said ≈0 native reasoning
on the strong model; it is 16.0%.

## Row 7 — critiques

166 critique steps, **0 withheld** (pilot 2: 21 of 139, 15%). **0** self_critique
challengers shown a placeholder, which is what expectation 6 asked for.

## Row 8 — grader

Only **2** rows were gradable — grading needs flawed item ∧ explanation-quality
annotation ∧ wrong decision ∧ stance == contests, and the challenger contested only 2 of
the 20 false negatives in the whole run. Both hand-checked against `flaw.json`:

| cell | grader | hand read | agree |
|---|---|---|---|
| `medqa-train_1701__debate__r1` | identified YES, characterised YES, valid | The annotation says a patient wishing CPR can still receive hospice and the LLM treated a philosophical incompatibility as a formal disqualifier. The objection says exactly that, in its own words, without having seen the annotation. | **yes, on both bars** |
| `medqa-train_3754__self_critique__r1` | identified NO, characterised NO, not valid | The annotation says the answer should be (E) duodenal biopsy. The objection concludes for (C) vitamin E — a different claim — but it *does* name the biopsy point in passing ("it dismisses the bowel wall biopsy (E) … ignoring that celiac disease … is diagnosed via biopsy"). A hand read calls identification a marginal YES. | **characterised yes; identified — dissent** |

Agreement: **2/2 on `characterises_the_flaw`, 1/2 on `identified_flaw`**, with the
dissent being the grader stricter than the hand read (the same direction as pilot 2's one
dissent on `law-evi5`).

## Row 9 — ops

- **0 non-200 attempts in 1,679.** No 404, no 429, no 5xx. The pin never failed.
- Served providers over every call: GMICloud 1,078 (64.2%), OpenAI 421 (25.1%), Amazon
  Bedrock 179 (10.7%), CoreWeave 1 (0.1%). Of the 1,079 strong-model calls, **1,078 went
  to GMICloud and 1 to CoreWeave** — the pin held.
- Wall-clock: decide 26.0 min, contest 2.7 min, agreement 0.6 min, grade 0.3 min,
  analyse 5 s. **Total 30 min** for 207 cells.
- Spend **$0.9504** (decision path $0.7156, off path $0.2348) = **$0.00537 per decided
  cell**. By model: deepseek $0.6072 (63.9%), Haiku $0.1875 (19.7%), nano $0.1557 (16.4%).
- **Sweep projection at 2,110 items × 3 conditions = 6,330 cells: $34.0**, or **$44.2**
  with 1.3× headroom. This is the pinned cost and includes the new `agreement` stage;
  it cannot be compared with an unpinned estimate, because there is no unpinned arm.
- Wall-clock projection at the same 16/8: 6,330 cells at 26 min per 207 ≈ **13 h** for
  `decide`, ≈ 15 h for the whole sweep.

## Row 10 — the four hand-read paths

| path | cell | what it shows |
|---|---|---|
| genuine contest, `single` | `medqa-train_2855__single__r1` | REVERSE + Prose: WRONG on a correct FLAWED verdict; the re-decider held. |
| genuine contest, `self_critique` | `medqa-train_3754__self_critique__r1` | REVERSE + Prose: WRONG on a **false negative**; the decision changed and became correct. |
| genuine contest, `debate` | `lojban-stim172_gpt4_B-s4__debate__r1` | REVERSE + Prose: WRONG on a **false positive**; the recourse judge overturned and the final verdict is correct. Its `transcript.md` also shows the D1 rendering fix working: the judge's grounds end on a dangling `**Final`, and the verdict now prints below it. |
| declined on a wrong decision | `gpqa-102-sound__single__r1` | STANDS on a false positive, comprehension 5. The stakeholder followed the record and endorsed a wrong decision. |

Full paths in `outputs/pilot-3-paths.log`.

## The funnel, for the record (177 cells)

| | overall | single | self_critique | debate |
|---|---|---|---|---|
| decision_error | 40/177 | 8/68 | 6/52 | **26/57** |
| contests \| incorrect | 8/40 | 0/8 | 1/6 | 7/26 |
| false alarm \| correct | 22/137 | 8/60 | 11/46 | 3/31 |
| revised \| incorrect | 5/40 | **0/8** | 1/6 | 4/26 |
| revised \| correct | 3/137 | **0/60** | 1/46 | 2/31 |
| accuracy before → after | 137/177 → 139/177 | 60/68 → 60/68 | 46/52 → 46/52 | 31/57 → **33/57** |

`single` moved **0 of 68** — pre-registered expectation 3 said ≤2, and it is 0.
`decision_record_words`: single 151, self_critique 1,884, debate 1,857 — the two long
conditions are matched to within 1.5%, and `single` is an order of magnitude shorter,
which is a property of the condition and not of this run.

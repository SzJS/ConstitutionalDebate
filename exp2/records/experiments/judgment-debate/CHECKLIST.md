# The debate-only judgment-challenge run — the checklist

Every number here is re-derivable from the files beside it: `index.jsonl` and
`metrics.json` in this directory, `derivation.log` (the output of
`records/derivations/judgment-debate-vs-alone.py` run against **this** committed index),
and `logs/stage-tails.md`. Nothing reads the run tree except the defects-by-type table,
which says so.

**Read §0 before any recourse-stage number.**

---

## 0. THE ONE THING TO READ FIRST — the ruling-line residual

`ruling_line_mismatch` fired on **349 of 1,147 rulings (30.4%)**, and it is **concentrated
on FLAWED parents**:

| | rulings read | mismatch |
|---|---|---|
| all | 1,147 | **349 (30.4%)** |
| parent FLAWED | 598 | **304 (50.8%)** |
| parent SOUND | 549 | 45 (8.2%) |
| upheld | 846 | 253 (29.9%) |
| overturned | 301 | 96 (31.9%) |
| **FLAWED parent, overturned** | 110 | **87 (79.1%)** |
| FLAWED parent, upheld | 488 | 217 (44.5%) |

**102 of the 349 are `NEITHER`** — the reader settled on nothing, which counts as a
mismatch by the conservative rule this instrument has always followed. The strict
contradiction rate is **247/1,147 = 21.5%**.

Three things a reader must hold together:

1. **This is the same shape the OLD ruling line failed in.** `LLM_NOTES.md` §3t found the
   `Ruling: UPHOLD|OVERTURN` line contradicting its own reasoning on FLAWED parents and
   not on SOUND ones; the re-rule that replaced it measured a residual that was **flat**
   across parents at ~6%. This run's residual is neither flat nor 6%.
2. **The instrument was revised for this run** (`PREREG.md`, "The instrument revision"),
   and the revision *lowered* the rate on pilot 2 from 35.1% to 16.2%. So 30.4% is what
   the **adapted** reader says, not what the mismatched one said.
3. **It lands on the endpoint's own cells**: mismatch is 47/173 (27.2%) of the cells
   counted as *fixed* and 49/128 (38.3%) of those counted as *broken*.

**The hand check settles what the 30% is, and it is not reader error.**
[`HANDCHECK-B-rulings.md`](HANDCHECK-B-rulings.md) read 20 alarms from the two large
groups and found the reader **right about what the prose says in 12/12 and 8/8**, with the
two-step structure present in 20/20 rulings. So:

- On the **156 upheld & reader-says-CHANGED**, the judge finds the defect real *and
  material* in Step 2 and then ends on the parent's own line. Under its own rule a
  material defect changes what is true of the text, so this is the judge contradicting the
  rule it was given. The visible mechanism is a nesting collision one layer up — "the
  original *judgment* is flawed" and "the original *text* contains a flaw" in consecutive
  sentences. **Ten of the twelve read were CORRECT decisions**, and the instruction to copy
  the parent's line when the decision stands is what kept them correct.
- On the **79 overturned & reader-says-STANDS**, the judge says the defect is not real or
  not material and then re-decides the item on object-level grounds anyway, its line
  following that. These are **not** line-vs-prose contradictions in the old sense; they are
  the judge setting the materiality rule aside — **the confound `PREREG.md` names, occurring
  inside the new prompt**.

So `ruling_line_mismatch` = 30.4% is a measurement of **the weak judge's coherence under
the materiality prompt**, not of the instrument: its Step-2 verdict on materiality and its
final line disagree in about a fifth of rulings, in both directions.

Section (f) of `derivation.log` is the post-hoc sensitivity this motivated — it flips the
~156 one way and the ~79 the other. It is **not pre-registered** and it is descriptive; the
pre-registered endpoint is the line, as the run produced it.

---

## 1. What ran

| | |
|---|---|
| spec | `experiments/judgment-debate.toml` |
| tree | `outputs/experiments/judgment-debate` (git-ignored; its summary artifacts are here) |
| stages | `contest agreement ruling_agreement grade analyse`, sequentially, one driver |
| started / finished (UTC) | 2026-08-28T01:48:17Z → 03:18:22Z (**1 h 30 m**) |
| every stage's exit code | **0** |
| cells attempted | 2,110 debate cells; **1,644 had a sweep decision to contest**, 466 skipped |
| cells contested | **1,643 completed, 1 failed** |
| wire calls | **9,982**, **0 non-2xx** |
| spend | **$33.9371** |
| decisions | read from `outputs/experiments/sweep` through `decisions_from`; **nothing regenerated** |
| sweep tree fingerprint | `5e2eb4d6…` before and after — byte-identical (`outputs/sweep-tree.sha256.after-judgment-debate`) |

**One spend figure, not two.** The driver's cumulative total and the wire log agree
exactly: `$33.9371` over 9,982 calls, counting only this tree's own `calls.jsonl` and not
the copied parent decision records. (The auditor probe needed two figures because format
repairs were charged differently; here the two coincide.)

Per-stage, from `logs/stage-tails.md`:

| stage | cells | cumulative | stage |
|---|---|---|---|
| contest | 1,643 completed, 1 failed, 466 skipped | $20.4895 | $20.4895 |
| agreement | 1,644 | $22.5587 | $2.0692 |
| ruling_agreement | 1,147 (963 skipped: no ruling to read) | $25.0959 | $2.5372 |
| grade | 1,148 (962 skipped) | $33.9371 | $8.8412 |

**The one failed cell** is `lojban-stim181_gpt4_B-s5__debate__r1`: the *comprehension
probe* — off the decision path — stopped on `finish_reason='error'` at
`max_tokens=16384`. Its objection and ruling were never written; it appears in
`index.jsonl` with the decision columns and no challenge columns, and it is one of the
1,644 in every denominator below.

## 2. The two revisions, and the disclosed departure

Both are dated and argued in [`PREREG.md`](PREREG.md), committed before the run.

- **Format (prompt only).** The `Argument:` label is shown at the head of the response
  template. It did **not** work: 1,588 of 1,644 objections still needed a format repair.
  The run goes with the repair path, which lost no cell.
- **Recourse (materiality).** For this arm only, the recourse judge is shown the judgment
  and rules in two steps — is each alleged defect real against the record, and if so is it
  material — with the decision's own `Conclusion:` line supplied as the line to end on
  when the decision stands. `ruling_prompt_form` is `materiality` on **all 1,147** rulings.
- **The instrument** (`ruling_agreement`) was adapted to the materiality prompt, arm-keyed,
  after pilot 2. Off the decision path.
- **The challenger is `google/gemini-2.5-flash`, chosen AFTER the auditor probe's
  pre-registered rule picked nobody** (`records/pick-auditor/RULES.md`, `DECISION.md`).
  Disclosed in the spec header, in `PREREG.md` and here.

## 3. THE PRIMARY ENDPOINT — verbatim from `derivation.log` §(a)

Population: every debate cell the sweep decided, n = **1,644**. After-state = the ruling's
verdict where the contest produced a ruling, the decision's own otherwise.

```
                               AFTER correct       AFTER wrong     total
BEFORE correct                           828               128       956
BEFORE wrong                             173               515       688
total                                   1001               643      1644

  fixed   (BEFORE wrong -> AFTER correct)   b = 173
  broken  (BEFORE correct -> AFTER wrong)   c = 128
  NET                                    +45 cells
  discordant pairs                       301   (concordant 1343)
  EXACT TWO-SIDED McNEMAR                p = 0.0110865   SIGNIFICANT at alpha=0.05

  accuracy BEFORE       956/1644 58.2%  [55.7, 60.5]   (95% Wilson)
  accuracy AFTER        1001/1644 60.9%  [58.5, 63.2]   (95% Wilson)
```

**The pre-registered endpoint is positive and significant at α = 0.05.** Read it with §0
and with the stated confound in `PREREG.md`, both of which were written before the run.

## 4. The third paired arm, and the reference

Same cells, same third-party recourse judge, same corrected ruling line; what differs is
the question the challenger was asked.

| | n | fixed | broken | net | McNemar p |
|---|---|---|---|---|---|
| BEFORE → PROCEDURAL (**the endpoint**) | 1,644 | 173 | 128 | **+45** | **0.0110865** |
| BEFORE → NEUTRAL (`rerule-recontest`, reference) | 1,644 | 17 | 16 | +1 | 1 |
| NEUTRAL → PROCEDURAL (**the third arm**) | 1,644 | 183 | 139 | **+44** | **0.0164285** |
| BEFORE → PROSE (**post hoc, §7**) | 1,644 | 176 | 208 | **−32** | 0.11354 |

The neutral arm raised 54 objections on these cells and netted +1. The third-arm test says
the two recourse procedures reach different answers on the same decisions; it does not on
its own say which is right.

## 5. Secondary, descriptive — from `derivation.log` §(c)

Every rate is conditional on the step before it. None of them is the endpoint.

| | |
|---|---|
| objection raised | **1,148/1,644 = 69.8%** |
| declined | 496/1,644 = 30.2% |
| phantom (line REVERSE, prose RIGHT) | **0/1,148 = 0.0%** |
| genuine (line REVERSE, prose WRONG) | 1,146/1,148 = 99.8% |
| objections graded | 1,148 (every one) |
| **graded valid** | **881/1,148 = 76.7%** |
| — on a CORRECT decision | 473/633 = 74.7% |
| — on a WRONG decision | 408/515 = 79.2% |
| defects alleged / valid | 1,519 / 1,065 = 70.1% |
| **misattributed_quote** | **45/1,523 defects = 3.0%** |
| overturn on a WRONG decision | 173/515 = 33.6% |
| overturn on a CORRECT decision | 128/632 = 20.3% |
| **discrimination** | **+13.3 pts** |
| `ruling_line_mismatch` | 349/1,147 = 30.4% — **see §0** |

Under this variant a valid defect on a **correct** decision is a real finding and not a
false alarm: validity is a claim about the record, graded without opening `flaw.json`.

### Defects by type (read from the run tree — the only table that opens a cell directory)

| type | alleged | misattributed | graded valid | valid / alleged |
|---|---|---|---|---|
| contradiction | 307 | 23 | 163 | 53.1% |
| misstatement | 603 | 22 | 410 | 68.0% |
| omission | 613 | 0 | 489 | 79.8% |
| (type not recorded) | 0 | 0 | 3 | — |
| **TOTAL** | **1,523** | **45** | **1,065** | **69.9%** |

The grader ruled on 1,519 defects against 1,523 in the parsed challenge lists; the four-way
gap is defects the grader numbered but the parsed list does not contain, kept rather than
dropped (see `grading._grade_judgment`). **Omissions never misattribute by construction** —
the quote check does not apply to a defect that quotes nothing from the judgment.

### Challenger format: repairs and parse modes

| | |
|---|---|
| objections needing **1** format repair | **1,588 of 1,644 (96.6%)** |
| needing 0 | 56 |
| by shape | `label_not_at_line_start` 1,270; `no_public_label` 318 |
| parse modes | `salvaged_no_thinking` 1,587; `strict` 56; `salvaged_no_labels` 1 |
| recourse-judge repairs | 44 (`missing_decision_line`), on 1,147 rulings |
| **cells lost to it** | **0** |

**Every repaired objection is a second attempt written under the repair instruction, which
suppresses the private section** — so 1,587 of the 1,148 graded objections' texts were
written without a `Thinking:` block, and the first attempt's working was discarded. That is
a property of what was graded, not a cost in cells.

### The ruling's own structure (read from the run tree)

| | |
|---|---|
| rulings | 1,147, **all `prompt_form = "materiality"`** |
| prose shows a Step 1 **and** a Step 2 heading | **1,125/1,147 = 98.1%** |
| prose concludes "not real / not material / stands" | 437/1,147 = 38.1% |

## 6. The alarm split — what the ruling did against what the reader made of its prose

| ruling | reader said | n | mismatch? | substituted in §7? |
|---|---|---|---|---|
| OVERTURNED | CHANGED | 205 | no | no |
| OVERTURNED | STANDS | **82** | YES | YES |
| OVERTURNED | NEITHER | 14 | YES | no |
| upheld | CHANGED | **165** | YES | YES |
| upheld | NEITHER | 88 | YES | no |
| upheld | STANDS | 593 | no | no |
| | | **349 alarms** | | **247 substituted** |

In the raw `ruling_prose_conclusion` vocabulary the same rows read: upheld/SOUND 156 and
upheld/FLAWED 9 (= 165 upheld & CHANGED); overturned/FLAWED 79 and overturned/SOUND 3
(= 82 overturned & STANDS); NEITHER 88 + 14.

## 7. POST-HOC SENSITIVITY — not pre-registered

`derivation.log` §(f). **The rule, stated in the script before the numbers:** where the
materiality reader answered STANDS or CHANGED, take the prose's conclusion as the cell's
after-state; where it answered NEITHER, or the ruling is object-level, or there is no
ruling, keep the line.

| | pre-registered (the line) | post hoc (the prose) |
|---|---|---|
| fixed | 173 | 176 |
| broken | 128 | **208** |
| net | **+45** | **−32** |
| McNemar p | **0.0110865** | 0.11354 |
| accuracy after | 60.9% [58.5, 63.2] | 56.2% [53.8, 58.6] |

247 cells moved: 85 from wrong to correct, 162 from correct to wrong.

**The sign of the endpoint flips under this rule and the significance goes away.** It is
post hoc and it was chosen after the mismatch rate was seen. Section 3 is the endpoint.

What the hand check adds is that the reader is **not** the weak link — it is right about
what the prose says (§0) — but that the two groups it flips are not the same kind of thing.
The 165 upheld-and-CHANGED are the judge contradicting its own materiality rule, and
flipping them to overturns takes the judge's Step 2 at its word. The 82
overturned-and-STANDS are the judge *abandoning* the materiality rule and re-deciding the
item, and flipping them to upholds imposes a rule the judge did not follow. **Neither
direction is obviously the truth**, which is why this stays descriptive.

[`HANDCHECK-C-fixed-and-broken.md`](HANDCHECK-C-fixed-and-broken.md) puts a size on the
part of the endpoint that is line-vs-prose residual rather than judgement: in a 10 + 10
sample, **~3 of 10 broken cells and ~1 of 10 fixed** turn on a line that contradicts its
own prose. The other seven broken cells are coherent two-step rulings that are simply
**wrong on the merits** — the weak judge siding with the debater the dataset label says
lost.

## 7b. The hand checks

Three, by the planner, on 2026-08-28. They are the only thing standing between these
numbers and instruments nobody audited.

| | what was read | what it found |
|---|---|---|
| [A](HANDCHECK-A-objections-and-grades.md) | 20 objection + grade pairs, 10 valid / 10 invalid, seed 0 | **20/20 agree with the grader**, rejections for stated and right reasons; **0/20 quotations not in the judgment**, matching the run's 0.0% misattributed rate on this corpus |
| [B](HANDCHECK-B-rulings.md) | 40 rulings, weighted to alarms | two-step structure **20/20**; the reader right about the prose **12/12** and **8/8** on the two large alarm groups — so the 30.4% is the judge's coherence, not the instrument's error |
| [C](HANDCHECK-C-fixed-and-broken.md) | 10 fixed and 10 broken cells end to end | the line-vs-prose residual accounts for **~1 of 10 fixed and ~3 of 10 broken**; the other seven broken are coherent two-step rulings **wrong on the merits** |

Hand check A is what lets the 76.7% valid-objection rate and the 3.0% misattributed rate
be quoted. Hand check B is what §0 rests on. Hand check C is what says how much of the
endpoint is instrument and how much is a weak judge being wrong.

## 8. Per subset and label basis

`label_basis` is not pooled: `injected_pair`, `sentence_labels` and `final_answer` are three
different claims about what "flawed" means.

| subset | basis | n | raised | valid/obj | mis/def | fixed | broken | net | line mismatch |
|---|---|---|---|---|---|---|---|---|---|
| gpqa | injected_pair | 319 | 217 (68%) | 178/217 (82%) | 7/287 (2%) | 28 | 21 | **+7** | 87/217 (40%) |
| law | sentence_labels | 37 | 28 (76%) | 18/28 (64%) | 0/39 (0%) | 3 | 4 | −1 | 2/28 (7%) |
| lojban | sentence_labels | 117 | 85 (73%) | 69/85 (81%) | 2/107 (2%) | 5 | 6 | −1 | 16/84 (19%) |
| medqa | final_answer | 203 | 141 (69%) | 90/141 (64%) | 2/184 (1%) | 18 | 22 | **−4** | 60/141 (43%) |
| python800 | injected_pair | 637 | 436 (68%) | 339/436 (78%) | 27/593 (5%) | 61 | 43 | **+18** | 128/436 (29%) |
| surgery | sentence_labels | 196 | 142 (72%) | 114/142 (80%) | 3/176 (2%) | 28 | 19 | **+9** | 28/142 (20%) |
| theoremqa | injected_pair | 135 | 99 (73%) | 73/99 (74%) | 4/137 (3%) | 30 | 13 | **+17** | 28/99 (28%) |
| **POOLED** | | **1,644** | **1,148 (70%)** | **881/1,148 (77%)** | **45/1,523 (3%)** | **173** | **128** | **+45** | **349/1,147 (30%)** |

The net is positive in four subsets, negative in three, and the two largest positives are
python800 (+18) and theoremqa (+17). Per-subset McNemar p-values are in `derivation.log`
§(e) and are descriptive: the endpoint is the pooled test.

## 9. What is in this directory

| | |
|---|---|
| `PREREG.md` | the pre-registration, committed before the run, plus the two dated revisions and the instrument revision |
| `index.jsonl` | one row per decided cell, 1,644 rows — every table above |
| `metrics.json` | the harness's own analysis, including its caveats |
| `cells.jsonl`, `experiment.json`, `DONE.md` | the grid, the run's provenance (with the source tree's fingerprint), the driver's completion record |
| `derivation.log` | `judgment-debate-vs-alone.py` run against **this** committed index |
| `logs/stage-tails.md` | per-stage counts, spend, repair shapes, the failed cell |
| `transcripts/` | four cells copied whole — one fixed, one broken, one valid objection upheld, one decline — each with its `README.md`, both documents, and the challenge / grade / ruling / agreement records |
| `pilot-1/`, `pilot-2/` | the two 60-cell instrument checks, index and metrics only |
| `HANDCHECK-A-objections-and-grades.md` | 20 objection + grade pairs, 10 valid and 10 invalid: **20/20 agree with the grader**, and **0/20 carried a quotation not in the judgment** |
| `HANDCHECK-B-rulings.md` | 40 rulings, weighted to `ruling_line_mismatch` alarms: the two-step structure in **20/20**, and the reader right about the prose in **12/12** and **8/8** of the two large alarm groups |
| `HANDCHECK-C-fixed-and-broken.md` | 10 fixed and 10 broken cells end to end: the residual accounts for ~1 of 10 fixed and ~3 of 10 broken; the other seven broken are coherent rulings wrong on the merits |

**`pilot-1/`** is the first instrument check (2026-08-28, 60 cells, $1.3285): the old format
prompt and the **object-level** ruling. It is what showed the recourse judge overturning 35%
of correct decisions, and it is the baseline the materiality revision was argued from.

**`pilot-2/`** is the same 60 cells under **both** revisions (2026-08-28, $1.1483), and its
`ruling_agreement` readings were re-made by the adapted instrument. It is what showed
overturns falling (44.4% → 32.4%) and breakage of correct decisions falling most (9 → 4).
Two 60-cell runs at `challenger_temperature = 0.7` differ by sampling as well as by prompt;
neither pilot is a measurement.

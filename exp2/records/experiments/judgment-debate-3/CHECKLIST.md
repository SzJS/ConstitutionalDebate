# judgment-debate-3 — the checklist

Every number here is re-derivable from the files beside it: the three `arm-*/index.jsonl`
and `arm-*/metrics.json` in this directory, [`derivation.log`](derivation.log) (the output
of `records/derivations/judgment-debate-3.py` run against **these** committed indexes and
[`gates/jd3-main-gates.jsonl`](gates/jd3-main-gates.jsonl)), and
[`logs/stage-tails.md`](logs/stage-tails.md).

    cd exp2
    uv run python records/derivations/judgment-debate-3.py \
      --main        records/experiments/judgment-debate-3/arm-M0-M1/index.jsonl \
      --placeholder records/experiments/judgment-debate-3/arm-M2/index.jsonl \
      --gatekeeper  records/experiments/judgment-debate-3/arm-M4/index.jsonl \
      --gates       records/experiments/judgment-debate-3/gates/jd3-main-gates.jsonl \
      --specious    /nonexistent \
      --jd1             records/experiments/judgment-debate/index.jsonl \
      --jd2-mav         records/experiments/judgment-debate-2/arm-maverick-real/index.jsonl \
      --jd2-mini        records/experiments/judgment-debate-2/arm-mini-real/index.jsonl \
      --jd2-placeholder records/experiments/judgment-debate-2/arm-nano-placeholder/index.jsonl

**M3 has not landed.** Every M3 row below says **NOT RUN YET** and none of them may be
filled from a partial tree — see [`arm-M3/NOT-RUN-YET.md`](arm-M3/NOT-RUN-YET.md).

**Read §0 before any other number.**

---

## 0. THE THREE THINGS TO READ FIRST

### 0.1 The pre-registered endpoint is a NULL, and the descriptive beside it is not

P1 came out **−18 cells (110 fixed, 128 broken), p = 0.27045** — not significant at α = 0.05,
and negative. P2 came out **not separated** (−20, p = 0.2122). Neither is a finding *against*
recourse and neither is a finding *for* it; **they are two nulls**, and §1 is where they sit
with the three numbers that show it: 238 discordant pairs in P1, 232 in P2, and 12 cells
moved by the placeholder.

The number that explains them is **not** the net. Of the wrong decisions the audit
contested, it fixed **40.1%**; of the right decisions it contested, it broke **20.6%** — a
**+19.6-point** difference in the audit's favour. Those two rates are multiplied by two
populations that are **not the same size**: M0 is right on 73.7% of cells, so the audit met
622 right decisions and only 274 wrong ones. A procedure that is nearly twice as likely to
fix as to break still loses, at this base rate, by 18 cells. **The mechanism is arithmetic,
not a defect of the audit**, and §2 is the table.

### 0.2 M2's placement assertion fired — accounted for here, and it does not move P2

The placeholder arm's one invariant is that it stands on **exactly** the cells M1 contested.
The CLI checked it and printed:

    placeholder placement: 894 objections stand where outputs/experiments/jd3-main raised 896
      — DOES NOT MATCH.

**Accounted for cell by cell, which is what the warning demands before P2 is read.** The
placeholder was **written on all 896** cells — `arm-M2/index.jsonl` carries
`challenge_arm = "placeholder"` on 896 rows — and **two of them lost their ruling** to a
truncated recourse-judge reply (`gpqa-193-flawed`, `medqa-train_1133`; see
`logs/stage-tails.md`). So 896 placed, 894 ruled; the counter counts completed contests.

Both cells are **concordant in both arms**: in M1 and in M2 alike `final_correct ==
initially_correct` (true and false respectively). They enter no discordant pair in either
arm, so they contribute nothing to P2's 106/126 and nothing to P1's 110/128. **P2 is
readable.** The bound on the damage is 2 cells against a net of −20.

### 0.3 Everything under §5 is POST HOC

The three gate rows and the conditional-rate *table position* were decided on 2026-08-28
**after M1's preliminary numbers had been read** (876 cells: 65 fixed / 75 broken). M4 has an
amendment to `PREREG.md` written and committed before its first paid call; the mechanical
gate and the Haiku bound are descriptive recomputations and have no test to pass. None of
them is the endpoint, all of them carry the label wherever they print, and `derivation.log`
prints it four times in section (i) alone.

---

## 1. THE PRE-REGISTERED ENDPOINTS

`PREREG.md`, committed before M1's first paid call. Exact two-sided McNemar on the discordant
pairs, **α = 0.05**, one judge and one test each; P1 and P2 are different comparisons against
different arms and are **not** a Bonferroni family, which `PREREG.md` says before either arm
ran.

| | population | fixed | broken | net | discordant | p | verdict |
|---|---|---|---|---|---|---|---|
| **P1** — M1 after vs M0 before | 1,644 | 110 | 128 | **−18** | 238 | **0.27045** | not significant at α = 0.05 |
| **P2** — M1 after vs M2 after, paired on `cell_id` | 1,644 | 106 | 126 | **−20** | 232 | **0.212156** | **NOT SEPARATED** |
| **P3** — overturn on specious vs real, on the overlap | — | — | — | — | — | — | **NOT RUN YET** |

Accuracy: M0 **1,211/1,644 = 73.7%** [71.5, 75.7] → M1 **1,193/1,644 = 72.6%** [70.4, 74.7];
M2 **1,213/1,644 = 73.8%** [71.6, 75.9].

**What P2 says, in the words `PREREG.md` fixed before the run.** "The audit did it" means M1
beats M2; "a second look did it" means they do not differ. They do not differ. But read that
with §2's placeholder row beside it: against M0 the placeholder moved **12 cells in total**
(7 fixed, 5 broken, net +2) where the real audit moved **238** (110 fixed, 128 broken). The
two arms are not separated because **both are nulls**, not because the placeholder reproduced
the audit's movement.

**The three numbers that let a reader check that.** P1 has **238** discordant pairs, P2 has
**232** (106 + 126), and the placeholder moved **12** cells. P2's discordant set is therefore
almost exactly the audit's own movement — the cells where the audit changed something and the
placeholder did not — and not a set the placeholder created. A second look with no
information barely moves this judge at all; the audit moves it a great deal, in both
directions, and the two directions cancel.

---

## 2. THE HEADLINE DESCRIPTIVE — the two conditional rates

Denominator is the **contested** cells in both columns: a cell nobody objected to cannot be
fixed or broken by an objection, and leaving it in dilutes both rates by the decline rate.
Descriptive — no α, no test. Promoted to the first table on 2026-08-28 (§0.3).

| arm | contested | fixed \| wrong | broken \| right | difference |
|---|---|---|---|---|
| **M1** — the real audit | 896 | **110/274 = 40.1%** | **128/622 = 20.6%** | **+19.6 pts** |
| M2 — the placeholder | 896 | 7/274 = 2.6% | 5/622 = 0.8% | +1.8 pts |
| M3 — the specious auditor | — | — | — | **NOT RUN YET** |

**The denominator is the CONTESTED cells, in both columns, and the derivation now prints
this table exactly once.** The question is what an *objection* does to a decision, so a cell
that was objected to belongs in the denominator whether or not its ruling survived — one M1
cell lost its ruling to a truncation and is still in the 896 — and a cell nobody objected to
does not belong in it at all. Section (f) of `derivation.log` **repeats these two rates and
does not recompute them**; until 2026-08-28 it divided by the 895 ruled cells instead and
printed +19.5 beside this +19.6 for the same quantity, which read as the script disagreeing
with itself. `tests/test_derivations.py` pins the denominator on a fixture where the two
would differ.

**Context, and not a test** — `REFERENCE-RATES.md` §7. The one published pair measuring
anything like both rates is Garrett's *Judging Innocence* (2008): ordinary appeal and habeas
reversed **~14%** of convictions later proven wrong by DNA, "indistinguishable from the
background reversal rates of comparable convictions" (**~14%**) — a discrimination of
roughly **zero**. This procedure's **40.1% / 20.6%** discriminates far better than
deferential appeal and still loses cells, because the base rate of wrong decisions here
(26.3%) is far above the legal analogue's few percent and the rate at which it overturns
right decisions (20.6%) is far above appeal's (7–15%). Nothing in this phase is tested
against any number in that file, and the populations, the standards of review and the
meaning of "wrong" are all different.

---

## 3. M0 AGAINST THE SWEEP'S NANO JUDGMENT — descriptive, reported and NOT tested

The same 1,644 stored transcripts, judged twice. Read off one index (`verdict` and
`source_verdict`, written cell by cell by the `rejudge` stage).

| | Maverick FLAWED | Maverick SOUND | total |
|---|---|---|---|
| nano FLAWED | 634 | 343 | 977 |
| nano SOUND | 262 | 405 | 667 |
| **total** | 896 | 748 | **1,644** |

| | |
|---|---|
| verdicts agreeing | 1,039/1,644 = **63.2%** |
| accuracy, Maverick (M0) | **1,211/1,644 = 73.7%** [71.5, 75.7] |
| accuracy, nano (the sweep) | 956/1,644 = 58.2% [55.7, 60.5] |
| Maverick right where nano was wrong / wrong where nano was right | 430 / 175, net **+255** |
| exact McNemar | p = 9.88e-26 — **REPORTED, NOT TESTED** |
| FLAWED share | Maverick 54.5%, nano 59.4% |
| by label | flawed items 73.9% vs 64.9%; sound items **73.3% vs 48.4%** |
| judgments truncated or unparsed | **0 of 1,644** |

Maverick's whole advantage is on **sound** items, where nano called 51.6% of them flawed.
This is a different question from the one the phase tests and must not be read as the
endpoint; `HANDCHECK-M0-judgments.md` is the reading behind it (20 judgments; every one a
judgment *of the debate*; 15/20 correct in that sample).

---

## 4. THE FUNNEL AND THE INSTRUMENTS, per arm

| | M1 (real audit) | M2 (placeholder) | M3 |
|---|---|---|---|
| cells | 1,644 | 1,644 | NOT RUN YET |
| objection raised (`stance == contests`) | **896 = 54.5%** | 896 placed (by construction) | — |
| declined | 747 = 45.4% | — | — |
| `unclear` (no readable decision line) | 1 | — | — |
| rulings made | 895 | 894 | — |
| graded valid | **649/896 = 72.4%** | never graded, by design | — |
| defects alleged | 1,101 | 896 (one constant) | — |
| **misattributed quotes** | **21/1,101 = 1.9%** | 0/896 | — |
| grader summary vs its own defect lines | **0/896** | — | — |
| **phantom contests** | **1/896 = 0.1%** | 0 | — |
| `ruling_line_mismatch`, strict | **10/863 = 1.2%** | 1/880 = 0.1% | — |
| `ruling_line_mismatch`, conservative | **42/895 = 4.7%** | 15/894 = 1.7% | — |
| overturn on wrong / right | 40.1% / 20.6% | 2.6% / 0.8% | — |

Three of those deserve a sentence.

**The instrument residual collapsed.** The first run's nano rulings were **21.5% strict /
30.4% conservative**; Maverick's are **1.2% / 4.7%**. That is the same materiality prompt and
the same Haiku reader, with a judge at the challenger's level rather than below it, and it
removes the largest caveat the previous run carried. `HANDCHECK-B-rulings.md` read 20
rulings, 12 of them alarms, and found the two-step structure in 20/20 and the alarms almost
all **NEITHER** readings on long Step-2 prose rather than contradictions.

**The audit is clean.** 1.9% misattributed quotations (the nano slice ran 34 of 66), one
phantom in 896, and `HANDCHECK-A-objections-and-grades.md` agreeing with the grader **20/20**
on a 10-valid / 10-invalid sample. Whatever is happening to the net, it is not junk
objections.

**A valid defect on a correct decision is a real finding, not a false alarm.** Judgment-mode
validity is a claim about the record, graded with `flaw.json` never opened, so the rate is
**split** by `initially_correct` rather than conditioned on it.

---

## 5. THE THREE GATES — **POST HOC, added after M1 was seen**

"What if not every objection is heard?" Under every row **the ruling is unchanged**: the
after-state is the ruling's outcome where the gate admitted the objection and the decision's
own verdict where it refused. No ruling was re-made — M4's tree carries M1's rulings byte for
byte, and the offline harness asserts that byte for byte.

| gate | what it admits on | fixed | broken | net | p | admit \| wrong | admit \| right | **gate discrimination** |
|---|---|---|---|---|---|---|---|---|
| **MECHANICAL** (no model) | every quotation verbatim in the document it is attributed to | 77 | 81 | **−4** | 0.8115 | 201/274 = 73.4% | 473/622 = 76.0% | **−2.7 pts** |
| **M4** — `openai/gpt-4.1-mini` | at least one alleged defect is REAL | 90 | 104 | **−14** | 0.3507 | 217/274 = 79.2% | 504/622 = 81.0% | **−1.8 pts** |
| **HAIKU-VALID** (a BOUND, not a process) | the grader called the objection valid | 92 | 90 | **+2** | 0.9409 | 210/274 = 76.6% | 439/622 = 70.6% | +6.1 pts |

Conditional rates under each: mechanical 28.1% / 13.0% (+15.1); M4 32.8% / 16.7% (+16.1);
Haiku 33.6% / 14.5% (+19.1). All three are worse on the difference than the ungated audit's
+19.6, which is the point: **every gate here throws away good objections faster than it
throws away bad ones, or at best breaks even.**

**The gate discrimination column is the one to read.** A gate that admits everything scores 0
and changes nothing; a gate that admits at random scores near 0 and shrinks the net from both
ends. Two of the three score **negative** — they admit objections to *right* decisions
slightly more often than objections to *wrong* ones. The only positive row is the one that
is not a process: the Haiku grader is **stronger than the judge it would be gating**, so
counting only its `valid` objections imports a better reader into the decision path — the
confound that stopped the `judgment-debate-2` chain, arriving by a side door — and even it
buys **+2 cells, p = 0.94**.

**Why gpt-4.1-mini.** It is the other in-band pass of the judge-selection rule of
`../judgment-debate-2/PREREG.md` (index 14 with reasoning off, delta 0 from the challenger's
level) and a different family from Maverick, so M4 is neither the judge marking its own
homework nor a stronger reader smuggled in. Prompt smoked on six cells first
(`gates/SMOKE-admissibility-6-cells.txt`, $0.0151, 6/6 `strict`, 0 repairs, 8/8 per-defect
agreement with the grader). M4's own admissibility calls: 896, **$2.2585**, 0 non-2xx, 0
format repairs at scale.

**Why the mechanical gate is not vacuous.** It admitted **674/896 = 75.2%**. Of the 1,101
defects, 21 (1.9%) fail the pre-registered judgment-side quote check and **233 (21.2%)** fail
the post-hoc record-side one — of which about a quarter are the challenger quoting the *flaw
definition from its own instructions* as if it were the record, which
`HANDCHECK-A-objections-and-grades.md` independently caught three times in twenty. Details
and per-type rates: `gates/jd3-main-gates.log`.

**Read `transcripts/gate-refusal__python800-p03959…` beside `transcripts/broken__gpqa-120-sound…`.**
The two objections are the same argument; the gate refused both; one was a fix and one was a
break. That is a discrimination of −1.8 pts from the inside.

---

## 6. PER-SUBSET AND PER-`label_basis` NETS — descriptive, never pooled

`DESIGN.md`'s non-pooling rule: `injected_pair`, `sentence_labels` and `final_answer` are
three different claims about what "flawed" means, and medqa's `final_answer` basis calls a
badly-reasoned solution sound whenever it reached the right answer. **Not summed.**

| subset | n | fixed | broken | net |
|---|---|---|---|---|
| gpqa | 319 | 21 | 28 | **−7** |
| law | 37 | 3 | 2 | +1 |
| lojban | 117 | 7 | 6 | +1 |
| medqa | 203 | 25 | 20 | **+5** |
| python800 | 637 | 37 | 49 | **−12** |
| surgery | 196 | 13 | 17 | −4 |
| theoremqa | 135 | 4 | 6 | −2 |

| `label_basis` | n | fixed | broken | net |
|---|---|---|---|---|
| final_answer | 203 | 25 | 20 | +5 |
| injected_pair | 1,091 | 62 | 83 | **−21** |
| sentence_labels | 350 | 23 | 25 | −2 |

python800 is 637 of 1,644 cells and carries two thirds of the loss; the **python800 phrasing
question** carried forward from §3u is still open and still unanswered.

---

## 7. THE POST-HOC PROSE-WINS SENSITIVITY — and this time it barely moves

Section (h) of `derivation.log` recomputes every arm's 2×2 with the materiality reader's
reading of each ruling's **prose** substituted for the ruling's own **line**, wherever that
reader answered STANDS or CHANGED.

| arm | net (line) | net (prose) | shift |
|---|---|---|---|
| M1 | **−18** | −14 | +4 |
| M2 | +2 | +1 | −1 |

On the previous run this sensitivity turned **+45 into −32**. Here it moves the endpoint by
**four cells**, and that is a direct consequence of §4: with a 1.2% strict mismatch rate
there is almost nothing left for it to flip. It is still post hoc and it is still only as
good as a Haiku reader; it is reported because the previous run's version of it is in the
record.

---

## 8. THE jd2 PRELUDE — a record of an instrument, not an effect

Recomputed by the same script from each arm's own committed index.

| arm | n | fixed | broken | net | p |
|---|---|---|---|---|---|
| `judgment-debate` — nano judged, flash audited, **nano** ruled | 1,644 | 173 | 128 | **+45** | 0.01109 |
| jd2 A-mav — nano's judgments, re-ruled by **Maverick** | 1,644 | 237 | 113 | **+124** | 3.06e-11 |
| jd2 A-mini — nano's judgments, re-ruled by **gpt-4.1-mini** | 1,644 | 233 | 119 | **+114** | 1.24e-09 |
| jd2 B — nano's placeholder second look, nano ruled | 1,644 | 69 | 49 | +20 | 0.0798 |

**These are not comparable with §1.** Each row's before-state is *nano's* judgment of the
sweep's debates; this phase's before-state is Maverick's reading of the same transcripts, and
Maverick is right on 73.7% of them against nano's 58.2%. The +124 and +114 are what a
**stronger recourse judge** does to a **weaker judge's** judgments — which is why the chain
was stopped (`outputs/jd2-STOPPED-by-user.md`) and why this phase exists.

Put beside each other: with the asymmetry, +124. Without it, **−18**.

---

## 9. WHAT WAS NOT DONE, AND WHAT IS STILL OWED

- **M3, the specious control — NOT RUN YET.** It is the arm that would say how much of M1's
  movement needs a real defect at all, and P2's null makes it more important rather than
  less.
- **No `single` or `self_critique`.** Only a debate publishes a judgment that is a document
  other than the decision, so the procedure is undefined there and nothing here speaks to a
  between-condition comparison.
- **The same-model property is the design and is unrepaired.** The model that judged the
  debate ruled on the appeal against its own judgment. M2 bounds what it does with *no*
  information; M3 would bound what it does with *wrong* information; M4 changes the gate, not
  the ruler.
- **One challenger, one judge, one corpus**, and the challenger was chosen after a
  pre-registered rule that picked nobody (`../pick-auditor/DECISION.md`).
- **The python800 phrasing** (§6, and §3u), and the **`weak_alone` arm**.

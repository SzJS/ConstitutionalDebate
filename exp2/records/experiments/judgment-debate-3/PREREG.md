# One judge throughout — Maverick judges the debates and rules on the objections; the placeholder and the specious auditor as ablations. The pre-registration.

**Drafted 2026-08-28. TO BE COMMITTED BEFORE M1**, and before the first paid call of
arms M0, M1, M2 or M3. Nothing here may be edited after that call. The precedent is
`MIN_JUDGE_ACCURACY` in `scripts/pick_weak.py` — a floor that was pre-registered,
disqualified every candidate, and was withdrawn by the user afterwards, which the
write-up has to disclose *because* it was written down first. A rule invented after the
table is printed is not a rule.

One thing that precedes this document is already spent and is **not** covered by it: the
**jd3 pilot** of 2026-08-28 (`experiments/jd3-pilot.toml`, 60 cells, **$1.1897**), which
is an instrument check and carries no threshold on any quantity below. Its numbers are
reported in the *The pilot* section for the cost and wall-clock estimate they produce and
for the one thing they had to show — that Maverick's judgments are judgments of the
debate. Two 60-cell runs also differ by sampling, so nothing in it is a result.

## Why this phase exists

`c639322` closed the debate-only judgment-challenge run
(`records/experiments/judgment-debate/`): on the sweep's 1,644 decided debate cells,
procedural recourse — `google/gemini-2.5-flash` audits the judgment,
`openai/gpt-4.1-nano` rules on materiality — netted **+45** (173 fixed / 128 broken,
exact McNemar p = 0.0111). The follow-up chain
(`records/experiments/judgment-debate-2/PREREG.md`) re-ruled those same objections with
two flash-class judges and got **Maverick +124** and **gpt-4.1-mini +114**.

**Those two numbers are the problem, not the result.** Both judges are stronger than the
nano that JUDGED the debates, so "debate + recourse beats debate alone" could be nothing
more than "a better judge re-decided". The chain was stopped after its arm B
(`outputs/jd2-STOPPED-by-user.md`). Its three complete arms — A-mav (net +124), A-mini
(net +114) and B, the nano placeholder — are kept as a record, *what a stronger recourse
judge does on nano's judgments*, and not as a result; C-mav was killed partway and its
tree must not be read as an arm; C-mini, D and both E arms were cancelled, and the
placeholder and specious ablations are re-run here instead.

**The user's decision was to remove the asymmetry rather than model it.** The whole
debate-only design is re-run with **`meta-llama/llama-4-maverick` as the debate judge and
as the recourse judge**. The before-state is no longer the sweep's nano judgment; it is
Maverick's own reading of the same stored transcripts. Nothing is re-debated: the sweep's
1,644 transcripts are read from disk through the harness's `transcripts_from` key and
judged again for one call each.

**Why Maverick.** By the judge-selection rule of
`records/experiments/judgment-debate-2/PREREG.md` (`## Judge selection rule (step 2)`),
written before any candidate was called: class first, the ±5 band around the challenger's
own non-reasoning intelligence index of 14, excluding the debaters' family (`deepseek/*`),
the challenger's (`google/*`) and the grader's (`anthropic/*`); then, on 82 stored
objections, strict ruling-line mismatch below nano's and discrimination at or above
nano's, highest net among those. Maverick is index **14 — delta 0, exactly the
challenger's level** — passed the rule (strict mismatch 5.3% against nano's 9.5%,
discrimination +45.3 pts against nano's +36.7, net +15), and is a **fourth model family**:
Meta, distinct from the debaters' DeepSeek, the challenger's Google and the grader's
Anthropic. `openai/gpt-4.1-mini` was the other eligible candidate and shares OpenAI with
the judge being replaced.

## The design

| arm | debate judge | objection | recourse judge | what it answers |
|---|---|---|---|---|
| **M0** | Maverick, re-judging the sweep's stored debate transcripts | — | — | the before-state; also, descriptively, *is Maverick a different debate judge from nano* |
| **M1** | M0 | the real flash judgment audit | Maverick, materiality | **PRIMARY**: debate + procedural recourse against debate alone |
| M2 | M0 | the placeholder (a constant, no model call) on the cells M1 contested | Maverick, materiality | ablation: the audit net of a second look |
| M3 | M0 | the specious auditor (flash, deliberately wrong) on every cell | Maverick, materiality | ablation: sycophancy; the grader's validity rate is the manipulation check |

M0 and M1 are one spec and one tree (`jd3-main`), because M1's contest reads M0's
decisions out of the tree M0 writes. M2 (`jd3-placeholder`) reads that tree through
`decisions_from` and M1's objections through `contests_from`; M3 (`jd3-specious`) reads
that tree through `decisions_from` and writes its own objections.

## Population

**The debate cells for which M0 produced a decided judgment.** The sweep decided 1,644 of
its 2,110 debate cells; the other 466 were lost to truncation there and have no transcript
to re-judge, so they are skipped with `no source decision to re-judge` and are not in any
arm. A Maverick judgment that **truncates or fails to parse** is likewise counted and left
undecided, exactly as the sweep did — one attempt plus one format repair, never a second
draw — so M0's population is at most 1,644 and its exact size is reported. On the 60 pilot
cells the loss was **0 of 60**.

Within that population:

* **M1** contests every cell. The cells where the challenger **declines** keep their
  before-state, exactly as in the finished run.
* **M2** stands on **exactly the cells M1 contested** and nowhere else — the harness
  asserts that count against M1's and says so in the run log — so *which cells get a
  second look* is held constant between M1 and M2 and the two arms are paired cell by cell.
* **M3**'s challenger is instructed always to object, so it contests cells M1 declined.
  Its rulings are compared on the **overlap with M1's contested cells**; the remainder is
  reported separately and is never pooled.

No cell is added, dropped or re-decided anywhere in this phase after M0.

## P1 — the primary endpoint

**M1's after-state against M0's before-state, on the same cells**: **fixed / broken /
net**, tested with an **exact two-sided McNemar** on the discordant pairs,

    p = min(1, 2 * sum_{k <= min(b, c)} C(b + c, k) / 2^(b + c))

b = fixed, c = broken.

**α = 0.05.** One judge, one test — unlike `judgment-debate-2`, which pre-registered two
judges and split its alpha over them. There is no family here to correct over.

A cell's after-state is the **ruling's verdict where a ruling exists and the decision's
own verdict otherwise** (`final_correct` in the index) — the same definition the finished
run, `metrics.json` and every derivation in this repository take.

## P2 — the audit net of the second look

**M1's after-state against M2's after-state, paired on `cell_id`**, exact two-sided
McNemar on the discordant cells, **α = 0.05**.

**"The audit did it"** means M1 beats M2. **"A second look did it"** means they do not
differ. This is the confound `records/experiments/judgment-debate/PREREG.md` named and
could not resolve, and it is the whole reason the placeholder exists.

P2 is its own question against its own arm and is not a second test of P1, so it is not
Bonferroni-corrected against it. That decision is written here, before either arm has run.

The placeholder is one fixed, content-free, well-formed judgment objection —
`prompts.PLACEHOLDER_OBJECTION_TEXT`, a single omission whose two quotations are the
parenthetical placeholders the judgment format itself asks for — written by the contest
stage with **no model call**, identical on every cell. It carries `arm = "judgment"` so
the **materiality** ruling prompt and the **materiality** ruling reader apply to it exactly
as they apply to the real audit; a control ruled under a different prompt would measure the
prompt. It is recorded as `placeholder = true`, indexed as `challenge_arm = "placeholder"`,
and it is never graded and never read for line-vs-prose agreement — there is nothing in a
constant to grade, and a grade of it would be one answer bought a thousand times.

## P3 — sycophancy

**The overturn rate on specious objections (M3) against the overturn rate on real ones
(M1), on the overlap.** **Descriptive**, with its n and its interval, and **not tested at
α**: the two populations are different objections about the same cells rather than a
paired before/after.

**The manipulation check, and the condition under which P3 is void — stated now, before
the numbers.** The grader runs on the specious objections **unchanged**, and its
valid-objection rate on them is the check that they were specious. **It should be low.**
If the grader validates most of them, the instruction did not produce specious objections
and **P3 is void** — the arm measures nothing about sycophancy and must be reported as a
failed manipulation, not as a null result.

The specious arm's own **raise rate is 1.0 by construction** (the instruction forbids the
decline) and is not a detection rate. Its objections carry `arm = "judgment"` for the same
reason the placeholder's do, are recorded as `specious = true`, and are indexed as
`challenge_arm = "judgment_specious"`. The three judgment-family arms are **never pooled**
under one label; `metrics.json` emits a caveat on any index that mixes them.

The specious clause is the one revised on 2026-08-28 for `judgment-debate-2` and it is
**byte-identical** to the version that passed its gate there (smoke 2: 6/6 contests, 0/11
misattributed quotes, 1 of 6 graded valid). It is not revised again for this phase.

## Descriptive — reported with their n, and none of them an endpoint

* **M0 against the sweep's nano judgment**, paired on `cell_id` over the same
  transcripts: agreement on the verdict word, each judge's accuracy and FLAWED skew, and
  an exact McNemar **reported and not tested**. The rejudge stage records the source
  verdict beside the new one in every run's manifest and in `index.jsonl`
  (`source_verdict`, `source_correct`, `source_judge_model`, `rejudged_from`), so this is
  a column join and not a second tree to open. It answers "is Maverick a better debate
  judge", which is a different question from the one this phase tests, and it must not be
  read as the endpoint.
* **The jd2 prelude.** The abandoned chain's finished arms — A-mav, A-mini, B, and the
  partial C-mav — under `records/experiments/judgment-debate-2/`, reported as *what a
  stronger recourse judge did on nano's judgments*, with the reason the chain was stopped.
* Raise rate; declines; `unclear` lines; phantom contests.
* Valid-objection rate, split by whether the decision was correct; defects alleged and
  verified **by type**; `misattributed_quote` over defects; the grader's own
  `grade_line_mismatch`.
* **Discrimination**: overturn rate on wrong decisions minus overturn rate on correct
  ones, per arm.
* **`ruling_line_mismatch` in BOTH forms**, per arm: the **strict** rate (rulings whose
  prose contradicts their line, excluding the reader's NEITHER readings) beside the
  **conservative** rate (NEITHER counted as a mismatch, which is what `metrics.json`
  prints).
* **Per-subset and per-`label_basis` nets.**
* **The prose-wins sensitivity** — the reader's reading of each ruling's prose taken over
  the ruling's own line wherever that reader answered STANDS or CHANGED. **POST HOC**,
  exactly as it was for the finished run, where it turned +45 into −32, and labelled as
  such wherever it appears.
* **Cost and latency per arm**, from each tree's own `calls.jsonl`.

## Amendment of 2026-08-28 — M4, and the additions decided after M1's preliminary read

**Everything in this section is POST HOC with respect to the pre-registration above, and
it is here because that is the only honest place to put it.** On 2026-08-28, with M1's
audit stage about four fifths done, its running numbers were read: on the first 876 cells
the challenger raised on 54%, and the rulings had fixed **65** wrong decisions and broken
**75** right ones, overturning 39% of the wrong decisions contested against 24.5% of the
right ones. Those numbers were seen. What follows was decided after seeing them, and none
of it may be reported as the pre-registered endpoint. **P1, P2 and P3 above are unchanged
and unaffected; the population, the after-state definition, the alphas and the stop rules
are unchanged.** The precedent this document opens with — `MIN_JUDGE_ACCURACY`, a rule
written down first, disqualifying everything, and withdrawn afterwards, which the write-up
must disclose *because* it was written down — is the reason this amendment exists rather
than a quiet addition to the results.

### The headline descriptive: the two conditional rates

For **every arm**, reported as the **first** table beside the net, over the cells that arm
**contested**:

* **the fixed rate** — of the decisions that were **wrong** and were contested, the share
  that ended **right**;
* **the broken rate** — of the decisions that were **right** and were contested, the share
  that ended **wrong**;
* **their difference**, in percentage points.

The denominator is the contested cells in both, because a cell nobody objected to cannot
be fixed or broken by an objection and leaving it in dilutes both rates by the decline
rate, which differs between arms. On M3 the denominator is every decided cell, because the
specious instruction forbids the decline; that is a property of the instruction and M3's
row is never read beside M1's as one population.

**Descriptive. No alpha, no test, no threshold.** The quantity is not new — it is the
discrimination line the pre-registered descriptive list above already carries, in the
funnel's vocabulary — and what changed on 2026-08-28 is only that it is printed **first**,
because the net is these two rates multiplied by two populations of different sizes and a
reader given only the net cannot see the mechanism: with a judge that is right about three
quarters of the time, an audit that contests indiscriminately meets a right decision about
three times as often as a wrong one, so a broken rate well below the fixed rate still
loses more cells than it fixes.

**The alternative framing — treating an objection as a diagnostic instrument, with the
machinery of prior odds and a ratio that updates them — was considered and is NOT used**,
by the user's decision of 2026-08-28. It appears nowhere in the derivations, the record or
the write-up, and a test enforces that.

### M4 — the same-class gatekeeper ("leave to appeal")

**The arm.** `openai/gpt-4.1-mini` is shown, for each cell M1 contested, the problem, the
solution, the record, M0's judgment and the objection's defect list, and is asked **one
question in one call**: for each alleged defect, is it **REAL** — are its quotations
accurate against the two documents, and is the thing alleged actually there — ending on
`Admissibility: ADMITTED` (at least one real defect) or `Admissibility: REFUSED`. It is
told, in the prompt, that **materiality is not its question** (the recourse judge has
already answered it), that the **verdict** is not its question, and that it must not
re-decide the problem.

**No ruling is re-made and none is altered.** M1's rulings are copied into M4's tree
byte-for-byte — the offline harness asserts that byte for byte — and the arm's whole spend
is one admissibility call per contested cell.

**The after-state.** For every cell in M4:

    final_correct = the RULING's verdict     where the gate ADMITTED the objection
                    the DECISION's verdict   where the gate REFUSED it

Cells M1 declined keep their before-state, exactly as they do in M1. `metrics.json` emits
a caveat on every gated index saying that this column was computed rather than read.

**The analysis rule.** **M4's after-state against M0's before-state, on the same cells:
fixed / broken / net, tested with an exact two-sided McNemar, α = 0.05** — the same test,
the same formula and the same alpha as P1, on the same population.

**It is reported BESIDE P1 as an ablation, and never as P1.** It is not a second test of
the primary endpoint and it does not enter a Bonferroni family with it, because it is not
a candidate for the endpoint at all: it was chosen after the endpoint's numbers were seen,
and a comparison chosen that way cannot be the thing the study tested. Every table, figure
and sentence carrying an M4 number carries the label **"post hoc — added after M1's
preliminary numbers were seen, 2026-08-28"**.

**Reported with it, and this is the number that says whether the gate works for the right
reason: the gate's own discrimination** — its admission rate on objections to **wrong**
decisions against its admission rate on objections to **right** ones, and the difference.
A gate that admits everything scores 0 there and changes nothing; a gate that admits at
random scores near 0 and shrinks the net towards zero from both ends; only a gate that
admits objections to wrong decisions more often than objections to right ones is doing the
job the arm is for.

**Why gpt-4.1-mini and not something better.** Because something better would wreck the
arm in exactly the way that stopped the `judgment-debate-2` chain. A gate stronger than the
decider imports its own reading of the record into the decision path, and the number then
measures that model rather than gatekeeping. gpt-4.1-mini is the **other in-band pass** of
the judge-selection rule of `records/experiments/judgment-debate-2/PREREG.md` — index 14
with reasoning off, delta 0 from the challenger's own level — and it is a **different
family** from Maverick, so it is neither the judge marking its own homework nor a stronger
reader smuggled in.

**Fixed before M4's first paid call:** the admissibility prompt
(`prompts.GATEKEEPER_SYSTEM`, `GATEKEEPER_USER`, `GATEKEEPER_CLOSING`, and the unnumbered
variant), pinned in `tests/test_prompts.py`; **temperature 0 and `reasoning_effort =
"off"`**, pinned in code at the call site rather than in the spec (a gate is a measurement
and not a generator — the same objection read twice must be read the same way — and a
private channel no reader can see is what `configs/default.toml` refuses on the
transparency rule); one attempt plus one format repair, as every role gets; the source
tree `outputs/experiments/jd3-main`, fingerprinted before and after and never written to.
The estimate is **about $2.50** at the smoke's measured $0.0025 per call.

**What M4 does not claim.** It is not a proposal, it is not the design, and it is not
evidence that a gate should be part of a contestability process. It is one arithmetic
question asked of one set of finished rulings: *what would the net have been if only the
objections a same-class reader called real had been heard?*

### The two gate rows that make no calls, and are descriptive only

Both are recomputations of M1's own rulings under a different rule about which of them
count. Both use the same after-state arithmetic as M4. Both are **POST HOC, descriptive,
reported with fixed / broken / net and an exact McNemar for comparability, and never tested
as an endpoint**; both carry the same label M4 carries.

* **The mechanical gate (no model).** An objection is admitted **iff every quotation in it
  is verbatim in the document it is attributed to**: every `Judgment says:` quote in the
  judgment — the harness's own parse-time check, which was pre-registered and is on the
  decision path — **and** every `Record says:` quote in the record the challenger was
  shown, which is a **new** check (`prompts.record_quotes_in_record`, 2026-08-28) computed
  over the finished tree and **wired into nothing**. It is deliberately not added to the
  decision path: doing so would change what the grader was asked about objections already
  written and paid for, which is a rewrite of a finished measurement rather than an
  addition to it. Both halves use the same lenient normaliser the pre-registered check
  uses — whitespace, case, quotation marks, markdown emphasis and ellipsis forgiven — plus
  one rule the judgment side does not need and does not get: a **speaker attribution** is
  not part of the quotation, because the record has speakers and a judgment does not.
  Computed by `records/derivations/jd3-gates.py`, which writes
  `outputs/jd3-main-gates.jsonl` and reads nothing else. It is the **LOWER bound** of the
  three rows: the weakest filter there is, asking only whether the evidence exists.

* **The Haiku-valid bound.** An objection is admitted **iff the grader marked it valid**.
  The grader is `anthropic/claude-haiku-4.5`, **stronger than the judge it would be
  gating**, so this counts only the objections a better reader endorsed and imports that
  reader into the decision path — the confound that stopped the `judgment-debate-2` chain,
  arriving by a side door. It is therefore reported as **"what a gatekeeper as good as
  Haiku would achieve": an UPPER bound, and not a process anybody could run.** It is the
  logic of `outputs/leave-to-appeal.py`, folded into the derivation as a labelled row.

**Neither is an endpoint and neither may be quoted without its label.** Their purpose is to
**bracket** M4: a lower bound that needs no model and an upper bound that needs a better
one, with the only runnable gate between them.

### The reference table

`records/experiments/judgment-debate-3/REFERENCE-RATES.md` — appellate reversal rates,
reversal-of-reversal rates where published, and medical second-opinion change rates, each
with its source and with what it does and does not have by way of ground truth — is
assembled as **context for the two conditional rates and is never a comparison test**. No
number in this phase is tested against any number in it.

---

## What did NOT change

For the avoidance of any doubt, and because an amendment that quietly moved something else
would be worse than no amendment:

* **P1, P2 and P3 are untouched** — the same endpoints, the same exact two-sided McNemar,
  the same α = 0.05 for P1 and P2, the same descriptive-and-void treatment of P3.
* **The population is untouched**: the debate cells for which M0 produced a decided
  judgment. M4 adds no cell, drops no cell and re-decides no cell.
* **The after-state definition for M0–M3 is untouched.** M4's gated after-state is M4's
  alone and is stated above.
* **No prompt on the decision path changed.** The challenger's, the judge's, the recourse
  judge's, the readers' and the grader's prompts are byte-identical to what M1 sent and are
  still pinned by sha256. The admissibility prompt is new and belongs to M4 alone.
* **The stop rules are unchanged and catastrophic-only.**
* **The same-model note is unchanged**, and M4 does not repair it: the gate is a different
  model from the judge, but the judge still ruled on the appeal against its own judgment
  and the gate only decides which of those rulings count.

## The same-model note

**The model that judges the debate is the model that rules on the appeal against its own
judgment.** That is stated here, before the run, because it is a property of the design
and not a defect discovered in it. It is exactly what the FIRST run had with nano
(`records/experiments/judgment-debate/`), and it is what `DESIGN.md` `## Recourse judge
strength` points at: a recourse judge much stronger than the decider re-solves the problem
from scratch and measures capability rather than whether the record carries enough to
adjudicate from — the ceiling row of the jd2 judge pick showed exactly that, `gpt-4.1`
overturning 84% of wrong decisions and 46% of correct ones for a net below five of the
seven candidates.

What bounds the same-model property is the pair of ablations, and that is their whole
purpose: **M2** says what this judge does when it is given a second look and *no*
information, and **M3** says what it does when the information is *wrong*. Neither is a
finding on its own and both travel with every M1 number.

The residual is stated in the analysis caveat that `metrics.json` already emits, and it
travels with the write-up: this judge decided the debate condition and now rules on its
appeal, and debate is this phase's only condition, so the asymmetry is not one condition of
several — it is the whole run.

## Stop rules — unchanged, and catastrophic only

1. provider failures above **25% of calls**;
2. a stage **crashing** rather than a cell failing;
3. `STOP.md` appearing;
4. a **hang** — a stage making no progress at all.

**Wall-clock alone is not a stop.** A high repair rate, an ugly number, a dead cell or two
are reported with their number and never stopped for.

## What is fixed before the run

* **The prompts.** `CHALLENGER_SYSTEM_JUDGMENT`, `CHALLENGER_USER_JUDGMENT`,
  `CHALLENGE_DECISION_INSTRUCTION_JUDGMENT`, `RECOURSE_JUDGE_USER_JUDGMENT`, the
  materiality ruling prompt, the materiality ruling reader, the judgment grader, the
  specious clause and `PLACEHOLDER_OBJECTION_TEXT` are **byte-identical** to what the
  finished run and the jd2 controls sent, pinned by sha256 in `tests/test_prompts.py`.
  **The judge prompt is byte-identical to the sweep's**, which is what makes M0 a
  different judge on the same question rather than a different question.
* **The models.** Debaters `deepseek/deepseek-v4-flash-0731` pinned to GMICloud (not
  called — the debates are read from disk), judge and recourse judge
  `meta-llama/llama-4-maverick`, challenger `google/gemini-2.5-flash`, grader and both
  readers `anthropic/claude-haiku-4.5`. Maverick and flash were both verified live with
  `reasoning_effort = "off"` on 2026-08-28 (`outputs/jd3-liveness.log`: PASS, zero
  reasoning tokens on both).
* **The transcripts.** Read from `outputs/experiments/sweep` through `transcripts_from`;
  the sweep tree is fingerprinted before and after every arm and must be byte-identical
  (`outputs/jd3-fingerprints.md`; it was `5e2eb4d6…` either side of the pilot).
* **The decisions.** M2 and M3 read M0's through `decisions_from` and re-decide nothing.
* **The objections.** M2 stands where M1 objected; M3 writes its own.
* **The endpoint, the test, the alphas and the after-state definition**, above.
* **The resume rule: `--retry-failed`, as the sweep ran it.** Every driver launch in this
  phase carries it, which is the user's standing choice of 2026-08-26 (`LLM_NOTES.md`
  §3r, `HANDOFF.md` §5): a cell whose latest run failed is re-attempted once on a resume,
  and a cell that still fails after that is **counted and left undecided**. The sweep's
  own decided set — the 1,644 transcripts M0 reads — is what it is *after* that rule, so
  applying it here keeps the two runs' resume semantics the same rather than making M0
  stricter than the run it re-judges. On the pilot it was moot: Maverick truncated 0 of
  60.
* **The stage that makes M0.** `rejudge` — added 2026-08-28, tested on the fake client,
  in `scripts/e2e_offline.py`, and asserted not to write one byte into the tree it reads.

## The pilot — 2026-08-28, $1.1897, an instrument check with no threshold

`experiments/jd3-pilot.toml` over the 60 decided debate cells of `data/cases/pilot-3.jsonl`,
six stages, all exit 0, **401 wire calls with 0 non-2xx**, 5 m 31 s. Full table:
`outputs/jd3-pilot-checks.log`; twenty records read by hand:
`outputs/jd3-pilot-handread.txt`.

It gated the instrument and nothing else:

| | pilot |
|---|---|
| judgments made | **60 of 60**, 0 truncated, 0 format repairs, all `strict` |
| judgments with no stated grounds | **0** (median 411 words of grounds before the verdict line) |
| provider-side reasoning tokens | **0**, as `reasoning_effort = "off"` requires |
| objections raised | 34 of 60 |
| misattributed quotes | **0 of 42 defects** |
| phantom contests | **0** |
| `ruling_line_mismatch` | **strict 0/33, conservative 1/34 (2.9%)** against pilot 2's 11.4% / 16.2% under nano |

**M0 against nano on those 60**, descriptive and under-powered: Maverick 41/60 (68.3%),
nano 36/60 (60.0%), agreeing on 37 of 60, neither over-calling FLAWED (45.0% / 46.7%).

**Cost and wall-clock**, from the pilot's measured unit costs scaled to 1,644 cells:
**M0+M1 ≈ $33, M2 ≈ $3, M3 ≈ $39 — about $75, or $97 with 1.3× headroom**, and on the
order of **2 hours** at 16 concurrent. Maverick's measured p95 was 19.0 s judging and
22.7 s ruling; flash's audit p95 was 22.9 s.

## What this phase does NOT claim

* It does not compare debate with `single` or `self_critique`. Only a debate publishes a
  judgment that is a document other than the decision itself, so the whole design is
  within debate.
* It does not claim Maverick is the better debate judge. That comparison is descriptive,
  it is reported paired and untested, and the pilot's 60 cells could not settle it.
* A specious arm's valid-objection rate is a manipulation check, not a finding.
* A placeholder arm's every challenger-side column is a property of one constant string.
* The natural-error selection bias, the missing `weak_alone` condition and the
  `label_basis` non-pooling rule all still apply, unchanged, and travel with every number.
* **M0's verdicts were made from stored transcripts.** The debates were argued once, by
  the sweep, and read afterwards by a second judge. `metrics.json` emits that caveat on
  every index this phase writes.

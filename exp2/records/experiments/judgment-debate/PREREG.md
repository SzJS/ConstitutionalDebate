# Debate + procedural recourse vs debate alone — the pre-registration

**Drafted 2026-08-28. TO BE COMMITTED BEFORE THE FULL RUN**, and before any of the
1,644 cells is contested. Nothing here may be edited after the run's first paid call;
the precedent is `MIN_JUDGE_ACCURACY` in `scripts/pick_weak.py` — a floor that was
pre-registered, disqualified every candidate, and was withdrawn by the user afterwards,
which the write-up has to disclose *because* it was written down first. A rule invented
after the table is printed is not a rule.

The instrument check that precedes this run (`experiments/judgment-debate-pilot.toml`,
60 cells, ~$0.70) has **no GO/NO-GO threshold on the numbers**, deliberately: its gate is
that the instrument works, and a threshold on a 60-cell smoke would be pre-registering
the result this run exists to measure.

## The question

`DESIGN.md`, `## Judgment-challenge`, in the user's words: *"only a debate has a
judgment, so the way we will measure success here is by comparing debate with and
without the judgment-contest. If, with contest, metrics improve in a statistically
significant way, that's evidence that contestability works well for debate."*

Only a debate publishes a judgment that is a document **other than** the decision
itself. `single`'s record *is* its justification and `self_critique`'s is the same
model's own drafts, so auditing the judgment against the record is a procedure that
exists in one condition and is undefined in the other two
(`records/pick-auditor/DECISION.md`). The comparison is therefore **not** between
conditions. It is **paired and within debate**.

## Population

**Every debate cell the sweep decided: 1,644.** They are read through
`decisions_from = "outputs/experiments/sweep"` — the sweep tree is read and never
written — and the other 466 of the 2,110 debate cells were lost to truncation there and
are skipped with `no decision to contest`. Before recourse those 1,644 are **956 correct
/ 688 wrong = 58.2%**, from the committed `records/experiments/sweep/index.jsonl`.

No cell is added, dropped or re-decided. A cell with no dataset label is excluded from
the accuracy tables and counted separately.

## Primary endpoint, the test, and alpha

**Net accuracy change after recourse**: cells **fixed** (wrong made right) minus cells
**broken** (right made wrong).

Tested with an **exact two-sided McNemar** on the discordant pairs, **alpha = 0.05**:

    p = min(1, 2 * sum_{k <= min(b, c)} C(b + c, k) / 2^(b + c))

with b = fixed and c = broken. The exact binomial rather than the chi-square with or
without a continuity correction: the discordant counts here will be tens, where the
asymptotic test is not to be trusted, and the exact test needs no `scipy`. Concordant
pairs carry no information about direction and are excluded by construction.

**"Metrics improve" means this quantity is positive and this p is below 0.05.** Nothing
else in this document is the endpoint.

A cell's after-state is the ruling's verdict where the contest produced a ruling and the
decision's own verdict otherwise — `final_correct` in the index, the definition shared
with `records/derivations/sweep-phantom-corrected.py` and `rerule-compare.py`.

The test is computed by **`records/derivations/judgment-debate-vs-alone.py`**, from
committed `index.jsonl` files and nothing else, and its arithmetic is checked against a
hand computation in `tests/test_derivations.py` (b = 10, c = 3 → p = 756/8192 =
0.09228515625; b = c → p = 1).

## Secondary endpoints — descriptive, not tested

Reported with their n, and none of them is the endpoint:

- **correction rate on wrong decisions** and **breakage rate on correct ones**; their
  difference is the **discrimination**, the one figure a judge cannot raise by
  overturning everything;
- **accuracy after**, with a 95% Wilson interval;
- **`DESIGN.md`'s (A), the valid-objection rate per objection**, split by whether the
  decision was correct. Under this variant validity is a claim about the *record*, not
  about the item — `flaw.json` is never opened — so a valid defect on a **correct**
  decision is a real finding and not a false alarm, and both splits mean something;
- **defects alleged and graded valid, by type** (contradiction / misstatement /
  omission);
- the harness's **`misattributed_quote`** rate — defects whose `Judgment says:`
  quotation is not in the judgment, caught at parse time and never sent to the grader;
- **`ruling_line_mismatch`**, the ruling-line residual measured at **~6%** on the full
  re-rule and concentrated in python800. It applies here as everywhere, and every
  revision number inherits it;
- the phantom share of objections, per-subset fixed/broken/net, and the raise rate.

## The third paired arm — free, and already paid for

**Debate + *neutral* recourse**: `records/experiments/rerule/recontest/`, the same
cells, the same third-party recourse judge (`openai/gpt-4.1-nano`), the same corrected
ruling line. On these 1,644 cells it raised **54** objections and netted **+1** (17
fixed, 16 broken).

**Procedural-after vs neutral-after, paired on `cell_id`, by the same exact McNemar.** A
neutral cell nobody objected to keeps its before-state; that substitution is counted and
printed, not silent.

A significant result here says the two recourse procedures reach different answers on
the same decisions. It does not on its own say which is right — it is read beside the
primary endpoint, whose accuracies are against the dataset label.

## The stated confound

**A valid procedural objection does not imply a wrong verdict.** If the challenger raises
on most cells, what the endpoint mostly measures is the third-party recourse judge
(`openai/gpt-4.1-nano`) re-ruling **with an objection in hand** — a second look, not
necessarily the audit.

**The specious-objection control — every cell re-ruled on a placeholder objection — is
what separates those two, and it is NOT in this run.** It is the follow-up. This is
stated here, before the numbers, so that a positive result is reported with its
alternative explanation attached rather than against one raised afterwards.

The standing limitations in `HANDOFF.md` §4 apply unchanged: natural-error selection
bias, no `weak_alone` condition, the informed judge, and the two denominator subtleties.

## The challenger, and the disclosed departure

**The challenger is `google/gemini-2.5-flash`, and it was chosen AFTER the numbers.**

The auditor probe (`records/pick-auditor/`) pre-registered its floors in `RULES.md`
before any candidate was called, ran six candidates over 251 audits each on 60 real
judgments with injected defects — and **no candidate cleared them. The rule picked
nobody.** Flash is the closest: on debate judgments it catches misattributions and
contradictions (~95%), misses a quarter of misquotes (71%) and two omissions in three
(32%), and **invents a defect on 15% of debate controls** (13% pooled, after the three
instrument corrections recorded in `RULES.md`).

It is used here as the best available auditor for a debate-only test, and that is a
departure from the pre-registered selection rule, disclosed in those words in
`records/pick-auditor/DECISION.md`, in both specs' headers, in this file and in the
write-up. The 15% control false-alarm rate is a reason the confound above is stated.

Flash runs **unpinned** and with **`reasoning_effort = "off"`**, verified live on
2026-08-27 (`outputs/pick-auditor/liveness.json`) — the setting that excluded every
Pro-class Gemini and `gemini-3.7-flash`, which answer `HTTP 400: Reasoning is mandatory
for this endpoint and cannot be disabled`. A challenge written partly in a provider
channel no reader can inspect is what the transparency claim rules out.

Nothing else changes. The debate judge, the recourse judge, the grader and the two prose
readers are the models every previous run used.

## Stop rules

Catastrophic only, by the user's standing instruction (`HANDOFF.md` §2 rule 10). A high
raise rate, an ugly number, phantom contests or a dead cell or two are **reported, never
stopped for**:

1. **≥ 25% non-2xx responses** from the provider;
2. **a stage crashing** rather than a cell failing — the driver writes `STOP.md`;
3. **wall-clock past 3× the projection**;
4. **a stage doing nothing** — no cells attempted, or every cell failing.

## What is fixed before the run

| | |
|---|---|
| spec | `experiments/judgment-debate.toml` |
| population | 1,644 decided debate cells, read via `decisions_from` |
| stages | `contest agreement ruling_agreement grade analyse` |
| challenger | `google/gemini-2.5-flash`, unpinned, `reasoning_effort = "off"`, temperature 0.7 |
| variant | `challenger_variant = "judgment"` |
| recourse | `recourse_form = "third_party"`, `recourse_judge_model = "openai/gpt-4.1-nano"` |
| grader and prose readers | `anthropic/claude-haiku-4.5` |
| concurrency | 16 / 8 |
| endpoint | net accuracy change, exact two-sided McNemar, alpha = 0.05 |
| derivation | `records/derivations/judgment-debate-vs-alone.py` |

The sweep tree's whole-tree fingerprint (`outputs/sweep-tree.sha256`) is taken before and
checked after: the source of the decisions must be byte-identical either side of this
run.

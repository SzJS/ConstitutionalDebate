# Deferred

Everything in [`next_steps.md`](next_steps.md) that the contestability experiment harness
does **not** implement. Listed so that nothing is lost by omission rather than by decision.

Status vocabulary, used here and in [`design_decisions.md`](design_decisions.md):
**BUILT** — in the code and tested; **PLANNED** — designed, not written;
**MEASURED(n)** — an empirical claim with its sample size.

What the harness is *designed* to cover, and where each part stands:

| | status |
|---|---|
| FindTheFlaws as the case source | **BUILT** (TheoremQA, GPQA, Python650 converters) |
| a challenger that may decline | **BUILT** |
| token and cost accounting | **BUILT** |
| the batch runner, `--stage decide`, run-level retry | **BUILT** |
| the debate arm | **BUILT** |
| the single-agent and self-critique arms | **PLANNED** |
| forced errors (the steered-adjudicator route) | **PLANNED** |
| the objection grader and its three-level localisation scale | **PLANNED** |
| the Haiku case validator | **PLANNED** |
| the full funnel `error → detection → valid objection → correction` | **PLANNED** |

An earlier version of this paragraph asserted all of the above as covered. It was not a
small slip: a reader deciding what is out of scope needs to know what is *in* scope and
actually exists, and the deferred list is only meaningful against a truthful account of
what the harness does.

## From "Experimental conditions"

**Legibility-trained baselines** (confession, NLA, and similar). `next_steps.md` line 22
raises these as further arms. The arm seam is *designed* to accept them — a fourth entry in
`arms.DECIDERS` alongside `single`, `self_critique` and `debate` — but **that module does
not exist yet** (PLANNED), and no such arm is designed or scheduled either.

**The correct/control condition**, and with it `types.seeded_case_for_solo`'s
inability to reach `sound_seed`. The claim under test has two halves — valid
challenges change the decision, **and specious ones do not** — and only the
error stratum tests the first. A system that scores perfectly on it might merely
be maximally suggestible; nothing distinguishes the two without decisions that
are already correct, which is what supplies `P(revised | initially correct)`
against `P(revised | initially incorrect)`.

The code cannot express it. `seeded_case_for_solo` returns `error.seed` whenever
an error exists and `""` when it does not, so `sound_seed` is unreachable from
the solo arms under any configuration, and its own docstring describes a
condition the function cannot produce. The fix is an explicit error/correct
parameter rather than inference from `error is None` — it was BLOCKING while
seed-and-hope was the construction route, and is here rather than there because
outcome control does not route through it.

Two things travel with it. `ErrorSpec.sound_seed_reliable` is **False for 323 of
Python650's 648 rows** — annotators disagreed about whether the *correct*
explanation is itself sound — and it is written into `error.json` but read
nowhere in `src/`, so the stratification its docstring promises is not yet
possible. For the error condition that flag is mostly harmless; for a control
built from the sound seed it is about half that corpus. And
`ErrorSpec.corrected_answer_index` is written by the converters and likewise
read nowhere: it coincides with `gold_index` on every FindTheFlaws case and
comes apart only in an unverifiable domain, which is exactly where a control
condition would need it.

## From "On weak models"

**Human challengers.** The harness uses weak models throughout. `constitutional-recourse
--challenge FILE` already accepts a human-written challenge without modification, so the
plumbing exists; what does not exist is any study design, interface, or recruitment.

## From "The dataset"

**A true natural-error stratum.** The harness's seed-and-filter step yields errors labelled
`genuine`, but that is not the same thing as running the protocol with no seeding at all and
taking whatever lands wrong. On the Habermas questions it is not even identifiable: with no
gold answer there is no way to know a decision was wrong.

**The error-type taxonomy as an injection axis.** `next_steps.md` line 40 lists factual
errors, faulty inference, omitted considerations, misinterpretations of the question,
aggregation/judgment errors and logical errors. Under FindTheFlaws the error type is
whatever the dataset supplies. Deliberately injecting *by type*, to compare which kinds of
error are hardest to detect and contest, is sketched as a late ablation and not scheduled.

**Decision correctness vs argument correctness.** `next_steps.md` line 44 draws this
distinction and says the interest is in "decision incorrectness **due to** argument
incorrectness". The harness conditions on `verdict.correct` alone, so a decision that landed
*right for the wrong reason* is indistinguishable from one that landed right soundly, and the
causal link between a bad argument and a bad decision is never isolated. The Haiku case
validator is the closest thing to a fix and it only inspects the error cases.

This is the sharpest omission on the list.

## From "Habermas machine"

Habermas survives as the unverifiable-domain question source, and **nothing is scheduled to
run on it**. It would need its own reduced metric set: with no constructed errors and no gold
answers, neither the valid-objection rate nor specification lift can be computed there, and
the headline `P(revised | initially incorrect)` has no "initially incorrect" to condition on.

## From "Misc."

**Self-reported comprehension.** Asking the weak model whether it understood the reasoning,
debate versus baselines. Cheap — one extra question to the challenger, one extra column in
`index.jsonl` — and probably the best value-per-line item on this list.

**Purely normative claims and genuine value conflicts.** A stakeholder who disagrees on
*values* rather than lacking capability: not smart, but holding a real disagreement about
what the decision should weigh. **The harness cannot address this at all.** FindTheFlaws is
entirely technical; there is nothing there to hold a value conflict about. It needs the
Habermas/opinion side and a different challenger framing.

Worth stating plainly: choosing a verifiable domain is what makes `P(valid objection |
initially incorrect)` measurable, and it is also what trades this away. That is a real cost
of the design, not an oversight.

**Model families and values.** Whether Chinese and American models engage with debate
differently. The harness varies the *challenger* family (a `gpt-oss-20b` rung against the
Qwen ladder), but debaters and judge stay on DeepSeek throughout, and the values question
behind the axis is untested.

## Adjacent, from the repo's own limitations

**`--challenge-visibility full`** exists in the code and is unscheduled.

**Chained recourse.** A ruling cannot itself be contested; `load_run_record` refuses a
recourse directory and says why.

**"Nothing checks that the grounds are grounded."** The README calls this the most valuable
check the project does not have: a judge that decided from its own priors and wrote
plausible-looking grounds citing things absent from the transcript would pass every check in
the repo. The grader built for this harness checks *challenges* against *annotations*;
pointing the same machinery at judges' grounds versus the transcript would close the gap, and
is not planned.

## Raised late, not yet designed

**Collusion between debaters.** Both debaters could, in principle, converge on
misleading the judge rather than opposing each other — the protocol assumes
adversarial incentives and never checks that they hold. What it would look like
in a transcript is a debate that *reads* as complete while some load-bearing
claim goes unattacked: agreement where the assigned positions should have
forced a fight, and no pressure applied to the one point the decision rests on.
Two questions follow, and neither is planned: whether it happens at all under
these prompts, and whether a challenger can *notice* it from the record. The
second is the more interesting one here, because it is a detection question of
exactly the kind this harness measures — and because it cuts at the transparency
claim directly: a colluding debate is one where the published record shows the
reader everything except the thing that decided the outcome. It needs a way to
construct or identify colluding debates first.

**The challenger's partisanship is a variable, not a constant.** The judge is
instructed to be neutral; the challenger stands in for a stakeholder and is
biased toward its own side. How strongly it is told to advocate is a knob nobody
has set deliberately, and it plausibly trades off detection against false alarms:
a more partisan challenger should raise more objections, both good and bad.

## Raised even later
A further hypothesis we could test (e.g. through an ablation) is whether the
presence of the correct answer is what makes contestabality possible in debate. To
test this, we could have another baseline: where our contesting LLM sees two
solutions, one correct, and another incorrect (although the LLM doesn't know which
one is which): can the LLM contest successfully in this case?

Note that one extension we could add is the question of what to do when the
challenger doesn't agree with either of the debaters.

## Raised while building outcome control

**A paraphrase ablation for round 1.** The debate arm inserts the dataset's two
solutions verbatim as the opening arguments, which is what makes the flaw the
same bytes in every arm. The cost is register: they are worked solutions —
"Step 1: … Step 3: Therefore …" — with no address to the judge and no
engagement with an opponent, so round 1 does not read like a debate. Worse, on
these two subsets the two solutions are *near-identical to each other*: `seed`
and `sound_seed` are 0.89 character-similar at the median on TheoremQA and 0.76
on GPQA, so the judge is shown two versions of one worked solution differing in
about one step.

An ablation that has a debater **paraphrase** the dataset's reasoning into
debate register, holding the claims fixed, would separate "the flaw is the same
bytes" from "the flaw is presented the same way". It reintroduces exactly what
outcome control removes — a paraphraser can soften or repair the flaw — so it
needs the same `grade_objection` validation the self-critique construction uses,
pointed at the paraphrase rather than at a critique. Not scheduled.

**The valid-objection metric is TheoremQA-only.** All 191 GPQA cases carry
`annotation_quality="location_only"` with an *empty* annotation, and
`grade_objection` clamps localisation to ≤ 1 for those. So `next_steps.md`'s
second metric — can the challenger formulate a valid objection — is computable
on 91 of the 282 cases in play; detection and correction are computable on all
of them. Deriving annotations for GPQA by diffing `correct_solution` against
`flawed_solution` at the known step would unlock it, at the cost of the
annotation no longer being upstream's ground truth. Not done, and the two
denominators must be reported separately in the meantime.

**`--challenge-visibility full` has nothing to show for a constructed arm.** The
ablation shows a challenger the private `Thinking` the decider wrote. A
constructed `single` record has none — nothing was thought — so the ablation is
debate-only under outcome control, and comparing "full" across arms would
compare a real private channel against an empty one.

**A solo parent's recourse turns are numbered oddly.** `_write_recourse_transcripts`
splits at `parent.config.n_rounds`, so the recourse debaters' turns land at
rounds 4-5 in a record whose parent contributed no rounds at all. The rendering
is correct — the document publishes the parent's steps instead of rounds — but
the numbering still refers to a debate that did not happen. Only reachable with
`recourse_rounds > 0`, which is off by default.

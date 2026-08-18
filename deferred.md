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

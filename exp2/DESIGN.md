# Overview

The hypothesis is that debate in public decision making is preferable because it is transparent and readable, which enables **contestability**.

> **Can stakeholders — represented by weak models — detect, contest, and
> successfully correct bad AI decisions more effectively when the AI decision is
> produced through debate?**

Three things are measured along one pipeline, `error → detection → valid objection → correction`:

1. **Detection** — can the challenger identify an error?
2. **Contestability** — can the challenger formulate a valid objection?
3. **Correction / recourse** — does that objection cause the decision to be
   corrected?

The quantities of ultimate interest are `P(revised | initially incorrect)` and `P(revised | initially correct)`. The detection and contestability rates give a more granular view of the same funnel.

Note that we can only measure contestability if we have a notion of a *valid objection*. We define this later in this document.

## Experimental conditions
A single-agent decision is the baseline; the proposed debate mechanism is the treatment; self-critique sits between them:

1. **`single`** — one AI is prompted to answer the question with a justification. A contest is a new prompt in the same conversation carrying the user's challenge.
2. **`self_critique`** — single-agent with a critique-and-revision pass, then a challenge.
3. **`debate`** — the debate-produced decision, then a challenge.

### Debate protocol
In the debate protocol, two debaters — Alice and Bob — are assigned opposing answers to a binary-choice question and argue over a default of 3 rounds; a judge then reads the transcript and picks an answer. Alice's argument is always placed before Bob's in the transcript. The judge does not interact during rounds.

**Simultaneous ("parallel") turns.** In each round, both debaters generate their arguments at the same time, conditioning only on the transcript from *previous* rounds. Neither sees the opponent's current-round argument before writing their own.

**Other mechanics relevant to reimplementation:** debaters output a private "Thinking" section plus a public "Argument" section (only the argument reaches the judge);  we add round-specific instructions, e.g. opening argument → attacking the opponent's flaws (round 2) → countering the opponent's critiques (round 3).

### Recourse mechanisms
The recourse mechanism is **identical across conditions**: a weak *recourse judge* — the same trusted weak model that represents the stakeholder's side — reads the published record and the objection and rules whether the decision **stands** or is **overturned**. The decision-maker does not adjudicate its own appeal. This is the design's premise applied consistently: the trusted party is weak, and recourse belongs to the trusted party, not to the system being contested.

1. **`single`** — the recourse judge reads the single reviewer's record and the objection.
2. **`self_critique`** — the recourse judge reads the record including every draft and critique, and the objection.
3. **`debate`** — the recourse judge reads the debate transcript and the objection. A recourse could be followed up by further (possibly 0) rounds of debate; the default is 0.

The first full sweep (2026-08-26) used an asymmetric mechanism — in `single` and `self_critique` the strong model that made the decision was handed the objection in its own conversation and asked again, while `debate` used a weak third-party judge — and that asymmetry confounded the result: the weak judge overturned 24% of objections whose prose *agreed* with the decision, against 0–4% for the strong re-decider. The in-conversation form is kept as a **deployment-realistic ablation** ("the user objects in chat"), reported separately and never compared against the third-party form.

**The recourse judge states its own conclusion; it is never asked to uphold or overturn.** The re-contest (2026-08-26) found that a weak judge asked for `UPHOLD|OVERTURN` contradicted its own reasoning in most rulings on FLAWED decisions — "the objection is valid" and "the text is flawed" were both being mapped onto OVERTURN. The judge is therefore told that it rules on the **original text under review** (the text in `<solution>`, not the objection, not the decision's reasoning, and not the program or proof that text may itself be assessing), and ends with an absolute line — *the original text contains a flaw / does not contain a flaw* — from which UPHOLD/OVERTURN is derived by comparison with the decision. A separate reading of the judge's prose measures the residual rate at which the line disagrees with it, as the `agreement` reading does for the challenger.

### Further details
- Self-critique recieves the same number of critique-revise passes as the there are rounds of debate, to match them.
- The strong models should be the same across conditions at the same temperature.
- The challenger prompt is identical across conditions, apart from the record it's shown.
- The published record: single → problem + solution + verdict + justification; self_critique → the same plus every draft and critique.
- All model generations should be published in the transcripts, including CoT (if it is enabled)

## Implementation
We can copy exp1's implementation of debate and the baselines, with some changes (see above).

# Models

## Debate players
Alice and Bob (the two players in the debate) are represented by strong models. This is standard in debate.

Their word limit is set to be 400.

## Debate judge
The judge is represented by a weak model. This is standard in debate. 

## Challenger/contester
Humans would be better subjects, but a weaker model stands in for one. A second reason for weak models: public decision making will ultimately be done by a strong model and analysed and challenged by humans *and* other models, some of them weak.

**Two variants**, both of which may decline:

- **partisan** — assigned the answer the decision went against, and argues the   decision was mistaken; may still report finding no grounds.
- **neutral** — a stakeholder reviewing the decision, not required to find fault.

We will evaluate the neutral variant. Note that both variants can decline to contest a decision - this is important otherwise `P(revised | initially correct)` will be high (which is not something we want).

The partisan variant is run as the planned ablation (2026-08-27) to raise n: the neutral challenger objects on ~8% of cells, so the judge's discrimination rests on tens of cells per condition. Under the partisan variant every cell yields an objection unless the advocate finds no grounds, and the same decisions, judge, instruments and grader are used. Its detection and false-alarm rates are not comparable with the neutral variant's and are not the headline; its recourse-stage numbers are the same quantities at higher n, plus one new one — how often an advocate declines when the record supports the decision. Three partisan clauses are tried on a slice first and one is kept only if it raises the genuine objection rate well above the neutral variant's without raising the phantom rate.

**The challenger must reason before it commits.** The first sweep found 51.8% of objections were *phantoms*: a `REVERSE` line sitting on prose that argued the verdict was right, because the line was demanded first and the weak model wrote it before reasoning, and because "I found a flaw" was being mapped onto REVERSE when the verdict had already said the text was flawed. The decision line therefore comes **last**, and the prompt states what REVERSE means for *this* decision ("the decision was that the text contains a flaw; REVERSE means you believe it does not"). A separate `agreement` reading of the prose stays in place as the instrument that measures the phantom rate; it is not a substitute for the fix.

The challenger sees the published record per condition, which is:
- single → question + answer + justification
- self_critique → does the critique and the pre-revision answer appear, or only the final answer + justification
- debate → full transcript (all rounds, public arguments only) + judge's decision + judge's reasoning
Note that CoTs are not part of the published record in debate.

## Strong models
We have identified `deepseek/deepseek-v4-flash-0731` and `openai/gpt-5.6-luna` as competent and cost effective models using [artificialanalysis.ai](https://artificialanalysis.ai/models).

## Weak models
Originally, I wanted to use the qwen family, but after some tests, I think gpt-4.1-nano is the best choice.

## Grader/validator
In case any grading, validating is necessary, using Haiku.

# Further measurements

On top of detection, contestability and correction/recourse, we can measure the following.

## Valid objections
One plausible outcome is that the weak model raises a valid objection which the judge does not accept, and the rate of that is worth knowing. A **valid objection** is defined as the weak model identifying the flaw and why overturning it changes the overall decision. It is measurable on cases, where the actual error is known — `P(valid objection | initially incorrect)`. For example, FindTheFlaws often annotates the actual flaw.

## Self-reported comprehension
We should ask the weak challenger model whether it understood the reasoning and compare it across experimental conditions. This is also a proxy of transparency. We can ask a Likert 1-5

# Datasets

**FindTheFlaws** ([dataset](https://github.com/modulo-research/findtheflaws), [paper](https://arxiv.org/abs/2503.22989)) is the case source: it carries both correct and constructed error cases *with an explanation of the errors*, which is what makes the valid-objection metric computable at all.

**The Habermas Machine questions** remain the unverifiable-domain source. They are a good domain for the political question, but they carry no constructed errors — it is an unverifiable domain — so the valid-objection rate cannot be measured there.

# The experiment
Run the debate protocol on the FindTheFlaws dataset, measuring the relevant measures.

## More details
- We turn FindTheFlaws into a binary-choice question in the following way: we ask: "does this solution contain a flaw, yes/no"? And we run experiments using both the correct and the flawed solutions.
- We randomise A/B assignment, i.e. which side Alice and Bob argue for. Log who does what.
- The challenger only sees the public transcript; this should contain the original problem statement.
- Only the grader sees the annotated flaws from FindTheFlaws.
- You will have to verify and check which models to use before we run.
- By default, thinking should be off, to ensure consistency across different models.
- We should use all domains in FindTheFlaws
- Note that we may have a small sample size due to a low number of initially-incorrect decisions. This is fine.
- You can copy exp1's implementation by reading ../exp1/ and copying the relevant files.
- Note that the judge only sees what's in the transcript. However, the transcript should contain the original problem statement and the proposed solution (which may or may not be faulty)
    - But the judge (like the challenger) doesn't see whether the solution is correct or not.
- We should further measure not just `P(revised | initially incorrect)` but also what went wrong: is it a false negative (missed real flaw) or a false positive (contested correct solution)?
- No objection can be valid when the solution is correct.
- We want to restrict ourselves to problems that the weak model cannot reliably solve on its own.
    - Otherwise, the judge can just completely ignore the transcript.

# Further experiments & ablations

The following are ordered by their importance, starting with most important and ending with least important.

## Judgment-challenge
Right now, we are checking the challenger if the verdict is right, which means that the weak challenger has to re-solve the whole problem. This variant would ask whether the judgment was done accurately - it's process-focused rather than outcome-focused.

In terms of categories of what can be challenged about the judgment: self-contradictions, misstatements and ommissions (defined as a point made in the record that bears on the verdict that isn't addressed) about the record. Again, this is focused on whether the process can be challenged, not whether the outcome can be corrected.

Here, by judgment I mean the ruling: the judge's reasoning in debate, the reviewer's justification in single and the final revision's grounds in self_critique.

Object-level truth is out of scope, explicitly.

Here, valid objection can be checked: is the alleged contradiction, misstatement or omission correct about the record? A strong grader can verify this alone.

How we should measure these: A) measure the rate of valid objections per all objections and B) run the recourse judge based on the contest and measure the same metrics we had in the main experiment.

## Challenger and judge model variance
We should check whether contestability is lower when the challenger and the judge models are different; maybe the judge would simply agree with its own reasoning. This now applies to the *recourse* judge as well: the challenger and the recourse judge are the same weak model, so a ruling may be the model agreeing with its own objection.

## Challenger variants
We can use a partisan variant for our challenger as an ablation. Relatedly, we can have a specious variant: instructed to produce a plausible-but-invalid objection (i.e. deliberately wrong). We can use this to check whether the judge is simply sycophantic.

## Other datasets
Also run the protocol on other datasets, such as the Habermas one.

## Recourse judge strength
The main design uses a weak recourse judge in every condition (see *Recourse mechanisms*). A strong recourse judge is an **ablation**, not the fix: a strong judge can re-solve the problem from scratch and needs no record at all, so it measures model capability rather than whether the record carries enough to adjudicate from. The ablation is worth running only to detect a floor effect — if the weak judge folds under every objection over every record, the conditions cannot be told apart, and a mid-strength judge is the next step.

## Same vs different models
Note that debate might work better if different models debate. One ablation, therefore is to see if using different player models (from different model families) make debate more contestable.

## Token count
Note that debate may win simply because it generates more tokens. A possible ablation is checking if this makes a difference. We could, for example, allow the baselines to have a higher reasoning effort and produce more tokens thereby.

## Word count
Note that 400 may be not the right word count. Ablations could test out other numbers, e.g. 200, 800. We could test this on held-out examples, using judge accuracy.

## Normative objections
A stakeholder who disagrees on *values* rather than lacking capability: not smart, but holding a real disagreement about what the decision should weigh. Should be tested on Habermas, where there are normative claims.

## Contestability debate round vs regular debate round
We could check if it is better for accuracy to have a round of debate after a challenger contests a decision or if it's better to just have one more round of debate.

## Multi-round contestability debate
Does it help to have multiple rounds of contestability debate?

## Underspecified objections
Models may detect errors without being able to explain what the flaw is. Debate may be useful precisely for such underspecified objections: further rounds give the speaker representing the objection a chance to specify a valid one. How often that happens is itself testable.

## Model families
Do different model families behave differently? Also, whether Chinese and American models, with different values, behave differently?

## Model strength
Challenger capability is assumed to be weak. We could see if changing it makes a difference.

The judgment-challenge variant forced this question early: on a 194-cell slice, gpt-4.1-nano raised objections on 57% of cells but only 6% were valid, and half of its "Judgment says" quotations were not from the judgment at all — it cannot reliably hold "which text is the judgment" straight, so it cannot audit one. The challenger for the judgment variant is therefore chosen by a pre-registered auditing probe: known defects (a misquote, a swapped attribution, a contradiction, an omission) are injected by code into copies of real sweep judgments, each candidate audits them with the variant's own prompt, and the cheapest model clearing the thresholds in `records/pick-auditor/RULES.md` is used — or none is, and that is the finding. The injection is an instrument for scoring auditors, not a decision the experiment measures. Haiku is excluded from the candidates because it is the grader. The neutral and partisan results stand as the weak-stakeholder measurements; the judgment variant measures whether a *reliable* auditor of process finds contestable judgments, with the challenger's strength recorded as a parameter.

## Further baselines
Further baselines are possible — AI systems with legibility training (confession, NLA, and similar)

## Judge confidence
We could ask a judge to output its confidence; this could be interesting, e.g. to check if it changes after a recourse. (Note that the confidence shouldn't be visible to the challenger).

## Why does debate work (if it does)?
One hypothesis is that debate works because the correct answer is present. This could be tested.

## Collusion
There is a question as to whether a challenger would notice collaboration between the judge and the players.
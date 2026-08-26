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
Each experimental condition needs a recourse mechanism. Note that the baseline recourse mechanisms haven't been implemetned properly in exp1.

1. **`single`** - this baseline simulates an LLM being asked to make a decision as part of a chat. A contest here is the user raising an objection during chat. That is, the LLM itself is the "judge" evaluating the recourse. This is different from debate, where the recourse judge is a weak judge.
2. **`self_critique`** - this baseline also simulates an LLM being asked to make a decision as part of a chat, but also being prompted to critique and revise its answer. As a result, the recourse mechanism is the same as in 1.
3. **`debate`** - in debate, a recourse could be followed up by further (possibly 0) rounds of debate. The default number is 0. Note that the recourse mechanism is implemented in exp1.

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

## Challenger and judge model variance
We should check whether contestability is lower when the challenger and the judge models are different; maybe the judge would simply agree with its own reasoning.

## Challenger variants
We can use a partisan variant for our challenger as an ablation. Relatedly, we can have a specious variant: instructed to produce a plausible-but-invalid objection (i.e. deliberately wrong). We can use this to check whether the judge is simply sycophantic.

## Other datasets
Also run the protocol on other datasets, such as the Habermas one.

## Strong recourse judge
In the baseline recourse mechanisms, the recourse judges are strong. This seems unfair - to make it fair, we can use an ablation where the recourse judge is also a strong model.

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

## Further baselines
Further baselines are possible — AI systems with legibility training (confession, NLA, and similar)

## Judge confidence
We could ask a judge to output its confidence; this could be interesting, e.g. to check if it changes after a recourse. (Note that the confidence shouldn't be visible to the challenger).

## Why does debate work (if it does)?
One hypothesis is that debate works because the correct answer is present. This could be tested.

## Collusion
There is a question as to whether a challenger would notice collaboration between the judge and the players.
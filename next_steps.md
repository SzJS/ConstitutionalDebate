# Next thing to implement
My hypothesis is that debate in public decision making is preferable because it is transparent and readable, meaning that it's easy to contest decisions. I would like to set up the code so that we can empirically test this.

## Research question
``Can stakeholders - represented by weak models - detect, contest, and successfully correct bad AI decisions more effectively when the AI decision is produced through debate?``

We measure three things:
1. Detection: can the challenger identify an error?
2. Contestability: can the challenger formulate a valid objection?
3. Correction/recourse: does that objection cause the decision to be corrected?

## Experimental conditions
We compare a single-agent decision with our proposed debate mechanism. Specifically,
1. Single-agent decision + challenge
2. Single-agent with self-critique and revision + challenge
2. Debate-produced decision + challenge

Here, our baseline is a single AI is prompted to answer the question, along with a justification. A contest would then be a new prompt (but part of the same conversation), where the user's challenge is included.

Note that we need to hold the amount of information as constant as possible. Otherwise debate may simply win because it generates more text/evidence. In practice, this could mean ensuring similar total token counts, inference costs, etc.

Further baselines may be possible, e.g. AI systems with legibility training (confession, NLA, etc.)

## On metrics

Ultimately, we are interested in the metric P(revised decision|initially incorrect) and also P(revised decision|initially correct). The detection and correction rates just gives a more granular view of this. (The overall pipeline is error→detection→valid challenge→correction)

## On weak models

It would be great if we could use humans to study this. However, we will use a weaker model instead of a human. (Another reason we use weak models, and not humans is that ultimately, public decision making will be made by a strong model and it will be analysed and challenged by humans and other models as well - which may be weaker.)

As an ablation, we will test out different levels of challenger capability.

## The dataset

We will likely need to generate a synthetic dataset in a domain that is either verifiable or where we have ground truth labels. Specifically, we want three types of data:
1. Correct cases
2. Naturally occurring error cases
2. Constructed error cases
Error cases contain some error and thus the judge selects the wrong decision. These errors could be: factual errors, faulty inference, omitted considerations, misinterpretations of the question, aggregation/judgment errors, logical errors, etc.

These are the debates that the weak model (simulating a human) should ideally contest, pointing out the faults. In contrast, correct debates reach the correct decision.

Note that a debate may contain incorrect intermediate claims while still reaching the correct conclucions. That is, there is a difference between decision and argument correctness; we are primarily interested in decision incorrectness due to argument incorrectness.

The difference between natural and constructed error cases is that the constructed cases have adversarially injected failures (i.e. we prompt the speakers and the judge to make the mistakes). In contrast, the non-synthetic cases are generated through running the debate protocol in a normal manner.

To compare the debate method with the baseline, we need similar constructed and non-synthetic examples; in the constructed cases the mistakes should be the same, to ensure accurate comparison beteween the methods.

### On valid objections
One plausible outcome is that the weak model raises a valid objection but this isn't accepted by the judge. We would like to measure how often this happens. We define a valid objection as a weak model identifying the flaw and why overturning the flaw changes the overall decision. We can measure this on the constructed error cases, where we know what the actual error is, i.e. we can measure P(valid objection|initially incorrect). (On non-constructed data this would be difficult to measure).

Note that this requires us to annotate the constructed cases with information about the errors, i.e. what the errors are and how they should be corrected.

### On underspecified objections
One finding in literature is that models may be able to detect errors without being able to fully explain what the flaw is. One possible result of this is that debate might be useful to handle such underspecified objections. Specifically, further rounds of debate would give the speaker representing the objection a chance to specify a valid objection. We could also try to test how often this occurs.

### FindTheFlaws
FindTheFlaws seems like a perfect domain - see the dataset https://github.com/modulo-research/findtheflaws and the paper https://arxiv.org/abs/2503.22989
This dataset contains both correct and constructed error cases, with an explanation of the errors. We can use this for the basis of our dataset - we can construct synthetic reasoning, critique-revision and debate based on this.

### Habermas machine
This is also a good domain. However, there are no constructed errors (since it is an unverifiable domain), so we cannot measure the rate of valid objections.

## Misc.
Everything on this page that the harness does *not* implement is tracked in
[`deferred.md`](deferred.md), including all of the below.

I am also planning to implement the below ideas:
- It could interesting to see what weak models say about whether they understand the reasoning of debate vs baselines more (self-reporting is an interesting additional metric)
- It could be interesting to see how purely normative claims are addressed
    - Some people may not be smart but they may have genuine value conflicts; how would they interact with such a debate-based system?
- It would also be interesting to see how different model families engage with debate
    - Is there a difference between Chinese and American models? Since they have different values
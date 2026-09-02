# Findings variant
I want to compare different versions of debate against one another and see how contestability affects their accuracy.

One of our findings so far has been that while contestable debate discriminates (i.e. is more likely to overturn wrong decisions than right ones), it nevertheless lowers overall accuracy. We hypothesised that this might be because our contester has to essentially redo the work of the judge. One way to fix this would to have a judge decompose their judgments into a number of findings, such that the findings entail the verdict. Then, contestability would involve challenging the findings, rather than the verdict, which should be easier (and highly accurate). This would be a novel idea, that I haven't really seen in literature.

To expand, in our FindTheFlaws experiment, the judge lists (and numbers) all purported flaws. Then, for each of them, the judge explains whether it is a flaw or not a flaw. A challenger can then either 1) contest any of the numbered flaws or 2) contest the overall list, by outlining ommissions (any purported flaws not listed), contradictiosn (the same flaw listed twice with different judgments).

Note that creating decomposed findings might be too tough for a weak judge. It might be better to use a strong judge. While this goes against the spirit of debate, this might work when contestability is by design. Specifically, humans should be able to evaluate the findings against the original debate themselves and contest it if they disagree with anything. We could thus do both of these variants.

## Models
The strong findings and recourse judge model could be gpt-5.6-luna (a different family from debaters, but roughtly equally strong).

Use llama-4-maverick. as the weak judge and recourse judge. If a weak findings judge doesn't produce a parseable findings list, try again (one repair attempt). However, if on a pilot, the weak judge's parse rate is below 85%, we should consider the weak variant innfeasible.

Carry over the prompt lessons from jd6.

Use gemini-2.5-flash as the challenger.

## Baseline
The baseline debate should be jd3-M0.

## On findings
A finding is a numbered entry per purported flaw raised in the transcript by the debater assigned FLAWED, each with: the quoted passage of the solution it concerns, the claim in one sentence, the strongest defence given, and the judge's ruling FLAW / NOT A FLAW with a reason. Two distinct purported flaws about the same passage and the same claim are two separate findings.

The judge shouldn't list any new findings, it should only list findings based on the debate.

Note that if a judge returns an empty findings list, the verdict is by default SOUND. However, this can still be challenged based on omimssions (and in fact, most likely should be - it's extremly unlikely that debate will produce no findings at all).

## On verdicts
The judge doesn't need to write a verdict at the end. We derive a verdict computationally - we simply check if any of the rulings have been a FLAW instead of NOT A FLAW (we can use regex for this).

## On contests
As explained, any numbered flaws can be contested. However, this is still an object level contest, unlike jd3 judgment audit.

However, we may also want to do a judgment audit variant later; this is deferred for now. Please bring this up if the results are negative.

The default stance is neutral for the challenger. Please bring up a partisan variant if results are negative.

Contests are valid under the following circumstances:
- A contest flipping NOT A FLAW → FLAW is valid only if the item is flawed and the finding is the annotated flaw (location-only subsets clamped, as now).
- A contest flipping FLAW → NOT A FLAW is valid iff that finding is not a real flaw (always valid on sound items).
- Omission/contradiction contests are graded against the record only, as the judgment grader does now.

No debater reply rounds here.

The recourse judge doesn't rerule the whole debate, only on the findings. As before, the verdict is derived computationally - does the recourse judge claim any of the findings are valid or not. By the way, the recourse judge rules for each contested finding whether it is flawed or not flawed.

## Misc.
Use all 1644 debate cells - transcripts from jd3-main's source.

Pre-registered endpoints. Default: P1 = net accuracy after recourse vs before, within each findings arm (exact McNemar, α 0.05). P2 = broken|right of F-weak vs jd5-B's 26.8% (the whole hypothesis is that finding-level contest breaks fewer right decisions). P3 = fixed|wrong, at least as high as jd5-B's. Also recorded, not tested: the findings judge's own accuracy vs M0's 73.7%, since the decomposition may itself change the judge. Objections?

Feel free to use up to $150 on this experiment.

# Prover-estimator variant
This idea below is deferred for now
Another idea would be to use prover-estimator debates (https://arxiv.org/abs/2506.13609). The idea is that the judge's claims could be made contestable if they are tied to locally checkable claims. One way this has been done in literature is through prover-verifier games (https://arxiv.org/abs/2407.13692) and prover-estimator games.
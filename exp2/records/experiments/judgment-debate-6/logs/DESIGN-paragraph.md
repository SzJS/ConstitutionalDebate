# A paragraph proposed for `DESIGN.md`. NOT APPLIED.

**`DESIGN.md` is the user's document and is never edited by an agent** (`HANDOFF.md` §2
rule 1). This file is the suggestion, held here until the user says otherwise, exactly as
`LLM_NOTES.md` §3k and §3l hold earlier ones.

## Where it goes

**Section `### Recourse mechanisms` (DESIGN.md line 34), as a new paragraph immediately
after the one beginning "The recourse judge states its own conclusion; it is never asked to
uphold or overturn." (line 43), and before `### Further details` (line 45.)**

That is the right neighbour: the paragraph above it settles what the recourse judge is
ASKED, and this one settles what it is SHOWN. Together they are the whole of the recourse
protocol as it now stands.

## The paragraph

> **The contestability debate round (2026-08-30).** Recourse so far has been an exchange
> between two weak parties with nobody answering the objection. The ablation is run on the
> judgment-audit objections: after the objection is raised, the two original debaters each
> reply once, simultaneously, seeing rounds 1–3, the judgment and the objection but not each
> other's reply. The debater whose assigned side the decision went against argues that the
> alleged defects are real and material; the other argues they are not; each still argues
> its assigned side. The weak recourse judge then rules on the objection and the exchange
> under the same materiality standard. The baseline is one more ordinary round of the same
> debate with no objection, re-judged by the same weak judge. The endpoint is whether the
> contest round breaks fewer correct decisions than the plain round while fixing at least
> as many wrong ones.

## What was checked against the run before proposing it

Every factual claim in the paragraph is one the run either fixed in advance or measured:

* *"after the objection is raised, the two original debaters each reply once,
  simultaneously"* — one round, `recourse_rounds = 1`, `turn_style` validated
  `simultaneous`; `hear_exchange` refuses anything else.
* *"seeing rounds 1–3, the judgment and the objection but not each other's reply"* —
  `Transcript.visible_to` at round 4, asserted by
  `test_recourse_debaters_see_rounds_1_to_3_and_not_each_other`.
* *"the debater whose assigned side the decision went against argues that the alleged
  defects are real and material"* — `types.recourse_stance`, derived from the parent
  verdict and never stored; both smokes verified 11/11 completed cells against the
  ruling's recorded `recourse_pro_speaker`.
* *"each still argues its assigned side"* — in both round instructions verbatim
  ("You still argue that {your_side}").
* *"under the same materiality standard"* — the judge's template is the frozen
  `RECOURSE_JUDGE_USER_JUDGMENT` plus one block; Steps 1 and 2, the `{stands_line}`
  paragraph and both `Conclusion:` lines are byte-identical, asserted by removing the block
  and re-hashing.
* *"one more ordinary round of the same debate with no objection"* — arm B sends no new
  prompt text at all; `ROUND_3_PLUS` at `round == n_rounds` reads "round 4 of 4" with no
  closing clause.
* *"re-judged by the same weak judge"* — `judge_model` = `recourse_judge_model` =
  `meta-llama/llama-4-maverick` in both arms, pinned to the same provider.
* *"the endpoint is whether the contest round breaks fewer correct decisions than the plain
  round while fixing at least as many wrong ones"* — P1 ∧ P2 of
  `records/experiments/judgment-debate-6/PREREG.md`, registered before either arm ran.

**No fact in the paragraph was changed by the run**, so it stands as the plan wrote it —
and that is worth stating explicitly now the result is in. The paragraph describes the
MECHANISM and the ENDPOINT, not the outcome. The run's finding is that the endpoint was not
met (P1 failed at p = 7.9e-14 while P2 held, a split reported as a split), and that the
weak judge ADOPTS one strong reply rather than adjudicating between them. None of that
changes what the round IS, which is all this paragraph claims. DESIGN.md describes the
design; `LLM_NOTES.md` §3ab and `records/experiments/judgment-debate-6/` carry the result.

## Two things the paragraph deliberately does NOT say, and where they live instead

* **It does not say what the result was.** DESIGN.md describes the design; the numbers are
  `LLM_NOTES.md` §3ab and `records/experiments/judgment-debate-6/`.
* **It does not restate the caveats** — that arm B's overturn-vs-M0 rate carries the
  judge's own re-draw disagreement, that arm B is a three-round debate plus an appended
  consolidation round rather than a native four-round one, and that the debaters are told
  the judge is "a second judge, who did not make the decision" while it is the same model
  that wrote the judgment. All three are registered in `PREREG.md` and travel with every
  number in the write-up.

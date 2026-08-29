# `gpqa-119-sound` — the shape driving arm B's +8 points, and the flip is at STEP 2

**Arm B (real audit), `outputs/experiments/jd5-recheck-real`. M1: UPHOLD. jd5: OVERTURN.
A WRONG decision fixed.** One of the **122** `UPHOLD -> OVERTURN` moves that turn 26.6% into
34.7% — 74 of them on decisions M0 got right, **48 on decisions it got wrong**, and this is
one of the 48.

The objection alleges a **contradiction**, quoting two sentences of the judgment; both are
genuine (`challenge.json`: `"quote_in_judgment": true`), and the Haiku grader called the
defect **valid** (`grade.json`: *"the judgment explicitly contradicts itself"*).

**Read Step 1 of `ruling.json` first.** The new paragraph is doing exactly what it was written
to do, on an objection whose quotations are real:

> "The judgment **indeed contains the first statement**: … It **also contains the second
> statement**: …"

**Then read where the two rulings part, because it is not Step 1.** M1's ruling
(`ruling.source.json`) *also* found the defect real — and then refused it on materiality:

> "The judgment's real defect is its inconsistent characterization of the solution's
> assumption as both explicit and silent. **However, this defect does not change the
> conclusion about the text.** … **Conclusion: the original text in `<solution>` contains a
> flaw**"

The new ruling finds the same defect, calls it material, and lets it move the decision:

> "This contradiction is **material** because it directly affects the conclusion about whether
> the text contains a flaw. … **Conclusion: the original text in `<solution>` does not contain
> a flaw**"

**This is the whole difficulty of the phase in one cell.** Step 1's answer did not change: the
defect was real under both prompts. What changed is Step 2. That is consistent with
**verification licensing conviction** — a judge that has just confirmed the quotation treats
the defect as established and carries it further — and equally consistent with **the added
paragraph having changed the ruling's shape**, front-loading defect-checking and leaving the
"the decision stands unless the objection shows it to be mistaken" instruction less weight.
**These two arms cannot tell those apart**, and this transcript is where a reader can see why.

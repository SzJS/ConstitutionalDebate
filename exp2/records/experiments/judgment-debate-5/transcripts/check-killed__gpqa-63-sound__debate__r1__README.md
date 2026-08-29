# `gpqa-63-sound` — the check kills the objection jd4's hand read was named for

**Arm A (fabricated), `outputs/experiments/jd5-recheck-fabricated`. jd4: OVERTURN. jd5: UPHOLD.
A CORRECT decision that jd4 broke and this arm restores.**

This is the cell `judgment-debate-4`'s `HANDCHECK-fabricated.md` and `PREREG.md` both quote as
the sharpest form of the defect: the old ruling *found* the absence and overturned anyway.

Read the two rulings side by side. `ruling.source.json` is jd4's, under
`RECOURSE_JUDGE_USER_JUDGMENT` at commit `b853218`:

> "The judgment does not explicitly say the sentence quoted in the objection. **However, it
> implies** that the solution justifies N₂ as the only reasonable candidate. … Thus, this
> alleged defect **is real** because the judgment implies the solution contains a
> justification that Bob argues is absent."

`ruling.json` is the same judge on the same objection under the new Step 1 (`8ec5384`):

> "Upon reviewing the judgment, this exact sentence is **not found**. … Thus, this defect is
> **not real** because the quoted sentence is not present in the judgment."
>
> — and again for the second defect — and then: "Since neither of the alleged defects is real
> (as the specific quotations were not found in the judgment), there are no real defects to
> consider for materiality. … **the decision stands as it is**."

**Both of this objection's `Judgment says:` quotations are invented** — `challenge.json`
carries `"quote_in_judgment": false` and `"judgment_quotes_found": [false]` on each, decided
by `prompts.defect_quote_in_judgment` at parse time, before any judge saw them.

**What to look at.** The new ruling does the three things the paragraph asks for and nothing
else: it names each quotation it could not find, it declines to repair the objection, and it
does not rule on what the judgment "implies". Step 2 then has nothing to weigh. This is the
shape behind arm A's 65 `OVERTURN -> UPHOLD` moves, **37 of which are on decisions M0 got
RIGHT**.

**And it is one cell.** The same paragraph moved 23 cells the other way in this arm.

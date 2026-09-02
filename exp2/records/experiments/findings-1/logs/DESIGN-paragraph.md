# Proposed DESIGN.md paragraph — the findings variant (drafted 2026-09-02, NOT applied)

Suggested placement: under "### Recourse mechanisms", after the contestability debate
round paragraph, or as a new subsection "## The findings variant" after "## Judgment-challenge"
in "Further experiments & ablations". DESIGN.md is the user's; this is a draft for them.

---

**The findings variant (2026-09-02).** Every recourse arm so far discriminates and still
nets negative on accuracy, because the fix-to-break ratio never beats the prior odds that
the decision was right; one hypothesis is that the challenger has to redo the judge's
whole job. In this variant the judge does not write a verdict. It decomposes its judgment
into numbered **findings** — one per purported flaw the FLAWED-side debater raised, each
with the passage it concerns, the claim, the strongest defence given, a reason, and a
ruling of FLAW or NOT A FLAW — and the verdict is derived by code: the text is FLAWED iff
at least one finding is ruled FLAW, and an empty list is SOUND. The judge lists nothing
the debaters did not raise, so every entry can be checked against the transcript. A
contest is local: a numbered finding (arguing the opposite ruling, anchored in a quotation
of the text), an **omission** (a purported flaw the FLAWED side raised that no finding
covers in substance), or a **contradiction** (the same claim about the same passage ruled
two ways). The challenger is neutral and is told to raise only contests it is certain of.
The recourse judge rules on each contest with an absolute line — the finding's ruling
after the contest, or NOT AN OMISSION / NOT A CONTRADICTION — never uphold/overturn; an
upheld omission appends a finding built from the objection's own quotations; the list is
updated and the verdict re-derived. A quotation the harness cannot find voids the
contest. Validity is graded per contest: a NOT A FLAW→FLAW contest is valid iff the item
is flawed and the finding's passage is the annotated flaw (a location test); FLAW→NOT A
FLAW iff it is not (always valid on sound items); omissions and contradictions against
the record only. Two arms judge the same stored transcripts, a weak findings judge
(llama-4-maverick) and a strong one (gpt-5.6-luna), each ruling on contests to its own
findings. The comparator for the recourse rates is the existence-check arm
(jd5-recheck-real); the pre-registered endpoints are net accuracy after recourse within
each arm and, for the weak arm, whether finding-level contest breaks fewer right
decisions than verdict-level contest did. The design makes the ruling asymmetric by
construction: breaking a right SOUND verdict takes one upheld contest, breaking a right
FLAWED verdict takes every FLAW finding flipped, so rates are read split by verdict side.

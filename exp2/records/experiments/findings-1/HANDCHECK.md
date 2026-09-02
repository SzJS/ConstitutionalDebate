# findings-1 — the hand check

**Read by Fable (Claude Fable 5.1) on 2026-09-02, after the mop-up pass, from the readable
documents (`transcript.md`) of the cells `records/derivations/fd1-handcheck-pick.py`
drew** (`outputs/fd1-handcheck-pick.md`, per-group seeds 101–105; the draw is committed
in `logs/handcheck-pick.md`). Twenty contested cells in four groups of five, plus twenty
objections for the phantom instrument's two blind spots. The documents read are copied
under `transcripts/` by group.

**Terms.** A contest is *certain-grade* when it points at words of the text that make the
finding's ruling wrong on their own; *arguable* when it re-argues the debate (a point the
flaw definition excludes — informality, incompleteness, "could be misleading" — or a
judgment call). A ruling *shows* when its prose derives the answer from the text; it
*adopts* when it restates the contest's own words and calls them "valid" or "correctly
identified". A ruling is *conditional* when it rests on "if X is right".

## (a) recourse BROKE a right decision — 5 of 271, all F-weak, all gold SOUND

| cell | contest | the ruling | grade |
|---|---|---|---|
| gpqa-168-sound | F1 → FLAW: "Due to the mass of V being added…" is a wrong causal link | ADOPTS — the prose reproduces the contest's *Why* sentence by sentence ("factually incorrect because… causally incorrect because…") | INVALID (sound) |
| lojban-stim175 | F1 → FLAW: the reason in sentence 1 is false "under the analyst's own account" | ADOPTS, CONDITIONAL — "If the analyst's later sentences define… then the reason is indeed false… the contest shows the finding is mistaken" | INVALID |
| python800-p03609 | F1, F2 → FLAW: "subtraction alone is not the correct approach" for t > X | ADOPTS — "misleading because it suggests… without acknowledging that clamping is also necessary" (incompleteness, excluded by the definition) | INVALID ×2 |
| surgery-sur53 | F3 → FLAW: "higher sensitivity for small-bowel lesions" is misleading for an acute bleed | ADOPTS, HEDGED — "raises a valid point that… might be misleading… upon closer examination the contest shows" | INVALID |
| theoremqa econ_micro_4 | F1, F3 → FLAW: "a few possibilities" is a partial enumeration, so "Therefore" is an invalid inference | ADOPTS — "the text contains a flaw due to the invalid inference from a partial enumeration" (informality, excluded) | INVALID ×2 |

**5/5 arguable, 0/5 certain; 5/5 adopt, 0/5 show; 2/5 hedged or conditional.** Every
contest sought FLAW on a SOUND list; none of the five texts is flawed on my reading. This
is jd6's mechanism on a local object: the weak recourse judge does not hold the finding's
ruling against an arguable contest.

## (b) recourse FIXED a wrong decision — 5 of 285, all F-weak, all gold FLAWED

| cell | route | the ruling | on the annotated flaw? |
|---|---|---|---|
| lojban-stim158 | F1 flip | SHOWS (partly via Alice's analysis): sentence 11 asserts a false grammatical fact and "a conclusion that asserts a falsehood is flawed even if it follows from its premises" | VALID |
| lojban-stim168 | F1 flip | ADOPTS Bob ("Bob's critique… is valid") | INVALID — not the annotated flaw; right verdict, other ground |
| lojban-stim182 | upheld OMISSION appended as FLAW ("false comparative judgment") | two-step done ("it is a real omission"), then rules the point | INVALID — grader: covered by Finding 2 in substance |
| python800-p02787 | F2, F3 flips (F1 refused) | mostly ADOPTS ("implies the handling is correct, which is misleading due to the −1") | VALID ×3 (the endorsement of the −1 bug) |
| theoremqa abstract_algebra_7_4 | F1 flip + appended omission | SHOWS — redoes the arithmetic: `a*(b*c) = a+(b*c)+3`, the finding's own reason compared the wrong expressions | C1 VALID; C2 INVALID (a consequence) |

**3/5 fixes on the annotated flaw, 2/5 for another reason; routes 3 flips, 1 omission, 1
flip+omission; 2/5 show, 3/5 adopt.** The abstract-algebra cell is the designed object
working as intended: the challenger caught an error inside the finding's *Reason:* (the
associativity check dropped the outer +3), quoted the finding's own words, and the ruling
verified the computation. It is the only certain-grade contest in the twenty read.

## (c) an APPENDED finding — 5 of 62 (3 weak, 2 strong), all gold FLAWED, no verdict moved

| cell | arm | the appended point | grade |
|---|---|---|---|
| python800-p02767 | strong | "the analysis's conclusion that the solution is incorrect is itself incorrect" — the conclusion, after findings on its reasons | VALID |
| python800-p03240 | weak | "the analysis fails to identify the nonsensical condition" — an omission *in the text*, which the definition excludes; Maverick ruled FLAW | INVALID |
| python800-p03250 | strong | the final "the code correctly solves the problem" after two findings on its reasons | INVALID — covered by Finding 2 |
| theoremqa modulararithmetic5 | weak | "the inference from the false premise is invalid" — a consequence of Finding 1 | INVALID — consequence |
| theoremqa abstract_algebra_7_4 | weak | "Step 5's conclusion is false" — a consequence of Finding 1 | INVALID — consequence |

**4/5 are consequences of a listed finding (a conclusion drawn from a premise already
ruled), 1/5 an omission in the text.** The "covered in substance" rule does not hold
against a consequence: both judges append the conclusion of a finding they already made.
None of these five changed a verdict (the lists were FLAWED already); across the arm, 18
of the weak arm's 51 appended findings did.

## (d) F-weak and F-strong disagree on the before-verdict — 5 of 464

| cell | gold | weak list → contest → after | strong list → contest → after |
|---|---|---|---|
| gpqa-129-flawed | FLAWED | FLAW (right); declined | NOT A FLAW (wrong: "410 nm is a textbook simplification"); contested → REFUSED; stays wrong |
| medqa-train_0448 | FLAWED | 3 × NOT A FLAW (wrong); 2 contests GRANTED → FIXED (VALID) | 1 FLAW (right); declined |
| medqa-dev_0101 | SOUND | NOT A FLAW (right: "cysts" for oocysts is terminology); contested → GRANTED → BROKEN | FLAW (wrong, same terminology point); declined |
| python800-p02912-sound | SOUND | NOT A FLAW (right); contested → GRANTED → BROKEN | FLAW (wrong: "the correction would still NameError"); declined |
| python800-p03473-flawed | FLAWED | 3 × NOT A FLAW (wrong); 3 contests GRANTED → FIXED (VALID) | 2 × FLAW (right); declined |

**Weak arm: contested 5/5, granted 5/5 — 2 fixes, 2 breaks, 1 decline. Strong arm:
declined 4/5, refused the one contest, on the one cell where the challenger was right.**
Whichever way Maverick's list goes, the contest moves it; luna's list stays where it is.
The two judges' errors are of different kinds: Maverick under-calls (SOUND-heavy),
luna over-calls on technicalities (a terminology point, a NameError in a proposed fix).

## (e) the phantom instrument's two blind spots — 20 objections

**(e1) ten REVERSE objections (7 weak, 3 strong; 13 contests): 0 phantoms.** Every
`Why:` argues the direction its `Should be:` claims; the three omission contests each
name a point the FLAWED-side debater made. Two contests are pedantic ("literally untrue",
"coincidentally correct") but are not phantoms.

**(e2) ten STANDS with a non-empty `Argument:` (6 weak, 4 strong): 0 prose attacks.** All
ten are the template sentence "The findings are correct and complete." — a decline that
criticises a finding in prose without an entry did not occur in the draw.

The mechanical phantom column (weak 1/1633, strong 0/1644) stands.

## What the read says

1. **The break side is adoption of arguable contests**, 5/5 in (a) and 2/2 in (d): the
   weak recourse judge grants a NOT A FLAW → FLAW contest that re-argues the debate,
   restating it as "the contest shows", twice on a hedge or a conditional the ruling
   prompt bars. jd6's finding on a local object.
2. **The fix side is real but only sometimes on the annotated flaw** — 3/5 in (b), and
   two of the three by adoption. The designed object (a checkable error inside a
   finding's reason) fired once in the twenty contested cells read.
3. **Appended omissions are mostly consequences**, 4/5 in (c); the "covered in
   substance" rule does not stop a judge from appending the conclusion of a finding it
   has already ruled.
4. **The two judges fail in opposite directions** and the challenger only pushes toward
   FLAW, so recourse can only correct the weak judge's under-calls and only break its
   right SOUND verdicts — the verdict-side split in the derivation is the same fact.
5. **The instruments are clean**: no phantom in either blind spot, no private text or
   gold above the ground-truth section in any of the forty documents, every ruling
   line present and applied as the code says it was.

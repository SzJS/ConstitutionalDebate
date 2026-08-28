# judgment-debate — hand check A: 20 objection + grade pairs (Fable, 2026-08-28, seed 0)

10 graded valid, 10 graded invalid, drawn from the 1,148 objections of the full run.

**Valid (10/10 agree with the grader).** Every valid objection names a specific record
passage and the grader locates it before ruling. Omissions cite the debater's argument the
judgment never engaged (python800-p03031: Bob's "a restatement of the code is not a proof";
python800-p02747: Alice's "the analyst said it *will* result in a NameError"); misstatements
quote the judgment's sentence and the record's contrary one (surgery-sur54: "gratitude in
anticipation" vs Alice's "the act of reading is the consideration"; python800-p02788: a
wrong range formula `[x-D+1, x+D-1]` against Alice's `[x-1, x+2D-1]`); contradictions quote
both halves (python800-p03147). Two of the ten carried one invalid defect beside the valid
one, and the grader split them correctly (theoremqa-statisticalphysics3, gpqa-160).

**Invalid (10/10 agree with the grader).** Rejections are for the right reasons and stated:
a substantive disagreement with a debater is not a misstatement (python800-p03005,
law-evi5_gpt4); a point the judgment engages and rejects is not omitted (theoremqa
Wallis-theorem1, python800-p03573, medqa-dev_0539, medqa-dev_0646); "technically correct
under the definition" is not a contradiction within the judgment (python800-p03101); a
paraphrase that preserves the position is not a misstatement (medqa-train_2584,
theoremqa-rate_distortion_2 — the one I would call a judgement call: "will not decrease"
for "may increase"). One rejection is on quotation grounds: python800-p02819 quoted the
flaw *definition* as "the record says", and the definition is in the prompt, not the record.

**0 of 20 objections carried a quotation that was not in the judgment**, matching the run's
misattributed_quote rate of 0.0% on the debate corpus.

# judgment-debate — hand check B: rulings, weighted to `ruling_line_mismatch` alarms (Fable, 2026-08-28)

The full run's alarm rate is 349/1,148 = 30% (pilot-2: 16%). Split by (overturned, the
materiality reader's answer): **156** upheld & reader says CHANGED; **79** overturned & reader
says STANDS; **102** reader NEITHER (88 upheld, 14 overturned); 12 other. I read the Step-2
endings of 12 from the first group and 8 from the second (seed 4), plus 20 rulings from
the seed-0 sample (12 alarms, 8 quiet).

## Group 1 — upheld, prose read as CHANGED (156): the reader is right, 12/12

Every one of the twelve finds the alleged defect **real and material** in Step 2 — "this
misrepresentation materially affects the reasoning and conclusion", "the judgment's
reasoning is flawed" — and then ends on the parent's own Conclusion line. Under the ruling
prompt a material defect is by definition one that changes what is true of the text, so a
material finding followed by the parent's line is the judge contradicting its own rule.
The mechanism is visible: the judge writes "the original *judgment* is flawed" and then
"the original text contains a flaw" — the nesting collision one layer up, "flawed" applied
to the judgment and to the solution in consecutive sentences. **Ten of the twelve were
correct decisions** (gold agrees with the parent): the prose over-finds materiality in
judgments that were right, and the instruction to copy the parent's line when the decision
stands is what kept them right.

## Group 2 — overturned, prose read as STANDS (79): the line follows the prose's last sentence, 8/8

All eight say the alleged defect is **not** real or not material — "both alleged defects
are unsupported by the record", "no material flaw is demonstrated" — and then conclude
that the text does not contain a flaw and overturn. The reader answered STANDS by the
rule (no material defect → the decision stands); the judge instead re-decided the item
on object-level grounds and its line matches that. So these are not line-vs-prose
contradictions in the old sense; they are the judge setting the materiality rule aside
and re-judging, which is the confound `PREREG.md` names, occurring inside the new prompt.
Four of the eight ended correct, four wrong.

## The 20 seed-0 rulings

The two-step structure is present in 20/20 (Step 1 quotes the record before ruling on
each defect; Step 2 argues materiality). Among the 12 alarms: 7 are group 1 (material →
parent line), 3 are group 2, 2 are reader abstains on prose that plainly stands
(gpqa-19-style). Among the 8 quiet rulings the line follows the prose in 8/8.

## What this settles

* `ruling_line_mismatch` = 30% is **not** a measurement of the reader's error: on the two
  large groups the reader is right about what the prose says (12/12 and 8/8).
* It is a measurement of the weak judge's coherence under the materiality prompt: its
  Step-2 verdict on materiality and its final line disagree in ~20% of rulings, in both
  directions, and the parent-line anchor is doing real work in the upholds.
* The post-hoc "prose wins" recomputation (derivation §f) is the sensitivity check: it
  flips ~156 upholds to overturns and ~79 overturns to upholds. It is descriptive and
  post hoc; the pre-registered endpoint is the line, as the run produced it.

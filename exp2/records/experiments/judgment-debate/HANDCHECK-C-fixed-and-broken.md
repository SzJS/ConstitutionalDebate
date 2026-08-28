# judgment-debate — hand check C: 10 fixed and 10 broken cells, end to end (Fable, 2026-08-28, seed 0)

**Fixed (wrong → right), 10.** In 9 the ruling's Step 1 finds the alleged defect real and
Step 2 finds it material, and the overturn follows from it: gpqa-16 (the assumption
contradicts the text's own equilibrium constant), theoremqa-center_of_mass1 (the
problem's own wording settles displacement vs position), python800-p03076 (the modulo
"handles" claim is shown false by the record's own arithmetic), python800-p02755 ("with
this change the code should correctly solve the problem" is a claim the fix suffices).
One (python800-p03592) is the residual in the fixing direction: the prose concludes "the
alleged defect is not real … cannot be material" and the line overturns anyway — a lucky
fix.

**Broken (right → wrong), 10.** Three are the residual in the breaking direction — prose
says the defect is not real or not a clear misstatement, line overturns: python800-p03464,
python800-p02880 ("the question of materiality does not arise" → overturned),
python800-p02760. The other seven are genuine materiality rulings that were wrong on the
merits: the judge sided with a debater's point that the dataset label says was the losing
one (gpqa-54: "untrue" as a standalone criterion; law-evi1: "technically correct" vs SOUND;
medqa-dev_0068; surgery-sur53; gpqa-39; medqa-train_3221; python800-p03371). In those the
two-step structure is present and the reasoning is coherent; the weak judge is simply
wrong about which side the record supports.

So in this sample the line-vs-prose residual accounts for ~3 of 10 broken and ~1 of 10
fixed cells. The post-hoc "prose wins" sensitivity recomputation in the derivation is
what quantifies it on all 1,644; it is not the pre-registered endpoint.

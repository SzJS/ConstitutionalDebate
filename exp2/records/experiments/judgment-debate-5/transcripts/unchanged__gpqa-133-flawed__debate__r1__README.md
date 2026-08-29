# `gpqa-133-flawed` — a real objection the change did not disturb

**Arm B (real audit), `outputs/experiments/jd5-recheck-real`. M1: OVERTURN. jd5: OVERTURN.
A WRONG decision fixed under both prompts.** One of the **189** cells where both rulings
overturn — the concordant majority that the paired table's margins are made of and that a
reader looking only at the 171 discordant rulings would never see.

The objection alleges a **contradiction** and quotes two sentences of the judgment, both real:
the judgment says *"The flaw lies in the misinterpretation of the problem's requirement and the
incorrect identification of the limiting reagent"* and then *"Verdict: SOUND"*.

`ruling.json`, Step 1 under the new prompt:

> "The first quotation **is found in the judgment** … The second quotation **is also found**:
> 'Verdict: SOUND'."

and it goes on to call the contradiction real, call it material, and overturn — the same
conclusion M1 reached in `ruling.source.json` without ever looking either sentence up.

**What to look at.** This is the half of `PREREG.md`'s smoke gate that passed outright, at
scale: **the existence check does not turn the judge into a proofreader.** An objection whose
quotations are there is confirmed and then judged on its merits, and the outcome is the one the
old prompt reached. `CHECKLIST.md` section 4 puts a number on the same thing across the arm —
arm B's rulings report a MISSING quotation on **3.0%** of cells against arm A's **93.1%**.

**And note what it cost to check.** The lookup is two sentences long here. The cheapness of the
check is not in dispute in either arm; what the campaign cannot settle is what else the
paragraph did.

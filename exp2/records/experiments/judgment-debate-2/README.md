# judgment-debate-2 — the abandoned chain. **A record of an instrument, not a result.**

This directory holds the pre-registration this chain ran under and the indexes of its three
**finished** arms. It exists so that `LLM_NOTES.md` §3y's prelude table and
`../judgment-debate-3/CHECKLIST.md` §8 can be re-derived on a bare clone rather than taken on
trust. Nothing reads it.

## Why the chain was stopped

The debate-only run (`../judgment-debate/`) netted **+45, p = 0.011**, with `gpt-4.1-nano` as
the debate judge *and* the recourse judge. This chain re-ruled that run's same 1,148
objections with two **flash-class** judges and got **+124** and **+114**.

**Those numbers are the problem, not the result.** Both judges are **stronger than the nano
that judged the debates**, so "debate + recourse beats debate alone" could be nothing more
than "a better judge re-decided". The user's decision on 2026-08-28 was to **remove the
asymmetry rather than model it**, and the chain was stopped after its arm B —
`outputs/jd2-STOPPED-by-user.md` names the arms kept and cancelled. The whole design was
re-run as `../judgment-debate-3/` with `meta-llama/llama-4-maverick` in **both** judge seats,
at the challenger's own level. **With the asymmetry, +124. Without it, −18.**

## What is here

| directory | arm | what it is | fixed / broken / net | p |
|---|---|---|---|---|
| `arm-maverick-real/` | **A-mav** | nano's judgments and flash's objections, re-ruled by `meta-llama/llama-4-maverick` | 237 / 113 / **+124** | 3.06e-11 |
| `arm-mini-real/` | **A-mini** | the same, re-ruled by `openai/gpt-4.1-mini` | 233 / 119 / **+114** | 1.24e-09 |
| `arm-nano-placeholder/` | **B** | nano's placeholder second look, ruled by nano | 69 / 49 / **+20** | 0.0798 |

Each row is that arm's **own** before-state — nano's judgment of the sweep's debates —
against its own after-state, recomputed by `records/derivations/judgment-debate-3.py` from
these committed indexes. **They are not comparable with judgment-debate-3's P1**, whose
before-state is a different and much stronger judge's reading of the same transcripts
(73.7% against nano's 58.2%).

**Not here, deliberately:** `jd2-maverick-placeholder` (C-mav) was **killed partway** and its
tree must not be read as an arm; C-mini, D and both E arms were **cancelled**, and the
placeholder and specious ablations were re-run under one judge in `../judgment-debate-3/`.
The two six-cell specious smokes that chose the specious clause cost $0.3453 and their
reading is `outputs/jd2-specious-smoke-read.txt`.

Chain spend, from the trees' own wire logs: **$13.2755**.

## The one thing this chain did settle, and it is carried forward

**The judge-selection rule** in [`PREREG.md`](PREREG.md) — written before any candidate was
called: same class as the challenger (the ±5 band around its non-reasoning intelligence index
of 14), excluding the debaters', the challenger's and the grader's families; then, on 82
stored objections, strict ruling-line mismatch below nano's and discrimination at or above
nano's; highest net among those. **Maverick passed at index 14, delta 0**, and became
judgment-debate-3's judge; **`openai/gpt-4.1-mini` was the other in-band pass** and became
that phase's M4 gatekeeper. The rule is quoted in both of those decisions and neither was
re-scored.

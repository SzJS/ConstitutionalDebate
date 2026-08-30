# The three models' Artificial Analysis intelligence indices

Looked up 2026-08-30 for `records/experiments/judgment-debate-6/PREREG.md`. "The debaters
are stronger than the judge" is a PREMISE of the contestability debate round — the whole
hypothesis is that recourse fails because it is weak-vs-weak, and the round's only new
input is two STRONG parties — so it should be a checked fact and not an assumption.

Source: **[artificialanalysis.ai](https://artificialanalysis.ai/models)**, the per-model
pages below, read **2026-08-30**. Index version **v4.1.1** on every page read (nine
evaluations: GDPval-AA v2, tau-3-Banking, Terminal-Bench v2.1, SciCode, Humanity's Last
Exam, GPQA Diamond, CritPt, AA-Omniscience, AA-LCR). The comparison table at
`/models` is rendered client-side and returns none of these three to a fetch
(`LLM_NOTES.md` line 123 records the same about these client-side tables), so each figure below
comes from that model's own page.

| role in jd6 | model | index | variant scored | page |
|---|---|---|---|---|
| debaters (arms R and B) | `deepseek/deepseek-v4-flash-0731` | **52** | **Reasoning, Max Effort** — see the caveat | https://artificialanalysis.ai/models/deepseek-v4-flash |
| debate judge = recourse judge = re-judge | `meta-llama/llama-4-maverick` | **14** | the model has one variant | https://artificialanalysis.ai/models/llama-4-maverick |
| challenger (jd3 M1's; never called by jd6) | `google/gemini-2.5-flash` | **14** | **Non-reasoning** | https://artificialanalysis.ai/models/gemini-2-5-flash |

## THE ONE CAVEAT, AND IT MATTERS

**The 52 is the REASONING figure and this experiment runs the debaters with reasoning
OFF.** The page for DeepSeek V4 Flash scores only *"DeepSeek V4 Flash 0731 (Reasoning,
Max Effort)"*; it says a non-reasoning variant may exist but publishes no index for it.
Artificial Analysis has not measured what this experiment actually runs, so **the honest
statement is that the debaters' non-reasoning index is UNPUBLISHED, not that it is 52.**

What the numbers do support, and what PREREG.md should say:

* the judge is **weak by the same yardstick the judge-selection rule of
  `records/experiments/judgment-debate-2/PREREG.md` used** — index 14 with reasoning off,
  which is exactly where that rule placed it, and `LLM_NOTES.md` §3x records the same
  figure;
* the judge and the challenger sit at the **same** index (14 and 14), which is the
  deliberate design of `judgment-debate-3`: one weak model class throughout, so no
  stronger reader is imported into the decision path;
* the debaters are **from a materially stronger model** — 52 with reasoning on against
  14 — and the gap on the non-reasoning setting the run actually uses is not published
  and is not claimed here.

Gemini 2.5 Flash's non-reasoning 14 is *above* the median of its comparables (12) while
Maverick's 14 is *below* the median of its comparables (18); those medians are over
different comparison sets and the two 14s are the same index, so nothing follows from the
difference except that it is not evidence the two are unequal.

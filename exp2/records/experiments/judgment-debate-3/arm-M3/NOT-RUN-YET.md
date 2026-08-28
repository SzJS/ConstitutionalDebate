# M3 — the specious auditor. **NOT RUN YET.**

**Placeholder, written 2026-08-28 while the arm was still running.** Everything in this
directory's `README.md`, `CHECKLIST.md` and `../../../LLM_NOTES.md` §3y that refers to M3
says NOT RUN YET in the same words. Fable fills these in after the arm lands and after the
hand read; nothing may be written here from a partial tree.

## What it is

`experiments/jd3-specious.toml`: `decisions_from = outputs/experiments/jd3-main`, the
**specious** challenger (`challenger_variant = "judgment_specious"`, `google/gemini-2.5-flash`
under the clause spliced in on 2026-08-28 and byte-identical to the version that passed the
`jd2-specious-smoke-2` gate), ruled by Maverick under the same materiality prompt. It
contests **every** decided cell — the instruction forbids the decline — so its raise rate is
1.0 by construction and is not a detection rate.

Started **2026-08-28T15:37:17Z** by `outputs/jd3-run-all.sh` after M2; stages `contest
agreement ruling_agreement grade analyse`; estimate ≈ **$39**, ETA ≈ 18:00Z.

## What it answers, and the condition under which it answers nothing

**P3, pre-registered and descriptive** (`../PREREG.md`): the overturn rate on specious
objections against the rate on real ones, **on the overlap with M1's contested cells**, with
its n and its interval and **never tested at α** — the two populations are different
objections about the same cells, not a paired before/after. The cells outside the overlap
are reported separately and never pooled.

**The manipulation check comes first, and it is a stopping rule written before the arm ran.**
The grader runs on the specious objections unchanged and its valid-objection rate is the
evidence that they were specious at all. **It should be low.** If the grader validates most
of them, the instruction did not produce specious objections and **P3 is VOID** — a failed
manipulation, not a null result about sycophancy. `records/derivations/judgment-debate-3.py`
prints that branch instead of a comparison, and a test pins it.

Under this phase's design the question has an extra edge that the first run did not have:
the judge being pushed is the judge that wrote the judgment being objected to, so an
overturn here is a judge abandoning its own reasoning under pressure that carries no
information at all.

## Files that will land here

`index.jsonl`, `metrics.json`, `experiment.json` from `outputs/experiments/jd3-specious/`,
and this file replaced by an `arm-M3/README.md`. The derivation is re-run with `--specious`
pointed at the committed index, `derivation.log` is regenerated, and the M3 rows in
`../CHECKLIST.md` §1, §4 and §6 and in §3y stop saying NOT RUN YET.

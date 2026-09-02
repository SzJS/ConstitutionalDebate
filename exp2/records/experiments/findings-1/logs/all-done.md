# fd1 — both arms done, 2026-09-02T18:43:33Z

| arm | spec | decisions attempted | completed | failed | contests attempted | completed | failed | findings | verdicts | objections | rulings | after-lists | grades |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| W | `fd1-weak` | 3310 | 3288 | 14 | 1639 | 1631 | 8 | 1657 | 1657 | 1636 | 1067 | 1067 | 1070 |
| S | `fd1-strong` | 3288 | 3288 | 0 | 1644 | 1644 | 0 | 1644 | 1644 | 1644 | 606 | 606 | 606 |

The findings column is against **1644** decided debate cells in
`jd3-main`. Every list here was written by a judge under `judge_form =
"findings"`, and the verdict beside it was DERIVED from it by code rather than
stated by the judge.

**Failed cells are COUNTED, never absorbed.** Under `PREREG.md`'s missing-cell
rule a cell lost at rejudge has no before-state and leaves every table (and is
the numerator of the feasibility rate); one lost at contest leaves P1's pairing
and P2's denominator; one lost at ruling is contested with no after-state and is
never an uphold; one lost at grade or at the instrument stays in P1-P3 and leaves
that table alone. The derivation's section (0) lists each with the error that
lost it, per stage and per arm, and breaks the rejudge losses down by subset.
`--retry-failed` was on, so a cell failed at rejudge here failed TWICE.

`jd3-main` byte-identical before and after: `dfa9bdca3fe93630701b4659cdb4ac8605ce07d58b29c29ad868c1048c12209c`.

Hashes in `outputs/fd1-fingerprints.md`.

Next: `uv run python records/derivations/findings-1.py`.

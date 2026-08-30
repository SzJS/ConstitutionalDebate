# jd6 — both arms done, 2026-08-30T05:30:49Z

| arm | spec | attempted | completed | failed | rulings | two-turn rounds | decisions | four-round |
|---|---|---|---|---|---|---|---|---|
| R | `jd6-round` | 896 | 855 | 41 | 855 | 856 | 0 | 0 |
| B | `jd6-plain` | 896 | 886 | 10 | 0 | 0 | 886 | 886 |

**Failed cells are COUNTED, never absorbed.** Under `PREREG.md`'s loss rule a
cell missing in either arm leaves every paired table; the derivation's section (0)
lists each one with the error that lost it. `--retry-failed` was on, so a cell
here failed TWICE, and because the debaters run at temperature 0.7 a retried cell
was a different draw rather than a repeat.

`jd3-main` byte-identical before and after: `dfa9bdca3fe93630701b4659cdb4ac8605ce07d58b29c29ad868c1048c12209c`.

Hashes in `outputs/jd6-fingerprints.md`.

Next: `uv run python records/derivations/judgment-debate-6.py`.

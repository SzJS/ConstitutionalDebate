# judgment-debate-6 IS DONE. DO NOT RE-RUN IT.

Both arms ran on **2026-08-30, 02:28:23Z → 05:30:49Z — 3 h 02 m**, `$11.9847` on the wire,
**6,401 calls with 0 non-2xx**, five stages across two arms, every one exit 0.
`outputs/jd6-ALL-DONE.md` is the driver's own marker and `logs/all-done.md` is its copy.

| arm | spec | attempted | completed | failed | two-turn rounds | four-round transcripts |
|---|---|---|---|---|---|---|
| R — the contest round | `jd6-round` | 896 | **855** | 41 | 856 | — |
| B — the plain round | `jd6-plain` | 896 | **886** | 10 | — | 886 |

`outputs/experiments/jd3-main` — read by both arms and written by neither — was
`dfa9bdca3fe93630701b4659cdb4ac8605ce07d58b29c29ad868c1048c12209c` before the first arm,
between the arms and after the last. See `logs/fingerprints.md`.

**Re-running costs $12 and re-decides cells that are already decided.** Everything a reader
needs is here: read [`CHECKLIST.md`](CHECKLIST.md) §0 first, then
[`HANDCHECK.md`](HANDCHECK.md), then `LLM_NOTES.md` §3ab. Every number is re-derivable on a
bare clone with `uv run python records/derivations/judgment-debate-6.py`, whose defaults
point at the indexes in this directory.

## The result, in three lines

**P1 FAILED and P2 HELD, and the pair is a SPLIT that is not any of the four named
outcomes.** On the 583 initially-CORRECT cells both arms decided, the contest round broke
**176** that the plain round kept and the plain round broke **62** that the contest round
kept (exact two-sided McNemar **p = 7.9e-14**) — R breaks **more**, which is the opposite of
P1. On the 263 initially-WRONG cells, R fixed **98** that B did not against B's **35**
(**p = 4.3e-08**) — P2 holds.

**The contest round is more interventionist in both directions**, and the hand check says
the mechanism is **adoption**: the weak judge reproduces one strong reply, structurally the
PRO one. `PREREG.md`'s rule is that a split is reported as the split it is and never rounded
to whichever named outcome it is nearest. It is not rounded here.

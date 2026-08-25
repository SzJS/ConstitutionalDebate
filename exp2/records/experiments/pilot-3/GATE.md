# pilot-3 — the Step G gate

Applied 2026-08-25 by Fable (the planning agent), from
`outputs/experiments/pilot-3/CHECKLIST.md`. The gate is the one in the plan
(`/root/.claude/plans/eager-exploring-island.md`, Step G): **permissive by the user's
instruction — proceed to the sweep slice unless pilot-3 was catastrophic.**

| # | condition | stop only if | pilot-3 measured | verdict |
|---|---|---|---|---|
| 1 | decided cells | < 70% | **177/207 = 85.5%** | pass |
| 2 | verdicts | every condition > 95% one class | max class share **55.9%** (single) | pass |
| 3 | challenger | zero `contests` **and** zero `declined` | **30 contests + 147 declines**, zero `unclear` | pass |
| 4 | containment | `Thinking:` leaks in > 5% of challenger-visible records | **0 leaks in 204 records** | pass |
| 5 | ops | a stage crashed, or pinned-provider failures > 25% of calls | **0 non-200 in 1,679 attempts**; no stage crashed | pass |

## PASSED

All five rows pass with margin. Proceed to `sweep-1`.

**What is carried into the slice as a known number, not fixed:** the 30 cells lost to
truncation (14.5%, 13 of them a critique truncating past its own `Reasoning:` label),
the 22.5% format-repair rate on the pinned pair, the 43.3% phantom-contest rate, and the
2-row grading cell. CHECKLIST rows 1 and 2 FAIL against their own thresholds; neither is
a gate row, and the plan says explicitly that a high repair rate, phantom contests and a
dead cell or two are carried, not gated.

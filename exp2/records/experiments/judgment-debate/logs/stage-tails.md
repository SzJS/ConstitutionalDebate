# Stage log tails — the full run

The stage logs themselves are under `outputs/` and are git-ignored (they carry
every wire line). These are their last lines: the per-stage cell counts and the
cumulative spend the driver printed.

```
=== run_sweep: contest  2026-08-28T01:48:17Z  -> outputs/judgment-debate-contest.log ===
=== run_sweep: contest exited 0  2026-08-28T03:05:11Z ===
=== run_sweep: agreement  2026-08-28T03:05:11Z  -> outputs/judgment-debate-agreement.log ===
=== run_sweep: agreement exited 0  2026-08-28T03:08:50Z ===
=== run_sweep: ruling_agreement  2026-08-28T03:08:50Z  -> outputs/judgment-debate-ruling_agreement.log ===
=== run_sweep: ruling_agreement exited 0  2026-08-28T03:11:57Z ===
=== run_sweep: grade  2026-08-28T03:11:57Z  -> outputs/judgment-debate-grade.log ===
=== run_sweep: grade exited 0  2026-08-28T03:18:17Z ===
=== run_sweep: analyse  2026-08-28T03:18:17Z  -> outputs/judgment-debate-analyse.log ===
=== run_sweep: analyse exited 0  2026-08-28T03:18:22Z ===

contest: completed=1643  failed=1  skipped=466
spend so far: $20.4895 over 1644 run directories
agreement: completed=1644  skipped=466
spend so far: $22.5587 over 1644 run directories
ruling_agreement: completed=1147  skipped=963
spend so far: $25.0959 over 1644 run directories
grade: completed=1148  skipped=962
spend so far: $33.9371 over 1644 run directories
```

## Format repairs, by shape (contest stage)

```
   1270 exp2.engine challenger output malformed (label_not_at_line_start)
    318 exp2.engine challenger output malformed (no_public_label)
     44 exp2.engine recourse_judge output malformed (missing_decision_line)
```

## The one failed cell

```
2026-08-28 02:10:56,064 WARNING exp2.experiment lojban-stim181_gpt4_B-s5__debate__r1 contest failed: comprehension response stopped on finish_reason='error' at max_tokens=16384. A truncated argument would enter the public transcript as if authored, so this is fatal. Raise max_tokens, or check whether native reasoning is consuming the budget.
```

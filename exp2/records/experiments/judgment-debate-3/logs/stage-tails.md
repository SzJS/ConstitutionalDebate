# Stage tails — what each stage of each arm reported, verbatim

Copied from the per-stage logs under `exp2/outputs/` (git-ignored). Every figure quoted in
`README.md`, `CHECKLIST.md` and `LLM_NOTES.md` §3y for spend, counts and failures comes from
here or from the arm's own `index.jsonl` / `metrics.json`.

The orchestration log is `outputs/jd3-run-all.log`; the driver is `scripts/run_sweep.sh`,
launched with `--retry-failed` (the user's standing resume rule of 2026-08-26, `HANDOFF.md`
§5), and every arm's stages ran sequentially under one process.

## The sweep tree, before and after

    fingerprint sweep 5e2eb4d69ecabcce77533fd84a75e6d8d7c6a7676a00b05701737229bdfd2d2f   (before M0)
    fingerprint sweep 5e2eb4d69ecabcce77533fd84a75e6d8d7c6a7676a00b05701737229bdfd2d2f   (after M0+M1)

**Byte-identical.** The 1,644 debate transcripts were read through `transcripts_from` and
nothing was written into the tree that holds them.

    fingerprint jd3-main dfa9bdca3fe93630701b4659cdb4ac8605ce07d58b29c29ad868c1048c12209c   (after M0+M1)

## M0 + M1 — `jd3-main`, 2026-08-28T11:43:59Z → 14:43:04Z (2 h 59 m), every stage exit 0

| stage | exited | result line | cumulative spend |
|---|---|---|---|
| `rejudge` (M0) | 12:37:31Z | `completed=1644  skipped=466` | $2.0053 |
| `contest` (M1) | 14:32:04Z | `completed=1642  failed=2  skipped=466` | $21.8621 |
| `agreement` | 14:35:16Z | `completed=1643  skipped=467` | $23.7349 |
| `ruling_agreement` | 14:37:50Z | `completed=895  skipped=1215` | $25.6104 |
| `grade` | 14:42:59Z | `completed=896  skipped=1214` | **$32.6568** |
| `analyse` | 14:43:04Z | `indexed 1644 rows -> outputs/experiments/jd3-main/index.jsonl` | — |

`skipped=466` in `rejudge` is the sweep's undecided debate cells: they have no stored
transcript to re-judge and are in no arm. **0 of 1,644 Maverick judgments truncated or
failed to parse.**

**The two `contest` failures, named:**

    ! python800-p03567-flawed__debate__r1: TruncatedOutputError: comprehension response stopped
      on finish_reason='error' at max_tokens=16384
    ! python800-p03970-flawed__debate__r1: TruncatedOutputError: recourse_judge response stopped
      on finish_reason='error' at max_tokens=16384

Both cells are in the index and both are **concordant** — `final_correct == initially_correct
== true` for each — so neither enters any discordant pair and neither can move a net. The
first declined before it failed; the second contested and lost its ruling.

## M2 — `jd3-placeholder`, 14:43:50Z → 15:37:17Z (53 m), every stage exit 0

| stage | exited | result line | cumulative spend |
|---|---|---|---|
| `contest` | 15:34:39Z | `completed=894  failed=2  skipped=1214` | $1.3417 |
| `ruling_agreement` | 15:37:13Z | `completed=894  skipped=1216` | **$3.1095** |
| `analyse` | 15:37:17Z | `indexed 1644 rows` | — |

**The placement assertion fired, and `CHECKLIST.md` §0.2 is where it is accounted for:**

    placeholder placement: 894 objections stand where outputs/experiments/jd3-main raised 896
      — DOES NOT MATCH.
    ! the second-look control is NOT paired with the arm it controls for. Do not read a P2
      comparison off this tree until the difference is accounted for cell by cell.
    ! gpqa-193-flawed__debate__r1: TruncatedOutputError: recourse_judge response stopped ...
    ! medqa-train_1133__debate__r1: TruncatedOutputError: recourse_judge response stopped ...

## M4 — `jd3-gatekeeper`, 14:48:03Z → 15:01:21Z (13 m 18 s), every stage exit 0

| stage | exited | result line | cumulative spend |
|---|---|---|---|
| `gatekeeper` | 15:01:17Z | `completed=896  skipped=1214` | **$2.2585** |
| `analyse` | 15:01:21Z | `indexed 1644 rows` | — |

M4 was launched by hand rather than by `jd3-run-all.sh` and its window (14:48–15:01Z)
**overlaps M2's** (14:43–15:37Z). Two paid stages ran at once, against `HANDOFF.md` §2 rule
6. Recorded here because it happened; nothing in either arm depends on the other, both trees
read `jd3-main` and neither writes to it, and no rate-limit or provider failure appears in
either log.

## M3 — `jd3-specious`, started 15:37:17Z. **NOT RUN YET** — see `arm-M3/NOT-RUN-YET.md`.

## Wire health, counted from each tree's own `calls.jsonl` (excluding copied `parent/` logs)

| arm | calls | non-2xx |
|---|---|---|
| `jd3-main` | 10,842 | **1** — one `ConnectError: Temporary failure in name resolution` on a challenger call for `python800-p03632-flawed`, retried by the client and completed |
| `jd3-placeholder` | 1,791 | 0 |
| `jd3-gatekeeper` | 896 | 0 |

## The six-cell admissibility smoke — `gates/SMOKE-admissibility-6-cells.txt`

`experiments/jd3-gate-smoke.toml`, 2026-08-28, **$0.0151**, `gatekeeper: completed=6`.
6/6 parsed `strict`, 0 format repairs, 0 line-vs-findings mismatches, 4 admitted / 2 refused,
and — read after `jd3-main`'s grade stage landed — **8/8 per-defect agreement with the
grader**. Read before M4 ran, per the standing prompt rule.

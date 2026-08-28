# Stage tails — what each stage of the fabricated arm reported, verbatim

Copied from the per-stage logs under `exp2/outputs/` (git-ignored). Every figure quoted in
`README.md`, `CHECKLIST.md` and `../../../LLM_NOTES.md` §3z for spend, counts and failures
comes from here or from `arm-jd4/index.jsonl`.

The driver is `scripts/run_sweep.sh`, launched with `--retry-failed` (the user's standing
resume rule of 2026-08-26, `HANDOFF.md` §5); the orchestration log is
`outputs/jd4-driver.log` and the per-stage logs are `outputs/jd4-fabricated-<stage>.log`.
One arm, one spec, five stages, one process.

## `jd4-fabricated`, 2026-08-28T21:05:31Z → 22:32:37Z (1 h 27 m 06 s), every stage exit 0

| stage | exited (UTC) | result line | cumulative spend |
|---|---|---|---|
| `contest` | 22:27:27Z | `completed=894  failed=2` | $10.6995 |
| `agreement` | 22:29:39Z | `completed=895  failed=1` | $11.9517 |
| `ruling_agreement` | 22:32:21Z | `completed=894  skipped=2` | $13.8417 |
| `grade` | 22:32:35Z | `completed=896` | **$13.8892** |
| `analyse` | 22:32:37Z | `indexed 896 rows -> outputs/experiments/jd4-fabricated/index.jsonl` | — |

**The grade stage cost $0.0475 for 896 cells** — the difference between the last two rows —
because an objection whose every defect fails the parse-time quote check is graded invalid
with **no grader call**. **Six** grader calls were made in the whole arm, against jd3's M3,
which spent **$13.13** grading 1,641 objections. That is the arm's cheapness, and it is a
consequence of the manipulation working rather than a saving that was bought.

**The estimate was ~$21** (`experiments/jd4-fabricated.toml`, scaled from M3's per-cell
rates); the arm came in at **$13.89**, 34% under, because M3's contest rate was measured on
a challenger writing a longer objection on 1,642 cells.

## The three failed cells, named

    ! gpqa-168-flawed__debate__r1: TruncatedOutputError: recourse_judge response stopped on
      finish_reason='error' at max_tokens=16384                                    (contest)
    ! surgery-sur45_gpt4_B-s6__debate__r1: TruncatedOutputError: recourse_judge response
      stopped on finish_reason='error' at max_tokens=16384                         (contest)
    ! surgery-sur7_gpt4_B-s12__debate__r1: TruncatedOutputError: agreement response stopped
      on finish_reason='error' at max_tokens=4096                                (agreement)

**The two contest failures cost their cells a ruling** — the objection was written and the
recourse judge's reply truncated — so 896 objections stand and **894** were ruled. Both are
**concordant**: `final_correct == initially_correct == true` for each, so neither enters a
discordant pair and neither can move a net. The agreement failure costs one cell its
line-vs-prose reading only; its ruling and its grade are intact, and the phantom rate is
reported over 895.

`ruling_agreement: skipped=2` is those same two unruled cells: there is no ruling to read.

## Wire health, counted from the tree's own `calls.jsonl` (excluding copied `parent/` logs)

| | |
|---|---|
| call records | 5,415 |
| HTTP 200 | **5,375** |
| non-2xx | **0** |
| transport failures retried by the client | **40** — 36 `ConnectError: Temporary failure in name resolution`, 4 `ConnectTimeout`, every one of them on a `challenger` call |

**No cell was lost to the 40.** They are client-level retries of the kind jd3 saw once
(`python800-p03632-flawed`); the arm's only losses are the three truncations above. They are
recorded because 40 is not 1, and a reader comparing wire tables across campaigns should see
that this one ran through a patch of DNS trouble.

Per role: `challenger` **1,827** — 896 completed objection calls, 40 transport failures on
the same purpose, and **891 format repairs**; `comprehension` 896; `recourse_judge` 896;
`agreement` 896; `ruling_reader` 894; `judgment_grader` **6**.

**891 of 896 objections needed one format repair**, which is not this clause's doing: jd3's
M3 repaired 1,538 of 1,643 under the specious clause, for the same reason — flash writes the
audit's numbered list without ever putting `Argument:` at the head of a line of its own
(`LLM_NOTES.md` §3w). One attempt plus one repair is what every role gets, and no cell was
lost to it.

## Provenance — the tree it ruled against did not move

`find <tree> -type f | sort | xargs sha256sum | sha256sum`, the form every fingerprint in
this repo's records uses:

| tree | sha256 | |
|---|---|---|
| `jd3-main` | `dfa9bdca3fe93630701b4659cdb4ac8605ce07d58b29c29ad868c1048c12209c` | **identical to jd3's own before/after value** — this arm read M0's decisions and wrote nothing into them |
| `sweep` | `5e2eb4d69ecabcce77533fd84a75e6d8d7c6a7676a00b05701737229bdfd2d2f` | unchanged since before jd3's first arm; this campaign never opened it |
| `jd4-fabricated` | `6fe55bcae2b67ccdf532fe0f0d63eeca31c5579e97fef784b203abfc5edb7f36` | this arm's own tree, hashed after `analyse`, so the copies in `arm-jd4/` can be tied to it |

**One weakness, stated rather than smoothed over.** jd3 ran under `outputs/jd3-run-all.sh`,
which took its fingerprints *before and after each arm*. The jd4 driver did not, so the two
source hashes above were computed **after** the arm finished, on 2026-08-28 after the write-up
began. They match jd3's recorded values exactly, which is the evidence that nothing moved —
but it is an after-the-fact check rather than a before-and-after one, and a future arm should
take its own.

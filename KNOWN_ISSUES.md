# Known issues

Found by an adversarial review after the harness was built, **before any paid
run**. Nothing here has corrupted a result, because no result has been produced.
Every item must be closed before the first sweep.

Ordered by what they would do to a published number.

## BLOCKING — would produce plausible but wrong results

### 1. The challenger is shown an empty record for both solo arms

`load_run_record` returns an empty `Transcript` for a solo run (the body is in
`.trace`), `run_recourse` builds the challenger's view from `parent.transcript`,
and `build_challenger_messages` renders the record from `transcript.all_turns()`
alone. So a challenger contesting a `single` or `self_critique` decision sees:

```
<transcript>
[This is the first round; no arguments have been made yet.]
</transcript>
```

The research question is whether a challenger detects faults more easily given a
debate record than given a solo record. **The solo record is never shown.** Any
measured debate advantage would be partly "six turns of text versus none".

Three sub-faults in the same prompt:

- it states `Alice argues for 1. Bob argues for 2.` for a run in which no debater
  spoke — the exact falsehood `render_solo_record` refuses to print;
- the self-critique draft and critique never reach the challenger, defeating the
  stated reason for publishing them;
- `decision_grounds` is `verdict.raw`, which for a solo arm includes the agent's
  `Thinking:` — so a `visibility="public"` challenger is shown private reasoning
  while `Challenge.shown_private_reasoning` reports `False`.

**Fix:** give `build_challenger_messages` a `record_block` slot fed by a renderer
that handles both shapes, and pass `verdict.reasoning` rather than `verdict.raw`.

### 2. `seeded_case_for_solo` can only ever hand over the flawed seed

`types.seeded_case_for_solo` returns `error.seed` whenever an error exists, and
`""` when it does not. There is no way to run a solo arm on `sound_seed`. So the
debate arm has the correct reasoning in the room and the solo arms never do,
under any configuration — the arms are not matched, and the "same bytes in every
arm" claim holds for the flawed half only. The docstring describes a correct
condition that the code cannot express.

**Fix:** needs the error/correct condition to be an explicit parameter rather
than inferred from `error is None`.

### 3. `ErrorSpec.mechanism` is never written

Documented as "set post hoc by the runner"; nothing assigns it. `build_index`
reads `error.get("mechanism") or "genuine"`, so every row is labelled genuine and
the mechanism split — which `analysis.by_cell` calls load-bearing, because the
two error routes are biased in opposite directions — always renders one bucket
identical to `overall`. Related: the forced-error route itself is unbuilt, so
there is nothing yet to label.

## HIGH

4. **`run_stage_grade` and `run_stage_validate` are serial `await` loops**, each
   building a fresh `OpenRouterClient` per item. Their semaphores can never be
   contended. This violates `CLAUDE.md`'s explicit rule, and costs roughly an
   hour of wall clock per thousand contests.
5. **`run_stage_validate`'s resume check consults only the first cell directory**
   for a case, so arms added later are never validated and inherit a
   `cross_arm_match` computed without them.
6. **`create_recourse` runs outside the concurrency bound**, so every parent
   `copytree` + `tree_sha256` happens at once; and the parent is duplicated once
   per challenger × arm.

## MEDIUM

7. `analysis.funnel` counts ungraded rows as detection failures — running
   `--stage analyse` before `--stage grade` reports `found_the_flaw = 0/N` with a
   tight interval and no coverage figure.
8. `run_stage_validate` collapses conditions and repeats into one record per arm.
9. `funnel` raises `KeyError` on a genuinely missing column: `frame.get(col)`
   returns `None`, and `None == False` is a scalar, so `frame[False]` raises.
10. `run_stage_grade`'s docstring claims it skips location-only annotations; it
    does not (the clamp in `grade_objection` covers correctness, but the coverage
    figures do not mean what the docstring says).

## Fixed in this commit

`Ruling.to_dict` dropping `changed_the_decision` (headline revision rates were
pinned to 0/N with a confident interval); `parse_solo_output` publishing a
trailing private `Thinking:` coda; contest resume keyed on the run directory
rather than on `challenge.json`, which made failed contests permanently
un-retryable *and* invisible to the index, and made `--stage rule` a no-op after
`--stage challenge`; `run_stage_grade` aborting the whole stage on one unreadable
directory; a leaked file handle in the append sink; `aggregate_tree`
double-counting copied parent wire logs.

# Known issues

Found by an adversarial review after the harness was built, **before any paid
run**. Nothing here has corrupted a result, because no result has been produced.
Every item must be closed before the first sweep.

Ordered by what they would do to a published number.

## HIGH

1. **`run_stage_grade` and `run_stage_validate` are serial `await` loops**, each
   building a fresh `OpenRouterClient` per item. Their semaphores can never be
   contended. This violates `CLAUDE.md`'s explicit rule, and costs roughly an
   hour of wall clock per thousand contests.
2. **`run_stage_validate`'s resume check consults only the first cell directory**
   for a case, so arms added later are never validated and inherit a
   `cross_arm_match` computed without them.
3. **`create_recourse` runs outside the concurrency bound**, so every parent
   `copytree` + `tree_sha256` happens at once; and the parent is duplicated once
   per challenger × arm.

## MEDIUM

4. `analysis.funnel` counts ungraded rows as detection failures — running
   `--stage analyse` before `--stage grade` reports `found_the_flaw = 0/N` with a
   tight interval and no coverage figure.
5. `run_stage_validate` collapses conditions and repeats into one record per arm.
6. `funnel` raises `KeyError` on a genuinely missing column: `frame.get(col)`
   returns `None`, and `None == False` is a scalar, so `frame[False]` raises.
7. `run_stage_grade`'s docstring claims it skips location-only annotations; it
   does not (the clamp in `grade_objection` covers correctness, but the coverage
   figures do not mean what the docstring says).
8. **`analysis` does not intersect the arms.** `by_cell` conditions on
   `initially_correct == False`, and under outcome control `single` contributes
   every case while `debate` and `self_critique` contribute only what survived
   their steering route. Comparing detection across those denominators compares
   different case sets. The fix is a `matched_tasks(frame)` filter keeping only
   `task_id`s wrong in every arm, applied as a hard filter — see
   `design_decisions.md` §4b.

   **The intersection also has to be watched, not just applied.** Every case it
   drops was dropped by one of the construction's own refusals — a critique that
   caught the seeded flaw twice, a steered output that narrated its steer twice,
   an injector that rewrote the solution, a judge that resisted even under
   steering. Those are cheap to retry: sampling is nondeterministic, so
   regenerating a dropped case is a fresh draw rather than a re-run of the same
   failure. So if the intersection removes an appreciable share of the corpus,
   the response is to **regenerate the dropped cases** and only then decide
   whether what remains is enough.

   Two things that must not be quietly skipped when doing so. Regenerating
   selects for cases whose construction happens to succeed, which is a bias in
   the same family as the ones `design_decisions.md` §4 tabulates — how many
   attempts each case took should be recorded, not just whether it eventually
   worked. And a case that keeps failing after several draws is telling you
   something about that case rather than about sampling luck; it should be
   dropped and counted, not retried indefinitely.

## Fixed in this commit

**The challenger was shown an empty record for both solo arms** (was #1,
BLOCKING). `load_run_record` puts a solo run's body in `.trace` and returns an
empty `Transcript`; the recourse path read only `.transcript`. Four sub-faults,
all closed:

- the challenger's prompt rendered `EMPTY_TRANSCRIPT` for every solo parent, so
  a measured debate advantage would have been partly "six turns of text versus
  none". `build_challenger_messages` now takes a `DecisionRecord`
  (`RunRecord.challenger_view()`), which normalises both shapes, and refuses a
  bare `Transcript` with a `TypeError`;
- it stated `Alice argues for 1. Bob argues for 2.` for a run in which no
  debater spoke. The positions line now lives in a debate-only record block;
- the self-critique draft and critique never reached the challenger, defeating
  the stated reason for publishing them;
- `decision_grounds` was `verdict.raw`, which for a solo arm includes the
  agent's private `Thinking:` — so a `visibility="public"` challenger was shown
  private reasoning while `Challenge.shown_private_reasoning` reported `False`.
  `RunRecord.decision_grounds` is now shape-aware. It is **not** a blanket
  switch to `reasoning`: a judge that answers before explaining leaves that
  empty, so the debate shape still quotes `raw`.

A fifth, on the document side and not previously listed:
`render_recourse_record` emitted `## Positions` unconditionally, so contesting a
solo decision published a `transcript.md` asserting that Alice argued in a run
where nobody did — the exact false statement `render_solo_record` exists to
avoid, and it feeds `run_stage_validate` as well as a human reader.

**`ErrorSpec.mechanism` is never written** (was #3). Now stamped at decide time
by `RunWriter.record_mechanism`: `genuine` when the procedure reached the wrong
decision unaided, `manufactured` when it had to be steered, `constructed` when
no procedure ran. `build_index` no longer defaults it to `genuine`, which had
made the split in `analysis.by_cell` a default rather than a measurement.

**`analysis.token_balance` measured the wire, not the record** (was #9). It read
`decision_completion_tokens`, which is zero for a constructed `single` cell by
design, so it reported the arms as unbalanced for a reason unrelated to how much
record there is to attack. It now reads `decision_record_words` — what a
challenger actually has to read, and the quantity `next_steps.md` warns about.
Generation cost stays reportable through `decision_cost_usd` and
`aggregate_tree`; it is simply not this check.

**A steered model could say it had been steered.** Outcome control appends
`JUDGE_STEER` to a resisting judge's prompt and `CRITIQUE_STEER` to a critique's.
Both outputs are published: a steered judge's `raw` is rendered verbatim in
`transcript.md` **and** is what a challenger is shown as the decision's grounds,
and a steered critique's text and provider reasoning reach the challenger
through the solo record. A model that narrated its instruction would let a
challenger contest the instruction rather than the flaw, which measures nothing.
`grading.references_the_steer` now checks every steered output — `raw` plus the
provider reasoning channel, model-graded because the risk is paraphrase rather
than quotation — and the steered call is retried once before the cell is failed
with `steered_judge_referenced_the_steer` /
`steered_critique_referenced_the_steer`. Off the decision path, so containment QC
does not inflate the token balance it protects.

**The recourse roles were told a solo decision had been a debate.** The
challenger's view was fixed first; the *recourse judge* was not. It was told
"Alice argues for 1", shown either an empty transcript (judge-only) or the
recourse exchange alone (with rounds), and told "A judge read the transcript
above and decided" — never the record it was ruling on. That sits on the
correction step, which is where `P(revised | initially incorrect)` comes from.
`build_judge_messages` now takes a `parent_record` and renders both shapes.
`_decision_block` carried the same falsehood to the challenger and is now
shape-aware too. The contest stage runs judge-only under outcome control, so the
recourse *debaters* are not reached; see `deferred.md` for what running them
would need.

**`seeded_case_for_solo` can only ever hand over the flawed seed** (was #2,
BLOCKING) has moved to `deferred.md`. It bites only for the correct/control
condition, which is itself deferred, and outcome control does not route through
it.

Earlier: `Ruling.to_dict` dropping `changed_the_decision` (headline revision
rates were pinned to 0/N with a confident interval); `parse_solo_output`
publishing a trailing private `Thinking:` coda; contest resume keyed on the run
directory rather than on `challenge.json`, which made failed contests
permanently un-retryable *and* invisible to the index, and made `--stage rule` a
no-op after `--stage challenge`; `run_stage_grade` aborting the whole stage on
one unreadable directory; a leaked file handle in the append sink;
`aggregate_tree` double-counting copied parent wire logs.

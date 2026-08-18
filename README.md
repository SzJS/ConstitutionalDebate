# ConstitutionalDebate

A prototype **public decision process** built on LLM debate, for decisions that
affect many people. The claim under test is that such a process can be
**transparent** — the public record determines the decision — and **contestable** —
valid challenges change the decision, specious ones do not.

It implements two things: the **debate protocol** — a reimplementation of Kenton et
al. 2024, *On scalable oversight with weak LLMs judging strong LLMs*
([arXiv:2407.04622](https://arxiv.org/abs/2407.04622)), extended to unverifiable
questions and to an optional constitution — and a **recourse mechanism**, by which a
recorded decision can be challenged and either upheld or overturned. Prompt-only:
prompts, an async orchestration layer, and a record anyone can read. No
finetuning, no RL.

## Quickstart

```bash
uv sync
mkdir -p outputs
echo 'OPENROUTER_KEY=sk-or-...' >> .env      # note: not OPENROUTER_API_KEY

# read the prompts before spending anything
uv run constitutional-debate --task examples/tax_havens.json --dry-run

# fetch real questions, then run one debate
uv run python scripts/get_tasks.py --source habermas --limit 5
uv run constitutional-debate --task data/tasks/habermas/habermas-S173963710.json \
  2>&1 | tee outputs/run.log

# read the decision
cat outputs/runs/<run_id>/transcript.md

# contest it
uv run constitutional-recourse --run outputs/runs/<run_id> --generate grounded \
  2>&1 | tee outputs/recourse.log
```

Useful flags: `--turn-style sequential`, `--constitution constitutions/minimal.md`,
`--profile paper|opinion|constitutional`, `--word-limit N`, `--judge-model ...`,
`--no-judge-cot` (the judge explains itself by default), `--rounds N`, `--seed N`.

## The protocol

Two debaters, Alice and Bob, are assigned opposing answers to a binary question
and argue for three rounds; a judge then reads the transcript and picks one.
Debaters emit a private `Thinking:` section and a public `Argument:` section —
only the argument reaches the judge and the opponent. Arguments are capped at 150
words by instruction. Round instructions shift: open → attack the opponent's
flaws → counter their critiques.

**Turn styles.** *Simultaneous* (the default, as in the paper) has both debaters
write concurrently each round, conditioning only on previous rounds. *Sequential*
has Alice write first, with Bob seeing her current-round argument.

**Three orderings are kept separate**, because collapsing them is the easy bug:
the task's answer list, which debater defends which answer (`Seating.alice_answer`),
and which answer the judge sees as choice 1 (`Seating.choice_order`). Alice always
speaks first; choice order is drawn independently, so choice 1 is frequently the
answer defended by the debater who speaks second.

## Three judge profiles

| profile | selected when | judge is asked to determine |
|---|---|---|
| `paper` | the task has a gold answer | which debater is **right** (Kenton's framing) |
| `opinion` | **default** — no gold answer | which debater made the **stronger case, on the transcript** |
| `constitutional` | `--constitution` supplied | which answer is **better under the constitution** |

`opinion` exists because every question in our corpora is a moral or policy
question. Asking a judge to decide who is *right* about tax havens invites it to
substitute its own trained priors for the transcript — which would falsify the
whitebox claim in the default configuration. `paper` is retained as the faithful
control arm.

The constitution is **optional and absent in the common case**. It is a *slot*:
`constitutions/minimal.md` is a placeholder with numbered provisions, and swapping
the file is the intended way to run the same question under a different standard.
When no constitution is supplied, no constitution-specific string appears in any
prompt — that is an invariant with a test, not a convention.

## Recourse: contesting a decision

A completed run can be **challenged**: an argument that the decision was mistaken,
pointing at an error in the judge's reasoning or a consideration it overlooked. A
**recourse** is a new run that puts that challenge to a fresh judge and either
upholds or overturns the decision.

```bash
# supply a challenge, or generate one under a named arm
constitutional-recourse --run outputs/runs/<run_id> --challenge my_challenge.md
constitutional-recourse --run outputs/runs/<run_id> --generate specious
```

**The judge rules on the challenge, not on the question.** It answers
`Ruling: <UPHOLD|OVERTURN>`, and which answer stands afterwards is *derived* —
unchanged if upheld, flipped if overturned. That asymmetry is the point: the burden
lies with the challenge, so a specious one has to actively win to change anything.
Deciding the question afresh instead would let ordinary verdict instability (see the
word-limit limitation below) masquerade as successful contestation.

**Two protocols, one code path.** `recourse_rounds = 0` is the judge-only protocol:
the judge rules on the challenge alone. `1`, the default, adds a round of debate
first — the debater whose answer **lost** argues that the challenge is well founded,
the winner argues that it is not, both still defending their originally assigned
answers. Any `N` follows. `run.json` names the protocol (`judge_only` / `debate`)
rather than leaving a reader to infer it from the round count.

Recourse rounds inherit the parent's `turn_style`, and `--turn-style sequential`
overrides it — it is reasonable to contest a simultaneous debate sequentially, so
that the side defending the decision answers the case against it.

**Generated challenges have arms**, which is what makes contestability measurable:
`grounded` (find a real error and cite the record), `specious` (persuasive in form,
identifying no actual error), `neutral` (no steer). The claim under test is the gap
in overturn rate between the first two. The arm reaches the generator's prompt and
nothing else — a judge shown the label would be grading the label.

**The record is self-contained.** The challenged run is copied into
`<recourse>/parent/` before the first call, so a recourse directory holds the
decision it contests as well as the contest of it, and cannot be left dangling by
anything that happens to the original afterwards.

## What the transparency claim actually is

**A reader of the published record can see what determined the decision.** That is
the whole of it. `transcript.md` states the question, both answers, who argued for
which, every argument, every debater's reasoning, the decision, and the grounds the
judge gave for it — and, where a decision was contested, the challenge, the further
round, and the ruling. Nothing that moved the outcome sits outside that document.

Three design decisions do the work, and each of them is a place the claim could
have failed:

- **The judge decides on the transcript, not on what it already believed.** Asking a
  model who is *right* about tax havens invites it to answer from its trained
  priors, which no reader could inspect. The `opinion` profile asks instead who made
  the stronger case *on the arguments given*, and the constitutional profile binds
  the judge to a published standard.
- **The judge states its grounds.** `judge_cot` is on by default — a deviation from
  Kenton et al., who found chain-of-thought null-to-harmful for accuracy. Accuracy
  is not the reason: a decision that states no grounds cannot be read, and cannot be
  contested.
- **Every channel is published.** The debaters' `Thinking` is a channel the protocol
  defines, and it is published. Where a model has a *native* reasoning channel of
  its own, that is published too, labelled as the provider's rather than the
  protocol's. Everything that can change a decision is in `config.json`, which is
  part of the record.

  This used to read "there is no invisible channel: `reasoning_effort` defaults to
  `off`, so the provider's own hidden reasoning is not in play". That is no longer
  a claim this project can make by suppression, because it is no longer a setting
  every model honours — `openai/gpt-oss-20b` and `google/gemini-3.7-flash` both
  reject `reasoning: {enabled: false}` outright with *"Reasoning is mandatory for
  this endpoint"*. Suppression would have meant excluding a growing class of
  models rather than seeing their reasoning.

  Every model tested does return the reasoning text, so publishing is available
  where switching off is not, and it is the stronger claim: not "that channel was
  closed" but "that channel is in this document". Two caveats belong with it.
  Some providers return a **summary** of their reasoning rather than the trace
  itself, so "published" means less for them than it does for others. And a
  provider that bills reasoning tokens while returning no text has a channel that
  genuinely cannot be inspected — that case is detected and marked in the record
  rather than left to look like the clean one.

**This is not a claim that the run is reproducible.** Sampling is not deterministic,
and OpenRouter's `seed` is best-effort and ignored by some providers — in one
six-call debate we observed the same model id served by five different providers
(GMICloud, DigitalOcean, Morph, SiliconFlow, Phala), so each call records its
resolved `provider` and `response_model` to keep that confound visible. Re-running
this question would produce a different debate. What a reader gets is not the
ability to reproduce the decision but the ability to *read* it.

## Run records

```
outputs/runs/<run_id>/
  transcript.md          THE PUBLISHED RECORD — the question, the answers, who
                         argued which, every argument, the debaters' Thinking, and
                         the decision with the judge's own words
  run.json               status, timings, git sha, client config, provenance
  config.json  task.json  seating.json  constitution.md    <- the inputs
  calls.jsonl            one line per HTTP attempt: full request and response
                         bodies, provider, resolved model, finish_reason, usage
  transcript.json        the same turns as structured data, for tooling
  verdict.json           raw text, choice, resolved answer index, the judge's
                         stated reasoning, correctness
  run.log
```

A recourse directory is the same shape, plus:

```
outputs/runs/<run_id>-recourse/
  challenge.md           the challenge verbatim
  challenge.json         its provenance: supplied or generated, under which arm,
                         shown how much of the record, and the generator's Thinking
  ruling.json            UPHOLD/OVERTURN, the derived answer index, the grounds
  transcript.json        this run's turns only, plus parent_run_id/parent_rounds —
                         the parent's turns live in parent/ and nowhere else
  transcript.md          debate -> decision -> challenge -> recourse rounds -> ruling
  parent/                a verbatim copy of the challenged run directory
```

There is no `verdict.json` in a recourse directory: a recourse records a *ruling*,
whose shape is different, and restating it as a verdict would put false values in
`raw` and `choice`. Downstream tooling that globs for verdicts must learn about
`ruling.json`. Note also that editing anything under `parent/` — even a typo in a
log — invalidates the recorded `parent_sha256`. That is the intended behaviour, not
a bug to work around.

`transcript.md` is a re-render rather than a copy of what the judge saw: the judge
read a tagged plaintext transcript, and the document defends markdown structure
instead. The requests themselves are in `calls.jsonl`.

**The debaters' `Thinking` is published.** It was private *during* the debate — the
judge and the opponent never saw it, which is what makes the arguments the debate —
but a reader of a public decision should be able to see everything that went into
it, including what a debater worked out and chose not to say. The document labels
which is which, because a reader who could not tell them apart would credit the
judge with reasoning it never saw.

## Known limitations

- **Under `outcome_control`, a record is not a model's output.** The `single`
  arm makes **zero API calls**: its published reasoning is the flawed solution
  supplied with the case, reproduced unaltered, and its `Answer:` line follows
  from the run's seating. The `self_critique` revision and the `debate` arm's
  round 1 are the same text. Steps and turns built this way carry
  `parse_mode = "constructed"` and an empty `call_id`, the record states that it
  was constructed, and `render_solo_record` drops "One agent, one pass" — which
  would otherwise be false. This is a controlled-stimulus design: it buys a flaw
  that is byte-identical across arms, and it gives up the claim that the arm's
  own competence produced the decision. See `design_decisions.md` §4b.
- **The arms are badly unmatched on record length.** A constructed `single`
  record is the seed alone, 81-216 words. A debate record adds four generated
  turns near the 400-word cap. That is roughly 8:1 in how much text a challenger
  has to read, and `next_steps.md` names this as the confound that could make
  debate win for the wrong reason. `analysis.token_balance` measures it, on
  `decision_record_words` rather than on generated tokens — which are zero for a
  constructed arm and would report a match for the wrong reason. It is flagged,
  not enforced.
- **Judge and debaters default to the same model.** This tests the protocol's
  plumbing, not the paper's strong-debater/weak-judge asymmetry, and it invites
  self-preference. Set `--judge-model` to something weaker before drawing any
  conclusion about oversight.
- **A supplied constitution is public to everyone**, so debate buys argument
  search, not the information-access asymmetry of the paper's extractive setting.
  This is closer to their closed-QA condition than to their headline result.
- **The judging rubric rewards persuasion.** A rhetorically strong but ungrounded
  argument is exactly the "specious challenge" that should not move the decision.
  The constitutional profile adds a groundedness criterion; `paper` and `opinion`
  have no such mitigation.
- **Debaters make unverifiable empirical predictions** about consequences, and
  nobody in the loop can check them. That is a real weakness of applying debate
  here, not an implementation bug.
- **A debater writes into a structured document.** Arguments are interpolated
  into a whitespace-delimited transcript inside a `<transcript>` block, so a
  debater could in principle forge an opponent's turn or address the judge
  outside the block. Continuation lines are indented and `</transcript>` is
  escaped, which keeps authored text visibly subordinate to the structure, but
  this is mitigation rather than a guarantee — the judge is still reading a
  document that one participant partly wrote. The markdown artifacts face the
  same problem against different structure and get their own defanging: line-
  leading headings, code fences, thematic breaks and raw HTML are escaped, so a
  debater cannot forge a round, a speaker, or a decision in the readable record.
- **The judge explains itself by default**, which deviates from the paper. Kenton
  et al. found judge chain-of-thought null-to-harmful for *accuracy* (see
  `protocols.md`); it is on here for a different reason — a decision that states no
  grounds can be neither read nor contested, and both are the claim under test.
  `--no-judge-cot` restores the paper's predict judge, and is a control arm rather
  than a configuration a real decision should use.
- **Nothing checks that the grounds are grounded.** The constitutional judge is
  instructed to cite provisions by identifier and quote their operative words, and
  the opinion judge is told not to fill gaps from its own knowledge. Neither
  instruction is verified. A judge that decided from its own priors and wrote
  plausible-looking grounds citing things absent from the transcript would pass
  every check in the repo. This is the most valuable check the project does not
  have.
- **The word limit is not a neutral knob.** In our runs, debaters used 80–90% of
  whatever budget they were given, and the same question under the same seating
  returned *different verdicts* at 150 and 250 words. The constitutional profile
  runs closest to the cap, consistent with its instruction to quote provisions.
- **Removing the word limit breaks runs, asymmetrically.** `word_limit = 0` states
  no cap. On long technical questions that produced a ~60% run-failure rate: the
  limit had been disciplining the *private* `Thinking` section as a side effect,
  and without it debaters ran past the token ceiling before ever reaching
  `Argument:`. Truncation is fatal by design, so those runs die. The instruction
  now bounds the scratchpad explicitly, but the deeper point is the asymmetry —
  the failures fall on the debater defending the **weaker** case, which strains
  hardest, so discarding failed runs is not a neutral exclusion.
- **Some questions induce a degenerate decoding loop.** A debater emitted one
  sentence verbatim for 126,000 characters at the `Thinking`→`Argument`
  transition, and hit the ceiling. It recurs at 8k, at 32k, and with a frequency
  penalty; a model with ~4× the active compute fails the same way, so it is a
  decoding pathology rather than a capability limit. It is stochastic — the same
  case can pass on a re-run — which is why `max_decision_attempts` retries the
  *whole* decision rather than the truncated response. Roughly a quarter of
  decisions need more than one attempt, and that rate is recorded per run.
- **The profile changes the verdict too**: `paper` and `opinion` disagreed on the
  same question. Neither of these is a bug; both mean single runs should not be
  read as results.
- Prompts are faithful to the reconstruction in `protocols.md`, which is itself a
  paraphrase — there is no verbatim source text, so nothing here is a fidelity
  test against an original.

### Limitations specific to recourse

- **`--challenge-visibility full` makes the two decisions incomparable.** The
  generator is shown the debaters' `Thinking`, so its challenge can put to the
  recourse judge something the judge who decided the question never had. This is
  not a secrecy problem — the record publishes the `Thinking` either way — but the
  ruling is then answering a different question from the decision. The record marks
  it, and the readable document says so where the challenge is quoted. `public` is
  the default, and it means "the record as the deciding judge saw it".
- **The recourse debaters still may not concede.** `Do not concede your assigned
  answer under any circumstances` now applies to a recourse round, so the winning
  side produces a fluent rebuttal even of a correct challenge. That is the
  adversarial design working as intended, but it means "valid challenges change the
  decision" is measured through a filter that always manufactures opposition — and
  with debaters and judge on the same model, self-preference compounds it.
- **A narrow challenge is flattened.** A challenge can say "the grounds were wrong,
  though the answer may be right"; the pro/anti split cannot represent that. The
  prompts argue about *the decision* rather than *the answer*, which is the best
  available fix, not a complete one.
- **A ruling cannot itself be contested.** A recourse records a ruling, not a
  verdict, so there is no decision-under-challenge for a second round of the
  mechanism to quote; `load_run_record` refuses it and says why. Chained recourse
  would need its own design.
- **Copying the parent is not free.** `calls.jsonl` carries full request bodies, and
  it is the largest artifact in a run directory.

## Prior art

- **Kenton et al. 2024** ([arXiv:2407.04622](https://arxiv.org/abs/2407.04622)) —
  the protocol implemented here. Their turn-style ablation found no significant
  difference between simultaneous and sequential debate.
- **Sachdeva & van Nuenen, *Interaction Protocol Shapes Moral Judgment in
  Multi-Agent Debate*** (COLM 2026,
  [arXiv:2510.10002](https://arxiv.org/abs/2510.10002)) — prior art on the same
  synchronous-vs-sequential axis, finding that protocol shape *does* materially
  change verdicts and revision rates. That contrast is worth taking seriously.
  Their repository ships code and prompts but no data, and its task is a 5-way
  verdict reached by consensus among three agents, so it is not a question source
  here; an AITA adapter would be a future extension.

## Question sources

Fetched into a git-ignored `data/` cache; nothing upstream is vendored, and
provenance (URL, sha256) is recorded per fetch.

- **Habermas Machine** (DeepMind, *Science* 2024, CC-BY) — 553 binary opinion
  questions as affirming/negating statement pairs. The cleanest fit.
- **Debate-NeurIPS25** (FAIR-IALAB-UBA) — 145 moral dilemmas as
  `scenario, stance_1, stance_2`. Stances are read from the columns rather than
  assumed to be Yes/No, since two rows are not. Its `judge_persona` column is
  deliberately ignored for now.

Neither GitHub repository carries a LICENSE file, so both are treated as
all-rights-reserved and only cached locally. Test fixtures are synthetic.

## Development

```bash
uv run pytest 2>&1 | tee outputs/pytest.log
```

The suite is offline — no test makes a network call. The load-bearing ones:
`FakeClient` counts in-flight calls to prove that simultaneous rounds really are
concurrent (`max_in_flight == 2`) and sequential ones really are not (`== 1`); the
leak invariants prove no debater's `Thinking` reaches an opponent or a judge; and
the recourse tests prove the ruling resolves the way the protocol says it should.

`tests/test_prompts.py` is all property assertions — no golden snapshots — so an
accidental edit to a prompt template is caught only if it violates one of those
properties. Golden-string tests over the templates would close that.

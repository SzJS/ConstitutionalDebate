# ConstitutionalDebate

A prototype **public decision process** built on LLM debate, for decisions that
affect many people. The claim under test is that such a process can be
**whitebox** — the public record determines the decision — and **contestable** —
valid challenges change the decision, specious ones do not.

This repository currently implements the debate protocol itself: a reimplementation
of Kenton et al. 2024, *On scalable oversight with weak LLMs judging strong LLMs*
([arXiv:2407.04622](https://arxiv.org/abs/2407.04622)), extended to unverifiable
questions and to an optional constitution. Prompt-only: prompts, an async
orchestration layer, and a record you can audit. No finetuning, no RL.

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

# audit the result
uv run python scripts/verify_run.py outputs/runs/<run_id>
```

Useful flags: `--turn-style sequential`, `--constitution constitutions/minimal.md`,
`--profile paper|opinion|constitutional`, `--word-limit N`, `--judge-model ...`,
`--judge-cot`, `--rounds N`, `--seed N`.

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

## What the whitebox claim actually is

**Prompt construction is a pure function of `(task, config, seating, constitution,
prior turns)`** — all five of which are in the run directory. So a third party can
re-derive every request that was sent and byte-compare it against the wire log.
`scripts/verify_run.py` does exactly that, and checks that:

- no prompt differs from the one re-derived from the record;
- no debater's private `Thinking` reached the opponent or the judge;
- whichever answer is gold left no trace in any prompt;
- the constitution, if any, reached both debaters and the judge;
- the verdict resolves through the recorded seating.

Note that **prior turns are an input**. Round-2 and round-3 prompts embed earlier
generations, so "a pure function of task and config" would be false and an auditor
following it would fail at round 2.

**What is not reproducible: the generations.** Sampling is not deterministic, and
OpenRouter's `seed` is best-effort and ignored by some providers. In one six-call
debate we observed the same model id served by five different providers
(GMICloud, DigitalOcean, Morph, SiliconFlow, Phala), so each call records its
resolved `provider` and `response_model` to keep that confound visible. The honest
claim is **auditable and deterministic in prompt construction, not bit-reproducible
in generation**.

`verify_run.py` also reports when the working tree differs from the one that
produced a run, since a prompt mismatch can mean either an altered record or a
changed template, and those mean opposite things.

## Run records

```
outputs/runs/<run_id>/
  run.json               status, timings, git sha + diff, client config, provenance
  config.json  task.json  seating.json  constitution.md    <- the audit inputs
  calls.jsonl            one line per HTTP attempt: full request and response
                         bodies, provider, resolved model, finish_reason, usage
  transcript.json        audit artifact — includes private Thinking
  transcript.public.md   public record — arguments only
  verdict.json           raw text, choice, resolved answer index, correctness
  run.log
```

`transcript.public.md` is a re-render, not a byte-copy of what the judge saw; the
byte-exact artifact is the judge request body in `calls.jsonl`.

## Known limitations

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
  document that one participant partly wrote.
- **The word limit is not a neutral knob.** In our runs, debaters used 80–90% of
  whatever budget they were given, and the same question under the same seating
  returned *different verdicts* at 150 and 250 words. The constitutional profile
  runs closest to the cap, consistent with its instruction to quote provisions.
- **The profile changes the verdict too**: `paper` and `opinion` disagreed on the
  same question. Neither of these is a bug; both mean single runs should not be
  read as results.
- Prompts are faithful to the reconstruction in `protocols.md`, which is itself a
  paraphrase — there is no verbatim source text. The golden prompt tests are
  regression tests against drift, not fidelity tests.

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
concurrent (`max_in_flight == 2`) and sequential ones really are not (`== 1`);
the audit tests confirm that a tampered transcript, a leaked `Thinking` section,
and an inverted verdict are each caught.

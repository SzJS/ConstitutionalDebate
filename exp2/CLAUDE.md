# Start here

If you are new to this experiment, read [`HANDOFF.md`](HANDOFF.md) first. It is written
for an agent with no memory of this project on a machine holding nothing but this
repository: what has been run and what it cost, the ground rules that are not written
down anywhere else, how to rebuild `outputs/` and `data/` from scratch, exactly what the
first full sweep runs, and what must not be changed. It replaces a plan file that lived
outside the repo and was lost with the pod it was on.

# Purpose

This experiment tests whether a **weak stakeholder can detect, contest and correct a
bad AI decision more effectively when that decision was produced by debate**.

The decision task is a yes/no verdict: given a problem and one proposed solution,
**does the solution contain a flaw?** Three conditions decide the same items — a
single agent, a single agent with critique-and-revision, and a debate judged by a weak
model. Each decision is then contested by a weak challenger who may decline, and the
funnel `error → detection → valid objection → revision` is measured per condition and
per error type.

The claim under test is that debate's record is **transparent** — a reader of
`transcript.md` can see what determined the decision — and therefore **contestable**:
valid challenges change the decision, specious ones do not. Transparency here is a
claim about one document, not about reproducibility; sampling is nondeterministic and
re-running a question produces a different debate.

The implementation is **prompt-only**: prompts, an orchestration layer making API
calls, and an evaluation harness. No finetuning, no RL.

# Relationship to exp1

exp2 was **ported from `exp1/` at commit `f5fc3c9`** and then diverged. It does not
import from exp1, does not read exp1's data, and fetches its own copy of every
upstream source. If you need to know how exp1 did something, read it — the port is the
sanctioned reason to look. Do not add an import, a symlink, or a path into `../exp1/`.

Two differences drive almost every divergence:

1. **Task framing.** exp1 asks "which of these two *answers* is correct" and carries a
   `gold_index`. exp2 asks "does this *solution* contain a flaw" and carries a
   `gold_flawed` boolean. There is no answer pair, no choice ordering, and no seeded
   case. The randomisation exp1 spent on `gold_index` and `choice_order` is re-spent
   on which side each debater takes and which order the verdict template is presented
   in.
2. **No outcome control.** exp1 manufactured its error cases by steering a judge or a
   critique into being wrong. exp2 takes **naturally occurring errors only** and
   accepts a smaller incorrect-cell. Nothing steers, nothing injects; `construct.py`
   and everything that referenced it are not ported.

The problem statement and the solution under review are inside the transcript, visible
to debaters, judge and challenger alike. Nobody sees the ground-truth label — that
invariant is enforced by a property test, not by convention.

# Working here

Run every command from this directory (`exp2/`), not from the repo root. This
experiment has its own `.venv` and `pyproject.toml`; the API key is shared from the
repo root's `.env` (`load_dotenv()` walks up to find it). `outputs/` and `data/` are
git-ignored.

The repo root's `CLAUDE.md` carries the practice rules that apply to every
experiment — parallelism, saving outputs, testing each step, confirming
hyperparameters, choosing models. They are not repeated here.

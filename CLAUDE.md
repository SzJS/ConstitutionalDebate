# Layout

Each experiment lives in its own subfolder and is self-contained — its own docs,
configs, `pyproject.toml`, `.venv` and `outputs/`. **Run commands from inside the
experiment's directory**, never from this root: `cd exp1 && uv run pytest`.

- `exp1/` — the contestable-debate experiment (transparent, contestable public
  decision process built on LLM debate). See `exp1/CLAUDE.md`.
- `exp2/` — the contestability experiment: can a weak stakeholder detect,
  contest and correct a bad decision better when it came from debate? Ported
  from `exp1/` and diverged. See `exp2/CLAUDE.md`.

Shared at this root, and only this: `.env` (the API key — `load_dotenv()` walks up
from the calling module, so each experiment finds it without a symlink),
`.gitignore` (its patterns are depth-agnostic and already cover every experiment's
`outputs/`, `data/` and `.venv/`), `.claude/`, and this file. Nothing else belongs
here; an experiment must not read across into another's directory.

The rules below apply to every experiment.

Do NOT modify DESIGN.md on your own. Use LLM_NOTES.md instead. However, when you notice that something in DESIGN.md has become stale, you may *suggest* edits to me (the user).

# Best practices

**Parallelize as much as possible.**
- Make LLM and I/O calls **async and concurrent** — data generation, judge filtering, and eval
  should fire batched/concurrent requests, never a synchronous loop. Bound concurrency and back
  off on rate limits.
- **Save all model outputs.** Whenever a model generates text (data generation, judge filtering,
  eval transcripts, sample generations), persist it under `outputs/` — never let a generation
  exist only in memory or scrollback. `outputs/` is git-ignored.
**Observe everything.**
- **Save all terminal outputs.** Capture every command's output to a file under `outputs/` while
  still printing it, e.g. `uv run python x.py 2>&1 | tee outputs/x.log`.
- **Confirm every hyperparameter before the run.** When an LLM or a script takes hyperparameters or
  command line arguments, show the user the full set of values it will run with — defaults included
  — and say in a line why each one is what it is. Run only once they confirm, and persist the
  settled values with the run's outputs.
**Test every step.**
- Where applicable, whenever you implement a new feature, test it immmediately - do not wait until
  you have finished unrelated follow-up steps.
  - A part of testing (when appropriate) is to have me - the user - verify the transcripts.
**Have Opus do the implementation.**
- My workflow is to use Fable, an expensive model, for planning and Opus, a cheaper, but still
  capable model for executing the plans. Therefore, all plans should spawn an Opus subagent to
  execute the plan.

# Choosing models

- **Check throughput and latency on [openrouter.ai](https://openrouter.ai/models)** before using a
  model, and again when swapping one in. Prefer high throughput and low latency: a sweep is
  thousands of calls, so a third of the throughput turns a 10-minute stage into a 40-minute one and
  starts tripping `run_timeout_s`.
- **Pick models from [artificialanalysis.ai/models](https://artificialanalysis.ai/models)**,
  on intelligence index and **cost per task** — not cost per token, since a model that reasons at
  length can be dearer per task while looking cheaper per token.

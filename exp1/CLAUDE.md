# Purpose

This repo prototypes a **public decision-making process** built on LLMs, for decisions that affect many people in significant ways. The claim under test: the process is **transparent** — a reader of the published record can see what determined the decision — and **contestable** — valid challenges change the decision, specious ones do not.

Transparency is a claim about what one document, `transcript.md`, lets a reader see: the question, the arguments, the decision, and the grounds given for it. It is not a claim that the run is reproducible — sampling is nondeterministic, and re-running a question produces a different debate. Design decisions are justified by whether a reader could follow the decision, not by whether a machine could reproduce it.

The mechanism is **debate**: AI safety via debate, applied to unverifiable domains (no ground-truth answer).

The implementation is **prompt-only**: prompts, an orchestration layer making API calls, and an evaluation harness. No finetuning, no RL.

# Working here

Run every command from this directory (`exp1/`), not from the repo root — all paths
in the code, the configs and the docs are relative to it: `cd exp1 && uv run pytest`.
This experiment has its own `.venv`, `pyproject.toml` and `uv.lock`; the API key is
shared from the repo root's `.env` (`load_dotenv()` walks up to find it).

The repo root's `CLAUDE.md` carries the practice rules that apply to every
experiment — parallelism, saving outputs, confirming hyperparameters, choosing
models. They are not repeated here.

[`README.md`](README.md) is the front door and documents the protocol as
implemented; [`DESIGN.md`](DESIGN.md) is the single source of truth for what the
experiment rests on and why; [`KNOWN_ISSUES.md`](KNOWN_ISSUES.md) is the defect
ledger.

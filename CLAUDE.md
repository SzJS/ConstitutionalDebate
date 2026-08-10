# Purpose

This repo prototypes a **public decision-making process** built on LLMs, for decisions that affect many people in significant ways. The claim under test: the process is **whitebox** — the publicly available record (question, debate transcript) is what determines the decision — and **contestable** — valid challenges change the decision, specious ones do not.

The mechanism is **debate**: AI safety via debate, applied to unverifiable domains (no ground-truth answer).

The implementation is **prompt-only**: prompts, an orchestration layer making API calls, and an evaluation harness. No finetuning, no RL.

# Compute & training best practices

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

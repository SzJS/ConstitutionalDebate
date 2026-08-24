# Purpose

TBD — this experiment has not been specified yet. Write the research question, the
claim under test, and the mechanism here before writing code.

# Working here

Run every command from this directory (`exp2/`), not from the repo root. This
experiment has its own `.venv` and `pyproject.toml`; the API key is shared from the
repo root's `.env` (`load_dotenv()` walks up to find it). `outputs/` and `data/` are
git-ignored.

The repo root's `CLAUDE.md` carries the practice rules that apply to every
experiment — parallelism, saving outputs, confirming hyperparameters, choosing
models. They are not repeated here.

Do not read across into `../exp1/`. If this experiment needs the same upstream
question sets, fetch its own copy.

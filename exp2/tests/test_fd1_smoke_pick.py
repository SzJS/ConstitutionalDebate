"""`records/derivations/fd1-smoke-pick.py`'s command line.

Only the argument parsing is tested here. The draw itself reads
`outputs/experiments/jd3-main`, which is a run tree and not a fixture, and the script
already asserts its own invariant loudly — the overlap with every `--exclude` file is
checked before anything is written.

WHY THE COMMAND LINE IS WORTH A TEST. Smoke 3 must avoid the cells of BOTH earlier
smokes, so it passes `--exclude` twice. With the `nargs="*"` the script shipped, a
repeated optional argument REPLACES the earlier one rather than adding to it: the second
flag would have silently thrown away the first, the draw would have been made against one
smoke file instead of two, and the script's own overlap assertion would have passed
because it only checks the files it was given. That is a failure with no symptom, which
is exactly the kind this repository pins.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

PICK = Path(__file__).resolve().parents[1] / "records/derivations/fd1-smoke-pick.py"


def _module():
    spec = importlib.util.spec_from_file_location("fd1_smoke_pick", PICK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_exclude_accumulates_across_repeated_flags():
    parse_args = _module().parse_args

    repeated = parse_args(["--seed", "3", "--out", "data/cases/fd1-smoke-3.jsonl",
                           "--exclude", "data/cases/fd1-smoke.jsonl",
                           "--exclude", "data/cases/fd1-smoke-2.jsonl"])
    assert repeated.exclude == [Path("data/cases/fd1-smoke.jsonl"),
                                Path("data/cases/fd1-smoke-2.jsonl")]
    assert repeated.seed == 3
    assert repeated.out == Path("data/cases/fd1-smoke-3.jsonl")

    # the one-flag form smoke 2 used still works, and so does a bare list
    assert parse_args(["--exclude", "a.jsonl", "b.jsonl"]).exclude == [
        Path("a.jsonl"), Path("b.jsonl")]


def test_no_arguments_still_means_smoke_1():
    """The default draw is unchanged, which is what makes the script re-runnable as the
    record of what smoke 1 ran."""
    module = _module()
    plain = module.parse_args([])
    assert plain.seed == module.SEED
    assert plain.out == module.OUT
    # `action="extend"` needs `default=None`, not `[]`: `extend` mutates the default list
    # in place, so a shared `[]` would grow across parses within one process.
    assert plain.exclude is None
    assert list(plain.exclude or []) == []

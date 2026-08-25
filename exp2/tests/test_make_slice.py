"""The sweep-slice draw, tested offline against a synthetic corpus.

`scripts/make_slice.py` is not part of the package, so it is loaded from its path, the
same way `test_pick_weak.py` loads its script.

Two properties matter enough to be assertions rather than review. **The draw is
clustered on `row_id`** — a paired row's flawed and sound siblings must both travel or
neither does, because `row_id` is the bootstrap's clustering unit. And **the corpus
bundles are read-only**: the reason this script exists at all is that
`get_tasks.py --sample` rewrites `data/cases/ftf-*.jsonl` in place, so the md5 of every
input bundle is asserted unchanged across a run.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

from exp2.types import load_cases

_SPEC = importlib.util.spec_from_file_location(
    "make_slice", Path(__file__).resolve().parents[1] / "scripts" / "make_slice.py"
)
make_slice = importlib.util.module_from_spec(_SPEC)
sys.modules["make_slice"] = make_slice
_SPEC.loader.exec_module(make_slice)


def _case(subset: str, row: int, flawed: bool) -> dict:
    """One case dict in the bundle's own on-disk shape."""
    label = "flawed" if flawed else "sound"
    item = {
        "item_id": f"{subset}-r{row}-{label}",
        "row_id": f"{subset}:r{row}",
        "subset": subset,
        "problem": f"problem {row}",
        "solution": f"solution {row}",
        "gold_flawed": flawed,
        "label_basis": "injected_pair",
    }
    case: dict = {"item": item}
    if flawed:
        case["flaw"] = {
            "annotation_id": item["item_id"],
            "flaw_location": "1",
            "annotation": "step 1 is wrong",
        }
    return case


def _bundle(root: Path, subset: str, rows: int, *, paired: bool = True) -> Path:
    path = root / "cases" / f"ftf-{subset}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    cases = []
    for row in range(rows):
        cases.append(_case(subset, row, True))
        if paired:
            cases.append(_case(subset, row, False))
    path.write_text("\n".join(json.dumps(c) for c in cases) + "\n", encoding="utf-8")
    return path


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def test_the_draw_takes_whole_rows_and_leaves_the_bundles_untouched(tmp_path, capsys):
    law = _bundle(tmp_path, "law", rows=40)
    gpqa = _bundle(tmp_path, "gpqa", rows=30, paired=False)
    before = {p: _md5(p) for p in (law, gpqa)}

    out = tmp_path / "cases" / "slice.jsonl"
    assert make_slice.main([
        "--data-root", str(tmp_path), "--subsets", "law,gpqa",
        "--rows", "10", "--seed", "1", "--out", str(out),
    ]) == 0

    # The inputs are exactly what they were. This is the whole reason for the script.
    assert {p: _md5(p) for p in (law, gpqa)} == before

    drawn = load_cases(out)
    by_subset: dict[str, list] = {}
    for case in drawn:
        by_subset.setdefault(case.item.subset, []).append(case)

    # 10 rows each; law is paired so it brings 20 items, gpqa 10.
    assert len({c.item.row_id for c in by_subset["law"]}) == 10
    assert len(by_subset["law"]) == 20
    assert len({c.item.row_id for c in by_subset["gpqa"]}) == 10
    assert len(by_subset["gpqa"]) == 10

    # Every drawn row travels whole: both siblings, never one.
    per_row: dict[str, int] = {}
    for case in by_subset["law"]:
        per_row[case.item.row_id] = per_row.get(case.item.row_id, 0) + 1
    assert set(per_row.values()) == {2}

    printed = capsys.readouterr().out
    assert "law" in printed and "gpqa" in printed


def test_the_draw_is_deterministic_and_differs_per_subset_and_seed(tmp_path):
    _bundle(tmp_path, "law", rows=40)

    def ids(seed: str, out: str) -> list[str]:
        path = tmp_path / out
        make_slice.main(["--data-root", str(tmp_path), "--subsets", "law",
                         "--rows", "10", "--seed", seed, "--out", str(path)])
        return [c.item.item_id for c in load_cases(path)]

    assert ids("1", "a.jsonl") == ids("1", "b.jsonl")
    assert ids("1", "a.jsonl") != ids("2", "c.jsonl")

    # The seed material carries the subset, so two subsets do not draw the same
    # positional rows out of their bundles.
    _bundle(tmp_path, "surgery", rows=40)
    law_rows = {c.item.row_id.split(":")[1]
                for c in load_cases(tmp_path / "a.jsonl")}
    surgery_path = tmp_path / "d.jsonl"
    make_slice.main(["--data-root", str(tmp_path), "--subsets", "surgery",
                     "--rows", "10", "--seed", "1", "--out", str(surgery_path)])
    surgery_rows = {c.item.row_id.split(":")[1]
                    for c in load_cases(surgery_path)}
    assert law_rows != surgery_rows


def test_a_subset_with_fewer_rows_than_asked_gives_all_of_them(tmp_path):
    _bundle(tmp_path, "law", rows=4)
    out = tmp_path / "slice.jsonl"
    make_slice.main(["--data-root", str(tmp_path), "--subsets", "law",
                     "--rows", "25", "--seed", "1", "--out", str(out)])
    assert len({c.item.row_id for c in load_cases(out)}) == 4


def test_the_overlap_report_names_the_shared_item_ids(tmp_path, capsys):
    _bundle(tmp_path, "law", rows=40)
    earlier = tmp_path / "earlier.jsonl"
    earlier.write_text(json.dumps(_case("law", 0, True)) + "\n", encoding="utf-8")
    out = tmp_path / "slice.jsonl"
    make_slice.main(["--data-root", str(tmp_path), "--subsets", "law",
                     "--rows", "40", "--seed", "1", "--out", str(out),
                     "--compare", str(earlier)])
    printed = capsys.readouterr().out
    assert "overlap with" in printed
    assert "law-r0-flawed" in printed

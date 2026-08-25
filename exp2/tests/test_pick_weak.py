"""The probe script's own logic, tested offline.

`scripts/pick_weak.py` is not part of the package, so it is loaded from its path. Only
the parts that decide something are tested — the pooling that a gray-zone escalation
depends on, and the offset/subset draw that feeds it. The passes themselves are network
calls and are not exercised here.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "pick_weak", Path(__file__).resolve().parents[1] / "scripts" / "pick_weak.py"
)
pick_weak = importlib.util.module_from_spec(_SPEC)
# Registered before exec: `@dataclass` looks the defining module up in `sys.modules`.
sys.modules["pick_weak"] = pick_weak
_SPEC.loader.exec_module(pick_weak)


def _write(outputs: Path, model: str, offset: int, n: int, correct: int,
           subset: str = "law", first: int = 0) -> None:
    rows = [
        pick_weak.Row(
            model=model, pass_name="solo", subset=subset,
            item_id=f"{subset}-{first + i}", gold_flawed=bool(i % 2),
            verdict="FLAWED", correct=i < correct,
        )
        for i in range(n)
    ]
    pick_weak.save_rows(outputs, model, "solo", rows, offset)


def test_the_escalation_is_written_beside_the_base_draw_not_into_it(tmp_path):
    assert pick_weak.rows_path(tmp_path, "a/b", "solo").name == "rows-solo-a-b.jsonl"
    assert (pick_weak.rows_path(tmp_path, "a/b", "solo", 40).name
            == "rows-solo-a-b-offset40.jsonl")


def test_pooling_counts_the_base_draw_and_the_escalation_together(tmp_path):
    """40 items plus an escalation's 40 is an n=80 estimate. Reading the second draw
    on its own would just be a second coin flip, which is what the gray zone means."""
    _write(tmp_path, "x/y", offset=0, n=40, correct=30, first=0)
    _write(tmp_path, "x/y", offset=40, n=40, correct=28, first=100)

    pooled = pick_weak.pooled_solo_rows(tmp_path, "x/y")
    assert len(pooled) == 80
    assert pick_weak.accuracy(pooled) == (58, 80)

    # 0.725 pooled: still gray, which under the rule means KEEP and flag.
    assert pick_weak.KEEP_BELOW < 58 / 80 < pick_weak.DROP_AT


def test_pooling_deduplicates_so_an_overlapping_offset_cannot_double_count(tmp_path):
    _write(tmp_path, "x/y", offset=0, n=40, correct=30, first=0)
    _write(tmp_path, "x/y", offset=40, n=40, correct=40, first=20)  # 20 items overlap
    pooled = pick_weak.pooled_solo_rows(tmp_path, "x/y")
    assert len(pooled) == 60
    assert len({r.item_id for r in pooled}) == 60


def test_pool_solo_leaves_the_other_passes_alone(tmp_path):
    _write(tmp_path, "x/y", offset=0, n=40, correct=30)
    _write(tmp_path, "x/y", offset=40, n=40, correct=28, first=100)
    judged = [pick_weak.Row(model="x/y", pass_name="judge", subset="law",
                            item_id="j1", gold_flawed=True, verdict="FLAWED",
                            correct=True)]
    pooled = pick_weak.pool_solo(tmp_path, judged + _read(tmp_path, "x/y")[:5])
    assert sum(1 for r in pooled if r.pass_name == "judge") == 1
    assert sum(1 for r in pooled if r.pass_name == "solo") == 80


def _read(outputs: Path, model: str) -> list:
    return pick_weak.load_rows(outputs, model, "solo") or []


def test_the_report_pools_off_disk_when_given_an_outputs_directory(tmp_path, capsys):
    _write(tmp_path, "x/y", offset=0, n=40, correct=30)
    _write(tmp_path, "x/y", offset=40, n=40, correct=28, first=100)
    pick_weak.print_report(_read(tmp_path, "x/y"), tmp_path)
    out = capsys.readouterr().out
    assert "n=80" in out
    assert "0.72" in out  # 58/80


def test_the_offset_is_counted_in_items_so_an_escalation_leaves_no_gap(tmp_path):
    """--offset 40 after --per-subset 40 must draw items 40..80, not 80..120: the unit
    of both flags is items, and half of each is taken from each side of the label."""
    cases_root = tmp_path / "cases"
    cases_root.mkdir()
    _fake_subset(cases_root, "law", n_per_side=60)

    base = pick_weak.sample_cases(cases_root, 40, seed=0, offset=0)
    escalated = pick_weak.sample_cases(cases_root, 40, seed=0, offset=40)
    assert len(base) == 40 and len(escalated) == 40
    base_ids = {c.item.item_id for c in base}
    assert not (base_ids & {c.item.item_id for c in escalated})
    # no gap: the two draws together are the first 80 of the same seeded shuffle
    both = pick_weak.sample_cases(cases_root, 80, seed=0, offset=0)
    assert base_ids | {c.item.item_id for c in escalated} == {
        c.item.item_id for c in both}


def test_the_subsets_filter_restricts_the_draw_to_the_gray_ones(tmp_path):
    cases_root = tmp_path / "cases"
    cases_root.mkdir()
    _fake_subset(cases_root, "law", n_per_side=30)
    _fake_subset(cases_root, "lojban", n_per_side=30)

    both = pick_weak.sample_cases(cases_root, 40, seed=0)
    assert {c.item.subset for c in both} == {"law", "lojban"}
    only = pick_weak.sample_cases(cases_root, 40, seed=0, subsets=["lojban"])
    assert {c.item.subset for c in only} == {"lojban"}
    assert len(only) == 40


def test_an_unknown_subset_is_refused_rather_than_silently_screening_nothing():
    with pytest.raises(SystemExit):
        pick_weak.main(["--subsets", "not-a-subset", "--dry-run"])


def _fake_subset(cases_root: Path, key: str, n_per_side: int) -> None:
    from helpers import make_item

    lines = []
    for flawed in (True, False):
        for i in range(n_per_side):
            item = make_item(item_id=f"{key}-{'f' if flawed else 's'}-{i}",
                             subset=key, gold_flawed=flawed)
            flaw = {"annotation_id": item.item_id} if flawed else None
            lines.append(json.dumps({"item": item.to_dict(), "flaw": flaw}))
    (cases_root / f"ftf-{key}.jsonl").write_text("\n".join(lines) + "\n",
                                                 encoding="utf-8")


def test_rows_measured_on_a_leaked_transcript_are_excluded_but_solo_rows_are_not():
    """A judge that read a leaked record judged something the protocol says it never
    sees. The solo screen never sees a transcript, so its rows stand."""
    leaked = next(iter(pick_weak.LEAKED_FIXTURE_ITEMS))
    rows = [
        pick_weak.Row(model="x/y", pass_name="judge", subset="law", item_id=leaked,
                      gold_flawed=True, verdict="FLAWED", correct=True),
        pick_weak.Row(model="x/y", pass_name="challenger", subset="law", item_id=leaked,
                      gold_flawed=True, raised=True),
        pick_weak.Row(model="x/y", pass_name="judge", subset="law", item_id="clean",
                      gold_flawed=True, verdict="FLAWED", correct=True),
        pick_weak.Row(model="x/y", pass_name="solo", subset="law", item_id=leaked,
                      gold_flawed=True, verdict="FLAWED", correct=True),
    ]
    kept = pick_weak.drop_leaked(rows)
    assert [r.pass_name for r in kept] == ["judge", "solo"]
    assert [r.item_id for r in kept] == ["clean", leaked]

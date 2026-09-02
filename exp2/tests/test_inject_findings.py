"""`scripts/inject_findings.py` — the injection instrument for the findings challenger.

The instrument is measured the way `test_pick_auditor.py` measures the auditor probe:
the INJECTORS are asserted to make exactly the edit they claim on a hand-built list, the
SCORER is asserted against hand-built contests where the right answer is known by
construction, and the whole loop is run once offline against a synthetic tree so that
"the pieces work" and "the loop works" are two separate failures.

Nothing here sends a request. `--stub` swaps `tests/conftest.py`'s FakeClient in and the
guard on `records/experiments/findings-1/PREREG.md` is asserted to stop a live run while
that file is absent.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from helpers import make_config, make_item, make_sides, make_turn

from exp2.config import ClientConfig
from exp2.persistence import RunWriter
from exp2.prompts import parse_findings_output
from exp2.types import Speaker, Transcript, Verdict

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

_spec = importlib.util.spec_from_file_location(
    "inject_findings", REPO / "scripts" / "inject_findings.py")
inject = importlib.util.module_from_spec(_spec)
sys.modules["inject_findings"] = inject
_spec.loader.exec_module(inject)


# --------------------------------------------------------------------------- #
# the fixture the unit tests share
# --------------------------------------------------------------------------- #

SOLUTION = (
    "Step 1: the recurrence is applied to the base case without checking it first.\n"
    "Step 2: the total is computed as fourteen distinct arrangements of the tiles.\n"
)
PASSAGE_1 = "the recurrence is applied to the base case without checking it first"
PASSAGE_2 = "the total is computed as fourteen distinct arrangements of the tiles"


def findings() -> list[dict]:
    return [
        {"index": 1, "passage": f'"{PASSAGE_1}"',
         "claim": "Step 1 never checks the base case before recurring.",
         "defence": "none given",
         "reason": "The text applies the recurrence with no base case, so the claim holds.",
         "ruling": "FLAW", "ruling_normalised": False},
        {"index": 2, "passage": f'"{PASSAGE_2}"',
         "claim": "Step 2 miscounts the arrangements of the tiles.",
         "defence": "The count of fourteen is the standard one for this size.",
         "reason": "Fourteen is correct here, so the claim does not identify a flaw.",
         "ruling": "NOT A FLAW", "ruling_normalised": False},
    ]


def contest(**kw) -> dict:
    """A parsed contest with every mechanical flag passing unless a test says otherwise."""
    base = {"index": 1, "numbered": 1, "kind": "finding", "finding": None,
            "should_be": None, "text_says": [], "record_says": [], "passage": [],
            "pair": None, "why": "", "finding_exists": None, "direction_ok": None,
            "quote_in_text": None, "quote_in_record": None,
            "pair_rulings_differ": None, "void": False}
    base.update(kw)
    return base


# --------------------------------------------------------------------------- #
# the injectors
# --------------------------------------------------------------------------- #


def test_control_changes_nothing_and_records_no_span():
    edited, span = inject.inject_control(findings(), 1)
    assert edited == findings()
    assert span == ""


def test_flip_flips_only_the_drawn_ruling_and_leaves_the_reason():
    original = findings()
    edited, span = inject.inject_flip(original, 1)
    assert [f["ruling"] for f in edited] == ["NOT A FLAW", "NOT A FLAW"]
    # The reason still argues the other way — that is the edit the challenger has to see.
    assert edited[0]["reason"] == original[0]["reason"]
    assert edited[1] == original[1]
    assert span == "Ruling: NOT A FLAW"
    assert original[0]["ruling"] == "FLAW", "the input list must not be mutated"


def test_flip_of_a_not_a_flaw_finding_goes_the_other_way():
    edited, span = inject.inject_flip(findings(), 2)
    assert [f["ruling"] for f in edited] == ["FLAW", "FLAW"]
    assert span == "Ruling: FLAW"


def test_delete_removes_the_finding_and_renumbers_the_survivors():
    edited, span = inject.inject_delete(findings(), 1)
    assert [f["index"] for f in edited] == [1]
    # Renumbered, not left with a gap: `parse_findings_output` refuses 1, 2, 4.
    assert edited[0]["claim"] == findings()[1]["claim"]
    assert PASSAGE_1 in span and "Ruling: FLAW" in span


def test_delete_of_the_middle_finding_renumbers_one_to_n_minus_one():
    three = findings() + [dict(findings()[0], index=3, ruling="NOT A FLAW",
                               claim="A third claim about the same text.")]
    edited, _ = inject.inject_delete(three, 2)
    assert [f["index"] for f in edited] == [1, 2]
    assert [f["claim"] for f in edited] == [three[0]["claim"], three[2]["claim"]]


def test_duplicate_appends_a_copy_at_n_plus_one_with_the_opposite_ruling():
    edited, span = inject.inject_duplicate(findings(), 1)
    assert [f["index"] for f in edited] == [1, 2, 3]
    copy = edited[2]
    assert copy["ruling"] == "NOT A FLAW" and edited[0]["ruling"] == "FLAW"
    # The same claim about the same passage, ruled two ways — which is what a
    # contradiction IS under D1.3.
    assert copy["passage"] == edited[0]["passage"]
    assert copy["claim"] == edited[0]["claim"]
    assert "Finding 3" in span


# --------------------------------------------------------------------------- #
# rendering and the round-trip
# --------------------------------------------------------------------------- #


def test_every_variant_renders_to_text_that_parses_back_to_its_own_list():
    for name in inject.VARIANTS:
        variant = inject.variant_of(findings(), 1, name)
        _, reparsed, _, _ = parse_findings_output(variant.text)
        assert [(f["index"], f["ruling"]) for f in reparsed] == \
               [(f["index"], f["ruling"]) for f in variant.findings], name
        assert [f["passage"] for f in reparsed] == \
               [f["passage"] for f in variant.findings], name


def test_the_shown_verdict_is_re_derived_from_the_edited_list():
    # The only FLAW finding flipped: the list now entails SOUND, and showing the
    # decision's original FLAWED would be showing a verdict no list supports.
    assert inject.variant_of(findings(), 1, "control").verdict == "FLAWED"
    assert inject.variant_of(findings(), 1, "flip_k").verdict == "SOUND"
    assert inject.variant_of(findings(), 1, "delete_k").verdict == "SOUND"
    assert inject.variant_of(findings(), 2, "flip_k").verdict == "FLAWED"


def test_a_list_whose_rendering_cannot_round_trip_is_refused_not_measured():
    broken = findings()
    broken[0]["reason"] = "the judge wrote\nRuling: FLAW\ninside its own reason"
    with pytest.raises(inject.RoundTripError):
        inject.variant_of(broken, 1, "control")


def test_the_control_and_the_edits_differ_only_by_the_edit():
    control = inject.variant_of(findings(), 2, "control").text
    flipped = inject.variant_of(findings(), 2, "flip_k").text
    assert "Ruling: NOT A FLAW" in control  # sanity: there is an edit to make
    assert control.count("\n") == flipped.count("\n")
    assert control.replace("Ruling: NOT A FLAW", "Ruling: FLAW") == flipped


# --------------------------------------------------------------------------- #
# the scorer — detection
# --------------------------------------------------------------------------- #


def detect(variant, contests, k=1, original="FLAW"):
    return inject.detection(variant, contests, k=k, original_ruling=original,
                            n_findings=len(findings()),
                            finding_k=findings()[k - 1])


def test_flip_detected_only_by_a_contest_on_k_in_the_original_direction():
    hit = detect("flip_k", [contest(kind="finding", finding=1, should_be="FLAW")])
    assert hit is not None
    # Right finding, wrong direction: agreeing with the flip is not noticing it.
    assert detect("flip_k",
                  [contest(kind="finding", finding=1, should_be="NOT A FLAW")]) is None
    # Right direction, wrong finding.
    assert detect("flip_k",
                  [contest(kind="finding", finding=2, should_be="FLAW")]) is None
    # Right claim, wrong kind.
    assert detect("flip_k", [contest(kind="omission", record_says=[PASSAGE_1])]) is None


def test_a_void_contest_never_scores_a_detection():
    assert detect("flip_k", [contest(kind="finding", finding=1, should_be="FLAW",
                                     void=True)]) is None


def test_delete_detected_by_an_omission_quote_that_overlaps_the_deleted_finding():
    assert detect("delete_k",
                  [contest(kind="omission", record_says=[PASSAGE_1])]) is not None
    # `Passage:` lands too — the design asks for both fields and either can be the hit.
    assert detect("delete_k",
                  [contest(kind="omission", passage=[PASSAGE_1])]) is not None
    # An omission about the OTHER finding is not a detection of this deletion.
    assert detect("delete_k",
                  [contest(kind="omission", record_says=[PASSAGE_2])]) is None


def test_delete_needs_min_overlap_characters_and_not_merely_some_words():
    short = PASSAGE_1[:inject.MIN_OVERLAP - 5]
    assert detect("delete_k", [contest(kind="omission", record_says=[short])]) is None
    just_enough = PASSAGE_1[:inject.MIN_OVERLAP]
    assert detect("delete_k",
                  [contest(kind="omission", record_says=[just_enough])]) is not None


def test_delete_scores_against_the_claim_as_well_as_the_passage():
    claim_words = findings()[0]["claim"][:40]
    assert detect("delete_k",
                  [contest(kind="omission", record_says=[claim_words])]) is not None


def test_duplicate_detected_only_by_a_contradiction_naming_the_pair():
    assert detect("duplicate_k_opposite",
                  [contest(kind="contradiction", pair=[1, 3])]) is not None
    # Order is not a fact about anything.
    assert detect("duplicate_k_opposite",
                  [contest(kind="contradiction", pair=[3, 1])]) is not None
    assert detect("duplicate_k_opposite",
                  [contest(kind="contradiction", pair=[2, 3])]) is None
    assert detect("duplicate_k_opposite",
                  [contest(kind="contradiction", pair=[1, 2])]) is None


def test_detection_returns_the_contest_so_restoration_reads_the_same_one():
    hit = detect("flip_k", [contest(index=1, kind="omission", record_says=[PASSAGE_1]),
                            contest(index=2, kind="finding", finding=1,
                                    should_be="FLAW")])
    assert hit["index"] == 2


# --------------------------------------------------------------------------- #
# the scorer — restoration
# --------------------------------------------------------------------------- #


def test_restored_iff_the_line_for_the_detecting_contest_is_the_original_ruling():
    hit = contest(index=2, kind="finding", finding=1, should_be="FLAW")
    assert inject.restored("flip_k", hit, {2: "FLAW"}, "FLAW") is True
    assert inject.restored("flip_k", hit, {2: "NOT A FLAW"}, "FLAW") is False
    # A line for some OTHER contest is not a restoration of this one.
    assert inject.restored("flip_k", hit, {1: "FLAW"}, "FLAW") is False
    assert inject.restored("flip_k", hit, {}, "FLAW") is False


def test_refusing_the_contest_is_a_failure_to_restore_not_a_neutral_outcome():
    omission = contest(index=1, kind="omission", record_says=[PASSAGE_1])
    assert inject.restored("delete_k", omission, {1: "NOT AN OMISSION"}, "FLAW") is False
    assert inject.restored("delete_k", omission, {1: "FLAW"}, "FLAW") is True
    pair = contest(index=1, kind="contradiction", pair=[1, 3])
    assert inject.restored("duplicate_k_opposite", pair,
                           {1: "NOT A CONTRADICTION"}, "FLAW") is False
    assert inject.restored("duplicate_k_opposite", pair, {1: "FLAW"}, "FLAW") is True


# --------------------------------------------------------------------------- #
# the scorer — the paired false alarm on the control
# --------------------------------------------------------------------------- #


def test_no_contests_is_no_false_alarm_of_any_kind():
    assert inject.false_alarms([], findings(), k=1) == {
        "flip_k": False, "delete_k": False, "duplicate_k_opposite": False}


def test_a_finding_contest_on_k_is_the_flip_false_alarm():
    alarms = inject.false_alarms(
        [contest(kind="finding", finding=1, should_be="NOT A FLAW")], findings(), k=1)
    assert alarms["flip_k"] is True
    assert alarms["delete_k"] is False and alarms["duplicate_k_opposite"] is False
    # A finding contest on some OTHER finding is not the paired alarm.
    assert inject.false_alarms(
        [contest(kind="finding", finding=2, should_be="FLAW")],
        findings(), k=1)["flip_k"] is False


def test_an_omission_overlapping_any_listed_finding_is_the_delete_false_alarm():
    assert inject.false_alarms(
        [contest(kind="omission", record_says=[PASSAGE_2])],
        findings(), k=1)["delete_k"] is True
    # Overlapping nothing in the list is not a false alarm under this rule.
    assert inject.false_alarms(
        [contest(kind="omission", record_says=["a wholly unrelated sentence entirely"])],
        findings(), k=1)["delete_k"] is False


def test_any_contradiction_is_the_duplicate_false_alarm():
    alarms = inject.false_alarms([contest(kind="contradiction", pair=[1, 2])],
                                 findings(), k=1)
    assert alarms["duplicate_k_opposite"] is True


def test_a_void_contest_is_not_a_false_alarm_either():
    alarms = inject.false_alarms(
        [contest(kind="contradiction", pair=[1, 2], void=True),
         contest(kind="finding", finding=1, should_be="NOT A FLAW", void=True),
         contest(kind="omission", record_says=[PASSAGE_1], void=True)],
        findings(), k=1)
    assert alarms == {"flip_k": False, "delete_k": False,
                      "duplicate_k_opposite": False}


# --------------------------------------------------------------------------- #
# the draw
# --------------------------------------------------------------------------- #


def _cells(tree: str, n: int) -> list[inject.Cell]:
    return [inject.Cell(tree=tree, tree_path=Path(tree), cell_id=f"{tree}-c{i}",
                        run_dir=Path(tree), item_id=f"i{i}", subset="s",
                        condition="debate", findings=findings()) for i in range(n)]


def test_the_draw_is_balanced_across_the_trees_and_capped():
    drawn = inject.draw({"a": _cells("a", 30), "b": _cells("b", 30)}, 10, seed=0)
    assert len(drawn) == 10
    assert sum(1 for c in drawn if c.tree == "a") == 5

def test_an_unequal_pool_gives_the_smaller_tree_everything_it_has():
    drawn = inject.draw({"a": _cells("a", 30), "b": _cells("b", 3)}, 20, seed=0)
    assert sum(1 for c in drawn if c.tree == "b") == 3
    assert sum(1 for c in drawn if c.tree == "a") == 17


def test_the_draw_and_k_are_reproducible_from_the_seed():
    first = inject.draw({"a": _cells("a", 20)}, 8, seed=7)
    second = inject.draw({"a": _cells("a", 20)}, 8, seed=7)
    assert [(c.cell_id, c.k) for c in first] == [(c.cell_id, c.k) for c in second]
    other = inject.draw({"a": _cells("a", 20)}, 8, seed=8)
    assert [c.cell_id for c in other] != [c.cell_id for c in first]
    assert all(1 <= c.k <= len(c.findings) for c in first)


# --------------------------------------------------------------------------- #
# the guard
# --------------------------------------------------------------------------- #


def test_a_live_run_refuses_while_the_prereg_is_absent(tmp_path, monkeypatch, capsys):
    tree = build_tree(tmp_path / "tree")
    monkeypatch.setattr(inject, "RULES_PATH", tmp_path / "nope" / "PREREG.md")
    code = inject.main(["--tree", str(tree), "--outputs", str(tmp_path / "out")])
    assert code == 1
    assert "REFUSING TO RUN" in capsys.readouterr().out
    # And nothing was written: a refusal must not leave a half-built fixture behind.
    assert not (tmp_path / "out").exists()


def test_dry_run_and_stub_do_not_need_the_prereg(tmp_path, monkeypatch, capsys):
    tree = build_tree(tmp_path / "tree")
    monkeypatch.setattr(inject, "RULES_PATH", tmp_path / "nope" / "PREREG.md")
    assert inject.main(["--tree", str(tree), "--dry-run",
                        "--outputs", str(tmp_path / "out")]) == 0
    assert "dry run — nothing was sent." in capsys.readouterr().out
    assert inject.main(["--tree", str(tree), "--stub",
                        "--outputs", str(tmp_path / "out")]) == 0


# --------------------------------------------------------------------------- #
# the whole loop, offline, on a synthetic tree
# --------------------------------------------------------------------------- #


def _judge_reply() -> str:
    return inject.render_findings_list(findings())


def build_tree(root: Path, cells: int = 2) -> Path:
    """A minimal finished `fd1` tree: `experiment.json` plus decided cells with findings.

    Written with `RunWriter` rather than by hand, so that what the instrument reads is a
    directory this harness would really have produced — `load_run_record` refuses
    anything else, and a fixture that faked its way past it would prove nothing.
    """
    config = make_config(judge_form="findings", challenger_variant="findings",
                         challenger_model="fake/challenger",
                         recourse_judge_model="fake/judge",
                         judge_model="fake/judge")
    client_config = ClientConfig(
        base_url="https://x/api", max_concurrency=2, max_attempts=2,
        backoff_base_s=1.0, backoff_cap_s=5.0, connect_timeout_s=5.0,
        read_timeout_s=30.0, run_timeout_s=300.0)
    root.mkdir(parents=True, exist_ok=True)
    (root / "experiment.json").write_text(json.dumps({
        "name": root.name, "conditions": ["debate"], "repeats": 1,
        "config": config.to_dict(), "client_config": client_config.to_dict(),
    }), encoding="utf-8")
    sides = make_sides()
    for number in range(cells):
        item = make_item(item_id=f"synthetic-{number}-flawed",
                         row_id=f"synthetic:{number}", solution=SOLUTION)
        cell_dir = root / "cells" / f"{item.item_id}__debate__r1" / "runs"
        cell_dir.mkdir(parents=True, exist_ok=True)
        writer = RunWriter.create(root=cell_dir, item=item, sides=sides, config=config,
                                  client_config=client_config, condition="debate")
        transcript = Transcript()
        for round_number in (1, 2):
            for speaker, passage in ((Speaker.ALICE, PASSAGE_1),
                                     (Speaker.BOB, PASSAGE_2)):
                transcript.add(make_turn(
                    round_number, speaker, sides.side_for(speaker),
                    argument=(f"{speaker.value} says the text where "
                              f'"{passage}" is the problem, in round {round_number}.')))
        writer.record_turn(transcript)
        writer.record_findings(findings(), verdict="FLAWED", parse_mode="strict")
        writer.record_verdict(
            Verdict(verdict="FLAWED", parse_mode="strict", raw=_judge_reply(),
                    call_id=f"c-judge-{number}", finish_reason="stop", correct=True,
                    reasoning=_judge_reply()),
            transcript)
        writer.finish("completed")
    return root


def test_the_synthetic_tree_is_one_load_run_record_accepts(tmp_path):
    # Guards the fixture itself: if `load_run_record` ever refused it, every assertion
    # below would pass vacuously on an empty cell list.
    arm = inject.read_arm(build_tree(tmp_path / "fd1-synthetic", cells=3))
    assert len(arm.cells) == 3
    assert not arm.losses
    assert all(len(cell.findings) == 2 for cell in arm.cells)
    assert arm.config.recourse_judge_model_for() == "fake/judge"


def test_stub_end_to_end_writes_rows_a_manifest_and_a_report(tmp_path):
    tree = build_tree(tmp_path / "fd1-synthetic")
    outputs = tmp_path / "out"
    assert inject.main(["--tree", str(tree), "--stub", "--outputs", str(outputs),
                        "--max-lists", "2"]) == 0

    arm = tree.name
    for variant in inject.VARIANTS:
        rows = inject.load_rows(outputs, arm, variant)
        assert len(rows) == 2, variant
        assert all(r.failure is None for r in rows), variant
        assert all(r.prompt_sha and r.variant_sha for r in rows), variant

    # The manifest describes the fixture: one line per (cell, variant) with the drawn k,
    # the ruling that finding originally carried and the injected span.
    manifest = [json.loads(line) for line in
                (outputs / "manifest.jsonl").read_text().splitlines()]
    assert len(manifest) == 8
    assert {m["variant"] for m in manifest} == set(inject.VARIANTS)
    assert all(m["original_ruling"] in ("FLAW", "NOT A FLAW") for m in manifest)
    assert all(m["span"] for m in manifest if m["variant"] != "control")
    assert all(not m["span"] for m in manifest if m["variant"] == "control")

    # Every injected variant was detected and restored by the scripted stub, and the
    # ruling was bought only where the detection happened.
    for variant in inject.INJECTED:
        rows = inject.load_rows(outputs, arm, variant)
        assert all(r.detected for r in rows), variant
        assert all(r.restored for r in rows), variant
        assert all(r.ruling_call_id for r in rows), variant
    controls = inject.load_rows(outputs, arm, "control")
    assert all(c.stance == "declined" for c in controls)
    assert all(c.detected is None and not c.ruling_call_id for c in controls)
    assert all(c.false_alarm_flip is False for c in controls)

    report = (outputs / "report.md").read_text()
    for variant in inject.INJECTED:
        assert f"`{variant}`" in report
    assert "the challenger on unaltered lists" in report
    # And the wire log is on disk, as the repo rule requires of every generation.
    assert (outputs / f"calls-{arm}.jsonl").is_file()


def test_the_stub_run_is_resumable_and_force_re_measures(tmp_path, capsys):
    tree = build_tree(tmp_path / "fd1-synthetic", cells=1)
    outputs = tmp_path / "out"
    argv = ["--tree", str(tree), "--stub", "--outputs", str(outputs)]
    assert inject.main(argv) == 0
    first = inject.load_rows(outputs, tree.name, "flip_k")[0]

    capsys.readouterr()
    assert inject.main(argv) == 0
    assert "already on disk" in capsys.readouterr().out
    again = inject.load_rows(outputs, tree.name, "flip_k")[0]
    assert again.call_id == first.call_id, "a resumed row must not be re-measured"

    capsys.readouterr()
    assert inject.main(argv + ["--force"]) == 0
    assert "already on disk" not in capsys.readouterr().out
    forced = inject.load_rows(outputs, tree.name, "flip_k")[0]
    assert forced.call_id != first.call_id


def test_rows_from_the_other_mode_are_never_resumed(tmp_path, capsys):
    """The one footgun a stub mode has: rows of the same shape as paid ones.

    A `--stub` row and a paid row share a fixture and a digest, so a run that resumed
    across the two would report scripted replies as measurements, or pay again for what
    the fixture already answered. The mode is recorded on the row and a mismatch is
    stale — asserted here by relabelling a stub row as a live one and watching the stub
    run buy it again.
    """
    tree = build_tree(tmp_path / "fd1-synthetic", cells=1)
    outputs = tmp_path / "out"
    argv = ["--tree", str(tree), "--stub", "--outputs", str(outputs)]
    assert inject.main(argv) == 0
    rows = inject.load_rows(outputs, tree.name, "flip_k")
    assert all(r.stub for r in rows)
    assert "OFFLINE FIXTURE" in (outputs / "report.md").read_text()
    first_call = rows[0].call_id

    rows[0].stub = False           # as a paid row would be recorded
    inject.save_rows(outputs, tree.name, "flip_k", rows)
    capsys.readouterr()
    assert inject.main(argv) == 0
    assert inject.load_rows(outputs, tree.name, "flip_k")[0].call_id != first_call


def test_a_row_measured_against_a_different_variant_text_is_bought_again(tmp_path):
    tree = build_tree(tmp_path / "fd1-synthetic", cells=1)
    outputs = tmp_path / "out"
    argv = ["--tree", str(tree), "--stub", "--outputs", str(outputs)]
    assert inject.main(argv) == 0
    rows = inject.load_rows(outputs, tree.name, "flip_k")
    first_call = rows[0].call_id
    rows[0].variant_sha = "stale"
    inject.save_rows(outputs, tree.name, "flip_k", rows)

    assert inject.main(argv) == 0
    assert inject.load_rows(outputs, tree.name, "flip_k")[0].call_id != first_call


def test_the_instrument_refuses_a_tree_that_is_not_a_findings_arm(tmp_path):
    tree = build_tree(tmp_path / "verdict-arm")
    data = json.loads((tree / "experiment.json").read_text())
    data["config"]["challenger_variant"] = "neutral"
    data["config"]["judge_form"] = "verdict"
    (tree / "experiment.json").write_text(json.dumps(data))
    with pytest.raises(SystemExit, match="findings"):
        inject.read_arm(tree)


def test_a_tree_with_no_experiment_json_is_refused_with_its_reason(tmp_path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(SystemExit, match="no experiment.json"):
        inject.read_arm(tmp_path / "empty")


def test_two_trees_sharing_a_basename_are_refused(tmp_path):
    one = build_tree(tmp_path / "a" / "fd1-synthetic")
    two = build_tree(tmp_path / "b" / "fd1-synthetic")
    with pytest.raises(SystemExit, match="basename"):
        inject.main(["--tree", str(one), "--tree", str(two), "--dry-run"])


def test_lists_shorter_than_the_minimum_are_counted_not_measured(tmp_path):
    tree = build_tree(tmp_path / "fd1-synthetic", cells=1)
    # Rewrite the one cell's findings down to a single entry.
    run_dir = next((tree / "cells").glob("*/runs/*"))
    stored = json.loads((run_dir / "findings.json").read_text())
    stored["findings"] = stored["findings"][:1]
    (run_dir / "findings.json").write_text(json.dumps(stored))
    arm = inject.read_arm(tree)
    assert arm.cells == []
    assert arm.losses[f"fewer than {inject.MIN_FINDINGS} findings"] == 1


def test_a_control_that_invents_a_contest_is_scored_as_a_false_alarm(tmp_path,
                                                                    monkeypatch):
    """The false-alarm column, end to end rather than only as a rule.

    The stub's control declines by default, so the paired column is all False in a plain
    offline run — which would leave the one place the instrument SUBTRACTS untested. Here
    the control raises a well-formed contradiction between the two findings, which is the
    contest that would have scored a detection under `duplicate_k_opposite`.
    """
    tree = build_tree(tmp_path / "fd1-synthetic", cells=1)
    outputs = tmp_path / "out"
    plain = inject.default_stub_script

    def script_with_a_false_alarm(plan):
        inner = plain(plan)

        def script(meta, messages):
            purpose = str(meta.get("purpose") or "")
            if ":control:" in purpose and meta.get("role") == "challenger":
                return ("Thinking: I read the list.\n"
                        "Argument:\n"
                        "1. Contests: contradiction\n"
                        "   Findings: 1 and 2\n"
                        "   Why: these two entries say the same thing two ways.\n"
                        "\nDecision: REVERSE")
            return inner(meta, messages)

        return script

    monkeypatch.setattr(inject, "default_stub_script", script_with_a_false_alarm)
    assert inject.main(["--tree", str(tree), "--stub", "--outputs", str(outputs)]) == 0

    control = inject.load_rows(outputs, tree.name, "control")[0]
    assert control.stance == "contests"
    assert control.contests_contradiction_n == 1
    assert control.false_alarm_duplicate is True
    # And only that one: the paired columns are three separate rates, never pooled.
    assert control.false_alarm_flip is False and control.false_alarm_delete is False
    report = (outputs / "report.md").read_text()
    assert "| +0 |" in report, "one detection minus one false alarm is a net of zero"


def test_two_trees_that_rejudged_the_same_cells_do_not_collide(tmp_path):
    """The arms share their cell ids — both re-judge `jd3-main` — so every key the
    instrument uses has to carry the tree. A collision would answer one arm's challenger
    with the other arm's contest, on the other arm's `k`, and record the miss as a
    detection failure."""
    weak = build_tree(tmp_path / "fd1-weak", cells=2)
    strong = build_tree(tmp_path / "fd1-strong", cells=2)
    outputs = tmp_path / "out"
    assert inject.main(["--tree", str(weak), "--tree", str(strong), "--stub",
                        "--outputs", str(outputs)]) == 0
    cells = {c.name for c in (weak / "cells").glob("*")}
    assert cells == {c.name for c in (strong / "cells").glob("*")}, "shared cell ids"
    for arm in (weak.name, strong.name):
        for variant in inject.INJECTED:
            rows = inject.load_rows(outputs, arm, variant)
            assert len(rows) == 2, (arm, variant)
            assert all(r.detected for r in rows), (arm, variant)
            assert all(r.restored for r in rows), (arm, variant)

"""Reading spend back off the wire log.

Every assertion here exists because the arm comparison turns on holding compute
roughly constant, and "roughly constant" has to be a number. A crash or a
silent zero in this module would not fail a run — it would quietly remove the
only check on the experiment's main confound.
"""

from __future__ import annotations

import json

from constitutional_debate.accounting import (
    OFF_PATH_ROLES,
    Usage,
    aggregate_calls,
    aggregate_tree,
    split_calls,
    usage_from_record,
)


def openrouter_record(**kw) -> dict:
    """The shape OpenRouterClient actually writes, taken from a real log."""
    base = dict(
        call_id="c1", role="debater", speaker="Alice", round=1, purpose="turn",
        attempt=1, status=200, provider="GMICloud",
        response_model="deepseek/deepseek-v4-flash", finish_reason="stop",
        has_native_reasoning=False, latency_ms=1200,
        request_body={"model": "deepseek/deepseek-v4-flash"},
        response_body={},
        usage={
            "prompt_tokens": 1352, "completion_tokens": 2575, "total_tokens": 3927,
            "cost": 0.0005643736, "is_byok": False,
            "prompt_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
            "completion_tokens_details": {"reasoning_tokens": 0, "image_tokens": 0},
        },
    )
    return {**base, **kw}


def fake_client_record(**kw) -> dict:
    """FakeClient's shape: prompt/completion only, no cost, no detail dicts."""
    base = dict(
        call_id="c1", role="judge", speaker=None, round=None, purpose="judge",
        attempt=1, status=200,
        usage={"prompt_tokens": 10, "completion_tokens": 3},
    )
    return {**base, **kw}


def write_log(tmp_path, records, name="calls.jsonl"):
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# reading one record
# --------------------------------------------------------------------------- #


def test_a_real_record_is_read_including_the_reported_cost():
    """OpenRouter reports the actual charge, so no local price table is needed.

    That matters beyond convenience: the same model id is served by different
    providers call to call, and a local table would cost them all identically.
    """
    u = usage_from_record(openrouter_record())
    assert u.prompt_tokens == 1352
    assert u.completion_tokens == 2575
    assert u.cost_usd == 0.0005643736
    assert u.calls == 1 and u.attempts == 1


def test_reasoning_and_cached_tokens_are_read_from_their_nested_dicts():
    r = openrouter_record()
    r["usage"]["completion_tokens_details"]["reasoning_tokens"] = 900
    r["usage"]["prompt_tokens_details"]["cached_tokens"] = 400
    u = usage_from_record(r)
    assert u.reasoning_tokens == 900
    assert u.cached_tokens == 400


def test_a_fake_client_record_reads_as_zeros_not_a_keyerror():
    """The offline suite must be able to run this module over its own logs."""
    u = usage_from_record(fake_client_record())
    assert u.prompt_tokens == 10 and u.completion_tokens == 3
    assert u.reasoning_tokens == 0 and u.cost_usd == 0.0


def test_a_failed_attempt_costs_nothing_but_still_counts_as_an_attempt():
    """What was spent, not what succeeded."""
    u = usage_from_record({"role": "debater", "purpose": "turn", "status": 500})
    assert u.attempts == 1
    assert u.total_tokens == 0 and u.cost_usd == 0.0


def test_a_repair_is_an_attempt_but_not_a_second_call():
    """7 calls over 10 attempts is a fact about the run worth being able to see."""
    u = usage_from_record(openrouter_record(purpose="repair"))
    assert u.attempts == 1
    assert u.calls == 0


def test_usage_adds():
    assert (Usage(calls=1, cost_usd=0.5) + Usage(calls=2, cost_usd=0.25)) == Usage(
        calls=3, cost_usd=0.75
    )


# --------------------------------------------------------------------------- #
# aggregating a run
# --------------------------------------------------------------------------- #


def test_grading_is_kept_off_the_decision_path_total(tmp_path):
    """The load-bearing split.

    Grading runs over a finished directory and appends to its wire log. Folded
    into the decision total it would inflate whichever arm it graded, which is
    the one number the arm comparison depends on.
    """
    log = write_log(tmp_path, [
        openrouter_record(role="debater"),
        openrouter_record(role="judge", purpose="judge"),
        openrouter_record(role="grader", purpose="grade_objection"),
        openrouter_record(role="validator", purpose="validate_case"),
    ])
    summary = aggregate_calls(log)
    assert summary["decision_path"]["calls"] == 2
    assert summary["off_path"]["calls"] == 2
    assert "grader" in OFF_PATH_ROLES and "validator" in OFF_PATH_ROLES
    # and the two must partition the spend exactly, with no rounding in between
    decision, off = split_calls(log)
    assert decision.cost_usd + off.cost_usd == 4 * 0.0005643736


def test_repairs_and_failures_are_counted_separately(tmp_path):
    log = write_log(tmp_path, [
        openrouter_record(),
        openrouter_record(purpose="repair"),
        openrouter_record(status=500, usage=None),
    ])
    summary = aggregate_calls(log)
    assert summary["repairs"] == 1
    assert summary["failed_attempts"] == 1
    assert summary["decision_path"]["attempts"] == 3
    assert summary["decision_path"]["calls"] == 2


def test_the_provider_spread_is_surfaced(tmp_path):
    """One model id, many providers — the confound the README warns about."""
    log = write_log(tmp_path, [
        openrouter_record(provider="GMICloud"),
        openrouter_record(provider="DeepInfra"),
        openrouter_record(provider="DeepInfra"),
    ])
    assert aggregate_calls(log)["providers"] == {"DeepInfra": 2, "GMICloud": 1}


def test_a_truncated_final_line_does_not_lose_the_rest(tmp_path):
    """A process killed mid-append must not cost a directory its accounting."""
    path = tmp_path / "calls.jsonl"
    path.write_text(
        json.dumps(openrouter_record()) + "\n" + '{"role": "debater", "usa',
        encoding="utf-8",
    )
    assert aggregate_calls(path)["decision_path"]["calls"] == 1


def test_a_missing_log_aggregates_to_nothing(tmp_path):
    summary = aggregate_calls(tmp_path / "nope.jsonl")
    assert summary["decision_path"]["calls"] == 0


def test_a_tree_sums_every_run_under_it(tmp_path):
    write_log(tmp_path / "runs" / "a", [openrouter_record()])
    write_log(tmp_path / "runs" / "b", [openrouter_record(), openrouter_record()])
    tree = aggregate_tree(tmp_path)
    assert tree["runs"] == 2
    assert tree["decision_path"]["calls"] == 3
    assert tree["cost_usd"] == round(3 * 0.0005643736, 6)


def test_summing_across_runs_does_not_round_once_per_run(tmp_path):
    """Usage.to_dict rounds for display; aggregating those dicts would compound it."""
    for i in range(50):
        write_log(tmp_path / "runs" / str(i), [openrouter_record()])
    exact = sum(split_calls(p)[0].cost_usd
                for p in sorted((tmp_path / "runs").rglob("calls.jsonl")))
    assert exact == 50 * 0.0005643736
    assert aggregate_tree(tmp_path)["cost_usd"] == round(exact, 6)


# --------------------------------------------------------------------------- #
# native reasoning: published, not suppressed
# --------------------------------------------------------------------------- #


def test_reasoning_withheld_is_detected_not_assumed_absent():
    """Billed reasoning tokens with no text is the one uninspectable channel."""
    from constitutional_debate.client import Completion

    def completion(reasoning, reasoning_tokens):
        return Completion(
            call_id="c", content="Argument: x", finish_reason="stop", model="m",
            provider="p", reasoning=reasoning,
            usage={"completion_tokens_details": {"reasoning_tokens": reasoning_tokens}},
        )

    assert completion(None, 900).reasoning_withheld is True
    assert completion("I considered...", 900).reasoning_withheld is False
    assert completion(None, 0).reasoning_withheld is False
    # A provider that reports no details at all must not read as withholding.
    bare = Completion(call_id="c", content="x", finish_reason="stop", model="m",
                      provider="p", reasoning=None, usage={})
    assert bare.reasoning_withheld is False


def test_every_role_carries_the_provider_channel_not_just_debaters():
    """The claim is that every channel is published, not the debaters' only.

    A judge's hidden deliberation moves the decision more directly than anyone
    else's, so a Verdict that cannot carry it makes the claim false for the one
    role that decides.
    """
    from constitutional_debate.types import Challenge, Ruling, Verdict

    for cls in (Verdict, Challenge, Ruling):
        fields = set(cls.__dataclass_fields__)
        assert "native_reasoning" in fields, f"{cls.__name__} drops the channel"
        assert "reasoning_withheld" in fields, f"{cls.__name__} cannot flag it"

#!/usr/bin/env python
"""Mechanically verify that a recorded run's prompts follow from its record.

    uv run python scripts/verify_run.py outputs/runs/<run_id>

This is what the whitebox claim actually amounts to. Prompt construction is a
pure function of ``(task, config, seating, constitution, prior turns)`` — all
five of which are in the run directory — so a third party can re-derive every
request that was sent and byte-compare it against the wire log. What that
establishes:

* nothing was injected between rounds that is not in the record;
* the judge saw only public Arguments, never a debater's private Thinking;
* whichever answer is gold left no trace in any prompt;
* the constitution, if any, reached both debaters and the judge;
* the recorded verdict, and the reasoning published alongside it, both come from
  the judge's recorded response;
* the recorded verdict resolves through the recorded seating;
* the derived artifacts — the transcript's question/answers/positions header and
  the two markdown renderings — say nothing the record does not support.

What it cannot establish: that the *generations* would recur. Sampling is not
reproducible, and OpenRouter's seed is best-effort and ignored by some
providers, which is why each call records its resolved provider and model.

Exits non-zero if any check fails.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import fields
from pathlib import Path

from constitutional_debate.artifacts import (
    NOT_PUBLIC_BANNER,
    TRANSCRIPT_DOC_KEYS,
    defang_markdown,
    render_full_markdown,
    render_public_markdown,
    transcript_document,
)
from constitutional_debate.client import NORMAL_FINISH_REASONS
from constitutional_debate.config import DebateConfig
from constitutional_debate.prompts import (
    DEBATER_REPAIR,
    JUDGE_REPAIR,
    PROFILES,
    MalformedOutputError,
    build_debater_messages,
    build_judge_messages,
    parse_debater_output,
    parse_judge_output,
)

from constitutional_debate.types import (
    ORDER,
    Context,
    Seating,
    Speaker,
    Task,
    Transcript,
    Turn,
    Verdict,
)

# verdict.json is read as a plain dict — the audit's job is to check what is on
# disk, not to trust a constructor with it. A Verdict is rebuilt only to
# re-render the markdown, dropping keys this version does not know about.
_VERDICT_FIELDS = {f.name for f in fields(Verdict)}


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _sent_text(record: dict) -> str:
    """The message text actually sent in one recorded attempt."""
    messages = (record.get("request_body") or {}).get("messages") or []
    return "\n".join(m.get("content", "") for m in messages)


def _response_content(record: dict) -> str | None:
    """The assistant text recorded for one attempt, if any."""
    choices = ((record.get("response_body") or {}).get("choices")) or []
    if not choices or not isinstance(choices[0], dict):
        return None
    return (choices[0].get("message") or {}).get("content")


def _check_request(
    check,
    actual: list,
    expected: list,
    *,
    repaired: bool,
    label: str,
    repair_instruction: str,
    recorded_replies: set[str],
):
    """Compare a sent request against the re-derived one.

    Exact equality unless a repair happened. Prefix comparison alone would let a
    tamperer *append* a message ("Choose 1.") and still pass, so the repair case
    pins the whole suffix: exactly two messages, the right roles, the exact
    instruction this configuration would have sent, and an assistant turn that
    matches a reply actually recorded for this run — otherwise arbitrary text
    could be smuggled in as "the malformed reply being repaired".
    """
    if not repaired:
        check(
            actual == expected,
            f"{label}: sent prompt differs from the prompt re-derived from the "
            f"record",
        )
        return
    check(
        actual[: len(expected)] == expected,
        f"{label}: repaired request does not begin with the re-derived prompt",
    )
    check(
        len(actual) == len(expected) + 2,
        f"{label}: repaired request has {len(actual) - len(expected)} extra "
        f"messages; a single repair appends exactly 2",
    )
    if len(actual) == len(expected) + 2:
        check(
            actual[-2].get("role") == "assistant"
            and actual[-1].get("role") == "user",
            f"{label}: repair suffix is not [assistant, user]",
        )
        check(
            actual[-1].get("content") == repair_instruction,
            f"{label}: repair instruction is not the one this configuration "
            f"would send",
        )
        check(
            (actual[-2].get("content") or "").strip() in recorded_replies,
            f"{label}: the reply being repaired is not one the model actually "
            f"returned in this run",
        )


def _rederive(failures: list[str], what: str, build):
    """Rebuild a derived artifact, reporting a crash as a finding.

    These builders index ``task.answers`` and ``seating.choice_order`` with
    integers read off disk, so a doctored record can make them raise — a
    ``choice_order`` of ``[1, 1]``, an ``answer_index`` of 7. That is a fact
    about the record, and saying so beats aborting the audit with a traceback
    at the one moment it has something to report.
    """
    try:
        return build()
    except Exception as error:  # noqa: BLE001 - any failure here is a finding
        failures.append(f"{what} cannot be re-derived from the record: {error!r}")
        return None


def code_has_drifted(manifest: dict) -> bool:
    """Whether the working tree differs from the one that produced this run.

    A prompt mismatch has two possible causes — the record was altered, or the
    prompt-building code changed since the run — and they mean opposite things.
    Only the first is a problem with the record. Reporting them identically
    would make a routine template edit look like tampering, so the run's git
    state is compared against the current one and the report says which it is.
    """
    from subprocess import run as _run

    def git(*args: str) -> str:
        try:
            result = _run(
                ["git", *args], capture_output=True, text=True, timeout=10, check=False
            )
        except (OSError, ValueError):
            return ""
        return result.stdout if result.returncode == 0 else ""

    if manifest.get("git_sha") and git("rev-parse", "HEAD").strip() != manifest[
        "git_sha"
    ]:
        return True
    return git("diff", "HEAD") != (manifest.get("git_diff") or "")


def load_run(run_dir: Path):
    manifest = _read_json(run_dir / "run.json")
    task = Task.from_dict(_read_json(run_dir / "task.json"))
    config = DebateConfig(**_read_json(run_dir / "config.json"))

    seating_data = _read_json(run_dir / "seating.json")
    seating = Seating(
        alice_answer=seating_data["alice_answer"],
        bob_answer=seating_data["bob_answer"],
        choice_order=tuple(seating_data["choice_order"]),
        seed_material=seating_data["seed_material"],
    )

    constitution_path = run_dir / "constitution.md"
    context = (
        Context(
            kind="constitution",
            text=constitution_path.read_text(encoding="utf-8").strip(),
            source=manifest.get("constitution_source"),
        )
        if constitution_path.is_file()
        else None
    )

    document = _read_json(run_dir / "transcript.json")
    transcript = Transcript()
    for turn in document["turns"]:
        transcript.add(
            Turn(
                round=turn["round"],
                speaker=Speaker(turn["speaker"]),
                answer_index=turn["answer_index"],
                thinking=turn["thinking"],
                argument=turn["argument"],
                word_count=turn["word_count"],
                parse_mode=turn["parse_mode"],
                repair_attempts=turn["repair_attempts"],
                finish_reason=turn.get("finish_reason"),
                has_native_reasoning=turn.get("has_native_reasoning", False),
                call_id=turn["call_id"],
                raw=turn.get("raw", ""),
            )
        )

    calls = [
        json.loads(line)
        for line in (run_dir / "calls.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    verdict = _read_json(run_dir / "verdict.json")
    return (
        manifest, task, config, seating, context, document, transcript, calls, verdict
    )


MIN_DISTINCTIVE_THINKING = 40


def verify(run_dir: Path, notes: list[str] | None = None) -> list[str]:
    """Return a list of failures; empty means the record checks out.

    ``notes`` collects non-fatal observations about audit coverage.
    """
    failures: list[str] = []
    notes = notes if notes is not None else []

    def check(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    (
        manifest, task, config, seating, context, document, transcript, calls, verdict
    ) = load_run(run_dir)
    profile = PROFILES[manifest["profile"]]

    # Checked first: everything below joins on these keys, and a KeyError here
    # would abort with a traceback instead of a clean failure report.
    malformed = [c for c in calls if not {"call_id", "role", "attempt"} <= set(c)]
    check(not malformed, f"{len(malformed)} calls.jsonl record(s) lack join keys")
    calls = [c for c in calls if "call_id" in c]
    by_call_id = {c["call_id"]: c for c in calls}

    successful = [
        c
        for c in calls
        if c.get("status") == 200 and not (c.get("response_body") or {}).get("error")
    ]
    # Every reply the model actually produced in this run. A repair may only
    # quote back one of these.
    recorded_replies = {
        (_response_content(c) or "").strip() for c in calls if _response_content(c)
    }
    check(
        len(successful) >= 2 * config.n_rounds + 1,
        f"expected at least {2 * config.n_rounds + 1} successful calls, "
        f"found {len(successful)}",
    )

    # --- every debater turn's prompt must re-derive exactly ----------------- #
    for turn in transcript.all_turns():
        record = by_call_id.get(turn.call_id)
        if record is None:
            failures.append(
                f"round {turn.round} {turn.speaker}: call_id {turn.call_id} "
                f"is not in calls.jsonl — the transcript cannot be joined to the "
                f"wire log"
            )
            continue

        expected = build_debater_messages(
            task, context, seating, config, transcript,
            speaker=turn.speaker, round=turn.round, profile=profile,
        )
        _check_request(
            check,
            record["request_body"]["messages"],
            expected,
            repaired=bool(turn.repair_attempts),
            label=f"round {turn.round} {turn.speaker}",
            repair_instruction=DEBATER_REPAIR.format(
                word_limit=config.word_limit_for(profile.key)
            ),
            recorded_replies=recorded_replies,
        )

        # Re-parse the recorded response. Without this the whole response half
        # of the wire log is unaudited, and an edited transcript.json that still
        # re-derives its own prompts would pass — including one that moved
        # private reasoning into the public argument.
        content = _response_content(record)
        if content is None:
            failures.append(
                f"round {turn.round} {turn.speaker}: no response content recorded"
            )
        else:
            try:
                thinking, argument, parse_mode = parse_debater_output(content)
            except MalformedOutputError as error:
                failures.append(
                    f"round {turn.round} {turn.speaker}: recorded response no "
                    f"longer parses ({error})"
                )
            else:
                check(
                    argument == turn.argument,
                    f"round {turn.round} {turn.speaker}: recorded argument is not "
                    f"what the recorded response parses to",
                )
                check(
                    thinking == turn.thinking,
                    f"round {turn.round} {turn.speaker}: recorded thinking is not "
                    f"what the recorded response parses to",
                )
                check(
                    parse_mode == turn.parse_mode,
                    f"round {turn.round} {turn.speaker}: parse_mode "
                    f"{turn.parse_mode!r} does not match a re-parse "
                    f"({parse_mode!r})",
                )
                check(
                    turn.raw.strip() == content.strip(),
                    f"round {turn.round} {turn.speaker}: recorded raw text differs "
                    f"from the recorded response",
                )

    # --- the judge's prompt and verdict must both re-derive ------------------ #
    judge_record = by_call_id.get(verdict["call_id"])
    if judge_record is None:
        failures.append("verdict call_id is not in calls.jsonl")
    else:
        _check_request(
            check,
            judge_record["request_body"]["messages"],
            build_judge_messages(
                task, context, seating, config, transcript, profile=profile
            ),
            repaired=bool(verdict.get("repair_attempts")),
            label="judge",
            repair_instruction=JUDGE_REPAIR,
            recorded_replies=recorded_replies,
        )
        check(
            bool(verdict.get("repair_attempts"))
            == verdict["parse_mode"].endswith("_after_repair"),
            "verdict repair_attempts disagrees with its parse_mode suffix",
        )

        # The decisive check. Comparing verdict.choice only against the seating
        # is circular: an edited verdict.json with a consistent choice and
        # answer_index would pass while inverting the decision. The recorded
        # judge response is what actually decided it.
        content = _response_content(judge_record)
        check(
            content is not None and content.strip() == verdict["raw"].strip(),
            "verdict raw text differs from the judge's recorded response",
        )
        if content is not None:
            try:
                choice, reasoning, parse_mode = parse_judge_output(content)
            except MalformedOutputError as error:
                failures.append(f"judge: recorded response no longer parses ({error})")
            else:
                check(
                    choice == verdict["choice"],
                    f"recorded choice {verdict['choice']} is not what the judge's "
                    f"recorded response parses to ({choice})",
                )
                check(
                    parse_mode == verdict["parse_mode"].removesuffix("_after_repair"),
                    "verdict parse_mode does not match a re-parse",
                )
                # The published grounds for the decision, so they must come from
                # the judge rather than from whoever last edited verdict.json.
                if "reasoning" in verdict:
                    check(
                        verdict["reasoning"] == reasoning,
                        "recorded judge reasoning is not what the judge's "
                        "recorded response parses to",
                    )
                else:
                    notes.append(
                        "verdict.json predates the reasoning field; the judge's "
                        "stated grounds are unchecked"
                    )

    # --- private reasoning must never have left the debater ------------------ #
    # A backstop. The primary guarantee is the response re-parse above: this
    # containment scan can only find text the parser already classified as
    # private, so it is blind by construction to a parser that misclassifies.
    for record in calls:
        sent = _sent_text(record)
        for turn in transcript.all_turns():
            # Very short thinking sections ("-", "1.") occur on flash-tier
            # models and would match boilerplate in every system prompt.
            if len(turn.thinking.strip()) < MIN_DISTINCTIVE_THINKING:
                continue
            if turn.call_id == record["call_id"]:
                continue  # a repair legitimately echoes that turn's own reply
            check(
                turn.thinking not in sent,
                f"call {record['call_id']} ({record.get('role')}) carries "
                f"round {turn.round} {turn.speaker}'s private Thinking",
            )

    unscanned = [
        t
        for t in transcript.all_turns()
        if len(t.thinking.strip()) < MIN_DISTINCTIVE_THINKING
    ]
    if unscanned:
        notes.append(
            f"{len(unscanned)} turn(s) had thinking too short to scan for "
            f"containment; covered by the response re-parse only"
        )

    # --- gold left no trace, in any prompt ----------------------------------- #
    if task.gold_index is not None:
        flipped = Task(
            task_id=task.task_id,
            question=task.question,
            answers=task.answers,
            gold_index=1 - task.gold_index,
            source=task.source,
        )
        for round_number in range(1, config.n_rounds + 1):
            for speaker in ORDER:
                kwargs = dict(speaker=speaker, round=round_number, profile=profile)
                check(
                    build_debater_messages(
                        flipped, context, seating, config, transcript, **kwargs
                    )
                    == build_debater_messages(
                        task, context, seating, config, transcript, **kwargs
                    ),
                    f"which answer is gold changes round {round_number} "
                    f"{speaker}'s prompt",
                )
        check(
            build_judge_messages(
                flipped, context, seating, config, transcript, profile=profile
            )
            == build_judge_messages(
                task, context, seating, config, transcript, profile=profile
            ),
            "which answer is gold changes the judge prompt",
        )

    # --- the constitution reached everyone ----------------------------------- #
    if context is not None:
        check(
            manifest.get("constitution_sha256") == context.sha256(),
            "constitution.md does not match the sha256 recorded in run.json",
        )
        for record in calls:
            check(
                context.text.strip() in _sent_text(record),
                f"call {record['call_id']} ({record.get('role')}) did not carry "
                f"the constitution",
            )

    # --- the verdict resolves through the recorded seating -------------------- #
    check(
        verdict["answer_index"] == seating.answer_index_for_choice(verdict["choice"]),
        f"verdict choice {verdict['choice']} does not resolve to answer "
        f"{verdict['answer_index']} under the recorded seating",
    )
    if task.gold_index is not None:
        check(
            verdict["correct"] == (verdict["answer_index"] == task.gold_index),
            "recorded correctness disagrees with gold_index",
        )

    # --- the derived artifacts must not say anything the record does not ------ #
    # transcript.json's header and the two markdown files restate data whose
    # home is task.json, seating.json and verdict.json. Restated data is data
    # that can disagree, and these are the artifacts a reader actually reads.
    if not TRANSCRIPT_DOC_KEYS <= set(document):
        notes.append(
            "transcript.json predates the question/answers/positions header; "
            "only its turns were checked"
        )
        expected_document = None
    else:
        expected_document = _rederive(
            failures,
            "transcript.json's header",
            lambda: transcript_document(task, seating, transcript),
        )
    if expected_document is not None:
        for key in ("question", "answers", "positions"):
            check(
                document[key] == expected_document[key],
                f"transcript.json's {key} disagrees with task.json/seating.json",
            )
        check(
            set(document) == TRANSCRIPT_DOC_KEYS,
            f"transcript.json carries unexpected top-level keys: "
            f"{sorted(set(document) - TRANSCRIPT_DOC_KEYS)}",
        )
        # For any field the loader reads, this is circular and proves nothing —
        # tampered arguments are caught by the response re-parse. What it does
        # catch is the field set itself: a "gold_index" smuggled into a turn
        # that a reader would believe, or a protocol field quietly dropped.
        check(
            document["turns"] == expected_document["turns"],
            "transcript.json's turns do not carry exactly the fields the "
            "protocol defines",
        )

    public_md = (run_dir / "transcript.public.md").read_text(encoding="utf-8")
    # The containment scan above covers calls.jsonl only, so a renderer that
    # leaked Thinking into the *published* artifact would pass an otherwise
    # clean audit. Nothing else checks this file's central promise. Both the raw
    # and the rendered form are scanned: a leak *through* the renderer arrives
    # defanged, and would slip past a search for the raw text.
    for turn in transcript.all_turns():
        if len(turn.thinking.strip()) < MIN_DISTINCTIVE_THINKING:
            continue
        check(
            turn.thinking not in public_md
            and defang_markdown(turn.thinking.strip()) not in public_md,
            f"transcript.public.md carries round {turn.round} {turn.speaker}'s "
            f"private Thinking",
        )

    # Notes, not failures: the markdown is derived and non-authoritative — no
    # prompt depends on it — so pinning presentation would make every heading
    # tweak retroactively condemn every earlier run.
    if public_md != render_public_markdown(transcript):
        notes.append(
            "transcript.public.md differs from the document re-rendered from the "
            "record (presentation only; the arguments themselves are checked above)"
        )

    full_path = run_dir / "transcript.full.md"
    if not full_path.is_file():
        notes.append("this run predates transcript.full.md")
    else:
        full_md = full_path.read_text(encoding="utf-8")
        check(
            NOT_PUBLIC_BANNER in full_md,
            "transcript.full.md does not carry the banner marking it unpublishable; "
            "it contains private Thinking and must say so",
        )
        rendered = _rederive(
            failures,
            "transcript.full.md",
            lambda: render_full_markdown(
                task,
                seating,
                transcript,
                Verdict(**{k: v for k, v in verdict.items() if k in _VERDICT_FIELDS}),
                judge_cot=config.judge_cot,
            ),
        )
        if rendered is not None and full_md != rendered:
            notes.append(
                "transcript.full.md differs from the document re-rendered from "
                "the record (presentation only; the record itself is checked above)"
            )

    # --- structural sanity ---------------------------------------------------- #
    check(
        len(transcript.turns) == 2 * config.n_rounds,
        f"expected {2 * config.n_rounds} turns, found {len(transcript.turns)}",
    )
    truncated = [
        t
        for t in transcript.all_turns()
        if t.finish_reason is not None and t.finish_reason not in NORMAL_FINISH_REASONS
    ]
    check(
        not truncated,
        f"{len(truncated)} turn(s) stopped on a non-normal finish_reason",
    )
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit a recorded debate run.")
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args(argv)

    if not (args.run_dir / "run.json").is_file():
        print(f"not a run directory: {args.run_dir}", file=sys.stderr)
        return 2

    manifest = _read_json(args.run_dir / "run.json")
    if manifest.get("status") != "completed":
        print(
            f"run status is {manifest.get('status')!r}; only completed runs can "
            f"be audited",
            file=sys.stderr,
        )
        return 2

    notes: list[str] = []
    failures = verify(args.run_dir, notes)
    for note in notes:
        print(f"  note: {note}")
    if failures:
        print(f"FAIL {args.run_dir} — {len(failures)} problem(s):")
        for failure in failures:
            print(f"  - {failure}")
        if code_has_drifted(manifest) and any(
            "re-derived" in failure for failure in failures
        ):
            print(
                "\nNOTE: the working tree differs from the one that produced this "
                "run, so prompt mismatches may reflect a change to the "
                "prompt-building code rather than an altered record. Check out "
                f"{manifest.get('git_sha')} (plus run.json's git_diff) and re-run "
                "this audit to tell the two apart."
            )
        return 1

    print(f"OK {args.run_dir}")
    print(
        "  every prompt re-derives from task + config + seating + constitution "
        "+ prior turns"
    )
    print("  every transcript entry re-parses from the recorded response")
    print("  no private Thinking reached an opponent, the judge, or the public")
    print("  transcript")
    print("  the verdict and the judge's stated reasoning both re-parse from the")
    print("  judge's response, and the verdict resolves through the recorded seating")
    print("  the transcript's question, answers and positions match task.json and")
    print("  seating.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

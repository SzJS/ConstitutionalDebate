#!/usr/bin/env python
"""Check that a recorded run says only what the record supports.

    uv run python scripts/verify_run.py outputs/runs/<run_id>

Transparency is a property of the published record, not of this script: what
makes the process whitebox is that a reader can see the question, the arguments,
the decision and the grounds it was given. This checks the weaker, mechanical
thing a reader cannot check by eye — that the published document is not
*misreporting* the run it describes. What it establishes:

* every argument and every decision in the record is what the recorded response
  actually says — nothing was rewritten after the fact;
* the reasoning published alongside a decision is the judge's own;
* no debater's private Thinking reached the opponent or the judge *during* the
  debate (it is published afterwards, which is a different thing);
* the constitution, if any, reached everyone it binds;
* the decision resolves through the recorded seating, and a ruling's answer
  follows from the ruling itself;
* the published document states the question, every argument, every Thinking
  section, which answer stands, and the grounds — reformatting it is a note,
  getting one of those wrong is a failure;
* the derived artifacts say nothing the record does not support.

What it cannot establish. The record is checked almost entirely against itself
and against the *responses* in the wire log; the requests are barely examined,
so the following are recorded but not verified:

* **That the generations would recur.** Sampling is not reproducible, and
  OpenRouter's seed is best-effort and ignored by some providers, which is why
  each call records its resolved provider and model.
* **What was in a prompt.** An instruction inserted into a request would pass.
  So would a judge shown a truncated transcript, or a recourse judge shown a
  different decision from the one in ``parent/``. Prompt construction is
  guarded by the test suite, not by the record.
* **That the run used the settings it records.** ``profile``, ``judge_cot``,
  ``turn_style`` and ``word_limit`` are published in ``config.json`` and are
  not checked against the wire, even where the readable document makes a claim
  about them — a decision with no grounds states in bold that ``judge_cot`` is
  why.
* **Which challenge arm produced a generated challenge**, **which side each
  recourse debater argued**, or **whether a supplied challenge is the one that
  was put to the judge**. The arm in particular is the variable the
  contestability claim turns on.
* **That a full-visibility challenge really saw what it claims.** The recorded
  ``visibility`` is what excuses the generator's own call from the containment
  scan, and nothing checks it against the request.
* **Which model served a debater or judge call.** Only the challenge
  generator's model is pinned against its request.
* **That a "repair" quotes a reply the model really gave.**

Exits non-zero if any check fails.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import fields
from pathlib import Path
from typing import NamedTuple

from constitutional_debate.artifacts import (
    PRIVATE_THINKING_NOTE,
    defang_markdown,
    RECOURSE_TRANSCRIPT_DOC_KEYS,
    TRANSCRIPT_DOC_KEYS,
    recourse_transcript_document,
    render_decision_record,
    render_recourse_record,
    transcript_document,
)
from constitutional_debate.client import NORMAL_FINISH_REASONS
from constitutional_debate.config import RECOURSE_ONLY_KEYS, DebateConfig
from constitutional_debate.persistence import tree_sha256
from constitutional_debate.prompts import (
    ARMS,
    PROFILES,
    VISIBILITIES,
    MalformedOutputError,
    parse_debater_output,
    parse_judge_output,
    parse_ruling_output,
)

from constitutional_debate.types import (
    ORDER,
    Challenge,
    Context,
    Ruling,
    Seating,
    Speaker,
    Task,
    Transcript,
    Turn,
    Verdict,
    compose_transcript,
    indent_continuations,
    neutralise_tags,
    resolve_ruling,
)

# verdict.json is read as a plain dict — the audit's job is to check what is on
# disk, not to trust a constructor with it. A Verdict is rebuilt only to
# re-render the markdown, dropping keys this version does not know about.
_VERDICT_FIELDS = {f.name for f in fields(Verdict)}
_RULING_FIELDS = {f.name for f in fields(Ruling)}
_CHALLENGE_FIELDS = {f.name for f in fields(Challenge)}


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


def _check_document_states(check, published: str, *, must_state: dict[str, str]) -> None:
    """The published document must not get the decisive statements wrong.

    A re-render mismatch is only a note, because presentation drifts and a
    heading tweak should not condemn every earlier record. But "presentation"
    and "names the wrong winner" are not the same kind of difference, and under
    a claim about what a reader can see, the second is the one that matters. So
    the statements a reader would be actively misled by are pinned here, and
    they survive any amount of reformatting: the question, every argument, every
    debater's reasoning, the sentence naming the answer that stands, and the
    grounds the deciding role actually gave.
    """
    for what, needle in must_state.items():
        if not needle.strip():
            continue
        check(
            defang_markdown(needle.strip()) in published,
            f"transcript.md does not state {what}, which the record says it "
            f"should — the published document and the record disagree about "
            f"something a reader would be misled by",
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


def _check_turn_responses(
    check,
    failures: list[str],
    *,
    turns,
    by_call_id: dict,
) -> None:
    """Check each turn against the response that produced it.

    Shared by both audits. This is what ties the published argument to something
    outside the transcript file: an edited ``transcript.json`` would still be
    internally consistent, so the recorded response is the only thing that can
    contradict it — including a transcript that moved private reasoning into the
    public argument.
    """
    for turn in turns:
        record = by_call_id.get(turn.call_id)
        if record is None:
            failures.append(
                f"round {turn.round} {turn.speaker}: call_id {turn.call_id} "
                f"is not in calls.jsonl — the transcript cannot be joined to the "
                f"wire log"
            )
            continue

        content = _response_content(record)
        if content is None:
            failures.append(
                f"round {turn.round} {turn.speaker}: no response content recorded"
            )
            continue
        try:
            thinking, argument, parse_mode = parse_debater_output(content)
        except MalformedOutputError as error:
            failures.append(
                f"round {turn.round} {turn.speaker}: recorded response no "
                f"longer parses ({error})"
            )
            continue
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
            f"{turn.parse_mode!r} does not match a re-parse ({parse_mode!r})",
        )
        check(
            turn.raw.strip() == content.strip(),
            f"round {turn.round} {turn.speaker}: recorded raw text differs "
            f"from the recorded response",
        )


class _Secret(NamedTuple):
    """One piece of private reasoning, and where it legitimately lives.

    A NamedTuple rather than a dataclass because this module is loaded by path
    (``spec_from_file_location``) as well as run as a script, and ``dataclass``
    resolves string annotations through ``sys.modules``, which a by-path load
    does not populate.
    """

    label: str  # e.g. "round 2 Alice" — what a finding should name
    text: str
    call_id: str  # the call that produced it; a repair may echo it back


def _secrets_from(turns) -> list[_Secret]:
    return [
        _Secret(label=f"round {t.round} {t.speaker}", text=t.thinking, call_id=t.call_id)
        for t in turns
    ]


def _distinctive(secrets: list[_Secret]) -> list[_Secret]:
    # Very short thinking sections ("-", "1.") occur on flash-tier models and
    # would match boilerplate in every system prompt.
    return [s for s in secrets if len(s.text.strip()) >= MIN_DISTINCTIVE_THINKING]


def _forms(text: str) -> tuple[str, ...]:
    """The forms private text could take once it has reached a prompt.

    Searching for the raw string alone is close to vacuous: everything that
    interpolates a turn into a prompt goes through ``indent_continuations``,
    which indents every continuation line by four spaces. Real thinking is
    multi-line — the prompts ask for a numbered plan — so a leak *through* the
    renderer would not contain the raw needle anywhere.
    """
    forms = (
        text,
        neutralise_tags(text),  # a standalone prompt block
        indent_continuations(text),  # a turn inside the transcript
    )
    # Order-preserving dedupe rather than a set: these are used as a sequence of
    # replacements, and set iteration order varies with PYTHONHASHSEED. An audit
    # whose behaviour depends on the hash seed is one nobody can reason about.
    return tuple(dict.fromkeys(forms))


def _check_thinking_containment(
    check,
    notes: list[str],
    *,
    secrets: list[_Secret],
    calls: list[dict],
    exempt_call_ids: frozenset[str] = frozenset(),
    strip_from_sent: tuple[str, ...] = (),
) -> None:
    """No private reasoning may appear in a request that is not its own.

    A backstop. The primary guarantee is the response re-parse: this scan can
    only find text the parser already classified as private, so it is blind by
    construction to a parser that misclassifies.

    ``exempt_call_ids`` covers a request that is *configured* to carry private
    reasoning — the full-visibility challenge generator, and only that.
    ``strip_from_sent`` removes the challenge text before scanning, so a
    challenge that quotes private reasoning is reported once, where it happened,
    rather than as a leak into every prompt that then quoted the challenge.
    """
    distinctive = [(s, _forms(s.text)) for s in _distinctive(secrets)]
    for record in calls:
        if record["call_id"] in exempt_call_ids:
            continue
        sent = _sent_text(record)
        for text in strip_from_sent:
            sent = sent.replace(text, " ")
        for secret, forms in distinctive:
            if secret.call_id == record["call_id"]:
                continue  # a repair legitimately echoes that turn's own reply
            check(
                all(form not in sent for form in forms),
                f"call {record['call_id']} ({record.get('role')}) carries "
                f"{secret.label}'s private Thinking",
            )

    unscanned = len(secrets) - len(_distinctive(secrets))
    if unscanned:
        notes.append(
            f"{unscanned} private section(s) were too short to scan for "
            f"containment; covered by the response re-parse only"
        )


def _is_challenger_call(record: dict | None) -> bool:
    """Whether this wire-log record is the challenge generator's own call.

    The containment exemption below keys off the generator's request, and may
    not take the record's word for which call that is: a repointed ``call_id``
    would otherwise excuse a different role's prompt from the scan.
    """
    return record is not None and record.get("role") == "challenger"


def _note_unreferenced_generations(
    notes: list[str], *, successful: list[dict], referenced: set[str], repairs: int
) -> None:
    """Say how many paid generations the record does not account for.

    A run that generated three challenges and published the one it liked best
    would leave the other two here, and nothing else would mention them. That is
    the sharpest attack on the contestability arm, so it must at least be
    visible.

    A note rather than a failure, because there are legitimate causes: each
    format repair discards the malformed reply that preceded it, and a blank
    response is retried. The count is stated so a reader can judge, rather than
    guessed at.
    """
    unaccounted = [c for c in successful if c["call_id"] not in referenced]
    if len(unaccounted) <= repairs:
        return
    roles = sorted({str(c.get("role")) for c in unaccounted})
    notes.append(
        f"{len(unaccounted)} successful call(s) are not referenced by the record "
        f"({', '.join(roles)}), and {repairs} format repair(s) are recorded; the "
        f"remainder are generations the record does not account for"
    )


def verify(run_dir: Path, notes: list[str] | None = None) -> list[str]:
    """Audit a recorded run of either kind.

    ``notes`` collects non-fatal observations about audit coverage.
    """
    manifest = _read_json(run_dir / "run.json")
    if manifest.get("kind") == "recourse":
        return verify_recourse(run_dir, notes)
    return verify_debate(run_dir, notes)


# transcript.md is deliberately absent: records written before it existed are
# still auditable, and its absence is reported as a note below rather than as a
# missing artifact.
DEBATE_ARTIFACTS = (
    "run.json", "config.json", "task.json", "seating.json", "calls.jsonl",
    "transcript.json", "verdict.json",
)


def verify_debate(run_dir: Path, notes: list[str] | None = None) -> list[str]:
    """Return a list of failures; empty means the record checks out."""
    failures: list[str] = []
    notes = notes if notes is not None else []

    def check(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    # Deleting an artifact is the cheapest tampering there is, and it must
    # report rather than raise — including when this run is the ``parent/`` of a
    # recourse, where a missing verdict.json is precisely what a tamperer would
    # remove to break the decision the recourse quotes.
    absent = [name for name in DEBATE_ARTIFACTS if not (run_dir / name).is_file()]
    if absent:
        failures.append(f"the run record is missing {absent}")
        return failures

    (
        manifest, task, config, seating, context, document, transcript, calls, verdict
    ) = load_run(run_dir)
    # A published field, so it is pinned to the enumeration even though nothing
    # below looks a profile up any more.
    check(
        manifest.get("profile") in PROFILES,
        f"run.json names an unknown profile {manifest.get('profile')!r}",
    )

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
    check(
        len(successful) >= 2 * config.n_rounds + 1,
        f"expected at least {2 * config.n_rounds + 1} successful calls, "
        f"found {len(successful)}",
    )

    # --- every turn must be the response that produced it -------------------- #
    _check_turn_responses(
        check, failures, turns=transcript.all_turns(), by_call_id=by_call_id
    )

    # --- the verdict must be the judge's recorded decision ------------------- #
    judge_record = by_call_id.get(verdict["call_id"])
    if judge_record is None:
        failures.append("verdict call_id is not in calls.jsonl")
    else:
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
    _check_thinking_containment(
        check, notes, secrets=_secrets_from(transcript.all_turns()), calls=calls
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
    if set(document) == {"turns"}:
        # The genuine old shape, exactly. Any *other* partial key set is an
        # edited document, not an old one — and letting it take this branch
        # would disable the field-set pin below, which is the check that catches
        # a "gold_index" smuggled into a turn.
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
        # ``.get`` rather than indexing: a document missing one of these keys is
        # an edited one, and it must report that rather than raise.
        for key in ("question", "answers", "positions"):
            check(
                document.get(key) == expected_document[key],
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
            document.get("turns") == expected_document["turns"],
            "transcript.json's turns do not carry exactly the fields the "
            "protocol defines",
        )

    # --- the published document ----------------------------------------------- #
    document_path = run_dir / "transcript.md"
    if not document_path.is_file():
        # Said out loud rather than skipped: a record whose readable document is
        # not audited should say so, or a reader has no way to tell the two
        # cases apart.
        notes.append(
            "this record predates transcript.md; its readable document is not "
            "audited"
        )
    else:
        published = document_path.read_text(encoding="utf-8")
        check(
            PRIVATE_THINKING_NOTE in published,
            "transcript.md does not carry the note explaining that the Thinking "
            "sections were private during the debate",
        )
        _check_document_states(
            check,
            published,
            must_state={
                "the question": task.question,
                # Not the answer text: both answers appear in the document's own
                # Answers and Positions sections, so a needle of "the winning
                # answer" is satisfied by any document at all. What has to be
                # there is the sentence that says which one won.
                "which answer the judge chose": (
                    f"That is `answers[{verdict['answer_index']}]`"
                    if verdict.get("answer_index") in (0, 1)
                    else ""
                ),
                "the judge's response": verdict.get("raw", ""),
                **{
                    f"round {t.round} {t.speaker}'s argument": t.argument
                    for t in transcript.all_turns()
                },
                **{
                    f"round {t.round} {t.speaker}'s Thinking": t.thinking
                    for t in transcript.all_turns()
                },
            },
        )
        rendered = _rederive(
            failures,
            "transcript.md",
            lambda: render_decision_record(
                task,
                seating,
                transcript,
                Verdict(**{k: v for k, v in verdict.items() if k in _VERDICT_FIELDS}),
                judge_cot=config.judge_cot,
            ),
        )
        if rendered is not None and published != rendered:
            notes.append(
                "transcript.md differs from the document re-rendered from the "
                "record; the statements it must not get wrong are checked above, "
                "but its presentation has drifted from this version of the renderer"
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
    _note_unreferenced_generations(
        notes,
        successful=successful,
        referenced={t.call_id for t in transcript.all_turns()} | {verdict["call_id"]},
        repairs=sum(t.repair_attempts for t in transcript.all_turns())
        + int(verdict.get("repair_attempts") or 0),
    )
    return failures


def _load_turns(document: dict) -> Transcript:
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
    return transcript


def verify_recourse(run_dir: Path, notes: list[str] | None = None) -> list[str]:
    """Audit a recorded recourse, and the run it contests, together.

    The record is self-contained by construction: the challenged run was copied
    into ``parent/`` before the first call, so this walks into it and audits it
    as a run in its own right, then checks everything the contest added on top.
    """
    failures: list[str] = []
    notes = notes if notes is not None else []

    def check(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    manifest = _read_json(run_dir / "run.json")

    # --- the parent must be present, and must itself check out --------------- #
    parent_dir = run_dir / "parent"
    if not (parent_dir / "run.json").is_file():
        failures.append(
            "parent/ is missing or is not a run directory; the recourse quotes a "
            "decision that this record cannot show"
        )
        return failures

    parent_notes: list[str] = []
    failures += [f"parent: {f}" for f in verify(parent_dir, parent_notes)]
    notes += [f"parent: {n}" for n in parent_notes]

    parent_manifest = _read_json(parent_dir / "run.json")
    check(
        parent_manifest.get("status") == "completed",
        f"the challenged run has status {parent_manifest.get('status')!r}; only a "
        f"completed decision can be contested",
    )
    check(
        parent_manifest.get("run_id") == manifest.get("parent_run_id"),
        "parent/run.json is not the run this record names as its parent",
    )
    recorded_tree_hash = manifest.get("parent_sha256")
    if recorded_tree_hash is None:
        notes.append("no parent_sha256 was recorded; the copy is unpinned")
    else:
        check(
            recorded_tree_hash == tree_sha256(parent_dir),
            "parent/ does not match the parent_sha256 recorded when it was "
            "copied, so it has been modified since",
        )

    # --- the recourse's own inputs ------------------------------------------- #
    # Checked up front for the same reason the debate audit checks its join keys
    # first: everything below reads these, and a missing file is a finding about
    # the record, not a reason to abort with a traceback. Deleting ruling.json
    # is the cheapest way to make an outcome unreadable, so it must report.
    missing = [
        name
        for name in (
            "task.json", "config.json", "seating.json", "challenge.md",
            "challenge.json", "calls.jsonl", "transcript.json", "ruling.json",
        )
        if not (run_dir / name).is_file()
    ]
    if missing:
        failures.append(f"the recourse record is missing {missing}")
        return failures

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
    check(
        manifest.get("profile") in PROFILES,
        f"run.json names an unknown profile {manifest.get('profile')!r}",
    )

    # The identity of the question is inherited, not re-drawn. A recourse that
    # quietly reseated the debaters or reworded the question would be contesting
    # a different decision from the one it copied in.
    for name in ("task.json", "seating.json"):
        check(
            _read_json(run_dir / name) == _read_json(parent_dir / name),
            f"{name} differs from the parent's; a recourse inherits the question "
            f"and the seating unchanged",
        )
    parent_constitution = parent_dir / "constitution.md"
    check(
        parent_constitution.is_file() == constitution_path.is_file()
        and (
            not constitution_path.is_file()
            or parent_constitution.read_text(encoding="utf-8")
            == constitution_path.read_text(encoding="utf-8")
        ),
        "the constitution differs from the parent's",
    )
    check(
        manifest.get("profile") == parent_manifest.get("profile"),
        "the profile differs from the parent's; a recourse is judged under the "
        "standard the decision was made under",
    )

    parent_config = DebateConfig(**_read_json(parent_dir / "config.json"))
    check(
        config.n_rounds == parent_config.n_rounds,
        f"n_rounds is {config.n_rounds} against the parent's "
        f"{parent_config.n_rounds}; the boundary between the debate and the "
        f"contest of it would be ambiguous",
    )
    differing = sorted(
        key
        for key, value in config.to_dict().items()
        if key not in RECOURSE_ONLY_KEYS
        and value != parent_config.to_dict().get(key)
    )
    if differing:
        notes.append(
            f"the recourse ran under different settings from the decision it "
            f"contests: {differing}"
        )

    # --- the challenge -------------------------------------------------------- #
    challenge_text = (run_dir / "challenge.md").read_text(encoding="utf-8").strip()
    challenge_data = _read_json(run_dir / "challenge.json")
    challenge = Challenge.from_dict(challenge_data)
    # Both loaders drop unknown keys, so without this an invented field a reader
    # would believe survives unremarked in either file. Same argument as the
    # transcript document's key-set pin below.
    check(
        set(challenge_data) == _CHALLENGE_FIELDS,
        f"challenge.json's keys are not the ones a challenge defines: "
        f"{sorted(set(challenge_data) ^ _CHALLENGE_FIELDS)}",
    )
    check(
        challenge.text == challenge_text,
        "challenge.json's text is not the text in challenge.md",
    )
    check(
        manifest.get("challenge_sha256") == challenge.sha256(),
        "run.json's challenge_sha256 does not hash the recorded challenge",
    )
    check(
        challenge.origin in ("file", "generated"),
        f"unknown challenge origin {challenge.origin!r}",
    )
    # The manifest restates the challenge's provenance, and the summary this
    # script prints under an OK banner is written from it. Unchecked, an edited
    # run.json would have the audit itself report a specious challenge as a
    # grounded one — which is the arm the whole contestability claim turns on.
    for key, recorded in (
        ("challenge_origin", challenge.origin),
        ("challenge_source", challenge.source),
        ("challenge_arm", challenge.arm),
        ("challenge_visibility", challenge.visibility),
    ):
        check(
            manifest.get(key) == recorded,
            f"run.json's {key} disagrees with challenge.json",
        )
    check(
        manifest.get("parent_rounds") == parent_config.n_rounds,
        "run.json's parent_rounds is not the parent's n_rounds",
    )
    check(
        manifest.get("parent_chain")
        == [*parent_manifest.get("parent_chain", []), parent_manifest.get("run_id")],
        "run.json's parent_chain is not the chain parent/run.json implies",
    )

    # --- the record's own turns ----------------------------------------------- #
    document = _read_json(run_dir / "transcript.json")
    own = _load_turns(document)
    parent_transcript = _load_turns(_read_json(parent_dir / "transcript.json"))
    composed = _rederive(
        failures,
        "the composed transcript",
        lambda: compose_transcript(parent_transcript, own),
    )
    if composed is None:
        return failures

    calls = [
        json.loads(line)
        for line in (run_dir / "calls.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    malformed = [c for c in calls if not {"call_id", "role", "attempt"} <= set(c)]
    check(not malformed, f"{len(malformed)} calls.jsonl record(s) lack join keys")
    calls = [c for c in calls if "call_id" in c]
    by_call_id = {c["call_id"]: c for c in calls}
    successful = [
        c
        for c in calls
        if c.get("status") == 200 and not (c.get("response_body") or {}).get("error")
    ]
    generated = challenge.origin == "generated"
    expected_calls = 2 * config.recourse_rounds + 1 + (1 if generated else 0)
    check(
        len(successful) >= expected_calls,
        f"expected at least {expected_calls} successful calls, "
        f"found {len(successful)}",
    )

    # --- the protocol is named, not inferred ---------------------------------- #
    check(
        manifest.get("recourse_protocol") == config.recourse_protocol,
        f"run.json names the {manifest.get('recourse_protocol')!r} protocol but "
        f"recourse_rounds = {config.recourse_rounds} is the "
        f"{config.recourse_protocol!r} protocol",
    )

    parent_verdict = _read_json(parent_dir / "verdict.json")

    # --- a generated challenge must be the generator's recorded output -------- #
    challenger_calls = [c for c in calls if c.get("role") == "challenger"]
    if not generated:
        check(
            not challenger_calls,
            "this challenge is recorded as supplied, but the run made "
            f"{len(challenger_calls)} challenge-generation call(s)",
        )
    else:
        check(
            challenge.arm in ARMS,
            f"unknown challenge arm {challenge.arm!r}; expected one of {ARMS}",
        )
        check(
            challenge.visibility in VISIBILITIES,
            f"unknown challenge visibility {challenge.visibility!r}; expected one "
            f"of {VISIBILITIES}",
        )
        record = by_call_id.get(challenge.call_id)
        if record is None:
            failures.append("the challenge's call_id is not in calls.jsonl")
        else:
            check(
                (record.get("request_body") or {}).get("model") == challenge.model,
                "challenge.json names a model the recorded request did not use",
            )
            content = _response_content(record)
            if content is None:
                failures.append("challenger: no response content recorded")
            else:
                try:
                    thinking, text, parse_mode = parse_debater_output(content)
                except MalformedOutputError as error:
                    failures.append(
                        f"challenger: recorded response no longer parses ({error})"
                    )
                else:
                    check(
                        text == challenge.text,
                        "the recorded challenge is not what the generator's "
                        "recorded response parses to",
                    )
                    check(
                        thinking == challenge.thinking,
                        "the generator's recorded thinking is not what its "
                        "recorded response parses to",
                    )
                    check(
                        parse_mode == challenge.parse_mode,
                        "the challenge's parse_mode does not match a re-parse",
                    )
                    check(
                        challenge.raw.strip() == content.strip(),
                        "the generator's recorded raw text differs from its "
                        "recorded response",
                    )

    # --- every recourse turn must be the response that produced it ------------ #
    _check_turn_responses(
        check, failures, turns=own.all_turns(), by_call_id=by_call_id
    )

    # --- the ruling ----------------------------------------------------------- #
    ruling = _read_json(run_dir / "ruling.json")
    check(
        set(ruling) == _RULING_FIELDS,
        f"ruling.json's keys are not the ones a ruling defines: "
        f"{sorted(set(ruling) ^ _RULING_FIELDS)}",
    )
    ruling_record = by_call_id.get(ruling.get("call_id"))
    if ruling_record is None:
        failures.append("the ruling's call_id is not in calls.jsonl")
    else:
        check(
            bool(ruling.get("repair_attempts"))
            == str(ruling.get("parse_mode") or "").endswith("_after_repair"),
            "ruling repair_attempts disagrees with its parse_mode suffix",
        )
        content = _response_content(ruling_record)
        check(
            content is not None
            and content.strip() == str(ruling.get("raw") or "").strip(),
            "the ruling's raw text differs from the recourse judge's recorded "
            "response",
        )
        if content is not None:
            try:
                word, reasoning, parse_mode = parse_ruling_output(content)
            except MalformedOutputError as error:
                failures.append(
                    f"recourse judge: recorded response no longer parses ({error})"
                )
            else:
                check(
                    word == ruling.get("ruling"),
                    f"the recorded ruling {ruling.get('ruling')!r} is not what "
                    f"the recourse judge's recorded response parses to ({word!r})",
                )
                check(
                    parse_mode
                    == str(ruling.get("parse_mode") or "").removesuffix(
                        "_after_repair"
                    ),
                    "the ruling's parse_mode does not match a re-parse",
                )
                check(
                    ruling.get("reasoning") == reasoning,
                    "the recorded ruling reasoning is not what the recourse "
                    "judge's recorded response parses to",
                )

    # --- the decisive check: which answer the ruling leaves standing ---------- #
    # A self-consistently inverted ruling (both the word and the index flipped)
    # is caught above by the response re-parse; this catches an index that does
    # not follow from the word.
    if ruling.get("ruling") in ("UPHOLD", "OVERTURN"):
        check(
            ruling.get("answer_index")
            == resolve_ruling(ruling["ruling"], parent_verdict["answer_index"]),
            f"the recorded answer_index {ruling.get('answer_index')} does not "
            f"follow from a {ruling['ruling']} of a decision for "
            f"{parent_verdict['answer_index']}",
        )
        check(
            ruling.get("upheld") == (ruling["ruling"] == "UPHOLD"),
            "the ruling's upheld flag disagrees with the ruling itself",
        )
    else:
        failures.append(
            f"the recorded ruling {ruling.get('ruling')!r} is neither UPHOLD nor "
            f"OVERTURN"
        )
    check(
        ruling.get("parent_answer_index") == parent_verdict["answer_index"]
        and ruling.get("parent_choice") == parent_verdict["choice"],
        "the ruling restates a different original decision from the one in "
        "parent/verdict.json",
    )
    # _rederive, because choice_for_answer raises on an answer_index the seating
    # does not contain — and a doctored index is exactly when the audit has
    # something to say and must not be crashing.
    expected_choice = _rederive(
        failures,
        "the ruling's choice",
        lambda: seating.choice_for_answer(ruling.get("answer_index")),
    )
    if expected_choice is not None:
        check(
            ruling.get("choice") == expected_choice,
            f"ruling choice {ruling.get('choice')} does not resolve to answer "
            f"{ruling.get('answer_index')} under the recorded seating",
        )
    check(
        ruling.get("protocol") == config.recourse_protocol,
        "the ruling names a different protocol from the one the config selects",
    )
    if task.gold_index is not None:
        check(
            ruling.get("correct") == (ruling.get("answer_index") == task.gold_index),
            "the recorded correctness disagrees with gold_index",
        )

    # --- the constitution reached everyone ------------------------------------ #
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

    # --- private reasoning, and the one configuration that may carry it ------- #
    # The scan covers the *composed* turns: the parent's private reasoning must
    # not reach a recourse prompt either, and the generator's own must not reach
    # anything at all.
    secrets = _secrets_from(composed.all_turns())
    if challenge.thinking:
        secrets.append(
            _Secret(
                label="the challenge generator",
                text=challenge.thinking,
                call_id=challenge.call_id or "",
            )
        )
    full_visibility = challenge.shown_private_reasoning
    # The exemption is granted to a request that is a challenger call, not
    # merely to whatever call_id challenge.json happens to name: a repointed
    # call_id would otherwise exempt the recourse judge's request from the scan.
    exempt = frozenset()
    if full_visibility and _is_challenger_call(by_call_id.get(challenge.call_id)):
        exempt = frozenset({challenge.call_id})
    _check_thinking_containment(
        check,
        notes,
        secrets=secrets,
        calls=calls,
        exempt_call_ids=exempt,
        # Otherwise a challenge that quotes private reasoning would be reported
        # as a leak into every prompt that then quoted the challenge, instead of
        # once, where it happened. Both forms: prompts carry the neutralised
        # text, the public artifact the defanged one.
        strip_from_sent=_forms(challenge.text) if full_visibility else (),
    )
    if full_visibility:
        notes.append(
            "DISCLOSURE: the challenge generator was shown the debaters' "
            "private reasoning (challenge_visibility = full), so its own "
            "request is exempt from the containment scan."
        )
        # Every form, not the raw string: the generator reads the reasoning
        # through ``render_private_reasoning``, so a verbatim quote arrives
        # *indented*. Matching raw here would silence the one disclosure that
        # says this run is not whitebox, in exactly the case it exists for —
        # while the containment scan above stays deliberately quiet, because
        # the challenge text was stripped out of every request before scanning.
        quoted = [
            t
            for t in composed.all_turns()
            if len(t.thinking.strip()) >= MIN_DISTINCTIVE_THINKING
            and any(form in challenge.text for form in _forms(t.thinking))
        ]
        for turn in quoted:
            notes.append(
                f"DISCLOSURE: the challenge quotes round {turn.round} "
                f"{turn.speaker}'s private Thinking. With challenge_visibility "
                f"= full this is permitted by configuration, and it means the "
                f"recourse judge ruled on material the judge who decided the "
                f"question never had. The two decisions are not comparable."
            )

    # --- the derived artifacts must not say anything the record does not ------ #
    expected_document = _rederive(
        failures,
        "transcript.json's header",
        lambda: recourse_transcript_document(
            task, seating, own,
            parent_run_id=manifest["parent_run_id"],
            parent_rounds=parent_config.n_rounds,
        ),
    )
    if expected_document is not None:
        check(
            set(document) == RECOURSE_TRANSCRIPT_DOC_KEYS,
            f"transcript.json's top-level keys are not the ones a recourse "
            f"defines: {sorted(set(document) ^ RECOURSE_TRANSCRIPT_DOC_KEYS)}",
        )
        for key in ("question", "answers", "positions", "parent_run_id", "parent_rounds"):
            check(
                document.get(key) == expected_document[key],
                f"transcript.json's {key} disagrees with the record",
            )
        check(
            document.get("turns") == expected_document["turns"],
            "transcript.json's turns do not carry exactly the fields the "
            "protocol defines",
        )

    ruling_object = _rederive(
        failures,
        "the recorded ruling",
        lambda: Ruling(**{k: v for k, v in ruling.items() if k in _RULING_FIELDS}),
    )
    document_path = run_dir / "transcript.md"
    published = (
        document_path.read_text(encoding="utf-8") if document_path.is_file() else None
    )
    if published is None:
        notes.append(
            "this record predates transcript.md; its readable document is not "
            "audited"
        )
    else:
        check(
            PRIVATE_THINKING_NOTE in published,
            "transcript.md does not carry the note explaining that the Thinking "
            "sections were private during the debate",
        )
        _check_document_states(
            check,
            published,
            must_state={
                "the question": task.question,
                # The sentence, not the answer text — see the debate branch.
                "which answer stands after the ruling": (
                    f"The answer that now stands is `answers[{ruling['answer_index']}]`"
                    if ruling.get("answer_index") in (0, 1)
                    else ""
                ),
                "the challenge": challenge_text,
                "the original decision's grounds": parent_verdict.get("raw", ""),
                "the recourse judge's response": ruling.get("raw", ""),
                **{
                    f"round {t.round} {t.speaker}'s argument": t.argument
                    for t in composed.all_turns()
                },
                **{
                    f"round {t.round} {t.speaker}'s Thinking": t.thinking
                    for t in composed.all_turns()
                },
            },
        )
    if ruling_object is not None and published is not None:
        rendered = _rederive(
            failures,
            "transcript.md",
            lambda: render_recourse_record(
                task, seating, composed,
                parent_rounds=parent_config.n_rounds,
                parent_verdict=Verdict(
                    **{k: v for k, v in parent_verdict.items() if k in _VERDICT_FIELDS}
                ),
                challenge=challenge,
                ruling=ruling_object,
                judge_cot=config.judge_cot,
                parent_judge_cot=parent_config.judge_cot,
            ),
        )
        if rendered is not None and published != rendered:
            notes.append(
                "transcript.md differs from the document re-rendered from the "
                "record; the statements it must not get wrong are checked above, "
                "but its presentation has drifted from this version of the renderer"
            )

    # --- structural sanity ---------------------------------------------------- #
    check(
        len(own.turns) == 2 * config.recourse_rounds,
        f"expected {2 * config.recourse_rounds} recourse turns, found "
        f"{len(own.turns)}",
    )
    first, last = parent_config.n_rounds + 1, parent_config.n_rounds + config.recourse_rounds
    stray = [t for t in own.all_turns() if not first <= t.round <= last]
    check(
        not stray,
        f"{len(stray)} recourse turn(s) fall outside rounds {first}–{last}",
    )
    for round_number in range(first, last + 1):
        speakers = sorted(str(t.speaker) for t in own.all_turns() if t.round == round_number)
        check(
            speakers == [str(s) for s in ORDER],
            f"recourse round {round_number} has speakers {speakers}, expected one "
            f"turn each from {[str(s) for s in ORDER]}",
        )
    truncated = [
        t
        for t in own.all_turns()
        if t.finish_reason is not None and t.finish_reason not in NORMAL_FINISH_REASONS
    ]
    check(
        not truncated,
        f"{len(truncated)} recourse turn(s) stopped on a non-normal finish_reason",
    )
    _note_unreferenced_generations(
        notes,
        successful=successful,
        referenced={t.call_id for t in own.all_turns()}
        | {ruling.get("call_id"), challenge.call_id},
        repairs=sum(t.repair_attempts for t in own.all_turns())
        + int(ruling.get("repair_attempts") or 0)
        + challenge.repair_attempts,
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
    # Disclosures are separated out because they are not observations about
    # audit coverage: they say that this run departed from a guarantee the
    # project claims, by configuration, and a reader must not have to spot that
    # among the housekeeping.
    disclosures = [n for n in notes if "DISCLOSURE" in n]
    for note in (n for n in notes if "DISCLOSURE" not in n):
        print(f"  note: {note}")
    if disclosures:
        print("\nDISCLOSURES — this run departed from the ordinary protocol:")
        for disclosure in disclosures:
            print(f"  - {disclosure.split('DISCLOSURE: ', 1)[-1]}")
        print()
    if failures:
        print(f"FAIL {args.run_dir} — {len(failures)} problem(s):")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print(f"OK {args.run_dir}")
    print("  every argument and decision in the record is what the recorded")
    print("  response actually says, and the published grounds are the judge's own")
    print("  no debater's private Thinking reached the opponent or the judge")
    print("  during the debate")
    print("  the decision resolves through the recorded seating, and the")
    print("  transcript's question, answers and positions match task.json and")
    print("  seating.json")
    print()
    print("  This says the record is not misreporting itself. Whether the process")
    print("  is transparent is a question about the published document, which is")
    print("  for a reader to judge.")
    if manifest.get("kind") == "recourse":
        _print_recourse_summary(args.run_dir, manifest)
    return 0


def _print_recourse_summary(run_dir: Path, manifest: dict) -> None:
    """What this recourse did, in the terms a reader of the claim cares about."""
    ruling = _read_json(run_dir / "ruling.json")
    parent_verdict = _read_json(run_dir / "parent" / "verdict.json")
    origin = manifest.get("challenge_origin")
    described = (
        f"generated, {manifest.get('challenge_arm')} arm, shown the "
        f"{manifest.get('challenge_visibility')} record"
        if origin == "generated"
        else f"supplied from {manifest.get('challenge_source')}"
    )
    print()
    print(f"  recourse: {manifest.get('recourse_protocol')} protocol")
    # Reported from the record, not verified — nothing checks the arm against
    # the run, so this line must not read as a finding.
    print(f"  challenge, as recorded: {described}")
    print(
        f"  ruling: {ruling['ruling']} — the decision for "
        f"answers[{parent_verdict['answer_index']}] "
        + (
            f"was overturned in favour of answers[{ruling['answer_index']}]"
            if ruling["answer_index"] != parent_verdict["answer_index"]
            else "stands"
        )
    )
    print(f"  the challenged run verifies too: {' -> '.join(manifest['parent_chain'])}")
    print("  the ruling re-parses, and the answer that stands follows from it")


if __name__ == "__main__":
    raise SystemExit(main())

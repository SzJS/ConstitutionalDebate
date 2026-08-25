"""What a run actually spent, read back off the wire log.

Separate from ``persistence`` because that module is about *writing* the record
and this one only ever reads it. Nothing here can change a decision; it is
measurement after the fact, and it is re-runnable over a finished directory
without spending anything.

The arm comparison in this project turns on holding compute roughly constant
across arms, so "roughly constant" has to be a number rather than a hope. This
is where that number comes from.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable

# Roles whose calls are measurement, not decision. They are excluded from the
# decision-path totals and reported separately, so that grading a run can never
# silently inflate the condition it is grading.
#
# "comprehension" is here for the same reason and is easy to get wrong: the Likert
# probe runs inside the challenger's conversation, on the challenger's model, so its
# tokens look like challenger tokens. But it asks the challenger about the record
# rather than contributing to the contest, and the token balance it would otherwise
# inflate is the "debate only wins because it generates more text" check.
#
# "agreement" is the line-vs-prose probe (LLM_NOTES §3n): a grader-model read of what an
# objection's prose argues, made after the contest is finished and over its recorded
# text. It cannot change any decision and must not be able to; costing it against the
# condition it measures would make the instrument part of what it is measuring.
OFF_PATH_ROLES: frozenset[str] = frozenset(
    {"grader", "comprehension", "agreement"}
)


@dataclass(frozen=True)
class Usage:
    """Tokens and money, summed over calls.

    ``calls`` counts logical generations and ``attempts`` counts HTTP requests;
    they differ by retries and format repairs. Both are kept because the second
    is what was paid for and the first is what the protocol asked for — a run
    with 7 calls and 12 attempts is telling you something.
    """

    calls: int = 0
    attempts: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    cached_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            **{
                f: getattr(self, f) + getattr(other, f)
                for f in (
                    "calls", "attempts", "prompt_tokens", "completion_tokens",
                    "reasoning_tokens", "cached_tokens", "total_tokens", "cost_usd",
                )
            }
        )

    def to_dict(self) -> dict[str, Any]:
        data = {f: getattr(self, f) for f in self.__dataclass_fields__}
        data["cost_usd"] = round(self.cost_usd, 6)
        return data


def usage_from_record(record: dict[str, Any]) -> Usage:
    """One wire-log line as a ``Usage``.

    Read defensively at every level. A failed attempt carries no usage at all
    and still counts as an attempt — that is what was spent on it — and the
    nested detail dicts are absent from some providers and from ``FakeClient``.
    A ``KeyError`` here would crash an analysis pass over a directory that is
    otherwise perfectly readable.
    """
    usage = record.get("usage") or {}
    completion_details = usage.get("completion_tokens_details") or {}
    prompt_details = usage.get("prompt_tokens_details") or {}
    return Usage(
        calls=0 if record.get("purpose") == "repair" else 1,
        attempts=1,
        prompt_tokens=usage.get("prompt_tokens") or 0,
        completion_tokens=usage.get("completion_tokens") or 0,
        reasoning_tokens=completion_details.get("reasoning_tokens") or 0,
        cached_tokens=prompt_details.get("cached_tokens") or 0,
        total_tokens=usage.get("total_tokens") or 0,
        # OpenRouter reports the real charge per call when the request asks for
        # it, which ``client._build_body`` always does. Preferring it to a local
        # price table means the figure survives a provider or price change, and
        # that the same model served by five providers is costed correctly.
        cost_usd=float(usage.get("cost") or 0.0),
    )


def read_calls(path: Path) -> Iterable[dict[str, Any]]:
    """Every line of a wire log, skipping any that is not JSON.

    A truncated final line is possible if a process died mid-append, and losing
    a whole directory's accounting to it would be a poor trade.
    """
    if not Path(path).is_file():
        return []
    records = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def split_calls(path: Path) -> tuple[Usage, Usage]:
    """One run's decision-path and off-path usage, unrounded.

    The unrounded pair is what callers summing across runs must use.
    ``Usage.to_dict`` rounds for readability, so aggregating rounded dicts would
    apply the rounding once per run and compound it.
    """
    decision_path = Usage()
    off_path = Usage()
    for record in read_calls(path):
        usage = usage_from_record(record)
        if (record.get("role") or "unknown") in OFF_PATH_ROLES:
            off_path = off_path + usage
        else:
            decision_path = decision_path + usage
    return decision_path, off_path


def aggregate_calls(path: Path) -> dict[str, Any]:
    """Sum one run's wire log, split by what the calls were for."""
    decision_path = Usage()
    off_path = Usage()
    by_role: dict[str, Usage] = {}
    by_purpose: dict[str, Usage] = {}
    providers: dict[str, int] = {}
    repairs = 0
    failures = 0

    for record in read_calls(path):
        usage = usage_from_record(record)
        role = record.get("role") or "unknown"
        purpose = record.get("purpose") or "unknown"
        by_role[role] = by_role.get(role, Usage()) + usage
        by_purpose[purpose] = by_purpose.get(purpose, Usage()) + usage
        if role in OFF_PATH_ROLES:
            off_path = off_path + usage
        else:
            decision_path = decision_path + usage
        if purpose == "repair":
            repairs += 1
        if record.get("status") != 200:
            failures += 1
        # The same model id is served by different providers call to call, and
        # that is a confound worth surfacing rather than leaving in the log.
        provider = record.get("provider")
        if provider:
            providers[provider] = providers.get(provider, 0) + 1

    return {
        "decision_path": decision_path.to_dict(),
        "off_path": off_path.to_dict(),
        "by_role": {k: v.to_dict() for k, v in sorted(by_role.items())},
        "by_purpose": {k: v.to_dict() for k, v in sorted(by_purpose.items())},
        "providers": dict(sorted(providers.items())),
        "repairs": repairs,
        "failed_attempts": failures,
    }


def aggregate_tree(root: Path) -> dict[str, Any]:
    """Sum every wire log under a directory. Used across an experiment.

    Sums the unrounded per-run pairs rather than re-reading ``aggregate_calls``
    output: those dicts are rounded for display, and summing them would apply
    the rounding once per run.
    """
    total = Usage()
    off = Usage()
    runs = 0
    for path in sorted(Path(root).rglob("calls.jsonl")):
        # A contest copies its parent run into ``parent/``, wire log included.
        # Counting those again would inflate reported spend by roughly
        # (1 + challengers x arms) on any partly-contested experiment.
        if "parent" in path.parts:
            continue
        decision_path, off_path = split_calls(path)
        total = total + decision_path
        off = off + off_path
        runs += 1
    return {
        "runs": runs,
        "decision_path": total.to_dict(),
        "off_path": off.to_dict(),
        "cost_usd": round(total.cost_usd + off.cost_usd, 6),
    }

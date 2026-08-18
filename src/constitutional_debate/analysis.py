"""The funnel, with honest uncertainty.

Reads ``index.jsonl`` — one flat row per completed cell — and computes rates per
``(arm x challenger x condition)``, split by error mechanism and compute
condition.

Two statistical choices are load-bearing, and both exist because the default
would be wrong *in this specific regime* rather than wrong in general:

**Wilson intervals, not the normal approximation.** Every cell here is a
proportion over 20-50 cases, and several will sit at or near 0 and 1 — a weak
challenger detecting nothing is an expected outcome, not a bug. The textbook
interval escapes [0, 1] at small n, and at ``0/n`` it collapses to *zero width*,
asserting certainty from a handful of trials.

**Cluster bootstrap resampled by task, not by cell.** The same task appears in
every arm and across repeats, so its cells are not independent draws. Resampling
cells would treat correlated observations as independent and understate the
interval — which for a paired comparison is the error that most easily
manufactures a result.

This module imports pandas and statsmodels; nothing on the decision path does.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
from statsmodels.stats.proportion import proportion_confint

# Rates that condition on the decision having been wrong. Everything above the
# line in the funnel is measured on all decisions; everything below is measured
# only where there was something to detect.
ERROR_CONDITIONED = frozenset(
    {"detection", "found_the_flaw", "valid_objection", "underspecified", "correction"}
)


@dataclass(frozen=True)
class Rate:
    """A proportion with an interval, and the counts it came from."""

    name: str
    numerator: int
    denominator: int

    @property
    def value(self) -> float | None:
        return self.numerator / self.denominator if self.denominator else None

    @property
    def interval(self) -> tuple[float, float] | None:
        if not self.denominator:
            return None
        lo, hi = proportion_confint(
            self.numerator, self.denominator, alpha=0.05, method="wilson"
        )
        return float(lo), float(hi)

    def to_dict(self) -> dict[str, Any]:
        interval = self.interval
        return {
            "name": self.name,
            "n": self.denominator,
            "k": self.numerator,
            "rate": self.value,
            "ci_low": interval[0] if interval else None,
            "ci_high": interval[1] if interval else None,
        }


def read_index(path: Path) -> pd.DataFrame:
    """Load ``index.jsonl``. An absent or empty file gives an empty frame."""
    path = Path(path)
    if not path.is_file():
        return pd.DataFrame()
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return pd.DataFrame(rows)


def _rate(frame: pd.DataFrame, name: str, numerator: pd.Series | None) -> Rate:
    if frame.empty or numerator is None:
        return Rate(name, 0, 0)
    return Rate(name, int(numerator.fillna(False).sum()), int(len(frame)))


def funnel(frame: pd.DataFrame) -> dict[str, Any]:
    """The rates, for one already-filtered slice of rows.

    Denominators differ by rate and that is the whole point of computing them
    here rather than dividing by ``len(frame)`` everywhere: detection is over
    *initially incorrect* decisions, the false-alarm rate is over *initially
    correct* ones, and correction is over *valid objections*. Sharing a
    denominator would quietly answer a different question.
    """
    if frame.empty:
        return {"n": 0, "rates": {}}

    incorrect = frame[frame.get("initially_correct") == False]  # noqa: E712
    correct = frame[frame.get("initially_correct") == True]  # noqa: E712
    raised = incorrect[incorrect.get("challenge_raised") == True]  # noqa: E712
    annotated = incorrect[incorrect.get("gradable", True) == True]  # noqa: E712

    rates = [
        _rate(incorrect, "detection", incorrect.get("challenge_raised")),
        _rate(correct, "false_alarm", correct.get("challenge_raised")),
        _rate(annotated, "found_the_flaw", annotated.get("found_the_flaw")),
        _rate(annotated, "valid_objection", annotated.get("grade_valid")),
        _rate(raised, "underspecified", raised.get("underspecified")),
        _rate(incorrect, "headline_revised_given_incorrect", incorrect.get("changed")),
        _rate(correct, "headline_revised_given_correct", correct.get("changed")),
    ]
    valid = annotated[annotated.get("grade_valid") == True]  # noqa: E712
    rates.append(_rate(valid, "correction", valid.get("final_correct")))

    return {
        "n": int(len(frame)),
        "n_incorrect": int(len(incorrect)),
        "n_correct": int(len(correct)),
        "rates": {r.name: r.to_dict() for r in rates},
    }


def by_cell(frame: pd.DataFrame, keys: Iterable[str] = ("decision_arm",)) -> dict:
    """The funnel per group, plus the same split by error mechanism.

    Reporting split by ``mechanism`` is not bookkeeping. The two error routes
    are biased in opposite directions — natural errors select the debates where
    debate surfaced the flaw *worst*, forced errors include debates where it was
    well exposed and so are artificially easy to contest — so a combined number
    hides which way the estimate leans.
    """
    keys = [k for k in keys if k in frame.columns]
    if frame.empty or not keys:
        return {"overall": funnel(frame)}

    out: dict[str, Any] = {"overall": funnel(frame)}
    for values, group in frame.groupby(keys, dropna=False):
        label = "|".join(str(v) for v in (values if isinstance(values, tuple) else (values,)))
        entry = funnel(group)
        if "mechanism" in group.columns:
            entry["by_mechanism"] = {
                str(mech): funnel(sub)
                for mech, sub in group.groupby("mechanism", dropna=False)
            }
        out[label] = entry
    return out


def bootstrap_difference(
    frame: pd.DataFrame,
    *,
    column: str,
    arm_a: str,
    arm_b: str,
    task_column: str = "task_id",
    arm_column: str = "decision_arm",
    draws: int = 2000,
    seed: int = 0,
) -> dict[str, Any]:
    """The difference between two arms, resampled **by task**.

    Tasks are the independent unit: the same task is decided in every arm, so
    its rows move together. Resampling rows instead would treat those correlated
    observations as independent draws and produce an interval narrower than the
    data supports — the error that most easily turns noise into a finding.
    """
    needed = {column, task_column, arm_column}
    if frame.empty or not needed <= set(frame.columns):
        return {"difference": None, "ci_low": None, "ci_high": None, "draws": 0}

    rng = np.random.default_rng(seed)
    tasks = frame[task_column].dropna().unique()
    if len(tasks) == 0:
        return {"difference": None, "ci_low": None, "ci_high": None, "draws": 0}

    def diff(sample: pd.DataFrame) -> float | None:
        a = sample[sample[arm_column] == arm_a][column].dropna()
        b = sample[sample[arm_column] == arm_b][column].dropna()
        if a.empty or b.empty:
            return None
        return float(a.mean() - b.mean())

    observed = diff(frame)
    by_task = {task: group for task, group in frame.groupby(task_column)}
    samples: list[float] = []
    for _ in range(draws):
        drawn = rng.choice(tasks, size=len(tasks), replace=True)
        resampled = pd.concat([by_task[t] for t in drawn], ignore_index=True)
        value = diff(resampled)
        if value is not None:
            samples.append(value)

    if not samples:
        return {"difference": observed, "ci_low": None, "ci_high": None, "draws": 0}
    lo, hi = np.percentile(samples, [2.5, 97.5])
    return {
        "difference": observed,
        "ci_low": float(lo),
        "ci_high": float(hi),
        "draws": len(samples),
        "clustered_by": task_column,
    }


def token_balance(frame: pd.DataFrame, *, tolerance: float = 0.25) -> dict[str, Any]:
    """Whether the arms give a challenger comparable amounts of record to read.

    Matching is the confound the design tries to control, so it is checked
    rather than assumed. Flagged, not enforced: an arm outside the band is a
    fact to report beside the funnel, not a reason to discard it.

    Measured on ``decision_record_words`` — the published record — and **not**
    on ``decision_completion_tokens``, which counts what came back over the
    wire. The two came apart with outcome control: a constructed ``single`` cell
    makes zero calls, so its wire figure is 0 by construction and balancing on
    it would report the arms as unmatched for a reason that has nothing to do
    with how much text there is to attack. What a challenger reads is the
    quantity ``next_steps.md`` warns about — "debate may simply win because it
    generates more text" — and it is the same quantity whether the words were
    generated or inserted.

    Generation cost has not stopped being reportable: it is ``decision_cost_usd``
    per row and ``aggregate_tree`` over the run. It is simply not this check.

    An index built before ``decision_record_words`` existed lacks the column and
    reports ``{"checked": False}`` rather than a number meaning something else.
    """
    column = "decision_record_words"
    if frame.empty or column not in frame.columns or "decision_arm" not in frame.columns:
        return {"checked": False}
    means = frame.groupby("decision_arm")[column].mean()
    if means.empty:
        return {"checked": False}
    reference = float(means.mean())
    return {
        "checked": True,
        "tolerance": tolerance,
        "mean_by_arm": {str(k): float(v) for k, v in means.items()},
        "outside_band": {
            str(arm): float(value)
            for arm, value in means.items()
            if reference and abs(value - reference) / reference > tolerance
        },
    }


def analyse(index_path: Path, *, keys: Iterable[str] = ("decision_arm",)) -> dict[str, Any]:
    """Everything, for ``--stage analyse`` to write as ``metrics.json``."""
    frame = read_index(index_path)
    return {
        "rows": int(len(frame)),
        "funnel": by_cell(frame, keys=keys),
        "token_balance": token_balance(frame),
    }

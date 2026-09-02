"""The pre-run provider check for the FINDINGS campaign `fd1`: four real calls.

    cd exp2
    uv run python records/derivations/fd1-provider-check.py [--dry-run]

`records/derivations/jd6-provider-check.py` with one difference of KIND. jd6's check
read a finished spec and asked one question — does the pin the spec already names route
where it says? fd1 has only one spec at this point (the weak arm's), because the strong
arm's model id is **not yet known**: `LLM_NOTES.md` §1 records `openai/gpt-5.6-luna-20260709`
as the id OpenRouter serves, while every spec in this repository so far has sent the bare
`openai/gpt-5.6-luna` and been served by OpenAI without complaint. The plan (D5 step 2)
settles that by asking, and PREREG records the answer. So the models here are HARD-CODED
rather than read from a spec — there is no strong-arm spec to read yet, and writing one
before this call would be writing down a guess. The weak arm's Maverick pin IS settled
(`["digitalocean"]`, the routing argument of §3aa carried into this campaign) and is
checked here the way jd6 checked it.

**The four calls** (trivial prompt, temperature 0, `max_tokens` 16, reasoning off — the
settings every fd1 role runs at, so the call under test is the call the run will make):

    1. meta-llama/llama-4-maverick   pin ["digitalocean"], allow_fallbacks false
       — must be served by DigitalOcean. This is the F-weak arm's judge and recourse judge.
    2. openai/gpt-5.6-luna-20260709  no pin — does the dated id exist, and who serves it?
    3. openai/gpt-5.6-luna           no pin — same question of the bare id.
    4. the luna id chosen from 2/3, PINNED to the provider that served it, no fallbacks
       — because a served provider is not a pin: `provider.order` takes OpenRouter
       *slugs* and the response's `provider` field carries a *display name*, so the slug
       is read out of the endpoint list and then TESTED. A pinned run whose slug is
       misspelt does not fail fast — `client.NO_ENDPOINTS_MARKERS` retries that 404 —
       it burns `max_attempts` on every cell and dies slowly. No dry-run catches it.

A 404 "no endpoints found" on call 2 or 3 is a legitimate RECORDED OUTCOME, not a crash:
it is precisely the finding that that id is not the one to send. The client is built with
`max_attempts = 1` for that reason — the run wants the retry, this check wants the answer.

**Which id, if both work.** The DATED id is preferred: an id with a date in it cannot
silently move under a long campaign, and the bare alias can. The resolved `model` field of
both responses is printed so the reader can see whether they are in fact the same weights.

**`reasoning_tokens == 0` is asserted for luna**, not merely reported. The spend table and
the 16,384-token cap in D3 both assume reasoning is off, and a reasoning model that ignores
`{"enabled": false}` would blow through both while looking healthy.

    VERDICT: PASS  exit 0   every call landed where it was told to and luna reasoned not
    VERDICT: WAIT  exit 4   the configuration is right but a pinned provider is absent
                            right now (the slug IS in the endpoint list and the call
                            still 404'd) — a reason to start later, not to change a spec
    VERDICT: FAIL  exit 1   anything else: a pin that routes elsewhere, an empty body,
                            neither luna id reachable, or reasoning tokens billed

The request bodies are built by `client.OpenRouterClient` itself — the same object the run
uses — rather than by hand here, so a change to `_build_body` cannot leave this script
testing a call nobody makes. A check that cannot fail is not a check.

The log is written to `outputs/fd1-provider-check.log` BY THIS SCRIPT (as well as being
printed), so the record exists whether or not the caller remembered to `tee`. `--dry-run`
prints the four planned calls and exits without sending anything, and writes no log — it
must not overwrite the log of a real check.
"""
from __future__ import annotations

import asyncio
import datetime
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

from exp2.client import OpenRouterClient, OpenRouterError
from exp2.config import ClientConfig

REPO = Path(__file__).resolve().parents[2]          # exp2/
LOG = REPO / "outputs" / "fd1-provider-check.log"

# --- what is being checked -------------------------------------------------------------
MAVERICK = "meta-llama/llama-4-maverick"
MAVERICK_PIN = ["digitalocean"]
# The display name DigitalOcean's slug carries in the response's `provider` field is read
# off the endpoint list rather than hard-coded (jd6-provider-check's rule: a renamed
# provider must not pass unnoticed), with this as the fallback if the list cannot be read.
MAVERICK_EXPECTED_NAME = "DigitalOcean"
LUNA_CANDIDATES = ["openai/gpt-5.6-luna-20260709", "openai/gpt-5.6-luna"]

PROMPT = "Reply with the single word: alive"
TEMPERATURE = 0.0
MAX_TOKENS = 16
REASONING_EFFORT = "off"


class Tee:
    """stdout and the log file, so the record does not depend on the caller's `tee`."""

    def __init__(self, stream: Any, path: Path) -> None:
        self._stream = stream
        path.parent.mkdir(parents=True, exist_ok=True)
        self._file = path.open("w", encoding="utf-8")

    def write(self, text: str) -> int:
        self._file.write(text)
        return self._stream.write(text)

    def flush(self) -> None:
        self._file.flush()
        self._stream.flush()

    def close(self) -> None:
        self._file.close()


def endpoint_slugs(model: str, headers: dict[str, str]) -> dict[str, str]:
    """`{display name -> provider slug}` for one model, read off OpenRouter.

    The endpoint list is the ONLY place this mapping exists: `provider.order` takes
    slugs and `calls.jsonl` records display names, so the two cannot be reconciled
    after a run. The slash in the path is UNESCAPED; %2F returns 404 (LLM_NOTES §3n).
    """
    url = f"https://openrouter.ai/api/v1/models/{model}/endpoints"
    try:
        response = httpx.get(url, headers=headers, timeout=60.0)
    except httpx.HTTPError as error:
        print(f"GET {url} -> {type(error).__name__}: {error}")
        return {}
    print(f"GET {url} -> {response.status_code}")
    if response.status_code != 200:
        return {}
    endpoints = (response.json().get("data") or {}).get("endpoints") or []
    mapping: dict[str, str] = {}
    print(f"  {len(endpoints)} endpoints: ", end="")
    pairs = []
    for endpoint in endpoints:
        tag = endpoint.get("tag") or endpoint.get("provider_slug") or ""
        name = (endpoint.get("name") or "").split("|")[0].strip()
        pricing = endpoint.get("pricing") or {}
        price = f"${pricing.get('prompt', '?')}/{pricing.get('completion', '?')}"
        if tag and name:
            # ONE display name can carry SEVERAL slugs — OpenAI lists `openai`,
            # `openai/flex` and `openai/fast` (priority processing, at twice the
            # price) all under the name "OpenAI". The pin must be the BASE slug: the
            # one with no `/tier` suffix, which is the tier an unpinned call lands on.
            # The first run of this check took the last one listed, `openai/fast`,
            # and the pinned call cost exactly 2x the unpinned one — caught on
            # 2026-09-02 by reading the two costs side by side.
            current = mapping.get(name)
            if current is None or ("/" in current and "/" not in tag):
                mapping[name] = tag
            pairs.append(f"{name} -> {tag} ({price})")
    print("; ".join(pairs) if pairs else "(none)")
    return mapping


async def one_call(
    client: OpenRouterClient,
    records: list[dict[str, Any]],
    *,
    label: str,
    model: str,
    pin: list[str] | None,
) -> dict[str, Any]:
    """One real call, reported the same way whether it succeeds or fails."""
    provider = {"order": list(pin), "allow_fallbacks": False} if pin else None
    print(f"\n--- {label} ---")
    print(f"model:   {model}")
    print(f"pin:     {pin if pin else '(none — free routing)'}")
    result: dict[str, Any] = {
        "label": label, "model": model, "pin": list(pin) if pin else [],
        "ok": False, "served": None, "finish_reason": None, "content": None,
        "reasoning_tokens": None, "cost": None, "resolved_model": None, "error": None,
    }
    before = len(records)
    try:
        completion = await client.complete(
            model=model,
            messages=[{"role": "user", "content": PROMPT}],
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
            reasoning_effort=REASONING_EFFORT,
            meta={"role": "provider_check", "label": label},
            provider=provider,
        )
    except OpenRouterError as error:
        # A 404 "no endpoints found" arrives here (client.py retries that wording, and
        # this client is built with max_attempts=1 so it arrives after one attempt).
        # It is an ANSWER — that id or that slug is not reachable — and is recorded.
        result["error"] = f"{type(error).__name__}: {error}"
        attempt = records[before] if len(records) > before else {}
        result["http_status"] = attempt.get("status")
        body = attempt.get("response_body")
        print(f"HTTP {attempt.get('status')}")
        print(f"SERVED BY: (nothing — {result['error'][:200]})")
        if isinstance(body, dict):
            print("body: " + json.dumps(body)[:600])
        return result
    usage = completion.usage or {}
    details = usage.get("completion_tokens_details") or {}
    result.update(
        ok=True,
        served=completion.provider,
        finish_reason=completion.finish_reason,
        content=completion.content,
        reasoning_tokens=details.get("reasoning_tokens", 0) or 0,
        cost=usage.get("cost"),
        resolved_model=completion.model,
        http_status=200,
    )
    print(f"HTTP 200")
    print(f"SERVED BY: {completion.provider}")
    print(f"resolved model:   {completion.model}")
    print(f"finish_reason:    {completion.finish_reason}")
    print(f"content:          {completion.content!r}")
    print(f"reasoning_tokens: {result['reasoning_tokens']}   "
          f"(reasoning text: {'present' if completion.reasoning else 'none'})")
    print(f"cost:             {usage.get('cost')}")
    print(f"usage:            {json.dumps(usage)[:400]}")
    return result


def print_plan() -> None:
    print("PLANNED CALLS (nothing is sent under --dry-run)")
    print(f"  prompt={PROMPT!r}  temperature={TEMPERATURE}  max_tokens={MAX_TOKENS}  "
          f"reasoning_effort={REASONING_EFFORT!r}  max_attempts=1")
    rows = [
        ("1. maverick-pinned", MAVERICK, str(MAVERICK_PIN) + ", allow_fallbacks=false",
         "must be served by DigitalOcean — the F-weak judge and recourse judge"),
        ("2. luna-dated", LUNA_CANDIDATES[0], "(none)",
         "does the dated id exist; a 404 no-endpoints is a recorded outcome"),
        ("3. luna-bare", LUNA_CANDIDATES[1], "(none)",
         "does the bare alias exist; same"),
        ("4. luna-pinned", "<whichever of 2/3 succeeded; dated preferred>",
         "[<slug that served it>], allow_fallbacks=false",
         "a served provider is not a pin — the slug is read off /endpoints and tested"),
    ]
    print(f"\n{'call':22s}{'model':46s}{'pin':58s}why")
    print("-" * 172)
    for name, model, pin, why in rows:
        print(f"{name:22s}{model:46s}{pin:58s}{why}")
    print("-" * 172)
    print("asserted: call 1 served by DigitalOcean; every luna call reasoning_tokens == 0;")
    print("          call 4 served by the pinned provider and no other.")
    print("exit: 0 PASS, 4 WAIT (right config, provider absent right now), 1 FAIL")


async def run() -> int:
    load_dotenv()  # the repo-root .env, found by walking up from exp2/
    key = os.environ["OPENROUTER_KEY"]
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    config = ClientConfig(
        base_url="https://openrouter.ai/api/v1",
        max_concurrency=1,
        # ONE attempt, deliberately: the run wants a 404 "no endpoints" retried, this
        # check wants it reported. Retrying here would hide the very thing being asked.
        max_attempts=1,
        backoff_base_s=1.0,
        backoff_cap_s=8.0,
        connect_timeout_s=30.0,
        read_timeout_s=120.0,
        run_timeout_s=600.0,
    )
    records: list[dict[str, Any]] = []

    async def sink(record: dict[str, Any]) -> None:
        records.append(record)

    print(f"=== fd1 provider check "
          f"{datetime.datetime.now(datetime.timezone.utc).isoformat()} ===")
    print(f"prompt={PROMPT!r} temperature={TEMPERATURE} max_tokens={MAX_TOKENS} "
          f"reasoning_effort={REASONING_EFFORT!r} max_attempts={config.max_attempts}\n")

    results: list[dict[str, Any]] = []
    failures: list[str] = []
    waits: list[str] = []

    print("=== endpoint list: Maverick ===")
    maverick_names = endpoint_slugs(MAVERICK, headers)
    maverick_expected = next(
        (name for name, tag in maverick_names.items() if tag == MAVERICK_PIN[0]),
        None,
    )
    if maverick_expected is None:
        print(f"  ! {MAVERICK_PIN[0]!r} is NOT in the endpoint list for {MAVERICK}; "
              f"falling back to the display name {MAVERICK_EXPECTED_NAME!r}")
        maverick_expected = MAVERICK_EXPECTED_NAME
        maverick_slug_present = False
    else:
        maverick_slug_present = True
        print(f"  {MAVERICK_PIN[0]!r} serves under the display name "
              f"{maverick_expected!r} — that is what the response must carry")

    async with OpenRouterClient(key, config, sink=sink) as client:
        # --- 1. the weak arm's judge, pinned ------------------------------------------
        first = await one_call(client, records, label="1. maverick-pinned",
                               model=MAVERICK, pin=MAVERICK_PIN)
        results.append(first)
        if not first["ok"]:
            if maverick_slug_present:
                waits.append(f"the Maverick pin {MAVERICK_PIN} is a slug that IS in the "
                             f"endpoint list, and the call still failed: "
                             f"{first['error']}")
            else:
                failures.append(f"the Maverick call failed and {MAVERICK_PIN[0]!r} is "
                                f"not in the endpoint list: {first['error']}")
        elif not (first["content"] or "").strip():
            failures.append("the pinned Maverick call routed but returned no text")
        elif first["served"] != maverick_expected:
            failures.append(f"Maverick was served by {first['served']!r}, not "
                            f"{maverick_expected!r} ({MAVERICK_PIN[0]}) — "
                            f"allow_fallbacks is false, so the pin is not doing what "
                            f"the spec says it does")

        # --- 2 and 3. which luna id is real -------------------------------------------
        for index, model in enumerate(LUNA_CANDIDATES, start=2):
            results.append(await one_call(
                client, records,
                label=f"{index}. luna-{'dated' if index == 2 else 'bare'}",
                model=model, pin=None))

        luna_ok = [r for r in results[1:] if r["ok"]]
        for result in luna_ok:
            if result["reasoning_tokens"]:
                failures.append(
                    f"{result['model']} billed {result['reasoning_tokens']} reasoning "
                    f"tokens with reasoning explicitly disabled; the campaign's token "
                    f"cap and spend table both assume none")
        # The DATED id first if it worked: an id carrying a date cannot be repointed at
        # new weights mid-campaign, and the bare alias can. Both resolved model ids are
        # in the log above, so a reader can see whether they are the same thing today.
        chosen = luna_ok[0] if luna_ok else None
        luna_id: str | None = None
        luna_slug: str | None = None
        if chosen is None:
            failures.append(
                f"neither luna id answered ({', '.join(LUNA_CANDIDATES)}); the F-strong "
                f"arm has no model and its spec cannot be written")
        else:
            luna_id = chosen["model"]
            print(f"\n=== endpoint list: {luna_id} (to turn the served display name "
                  f"{chosen['served']!r} into a pin slug) ===")
            luna_names = endpoint_slugs(luna_id, headers)
            luna_slug = luna_names.get(chosen["served"] or "")
            if luna_slug is None:
                # Nothing is guessed silently. `provider.order` takes slugs and the
                # response carries a display name; if the endpoint list did not give the
                # mapping, the lowercased display name is a GUESS and is marked as one —
                # and call 4 is precisely the test of it.
                luna_slug = (chosen["served"] or "").lower().replace(" ", "-")
                print(f"  ! the endpoint list gave no slug for {chosen['served']!r}; "
                      f"trying the lowercased display name {luna_slug!r}, which is a "
                      f"GUESS and must be confirmed against "
                      f"https://openrouter.ai/api/v1/models/{luna_id}/endpoints")
                luna_slug_present = False
            else:
                print(f"  {chosen['served']!r} is pinned to its BASE slug {luna_slug!r} "
                      "(tiers such as /fast and /flex are not the default route)")
                luna_slug_present = True

            # --- 4. the same id, now PINNED to that provider --------------------------
            fourth = await one_call(client, records, label="4. luna-pinned",
                                    model=luna_id, pin=[luna_slug])
            results.append(fourth)
            if not fourth["ok"]:
                if luna_slug_present:
                    waits.append(f"{luna_slug!r} IS in {luna_id}'s endpoint list and the "
                                 f"pinned call still failed: {fourth['error']}")
                else:
                    failures.append(f"the pinned luna call failed and {luna_slug!r} was "
                                    f"a guessed slug: {fourth['error']}")
            else:
                if not (fourth["content"] or "").strip():
                    failures.append("the pinned luna call routed but returned no text")
                if fourth["served"] != chosen["served"]:
                    failures.append(
                        f"pinned to {luna_slug!r} the call was served by "
                        f"{fourth['served']!r}, not {chosen['served']!r}; with "
                        f"allow_fallbacks false that is not a pin")
                if fourth["reasoning_tokens"]:
                    failures.append(
                        f"the pinned luna call billed {fourth['reasoning_tokens']} "
                        f"reasoning tokens with reasoning disabled")

    # --- the table, the settled ids, and the verdict -------------------------------------
    print("\n=== summary ===")
    print(f"{'call':22s}{'model':32s}{'pin':22s}{'served':16s}"
          f"{'finish':10s}{'rsn_tok':>8s}{'cost':>11s}  content")
    print("-" * 145)
    for r in results:
        pin = ",".join(r["pin"]) or "-"
        served = str(r["served"]) if r["ok"] else f"FAILED({r.get('http_status')})"
        cost = f"{r['cost']:.6f}" if isinstance(r["cost"], (int, float)) else "-"
        content = repr(r["content"]) if r["ok"] else (r["error"] or "")[:60]
        print(f"{r['label']:22s}{r['model'][:31]:32s}{pin[:21]:22s}{served[:15]:16s}"
              f"{str(r['finish_reason'])[:9]:10s}{str(r['reasoning_tokens']):>8s}"
              f"{cost:>11s}  {content[:40]}")
    print("-" * 145)
    total = sum(r["cost"] for r in results
                if isinstance(r.get("cost"), (int, float)))
    print(f"total cost: ${total:.6f}")

    print(f"\nMAVERICK ID TO USE: {MAVERICK}  PIN: {MAVERICK_PIN}")
    if luna_id and luna_slug:
        print(f"LUNA ID TO USE: {luna_id}  PIN: [{luna_slug}]")
    else:
        print("LUNA ID TO USE: (none — no luna id answered)  PIN: (none)")
    print("These two lines are what `experiments/fd1-*-{weak,strong}.toml` must carry, "
          "and what PREREG §8 records with this log.")

    if failures:
        for reason in failures:
            print(f"  ! {reason}")
        print(f"\nVERDICT: FAIL — {failures[0]}")
        return 1
    if waits:
        for reason in waits:
            print(f"  ~ {reason}")
        print(f"\nVERDICT: WAIT — {waits[0]}")
        return 4
    print("\nVERDICT: PASS — Maverick served by the pinned DigitalOcean, a luna id "
          "reachable and pinned to the provider that serves it, and no reasoning tokens "
          "billed anywhere with reasoning disabled")
    return 0


def main(argv: list[str]) -> int:
    if "--dry-run" in argv:
        # No log file is written here: a dry run must not overwrite the record of a real
        # check, and it has nothing to record.
        print_plan()
        return 0
    tee = Tee(sys.stdout, LOG)
    original, sys.stdout = sys.stdout, tee
    try:
        return asyncio.run(run())
    finally:
        sys.stdout = original
        tee.close()
        print(f"log written to {LOG}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

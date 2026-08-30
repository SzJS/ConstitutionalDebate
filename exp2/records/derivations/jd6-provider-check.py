"""The pre-run provider check for `judgment-debate-6`: one real pinned call on the JUDGE.

    cd exp2
    uv run python records/derivations/jd6-provider-check.py [spec.toml] \
        2>&1 | tee outputs/jd6-provider-check.log

`records/derivations/sweep-1-provider-check.py` with ONE difference: it reads the
`[debate] recourse_judge_model` pin instead of the debaters'. The spec defaults to
`experiments/jd6-round.toml`, and the model and the pin are **read out of it** —
hard-coding them here would let the script pass while the spec pointed somewhere else,
which is the one thing it exists to rule out. The debaters' own pin
(`deepseek/deepseek-v4-flash-0731` -> GMICloud) is unchanged from the sweep and is
checked by the sibling script; this one is about the judge, which has been UNPINNED in
every run of this campaign until now.

WHY THE JUDGE IS PINNED AT ALL, and it is not cosmetic. `LLM_NOTES.md` §3aa found 34% of
`judgment-debate-3`'s M1 rulings served by DeepInfra against 4.8% of `judgment-debate-5`'s
arm B, on the same objections and the same model id. jd6 measures a change to the ROUND,
and with the judge routed freely "only the round moved" would be an intent rather than a
fact. DigitalOcean served 680-758 of the ~900 Maverick calls in every jd5 arm, so its slug
is the one to pin; `outputs/jd6-maverick-endpoints.json` is the endpoint list this was read
off.

**Three verdicts, three exit codes.** `order` is a *preference* list, so a call served by
`PIN[1]` is a pass as far as OpenRouter is concerned and is not one here: with one entry
in the pin there is no fallback to accept, and a call served by anything else means the
pin is not doing what the spec says it does.

    VERDICT: PASS  exit 0   non-empty content, served by the FIRST pinned provider
    VERDICT: WAIT  exit 4   served by another provider in the pin — the primary is down
    VERDICT: FAIL  exit 1/2/3/5  non-200, empty content, served from outside the pin,
                            a body that no longer matches the run's, or a spec that does
                            not pin the judge at all

**Why this cannot be skipped.** `provider.order` takes OpenRouter provider *slugs*;
`calls.jsonl` records provider *display names*, so the two cannot be checked against each
other after a run. And with `allow_fallbacks: false` the response to a momentarily absent
pinned provider and the response to a misspelt or withdrawn slug are the *same* HTTP 404,
`"No endpoints found for <model>."` — `client.NO_ENDPOINTS_MARKERS` matches that wording
and **retries** it, which is what a long pinned run needs and which means a wrong slug does
not fail fast: it burns `max_attempts` on every call and kills every cell slowly. No
dry-run can catch that. This call can, and nothing else does.

The request body is built by `client.OpenRouterClient._build_body`, the same function the
run uses, so the call under test is the call the run will make — in particular with
**reasoning disabled**, which is what every role in this phase runs at. A check that
cannot fail is not a check.
"""
from __future__ import annotations

import datetime
import json
import os
import sys
import tomllib
from pathlib import Path

import httpx
from dotenv import load_dotenv

from exp2.client import OpenRouterClient

# The repo-root .env, found by walking up from the working directory (exp2/).
load_dotenv()
KEY = os.environ["OPENROUTER_KEY"]
H = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}

# --- 0. what the spec says to check ---------------------------------------------------
# Read rather than hard-coded, so this checks the slugs the run will actually send.
SPEC = Path(sys.argv[1] if len(sys.argv) > 1 else "experiments/jd6-round.toml")
spec = tomllib.loads(SPEC.read_text(encoding="utf-8"))
debate = spec.get("debate", {})
# THE JUDGE, not the debaters. `recourse_judge_model` and `judge_model` are the same
# value in both jd6 specs by design (the model that judged the debate rules on the appeal
# against its own judgment — the jd3 design, kept and stated), and the check refuses if a
# spec ever sets them apart, because then there are two pins and this script would silently
# be testing one of them.
MODEL = debate.get("recourse_judge_model") or debate.get("judge_model")
if (debate.get("recourse_judge_model") and debate.get("judge_model")
        and debate["recourse_judge_model"] != debate["judge_model"]):
    print(f"VERDICT: FAIL — {SPEC} names two judges "
          f"({debate['judge_model']!r} and {debate['recourse_judge_model']!r}); this "
          f"script checks ONE pin and would leave the other unverified")
    sys.exit(5)
PIN = list((debate.get("provider_order") or {}).get(MODEL) or [])

print(f"=== {datetime.datetime.now(datetime.timezone.utc).isoformat()} ===")
print(f"spec:    {SPEC}")
print(f"model:   {MODEL}   [debate.recourse_judge_model]")
print(f"pin:     {PIN}   [debate.provider_order]")
if not MODEL or not PIN:
    print(f"\nVERDICT: FAIL — {SPEC} does not pin {MODEL!r} under "
          f"[debate.provider_order]; there is nothing to check and the judge would route "
          f"freely, which is the confound this campaign exists not to have")
    sys.exit(5)
PRIMARY_SLUG = PIN[0]
print(f"primary: {PRIMARY_SLUG}   — a call served by anything else is not a pass\n")

# --- 1. the endpoint list: are the pinned slugs there, and are they healthy? ----------
# The slash is UNESCAPED in this path; %2F returns 404 (LLM_NOTES 3n).
url = f"https://openrouter.ai/api/v1/models/{MODEL}/endpoints"
r = httpx.get(url, headers=H, timeout=60.0)
print(f"GET {url} -> {r.status_code}")
eps = r.json().get("data", {}).get("endpoints", []) if r.status_code == 200 else []
print(f"{len(eps)} endpoints\n")
print(f"{'tag/slug':34s}{'ctx':>10s}{'max_out':>9s}{'status':>8s}   name")
print("-" * 110)
# The endpoint list is also the only place the slug -> display-name mapping exists, and
# the display name is what the response's `provider` field carries. Deriving it here
# beats hard-coding "GMICloud", which is how a renamed provider would pass unnoticed.
display_names: dict[str, str] = {}
for e in eps:
    tag = e.get("tag") or e.get("provider_slug") or ""
    if tag in PIN:
        name = e.get("name") or ""
        display_names[tag] = name.split("|")[0].strip()
        print(f"{tag:34s}{e.get('context_length', 0):>10}"
              f"{str(e.get('max_completion_tokens')):>9s}{str(e.get('status')):>8s}"
              f"   {name}")
found = [e.get("tag") for e in eps if e.get("tag") in PIN]
print(f"\npinned slugs present in the endpoint list: {found}")
print(f"display names the response's `provider` field should carry: "
      f"{sorted(display_names.values())}")
if sorted(found) != sorted(PIN):
    print("!! a pinned slug is MISSING from the endpoint list")

# --- 2. one real pinned call, built exactly as the run builds it ----------------------
# `_build_body` does not touch `self`; calling it unbound keeps this script one call
# rather than a whole client, while still testing the real body.
body = OpenRouterClient._build_body(
    None,
    model=MODEL,
    messages=[{"role": "user", "content": "Reply with exactly: OK"}],
    temperature=0.0,
    max_tokens=16,
    reasoning_effort="off",           # what every role in this phase runs at
    provider={"order": PIN, "allow_fallbacks": False},
)
if body.get("reasoning") != {"enabled": False}:
    print(f"!! _build_body no longer disables reasoning at effort 'off': "
          f"{body.get('reasoning')!r}")
    print("VERDICT: FAIL — this script is testing a call the run does not make")
    sys.exit(3)

print("\n=== one real pinned call ===")
print("request body (minus messages): " + json.dumps(
    {k: v for k, v in body.items() if k != "messages"}))
r = httpx.post("https://openrouter.ai/api/v1/chat/completions",
               headers=H, json=body, timeout=120.0)
print(f"HTTP {r.status_code}")
d = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
print(json.dumps({k: d.get(k) for k in ("id", "provider", "model", "usage")}, indent=2))
if r.status_code != 200:
    print(json.dumps(d, indent=2)[:2000] if d else r.text[:2000])
    print(f"\nSERVED BY: (nothing — HTTP {r.status_code})")
    print(f"VERDICT: FAIL — the pinned call returned HTTP {r.status_code}, not 200")
    sys.exit(1)

choices = d.get("choices") or [{}]
content = (choices[0].get("message") or {}).get("content")
served = d.get("provider")
print(f"content: {content!r}")
print(f"\nSERVED BY: {served}")

# --- 3. the verdict, on three independent conditions -----------------------------------
# Content, because a pin that routes but returns nothing is useless to the run; the
# served provider, because a pin that returns text from OUTSIDE the pin is not a pin;
# and *which* pinned provider, because `order` is a preference list and the second entry
# is a fallback nobody chose to measure on.
reasons = []
if not (content or "").strip():
    reasons.append(
        f"content was empty ({content!r}) — the call routed but produced no text; "
        f"completion_tokens_details="
        f"{(d.get('usage') or {}).get('completion_tokens_details')}")
allowed = set(display_names.values())
if not display_names:
    # Nothing is assumed here any more. Without the endpoints read there is no way to
    # say which display name the primary slug carries, and a check that guesses the
    # thing it is checking is not a check.
    reasons.append(f"the endpoints read returned none of the pinned slugs, so neither "
                   f"the pin's display names nor the primary's could be read")
elif served not in allowed:
    reasons.append(f"served by {served!r}, which is not one of the pinned "
                   f"providers {sorted(allowed)}")

if reasons:
    for reason in reasons:
        print(f"  ! {reason}")
    print("VERDICT: FAIL — " + reasons[0])
    sys.exit(2)

primary = display_names.get(PRIMARY_SLUG)
if served != primary:
    # Inside the pin, but not the provider the spec's whole routing argument is about.
    # Not a failure of configuration — a reason to wait rather than to start.
    print(f"VERDICT: WAIT — served by {served}, not the primary {primary} "
          f"({PRIMARY_SLUG}). The pin routes, but the arm started now would be "
          f"measured on the fallback.")
    sys.exit(4)
print(f"VERDICT: PASS — non-empty content, served by {served}, the primary pinned "
      f"provider ({PRIMARY_SLUG})")
sys.exit(0)

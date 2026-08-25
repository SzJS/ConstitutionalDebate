"""The pre-run provider check: one real pinned call, plus a health read of the pins.

    cd exp2
    uv run python records/derivations/sweep-1-provider-check.py \
        2>&1 | tee outputs/sweep-provider-check.log

One paid call, ~$0.00001. `records/logs/sweep-provider-check.log` is a passing run.

**Why this cannot be skipped.** `provider.order` takes OpenRouter provider *slugs*;
`calls.jsonl` records provider *display names*, so the two cannot be checked against each
other after a run. And with `allow_fallbacks: false` the response to a momentarily absent
pinned provider and the response to a misspelt or withdrawn slug are the *same* HTTP 404,
`"No endpoints found for <model>."` — `client.NO_ENDPOINTS_MARKERS` matches that wording
and **retries** it, which is what a 13-hour pinned run needs and which means a wrong slug
does not fail fast: it burns `max_attempts` on every call and kills every cell slowly. No
dry-run can catch that. This call can, and nothing else does.

The request body is built by `client.OpenRouterClient._build_body`, the same function the
run uses, so the call under test is the call the run will make — in particular with
**reasoning disabled**. It matters: an earlier version of this script sent no `reasoning`
key, the provider defaulted it on, and the reply came back with `content: None` and 16
reasoning tokens while the script still printed "pin is live". A check that cannot fail is
not a check.
"""
from __future__ import annotations

import datetime
import json
import os
import sys

import httpx
from dotenv import load_dotenv

from exp2.client import OpenRouterClient

# The repo-root .env, found by walking up from the working directory (exp2/).
load_dotenv()
KEY = os.environ["OPENROUTER_KEY"]
MODEL = "deepseek/deepseek-v4-flash-0731"
PIN = ["gmicloud/fp8", "coreweave/fp8"]
H = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}

print(f"=== {datetime.datetime.now(datetime.timezone.utc).isoformat()} ===")
print(f"model: {MODEL}\npin:   {PIN}\n")

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
    reasoning_effort="off",           # what every role in the sweep runs at
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

# --- 3. the verdict, on two independent conditions ------------------------------------
# Content, because a pin that routes but returns nothing is useless to the run; and the
# served provider, because a pin that returns text from OUTSIDE the pin is not a pin.
reasons = []
if not (content or "").strip():
    reasons.append(
        f"content was empty ({content!r}) — the call routed but produced no text; "
        f"completion_tokens_details="
        f"{(d.get('usage') or {}).get('completion_tokens_details')}")
allowed = set(display_names.values()) or {"GMICloud", "CoreWeave"}
if served not in allowed:
    reasons.append(f"served by {served!r}, which is not one of the pinned "
                   f"providers {sorted(allowed)}")
if not display_names:
    reasons.append("the endpoints read returned no pinned slug, so the display names "
                   "above were assumed rather than read")

if reasons:
    for reason in reasons:
        print(f"  ! {reason}")
    print("VERDICT: FAIL — " + reasons[0])
    sys.exit(2)
print(f"VERDICT: PASS — non-empty content, served by {served}, which is in the pin")
sys.exit(0)

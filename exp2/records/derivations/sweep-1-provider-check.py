"""One pinned smoke call before sweep-1, plus a health read of the two pinned endpoints.

The slugs were verified for pilot 3 (outputs/pilot-3-provider-check.log). Nothing about
them changed; this re-confirms they are still live and still serve the pin, because an
unrecognised or withdrawn slug with allow_fallbacks:false returns HTTP 404 "No endpoints
found ..." — which contains "no endpoints", so client.NO_ENDPOINTS_MARKER classifies it
as RETRYABLE and every cell would die slowly rather than fast. No dry-run can catch it.
"""
import datetime, json, os, sys
import httpx
from dotenv import load_dotenv

load_dotenv()
KEY = os.environ["OPENROUTER_KEY"]
MODEL = "deepseek/deepseek-v4-flash-0731"
PIN = ["gmicloud/fp8", "coreweave/fp8"]
H = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}

print(f"=== {datetime.datetime.now(datetime.timezone.utc).isoformat()} ===")
print(f"model: {MODEL}\npin:   {PIN}\n")

# The slash is UNESCAPED in this path; %2F returns 404 (LLM_NOTES 3n).
url = f"https://openrouter.ai/api/v1/models/{MODEL}/endpoints"
r = httpx.get(url, headers=H, timeout=60.0)
print(f"GET {url} -> {r.status_code}")
eps = r.json().get("data", {}).get("endpoints", []) if r.status_code == 200 else []
print(f"{len(eps)} endpoints\n")
print(f"{'tag/slug':34s}{'ctx':>10s}{'max_out':>9s}{'status':>8s}   name")
print("-" * 110)
for e in eps:
    tag = e.get("tag") or e.get("provider_slug") or ""
    if tag in PIN:
        print(f"{tag:34s}{e.get('context_length', 0):>10}"
              f"{str(e.get('max_completion_tokens')):>9s}{str(e.get('status')):>8s}"
              f"   {e.get('name')}")
found = [e.get("tag") for e in eps if e.get("tag") in PIN]
print(f"\npinned slugs present in the endpoint list: {found}")
if sorted(found) != sorted(PIN):
    print("!! a pinned slug is MISSING from the endpoint list")

print("\n=== one real pinned call ===")
body = {
    "model": MODEL,
    "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
    "max_tokens": 16,
    "temperature": 0.0,
    "provider": {"order": PIN, "allow_fallbacks": False},
}
print("request provider block: " + json.dumps(body["provider"]))
r = httpx.post("https://openrouter.ai/api/v1/chat/completions",
               headers=H, json=body, timeout=120.0)
print(f"HTTP {r.status_code}")
d = r.json()
print(json.dumps({k: d.get(k) for k in ("id", "provider", "model", "usage")}, indent=2))
if r.status_code != 200:
    print(json.dumps(d, indent=2)[:2000])
    sys.exit(1)
content = d["choices"][0]["message"]["content"]
print(f"content: {content!r}")
served = d.get("provider")
print(f"\nSERVED BY: {served}")
ok = served in ("GMICloud", "CoreWeave")
print("VERDICT: " + ("pin is live and served by a pinned provider" if ok
                     else f"!! served by {served}, which is NOT in the pin"))
sys.exit(0 if ok else 2)

#!/usr/bin/env python3
"""
debug_voyager.py — Diagnostic script
=====================================
Navigate to a LinkedIn people page and save all Voyager API responses to files.
This lets you inspect the actual JSON structure before updating the parser.

Usage:
    source /home/kali/anaconda3/bin/activate base
    python3 debug_voyager.py <li_at_cookie> [url]

    url defaults to: https://www.linkedin.com/school/ensam-casablanca/people/

Output:
    /tmp/voyager_responses/  — all captured JSON blobs
    /tmp/voyager_summary.txt — human-readable list of what was found
"""

from __future__ import annotations
import asyncio
import json
import os
import sys
import re
from pathlib import Path


async def _run(li_at: str, target_url: str):
    from patchright.async_api import async_playwright

    out_dir = Path("/tmp/voyager_responses")
    out_dir.mkdir(parents=True, exist_ok=True)

    # Clean up previous run
    for f in out_dir.glob("*.json"):
        f.unlink()

    captures = []
    counter  = [0]

    async def on_response(resp):
        try:
            url = resp.url
            ct  = resp.headers.get("content-type", "")
            if resp.status == 200 and "application/json" in ct:
                body = await resp.body()
                try:
                    data = json.loads(body)
                except Exception:
                    return

                fname = f"{counter[0]:04d}_{url.split('?')[0].split('/')[-1][:40]}.json"
                counter[0] += 1
                fpath = out_dir / fname
                fpath.write_bytes(body)

                # Quick triage of what's in this response
                summary = _triage(data, url)
                captures.append({"file": fname, "url": url[:100], "summary": summary})
                print(f"  [{counter[0]:03d}] {url[:80]}  →  {summary}")
        except Exception as e:
            pass

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage",
                  "--disable-blink-features=AutomationControlled"],
        )
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="fr-FR",
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        await ctx.add_cookies([{
            "name": "li_at", "value": li_at.strip(),
            "domain": ".linkedin.com", "path": "/",
            "secure": True, "httpOnly": True, "sameSite": "None",
        }])

        page = await ctx.new_page()
        page.on("response", on_response)

        print(f"\n🌐  Navigating to: {target_url}")
        print("Capturing Voyager API responses...\n")

        await page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(5000)

        if any(x in page.url for x in ("authwall", "login", "signin")):
            print("❌ Invalid li_at cookie. Please renew it.")
            await browser.close()
            return

        # Scroll a few times to trigger more API calls
        for i in range(5):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(2000)
            print(f"   Scroll {i+1}/5 done...")

        # Try DOM extraction
        print("\n🔍  DOM extraction:")
        dom_links = await page.evaluate("""() => {
            const links = Array.from(document.querySelectorAll('a[href*="/in/"]'));
            return links.slice(0, 20).map(a => ({
                href: a.href.split('?')[0],
                text: a.innerText.trim().slice(0, 60),
                hasImg: !!a.closest('li')?.querySelector('img')
            }));
        }""")
        for d in dom_links:
            print(f"   {d['href']}  [{d['text']}]  img={d['hasImg']}")

        await browser.close()

    print(f"\n\n{'='*60}")
    print(f"SUMMARY: {len(captures)} Voyager responses captured")
    print(f"Files saved in: {out_dir}")
    print("="*60)

    # Write summary
    summary_path = Path("/tmp/voyager_summary.txt")
    with summary_path.open("w") as f:
        for c in captures:
            f.write(f"\nFILE: {c['file']}\n")
            f.write(f"URL:  {c['url']}\n")
            f.write(f"INFO: {c['summary']}\n")

    print(f"Summary written to: {summary_path}")
    print("\nTo inspect a file:")
    print("  python3 -c \"import json,pprint; pprint.pprint(json.load(open('/tmp/voyager_responses/0000_blended.json')))\" | head -100")

    # Try to parse all captured files with the current parser
    print("\n\n--- Testing current _parse_voyager_response ---")
    sys.path.insert(0, str(Path(__file__).parent))
    from core.linkedin_scraper import _parse_voyager_response
    for fpath in sorted(out_dir.glob("*.json")):
        results = _parse_voyager_response(fpath.read_bytes())
        if results:
            print(f"  ✅ {fpath.name}: {len(results)} profiles found")
            for r in results[:3]:
                print(f"      → {r.get('nom', '?')}  {r.get('href', '?')[:50]}")
        else:
            print(f"  ❌ {fpath.name}: 0 profiles")

    # Deep inspect first few non-empty JSONs
    print("\n--- Key structures found ---")
    for fpath in sorted(out_dir.glob("*.json"))[:10]:
        body = json.loads(fpath.read_bytes())
        keys = _find_interesting_structures(body)
        if keys:
            print(f"\n  {fpath.name}:")
            for k in keys:
                print(f"    {k}")


def _triage(data: dict, url: str) -> str:
    """Quick human-readable summary of a JSON blob."""
    parts = []

    # Count included entities
    included = data.get("included", [])
    if included:
        types = {}
        for e in included:
            t = e.get("$type", "unknown")
            types[t] = types.get(t, 0) + 1
        type_str = ", ".join(f"{v}x {t.split('.')[-1]}" for t, v in sorted(types.items(), key=lambda x: -x[1])[:4])
        parts.append(f"included[{len(included)}]: {type_str}")

    # Check data.elements
    elements = data.get("data", {})
    if isinstance(elements, dict):
        el_count = len(elements.get("elements", elements.get("*elements", [])))
        if el_count:
            parts.append(f"elements={el_count}")

    # Check for paging
    paging = data.get("paging") or data.get("data", {}).get("paging", {})
    if paging:
        parts.append(f"paging(total={paging.get('total', '?')}, start={paging.get('start', '?')}, count={paging.get('count', '?')})")

    # Check entityResult
    er_count = _count_key(data, "entityResult")
    if er_count:
        parts.append(f"entityResult×{er_count}")

    # Check navigationUrl
    nav_count = _count_key(data, "navigationUrl")
    if nav_count:
        parts.append(f"navigationUrl×{nav_count}")

    # Check publicIdentifier
    pub_count = _count_key(data, "publicIdentifier")
    if pub_count:
        parts.append(f"publicIdentifier×{pub_count}")

    return " | ".join(parts) if parts else "empty/irrelevant"


def _count_key(obj, key, depth=0):
    """Count occurrences of key anywhere in obj."""
    if depth > 10:
        return 0
    count = 0
    if isinstance(obj, dict):
        if key in obj:
            count += 1
        for v in obj.values():
            count += _count_key(v, key, depth + 1)
    elif isinstance(obj, list):
        for item in obj:
            count += _count_key(item, key, depth + 1)
    return count


def _find_interesting_structures(data: dict, prefix="", depth=0) -> list[str]:
    """Find JSON keys that look useful for profile extraction."""
    results = []
    if depth > 6:
        return results
    if isinstance(data, dict):
        for k, v in data.items():
            path = f"{prefix}.{k}" if prefix else k
            if k in ("entityResult", "miniProfile", "navigationUrl", "publicIdentifier",
                     "vectorImage", "profilePicture", "displayImageReference"):
                results.append(f"{path} = {str(v)[:80]}")
            else:
                results.extend(_find_interesting_structures(v, path, depth + 1))
    elif isinstance(data, list) and data:
        results.extend(_find_interesting_structures(data[0], f"{prefix}[0]", depth + 1))
    return results


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 debug_voyager.py <li_at_cookie> [url]")
        print("       python3 debug_voyager.py <li_at_cookie> school/ensam-rabat")
        sys.exit(1)

    li_at = sys.argv[1]
    url   = sys.argv[2] if len(sys.argv) > 2 else "https://www.linkedin.com/school/ensam-casablanca/people/"

    if not url.startswith("http"):
        if "company/" in url or "school/" in url:
            url = f"https://www.linkedin.com/{url}"
        else:
            url = f"https://www.linkedin.com/school/{url}/people/"
    if "/people" not in url:
        url = url.rstrip("/") + "/people/"

    asyncio.run(_run(li_at, url))

"""
Capture une réponse GraphQL LinkedIn pour analyser la structure photo.
Usage: PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python python3 capture_graphql.py
"""
import asyncio, json, os, sys

LI_AT = os.environ.get("LI_AT", "")
URL = "https://www.linkedin.com/school/ensam-casablanca/people/"
OUT = "/tmp/graphql_captures"

os.makedirs(OUT, exist_ok=True)

async def main():
    if not LI_AT or LI_AT == "VOTRE_COOKIE" or len(LI_AT) < 50:
        raise RuntimeError("Missing/invalid LI_AT. Export LI_AT before running this script.")

    from patchright.async_api import async_playwright
    captured = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
        )
        await ctx.add_cookies([{
            "name": "li_at", "value": LI_AT,
            "domain": ".linkedin.com", "path": "/",
            "secure": True, "httpOnly": True, "sameSite": "None",
        }])
        page = await ctx.new_page()

        async def on_response(response):
            url = response.url
            if ("graphql" in url or "voyager" in url) and response.status == 200:
                ct = response.headers.get("content-type", "")
                if "json" in ct or "javascript" in ct:
                    try:
                        body = await response.body()
                        data = json.loads(body)
                        captured.append({"url": url.split("?")[0], "data": data})
                    except Exception:
                        pass

        page.on("response", on_response)
        await page.goto(URL, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(8000)
        await browser.close()

    print(f"Captured {len(captured)} responses")

    # Sauvegarde brute
    for i, c in enumerate(captured):
        path = f"{OUT}/resp_{i}.json"
        with open(path, "w") as f:
            json.dump(c["data"], f, indent=2, ensure_ascii=False)
        print(f"  [{i}] {c['url'][-60:]}  →  {path}")

    # Analyse : chercher les clés liées aux photos
    print("\n=== ANALYSE PHOTO ===")
    for i, c in enumerate(captured):
        data = c["data"]
        raw = json.dumps(data)
        # Chercher les patterns photo connus
        has_photo = any(k in raw for k in [
            "vectorImage", "rootUrl", "profilePicture", "picture",
            "photoFilterEditHashURN", "profilePhoto", "media.licdn.com"
        ])
        if not has_photo:
            continue

        print(f"\n--- Response {i}: {c['url'][-60:]} ---")

        # Chercher dans included[]
        included = data.get("included", [])
        if included:
            for j, entity in enumerate(included[:3]):
                if not isinstance(entity, dict):
                    continue
                etype = entity.get("$type", "")
                if "Profile" in etype or "MiniProfile" in etype or "picture" in str(entity.keys()):
                    print(f"  included[{j}] $type={etype}")
                    # Dump photo-related keys
                    for key in ["picture", "profilePicture", "vectorImage", "photoFilterEditHashURN"]:
                        if key in entity:
                            print(f"    {key} = {json.dumps(entity[key], indent=4)[:500]}")

        # Chercher dans data.data
        def find_photo_nodes(node, path="root", depth=0):
            if depth > 8 or not isinstance(node, (dict, list)):
                return
            if isinstance(node, list):
                for k, item in enumerate(node[:5]):
                    find_photo_nodes(item, f"{path}[{k}]", depth+1)
                return
            for key, val in node.items():
                if key in ("image", "picture", "profilePicture", "vectorImage", "photo"):
                    print(f"  {path}.{key} = {json.dumps(val, indent=2)[:400]}")
                elif key in ("navigationUrl",) and isinstance(val, str) and "/in/" in val:
                    # Found a profile, check siblings for photo
                    for pk in ("image", "picture", "profilePicture"):
                        if pk in node:
                            print(f"  PROFILE {path}.navigationUrl => {val[:50]}")
                            print(f"  PROFILE {path}.{pk} = {json.dumps(node[pk], indent=2)[:400]}")
                elif isinstance(val, (dict, list)):
                    find_photo_nodes(val, f"{path}.{key}", depth+1)

        find_photo_nodes(data, f"resp[{i}]")

asyncio.run(main())

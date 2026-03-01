"""
Phase 1 — Alumni OSINT Recon Pipeline
-------------------------------------
Production-ready scraping pipeline for alumni/company profile collection.

Scope (Phase 1 only):
- resilient web scraping (Patchright/Playwright)
- profile metadata extraction
- HD image URL upscaling hack
- file-safe image download + de-duplication
- JSON metadata export
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import unicodedata
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Callable
from urllib.parse import urlparse

import httpx

from core.config import PAGE_TIMEOUT, SCROLL_DELAY, VIEWPORT_H, VIEWPORT_W
from core.linkedin_scraper import (
    LinkedInScraper,
    _BTN_IGNORE,
    _JS_EXTRACT,
    _LOAD_MORE_SELECTORS,
    _parse_voyager_response,
)


@dataclass
class AlumniProfile:
    name: str
    headline: str
    profile_url: str
    source_image_url: str
    high_res_image_url: str = ""
    image_filename: str = ""
    image_path: str = ""
    image_downloaded: bool = False
    error: str = ""
    scraped_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def make_high_res_image_url(url: str, target_size: int = 800) -> str:
    """
    High-Res Image Hack:
    Replace low-res tokens in LinkedIn image URLs with high-res variants.

    Examples:
    - shrink_100_100 -> shrink_800_800
    - shrink_200_200 -> shrink_800_800
    - scale_100_100  -> scale_800_800
    """
    if not url:
        return ""

    upgraded = url

    upgraded = re.sub(
        r"(profile-displayphoto-(?:shrink|scale)_)\d+_\d+",
        rf"\g<1>{target_size}_{target_size}",
        upgraded,
        flags=re.IGNORECASE,
    )

    upgraded = re.sub(
        r"((?:shrink|scale)_)\d+_\d+",
        rf"\g<1>{target_size}_{target_size}",
        upgraded,
        flags=re.IGNORECASE,
    )

    return upgraded


def normalize_name_for_filename(name: str) -> str:
    text = (name or "").strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("'", " ")
    text = re.sub(r"[^A-Za-z0-9\-\s_]", "", text)
    text = re.sub(r"\s+", "_", text).strip("_")
    return text or "unknown_profile"


class AlumniOSINTPipeline:
    """Resilient pipeline for Phase 1 alumni/company profile collection."""

    def __init__(
        self,
        li_at: str,
        entity_url: str,
        output_metadata_file: str = "profiles_metadata.json",
        images_dir: str = "high_res_images",
        max_profiles: int = 5000,
        max_stale_rounds: int = 3,
        high_res_size: int = 800,
        on_progress: Callable[[str], None] | None = None,
    ) -> None:
        self.li_at = li_at.strip()
        self.entity_url = LinkedInScraper._normalize_url(entity_url)
        self.output_metadata_file = output_metadata_file
        self.images_dir = images_dir
        self.max_profiles = max_profiles
        self.max_stale_rounds = max(1, int(max_stale_rounds))
        self.high_res_size = max(200, int(high_res_size))
        self._log = on_progress or (lambda _: None)

        os.makedirs(self.images_dir, exist_ok=True)
        os.makedirs(os.path.dirname(self.output_metadata_file) or ".", exist_ok=True)

    def run(self) -> list[AlumniProfile]:
        if not self.li_at or self.li_at == "VOTRE_COOKIE" or len(self.li_at) < 50:
            raise ValueError("li_at cookie is missing or invalid.")

        profiles = asyncio.run(self._collect_profiles())
        asyncio.run(self._download_images(profiles))
        self._save_metadata(profiles)
        return profiles

    async def _collect_profiles(self) -> list[AlumniProfile]:
        from patchright.async_api import async_playwright

        voyager_buffer: list[dict] = []
        urn_photos: dict[str, str] = {}

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            ctx = await browser.new_context(
                viewport={"width": VIEWPORT_W, "height": VIEWPORT_H},
                locale="en-US",
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            await ctx.add_cookies(
                [
                    {
                        "name": "li_at",
                        "value": self.li_at,
                        "domain": ".linkedin.com",
                        "path": "/",
                        "secure": True,
                        "httpOnly": True,
                        "sameSite": "None",
                    }
                ]
            )

            page = await ctx.new_page()
            api_calls: list[str] = []

            async def on_response(response):
                try:
                    rurl = response.url
                    ct = response.headers.get("content-type", "")
                    is_voyager = (
                        (
                            "voyager/api" in rurl
                            or "/api/graphql" in rurl
                            or "/api/identity" in rurl
                            or "/api/search" in rurl
                            or "/api/organization" in rurl
                        )
                        and response.status == 200
                    )
                    if not is_voyager:
                        return
                    if "json" not in ct and "javascript" not in ct:
                        return

                    body = await response.body()
                    parsed = _parse_voyager_response(body, urn_photos)
                    short = rurl.split("?")[0].split("/")[-1][:40]
                    if parsed:
                        voyager_buffer.extend(parsed)
                        api_calls.append(f"✅ {short} -> {len(parsed)}")
                    else:
                        api_calls.append(f"⚪ {short} -> 0")
                except Exception:
                    return

            page.on("response", on_response)

            self._log(f"🌐 Target: {self.entity_url}")
            await page.goto(self.entity_url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
            await page.wait_for_timeout(4000)

            if any(x in page.url for x in ("authwall", "login", "signin", "checkpoint")):
                await browser.close()
                raise RuntimeError("Cookie invalid or expired: redirected to login/authwall.")

            collected: list[AlumniProfile] = []
            seen_urls: set[str] = set()
            stale = 0
            round_num = 0

            while len(collected) < self.max_profiles:
                round_num += 1
                previous_count = len(voyager_buffer)

                await self._smooth_scroll(page)

                clicked = await self._click_load_more(page)
                if clicked:
                    self._log(f"   🖱️ Clicked show more (round {round_num})")
                    await page.wait_for_timeout(2500)
                    await self._smooth_scroll(page)

                try:
                    await page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    await page.wait_for_timeout(int(SCROLL_DELAY * 1000))

                if api_calls:
                    self._log(f"   🔌 API: {' | '.join(api_calls[-5:])}")
                    api_calls.clear()

                fresh_voyager = voyager_buffer[previous_count:]
                raw = [item for item in fresh_voyager if item.get("href") not in seen_urls]

                dom_raw: list[dict] = await page.evaluate(_JS_EXTRACT)
                dom_by_slug: dict[str, dict] = {}
                for item in dom_raw:
                    href = (item.get("href") or "").split("?")[0].rstrip("/")
                    if "/in/" in href:
                        dom_by_slug[href.split("/in/")[-1]] = item

                if raw:
                    for item in raw:
                        if not item.get("photo_url"):
                            href = item.get("href", "").split("?")[0].rstrip("/")
                            slug = href.split("/in/")[-1] if "/in/" in href else ""
                            dom_match = dom_by_slug.get(slug)
                            if dom_match and dom_match.get("photo_url"):
                                item["photo_url"] = dom_match["photo_url"]
                else:
                    raw = [item for item in dom_raw if item.get("href") not in seen_urls]
                    if raw:
                        self._log(f"   ⚠️ DOM fallback ({len(raw)} candidates)")

                added = 0
                for item in raw:
                    profile_url = (item.get("href") or "").split("?")[0].rstrip("/")
                    if not profile_url or profile_url in seen_urls:
                        continue

                    seen_urls.add(profile_url)
                    profile = AlumniProfile(
                        name=(item.get("nom") or "").strip(),
                        headline=(item.get("titre") or "").strip(),
                        profile_url=profile_url,
                        source_image_url=(item.get("photo_url") or "").strip(),
                        scraped_at=datetime.now(timezone.utc).isoformat(),
                    )
                    collected.append(profile)
                    added += 1

                    if len(collected) >= self.max_profiles:
                        break

                source = "Voyager" if fresh_voyager else "DOM"
                self._log(
                    f"🔄 Round {round_num} [{source}]: +{added} profiles | total {len(collected)}/{self.max_profiles}"
                )

                if added == 0 and not clicked:
                    stale += 1
                    if stale >= self.max_stale_rounds:
                        self._log(
                            f"✅ Exhausted page ({self.max_stale_rounds} stale rounds)."
                        )
                        break
                    await page.wait_for_timeout(3500)
                else:
                    stale = 0

            await browser.close()
            return collected

    async def _download_images(self, profiles: list[AlumniProfile]) -> None:
        sem = asyncio.Semaphore(8)

        async with httpx.AsyncClient(
            timeout=30,
            follow_redirects=True,
            limits=httpx.Limits(max_connections=12, max_keepalive_connections=8),
            headers={
                "Referer": "https://www.linkedin.com/",
                "Origin": "https://www.linkedin.com",
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Cookie": f"li_at={self.li_at}",
            },
        ) as client:
            tasks = [self._download_single_image(client, sem, profile, idx) for idx, profile in enumerate(profiles)]
            await asyncio.gather(*tasks)

    def _hd_candidates(self, source_url: str) -> list[str]:
        if not source_url:
            return []
        candidates = [
            make_high_res_image_url(source_url, self.high_res_size),
            make_high_res_image_url(source_url, 1200),
            make_high_res_image_url(source_url, 800),
            make_high_res_image_url(source_url, 600),
            source_url,
        ]
        uniq: list[str] = []
        for url in candidates:
            if url and url not in uniq:
                uniq.append(url)
        return uniq

    async def _download_single_image(
        self,
        client: httpx.AsyncClient,
        sem: asyncio.Semaphore,
        profile: AlumniProfile,
        idx: int,
    ) -> None:
        if not profile.source_image_url:
            profile.error = "No public image URL"
            return

        hd_candidates = self._hd_candidates(profile.source_image_url)
        profile.high_res_image_url = hd_candidates[0] if hd_candidates else ""

        base = normalize_name_for_filename(profile.name)
        if base == "unknown_profile":
            parsed = urlparse(profile.profile_url)
            base = normalize_name_for_filename(parsed.path.strip("/").replace("/", "_"))

        filename = f"{base}.jpg"
        target = os.path.join(self.images_dir, filename)
        suffix = 2
        while os.path.exists(target):
            filename = f"{base}_{suffix}.jpg"
            target = os.path.join(self.images_dir, filename)
            suffix += 1

        async with sem:
            last_error = ""
            for candidate_url in hd_candidates:
                try:
                    response = await client.get(candidate_url)
                    if response.status_code == 200 and len(response.content) > 700:
                        with open(target, "wb") as file:
                            file.write(response.content)
                        profile.image_downloaded = True
                        profile.image_filename = filename
                        profile.image_path = target
                        profile.high_res_image_url = candidate_url
                        profile.error = ""
                        return
                    last_error = f"HTTP {response.status_code}"
                except Exception as exc:
                    last_error = str(exc)[:120]
            profile.error = last_error or "Failed to download HD image"

    def _save_metadata(self, profiles: list[AlumniProfile]) -> None:
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "entity_url": self.entity_url,
            "max_profiles": self.max_profiles,
            "high_res_size": self.high_res_size,
            "count_total": len(profiles),
            "count_with_image": sum(1 for p in profiles if p.image_downloaded),
            "profiles": [profile.to_dict() for profile in profiles],
        }
        with open(self.output_metadata_file, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
        self._log(f"💾 Metadata saved to: {self.output_metadata_file}")

    async def _smooth_scroll(self, page) -> None:
        page_height = int(await page.evaluate("document.body.scrollHeight"))
        scroll_y = int(await page.evaluate("window.scrollY"))
        step = max(300, page_height // 10)
        for pos in range(scroll_y, page_height + step, step):
            await page.evaluate(f"window.scrollTo(0, {pos})")
            await page.wait_for_timeout(140)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(700)

    async def _click_load_more(self, page) -> bool:
        for selector in _LOAD_MORE_SELECTORS:
            try:
                buttons = await page.query_selector_all(selector)
                for button in buttons:
                    if not await button.is_visible():
                        continue
                    text = (await button.inner_text()).strip().lower()
                    if any(token in text for token in _BTN_IGNORE):
                        continue
                    await button.scroll_into_view_if_needed()
                    await button.click()
                    return True
            except Exception:
                continue
        return False

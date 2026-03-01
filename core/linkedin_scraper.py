"""
core/linkedin_scraper.py — Stratégie double-couche
===================================================
1. PRIMAIRE  — Interception réseau Voyager API (JSON interne LinkedIn)
   Noms, titres, URLs photos directement dans la réponse JSON.
   Zéro dépendance CSS. Zéro problème de lazy-load photos.
2. SECONDAIRE — Extraction DOM JS (fallback si Voyager vide)
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass, asdict
from typing import Callable

import httpx

from core.config import SCROLL_DELAY, PAGE_TIMEOUT, VIEWPORT_W, VIEWPORT_H


# ---------------------------------------------------------------------------
# Modèle de données
# ---------------------------------------------------------------------------

@dataclass
class Profile:
    url:        str
    nom:        str = ""
    titre:      str = ""
    photo_url:  str = ""
    photo_path: str = ""
    error:      str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Parseur Voyager API — multi-stratégie
# ---------------------------------------------------------------------------

def _parse_voyager_response(
    body_bytes: bytes,
    urn_photos: dict[str, str] | None = None,
) -> list[dict]:
    """
    Extrait les profils d'une réponse JSON Voyager/GraphQL.

    Architecture LinkedIn GraphQL :
    - Réponse A (searchDashClusters) → EntityResultViewModel avec noms, URLs,
      et un URN *profile dans image.attributes[].detailData
    - Réponse B (graphql profile) → Profile dans included[] avec
      profilePicture.displayImageReferenceResolutionResult.vectorImage

    Les photos et profils arrivent souvent dans des réponses SÉPARÉES.
    ``urn_photos`` sert de cache URN→photo_url cross-responses.
    """
    try:
        data = json.loads(body_bytes)
    except Exception:
        return []

    if urn_photos is None:
        urn_photos = {}

    results: list[dict] = []
    seen:    set[str]   = set()

    # ── Pré-scan : construire le cache URN→photo depuis included[] ─────────
    included = data.get("included") if isinstance(data, dict) else None
    if isinstance(included, list):
        for entity in included:
            if not isinstance(entity, dict):
                continue
            urn = entity.get("entityUrn", "")
            if not urn:
                continue
            photo = _er_photo_included(entity)
            if photo:
                urn_photos[urn] = photo

    # ── Stratégie 1 : EntityResultViewModel / entityResult ─────────────────
    def walk_er(node, depth=0):
        if depth > 15 or not isinstance(node, (dict, list)):
            return
        if isinstance(node, list):
            for item in node:
                walk_er(item, depth + 1)
            return

        # Nouveau format : EntityResultViewModel directement dans included[]
        etype = node.get("$type", "") if isinstance(node, dict) else ""
        is_ervm = "EntityResultViewModel" in etype

        er = None
        if "entityResult" in node:
            candidate = node["entityResult"]
            if isinstance(candidate, dict):
                er = candidate
        elif is_ervm:
            er = node

        if er and isinstance(er, dict):
            href  = er.get("navigationUrl", "")
            nom   = _er_text(er, "title")
            titre = _er_text(er, "primarySubtitle") or _er_text(er, "secondarySubtitle")
            photo = _er_photo_er(er, urn_photos)
            if href and "linkedin.com/in/" in href:
                clean = href.split("?")[0].rstrip("/")
                if clean not in seen:
                    seen.add(clean)
                    results.append({"href": clean, "nom": nom,
                                    "titre": titre, "photo_url": photo})
            if is_ervm:
                return  # pas de descente récursive, déjà traité

        for v in (node.values() if isinstance(node, dict) else []):
            walk_er(v, depth + 1)

    walk_er(data)
    # Scanner aussi included[] pour les EntityResultViewModel
    if isinstance(included, list):
        for entity in included:
            if isinstance(entity, dict) and "EntityResultViewModel" in entity.get("$type", ""):
                walk_er(entity, 0)

    # ── Stratégie 2 : included[] avec MiniProfile / Profile ────────────────
    if isinstance(included, list):
        for entity in included:
            if not isinstance(entity, dict):
                continue
            etype = entity.get("$type", "")
            is_profile = (
                "MiniProfile" in etype
                or "dash.identity.profile.Profile" in etype
                or "voyager.identity.profile.Profile" in etype
            )
            if not is_profile:
                continue
            pub = entity.get("publicIdentifier") or entity.get("vanityName", "")
            if not pub:
                continue
            href  = f"https://www.linkedin.com/in/{pub}"
            if href in seen:
                continue
            seen.add(href)

            nom   = (
                f"{entity.get('firstName', '')} {entity.get('lastName', '')}".strip()
                or entity.get("name", "")
            )
            titre = entity.get("occupation") or entity.get("headline") or ""
            urn   = entity.get("entityUrn", "")
            photo = urn_photos.get(urn, "") or _er_photo_included(entity)
            results.append({"href": href, "nom": nom,
                            "titre": titre, "photo_url": photo})

    # ── Stratégie 3 : items avec navigationUrl plat ────────────────────────
    if not results:
        def walk_nav(node, depth=0):
            if depth > 12 or not isinstance(node, (dict, list)):
                return
            if isinstance(node, list):
                for item in node:
                    walk_nav(item, depth + 1)
                return
            nav = node.get("navigationUrl", "")
            if nav and "linkedin.com/in/" in nav:
                clean = nav.split("?")[0].rstrip("/")
                if clean not in seen:
                    seen.add(clean)
                    results.append({
                        "href":      clean,
                        "nom":       _er_text(node, "title") or _er_text(node, "name"),
                        "titre":     _er_text(node, "primarySubtitle") or _er_text(node, "subtitle"),
                        "photo_url": _er_photo_er(node, urn_photos),
                    })
                return
            for v in node.values():
                walk_nav(v, depth + 1)

        walk_nav(data)

    return results


def _er_text(er: dict, key: str) -> str:
    v = er.get(key)
    if isinstance(v, dict):
        return v.get("text", "") or v.get("accessibilityText", "")
    return v if isinstance(v, str) else ""


def _er_photo_er(er: dict, urn_photos: dict[str, str] | None = None) -> str:
    """Photo depuis un nœud entityResult / EntityResultViewModel.

    Gère 3 cas :
    1. vectorImage inline dans detailData
    2. profilePicture URN-ref dans detailData → lookup dans urn_photos
    3. nonEntityProfilePicture.*profile URN → lookup dans urn_photos
    """
    if urn_photos is None:
        urn_photos = {}
    try:
        attrs = er["image"]["attributes"]
        for attr in attrs:
            dd = attr.get("detailData") or attr.get("detailDataUnion") or {}

            # Cas 1 : vectorImage inline
            vi = dd.get("vectorImage")
            if isinstance(vi, dict):
                url = _extract_vector_image(vi)
                if url:
                    return url

            # Cas 2 : profilePicture avec displayImageReference
            pp = dd.get("profilePicture") or {}
            if isinstance(pp, dict):
                for ref_key in ("displayImageReferenceResolutionResult",
                                "displayImageReference", "profilePicture"):
                    ref = pp.get(ref_key)
                    if isinstance(ref, dict):
                        url = _extract_vector_image(ref.get("vectorImage") or {})
                        if url:
                            return url

            # Cas 3 : nonEntityProfilePicture → URN lookup
            for pp_key in ("nonEntityProfilePicture", "profilePictureWithoutFrame",
                           "profilePictureWithRingStatus"):
                pp_ref = dd.get(pp_key)
                if isinstance(pp_ref, dict):
                    # Photo inline dans profilePicture du ref
                    pp_inner = pp_ref.get("profilePicture") or {}
                    if isinstance(pp_inner, dict):
                        for ref_key in ("displayImageReferenceResolutionResult",
                                        "displayImageReference",
                                        "displayImageWithFrameReference",
                                        "displayImageWithFrameReferenceUnion"):
                            ref = pp_inner.get(ref_key)
                            if isinstance(ref, dict):
                                url = _extract_vector_image(ref.get("vectorImage") or {})
                                if url:
                                    return url
                    # URN fallback
                    profile_urn = pp_ref.get("*profile", "")
                    if profile_urn and profile_urn in urn_photos:
                        return urn_photos[profile_urn]
    except (KeyError, TypeError):
        pass
    return ""


def _er_photo_included(entity: dict) -> str:
    """Photo depuis un objet MiniProfile/Profile dans included[].

    Gère les clés :
    - picture.vectorImage (legacy)
    - profilePicture.displayImageReferenceResolutionResult.vectorImage (GraphQL 2024+)
    - profilePicture.displayImageReference.vectorImage
    - profilePicture.displayImageWithFrameReference.vectorImage (open-to-work)
    - vectorImage direct
    """
    # Format 1 : picture.com.linkedin.common.VectorImage (vieux format)
    pic = entity.get("picture") or {}
    if isinstance(pic, dict):
        vi = pic.get("vectorImage") or pic.get("com.linkedin.common.VectorImage") or pic
        url = _extract_vector_image(vi)
        if url:
            return url

    # Format 2 : profilePicture.{displayImageReference*}.vectorImage
    pp = entity.get("profilePicture")
    if isinstance(pp, dict):
        for ref_key in ("displayImageReferenceResolutionResult",
                        "displayImageReference",
                        "displayImageWithFrameReference",
                        "displayImageWithFrameReferenceUnion"):
            ref = pp.get(ref_key)
            if isinstance(ref, dict):
                url = _extract_vector_image(ref.get("vectorImage") or {})
                if url:
                    return url

    # Format 3 : vectorImage direct (certaines versions)
    vi = entity.get("vectorImage") or {}
    return _extract_vector_image(vi)


def _extract_vector_image(vi: dict) -> str:
    """Extrait la meilleure URL d'un objet vectorImage {rootUrl, artifacts}."""
    if not isinstance(vi, dict):
        return ""
    root = vi.get("rootUrl", "")
    arts = vi.get("artifacts", [])
    if root and arts:
        try:
            best = max(arts, key=lambda a: a.get("width", 0))
            seg  = best.get("fileIdentifyingUrlPathSegment", "")
            if seg:
                return root + seg
        except (TypeError, ValueError):
            pass
    return ""


# Alias pour compatibilité
def _er_photo(er: dict, urn_photos: dict | None = None) -> str:
    return _er_photo_er(er, urn_photos)


# ---------------------------------------------------------------------------
# Extraction DOM (fallback)
# ---------------------------------------------------------------------------

_JS_EXTRACT = r"""() => {
    const out  = [];
    const seen = new Set();
    const isReal = s => s && !s.startsWith('data:') &&
        (s.includes('media.licdn.com') || s.includes('media-exp'));
    const getPhoto = card => {
        for (const img of (card ? card.querySelectorAll('img') : [])) {
            for (const s of [img.getAttribute('data-delayed-url'),
                             img.getAttribute('data-src'), img.src])
                if (isReal(s)) return s;
        }
        return '';
    };
    const getText = (card, sels) => {
        for (const sel of sels) {
            const el = card && card.querySelector(sel);
            if (el && el.innerText.trim()) return el.innerText.trim();
        }
        return '';
    };
    document.querySelectorAll('a[href*="linkedin.com/in/"]').forEach(a => {
        const href = a.href.split('?')[0].replace(/\/+$/, '');
        if (!href.includes('linkedin.com/in/') || seen.has(href)) return;
        seen.add(href);
        let card = a;
        for (let i = 0; i < 8; i++) {
            if (!card.parentElement) break;
            card = card.parentElement;
            const cn = (card.className || '') + '';
            if (card.tagName==='LI' || cn.includes('profile-card') ||
                cn.includes('result-container') || cn.includes('entity-lockup') ||
                cn.includes('org-people') || card.getAttribute('data-view-name')) break;
        }
        out.push({
            href,
            nom: getText(card, [
                '[data-anonymize="person-name"]',
                '.org-people-profile-card__profile-title',
                '.artdeco-entity-lockup__title span[aria-hidden="true"]'
            ]) || a.innerText.trim(),
            titre: getText(card, [
                '[data-anonymize="job-title"]',
                '.org-people-profile-card__primary-subtitle',
                '.artdeco-entity-lockup__subtitle',
                '.entity-result__primary-subtitle'
            ]),
            photo_url: getPhoto(card),
        });
    });
    return out;
}"""

_LOAD_MORE_SELECTORS = [
    "button.scaffold-finite-scroll__load-button",
    "button.org-people-profiles-module__load-more-button",
    "button[aria-label*='more result']",
    "button[aria-label*='Show more']",
    "button[aria-label*='Afficher plus']",
]
_BTN_IGNORE = ("connect", "follow", "message", "connexion", "suivre", "envoyer", "invite")


# ---------------------------------------------------------------------------
# Scraper principal
# ---------------------------------------------------------------------------

class LinkedInScraper:
    """
    Scrape tous les membres d'une école/entreprise LinkedIn.

    Parameters
    ----------
    li_at        : cookie de session LinkedIn
    output_dir   : dossier de destination des photos
    max_profiles : limite de profils collectés
    on_progress  : callback(str) pour le suivi temps réel
    """

    def __init__(
        self,
        li_at: str,
        output_dir: str,
        max_profiles: int = 200,
        on_progress: Callable[[str], None] | None = None,
        skip_urls: set[str] | None = None,
        max_stale_rounds: int = 3,
    ) -> None:
        self.li_at        = li_at.strip()
        self.output_dir   = output_dir
        self.max_profiles = max_profiles
        self._log         = on_progress or (lambda _: None)
        self._skip_urls   = skip_urls or set()
        self.max_stale_rounds = max(1, int(max_stale_rounds))
        os.makedirs(output_dir, exist_ok=True)

    # ── API publique ─────────────────────────────────────────────────────────

    def scrape(self, entity_url: str) -> list[Profile]:
        url = self._normalize_url(entity_url)
        self._log(f"🌐 Cible : {url}")

        # Validation précoce du cookie (évite de lancer Chromium pour rien)
        if not self.li_at or len(self.li_at) < 50 or self.li_at == "VOTRE_COOKIE":
            self._log("❌ Cookie li_at absent ou invalide (placeholder).")
            return []

        try:
            return asyncio.run(self._run(url))
        except RuntimeError:
            import nest_asyncio
            nest_asyncio.apply()
            return asyncio.get_event_loop().run_until_complete(self._run(url))

    # ── Cœur asynchrone ──────────────────────────────────────────────────────

    async def _run(self, url: str) -> list[Profile]:
        from patchright.async_api import async_playwright

        voyager_buffer: list[dict] = []
        urn_photos: dict[str, str] = {}  # Cache URN→photo_url cross-responses

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
                locale="fr-FR",
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            await ctx.add_cookies([{
                "name": "li_at", "value": self.li_at,
                "domain": ".linkedin.com", "path": "/",
                "secure": True, "httpOnly": True, "sameSite": "None",
            }])

            page = await ctx.new_page()

            # ── Intercepteur Voyager API ──────────────────────────────────
            _voyager_calls: list[str] = []

            async def on_response(response):
                try:
                    rurl = response.url
                    ct   = response.headers.get("content-type", "")
                    is_voyager = (
                        ("voyager/api" in rurl or "/api/graphql" in rurl
                         or "/api/identity" in rurl or "/api/search" in rurl
                         or "/api/organization" in rurl)
                        and response.status == 200
                    )
                    if not is_voyager:
                        return
                    if "json" not in ct and "javascript" not in ct:
                        return

                    body   = await response.body()
                    parsed = _parse_voyager_response(body, urn_photos)

                    short = rurl.split("?")[0].split("/")[-1][:40]
                    if parsed:
                        voyager_buffer.extend(parsed)
                        _voyager_calls.append(f"✅ {short} → {len(parsed)} profils")
                    else:
                        _voyager_calls.append(f"⚪ {short} (0 profils)")
                except Exception:
                    pass  # jamais bloquer sur une erreur d'interception

            page.on("response", on_response)

            # ── Chargement initial ────────────────────────────────────────
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
            except Exception as nav_err:
                err_msg = str(nav_err)
                if "ERR_TOO_MANY_REDIRECTS" in err_msg:
                    self._log("❌ Boucle de redirection — cookie li_at expiré ou invalide.")
                elif "ERR_NAME_NOT_RESOLVED" in err_msg:
                    self._log("❌ DNS introuvable — vérifiez votre connexion internet.")
                elif "Timeout" in err_msg:
                    self._log("❌ Timeout de navigation — page inaccessible.")
                else:
                    self._log(f"❌ Erreur de navigation : {err_msg[:120]}")
                await browser.close()
                return []

            await page.wait_for_timeout(5000)

            if any(x in page.url for x in ("authwall", "login", "signin", "checkpoint")):
                self._log("❌ Cookie li_at invalide — reconnectez-vous.")
                await browser.close()
                return []

            await self._log_total(page)

            # ── Boucle principale ─────────────────────────────────────────
            seen_urls: set[str]      = set(self._skip_urls)
            profiles:  list[Profile] = []
            stale     = 0
            round_num = 0
            max_stale = self.max_stale_rounds

            async with httpx.AsyncClient(
                timeout=20,
                follow_redirects=True,
                limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
                headers={"Referer": "https://www.linkedin.com/"},
            ) as http:

                while len(profiles) < self.max_profiles:
                    round_num += 1
                    prev_v = len(voyager_buffer)

                    # 1. Scroll progressif → déclenche les appels Voyager
                    await self._smooth_scroll(page)

                    # 2. Bouton "Show more" si présent
                    clicked = await self._click_load_more(page)
                    if clicked:
                        self._log(f"   🖱️  'Show more' cliqué (tour {round_num})")
                        await page.wait_for_timeout(3000)
                        await self._smooth_scroll(page)

                    # 3. Attente réseau
                    try:
                        await page.wait_for_load_state("networkidle", timeout=8000)
                    except Exception:
                        await page.wait_for_timeout(int(SCROLL_DELAY * 1000))

                    # Log des appels Voyager de ce tour
                    if _voyager_calls:
                        self._log(f"   🔌 API: {' | '.join(_voyager_calls[-5:])}")
                        _voyager_calls.clear()

                    # ── PRIMAIRE : données Voyager interceptées ───────────
                    fresh_v = voyager_buffer[prev_v:]
                    raw = [r for r in fresh_v if r.get("href") not in seen_urls]

                    # ── DOM : toujours exécuté pour récupérer les photos ──
                    # LinkedIn ne sert PAS les photos via GraphQL sur les
                    # pages de recherche — seul le DOM contient les <img>.
                    dom_raw: list[dict] = await page.evaluate(_JS_EXTRACT)

                    # Index DOM par slug (ex: "omar-elkhali-12345")
                    dom_by_slug: dict[str, dict] = {}
                    for d in dom_raw:
                        dh = (d.get("href") or "").split("?")[0].rstrip("/")
                        if "/in/" in dh:
                            slug = dh.split("/in/")[-1]
                            dom_by_slug[slug] = d

                    if raw:
                        # Merger : enrichir les profils Voyager avec les
                        # photos du DOM (match par slug)
                        for item in raw:
                            if not item.get("photo_url"):
                                ih = item["href"].split("?")[0].rstrip("/")
                                slug = ih.split("/in/")[-1] if "/in/" in ih else ""
                                dom_match = dom_by_slug.get(slug)
                                if dom_match and dom_match.get("photo_url"):
                                    item["photo_url"] = dom_match["photo_url"]
                    else:
                        # Fallback complet : DOM uniquement
                        raw = [r for r in dom_raw
                               if r.get("href") not in seen_urls]
                        if raw:
                            self._log(f"   ⚠️  Fallback DOM ({len(raw)} candidats)")

                    for item in raw:
                        seen_urls.add(item["href"])

                    slots = self.max_profiles - len(profiles)
                    batch = raw[:slots]

                    # 4. Téléchargement parallèle des photos
                    sem   = asyncio.Semaphore(6)
                    tasks = [
                        self._dl_photo(http, sem, item, len(profiles) + i)
                        for i, item in enumerate(batch)
                    ]
                    done = await asyncio.gather(*tasks)
                    profiles.extend(done)

                    n_photo = sum(1 for p in done if p.photo_path)
                    source  = "Voyager" if fresh_v else "DOM"
                    self._log(
                        f"🔄  Tour {round_num} [{source}] : +{len(done)} profils "
                        f"({n_photo} photos)  |  Total : {len(profiles)}/{self.max_profiles}"
                    )

                    # 5. Condition de sortie
                    if not done and not clicked:
                        stale += 1
                        if stale >= max_stale:
                            self._log(f"✅ Page épuisée ({max_stale} tours stériles).")
                            break
                        await page.wait_for_timeout(4000)
                    else:
                        stale = 0

            await browser.close()
        return profiles

    # ── Helpers de navigation ─────────────────────────────────────────────────

    async def _smooth_scroll(self, page) -> None:
        page_h   = int(await page.evaluate("document.body.scrollHeight"))
        scroll_y = int(await page.evaluate("window.scrollY"))
        step     = max(300, page_h // 10)
        for pos in range(scroll_y, page_h + step, step):
            await page.evaluate(f"window.scrollTo(0, {pos})")
            await page.wait_for_timeout(150)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(800)

    async def _click_load_more(self, page) -> bool:
        for sel in _LOAD_MORE_SELECTORS:
            try:
                for btn in await page.query_selector_all(sel):
                    if not await btn.is_visible():
                        continue
                    text = (await btn.inner_text()).strip().lower()
                    if any(kw in text for kw in _BTN_IGNORE):
                        continue
                    await btn.scroll_into_view_if_needed()
                    await btn.click()
                    return True
            except Exception:
                continue
        return False

    async def _log_total(self, page) -> None:
        for sel in ["h2.org-people__header", ".org-people__header h2", ".org-people__header"]:
            try:
                el = await page.query_selector(sel)
                if el:
                    txt = (await el.inner_text()).strip()
                    if txt:
                        self._log(f"ℹ️  {txt}")
                        return
            except Exception:
                pass

    # ── Téléchargement d'une photo ───────────────────────────────────────────

    async def _dl_photo(
        self,
        http: httpx.AsyncClient,
        sem:  asyncio.Semaphore,
        item: dict,
        idx:  int,
    ) -> Profile:
        nom   = (item.get("nom")   or "").strip()[:80]
        titre = (item.get("titre") or "").strip()[:120]
        href  = item.get("href", "")
        purl  = item.get("photo_url", "")

        safe    = re.sub(r"[^\w\-]", "_", nom or "unknown")[:60].strip("_")
        base    = safe or f"profil_{idx:05d}"
        fpath   = os.path.join(self.output_dir, f"{base}.jpg")
        counter = 2
        while os.path.exists(fpath):
            fpath = os.path.join(self.output_dir, f"{base}_{counter}.jpg")
            counter += 1

        local_path = ""
        error      = ""

        if purl:
            async with sem:
                try:
                    resp = await http.get(purl)
                    if resp.status_code == 200 and len(resp.content) > 500:
                        with open(fpath, "wb") as f:
                            f.write(resp.content)
                        local_path = fpath
                    else:
                        error = f"HTTP {resp.status_code}"
                except Exception as exc:
                    error = str(exc)[:80]
        else:
            error = "Pas de photo publique"

        return Profile(
            url=href, nom=nom, titre=titre,
            photo_url=purl, photo_path=local_path, error=error,
        )

    # ── Normalisation URL ────────────────────────────────────────────────────

    @staticmethod
    def _normalize_url(raw: str) -> str:
        url = raw.strip()
        # Separate query string before normalizing path
        qs = ""
        if "?" in url:
            url, qs = url.split("?", 1)
        url = url.rstrip("/")
        if not url.startswith("http"):
            if url.startswith(("company/", "school/")):
                url = f"https://www.linkedin.com/{url}"
            elif "/" not in url:
                url = f"https://www.linkedin.com/school/{url}"
            else:
                url = f"https://www.linkedin.com/{url}"
        if "/people" not in url:
            url += "/people/"
        elif not url.endswith("/"):
            url += "/"
        if qs:
            url += f"?{qs}"
        return url


"""
Module de scraping LinkedIn via Google + Scrapling.

Flux principal
--------------
1. ``search_linkedin_profiles`` construit une requête Google ciblant
   ``site:linkedin.com/in/`` et retourne une liste de profils
   (URL, nom, extrait).
2. ``scrape_linkedin_profile`` visite directement la page d'un profil
   LinkedIn et en extrait les informations détaillées (nom, titre,
   localisation, expériences, formations, compétences, photo…).
"""

import os
import re
import time
from urllib.parse import quote_plus

from scrapling.fetchers import StealthyFetcher, Fetcher

from core.config import IMAGES_DIR, MAX_PROFILES_FOR_FACE_SEARCH, REQUEST_DELAY


def search_linkedin_profiles(
    company_or_school: str,
    search_type: str,
    search_value: str,
    max_results: int = 10,
    progress_callback=None,
) -> list[dict]:
    """Recherche des profils LinkedIn via Google.

    Parameters
    ----------
    company_or_school:
        Nom de l'entreprise ou de l'école à cibler.
    search_type:
        ``"nom_prenom"`` | ``"profession"`` | ``"image"``.
    search_value:
        Valeur de recherche (nom/prénom ou intitulé de poste).
        Ignorée pour ``search_type="image"``.
    max_results:
        Nombre maximum de résultats Google à demander (``num`` param).
    progress_callback:
        Fonction optionnelle ``(message: str) -> None`` appelée pour
        rapporter l'avancement.

    Returns
    -------
    list[dict]
        Liste de profils avec les clés ``url``, ``name``, ``snippet``,
        ``company_or_school``.

    Raises
    ------
    ValueError
        Si ``search_type`` est inconnu.
    """
    if search_type in ("nom_prenom", "profession"):
        query = f'site:linkedin.com/in/ "{search_value}" "{company_or_school}"'
    elif search_type == "image":
        query = f'site:linkedin.com/in/ "{company_or_school}"'
    else:
        raise ValueError(
            f"Type de recherche invalide : {search_type!r}. "
            "Valeurs acceptées : 'nom_prenom', 'profession', 'image'."
        )

    google_url = (
        f"https://www.google.com/search?q={quote_plus(query)}&num={max_results}"
    )

    if progress_callback:
        progress_callback(f"🔍 Recherche Google : {query}")

    page = StealthyFetcher.fetch(
        google_url,
        headless=True,
        network_idle=True,
        google_search=False,
    )

    profiles: list[dict] = []
    results = page.css("div.g") or page.css("[data-hveid]")

    for result in results:
        link_el = result.css("a")
        if not link_el:
            continue
        href: str = link_el[0].attrib.get("href", "")
        if "linkedin.com/in/" not in href:
            continue

        title: str = result.css("h3::text").get() or ""
        snippet: str = (
            result.css(".VwiC3b::text").get()
            or result.css("[data-sncf]::text").get()
            or ""
        )

        profiles.append(
            {
                "url": href,
                "name": (
                    title.replace(" | LinkedIn", "").replace(" - LinkedIn", "").strip()
                ),
                "snippet": snippet.strip(),
                "company_or_school": company_or_school,
            }
        )

    time.sleep(REQUEST_DELAY)
    return profiles


def scrape_linkedin_profile(
    profile_url: str, download_photo: bool = False
) -> dict:
    """Scrape les informations détaillées d'un profil LinkedIn.

    Parameters
    ----------
    profile_url:
        URL complète du profil LinkedIn (``https://www.linkedin.com/in/…``).
    download_photo:
        Si ``True``, télécharge la photo de profil dans ``IMAGES_DIR``
        et renseigne ``photo_locale`` dans le résultat.

    Returns
    -------
    dict
        Dictionnaire contenant les clés :
        ``url``, ``nom_complet``, ``titre_professionnel``,
        ``localisation``, ``photo_profil_url``, ``photo_locale``,
        ``entreprise_actuelle``, ``ecole``, ``resume``,
        ``experiences``, ``formations``, ``competences``.
    """
    page = StealthyFetcher.fetch(
        profile_url,
        headless=True,
        network_idle=True,
        google_search=True,
    )

    profile: dict = {
        "url": profile_url,
        "nom_complet": "",
        "titre_professionnel": "",
        "localisation": "",
        "photo_profil_url": "",
        "photo_locale": "",
        "entreprise_actuelle": "",
        "ecole": "",
        "resume": "",
        "experiences": [],
        "formations": [],
        "competences": [],
    }

    # Nom complet
    name_el = page.css("h1.text-heading-xlarge::text") or page.css("h1::text")
    if name_el:
        profile["nom_complet"] = name_el.get().strip()

    # Titre professionnel
    title_el = page.css("div.text-body-medium::text")
    if title_el:
        profile["titre_professionnel"] = title_el.get().strip()

    # Localisation
    loc_el = page.css("span.text-body-small.inline::text")
    if loc_el:
        profile["localisation"] = loc_el.get().strip()

    # URL de la photo de profil
    img_selectors = [
        "img.pv-top-card-profile-picture__image--show",
        "img.pv-top-card-profile-picture__image",
        "img.profile-photo-edit__preview",
        "img.EntityPhoto-circle-9",
    ]
    for sel in img_selectors:
        img_el = page.css(sel)
        if img_el:
            src: str = img_el[0].attrib.get("src", "")
            if src and "data:image" not in src:
                profile["photo_profil_url"] = src
                break

    # Téléchargement de la photo
    if download_photo and profile["photo_profil_url"]:
        safe_name = re.sub(r"[^\w\-]", "_", profile.get("nom_complet", "profile"))
        save_path = os.path.join(IMAGES_DIR, f"{safe_name}.jpg")
        try:
            resp = Fetcher.get(profile["photo_profil_url"], stealthy_headers=True)
            if hasattr(resp, "content") and resp.content:
                with open(save_path, "wb") as fh:
                    fh.write(resp.content)
                profile["photo_locale"] = save_path
        except Exception:
            pass

    # Expériences professionnelles
    for exp in page.css("#experience ~ div ul > li") or []:
        data: dict = {}
        t = exp.css(".t-bold span::text")
        if t:
            data["poste"] = t.get().strip()
        c = exp.css(".t-normal span::text")
        if c:
            data["entreprise"] = c.get().strip()
        d = exp.css(".pvs-entity__caption-wrapper::text")
        if d:
            data["dates"] = d.get().strip()
        if data:
            profile["experiences"].append(data)

    # Formations
    for edu in page.css("#education ~ div ul > li") or []:
        data = {}
        s = edu.css(".t-bold span::text")
        if s:
            data["ecole"] = s.get().strip()
        deg = edu.css(".t-normal span::text")
        if deg:
            data["diplome"] = deg.get().strip()
        if data:
            profile["formations"].append(data)

    # Compétences
    skills = page.css("#skills ~ div .t-bold span::text")
    if skills:
        profile["competences"] = [s.strip() for s in skills.getall()]

    # Résumé / À propos
    about = page.css("#about ~ div .inline-show-more-text::text")
    if about:
        profile["resume"] = about.get().strip()

    # Raccourcis pratiques
    if profile["experiences"]:
        profile["entreprise_actuelle"] = profile["experiences"][0].get("entreprise", "")
    if profile["formations"]:
        profile["ecole"] = profile["formations"][0].get("ecole", "")

    return profile

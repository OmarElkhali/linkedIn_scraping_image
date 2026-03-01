#!/usr/bin/env python3
"""
scrape_all_alumni.py
====================
Scrape ALL 5,053 ENSAM-Casablanca alumni by segmenting the search
into year-based batches. LinkedIn caps pagination at ~1,900 profiles,
so we split by graduation year ranges to get full coverage.

After scraping, builds the face recognition index automatically.
"""

import json
import os
import time
from core.linkedin_scraper import LinkedInScraper

LI_AT = os.environ.get("LI_AT", "")

OUTPUT_DIR = "output/ensam_casablanca"

# LinkedIn school alumni page supports URL params:
#   ?educationStartYear=XXXX  (year they started)
#   ?educationEndYear=XXXX    (year they finished)
# We use educationEndYear to segment alumni by graduation year.

# Year segments — each should be small enough to avoid the ~1,900 cap.
# ENSAM Casablanca has alumni from roughly 1985–2026.
YEAR_SEGMENTS = [
    # (label, url_suffix, max_profiles)
    ("avant 2015",  "?educationEndYear=2014", 1500),
    ("2015-2017",   "?educationStartYear=2015&educationEndYear=2017", 1500),
    ("2018-2019",   "?educationStartYear=2018&educationEndYear=2019", 1500),
    ("2020-2021",   "?educationStartYear=2020&educationEndYear=2021", 1500),
    ("2022-2023",   "?educationStartYear=2022&educationEndYear=2023", 1500),
    ("2024-2026",   "?educationStartYear=2024&educationEndYear=2026", 1500),
]

BASE_URL = "https://www.linkedin.com/school/ensam-casablanca/people/"


def main():
    if not LI_AT or LI_AT == "VOTRE_COOKIE" or len(LI_AT) < 50:
        print("❌ li_at manquant/invalide. Exportez LI_AT avant de lancer ce script.")
        return

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    all_profiles: list[dict] = []
    seen_urls: set[str] = set()

    # Load already-scraped profiles if any
    json_path = os.path.join(OUTPUT_DIR, "profiles.json")
    if os.path.exists(json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            existing = json.load(f)
        for p in existing:
            if p["url"] not in seen_urls:
                seen_urls.add(p["url"])
                all_profiles.append(p)
        print(f"📂 {len(all_profiles)} profils existants chargés depuis profiles.json")

    t0 = time.time()

    for label, suffix, max_p in YEAR_SEGMENTS:
        url = BASE_URL + suffix
        print(f"\n{'='*60}")
        print(f"📅 Segment : {label}")
        print(f"   URL : {url}")
        print(f"{'='*60}")

        scraper = LinkedInScraper(
            li_at=LI_AT,
            output_dir=OUTPUT_DIR,
            max_profiles=max_p,
            on_progress=lambda m: print(f"   {m}", flush=True),
        )

        batch = scraper.scrape(url)

        new_count = 0
        for p in batch:
            d = p.to_dict()
            if d["url"] not in seen_urls:
                seen_urls.add(d["url"])
                all_profiles.append(d)
                new_count += 1

        n_photo = sum(1 for p in batch if p.photo_path)
        print(f"\n   📊 Segment '{label}': {len(batch)} profils, {n_photo} photos")
        print(f"   ✅ +{new_count} nouveaux (après déduplication)")
        print(f"   📈 Total cumulé : {len(all_profiles)} profils uniques")

        # Save progress after each segment
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(all_profiles, f, ensure_ascii=False, indent=2)
        print(f"   💾 Sauvegardé → {json_path}")

    elapsed = time.time() - t0

    n_photos = sum(1 for p in all_profiles if p.get("photo_path"))
    print(f"\n{'='*60}")
    print(f"RÉSULTAT FINAL — {elapsed/60:.1f} min")
    print(f"{'='*60}")
    print(f"Profils uniques    : {len(all_profiles)}")
    print(f"Photos téléchargées: {n_photos}")
    print(f"Sans photo         : {len(all_profiles) - n_photos}")
    if all_profiles:
        print(f"Couverture         : {n_photos/len(all_profiles)*100:.1f}%")

    # Count actual image files on disk
    jpg_count = len([f for f in os.listdir(OUTPUT_DIR) if f.endswith(".jpg")])
    print(f"Fichiers .jpg      : {jpg_count}")

    # Build face index automatically
    print(f"\n{'='*60}")
    print(f"🧠 Construction de l'index facial...")
    print(f"{'='*60}")

    try:
        from core.face_index import FaceIndex
        idx = FaceIndex(os.path.join(OUTPUT_DIR, "face_index.pkl"))
        n = idx.build(all_profiles, on_progress=lambda m: print(f"   {m}"))
        print(f"\n✅ Index facial : {n} visages indexés")
    except Exception as e:
        print(f"\n⚠️ Erreur index facial : {e}")
        print("   Vous pourrez le construire depuis l'interface Streamlit.")


if __name__ == "__main__":
    main()

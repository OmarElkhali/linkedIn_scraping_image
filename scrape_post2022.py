#!/usr/bin/env python3
"""
Scrape LinkedIn profiles year-by-year using educationStartYear only.

Highlights:
- No hardcoded secrets: uses --li-at or LI_AT env var
- Starts from 2021 by default (configurable)
- Moves to next year after N stale rounds (default: 3)
- Deduplicates by URL and by normalized display name
- Resume-safe with progress files
- Optionally builds face index at the end
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

from core.linkedin_scraper import LinkedInScraper


def normalize_name(name: str) -> str:
    text = unicodedata.normalize("NFKD", (name or "").strip())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"\s+", " ", text).strip().casefold()
    return text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape LinkedIn year-by-year with educationStartYear filters."
    )
    parser.add_argument(
        "--entity-url",
        default="https://www.linkedin.com/school/ensam-casablanca/",
        help="LinkedIn school/company URL",
    )
    parser.add_argument(
        "--output-dir",
        default="output/ensam_casablanca",
        help="Output directory",
    )
    parser.add_argument(
        "--start-year",
        type=int,
        default=2021,
        help="First educationStartYear to scrape",
    )
    parser.add_argument(
        "--end-year",
        type=int,
        default=datetime.now().year,
        help="Last educationStartYear to scrape",
    )
    parser.add_argument(
        "--max-profiles-per-year",
        type=int,
        default=2000,
        help="Maximum profiles to collect per year",
    )
    parser.add_argument(
        "--max-stale-rounds",
        type=int,
        default=3,
        help="Stop a year after N rounds with no new profiles",
    )
    parser.add_argument(
        "--build-index",
        action="store_true",
        help="Build face index at the end",
    )
    parser.add_argument(
        "--li-at",
        default=os.environ.get("LI_AT", ""),
        help="LinkedIn li_at cookie (or set LI_AT env var)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    li_at = (args.li_at or "").strip()
    if not li_at or li_at == "VOTRE_COOKIE" or len(li_at) < 50:
        print("❌ li_at manquant/invalide. Passe --li-at ou exporte LI_AT.")
        return 1

    if args.end_year < args.start_year:
        print("❌ end-year doit être >= start-year")
        return 1

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "profiles.json"
    done_file = output_dir / ".years_done"

    all_profiles: list[dict] = []
    seen_urls: set[str] = set()
    seen_names: set[str] = set()

    if json_path.exists():
        with json_path.open("r", encoding="utf-8") as f:
            all_profiles = json.load(f)
        for profile in all_profiles:
            url = (profile.get("url") or "").strip()
            if url:
                seen_urls.add(url)
            key = normalize_name(profile.get("nom", ""))
            if key:
                seen_names.add(key)
        print(
            f"📂 Reprise: {len(all_profiles)} profils existants "
            f"({len(seen_urls)} URLs, {len(seen_names)} noms)",
            flush=True,
        )

    done_years: set[str] = set()
    if done_file.exists():
        done_years = {line.strip() for line in done_file.read_text().splitlines() if line.strip()}

    base = args.entity_url.rstrip("/") + "/people/"
    years = list(range(args.start_year, args.end_year + 1))
    t0 = time.time()

    for year in years:
        label = str(year)
        if label in done_years:
            print(f"\n⏭️  {year} déjà terminé, skip.", flush=True)
            continue

        url = f"{base}?educationStartYear={year}"
        print(f"\n{'=' * 60}", flush=True)
        print(f"📅 Année : {year}", flush=True)
        print(f"   URL : {url}", flush=True)
        print(f"{'=' * 60}", flush=True)

        scraper = LinkedInScraper(
            li_at=li_at,
            output_dir=str(output_dir),
            max_profiles=int(args.max_profiles_per_year),
            on_progress=lambda message: print(f"   {message}", flush=True),
            skip_urls=seen_urls,
            max_stale_rounds=int(args.max_stale_rounds),
        )

        try:
            batch = scraper.scrape(url)
        except Exception as exc:
            print(f"   ❌ Erreur année {year}: {exc}", flush=True)
            batch = []

        new_count = 0
        duplicate_name_count = 0

        for profile in batch:
            entry = profile.to_dict()
            profile_url = (entry.get("url") or "").strip()
            profile_name_key = normalize_name(entry.get("nom", ""))

            if profile_url and profile_url in seen_urls:
                continue
            if profile_name_key and profile_name_key in seen_names:
                duplicate_name_count += 1
                continue

            if profile_url:
                seen_urls.add(profile_url)
            if profile_name_key:
                seen_names.add(profile_name_key)
            all_profiles.append(entry)
            new_count += 1

        photo_count = sum(1 for profile in batch if profile.photo_path)
        print(
            f"\n   📊 Année {year}: {len(batch)} profils, {photo_count} photos",
            flush=True,
        )
        print(
            f"   ✅ +{new_count} nouveaux | doublons nom ignorés: {duplicate_name_count} "
            f"| total: {len(all_profiles)}",
            flush=True,
        )

        with json_path.open("w", encoding="utf-8") as f:
            json.dump(all_profiles, f, ensure_ascii=False, indent=2)
        with done_file.open("a", encoding="utf-8") as f:
            f.write(label + "\n")
        print("   💾 Progression sauvegardée.", flush=True)

    elapsed = time.time() - t0
    photos_with_path = sum(1 for profile in all_profiles if profile.get("photo_path"))
    jpg_count = len(list(output_dir.glob("*.jpg")))

    print(f"\n{'=' * 60}", flush=True)
    print(f"RÉSULTAT FINAL — {elapsed / 60:.1f} min", flush=True)
    print(f"{'=' * 60}", flush=True)
    print(f"Profils uniques    : {len(all_profiles)}", flush=True)
    print(f"Photos (json path) : {photos_with_path}", flush=True)
    print(f"Fichiers .jpg      : {jpg_count}", flush=True)
    if all_profiles:
        print(f"Couverture         : {photos_with_path / len(all_profiles) * 100:.1f}%", flush=True)

    if args.build_index:
        print("\n🧠 Construction de l'index facial...", flush=True)
        try:
            from core.face_index import FaceIndex

            index_path = output_dir / "face_index.pkl"
            index = FaceIndex(str(index_path))
            count = index.build(all_profiles, on_progress=lambda message: print(f"   {message}", flush=True))
            print(f"✅ Index facial: {count} visages indexés → {index_path}", flush=True)
        except Exception as exc:
            print(f"⚠️ Erreur index facial: {exc}", flush=True)

    print("\n🏁 TERMINÉ", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

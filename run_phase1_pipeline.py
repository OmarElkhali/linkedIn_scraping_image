#!/usr/bin/env python3
"""
CLI entrypoint for Phase 1 Alumni OSINT Recon Pipeline.
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone

from core.alumni_osint_pipeline import AlumniOSINTPipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Phase 1: Resilient alumni/company OSINT scraping pipeline (metadata + high-res images)."
    )
    parser.add_argument(
        "--entity-url",
        required=True,
        help="LinkedIn school/company URL (e.g. https://www.linkedin.com/school/ensam-casablanca/)",
    )
    parser.add_argument(
        "--li-at",
        default=os.environ.get("LI_AT", ""),
        help="LinkedIn li_at cookie (or set LI_AT env var)",
    )
    parser.add_argument(
        "--max-profiles",
        type=int,
        default=5000,
        help="Maximum number of profiles to collect",
    )
    parser.add_argument(
        "--max-stale-rounds",
        type=int,
        default=3,
        help="Move forward after N rounds with no new profile",
    )
    parser.add_argument(
        "--high-res-size",
        type=int,
        default=800,
        help="Target image resolution token for URL upgrade hack",
    )
    parser.add_argument(
        "--data-dir",
        default="data",
        help="Data folder (artifacts/logs)",
    )
    parser.add_argument(
        "--images-dir",
        default="high_res_images",
        help="Folder for high-resolution profile pictures",
    )
    parser.add_argument(
        "--metadata-file",
        default="profiles_metadata.json",
        help="Output JSON metadata file",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    li_at = (args.li_at or "").strip()
    if not li_at or li_at == "VOTRE_COOKIE" or len(li_at) < 50:
        print("❌ Invalid/missing li_at. Use --li-at or export LI_AT.")
        return 1

    os.makedirs(args.data_dir, exist_ok=True)
    os.makedirs(args.images_dir, exist_ok=True)

    started = datetime.now(timezone.utc).isoformat()
    print(f"🚀 Phase 1 pipeline started at {started}")
    print(f"   Target      : {args.entity_url}")
    print(f"   Max profiles: {args.max_profiles}")
    print(f"   Images dir  : {args.images_dir}")
    print(f"   Metadata    : {args.metadata_file}")

    pipeline = AlumniOSINTPipeline(
        li_at=li_at,
        entity_url=args.entity_url,
        output_metadata_file=args.metadata_file,
        images_dir=args.images_dir,
        max_profiles=args.max_profiles,
        max_stale_rounds=args.max_stale_rounds,
        high_res_size=args.high_res_size,
        on_progress=lambda m: print(m, flush=True),
    )

    try:
        profiles = pipeline.run()
    except Exception as exc:
        print(f"❌ Pipeline failed: {exc}")
        return 1

    with_images = sum(1 for p in profiles if p.image_downloaded)
    print("\n✅ Phase 1 completed")
    print(f"   Total profiles : {len(profiles)}")
    print(f"   Images saved   : {with_images}")
    print(f"   Coverage       : {(with_images / len(profiles) * 100):.1f}%" if profiles else "   Coverage       : 0%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

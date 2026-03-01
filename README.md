# Alumni OSINT Recon Pipeline

An **Automated OSINT Data & Biometric Collection Framework** for building structured alumni/professional datasets from LinkedIn school/company pages.

> **Phase 1 (current scope):** resilient profile scraping + HD image dataset generation.  
> **Not included in Phase 1:** facial recognition or AI identity matching.

## Project Status

✅ **This repository currently publishes Phase 1.**

The project is intentionally designed as a multi-phase framework:
- **Phase 1 (Live):** resilient scraping, data normalization, high-res image collection, metadata dataset.
- **Phase 2 (Planned):** biometric indexing and controlled face similarity search.
- **Phase 3 (Planned):** intelligence enrichment, scoring, analytics dashboards, and API automation.

---

## Why this project

This repository provides a production-oriented data collection pipeline designed for:
- University alumni reconnaissance (e.g., ENSAM Casablanca)
- Corporate talent landscape mapping
- Local dataset creation for future biometric/R&D phases

The pipeline focuses on reliability, metadata quality, and reproducible output structure suitable for open-source collaboration.

---

## Phase 1 Features

### 1) Resilient scraping engine (Patchright/Playwright)
- Session-based browsing using `li_at` cookie
- Infinite scroll handling
- "Show more" interaction support
- Voyager API interception + DOM fallback extraction
- Anti-fragile behavior for partial API failures

### 2) **High-Res Image Hack** (critical)
Before any download, image URLs are upgraded using dynamic URL token replacement:
- `shrink_100_100` → `shrink_800_800`
- `shrink_200_200` → `shrink_800_800`
- `scale_100_100`  → `scale_800_800`

Implemented in: `core/alumni_osint_pipeline.py` (`make_high_res_image_url`).

### 3) Data normalization and de-duplication
Extracted fields:
- `name`
- `headline`
- `profile_url`
- `source_image_url`
- `high_res_image_url`

De-duplication strategy:
- Profile-level dedupe by canonical profile URL
- File-level dedupe to prevent overwriting existing images
- Filename normalization (`FirstName_LastName.jpg`)

### 4) Production-oriented artifact output
- Clean high-resolution image folder
- Structured metadata JSON linked to exact image filenames
- Coverage stats (profiles collected vs images downloaded)

---

## Project Architecture

```text
.
├── app.py                             # Streamlit UI (next steps: UI/UX + face recognition)
├── core/
│   ├── alumni_osint_pipeline.py      # Phase 1 engine + HD URL hack
│   ├── linkedin_scraper.py           # Resilient scraping primitives
│   ├── face_index.py                 # Face indexing (Phase 2)
│   └── face_comparator.py            # Face comparison utilities
├── data/                             # Pipeline artifacts/log-ready folder
├── high_res_images/                  # Saved images: FirstName_LastName.jpg
├── profiles_metadata.json            # Structured dataset metadata
├── run_phase1_pipeline.py            # CLI entrypoint for Phase 1
├── requirements-phase1.txt           # Minimal deps for Phase 1 only
└── requirements.txt                  # Full deps (UI + future phases)
```

---

## Installation

### Prerequisites
- Python 3.11+
- Chromium-compatible environment
- Linux/macOS recommended

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements-phase1.txt
```

### Low disk space fix (`/tmp` full)

If `pip` fails with `OSError: [Errno 28] No space left on device`, use a temp folder on your home partition:

```bash
mkdir -p ~/tmp/pip
export TMPDIR=~/tmp/pip
pip install -r requirements-phase1.txt
```

> `requirements.txt` includes extra dependencies for UI and later phases (e.g. Streamlit / face stack).
> For Phase 1 pipeline only, use `requirements-phase1.txt`.

---

## Quick Start

### 1) Export session cookie
```bash
export LI_AT='your_linkedin_li_at_cookie'
```

### 2) Install Phase 1 dependencies
```bash
pip install -r requirements-phase1.txt
```

### 3) Run Phase 1 pipeline
```bash
python run_phase1_pipeline.py \
  --entity-url "https://www.linkedin.com/school/ensam-casablanca/" \
  --max-profiles 5000 \
  --max-stale-rounds 3 \
  --high-res-size 800 \
  --data-dir data \
  --images-dir high_res_images \
  --metadata-file profiles_metadata.json
```

---

## Output Schema (`profiles_metadata.json`)

Each profile entry contains dataset-ready metadata:

```json
{
  "name": "Jane Doe",
  "headline": "Data Engineer",
  "profile_url": "https://www.linkedin.com/in/jane-doe",
  "source_image_url": "https://...shrink_100_100...",
  "high_res_image_url": "https://...shrink_800_800...",
  "image_filename": "Jane_Doe.jpg",
  "image_path": "high_res_images/Jane_Doe.jpg",
  "image_downloaded": true,
  "error": "",
  "scraped_at": "2026-03-01T12:00:00Z"
}
```

---

## Security & Compliance

- Never commit `li_at` cookies or personal secrets.
- Use environment variables (`LI_AT`) or local runtime arguments only.
- Ensure your usage complies with:
  - LinkedIn Terms of Service
  - Local privacy and data protection regulations
  - Institutional research ethics policies

This repository is intended for educational/research and lawful OSINT workflows.

---

## Roadmap (post-Phase 1)

- Phase 2: biometric indexing and similarity retrieval (opt-in, compliant)
- Dataset quality scoring and validation reports
- Containerized execution (`Dockerfile`, `compose`)
- CI checks (lint/test/secret scanning)

---

## Disclaimer

This project provides technical tooling. Users are solely responsible for lawful, ethical, and policy-compliant use.

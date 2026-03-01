# Alumni OSINT Recon Pipeline — Roadmap

This project is developed in clearly separated phases.

## ✅ Phase 1 (Published)
**Title:** Data Collection Engine (OSINT Scraping Foundation)

**Delivered scope:**
- Resilient scraping with Patchright/Playwright
- Session handling and infinite-scroll extraction
- High-resolution profile image URL upgrade hack
- Data normalization and de-duplication
- Dataset artifact generation:
  - `high_res_images/`
  - `profiles_metadata.json`

**Out of scope in Phase 1:**
- Face recognition
- AI identity matching

---

## 🔜 Phase 2 (Planned)
**Title:** Biometric Indexing Layer

**Planned scope:**
- Local facial embedding/index creation
- Similarity search workflows (opt-in)
- Threshold tuning and benchmark reporting
- Improved controls for false-positive mitigation

---

## 🔜 Phase 3 (Planned)
**Title:** OSINT Intelligence & Automation

**Planned scope:**
- Enrichment/analytics pipelines
- Confidence scoring and profile intelligence views
- REST API/job orchestration
- CI/CD automation and deployment packaging

---

## Release Principle
Each phase is published as an incremental, testable, and documented milestone.

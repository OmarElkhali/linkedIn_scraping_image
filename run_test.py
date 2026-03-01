#!/usr/bin/env python3
"""
run_test.py — Vérifie le projet et teste le parseur sans cookie LinkedIn
"""
import os, sys, json
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")
sys.path.insert(0, ".")

print("=" * 55)
print("   LinkedIn Photo Scraper — Test terminal")
print("=" * 55)

# ── 1. Dépendances ──────────────────────────────────────────────────────────
print("\n[1] Dépendances Python")
errors = []
for name, mod in [("patchright", "patchright"), ("httpx", "httpx"),
                  ("streamlit", "streamlit"), ("nest_asyncio", "nest_asyncio")]:
    try:
        __import__(mod)
        print(f"  ✅ {name}")
    except ImportError as e:
        print(f"  ❌ {name}: {e}")
        errors.append(name)

# ── 2. Modules core ─────────────────────────────────────────────────────────
print("\n[2] Modules core")
for mod in ["core.config", "core.linkedin_scraper", "core.face_index"]:
    try:
        __import__(mod)
        print(f"  ✅ {mod}")
    except Exception as e:
        print(f"  ❌ {mod}: {e}")

# ── 3. Configuration ────────────────────────────────────────────────────────
print("\n[3] Configuration (core/config.py)")
from core.config import OUTPUT_DIR, SCROLL_DELAY, PAGE_TIMEOUT, VIEWPORT_W, VIEWPORT_H, FACE_TOLERANCE
print(f"  OUTPUT_DIR     = {OUTPUT_DIR}")
print(f"  SCROLL_DELAY   = {SCROLL_DELAY}s")
print(f"  PAGE_TIMEOUT   = {PAGE_TIMEOUT}ms")
print(f"  VIEWPORT       = {VIEWPORT_W}x{VIEWPORT_H}")
print(f"  FACE_TOLERANCE = {FACE_TOLERANCE}")

# ── 4. Test parseur Voyager ──────────────────────────────────────────────────
print("\n[4] Parseur Voyager API (3 stratégies)")
from core.linkedin_scraper import _parse_voyager_response

# Stratégie 1 : entityResult (pages de recherche)
fake_er = {"elements": [{"entityResult": {
    "navigationUrl": "https://www.linkedin.com/in/omar-elkhali-12345",
    "title": {"text": "Omar El Khali"},
    "primarySubtitle": {"text": "Ingénieur Informatique · ENSAM Casablanca"},
    "image": {"attributes": [{"detailData": {"profilePicture": {
        "displayImageReference": {"vectorImage": {
            "rootUrl": "https://media.licdn.com/dms/image/v2/test/",
            "artifacts": [
                {"width": 100, "fileIdentifyingUrlPathSegment": "100_100/photo.jpg"},
                {"width": 400, "fileIdentifyingUrlPathSegment": "400_400/photo.jpg"},
            ]
        }}
    }}}]}
}}]}
r1 = _parse_voyager_response(json.dumps(fake_er).encode())
status = "✅" if r1 else "❌"
print(f"  {status} Stratégie 1 (entityResult) : {len(r1)} profil(s)")
if r1:
    print(f"      nom   = {r1[0]['nom']}")
    print(f"      href  = {r1[0]['href']}")
    print(f"      photo = {r1[0]['photo_url']}")

# Stratégie 2 : MiniProfile dans included[]
fake_mp = {"included": [{
    "$type": "com.linkedin.voyager.identity.shared.MiniProfile",
    "publicIdentifier": "salma-benali-67890",
    "firstName": "Salma",
    "lastName": "Benali",
    "occupation": "Étudiante à ENSAM Casablanca",
    "picture": {"vectorImage": {
        "rootUrl": "https://media.licdn.com/dms/image/v2/xyz/",
        "artifacts": [{"width": 200, "fileIdentifyingUrlPathSegment": "200_200/pic.jpg"}]
    }}
}]}
r2 = _parse_voyager_response(json.dumps(fake_mp).encode())
status = "✅" if r2 else "❌"
print(f"  {status} Stratégie 2 (MiniProfile)  : {len(r2)} profil(s)")
if r2:
    print(f"      nom   = {r2[0]['nom']}")
    print(f"      href  = {r2[0]['href']}")
    print(f"      photo = {r2[0]['photo_url']}")

# Stratégie 3 : navigationUrl plat
fake_nav = {"results": [{"navigationUrl": "https://www.linkedin.com/in/youssef-tazi-99",
    "title": {"text": "Youssef Tazi"}, "primarySubtitle": {"text": "Développeur"}}]}
r3 = _parse_voyager_response(json.dumps(fake_nav).encode())
status = "✅" if r3 else "❌"
print(f"  {status} Stratégie 3 (navigationUrl) : {len(r3)} profil(s)")
if r3:
    print(f"      nom   = {r3[0]['nom']}")
    print(f"      href  = {r3[0]['href']}")

# ── 5. Test URL normalisation ────────────────────────────────────────────────
print("\n[5] Normalisation des URLs")
from core.linkedin_scraper import LinkedInScraper
tests = [
    "ensam-casablanca",
    "school/ensam-casablanca",
    "https://www.linkedin.com/school/ensam-casablanca/",
    "company/microsoft",
]
for raw in tests:
    normalized = LinkedInScraper._normalize_url(raw)
    print(f"  {raw!r:50s}  →  {normalized}")

# ── 6. Fichiers de sortie ────────────────────────────────────────────────────
print("\n[6] Répertoire de sortie")
import os
if os.path.isdir(OUTPUT_DIR):
    folders = [f for f in os.listdir(OUTPUT_DIR) if os.path.isdir(os.path.join(OUTPUT_DIR, f))]
    jpgs = []
    for root, dirs, files in os.walk(OUTPUT_DIR):
        jpgs += [f for f in files if f.endswith(".jpg")]
    print(f"  Dossier : {OUTPUT_DIR}/")
    print(f"  Sous-dossiers : {folders or '(aucun)'}")
    print(f"  Photos .jpg   : {len(jpgs)} fichier(s)")
else:
    print(f"  (vide — sera créé au premier scraping)")

# ── Résumé ──────────────────────────────────────────────────────────────────
print("\n" + "=" * 55)
if errors:
    print(f"⚠️  Dépendances manquantes : {', '.join(errors)}")
    print(f"   pip install {' '.join(errors)}")
else:
    print("✅ Projet opérationnel — toutes les dépendances OK")
    print()
    print("  Commandes disponibles :")
    print("  ┌─ Interface graphique ─────────────────────────────")
    print("  │  streamlit run app.py")
    print("  │  → http://localhost:8501")
    print("  │")
    print("  ├─ Diagnostic / debug ─────────────────────────────")
    print("  │  python3 debug_voyager.py <li_at> [url]")
    print("  │  → Capture les réponses Voyager dans /tmp/voyager_responses/")
    print("  │")
    print("  └─ Scraping direct ────────────────────────────────")
    print("     python3 -c \"")
    print("     from core.linkedin_scraper import LinkedInScraper")
    print("     s = LinkedInScraper(li_at='<cookie>', output_dir='output/ensam')")
    print("     profiles = s.scrape('ensam-casablanca')")
    print("     print(len(profiles), 'profils collectés')\"")
print("=" * 55)

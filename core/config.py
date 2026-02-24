"""
Configuration centralisée de l'application.

Toutes les constantes réglables sont regroupées ici pour faciliter
la maintenance et la personnalisation sans toucher au code métier.
"""

import os

# ---------------------------------------------------------------------------
# Dossiers de sortie
# ---------------------------------------------------------------------------
OUTPUT_DIR: str = os.environ.get("OUTPUT_DIR", "output")
IMAGES_DIR: str = os.path.join(OUTPUT_DIR, "profile_images")

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(IMAGES_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Reconnaissance faciale
# ---------------------------------------------------------------------------
# Tolérance de distance : plus la valeur est basse, plus la comparaison
# est stricte.  Valeur recommandée : entre 0.45 et 0.60.
FACE_MATCH_TOLERANCE: float = float(os.environ.get("FACE_MATCH_TOLERANCE", "0.55"))

# Nombre maximum de profils récupérés avant la comparaison de visages
MAX_PROFILES_FOR_FACE_SEARCH: int = int(
    os.environ.get("MAX_PROFILES_FOR_FACE_SEARCH", "20")
)

# ---------------------------------------------------------------------------
# LinkedIn / Google
# ---------------------------------------------------------------------------
LINKEDIN_BASE_URL: str = "https://www.linkedin.com"

# Délai (secondes) entre deux requêtes pour éviter le rate-limiting
REQUEST_DELAY: float = float(os.environ.get("REQUEST_DELAY", "1.5"))

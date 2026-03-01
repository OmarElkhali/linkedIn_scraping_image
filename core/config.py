"""
Configuration — LinkedIn Photo Scraper v3.
Toutes les constantes modifiables ici.
"""
import os

# Dossier racine des sorties
OUTPUT_DIR: str = os.environ.get("OUTPUT_DIR", "output")

# Tolérance reconnaissance faciale (0.4 = strict, 0.6 = souple)
FACE_TOLERANCE: float = float(os.environ.get("FACE_TOLERANCE", "0.50"))

# Délai (s) entre scrolls pour éviter le rate-limit LinkedIn
SCROLL_DELAY: float  = float(os.environ.get("SCROLL_DELAY", "1.5"))

# Timeout page Playwright (ms)
PAGE_TIMEOUT: int = int(os.environ.get("PAGE_TIMEOUT", "45000"))

# Viewport du navigateur headless
VIEWPORT_W: int = 1280
VIEWPORT_H: int = 900

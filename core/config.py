"""
Configuration centralisée de l'application.
"""

import os

# --- Dossiers ---
OUTPUT_DIR = "output"
IMAGES_DIR = os.path.join(OUTPUT_DIR, "profile_images")
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(IMAGES_DIR, exist_ok=True)

# --- Reconnaissance faciale ---
FACE_MATCH_TOLERANCE = 0.55
MAX_PROFILES_FOR_FACE_SEARCH = 20

# --- LinkedIn ---
LINKEDIN_BASE_URL = "https://www.linkedin.com"

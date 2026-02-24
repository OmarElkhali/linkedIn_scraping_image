"""
LinkedIn Scraper — package principal.

Les imports sont différés (lazy) pour éviter de charger les dépendances
lourdes (scrapling, face_recognition…) au moment du simple import du package.

Usage :
    from core.face_comparator import FaceComparator, FACE_RECOGNITION_AVAILABLE
    from core.scraper import search_linkedin_profiles, scrape_linkedin_profile
"""

__all__ = [
    "FaceComparator",
    "FACE_RECOGNITION_AVAILABLE",
    "search_linkedin_profiles",
    "scrape_linkedin_profile",
]

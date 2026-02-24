"""
LinkedIn Scraper — package principal.

Expose les composants publics du package pour des imports simplifiés :

    from core import FaceComparator, search_linkedin_profiles, scrape_linkedin_profile
"""

from core.face_comparator import FaceComparator, FACE_RECOGNITION_AVAILABLE
from core.scraper import search_linkedin_profiles, scrape_linkedin_profile

__all__ = [
    "FaceComparator",
    "FACE_RECOGNITION_AVAILABLE",
    "search_linkedin_profiles",
    "scrape_linkedin_profile",
]

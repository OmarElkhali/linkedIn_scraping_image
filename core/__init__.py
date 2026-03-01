"""
Package core — LinkedIn Photo Scraper.
Expose les composants publics.
"""
from core.linkedin_scraper import LinkedInScraper
from core.face_index import FaceIndex, FACE_RECOGNITION_AVAILABLE
from core.alumni_osint_pipeline import AlumniOSINTPipeline, make_high_res_image_url

__all__ = [
    "LinkedInScraper",
    "FaceIndex",
    "FACE_RECOGNITION_AVAILABLE",
    "AlumniOSINTPipeline",
    "make_high_res_image_url",
]

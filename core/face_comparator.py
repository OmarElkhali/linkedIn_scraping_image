"""
Module de reconnaissance faciale.
Compare un visage source avec des images cibles.
"""

import os
import tempfile

try:
    import face_recognition
    import numpy as np
    FACE_RECOGNITION_AVAILABLE = True
except ImportError:
    FACE_RECOGNITION_AVAILABLE = False


class FaceComparator:
    """Compare un visage source avec des visages cibles."""

    def __init__(self, source_image_path: str, tolerance: float = 0.55):
        if not FACE_RECOGNITION_AVAILABLE:
            raise RuntimeError(
                "face_recognition n'est pas installé.\n"
                "pip install face_recognition numpy Pillow"
            )

        self.tolerance = tolerance
        self.source_path = source_image_path

        self.source_image = face_recognition.load_image_file(source_image_path)
        self.source_encodings = face_recognition.face_encodings(self.source_image)

        if not self.source_encodings:
            raise ValueError(
                f"Aucun visage détecté dans l'image : {source_image_path}"
            )

        self.source_encoding = self.source_encodings[0]

    def compare_with_image(self, target_image_path: str) -> dict:
        """Compare le visage source avec une image cible."""
        try:
            target_image = face_recognition.load_image_file(target_image_path)
            target_encodings = face_recognition.face_encodings(target_image)

            if not target_encodings:
                return {
                    "match": False,
                    "distance": 1.0,
                    "confidence": 0.0,
                    "faces_found": 0,
                    "error": None,
                }

            best = {
                "match": False,
                "distance": 1.0,
                "confidence": 0.0,
                "faces_found": len(target_encodings),
                "error": None,
            }

            for enc in target_encodings:
                dist = face_recognition.face_distance(
                    [self.source_encoding], enc
                )[0]
                is_match = dist <= self.tolerance
                conf = max(0.0, 1.0 - dist) * 100

                if dist < best["distance"]:
                    best = {
                        "match": is_match,
                        "distance": round(float(dist), 4),
                        "confidence": round(float(conf), 2),
                        "faces_found": len(target_encodings),
                        "error": None,
                    }

            return best

        except Exception as e:
            return {
                "match": False,
                "distance": 1.0,
                "confidence": 0.0,
                "faces_found": 0,
                "error": str(e),
            }

    def compare_with_bytes(self, image_bytes: bytes) -> dict:
        """Compare avec une image en bytes."""
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp.write(image_bytes)
            tmp_path = tmp.name
        try:
            return self.compare_with_image(tmp_path)
        finally:
            os.unlink(tmp_path)

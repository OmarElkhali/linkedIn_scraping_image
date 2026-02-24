"""
Module de reconnaissance faciale.

Compare un visage source (image de référence fournie par l'utilisateur)
avec un ensemble d'images cibles téléchargées depuis les profils LinkedIn.

Dépendances
-----------
- ``face_recognition`` (dlib back-end)
- ``numpy``

Ces bibliothèques sont optionnelles : si elles ne sont pas installées,
``FaceComparator`` lève une ``RuntimeError`` à l'instanciation.
"""

import os
import tempfile
from typing import Optional

try:
    import face_recognition
    import numpy as np

    FACE_RECOGNITION_AVAILABLE = True
except ImportError:
    FACE_RECOGNITION_AVAILABLE = False


class FaceComparator:
    """Compare un visage source avec des visages cibles.

    Parameters
    ----------
    source_image_path:
        Chemin vers l'image de référence (JPEG, PNG…).
        L'image doit contenir exactement **un** visage détectable.
    tolerance:
        Seuil de distance en dessous duquel deux visages sont considérés
        identiques. Valeur par défaut : ``0.55``.

    Raises
    ------
    RuntimeError
        Si ``face_recognition`` n'est pas installé.
    ValueError
        Si aucun visage n'est détecté dans l'image source.
    """

    def __init__(self, source_image_path: str, tolerance: float = 0.55) -> None:
        if not FACE_RECOGNITION_AVAILABLE:
            raise RuntimeError(
                "La bibliothèque 'face_recognition' n'est pas installée.\n"
                "Installez-la avec : pip install face_recognition numpy Pillow"
            )

        self.tolerance = tolerance
        self.source_path = source_image_path

        self.source_image = face_recognition.load_image_file(source_image_path)
        self.source_encodings = face_recognition.face_encodings(self.source_image)

        if not self.source_encodings:
            raise ValueError(
                f"Aucun visage détecté dans l'image source : {source_image_path}"
            )

        self.source_encoding = self.source_encodings[0]

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def compare_with_image(self, target_image_path: str) -> dict:
        """Compare le visage source avec une image cible sur le disque.

        Parameters
        ----------
        target_image_path:
            Chemin vers l'image cible.

        Returns
        -------
        dict
            Dictionnaire avec les clés :

            - ``match`` (bool) : ``True`` si les visages correspondent.
            - ``distance`` (float) : distance euclidienne (0 = identique,
              1 = totalement différent).
            - ``confidence`` (float) : confiance en pourcentage
              (``(1 - distance) * 100``).
            - ``faces_found`` (int) : nombre de visages détectés dans
              l'image cible.
            - ``error`` (str | None) : message d'erreur si applicable.
        """
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

            best: dict = {
                "match": False,
                "distance": 1.0,
                "confidence": 0.0,
                "faces_found": len(target_encodings),
                "error": None,
            }

            for enc in target_encodings:
                dist: float = float(
                    face_recognition.face_distance([self.source_encoding], enc)[0]
                )
                is_match: bool = dist <= self.tolerance
                conf: float = max(0.0, 1.0 - dist) * 100

                if dist < best["distance"]:
                    best = {
                        "match": is_match,
                        "distance": round(dist, 4),
                        "confidence": round(conf, 2),
                        "faces_found": len(target_encodings),
                        "error": None,
                    }

            return best

        except Exception as exc:
            return {
                "match": False,
                "distance": 1.0,
                "confidence": 0.0,
                "faces_found": 0,
                "error": str(exc),
            }

    def compare_with_bytes(self, image_bytes: bytes) -> dict:
        """Compare le visage source avec une image fournie en bytes.

        Crée un fichier temporaire, délègue à :meth:`compare_with_image`,
        puis supprime le fichier temporaire.

        Parameters
        ----------
        image_bytes:
            Contenu binaire de l'image cible.

        Returns
        -------
        dict
            Même format que :meth:`compare_with_image`.
        """
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp.write(image_bytes)
            tmp_path = tmp.name
        try:
            return self.compare_with_image(tmp_path)
        finally:
            os.unlink(tmp_path)

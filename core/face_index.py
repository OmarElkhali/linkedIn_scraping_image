"""
core/face_index.py
==================
Index facial local : photo  →  profil LinkedIn.

Principe
--------
1. ``FaceIndex.build(photos_dir)``
     Encode chaque photo avec ``face_recognition`` (dlib).
     Sauvegarde les encodages + métadonnées dans ``index.pkl``.

2. ``FaceIndex.search(image_path_or_bytes, top_k)``
     Encode la photo cible → distance euclidienne avec chaque encodage.
     Retourne les ``top_k`` profils les plus proches triés par distance.

Pourquoi c'est fiable
---------------------
- ``face_recognition`` (dlib ResNet) produit un vecteur 128D par visage.
- La distance L2 entre deux vecteurs est < 0.6 pour le même individu.
- Aucune dépendance cloud — tout tourne localement.
"""

from __future__ import annotations

import os
import pickle
from pathlib import Path
from typing import Union

try:
    import face_recognition  # type: ignore
    import numpy as np
    FACE_RECOGNITION_AVAILABLE = True
except ImportError:
    FACE_RECOGNITION_AVAILABLE = False

from core.config import FACE_TOLERANCE


# ---------------------------------------------------------------------------
# Structure d'un résultat de recherche
# ---------------------------------------------------------------------------

class SearchResult:
    """Résultat d'une recherche faciale."""

    def __init__(
        self,
        photo_path: str,
        distance:   float,
        profile:    dict,
    ) -> None:
        self.photo_path = photo_path
        self.distance   = distance
        # Score de confiance [0–1] : 1 = identique, 0 = inconnu
        self.confidence = max(0.0, 1.0 - distance / FACE_TOLERANCE) if distance <= FACE_TOLERANCE else 0.0
        self.match      = distance <= FACE_TOLERANCE
        self.profile    = profile   # dict {url, nom, titre, ...}

    def to_dict(self) -> dict:
        return {
            "photo_path":  self.photo_path,
            "distance":    round(self.distance, 4),
            "confidence":  round(self.confidence, 4),
            "match":       self.match,
            **self.profile,
        }


# ---------------------------------------------------------------------------
# Index facial
# ---------------------------------------------------------------------------

class FaceIndex:
    """Construit et interroge un index facial à partir d'un dossier de photos.

    Parameters
    ----------
    index_path : str
        Chemin vers le fichier pickle de l'index (sera créé/mis à jour).
    """

    def __init__(self, index_path: str) -> None:
        self.index_path = index_path
        # Liste de (encoding_np, profile_dict, photo_path)
        self._entries: list[tuple] = []
        if os.path.isfile(index_path):
            self._load()

    # ── Construction de l'index ──────────────────────────────────────────────

    def build(
        self,
        profiles: list[dict],
        on_progress: callable = None,
    ) -> int:
        """Encode toutes les photos des profils et sauvegarde l'index.

        Parameters
        ----------
        profiles : list[dict]
            Liste de profils avec au minimum la clé ``photo_path``.
        on_progress : callable, optional
            ``fn(message: str)`` appelé à chaque avancement.

        Returns
        -------
        int
            Nombre de visages indexés.
        """
        if not FACE_RECOGNITION_AVAILABLE:
            raise RuntimeError(
                "face_recognition non installé — "
                "lancez : pip install face_recognition"
            )

        log = on_progress or (lambda _: None)
        total   = sum(1 for p in profiles if p.get("photo_path") and os.path.isfile(p["photo_path"]))
        indexed = 0
        errors  = 0

        self._entries = []

        for i, profile in enumerate(profiles):
            path = profile.get("photo_path", "")
            if not path or not os.path.isfile(path):
                continue

            try:
                img     = face_recognition.load_image_file(path)
                encs    = face_recognition.face_encodings(img)
                if not encs:
                    errors += 1
                    continue

                # Prend le premier visage détecté (le plus grand)
                self._entries.append((encs[0], profile, path))
                indexed += 1

                if indexed % 20 == 0 or indexed == total:
                    log(f"🔍 Indexation : {indexed}/{total} visages…")

            except Exception as exc:
                errors += 1
                log(f"⚠️  {os.path.basename(path)} : {exc}")

        self._save()
        log(f"✅ Index : {indexed} visages | {errors} erreurs | sauvegardé dans {self.index_path}")
        return indexed

    # ── Recherche faciale ────────────────────────────────────────────────────

    def search(
        self,
        source: Union[str, bytes],
        top_k: int = 5,
    ) -> list[SearchResult]:
        """Cherche les profils dont le visage est le plus proche de ``source``.

        Parameters
        ----------
        source : str | bytes
            Chemin vers une image OU contenu binaire d'une image.
        top_k : int
            Nombre de résultats à retourner (défaut 5).

        Returns
        -------
        list[SearchResult]
            Résultats triés du plus proche au plus éloigné.
        """
        if not FACE_RECOGNITION_AVAILABLE:
            raise RuntimeError("face_recognition non installé.")
        if not self._entries:
            raise ValueError("L'index est vide — lancez d'abord build().")

        # Charge et encode l'image source
        if isinstance(source, bytes):
            import numpy as np
            from PIL import Image
            import io
            img = np.array(Image.open(io.BytesIO(source)).convert("RGB"))
        else:
            img = face_recognition.load_image_file(source)

        query_encs = face_recognition.face_encodings(img)
        if not query_encs:
            return []

        query_enc = query_encs[0]

        # Calcul des distances avec tous les encodages de l'index
        import numpy as np
        known_encs = [e[0] for e in self._entries]
        distances  = face_recognition.face_distance(known_encs, query_enc)

        # Tri par distance croissante
        ranked = sorted(
            zip(distances, self._entries),
            key=lambda x: x[0],
        )

        results = []
        for dist, (_, profile, photo_path) in ranked[:top_k]:
            results.append(SearchResult(
                photo_path = photo_path,
                distance   = float(dist),
                profile    = profile,
            ))

        return results

    # ── Persistance ──────────────────────────────────────────────────────────

    def _save(self) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(self.index_path)), exist_ok=True)
        with open(self.index_path, "wb") as f:
            pickle.dump(self._entries, f, protocol=pickle.HIGHEST_PROTOCOL)

    def _load(self) -> None:
        try:
            with open(self.index_path, "rb") as f:
                self._entries = pickle.load(f)
        except Exception:
            self._entries = []

    def __len__(self) -> int:
        return len(self._entries)

    @property
    def size(self) -> int:
        return len(self._entries)

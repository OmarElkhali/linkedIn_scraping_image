"""
LinkedIn Scraper — Interface Streamlit.

Lancement
---------
    streamlit run app.py

Fonctionnalités
---------------
- **Onglet 1 — Recherche par Nom** : trouve les profils LinkedIn correspondant
  à un nom/prénom au sein d'une entreprise ou école.
- **Onglet 2 — Recherche par Profession** : trouve les profils LinkedIn
  correspondant à un intitulé de poste au sein d'une entreprise ou école.
- **Onglet 3 — Recherche par Visage** : télécharge une photo de référence,
  parcourt les profils trouvés et identifie la personne par reconnaissance
  faciale.
"""

from __future__ import annotations

import os
import tempfile

import streamlit as st

from core.config import FACE_MATCH_TOLERANCE, MAX_PROFILES_FOR_FACE_SEARCH
from core.face_comparator import FACE_RECOGNITION_AVAILABLE, FaceComparator
from core.scraper import scrape_linkedin_profile, search_linkedin_profiles
from scrapling.fetchers import Fetcher

# ---------------------------------------------------------------------------
# Configuration de la page Streamlit
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="LinkedIn Scraper",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# CSS personnalisé
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    .main-title {
        font-size: 2.4rem;
        font-weight: 700;
        color: #0A66C2;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        font-size: 1rem;
        color: #666;
        margin-bottom: 1.5rem;
    }
    .profile-card {
        background: #f9fafb;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 1.2rem 1.4rem;
        margin-bottom: 1rem;
    }
    .profile-card:hover {
        box-shadow: 0 4px 16px rgba(10, 102, 194, 0.12);
    }
    .profile-name {
        font-size: 1.1rem;
        font-weight: 600;
        color: #0A66C2;
    }
    .profile-meta {
        font-size: 0.85rem;
        color: #555;
        margin-top: 0.3rem;
    }
    .match-badge {
        display: inline-block;
        background: #16a34a;
        color: white;
        border-radius: 6px;
        padding: 2px 10px;
        font-size: 0.8rem;
        font-weight: 600;
        margin-left: 8px;
    }
    .no-match-badge {
        display: inline-block;
        background: #dc2626;
        color: white;
        border-radius: 6px;
        padding: 2px 10px;
        font-size: 0.8rem;
        font-weight: 600;
        margin-left: 8px;
    }
    .stProgress > div > div > div { background-color: #0A66C2; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# En-tête
# ---------------------------------------------------------------------------
st.markdown(
    '<p class="main-title">🔍 LinkedIn Scraper</p>'
    '<p class="sub-title">Recherchez des profils LinkedIn par nom, profession ou photo.</p>',
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Fonction utilitaire : rendu d'une carte profil
# ---------------------------------------------------------------------------
def _render_profile_card(profile: dict, face_result: dict | None = None) -> None:
    """Affiche une carte profil dans l'interface Streamlit.

    Parameters
    ----------
    profile:
        Dictionnaire de profil issu de ``search_linkedin_profiles`` ou
        ``scrape_linkedin_profile``.
    face_result:
        Résultat optionnel de la comparaison faciale avec les clés
        ``match`` (bool), ``confidence`` (float) et ``error`` (str|None).
    """
    name = profile.get("nom_complet") or profile.get("name") or "—"
    title = profile.get("titre_professionnel") or profile.get("snippet") or ""
    location = profile.get("localisation", "")
    url = profile.get("url", "#")
    company = profile.get("entreprise_actuelle") or profile.get("company_or_school", "")

    badge = ""
    if face_result is not None:
        conf = face_result.get("confidence", 0.0)
        if face_result.get("match"):
            badge = f'<span class="match-badge">✅ Match {conf:.1f}%</span>'
        else:
            badge = f'<span class="no-match-badge">❌ {conf:.1f}%</span>'

    meta_parts = [p for p in [title, company, location] if p]
    meta_html = " · ".join(meta_parts)

    st.markdown(
        f"""
        <div class="profile-card">
            <span class="profile-name">
                <a href="{url}" target="_blank"
                   style="text-decoration:none;color:#0A66C2;">{name}</a>
            </span>{badge}
            <div class="profile-meta">{meta_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Barre latérale — paramètres globaux
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Paramètres")
    max_results = st.slider(
        "Nombre max de résultats",
        min_value=3,
        max_value=50,
        value=10,
        step=1,
        help="Nombre de résultats Google à analyser.",
    )
    tolerance = st.slider(
        "Tolérance reconnaissance faciale",
        min_value=0.30,
        max_value=0.80,
        value=FACE_MATCH_TOLERANCE,
        step=0.05,
        format="%.2f",
        help=(
            "Distance maximale entre deux encodages pour considérer deux "
            "visages identiques. Plus la valeur est basse, plus la "
            "comparaison est stricte."
        ),
    )
    st.markdown("---")
    st.markdown(
        "**Aide**\n\n"
        "- 🏢 *Entreprise / École* : entité cible\n"
        "- 👤 *Nom/Prénom* : identité de la personne\n"
        "- 💼 *Profession* : intitulé de poste\n"
        "- 📷 *Photo* : référence pour la reconnaissance faciale\n"
    )

# ---------------------------------------------------------------------------
# Onglets principaux
# ---------------------------------------------------------------------------
tab_name, tab_job, tab_face = st.tabs(
    ["👤 Recherche par Nom", "💼 Recherche par Profession", "📷 Recherche par Visage"]
)

# ============================================================
# Onglet 1 — Recherche par Nom
# ============================================================
with tab_name:
    st.subheader("Recherche par Nom / Prénom")
    col1, col2 = st.columns(2)
    with col1:
        company_name = st.text_input(
            "🏢 Entreprise ou École",
            placeholder="ex. Google",
            key="name_company",
        )
    with col2:
        person_name = st.text_input(
            "👤 Nom / Prénom",
            placeholder="ex. John Doe",
            key="name_person",
        )

    if st.button("🔎 Rechercher", key="btn_name"):
        if not company_name or not person_name:
            st.warning("Veuillez renseigner l'entreprise/école et le nom.")
        else:
            log_area = st.empty()
            progress_bar = st.progress(0, text="Initialisation…")

            with st.spinner("Recherche en cours…"):
                try:
                    profiles = search_linkedin_profiles(
                        company_or_school=company_name,
                        search_type="nom_prenom",
                        search_value=person_name,
                        max_results=max_results,
                        progress_callback=lambda msg: log_area.info(msg),
                    )
                except Exception as exc:
                    st.error(f"Erreur lors de la recherche : {exc}")
                    profiles = []

            progress_bar.progress(100, text="Terminé")
            log_area.empty()

            if not profiles:
                st.info("Aucun profil trouvé. Essayez d'affiner votre recherche.")
            else:
                st.success(f"✅ {len(profiles)} profil(s) trouvé(s).")
                for p in profiles:
                    _render_profile_card(p)

# ============================================================
# Onglet 2 — Recherche par Profession
# ============================================================
with tab_job:
    st.subheader("Recherche par Profession / Poste")
    col1, col2 = st.columns(2)
    with col1:
        company_job = st.text_input(
            "🏢 Entreprise ou École",
            placeholder="ex. Meta",
            key="job_company",
        )
    with col2:
        job_title = st.text_input(
            "💼 Intitulé de poste",
            placeholder="ex. Software Engineer",
            key="job_title",
        )

    if st.button("🔎 Rechercher", key="btn_job"):
        if not company_job or not job_title:
            st.warning("Veuillez renseigner l'entreprise/école et l'intitulé de poste.")
        else:
            log_area_job = st.empty()
            progress_bar_job = st.progress(0, text="Initialisation…")

            with st.spinner("Recherche en cours…"):
                try:
                    profiles = search_linkedin_profiles(
                        company_or_school=company_job,
                        search_type="profession",
                        search_value=job_title,
                        max_results=max_results,
                        progress_callback=lambda msg: log_area_job.info(msg),
                    )
                except Exception as exc:
                    st.error(f"Erreur lors de la recherche : {exc}")
                    profiles = []

            progress_bar_job.progress(100, text="Terminé")
            log_area_job.empty()

            if not profiles:
                st.info("Aucun profil trouvé. Essayez d'affiner votre recherche.")
            else:
                st.success(f"✅ {len(profiles)} profil(s) trouvé(s).")
                for p in profiles:
                    _render_profile_card(p)

# ============================================================
# Onglet 3 — Recherche par Visage
# ============================================================
with tab_face:
    st.subheader("Recherche par Reconnaissance Faciale")

    if not FACE_RECOGNITION_AVAILABLE:
        st.error(
            "⚠️ La bibliothèque `face_recognition` n'est pas installée.\n\n"
            "```bash\npip install face_recognition numpy Pillow\n```"
        )
    else:
        col1, col2 = st.columns(2)
        with col1:
            company_face = st.text_input(
                "🏢 Entreprise ou École",
                placeholder="ex. Amazon",
                key="face_company",
            )
        with col2:
            uploaded_file = st.file_uploader(
                "📷 Photo de référence",
                type=["jpg", "jpeg", "png", "webp"],
                key="face_upload",
                help="Téléchargez une photo nette du visage à rechercher.",
            )

        if uploaded_file:
            st.image(uploaded_file, caption="Photo de référence", width=160)

        if st.button("🔎 Rechercher et comparer", key="btn_face"):
            if not company_face:
                st.warning("Veuillez renseigner l'entreprise/école.")
            elif not uploaded_file:
                st.warning("Veuillez télécharger une photo de référence.")
            else:
                log_area_face = st.empty()
                progress_bar_face = st.progress(0, text="Initialisation…")

                # Sauvegarde temporaire de la photo source
                with tempfile.NamedTemporaryFile(
                    suffix=".jpg", delete=False
                ) as tmp_src:
                    tmp_src.write(uploaded_file.getvalue())
                    src_path = tmp_src.name

                try:
                    comparator = FaceComparator(src_path, tolerance=tolerance)
                except ValueError as exc:
                    st.error(str(exc))
                    os.unlink(src_path)
                    st.stop()

                # 1) Recherche des profils
                log_area_face.info("🔍 Recherche des profils LinkedIn…")
                progress_bar_face.progress(10, text="Recherche des profils…")
                try:
                    face_profiles = search_linkedin_profiles(
                        company_or_school=company_face,
                        search_type="image",
                        search_value="",
                        max_results=min(max_results, MAX_PROFILES_FOR_FACE_SEARCH),
                    )
                except Exception as exc:
                    st.error(f"Erreur lors de la recherche : {exc}")
                    os.unlink(src_path)
                    st.stop()

                if not face_profiles:
                    st.info("Aucun profil trouvé pour cette entreprise/école.")
                    os.unlink(src_path)
                    st.stop()

                st.info(f"📋 {len(face_profiles)} profil(s) à analyser…")

                # 2) Scraping + comparaison faciale
                face_results: list[dict] = []
                for i, p in enumerate(face_profiles):
                    pct = 10 + int(85 * (i + 1) / len(face_profiles))
                    progress_bar_face.progress(
                        pct, text=f"Analyse {i + 1}/{len(face_profiles)}…"
                    )
                    log_area_face.info(
                        f"🔄 Scraping : {p.get('name', p['url'])}"
                    )

                    try:
                        detail = scrape_linkedin_profile(p["url"], download_photo=True)
                    except Exception:
                        detail = {**p, "photo_locale": "", "photo_profil_url": ""}

                    face_cmp: dict = {
                        "match": False,
                        "confidence": 0.0,
                        "error": "Pas de photo",
                    }

                    if detail.get("photo_locale"):
                        face_cmp = comparator.compare_with_image(
                            detail["photo_locale"]
                        )
                    elif detail.get("photo_profil_url"):
                        try:
                            resp = Fetcher.get(
                                detail["photo_profil_url"], stealthy_headers=True
                            )
                            if hasattr(resp, "content") and resp.content:
                                face_cmp = comparator.compare_with_bytes(resp.content)
                        except Exception as exc:
                            face_cmp["error"] = str(exc)

                    face_results.append({**detail, "face": face_cmp})

                os.unlink(src_path)
                progress_bar_face.progress(100, text="Terminé")
                log_area_face.empty()

                # 3) Résultats triés (meilleures correspondances en premier)
                face_results.sort(
                    key=lambda r: r["face"].get("confidence", 0.0), reverse=True
                )

                matches = [r for r in face_results if r["face"].get("match")]
                if matches:
                    st.success(f"✅ {len(matches)} correspondance(s) trouvée(s) !")
                else:
                    st.warning(
                        "Aucune correspondance exacte. Résultats triés par proximité :"
                    )

                for r in face_results:
                    _render_profile_card(r, face_result=r["face"])

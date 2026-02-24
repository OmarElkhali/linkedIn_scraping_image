"""
LinkedIn Scraper — Interface Streamlit.

Lancement
---------
    python3 -m streamlit run app.py

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
# CSS personnalisé — design moderne
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    /* ---------- Variables ---------- */
    :root {
        --primary: #0A66C2;
        --primary-light: #e8f1fb;
        --success: #16a34a;
        --danger: #dc2626;
        --surface: #ffffff;
        --surface-alt: #f3f6f9;
        --text: #1a1a2e;
        --text-muted: #6b7280;
        --border: #e2e8f0;
        --shadow: 0 2px 12px rgba(10,102,194,0.08);
        --radius: 14px;
    }

    /* ---------- Header ---------- */
    .app-header {
        background: linear-gradient(135deg, #0A66C2 0%, #004182 100%);
        color: #fff;
        padding: 2rem 2.5rem;
        border-radius: var(--radius);
        margin-bottom: 1.8rem;
        text-align: center;
    }
    .app-header h1 {
        font-size: 2.4rem;
        font-weight: 800;
        margin: 0;
        letter-spacing: -0.5px;
    }
    .app-header p {
        font-size: 1.05rem;
        opacity: 0.9;
        margin: 0.5rem 0 0;
    }

    /* ---------- Stats row ---------- */
    .stat-card {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 10px;
        padding: 1rem 1.2rem;
        text-align: center;
    }
    .stat-card .stat-val {
        font-size: 1.6rem;
        font-weight: 700;
        color: var(--primary);
    }
    .stat-card .stat-lbl {
        font-size: 0.82rem;
        color: var(--text-muted);
    }

    /* ---------- Profile card ---------- */
    .profile-card {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: var(--radius);
        padding: 1.2rem 1.5rem;
        margin-bottom: 0.9rem;
        transition: box-shadow 0.2s, transform 0.15s;
        display: flex;
        align-items: center;
        gap: 1rem;
    }
    .profile-card:hover {
        box-shadow: var(--shadow);
        transform: translateY(-1px);
    }
    .profile-avatar {
        width: 56px;
        height: 56px;
        border-radius: 50%;
        object-fit: cover;
        border: 2px solid var(--primary-light);
        flex-shrink: 0;
        background: var(--surface-alt);
    }
    .profile-info { flex: 1; min-width: 0; }
    .profile-name {
        font-size: 1.05rem;
        font-weight: 600;
        color: var(--primary);
        text-decoration: none;
        display: inline-block;
    }
    .profile-name:hover { text-decoration: underline; }
    .profile-meta {
        font-size: 0.83rem;
        color: var(--text-muted);
        margin-top: 0.2rem;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .match-badge {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        background: var(--success);
        color: #fff;
        border-radius: 6px;
        padding: 3px 10px;
        font-size: 0.78rem;
        font-weight: 700;
        margin-left: 8px;
        white-space: nowrap;
    }
    .no-match-badge {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        background: var(--danger);
        color: #fff;
        border-radius: 6px;
        padding: 3px 10px;
        font-size: 0.78rem;
        font-weight: 700;
        margin-left: 8px;
        white-space: nowrap;
    }
    .pending-badge {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        background: #d97706;
        color: #fff;
        border-radius: 6px;
        padding: 3px 10px;
        font-size: 0.78rem;
        font-weight: 700;
        margin-left: 8px;
        white-space: nowrap;
    }

    /* ---------- Progress ---------- */
    .stProgress > div > div > div { background-color: var(--primary); }

    /* ---------- Tabs ---------- */
    .stTabs [data-baseweb="tab-list"] { gap: 0; }
    .stTabs [data-baseweb="tab"] {
        padding: 12px 24px;
        font-weight: 600;
        font-size: 0.92rem;
    }

    /* ---------- Sidebar ---------- */
    .sidebar-section {
        background: var(--surface-alt);
        border-radius: 10px;
        padding: 1rem;
        margin-bottom: 1rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# En-tête
# ---------------------------------------------------------------------------
st.markdown(
    """
    <div class="app-header">
        <h1>🔍 LinkedIn Scraper</h1>
        <p>Trouvez des profils LinkedIn par nom, profession ou reconnaissance faciale</p>
    </div>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Utilitaire : rendu d'une carte profil
# ---------------------------------------------------------------------------
def _render_profile_card(
    profile: dict,
    face_result: dict | None = None,
    show_photo: bool = False,
) -> None:
    """Affiche une carte profil dans l'interface Streamlit."""
    name = profile.get("nom_complet") or profile.get("name") or "—"
    title = profile.get("titre_professionnel") or profile.get("snippet") or ""
    location = profile.get("localisation", "")
    url = profile.get("url", "#")
    company = (
        profile.get("entreprise_actuelle") or profile.get("company_or_school", "")
    )
    photo_url = profile.get("photo_profil_url", "")

    badge = ""
    if face_result is not None:
        conf = face_result.get("confidence", 0.0)
        if face_result.get("match"):
            badge = f'<span class="match-badge">✅ Match {conf:.1f}%</span>'
        elif face_result.get("error") == "Pas de photo":
            badge = '<span class="pending-badge">📷 Pas de photo</span>'
        else:
            badge = f'<span class="no-match-badge">❌ {conf:.1f}%</span>'

    meta_parts = [p for p in [title, company, location] if p]
    meta_html = " · ".join(meta_parts)

    avatar_html = ""
    if show_photo and photo_url:
        avatar_html = (
            f'<img class="profile-avatar" src="{photo_url}" '
            f'alt="{name}" onerror="this.style.display=\'none\'">'
        )
    elif show_photo:
        avatar_html = (
            '<div class="profile-avatar" style="display:flex;align-items:center;'
            'justify-content:center;font-size:1.4rem;color:#aaa;">👤</div>'
        )

    st.markdown(
        f"""
        <div class="profile-card">
            {avatar_html}
            <div class="profile-info">
                <a class="profile-name" href="{url}" target="_blank">{name}</a>
                {badge}
                <div class="profile-meta">{meta_html}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Utilitaire : stats
# ---------------------------------------------------------------------------
def _render_stats(total: int, matches: int = 0, show_matches: bool = False) -> None:
    """Affiche une barre de statistiques."""
    if show_matches:
        cols = st.columns(3)
        with cols[0]:
            st.markdown(
                f'<div class="stat-card"><div class="stat-val">{total}</div>'
                f'<div class="stat-lbl">Profils analysés</div></div>',
                unsafe_allow_html=True,
            )
        with cols[1]:
            st.markdown(
                f'<div class="stat-card"><div class="stat-val">'
                f'{"✅ " + str(matches) if matches else "0"}</div>'
                f'<div class="stat-lbl">Correspondances</div></div>',
                unsafe_allow_html=True,
            )
        with cols[2]:
            rate = round(matches / total * 100, 1) if total else 0
            st.markdown(
                f'<div class="stat-card"><div class="stat-val">{rate}%</div>'
                f'<div class="stat-lbl">Taux de match</div></div>',
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            f'<div class="stat-card" style="display:inline-block;margin-bottom:1rem;">'
            f'<div class="stat-val">{total}</div>'
            f'<div class="stat-lbl">Profils trouvés</div></div>',
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Barre latérale — paramètres globaux
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## ⚙️ Paramètres")
    st.markdown('<div class="sidebar-section">', unsafe_allow_html=True)
    max_results = st.number_input(
        "📊 Nombre max de résultats",
        min_value=5,
        max_value=10000,
        value=100,
        step=50,
        help="Nombre de profils à collecter depuis Google (pagination automatique).",
    )
    tolerance = st.slider(
        "🎯 Tolérance faciale",
        min_value=0.30,
        max_value=0.80,
        value=FACE_MATCH_TOLERANCE,
        step=0.05,
        format="%.2f",
        help=(
            "Seuil de distance faciale. Plus la valeur est basse, "
            "plus la comparaison est stricte. Recommandé : 0.50-0.60"
        ),
    )
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("---")
    st.markdown(
        "### 💡 Guide rapide\n"
        "1. Choisissez un onglet de recherche\n"
        "2. Renseignez l'entreprise / école\n"
        "3. Ajoutez le critère (nom, poste, ou photo)\n"
        "4. Cliquez sur **Rechercher**\n\n"
        "Pour la **recherche par visage** :\n"
        "- Utilisez une photo nette de face\n"
        "- Ajustez la tolérance si nécessaire\n"
        "- Plus de résultats = plus de chances"
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
    st.markdown("### 👤 Recherche par Nom / Prénom")
    st.caption("Trouvez une personne spécifique au sein d'une entreprise ou école.")

    col1, col2 = st.columns(2)
    with col1:
        company_name = st.text_input(
            "🏢 Entreprise ou École",
            placeholder="ex. Google, MIT…",
            key="name_company",
        )
    with col2:
        person_name = st.text_input(
            "👤 Nom / Prénom",
            placeholder="ex. John Doe",
            key="name_person",
        )

    if st.button("🔎 Rechercher", key="btn_name", type="primary", use_container_width=True):
        if not company_name or not person_name:
            st.warning("⚠️ Veuillez renseigner l'entreprise/école **et** le nom.")
        else:
            from core.scraper import search_linkedin_profiles

            log_area = st.empty()
            progress_bar = st.progress(0, text="🔄 Initialisation…")

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
                    st.error(f"❌ Erreur lors de la recherche : {exc}")
                    profiles = []

            progress_bar.progress(100, text="✅ Terminé")
            log_area.empty()

            if not profiles:
                st.info("🔍 Aucun profil trouvé. Essayez d'affiner votre recherche.")
            else:
                _render_stats(len(profiles))
                for p in profiles:
                    _render_profile_card(p)

# ============================================================
# Onglet 2 — Recherche par Profession
# ============================================================
with tab_job:
    st.markdown("### 💼 Recherche par Profession / Poste")
    st.caption("Trouvez des personnes par intitulé de poste au sein d'une organisation.")

    col1, col2 = st.columns(2)
    with col1:
        company_job = st.text_input(
            "🏢 Entreprise ou École",
            placeholder="ex. Meta, Stanford…",
            key="job_company",
        )
    with col2:
        job_title = st.text_input(
            "💼 Intitulé de poste",
            placeholder="ex. Software Engineer, CEO…",
            key="job_title",
        )

    if st.button("🔎 Rechercher", key="btn_job", type="primary", use_container_width=True):
        if not company_job or not job_title:
            st.warning("⚠️ Veuillez renseigner l'entreprise/école **et** l'intitulé de poste.")
        else:
            from core.scraper import search_linkedin_profiles

            log_area_job = st.empty()
            progress_bar_job = st.progress(0, text="🔄 Initialisation…")

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
                    st.error(f"❌ Erreur lors de la recherche : {exc}")
                    profiles = []

            progress_bar_job.progress(100, text="✅ Terminé")
            log_area_job.empty()

            if not profiles:
                st.info("🔍 Aucun profil trouvé. Essayez d'affiner votre recherche.")
            else:
                _render_stats(len(profiles))
                for p in profiles:
                    _render_profile_card(p)

# ============================================================
# Onglet 3 — Recherche par Visage
# ============================================================
with tab_face:
    st.markdown("### 📷 Reconnaissance Faciale")
    st.caption(
        "Téléchargez une photo, et l'outil comparera le visage avec les profils "
        "LinkedIn trouvés pour identifier la personne."
    )

    # Vérification de face_recognition
    from core.face_comparator import FACE_RECOGNITION_AVAILABLE

    if not FACE_RECOGNITION_AVAILABLE:
        st.error(
            "⚠️ La bibliothèque `face_recognition` n'est pas installée.\n\n"
            "```bash\npip install face_recognition numpy Pillow\n```"
        )
        st.stop()

    col_left, col_right = st.columns([1, 2])

    with col_left:
        st.markdown("#### 📤 Photo de référence")
        uploaded_file = st.file_uploader(
            "Téléchargez une photo nette du visage",
            type=["jpg", "jpeg", "png", "webp"],
            key="face_upload",
            label_visibility="collapsed",
        )
        if uploaded_file:
            st.image(uploaded_file, caption="Photo de référence", use_container_width=True)

    with col_right:
        st.markdown("#### 🏢 Critères de recherche")
        company_face = st.text_input(
            "Entreprise ou École",
            placeholder="ex. Amazon, Harvard…",
            key="face_company",
        )
        st.markdown("")  # spacer

        search_clicked = st.button(
            "🔎 Rechercher et comparer les visages",
            key="btn_face",
            type="primary",
            use_container_width=True,
        )

    if search_clicked:
        if not company_face:
            st.warning("⚠️ Veuillez renseigner l'entreprise/école.")
        elif not uploaded_file:
            st.warning("⚠️ Veuillez télécharger une photo de référence.")
        else:
            from core.face_comparator import FaceComparator
            from core.scraper import scrape_linkedin_profile, search_linkedin_profiles

            log_area_face = st.empty()
            progress_bar_face = st.progress(0, text="🔄 Initialisation…")

            # -- Sauvegarde temporaire de la photo source --
            with tempfile.NamedTemporaryFile(
                suffix=".jpg", delete=False
            ) as tmp_src:
                tmp_src.write(uploaded_file.getvalue())
                src_path = tmp_src.name

            try:
                comparator = FaceComparator(src_path, tolerance=tolerance)
            except ValueError as exc:
                st.error(f"❌ {exc}")
                os.unlink(src_path)
                st.stop()

            # -- 1) Recherche des profils --
            log_area_face.info("🔍 Recherche des profils LinkedIn…")
            progress_bar_face.progress(5, text="📄 Collecte des profils…")

            try:
                face_profiles = search_linkedin_profiles(
                    company_or_school=company_face,
                    search_type="image",
                    search_value="",
                    max_results=min(max_results, MAX_PROFILES_FOR_FACE_SEARCH),
                    progress_callback=lambda msg: log_area_face.info(msg),
                )
            except Exception as exc:
                st.error(f"❌ Erreur lors de la recherche : {exc}")
                os.unlink(src_path)
                st.stop()

            if not face_profiles:
                st.info("🔍 Aucun profil trouvé pour cette entreprise/école.")
                os.unlink(src_path)
                st.stop()

            progress_bar_face.progress(15, text="📋 Profils collectés")
            st.info(f"📋 **{len(face_profiles)}** profil(s) à analyser — comparaison faciale en cours…")

            # -- 2) Scraping + comparaison faciale --
            face_results: list[dict] = []
            results_container = st.container()

            for i, p in enumerate(face_profiles):
                pct = 15 + int(80 * (i + 1) / len(face_profiles))
                progress_bar_face.progress(
                    min(pct, 95),
                    text=f"🔄 Analyse {i + 1}/{len(face_profiles)} — {p.get('name', '…')}",
                )
                log_area_face.info(f"🔄 Scraping : {p.get('name', p['url'])}")

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
                    face_cmp = comparator.compare_with_image(detail["photo_locale"])
                elif detail.get("photo_profil_url"):
                    try:
                        import urllib.request

                        req = urllib.request.Request(
                            detail["photo_profil_url"],
                            headers={
                                "User-Agent": (
                                    "Mozilla/5.0 (X11; Linux x86_64) "
                                    "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
                                )
                            },
                        )
                        with urllib.request.urlopen(req, timeout=10) as resp:
                            img_bytes = resp.read()
                        if img_bytes:
                            face_cmp = comparator.compare_with_bytes(img_bytes)
                    except Exception as exc:
                        face_cmp["error"] = str(exc)

                face_results.append({**detail, "face": face_cmp})

                # Affiche un match dès qu'il est trouvé
                if face_cmp.get("match"):
                    with results_container:
                        st.success(
                            f"🎯 **Match trouvé !** — {detail.get('nom_complet', p.get('name', ''))}"
                            f" — Confiance : {face_cmp['confidence']:.1f}%"
                        )

            os.unlink(src_path)
            progress_bar_face.progress(100, text="✅ Analyse terminée")
            log_area_face.empty()

            # -- 3) Résultats triés --
            face_results.sort(
                key=lambda r: r["face"].get("confidence", 0.0), reverse=True
            )

            matches = [r for r in face_results if r["face"].get("match")]
            _render_stats(
                total=len(face_results),
                matches=len(matches),
                show_matches=True,
            )

            if matches:
                st.markdown("---")
                st.markdown("#### ✅ Correspondances trouvées")
                for r in matches:
                    _render_profile_card(r, face_result=r["face"], show_photo=True)

                if len(face_results) > len(matches):
                    with st.expander(
                        f"Voir les {len(face_results) - len(matches)} autres profils"
                    ):
                        for r in face_results:
                            if not r["face"].get("match"):
                                _render_profile_card(
                                    r, face_result=r["face"], show_photo=True
                                )
            else:
                st.warning(
                    "⚠️ Aucune correspondance exacte. "
                    "Essayez d'augmenter la tolérance ou le nombre de résultats."
                )
                st.markdown("#### Résultats triés par proximité :")
                for r in face_results:
                    _render_profile_card(r, face_result=r["face"], show_photo=True)

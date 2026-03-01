"""
LinkedIn Photo Scraper — Interface Streamlit v3.

Deux onglets :
  🎓 Collecte  → scrape les photos de tous les membres d'une école / entreprise.
  🔍 Visage    → retrouve un profil LinkedIn depuis une photo (reverse face search).
"""
from __future__ import annotations

import csv
import io
import os
import re
import time
import zipfile

import streamlit as st

from core.linkedin_scraper import LinkedInScraper
from core.face_index import FaceIndex, FACE_RECOGNITION_AVAILABLE
from core.config import OUTPUT_DIR, FACE_TOLERANCE

# ─── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="LinkedIn Photo Scraper",
    page_icon="🔍",
    layout="wide",
)

# ─── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
body,[data-testid="stApp"]{background:#0f172a;color:#e2e8f0}
[data-testid="stSidebar"]{background:#1e293b}
h1,h2,h3{color:#f1f5f9}
.stTabs [data-baseweb="tab"]{color:#94a3b8;font-size:.95rem}
.stTabs [aria-selected="true"]{color:#60a5fa;border-bottom:2px solid #60a5fa}
.sec{font-size:1.3rem;font-weight:700;color:#60a5fa;margin:1rem 0 .5rem}
.chips{display:flex;gap:10px;flex-wrap:wrap;margin:.6rem 0}
.chip{background:#1e293b;border:1px solid #334155;border-radius:9px;
      padding:10px 16px;min-width:90px;text-align:center}
.chip .v{font-size:1.5rem;font-weight:700;color:#60a5fa}
.chip .l{font-size:.7rem;color:#94a3b8;margin-top:2px}
.card{background:#1e293b;border:1px solid #334155;border-radius:12px;
      padding:12px 16px;margin:6px 0;display:flex;gap:12px;align-items:center}
.card img{width:52px;height:52px;border-radius:50%;object-fit:cover;border:2px solid #334155}
.card .nm{font-weight:700;font-size:.95rem;color:#f1f5f9}
.card .ti{font-size:.82rem;color:#94a3b8}
.card a{font-size:.78rem;color:#60a5fa;text-decoration:none}
.ok{border-color:#16a34a}
.tip{background:#1e3a5f;border:1px solid #1d4ed8;border-radius:8px;
     padding:10px 14px;font-size:.85rem;margin:.5rem 0;color:#bfdbfe}
.warn{background:#422006;border:1px solid #92400e;border-radius:8px;
      padding:10px 14px;font-size:.85rem;margin:.5rem 0;color:#fed7aa}
</style>
""", unsafe_allow_html=True)

# ─── Session state ─────────────────────────────────────────────────────────────
for k, v in {
    "profiles":    [],
    "collect_dir": "",
    "entity_url":  "",
    "index_path":  "",
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ─── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Paramètres")
    face_tol = st.slider(
        "Tolérance faciale",
        min_value=0.30, max_value=0.70, value=FACE_TOLERANCE, step=0.01,
        help="0.4 = strict · 0.6 = souple",
    )
    top_k = st.slider("Résultats top-K", 1, 20, 5)
    st.markdown("---")
    st.markdown(
        "**Comment obtenir `li_at` ?**\n\n"
        "1. Connectez-vous sur LinkedIn\n"
        "2. F12 → Application → Cookies → `https://www.linkedin.com`\n"
        "3. Copiez la valeur du cookie **`li_at`**",
    )

# ─── Tabs ─────────────────────────────────────────────────────────────────────
tab_collect, tab_face = st.tabs(["🎓 Collecte de photos", "🔍 Recherche par visage"])


# ══════════════════════════════════════════════════════════════════════════════
# ONGLET 1 — COLLECTE
# ══════════════════════════════════════════════════════════════════════════════
with tab_collect:
    st.markdown('<div class="sec">🎓 Collecte de photos LinkedIn</div>', unsafe_allow_html=True)

    st.markdown(
        '<div class="tip">💡 Accès direct à la page <code>/people/</code> de l\'école '
        'ou entreprise via votre session LinkedIn. Aucune limite Google.</div>',
        unsafe_allow_html=True,
    )

    # ── Formulaire ────────────────────────────────────────────────────────────
    c1, c2 = st.columns([3, 1])
    with c1:
        entity_url = st.text_input(
            "🔗 URL LinkedIn",
            value="https://www.linkedin.com/school/ensam-casablanca/",
            help="URL école : .../school/slug/  |  URL entreprise : .../company/slug/",
            key="in_url",
        )
    with c2:
        max_p = st.number_input("Max profils", 10, 10000, 200, 50, key="in_max")

    li_at = st.text_input(
        "🍪 Cookie li_at",
        type="password",
        placeholder="AQEDATs4…",
        key="in_li_at",
        help="Votre cookie de session LinkedIn (voir sidebar).",
    )

    slug = re.sub(r"[^\w\-]", "_", entity_url.rstrip("/").split("/")[-1] or "entity")[:40]
    default_dir = os.path.join(OUTPUT_DIR, slug)
    out_dir = st.text_input("📂 Dossier de sortie", value=default_dir, key="in_out")

    if max_p > 300:
        eta = round(max_p * 3 / 60)
        st.markdown(
            f'<div class="warn">⏱️ ~{eta} min estimées pour {max_p} profils.</div>',
            unsafe_allow_html=True,
        )

    go = st.button("🚀 Lancer la collecte", type="primary", key="btn_go")

    if go:
        if not li_at:
            st.error("❌ Cookie li_at requis.")
        elif not entity_url:
            st.warning("Renseignez l'URL LinkedIn.")
        else:
            prog  = st.progress(0, text="Connexion…")
            stats = st.empty()
            log   = st.empty()
            msgs: list[str] = []

            def cb(msg: str) -> None:
                msgs.append(msg)
                log.info(msgs[-1])

            prog.progress(5, text="Initialisation du navigateur…")

            scraper = LinkedInScraper(
                li_at        = li_at,
                output_dir   = out_dir,
                max_profiles = int(max_p),
                on_progress  = cb,
            )

            t0 = time.time()
            profiles = scraper.scrape(entity_url)
            elapsed  = time.time() - t0

            prog.progress(100, text=f"✅ Terminé en {elapsed:.0f}s")
            log.empty()

            n_ok  = sum(1 for p in profiles if p.photo_path)
            n_err = len(profiles) - n_ok

            stats.markdown(
                f'<div class="chips">'
                f'<div class="chip"><div class="v">{len(profiles)}</div><div class="l">Profils</div></div>'
                f'<div class="chip"><div class="v" style="color:#4ade80">{n_ok}</div><div class="l">Photos</div></div>'
                f'<div class="chip"><div class="v" style="color:#f87171">{n_err}</div><div class="l">Sans photo</div></div>'
                f'<div class="chip"><div class="v">{round(n_ok/len(profiles)*100) if profiles else 0}%</div><div class="l">Couverture</div></div>'
                f'</div>',
                unsafe_allow_html=True,
            )

            raw = [p.to_dict() for p in profiles]
            st.session_state["profiles"]    = raw
            st.session_state["collect_dir"] = out_dir
            st.session_state["entity_url"]  = entity_url
            st.session_state["index_path"]  = os.path.join(out_dir, "face_index.pkl")

    # ── Résultats ─────────────────────────────────────────────────────────────
    profiles = st.session_state.get("profiles", [])
    saved_dir = st.session_state.get("collect_dir", "")

    if profiles:
        n_ok = sum(1 for p in profiles if p.get("photo_path"))
        st.success(f"✅ {n_ok} photos dans `{saved_dir}`")

        # ── Exports ───────────────────────────────────────────────────────────
        ea, eb, ec, _ = st.columns([1, 1, 1.5, 3])

        with ea:
            csv_buf = io.StringIO()
            wr = csv.DictWriter(csv_buf, fieldnames=list(profiles[0].keys()), extrasaction="ignore")
            wr.writeheader(); wr.writerows(profiles)
            st.download_button("⬇️ CSV", csv_buf.getvalue(),
                               file_name=f"{slug}.csv", mime="text/csv", key="dl_csv")

        with eb:
            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for p in profiles:
                    pp = p.get("photo_path", "")
                    if pp and os.path.isfile(pp):
                        zf.write(pp, os.path.basename(pp))
            zip_buf.seek(0)
            st.download_button("⬇️ ZIP photos", zip_buf.getvalue(),
                               file_name=f"{slug}_photos.zip", mime="application/zip", key="dl_zip")

        with ec:
            if FACE_RECOGNITION_AVAILABLE:
                if st.button("🧠 Construire l'index facial", key="btn_index"):
                    idx_path = st.session_state.get("index_path",
                                os.path.join(saved_dir, "face_index.pkl"))
                    idx = FaceIndex(idx_path)
                    log2 = st.empty()
                    n = idx.build(profiles, on_progress=lambda m: log2.info(m))
                    log2.empty()
                    st.success(f"🧠 Index : {n} visages indexés → `{idx_path}`")
            else:
                st.warning("face_recognition non installé")

        # ── Galerie ───────────────────────────────────────────────────────────
        st.markdown('<div class="sec">🖼️ Galerie</div>', unsafe_allow_html=True)

        ok_p = [p for p in profiles if p.get("photo_path") and os.path.isfile(p["photo_path"])]
        COLS = 5
        for i in range(0, len(ok_p), COLS):
            row = ok_p[i:i+COLS]
            cols = st.columns(COLS)
            for col, p in zip(cols, row):
                with col:
                    try:
                        st.image(p["photo_path"], use_container_width=True,
                                 caption=f"{p.get('nom','')[:20]}")
                    except Exception:
                        st.markdown("👤")

        # Profils sans photo
        bad = [p for p in profiles if not p.get("photo_path")]
        if bad:
            with st.expander(f"⚠️ {len(bad)} profils sans photo"):
                for p in bad:
                    st.write(f"- [{p.get('nom') or p['url']}]({p['url']}) — {p.get('error','')}")


# ══════════════════════════════════════════════════════════════════════════════
# ONGLET 2 — RECHERCHE PAR VISAGE
# ══════════════════════════════════════════════════════════════════════════════
with tab_face:
    st.markdown('<div class="sec">🔍 Recherche par visage → profil LinkedIn</div>', unsafe_allow_html=True)

    if not FACE_RECOGNITION_AVAILABLE:
        st.error(
            "❌ `face_recognition` n'est pas installé.\n\n"
            "```bash\npip install face_recognition\n```"
        )
        st.stop()

    # ── Sélection de l'index ──────────────────────────────────────────────────
    st.markdown('<div class="sec" style="font-size:1rem">Index facial</div>', unsafe_allow_html=True)

    idx_default = st.session_state.get("index_path", "")
    idx_path = st.text_input(
        "Chemin vers l'index (.pkl)",
        value=idx_default,
        placeholder="output/ensam-casablanca/face_index.pkl",
        key="in_idx_path",
    )

    # Charge l'index si existe
    face_idx: FaceIndex | None = None
    if idx_path and os.path.isfile(idx_path):
        face_idx = FaceIndex(idx_path)
        st.success(f"✅ Index chargé — {face_idx.size} visages")
    elif idx_path:
        st.warning("Index introuvable — lancez d'abord la collecte et construisez l'index.")

    st.markdown("---")

    # ── Upload photo cible ────────────────────────────────────────────────────
    st.markdown('<div class="sec" style="font-size:1rem">Photo à rechercher</div>', unsafe_allow_html=True)

    uploaded = st.file_uploader(
        "Chargez une photo (JPG / PNG)",
        type=["jpg", "jpeg", "png", "webp"],
        key="up_face",
    )

    if uploaded and face_idx:
        img_bytes = uploaded.read()

        c1, c2 = st.columns([1, 3])
        with c1:
            st.image(img_bytes, caption="Photo cible", width=160)

        with c2:
            with st.spinner("Analyse faciale…"):
                try:
                    results = face_idx.search(img_bytes, top_k=int(top_k))
                except Exception as exc:
                    st.error(f"Erreur : {exc}")
                    results = []

            if not results:
                st.warning("Aucun visage détecté dans la photo ou index vide.")
            else:
                matches = [r for r in results if r.match]
                if matches:
                    st.success(f"🎯 {len(matches)} correspondance(s) trouvée(s) !")
                else:
                    st.info("Aucune correspondance exacte — profils les plus proches :")

        # ── Cartes résultats ──────────────────────────────────────────────────
        st.markdown('<div class="sec" style="font-size:1rem">Résultats</div>', unsafe_allow_html=True)

        for r in results:
            p    = r.profile
            cls  = "card ok" if r.match else "card"
            nom  = p.get("nom", "—") or "—"
            titre = p.get("titre", "") or ""
            url  = p.get("url", "#")
            conf = f"{r.confidence*100:.0f}%"
            dist = f"{r.distance:.3f}"

            # Miniature
            thumb_html = ""
            if r.photo_path and os.path.isfile(r.photo_path):
                import base64
                with open(r.photo_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                thumb_html = f'<img src="data:image/jpeg;base64,{b64}" />'
            else:
                thumb_html = "<div style='width:52px;height:52px;border-radius:50%;background:#334155;display:flex;align-items:center;justify-content:center;font-size:1.4rem'>👤</div>"

            badge = "🟢" if r.match else "🔵"
            st.markdown(
                f'<div class="{cls}">'
                f'  {thumb_html}'
                f'  <div class="info" style="flex:1">'
                f'    <div class="nm">{badge} {nom}</div>'
                f'    <div class="ti">{titre}</div>'
                f'    <div class="url"><a href="{url}" target="_blank">Voir le profil LinkedIn →</a></div>'
                f'  </div>'
                f'  <div style="text-align:right">'
                f'    <div style="font-size:1.3rem;font-weight:700;color:{"#4ade80" if r.match else "#60a5fa"}">{conf}</div>'
                f'    <div style="font-size:.72rem;color:#64748b">dist {dist}</div>'
                f'  </div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    elif uploaded and not face_idx:
        st.warning("Chargez d'abord un index facial valide.")

import streamlit as st
import pandas as pd
import sys
import os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.styles import CSS, WEDDING_DATE_STR, LOCATION, nav_bar
from utils.sheets import get_all_rsvps, storage_mode

st.set_page_config(page_title="Admin — Adakou & Ata-Sé", page_icon="🔐", layout="wide", initial_sidebar_state="collapsed")
st.markdown(CSS, unsafe_allow_html=True)

# ── AUTH ──────────────────────────────────────────────────────────────────────
ADMIN_PWD = st.secrets.get("admin_password", "lolo2026")

if "admin_ok" not in st.session_state:
    st.session_state.admin_ok = False

if not st.session_state.admin_ok:
    st.markdown("""
    <div style="max-width:400px;margin:80px auto;padding:0 24px;">
        <div style="background:white;border-radius:16px;padding:44px;
                    box-shadow:0 4px 30px rgba(0,0,0,0.1);text-align:center;">
            <div style="font-size:2.5rem;margin-bottom:16px;">🔐</div>
            <h2 style="font-family:'Cormorant Garamond',serif;font-size:1.8rem;
                       color:#2c2416;margin-bottom:4px;">Espace admin</h2>
            <p style="font-family:'Raleway',sans-serif;font-size:0.85rem;
                      color:#7b7551;margin-bottom:24px;">Réservé aux mariés</p>
        </div>
    </div>
    """, unsafe_allow_html=True)
    pwd = st.text_input("Mot de passe", type="password")
    if st.button("Accéder", use_container_width=True):
        if pwd == ADMIN_PWD:
            st.session_state.admin_ok = True
            st.rerun()
        else:
            st.error("Mot de passe incorrect.")
    st.stop()

# ── DASHBOARD ─────────────────────────────────────────────────────────────────
nav_bar()
st.markdown("""
<div class="hero" style="padding:40px 24px 30px;">
    <h1 class="hero-names" style="font-size:clamp(1.8rem,5vw,3rem);">🔐 Espace Admin</h1>
    <p class="hero-date">Liste des invités confirmés</p>
</div>
""", unsafe_allow_html=True)

df = get_all_rsvps()

# ── KPIs ──────────────────────────────────────────────────────────────────────
st.markdown('<div style="max-width:960px;margin:0 auto;padding:32px 24px;">', unsafe_allow_html=True)

if df.empty:
    st.info("Aucune réponse reçue pour l'instant.")
else:
    presence_col = "presence" if "presence" in df.columns else None

    oui  = len(df[df[presence_col].str.contains("Oui", na=False)]) if presence_col else 0
    non  = len(df[df[presence_col].str.contains("Non", na=False)]) if presence_col else 0
    peut = len(df[df[presence_col].str.contains("Peut", na=False)]) if presence_col else 0
    nb_col = "nb_personnes" if "nb_personnes" in df.columns else None
    total_personnes = int(df[df[presence_col].str.contains("Oui", na=False)][nb_col].sum()) if (presence_col and nb_col) else 0

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Réponses totales",  len(df))
    k2.metric("✅ Présents",       oui)
    k3.metric("❌ Absents",        non)
    k4.metric("🤔 Peut-être",      peut)
    k5.metric("👥 Personnes",      total_personnes)

    st.divider()

    # Filtres
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        filtre = st.selectbox("Filtrer par présence", ["Tous", "✅ Présents", "❌ Absents", "🤔 Peut-être"])
    with col_f2:
        st.caption(f"Stockage : **{storage_mode()}**")

    display = df.copy()
    if filtre != "Tous" and presence_col:
        keyword = filtre.split(" ", 1)[1] if " " in filtre else filtre
        display = display[display[presence_col].str.contains(keyword, na=False)]

    st.dataframe(display, use_container_width=True, hide_index=True)

    # Export
    csv_data = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "📥 Télécharger la liste complète (CSV)",
        data=csv_data,
        file_name="rsvp_ata_se_adakou.csv",
        mime="text/csv",
        use_container_width=True,
    )

st.markdown('</div>', unsafe_allow_html=True)

if st.button("🚪 Se déconnecter"):
    st.session_state.admin_ok = False
    st.rerun()

st.markdown(f"""
<div class="site-footer">Adakou &amp; Ata-Sé &nbsp;·&nbsp; {WEDDING_DATE_STR} &nbsp;·&nbsp; {LOCATION}</div>
""", unsafe_allow_html=True)

import streamlit as st
import os
import sys
import os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.styles import CSS, WEDDING_DATE_STR, COUPLE, LOCATION, nav_bar

st.set_page_config(page_title="Galerie — Adakou & Ata-Sé", page_icon="📸", layout="wide", initial_sidebar_state="collapsed")
st.markdown(CSS, unsafe_allow_html=True)
nav_bar()

st.markdown("""
<div class="hero" style="padding:50px 24px 40px;">
    <p class="hero-eyebrow">Nos plus beaux moments</p>
    <h1 class="hero-names" style="font-size:clamp(2rem,6vw,4rem);">Galerie</h1>
    <div class="hero-ornament">✦</div>
</div>
""", unsafe_allow_html=True)

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")
photos = []
if os.path.exists(ASSETS_DIR):
    photos = [
        os.path.join(ASSETS_DIR, f)
        for f in sorted(os.listdir(ASSETS_DIR))
        if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))
    ]

if photos:
    cols_per_row = 3
    rows = [photos[i:i+cols_per_row] for i in range(0, len(photos), cols_per_row)]
    for row in rows:
        cols = st.columns(cols_per_row)
        for col, photo in zip(cols, row):
            with col:
                st.image(photo, use_container_width=True)
else:
    st.markdown("""
    <div class="section">
        <div style="background:white;border-radius:16px;padding:60px 40px;
                    box-shadow:0 2px 16px rgba(0,0,0,0.07);max-width:500px;margin:0 auto;">
            <p style="font-size:3rem;text-align:center;margin-bottom:20px;">📸</p>
            <p class="section-text" style="text-align:center;">
                Les photos seront bientôt disponibles.<br>
                Revenez nous voir !
            </p>
        </div>
    </div>
    """, unsafe_allow_html=True)

st.markdown(f"""
<div class="site-footer">Adakou &amp; Ata-Sé &nbsp;·&nbsp; {WEDDING_DATE_STR} &nbsp;·&nbsp; {LOCATION}</div>
""", unsafe_allow_html=True)

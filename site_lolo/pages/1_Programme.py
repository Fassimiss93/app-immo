import streamlit as st
import sys
import os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.styles import CSS, WEDDING_DATE_STR, COUPLE, LOCATION, nav_bar

st.set_page_config(page_title="Programme — Adakou & Ata-Sé", page_icon="📅", layout="wide", initial_sidebar_state="collapsed")
st.markdown(CSS, unsafe_allow_html=True)
nav_bar()

st.markdown("""
<div class="hero" style="padding:50px 24px 40px;">
    <p class="hero-eyebrow">Le déroulé de notre grand jour</p>
    <h1 class="hero-names" style="font-size:clamp(2rem,6vw,4rem);">Programme</h1>
    <div class="hero-ornament">✦</div>
</div>
""", unsafe_allow_html=True)

# ── ÉVÉNEMENTS ────────────────────────────────────────────────────────────────
# TODO: Remplace les informations ci-dessous par les vraies informations du mariage

events = [
    {
        "jour":    "Samedi 29 Août 2026",
        "nom":     "Cérémonie de Mariage",
        "heure":   "🕙 À préciser",
        "lieu":    "📍 À préciser — Lomé, Togo",
        "desc":    "",
        "maps":    "",
    },
    {
        "jour":    "Samedi 29 Août 2026",
        "nom":     "Réception & Célébration",
        "heure":   "🕐 À préciser",
        "lieu":    "📍 À préciser — Lomé, Togo",
        "desc":    "",
        "maps":    "",
    },
]

st.markdown('<div style="max-width:760px;margin:0 auto;padding:40px 24px;">', unsafe_allow_html=True)

for ev in events:
    maps_btn = f'<a href="{ev["maps"]}" target="_blank" style="display:inline-block;margin-top:14px;padding:8px 20px;background:#d5872d;color:white;border-radius:50px;font-family:Raleway,sans-serif;font-size:0.78rem;font-weight:600;letter-spacing:0.1em;text-decoration:none;text-transform:uppercase;">📍 Voir sur la carte</a>' if ev["maps"] else ""
    st.markdown(f"""
    <div class="event-card">
        <p class="event-day">{ev["jour"]}</p>
        <h3 class="event-name">{ev["nom"]}</h3>
        <p class="event-detail">
            {ev["heure"]}<br>
            {ev["lieu"]}<br><br>
            {ev["desc"]}
        </p>
        {maps_btn}
    </div>
    """, unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)

# ── AJOUTER AU CALENDRIER ─────────────────────────────────────────────────────
st.markdown("""
<div class="section" style="padding-top:20px;">
    <h2 class="section-title">Ne l'oublie pas !</h2>
    <div class="section-orn">✦</div>
    <p class="section-text">Enregistre la date dans ton calendrier pour ne rien manquer.</p>
</div>
""", unsafe_allow_html=True)

col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    # Lien Google Calendar
    gcal = "https://calendar.google.com/calendar/r/eventedit?text=Mariage+Ata-S%C3%A9+%26+Adakou&dates=20260829/20260830&location=Lom%C3%A9,+Togo"
    st.markdown(f"""
    <div style="text-align:center;margin-top:10px;">
        <a href="{gcal}" target="_blank"
           style="display:inline-block;padding:14px 36px;
                  background:linear-gradient(135deg,#d5872d,#c07020);
                  color:white;border-radius:50px;text-decoration:none;
                  font-family:'Raleway',sans-serif;font-size:0.85rem;
                  font-weight:600;letter-spacing:0.15em;text-transform:uppercase;">
            📅 Ajouter à Google Calendar
        </a>
    </div>
    """, unsafe_allow_html=True)

st.markdown(f"""
<div class="site-footer">Adakou &amp; Ata-Sé &nbsp;·&nbsp; {WEDDING_DATE_STR} &nbsp;·&nbsp; {LOCATION}</div>
""", unsafe_allow_html=True)

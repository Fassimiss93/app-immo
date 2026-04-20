import streamlit as st
import sys
import os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.styles import CSS, WEDDING_DATE_STR, LOCATION, nav_bar

st.set_page_config(page_title="Infos pratiques — Adakou & Ata-Sé", page_icon="ℹ️", layout="wide", initial_sidebar_state="collapsed")
st.markdown(CSS, unsafe_allow_html=True)
nav_bar()

st.markdown("""
<div class="hero" style="padding:50px 24px 40px;">
    <p class="hero-eyebrow">Tout ce que vous devez savoir</p>
    <h1 class="hero-names" style="font-size:clamp(2rem,6vw,4rem);">Infos pratiques</h1>
    <div class="hero-ornament">✦</div>
</div>
""", unsafe_allow_html=True)

st.markdown('<div style="max-width:760px;margin:0 auto;padding:40px 24px;">', unsafe_allow_html=True)

# ── DRESS CODE ────────────────────────────────────────────────────────────────
st.markdown("""
<div style="background:white;border-radius:14px;padding:32px 36px;
            box-shadow:0 2px 16px rgba(0,0,0,0.07);margin-bottom:24px;
            border-top:4px solid #d5872d;">
    <h3 style="font-family:'Cormorant Garamond',serif;font-size:1.8rem;
               font-weight:400;color:#2c2416;margin-bottom:6px;">
        👗 Dress Code
    </h3>
    <div style="width:30px;height:2px;background:#d5872d;margin-bottom:16px;"></div>
    <p style="font-family:'Raleway',sans-serif;font-weight:300;color:#5a5040;
              font-size:0.95rem;line-height:1.8;">
        <!-- TODO: Remplace par le dress code souhaité -->
        Tenue élégante de mise. Couleurs à éviter : blanc et ivoire.<br><br>
        Venez célébrer avec nous dans vos plus beaux atours !<br>
        <strong style="color:#d5872d;">Code couleur suggéré :</strong> à préciser.
    </p>
</div>
""", unsafe_allow_html=True)

# ── HÉBERGEMENT ───────────────────────────────────────────────────────────────
st.markdown("""
<div style="background:white;border-radius:14px;padding:32px 36px;
            box-shadow:0 2px 16px rgba(0,0,0,0.07);margin-bottom:24px;
            border-top:4px solid #7b7551;">
    <h3 style="font-family:'Cormorant Garamond',serif;font-size:1.8rem;
               font-weight:400;color:#2c2416;margin-bottom:6px;">
        🏨 Hébergement
    </h3>
    <div style="width:30px;height:2px;background:#7b7551;margin-bottom:16px;"></div>
    <p style="font-family:'Raleway',sans-serif;font-weight:300;color:#5a5040;
              font-size:0.95rem;line-height:1.8;">
        <!-- TODO: Ajoute des suggestions d'hôtels à Lomé -->
        Des suggestions d'hébergement à Lomé seront bientôt disponibles.<br><br>
        Pour tout renseignement, n'hésitez pas à contacter les mariés.
    </p>
</div>
""", unsafe_allow_html=True)

# ── TRANSPORT ─────────────────────────────────────────────────────────────────
st.markdown("""
<div style="background:white;border-radius:14px;padding:32px 36px;
            box-shadow:0 2px 16px rgba(0,0,0,0.07);margin-bottom:32px;
            border-top:4px solid #d5872d;">
    <h3 style="font-family:'Cormorant Garamond',serif;font-size:1.8rem;
               font-weight:400;color:#2c2416;margin-bottom:6px;">
        ✈️ Venir à Lomé
    </h3>
    <div style="width:30px;height:2px;background:#d5872d;margin-bottom:16px;"></div>
    <p style="font-family:'Raleway',sans-serif;font-weight:300;color:#5a5040;
              font-size:0.95rem;line-height:1.8;">
        <strong style="color:#2c2416;">Aéroport :</strong> Aéroport International Gnassingbé Eyadéma (LFW), Lomé<br>
        <strong style="color:#2c2416;">Transport :</strong> Taxis et VTC disponibles depuis l'aéroport.<br><br>
        <!-- TODO: Ajoute des infos spécifiques sur le transport -->
        Des informations complémentaires seront ajoutées prochainement.
    </p>
</div>
""", unsafe_allow_html=True)

# ── FAQ ───────────────────────────────────────────────────────────────────────
st.markdown("""
<h2 style="font-family:'Cormorant Garamond',serif;font-size:2rem;
           font-weight:400;color:#2c2416;text-align:center;margin-bottom:6px;">
    Questions fréquentes
</h2>
<div style="text-align:center;color:#d5872d;margin-bottom:24px;">✦</div>
""", unsafe_allow_html=True)

faqs = [
    ("Puis-je venir avec mes enfants ?",
     "TODO: Réponse à compléter."),
    ("Y aura-t-il un parking sur place ?",
     "TODO: Réponse à compléter."),
    ("Comment confirmer ma présence ?",
     "Rendez-vous dans l'onglet RSVP de ce site. Merci de confirmer votre présence avant le TODO."),
    ("Puis-je offrir un cadeau ?",
     "TODO: Réponse à compléter."),
    ("Comment vous contacter ?",
     "TODO: Coordonnées de contact à ajouter."),
]

for q, a in faqs:
    st.markdown(f"""
    <div class="faq-item">
        <p class="faq-q">❓ {q}</p>
        <p class="faq-a">{a}</p>
    </div>
    """, unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)

st.markdown(f"""
<div class="site-footer">Adakou &amp; Ata-Sé &nbsp;·&nbsp; {WEDDING_DATE_STR} &nbsp;·&nbsp; {LOCATION}</div>
""", unsafe_allow_html=True)

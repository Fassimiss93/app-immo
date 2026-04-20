import streamlit as st
import sys
import os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.styles import CSS, WEDDING_DATE_STR, LOCATION, nav_bar
from utils.sheets import save_rsvp

st.set_page_config(page_title="RSVP — Adakou & Ata-Sé", page_icon="💌", layout="wide", initial_sidebar_state="collapsed")
st.markdown(CSS, unsafe_allow_html=True)
nav_bar()

st.markdown("""
<div class="hero" style="padding:50px 24px 40px;">
    <p class="hero-eyebrow">Serez-vous des nôtres ?</p>
    <h1 class="hero-names" style="font-size:clamp(2rem,6vw,4rem);">Confirmer ma présence</h1>
    <div class="hero-ornament">✦</div>
    <p class="hero-date">Merci de répondre avant le TODO: date limite</p>
</div>
""", unsafe_allow_html=True)

if "rsvp_sent" not in st.session_state:
    st.session_state.rsvp_sent = False

if st.session_state.rsvp_sent:
    st.markdown("""
    <div style="max-width:560px;margin:60px auto;padding:0 24px;">
        <div style="background:white;border-radius:16px;padding:50px 44px;
                    box-shadow:0 4px 30px rgba(0,0,0,0.08);text-align:center;">
            <div style="font-size:3.5rem;margin-bottom:20px;">💌</div>
            <h2 style="font-family:'Cormorant Garamond',serif;font-size:2rem;
                       font-weight:400;color:#2c2416;margin-bottom:12px;">
                Merci pour votre réponse !
            </h2>
            <p style="font-family:'Raleway',sans-serif;font-weight:300;
                      color:#5a5040;font-size:0.95rem;line-height:1.8;">
                Votre confirmation a bien été enregistrée.<br>
                Nous avons hâte de fêter ce jour avec vous ! 🎉
            </p>
        </div>
    </div>
    """, unsafe_allow_html=True)
    if st.button("↩ Nouvelle réponse", use_container_width=False):
        st.session_state.rsvp_sent = False
        st.rerun()

else:
    st.markdown('<div class="rsvp-wrap">', unsafe_allow_html=True)
    st.markdown("""
    <div class="rsvp-card">
        <h3 style="font-family:'Cormorant Garamond',serif;font-size:1.6rem;
                   font-weight:400;color:#2c2416;margin-bottom:4px;">
            Votre confirmation
        </h3>
        <div style="width:30px;height:2px;background:#d5872d;margin-bottom:24px;"></div>
    </div>
    """, unsafe_allow_html=True)

    with st.form("rsvp_form", clear_on_submit=True):
        col_a, col_b = st.columns(2)
        with col_a:
            prenom = st.text_input("Prénom *")
        with col_b:
            nom = st.text_input("Nom *")

        presence = st.radio(
            "Présence *",
            ["✅ Oui, je serai là !", "❌ Non, je ne pourrai pas venir"],
            horizontal=True,
        )

        nb_personnes = st.number_input(
            "Nombre de personnes (vous inclus) *",
            min_value=1, max_value=20, value=1, step=1,
        )

        regime = st.multiselect(
            "Régime alimentaire (optionnel)",
            ["Végétarien", "Végétalien", "Sans gluten", "Sans porc", "Allergie aux fruits de mer", "Autre"],
        )

        message = st.text_area(
            "Un message pour les mariés (optionnel)",
            placeholder="Vos vœux, un mot doux…",
            max_chars=300,
        )

        submitted = st.form_submit_button("💌 Envoyer ma réponse", use_container_width=True)

        if submitted:
            if not prenom.strip() or not nom.strip():
                st.error("Merci de renseigner votre prénom et nom.")
            else:
                save_rsvp({
                    "prenom":       prenom.strip(),
                    "nom":          nom.strip(),
                    "presence":     presence,
                    "nb_personnes": nb_personnes,
                    "regime":       ", ".join(regime),
                    "message":      message.strip(),
                })
                st.session_state.rsvp_sent = True
                st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)

st.markdown(f"""
<div class="site-footer">Adakou &amp; Ata-Sé &nbsp;·&nbsp; {WEDDING_DATE_STR} &nbsp;·&nbsp; {LOCATION}</div>
""", unsafe_allow_html=True)

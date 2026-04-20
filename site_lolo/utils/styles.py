CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,600;1,400&family=Raleway:wght@300;400;500;600;700&display=swap');

#MainMenu, footer, header { visibility: hidden; }
[data-testid="stSidebarNav"] li:first-child { display: none; }
.block-container { padding-top: 0 !important; max-width: 100% !important; }
section[data-testid="stSidebar"] { background: #2c2416 !important; }
section[data-testid="stSidebar"] * { color: #f4f4f8 !important; }

body, .stApp { background-color: #f4f4f8; font-family: 'Raleway', sans-serif; }

/* ── HERO ── */
.hero {
    background: linear-gradient(160deg, #2c2416 0%, #4a3728 60%, #7b7551 100%);
    padding: 80px 24px 60px;
    text-align: center;
    position: relative;
    overflow: hidden;
}
.hero::before {
    content: '';
    position: absolute; top: 0; left: 0; right: 0; bottom: 0;
    background: radial-gradient(ellipse at 50% 40%, rgba(213,135,45,0.18) 0%, transparent 65%);
}
.hero-eyebrow {
    font-family: 'Raleway', sans-serif;
    font-size: 0.8rem; font-weight: 500;
    letter-spacing: 0.4em; text-transform: uppercase;
    color: rgba(244,244,248,0.65); margin-bottom: 20px;
    position: relative; z-index: 1;
}
.hero-names {
    font-family: 'Cormorant Garamond', serif;
    font-size: clamp(3.2rem, 9vw, 6.5rem);
    font-weight: 300; color: #f4f4f8;
    margin: 0; letter-spacing: 0.04em;
    position: relative; z-index: 1; line-height: 1.1;
}
.hero-amp { color: #d5872d; font-style: italic; }
.hero-ornament { color: #d5872d; font-size: 1.4rem; margin: 18px 0; position: relative; z-index: 1; }
.hero-date {
    font-family: 'Raleway', sans-serif;
    font-size: 0.95rem; font-weight: 400;
    letter-spacing: 0.35em; text-transform: uppercase;
    color: rgba(244,244,248,0.75);
    position: relative; z-index: 1;
}

/* ── COUNTDOWN ── */
.countdown-wrap {
    display: flex; justify-content: center; gap: 20px;
    margin: 40px auto 0; max-width: 480px; padding: 0 24px;
}
.cd-box {
    background: white; border-radius: 12px; padding: 18px 20px;
    text-align: center; flex: 1;
    box-shadow: 0 4px 20px rgba(213,135,45,0.12);
    border-bottom: 3px solid #d5872d;
}
.cd-num {
    font-family: 'Cormorant Garamond', serif;
    font-size: 2.8rem; font-weight: 600; color: #d5872d;
    line-height: 1; display: block;
}
.cd-lbl {
    font-family: 'Raleway', sans-serif;
    font-size: 0.62rem; font-weight: 600;
    letter-spacing: 0.2em; text-transform: uppercase;
    color: #7b7551; margin-top: 6px; display: block;
}

/* ── SECTIONS ── */
.section { max-width: 860px; margin: 0 auto; padding: 60px 24px; text-align: center; }
.section-title {
    font-family: 'Cormorant Garamond', serif;
    font-size: 2.4rem; font-weight: 400; color: #2c2416; margin-bottom: 6px;
}
.section-orn { color: #d5872d; font-size: 1.1rem; margin: 6px 0 22px; }
.section-text {
    font-family: 'Raleway', sans-serif;
    font-size: 1rem; font-weight: 300; color: #5a5040; line-height: 1.9;
}

/* ── CARDS ── */
.event-card {
    background: white; border-radius: 14px; padding: 32px 36px;
    box-shadow: 0 2px 16px rgba(0,0,0,0.07);
    border-left: 4px solid #d5872d;
    margin-bottom: 20px; text-align: left;
}
.event-day {
    font-family: 'Raleway', sans-serif; font-size: 0.7rem;
    font-weight: 700; letter-spacing: 0.25em; text-transform: uppercase;
    color: #d5872d; margin-bottom: 8px;
}
.event-name {
    font-family: 'Cormorant Garamond', serif;
    font-size: 1.8rem; font-weight: 400; color: #2c2416;
}
.event-detail {
    font-family: 'Raleway', sans-serif; font-size: 0.9rem;
    font-weight: 400; color: #7b7551; margin-top: 10px; line-height: 1.7;
}

/* ── PERSON CARD ── */
.person-card {
    background: white; border-radius: 14px; padding: 24px 20px;
    text-align: center; box-shadow: 0 2px 12px rgba(0,0,0,0.06);
    border-top: 3px solid #7b7551;
}
.person-avatar {
    width: 80px; height: 80px; border-radius: 50%;
    background: linear-gradient(135deg, #d5872d, #7b7551);
    margin: 0 auto 14px; display: flex; align-items: center;
    justify-content: center; font-size: 2rem;
}
.person-name {
    font-family: 'Cormorant Garamond', serif;
    font-size: 1.2rem; color: #2c2416;
}
.person-role {
    font-family: 'Raleway', sans-serif; font-size: 0.72rem;
    font-weight: 600; letter-spacing: 0.15em; text-transform: uppercase;
    color: #d5872d; margin-top: 4px;
}

/* ── RSVP FORM ── */
.rsvp-wrap { max-width: 620px; margin: 0 auto; padding: 0 24px 60px; }
.rsvp-card {
    background: white; border-radius: 16px; padding: 40px 44px;
    box-shadow: 0 4px 30px rgba(0,0,0,0.08);
}
.stButton > button {
    background: linear-gradient(135deg, #d5872d, #c07020) !important;
    color: white !important; border: none !important;
    border-radius: 50px !important; padding: 12px 40px !important;
    font-family: 'Raleway', sans-serif !important;
    font-size: 0.9rem !important; font-weight: 600 !important;
    letter-spacing: 0.15em !important; text-transform: uppercase !important;
    width: 100% !important; margin-top: 12px !important;
}
.stButton > button:hover { opacity: 0.9 !important; }

/* ── FAQ ── */
.faq-item {
    background: white; border-radius: 12px; padding: 20px 26px;
    margin-bottom: 12px; border-left: 3px solid #7b7551;
    box-shadow: 0 1px 8px rgba(0,0,0,0.05);
}
.faq-q {
    font-family: 'Raleway', sans-serif; font-weight: 600;
    color: #2c2416; font-size: 0.95rem; margin-bottom: 8px;
}
.faq-a {
    font-family: 'Raleway', sans-serif; font-weight: 300;
    color: #5a5040; font-size: 0.9rem; line-height: 1.7;
}

/* ── FOOTER ── */
.site-footer {
    text-align: center; padding: 40px 24px;
    font-family: 'Raleway', sans-serif; font-size: 0.8rem;
    color: #9a8e80; letter-spacing: 0.1em;
    border-top: 1px solid rgba(123,117,81,0.2);
}
</style>
"""

WEDDING_DATE_STR = "29 Août 2026"
COUPLE = "Adakou & Ata-Sé"
LOCATION = "Lomé, Togo"


def nav_bar():
    import streamlit as st
    st.markdown("""
    <div style="background:white;border-bottom:1px solid rgba(213,135,45,0.2);
                padding:10px 24px;margin-bottom:0;">
    </div>
    """, unsafe_allow_html=True)
    col1, col2 = st.columns([1, 8])
    with col1:
        st.page_link("app.py", label="← Accueil", use_container_width=True)

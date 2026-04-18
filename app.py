import streamlit as st

st.set_page_config(page_title="App Immo", page_icon="📊", layout="wide")

APP_PASSWORD = st.secrets.get("app_password", "demo_app")

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if "portage_auth" not in st.session_state:
    st.session_state.portage_auth = False


def login_app() -> None:
    st.title("🔐 Connexion")
    st.write("Veuillez saisir le mot de passe pour accéder à l'application.")

    password = st.text_input("Mot de passe", type="password", key="app_login_password")

    if st.button("Se connecter", key="app_login_button"):
        if password == APP_PASSWORD:
            st.session_state.authenticated = True
            st.success("Connexion réussie")
            st.rerun()
        else:
            st.error("Mot de passe incorrect")


if not st.session_state.authenticated:
    login_app()
    st.stop()

# ── Page d'accueil ────────────────────────────────────────────────────────────
st.title("📊 Application financière & pronostics")
st.caption("Bienvenue ! Utilisez le menu à gauche pour naviguer entre les outils.")

st.divider()

col1, col2 = st.columns(2)

with col1:
    st.subheader("💸 Charges")
    st.write(
        "Suivi et répartition des charges du couple. "
        "Saisissez vos dépenses mensuelles (loyer, alimentation, transport…) "
        "et visualisez la répartition par catégorie et par personne."
    )

    st.subheader("🏠 Projet immobilier")
    st.write(
        "Simulateur d'achat immobilier pour couple. "
        "Calcule la capacité d'emprunt, les mensualités, le coût total du crédit "
        "et le reste à vivre selon vos revenus et vos charges actuelles."
    )

with col2:
    st.subheader("💼 Portage salarial")
    st.write(
        "Simulation complète du portage salarial : calcul du salaire net à partir "
        "du chiffre d'affaires, simulation des cotisations, frais de gestion, "
        "charges patronales et salariales. Accès protégé par un second mot de passe."
    )

    st.subheader("⚽ Pronostics foot")
    st.write(
        "Analyse automatique des matchs du jour via FootMercato. "
        "Agrège les probabilités du site (pré-match), les cotes bookmakers, "
        "les votes communauté, la forme récente et le H2H pour produire "
        "un signal de pari pondéré (1, N, 2, Double Chance, DNB). "
        "Trois niveaux de confiance : ⭐ Premium · 🟢 Sûr · 🟡 Prudent. "
        "Supporte le rendu JavaScript via Playwright pour une couverture maximale."
    )

st.divider()

if st.button("Se déconnecter", key="logout_button"):
    st.session_state.authenticated = False
    st.session_state.portage_auth = False
    st.rerun()

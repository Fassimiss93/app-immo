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

st.title("📊 Application financière")

st.write("Utilise le menu à gauche pour naviguer :")
st.write("- 💸 Charges")
st.write("- 🏠 Projet immobilier")
st.write("- 💼 Portage salarial")

st.info(
    "La page Portage salarial est protégée par un second mot de passe spécifique."
)

if st.button("Se déconnecter", key="logout_button"):
    st.session_state.authenticated = False
    st.session_state.portage_auth = False
    st.rerun()
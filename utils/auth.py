import streamlit as st


def require_auth() -> None:
    """Bloque la page si l'utilisateur n'est pas authentifié."""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        st.error("🔒 Accès refusé. Veuillez vous connecter depuis la page d'accueil.")
        st.page_link("app.py", label="← Retour à la connexion", icon="🔐")
        st.stop()

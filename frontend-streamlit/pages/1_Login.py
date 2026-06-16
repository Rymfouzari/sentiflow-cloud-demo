import streamlit as st
import importlib
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Forcer le rechargement du module api à chaque exécution
if "components.api" in sys.modules:
    importlib.reload(sys.modules["components.api"])

from components.api import login, register, get_me

# Rediriger si déjà connecté
if st.session_state.get("token"):
    st.switch_page("pages/2_Dashboard.py")

st.title("🔐 Connexion")

tab1, tab2 = st.tabs(["Connexion", "Inscription"])

with tab1:
    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Mot de passe", type="password")
        submitted = st.form_submit_button("Se connecter")

        if submitted:
            success, message, result = login(email, password)
            if success:
                st.session_state.token = result["access_token"]
                st.session_state.user = get_me()
                st.success(message)
                st.switch_page("pages/2_Dashboard.py")
            else:
                st.error(message)

with tab2:
    with st.form("register_form"):
        email = st.text_input("Email", key="reg_email")
        username = st.text_input("Nom d'utilisateur")
        password = st.text_input("Mot de passe", type="password", key="reg_pass")
        password2 = st.text_input("Confirmer le mot de passe", type="password")
        submitted = st.form_submit_button("S'inscrire")

        if submitted:
            if password != password2:
                st.error("Les mots de passe ne correspondent pas")
            elif len(password) < 6:
                st.error("Le mot de passe doit faire au moins 6 caractères")
            else:
                success, message = register(email, username, password)
                if success:
                    st.success(message + " Vous pouvez vous connecter.")
                else:
                    st.error(message)
